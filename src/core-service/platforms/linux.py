"""
platforms/linux.py
==================
Linux platform adapter for BatteryOS.

Battery reads
-------------
Reads directly from the kernel's ``/sys/class/power_supply/BAT*`` sysfs
interface — no external tools required.

Charge control
--------------
Priority order:
  1. ``charge_stop_threshold`` / ``charge_start_threshold`` sysfs nodes
     (ThinkPad ACPI, ASUS, and other OEMs via kernel drivers).
  2. ``batteryos-linux`` native helper binary (compiled from native-modules/).
  3. TLP CLI (``tlp`` must be installed) — graceful fallback.

All write operations require either root privileges or a udev rule such as:

    SUBSYSTEM=="power_supply", ATTR{status}=="*", \\
    RUN+="/bin/chmod 666 /sys/class/power_supply/BAT0/charge_stop_threshold"
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

import psutil

from . import BasePlatform
from ..utils import BatterySnapshot, get_logger

logger = get_logger(__name__)

# sysfs base
_POWER_SUPPLY = Path("/sys/class/power_supply")

# Preferred battery names; fall back to scanning for any BAT*
_PREFERRED = ["BAT0", "BAT1", "BAT"]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _find_battery_path() -> Optional[Path]:
    """Return the sysfs path for the first detected battery."""
    for name in _PREFERRED:
        p = _POWER_SUPPLY / name
        if p.is_dir():
            return p
    # Generic scan
    if _POWER_SUPPLY.exists():
        for entry in sorted(_POWER_SUPPLY.iterdir()):
            if entry.name.startswith("BAT"):
                return entry
    return None


def _read_node(bat: Path, node: str) -> Optional[str]:
    """Read and strip a sysfs text node; return None on error."""
    try:
        return (bat / node).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _read_float(bat: Path, node: str) -> Optional[float]:
    raw = _read_node(bat, node)
    try:
        return float(raw) if raw is not None else None
    except ValueError:
        return None


def _read_int(bat: Path, node: str) -> Optional[int]:
    raw = _read_node(bat, node)
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


def _write_node(bat: Path, node: str, value: str) -> bool:
    """Write a value to a sysfs node; returns True on success."""
    try:
        (bat / node).write_text(value + "\n", encoding="utf-8")
        return True
    except PermissionError:
        logger.error(
            "Permission denied writing %s — run as root or add a udev rule.",
            bat / node,
        )
        return False
    except OSError as exc:
        logger.error("Could not write %s: %s", bat / node, exc)
        return False


def _run_helper(action: str) -> bool:
    """Invoke the batteryos-linux native helper binary."""
    try:
        result = subprocess.run(
            ["batteryos-linux", action],
            check=True, timeout=10,
            capture_output=True, text=True,
        )
        logger.debug("batteryos-linux %s: %s", action, result.stdout.strip())
        return True
    except FileNotFoundError:
        logger.debug("batteryos-linux helper not found.")
        return False
    except subprocess.CalledProcessError as exc:
        logger.warning("batteryos-linux %s failed (exit %d): %s",
                       action, exc.returncode, exc.stderr.strip())
        return False


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class LinuxPlatform(BasePlatform):
    """
    Battery management adapter for Linux using the sysfs power_supply class.
    """

    def __init__(self) -> None:
        self._bat: Optional[Path] = _find_battery_path()
        if self._bat:
            logger.info("Linux battery sysfs: %s", self._bat)
        else:
            logger.warning("No battery found in /sys/class/power_supply/")

    # ── Identification ────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "Linux"

    # ── Status ────────────────────────────────────────────────────────────

    def read_status(self) -> Optional[BatterySnapshot]:
        # psutil provides the cross-platform baseline
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

        # Enrich from sysfs when available
        if self._bat:
            self._enrich(snap)

        return snap

    def _enrich(self, snap: BatterySnapshot) -> None:
        """Fill extended fields from sysfs nodes."""
        bat = self._bat
        assert bat is not None

        # Energy (µWh → Wh)
        energy_now    = _read_float(bat, "energy_now")
        energy_full   = _read_float(bat, "energy_full")
        energy_design = _read_float(bat, "energy_full_design")
        power_now     = _read_float(bat, "power_now")

        if energy_now    is not None: energy_now    /= 1_000_000
        if energy_full   is not None: energy_full   /= 1_000_000
        if energy_design is not None: energy_design /= 1_000_000
        if power_now     is not None: power_now     /= 1_000_000

        if energy_full and energy_design and energy_design > 0:
            snap.health_percent = round(energy_full / energy_design * 100, 1)

        if power_now is not None:
            snap.power_watts = power_now if snap.charging else -power_now

        if energy_now and power_now and power_now > 0:
            if snap.charging and energy_full:
                snap.time_left_seconds = (energy_full - energy_now) / power_now * 3600
            elif not snap.charging:
                snap.time_left_seconds = energy_now / power_now * 3600

        voltage = _read_float(bat, "voltage_now")
        if voltage is not None:
            snap.voltage_volts = voltage / 1_000_000

        temp = _read_float(bat, "temp")
        if temp is not None:
            snap.temperature_celsius = temp / 10

        cycles = _read_int(bat, "cycle_count")
        if cycles is not None:
            snap.cycle_count = cycles

    # ── Charge control ────────────────────────────────────────────────────

    def stop_charging(self) -> None:
        logger.info("Linux: stopping charging.")
        if self._bat and self._write_threshold("charge_stop_threshold",
                                               int(psutil.sensors_battery().percent or 99)):
            return
        if _run_helper("stop"):
            return
        logger.warning("No supported charge-stop method found on this hardware.")

    def start_charging(self) -> None:
        logger.info("Linux: resuming charging.")
        if self._bat:
            self._write_threshold("charge_stop_threshold", 100)
            self._write_threshold("charge_start_threshold", 0)
            return
        if _run_helper("start"):
            return
        logger.warning("No supported charge-start method found on this hardware.")

    def set_charge_thresholds(self, min_pct: int, max_pct: int) -> None:
        logger.info("Linux: setting thresholds min=%d%% max=%d%%.", min_pct, max_pct)
        if self._bat:
            # Write stop first to avoid kernel rejection (stop must be ≥ start)
            ok_max = self._write_threshold("charge_stop_threshold",  max_pct)
            ok_min = self._write_threshold("charge_start_threshold", min_pct)
            if ok_max or ok_min:
                return
        _run_helper(f"set-thresholds {min_pct} {max_pct}")

    def _write_threshold(self, node: str, value: int) -> bool:
        if self._bat and (self._bat / node).exists():
            return _write_node(self._bat, node, str(value))
        return False
