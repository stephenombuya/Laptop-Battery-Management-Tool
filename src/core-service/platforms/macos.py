"""
platforms/macos.py
==================
macOS platform adapter for BatteryOS.

Battery reads
-------------
Parses ``ioreg -rn AppleSmartBattery`` output for rich battery data
(voltage, temperature, cycle count, health, amperage).  Uses ``psutil``
as the authoritative source for charge percentage and plug status since
it wraps the same IOKit API with proper error handling.

Charge control
--------------
Priority order:
  1. ``batteryos-macos`` native helper binary (compiled from native-modules/,
     uses IOKit + SMC BCLM/BCLB keys — most reliable).
  2. ``bclm`` open-source CLI tool (https://github.com/zackelia/bclm)
     if installed via Homebrew.
  3. ``pmset`` (read-only; charge control not supported but used for
     diagnostics / sleep settings).

The helper binary must run as root (or hold the battery entitlement) to
write charge thresholds.  The module logs a clear error when permission
is insufficient rather than crashing.
"""

from __future__ import annotations

import re
import subprocess
import time
from typing import Optional

import psutil

from . import BasePlatform
from ..utils import BatterySnapshot, get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# ioreg parsing helpers
# ---------------------------------------------------------------------------

def _ioreg_output() -> str:
    """Run ioreg and return its stdout as a string."""
    try:
        result = subprocess.run(
            ["ioreg", "-rn", "AppleSmartBattery"],
            capture_output=True, text=True, timeout=8, check=True,
        )
        return result.stdout
    except (FileNotFoundError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        logger.warning("ioreg failed: %s", exc)
        return ""


def _parse_int(text: str, key: str) -> Optional[int]:
    """Extract the integer value of a named IOKit property."""
    m = re.search(rf'"{re.escape(key)}"\s*=\s*(-?\d+)', text)
    return int(m.group(1)) if m else None


def _parse_bool(text: str, key: str) -> Optional[bool]:
    """Extract a boolean IOKit property (Yes/No or true/false)."""
    m = re.search(rf'"{re.escape(key)}"\s*=\s*(Yes|No|true|false)',
                  text, re.IGNORECASE)
    if not m:
        return None
    return m.group(1).lower() in ("yes", "true")


def _parse_str(text: str, key: str) -> Optional[str]:
    """Extract a string IOKit property."""
    m = re.search(rf'"{re.escape(key)}"\s*=\s*"([^"]*)"', text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Helper binary / CLI wrappers
# ---------------------------------------------------------------------------

def _run_helper(action: str) -> bool:
    """Invoke batteryos-macos native helper."""
    try:
        result = subprocess.run(
            ["batteryos-macos", action],
            check=True, timeout=10,
            capture_output=True, text=True,
        )
        logger.debug("batteryos-macos %s: %s", action, result.stdout.strip())
        return True
    except FileNotFoundError:
        logger.debug("batteryos-macos helper not found.")
        return False
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        if exc.returncode == 3:
            logger.error("batteryos-macos %s: permission denied — run as root.", action)
        elif exc.returncode == 4:
            logger.warning("batteryos-macos %s: not supported on this Mac.", action)
        else:
            logger.warning("batteryos-macos %s failed (exit %d): %s",
                           action, exc.returncode, stderr)
        return False


def _run_bclm(action: str, value: Optional[int] = None) -> bool:
    """
    Invoke the ``bclm`` Homebrew tool as a fallback.
    https://github.com/zackelia/bclm

    bclm read          — print current BCLM value
    bclm write <0-100> — set max charge level
    bclm persist       — persist across reboots
    """
    try:
        cmd = ["bclm", action]
        if value is not None:
            cmd.append(str(value))
        subprocess.run(cmd, check=True, timeout=10, capture_output=True)
        return True
    except FileNotFoundError:
        logger.debug("bclm not found — Homebrew fallback unavailable.")
        return False
    except subprocess.CalledProcessError as exc:
        logger.warning("bclm %s failed (exit %d).", action, exc.returncode)
        return False


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class MacOSPlatform(BasePlatform):
    """
    Battery management adapter for macOS using IOKit and SMC.
    """

    @property
    def name(self) -> str:
        return "macOS"

    # ── Status ────────────────────────────────────────────────────────────

    def read_status(self) -> Optional[BatterySnapshot]:
        # psutil baseline (authoritative for percent + plug status)
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

        # Enrich from ioreg
        self._enrich_from_ioreg(snap)
        return snap

    def _enrich_from_ioreg(self, snap: BatterySnapshot) -> None:
        """Parse ioreg output to fill extended battery fields."""
        raw = _ioreg_output()
        if not raw:
            return

        # Capacity & health
        max_cap    = _parse_int(raw, "MaxCapacity")
        design_cap = _parse_int(raw, "DesignCapacity")
        if max_cap and design_cap and design_cap > 0:
            snap.health_percent = round(max_cap / design_cap * 100, 1)

        # Voltage (mV → V)
        voltage_mv = _parse_int(raw, "Voltage")
        if voltage_mv is not None:
            snap.voltage_volts = voltage_mv / 1000.0

        # Amperage (mA) + voltage → watts
        amperage_ma = _parse_int(raw, "Amperage")
        if amperage_ma is not None and voltage_mv:
            snap.power_watts = (amperage_ma * voltage_mv) / 1_000_000.0

        # Temperature (hundredths of °C → °C)
        temp_raw = _parse_int(raw, "Temperature")
        if temp_raw is not None:
            snap.temperature_celsius = temp_raw / 100.0

        # Cycle count
        cycles = _parse_int(raw, "CycleCount")
        if cycles is not None:
            snap.cycle_count = cycles

        # Time remaining override (IOKit reports minutes)
        time_rem_min = _parse_int(raw, "TimeRemaining")
        if time_rem_min is not None and time_rem_min > 0:
            snap.time_left_seconds = time_rem_min * 60.0

    # ── Charge control ────────────────────────────────────────────────────

    def stop_charging(self) -> None:
        logger.info("macOS: stopping charging.")
        if _run_helper("stop"):
            return
        # bclm fallback: freeze at current percent
        raw = psutil.sensors_battery()
        pct = int(raw.percent) if raw else 80
        if _run_bclm("write", pct):
            _run_bclm("persist")
            return
        logger.warning(
            "Could not stop charging — install batteryos-macos or bclm."
        )

    def start_charging(self) -> None:
        logger.info("macOS: resuming charging.")
        if _run_helper("start"):
            return
        if _run_bclm("write", 100):
            _run_bclm("persist")
            return
        logger.warning(
            "Could not start charging — install batteryos-macos or bclm."
        )

    def set_charge_thresholds(self, min_pct: int, max_pct: int) -> None:
        logger.info("macOS: setting thresholds min=%d%% max=%d%%.", min_pct, max_pct)
        # Native helper supports both BCLM and BCLB
        if _run_helper(f"set-max {max_pct}") and _run_helper(f"set-min {min_pct}"):
            return
        # bclm only supports max (BCLM key)
        if _run_bclm("write", max_pct):
            _run_bclm("persist")
            if min_pct > 0:
                logger.info(
                    "macOS: min threshold (%d%%) not supported by bclm — "
                    "only max (%d%%) was applied.", min_pct, max_pct
                )
            return
        logger.warning(
            "Could not set charge thresholds on this Mac — "
            "install batteryos-macos (native) or bclm (Homebrew)."
        )
