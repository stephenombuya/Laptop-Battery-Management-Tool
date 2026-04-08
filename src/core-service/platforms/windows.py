"""
platforms/windows.py
====================
Windows platform adapter for BatteryOS.

Battery reads
-------------
Uses ``psutil`` as the primary source for charge percentage, plug status,
and time remaining.  Enriches the snapshot with WMI via the ``wmi`` package
for cycle count, health, voltage, and temperature when available.

Charge control
--------------
Priority order:
  1. ``batteryos-windows.exe`` native helper (compiled from native-modules/,
     uses IOCTL_BATTERY_* and WinAPI — requires Administrator privileges).
  2. ``powercfg`` CLI (built into Windows) for reading advanced battery
     reports and writing some OEM-specific settings.
  3. Smart-plug fallback via ``SmartPlugController`` in utils.py.

Administrator privileges are required for charge-control operations.
The module detects this and logs a clear error rather than crashing.

Dependencies
------------
  psutil      — cross-platform baseline (always available)
  wmi         — optional; used for extended fields (pip install wmi)
  pywin32     — optional; used for ctypes IOCTL calls
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from typing import Optional

import psutil

from . import BasePlatform
from ..utils import BatterySnapshot, get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# WMI helper (optional import)
# ---------------------------------------------------------------------------

try:
    import wmi as _wmi  # type: ignore[import]
    _WMI_AVAILABLE = True
except ImportError:
    _WMI_AVAILABLE = False
    logger.debug("wmi package not available — extended battery data limited.")


def _is_admin() -> bool:
    """Return True if the current process has Administrator privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except AttributeError:
        return False


# ---------------------------------------------------------------------------
# WMI enrichment helpers
# ---------------------------------------------------------------------------

def _wmi_battery_data() -> Optional[dict]:
    """
    Query Win32_Battery and BatteryFullChargedCapacity via WMI.
    Returns a dict of available fields or None on failure.
    """
    if not _WMI_AVAILABLE:
        return None
    try:
        c = _wmi.WMI()
        results = {}

        # Win32_Battery — basic info
        for bat in c.Win32_Battery():
            results["design_capacity_mwh"] = getattr(bat, "DesignCapacity", None)
            results["full_charge_capacity"] = getattr(bat, "FullChargeCapacity", None)
            results["cycle_count"]          = getattr(bat, "CycleCount",          None)
            results["voltage_mv"]           = getattr(bat, "DesignVoltage",        None)
            results["chemistry"]            = getattr(bat, "Chemistry",            None)
            results["manufacturer"]         = getattr(bat, "Manufacturer",         None)
            results["name"]                 = getattr(bat, "Name",                 None)
            break   # use only first battery

        # BatteryFullChargedCapacity (more accurate than Win32_Battery)
        try:
            for cap in c.BatteryFullChargedCapacity():
                results["full_charge_mwh"] = getattr(cap, "FullChargedCapacity", None)
                break
        except Exception:
            pass

        # BatteryCycleCount
        try:
            for cc in c.BatteryCycleCount():
                results["cycle_count"] = getattr(cc, "CycleCount", None)
                break
        except Exception:
            pass

        return results or None

    except Exception as exc:
        logger.debug("WMI query failed: %s", exc)
        return None


def _powercfg_battery_report() -> Optional[str]:
    """
    Run ``powercfg /batteryreport /output <temp> /xml`` and return the XML.
    Used for health and cycle-count data on machines without WMI access.
    This is slow (~1s) so it is called at most once per session.
    """
    import tempfile
    import os
    try:
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            tmp = f.name
        subprocess.run(
            ["powercfg", "/batteryreport", "/output", tmp, "/xml"],
            check=True, timeout=15, capture_output=True,
        )
        content = open(tmp, encoding="utf-8", errors="replace").read()
        os.unlink(tmp)
        return content
    except Exception as exc:
        logger.debug("powercfg battery report failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Native helper wrapper
# ---------------------------------------------------------------------------

def _run_helper(action: str) -> bool:
    """Invoke batteryos-windows.exe native helper."""
    try:
        result = subprocess.run(
            ["batteryos-windows.exe", action],
            check=True, timeout=10,
            capture_output=True, text=True,
        )
        logger.debug("batteryos-windows %s: %s", action, result.stdout.strip())
        return True
    except FileNotFoundError:
        logger.debug("batteryos-windows.exe helper not found.")
        return False
    except subprocess.CalledProcessError as exc:
        if exc.returncode == 3:
            logger.error(
                "batteryos-windows.exe %s: access denied — "
                "run BatteryOS as Administrator.", action
            )
        elif exc.returncode == 4:
            logger.warning(
                "batteryos-windows.exe %s: not supported on this hardware.", action
            )
        else:
            logger.warning(
                "batteryos-windows.exe %s failed (exit %d).", action, exc.returncode
            )
        return False


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class WindowsPlatform(BasePlatform):
    """
    Battery management adapter for Windows using psutil, WMI, and WinAPI.
    """

    def __init__(self) -> None:
        self._admin = _is_admin()
        if not self._admin:
            logger.warning(
                "BatteryOS is not running as Administrator — "
                "charge control operations will be unavailable."
            )
        # Cache WMI data (expensive call); refreshed every 10 ticks
        self._wmi_cache: Optional[dict] = None
        self._wmi_tick  = 0
        self._wmi_ttl   = 10

    @property
    def name(self) -> str:
        return "Windows"

    # ── Status ────────────────────────────────────────────────────────────

    def read_status(self) -> Optional[BatterySnapshot]:
        raw = psutil.sensors_battery()
        if raw is None:
            return None

        snap = BatterySnapshot(
            percent=round(raw.percent, 1),
            plugged_in=bool(raw.power_plugged),
            charging=bool(raw.power_plugged) and raw.percent < 100,
            time_left_seconds=(
                raw.secsleft
                if raw.secsleft not in (
                    psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN
                )
                else None
            ),
            timestamp=time.time(),
        )

        self._enrich_from_wmi(snap)
        return snap

    def _enrich_from_wmi(self, snap: BatterySnapshot) -> None:
        """Fill extended fields using cached WMI data."""
        self._wmi_tick += 1
        if self._wmi_cache is None or self._wmi_tick >= self._wmi_ttl:
            self._wmi_cache = _wmi_battery_data()
            self._wmi_tick  = 0

        data = self._wmi_cache
        if not data:
            return

        # Health
        full   = data.get("full_charge_mwh") or data.get("full_charge_capacity")
        design = data.get("design_capacity_mwh")
        if full and design and design > 0:
            snap.health_percent = round(full / design * 100, 1)

        # Cycle count
        cycles = data.get("cycle_count")
        if cycles is not None:
            snap.cycle_count = int(cycles)

        # Voltage (mV → V)
        voltage_mv = data.get("voltage_mv")
        if voltage_mv:
            snap.voltage_volts = voltage_mv / 1000.0

    # ── Charge control ────────────────────────────────────────────────────

    def stop_charging(self) -> None:
        if not self._admin:
            logger.error(
                "Cannot stop charging — relaunch BatteryOS as Administrator."
            )
            return
        logger.info("Windows: stopping charging.")
        if not _run_helper("stop"):
            logger.warning(
                "Charge-stop is not supported on this hardware. "
                "Consider using a smart plug (enable IoT integration)."
            )

    def start_charging(self) -> None:
        if not self._admin:
            logger.error(
                "Cannot start charging — relaunch BatteryOS as Administrator."
            )
            return
        logger.info("Windows: resuming charging.")
        if not _run_helper("start"):
            logger.warning(
                "Charge-start is not supported on this hardware."
            )

    def set_charge_thresholds(self, min_pct: int, max_pct: int) -> None:
        if not self._admin:
            logger.error(
                "Cannot set thresholds — relaunch BatteryOS as Administrator."
            )
            return
        logger.info("Windows: setting thresholds min=%d%% max=%d%%.", min_pct, max_pct)
        # Native helper handles OEM-specific ACPI/WMI threshold writes
        ok_max = _run_helper(f"set-max {max_pct}")
        ok_min = _run_helper(f"set-min {min_pct}")
        if not (ok_max or ok_min):
            logger.warning(
                "Charge threshold control is not supported on this Windows hardware. "
                "Supported OEMs: Lenovo ThinkPad (BatteryThreshold WMI), "
                "Dell (OMCI), ASUS (ATKACPI WMI). "
                "For unsupported hardware use IoT smart plug integration."
            )

    # ── Extras ───────────────────────────────────────────────────────────

    def generate_battery_report(self, output_path: str = "battery_report.html") -> bool:
        """
        Generate a full Windows battery report via ``powercfg``.
        Saved to ``output_path`` (HTML format).

        Returns True on success.
        """
        try:
            subprocess.run(
                ["powercfg", "/batteryreport", "/output", output_path],
                check=True, timeout=30, capture_output=True,
            )
            logger.info("Battery report saved: %s", output_path)
            return True
        except subprocess.CalledProcessError as exc:
            logger.error("powercfg /batteryreport failed: %s", exc)
            return False
