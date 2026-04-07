"""
core.py
=======
BatteryManager — the central monitoring and charge-control engine.

Responsibilities
----------------
* Poll battery status at a configurable interval via psutil.
* Enforce configurable charge thresholds (min / max).
* Issue OS-level charging-control commands through platform adapters.
* Emit desktop notifications on threshold events.
* Optionally toggle an IoT smart plug for physical power cutoff.
* Expose a thread-safe status snapshot for the GUI / IPC layer.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import psutil

from .utils import (
    detect_platform,
    get_logger,
    notify,
    stop_charging,
    start_charging,
    SmartPlugController,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class BatterySnapshot:
    """Immutable point-in-time view of battery state, safe to share across threads."""

    percent: float = 0.0
    charging: bool = False
    plugged_in: bool = False
    time_left_seconds: Optional[float] = None   # None == unknown
    power_watts: Optional[float] = None
    temperature_celsius: Optional[float] = None
    health_percent: Optional[float] = None
    cycle_count: Optional[int] = None
    voltage_volts: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def time_left_human(self) -> str:
        """Return a human-readable time-remaining string."""
        if self.time_left_seconds is None or self.time_left_seconds < 0:
            return "Unknown"
        hours, remainder = divmod(int(self.time_left_seconds), 3600)
        minutes = remainder // 60
        return f"{hours}h {minutes}m"


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class BatteryManager:
    """
    Monitor battery level and control charging to extend battery longevity.

    Parameters
    ----------
    max_charge_limit : int
        Stop charging when battery reaches this percentage (default 80).
    min_charge_limit : int
        Resume charging when battery falls to this percentage (default 20).
    check_interval : int
        Seconds between each status poll (default 300).
    smart_plug_enabled : bool
        When True, a physical smart plug is toggled alongside OS commands.
    log_level : str
        Logging verbosity passed through to the root logger.
    """

    def __init__(
        self,
        max_charge_limit: int = 80,
        min_charge_limit: int = 20,
        check_interval: int = 300,
        smart_plug_enabled: bool = False,
        log_level: str = "INFO",
    ) -> None:
        if not (0 <= min_charge_limit < max_charge_limit <= 100):
            raise ValueError(
                f"Invalid thresholds: min={min_charge_limit}, max={max_charge_limit}. "
                "Ensure 0 ≤ min < max ≤ 100."
            )

        self.max_charge_limit = max_charge_limit
        self.min_charge_limit = min_charge_limit
        self.check_interval = check_interval
        self.smart_plug_enabled = smart_plug_enabled

        self.platform = detect_platform()

        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._snapshot: BatterySnapshot = BatterySnapshot()
        self._smart_plug: Optional[SmartPlugController] = (
            SmartPlugController() if smart_plug_enabled else None
        )

        logger.setLevel(log_level)
        logger.info(
            "BatteryManager initialised — platform=%s, min=%d%%, max=%d%%, interval=%ds",
            self.platform, min_charge_limit, max_charge_limit, check_interval,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def snapshot(self) -> BatterySnapshot:
        """Thread-safe read of the latest battery snapshot."""
        with self._lock:
            return self._snapshot

    def run(self) -> None:
        """
        Start the blocking monitoring loop.
        Runs until :meth:`stop` is called from another thread.
        """
        logger.info("Monitoring loop started.")
        notify("BatteryOS", "Battery monitoring is now active.")

        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception:
                logger.exception("Unexpected error during battery check — will retry.")

            self._stop_event.wait(timeout=self.check_interval)

        logger.info("Monitoring loop stopped.")

    def stop(self) -> None:
        """Signal the monitoring loop to exit cleanly."""
        logger.info("Stop requested.")
        self._stop_event.set()

    def update_thresholds(self, min_limit: int, max_limit: int) -> None:
        """
        Update charge thresholds at runtime (e.g., from GUI or IPC).

        Raises
        ------
        ValueError
            If the new thresholds are logically invalid.
        """
        if not (0 <= min_limit < max_limit <= 100):
            raise ValueError(
                f"Invalid thresholds: min={min_limit}, max={max_limit}."
            )
        with self._lock:
            self.min_charge_limit = min_limit
            self.max_charge_limit = max_limit
        logger.info("Thresholds updated — min=%d%%, max=%d%%", min_limit, max_limit)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        """Perform one battery check cycle."""
        battery = psutil.sensors_battery()
        if battery is None:
            logger.warning("No battery detected — is this a desktop machine?")
            return

        snap = self._build_snapshot(battery)

        with self._lock:
            self._snapshot = snap

        self._log_status(snap)
        self._enforce_limits(snap)

    def _build_snapshot(self, battery: psutil._common.sbattery) -> BatterySnapshot:
        """Construct a BatterySnapshot from a raw psutil battery reading."""
        charging = battery.power_plugged and battery.percent < 100

        return BatterySnapshot(
            percent=round(battery.percent, 1),
            charging=charging,
            plugged_in=bool(battery.power_plugged),
            time_left_seconds=(
                battery.secsleft
                if battery.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN)
                else None
            ),
            timestamp=time.time(),
        )

    def _log_status(self, snap: BatterySnapshot) -> None:
        status = "charging" if snap.charging else ("plugged in (full)" if snap.plugged_in else "discharging")
        logger.info(
            "Battery: %.1f%% | %s | time left: %s",
            snap.percent, status, snap.time_left_human,
        )

    def _enforce_limits(self, snap: BatterySnapshot) -> None:
        """Apply charging-control logic based on current snapshot."""
        pct = snap.percent

        if snap.plugged_in and pct >= self.max_charge_limit and snap.charging:
            logger.warning(
                "Battery at %.1f%% — reached max limit (%d%%). Stopping charging.",
                pct, self.max_charge_limit,
            )
            self._halt_charging()
            notify(
                "BatteryOS — Charging Stopped",
                f"Battery reached {self.max_charge_limit}%. Charging halted to protect battery health.",
            )

        elif not snap.plugged_in and pct <= self.min_charge_limit:
            logger.warning(
                "Battery at %.1f%% — reached min limit (%d%%). Please plug in.",
                pct, self.min_charge_limit,
            )
            notify(
                "BatteryOS — Low Battery",
                f"Battery at {pct:.0f}%. Please connect your charger.",
            )

        elif snap.plugged_in and not snap.charging and pct < self.min_charge_limit:
            logger.info(
                "Battery at %.1f%% — below min limit while plugged in. Resuming charging.",
                pct,
            )
            self._resume_charging()

    def _halt_charging(self) -> None:
        """Stop charging via OS command and (optionally) smart plug."""
        stop_charging(self.platform)
        if self._smart_plug:
            self._smart_plug.turn_off()

    def _resume_charging(self) -> None:
        """Resume charging via OS command and (optionally) smart plug."""
        start_charging(self.platform)
        if self._smart_plug:
            self._smart_plug.turn_on()
