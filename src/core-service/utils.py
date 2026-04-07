"""
utils.py
========
Shared utilities for BatteryOS core service:

* Structured logging setup
* Cross-platform desktop notifications
* Platform detection
* OS-level charging control commands
* IoT smart-plug stub
"""

from __future__ import annotations

import logging
import platform
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOG_DIR = Path.home() / ".batteryos" / "logs"
_LOG_FILE = _LOG_DIR / "battery_manager.log"
_LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 5 * 1024 * 1024   # 5 MB per file
_BACKUP_COUNT = 3


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger that writes to both stderr and a rotating log file.

    The log directory is created on first call if it does not already exist.
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)

    if logger.handlers:
        # Already configured — avoid adding duplicate handlers
        return logger

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)

    # Rotating file handler — keeps up to 5 MB × 3 backup files
    file_handler = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

    return logger


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def detect_platform() -> str:
    """
    Return a normalised platform identifier: 'windows', 'macos', or 'linux'.

    Raises
    ------
    RuntimeError
        If the current OS is not supported.
    """
    system = platform.system().lower()
    mapping = {
        "windows": "windows",
        "darwin": "macos",
        "linux": "linux",
    }
    result = mapping.get(system)
    if result is None:
        raise RuntimeError(
            f"Unsupported operating system: '{platform.system()}'. "
            "BatteryOS supports Windows, macOS, and Linux."
        )
    return result


# ---------------------------------------------------------------------------
# Desktop notifications
# ---------------------------------------------------------------------------

def notify(title: str, message: str) -> None:
    """
    Send a non-blocking desktop notification using the best available method
    for the current platform.  Failures are logged as warnings, never raised.
    """
    logger = get_logger(__name__)
    try:
        _send_notification(title, message)
    except Exception as exc:
        logger.warning("Could not send notification (%s): %s", type(exc).__name__, exc)


def _send_notification(title: str, message: str) -> None:
    """Dispatch to the correct platform-specific notification mechanism."""
    system = platform.system().lower()

    if system == "darwin":
        script = (
            f'display notification "{message}" '
            f'with title "{title}" '
            f'sound name "Basso"'
        )
        subprocess.run(["osascript", "-e", script], check=True, timeout=5)

    elif system == "linux":
        subprocess.run(
            ["notify-send", "--urgency=normal", title, message],
            check=True,
            timeout=5,
        )

    elif system == "windows":
        # Requires the 'win10toast' package (listed in requirements.txt)
        from win10toast import ToastNotifier  # type: ignore[import]
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=5, threaded=True)

    else:
        raise RuntimeError(f"No notification backend for system: {system!r}")


# ---------------------------------------------------------------------------
# Charging control
# ---------------------------------------------------------------------------

def stop_charging(platform_name: str) -> None:
    """
    Issue an OS-level command to stop or limit battery charging.

    On Linux this writes '0' to the charge_stop_threshold sysfs node (ThinkPads
    and similar). On macOS / Windows it delegates to a native helper that must
    be present on PATH (see native-modules).
    """
    logger = get_logger(__name__)
    logger.info("Halting charging via platform adapter (%s).", platform_name)
    _dispatch_charging_command(platform_name, action="stop")


def start_charging(platform_name: str) -> None:
    """Resume battery charging through the OS-level adapter."""
    logger = get_logger(__name__)
    logger.info("Resuming charging via platform adapter (%s).", platform_name)
    _dispatch_charging_command(platform_name, action="start")


def _dispatch_charging_command(platform_name: str, action: str) -> None:
    """
    Route 'start' / 'stop' to the correct platform implementation.

    Linux  — sysfs charge_stop_threshold
    macOS  — batteryos-helper (IOKit native module)
    Windows — batteryos-helper.exe (WinAPI native module)
    """
    try:
        if platform_name == "linux":
            _linux_charging(action)
        elif platform_name == "macos":
            _macos_charging(action)
        elif platform_name == "windows":
            _windows_charging(action)
    except FileNotFoundError as exc:
        logger = get_logger(__name__)
        logger.error(
            "Charging control command not found — is the native module installed? (%s)",
            exc,
        )
    except subprocess.CalledProcessError as exc:
        logger = get_logger(__name__)
        logger.error("Charging control command failed (exit %d): %s", exc.returncode, exc)


def _linux_charging(action: str) -> None:
    """
    Toggle charging via the sysfs battery interface.
    Requires write access (run as root or via polkit rule).
    """
    sysfs_paths = [
        Path("/sys/class/power_supply/BAT0/charge_stop_threshold"),
        Path("/sys/class/power_supply/BAT1/charge_stop_threshold"),
    ]
    value = b"0\n" if action == "stop" else b"100\n"

    for path in sysfs_paths:
        if path.exists():
            path.write_bytes(value)
            return

    # Fall back to the compiled native helper
    subprocess.run(["batteryos-linux", action], check=True, timeout=10)


def _macos_charging(action: str) -> None:
    subprocess.run(["batteryos-macos", action], check=True, timeout=10)


def _windows_charging(action: str) -> None:
    subprocess.run(["batteryos-windows.exe", action], check=True, timeout=10)


# ---------------------------------------------------------------------------
# IoT Smart Plug
# ---------------------------------------------------------------------------

class SmartPlugController:
    """
    Thin wrapper around a TP-Link Kasa or Tasmota smart plug.

    Set the BATTERYOS_PLUG_IP environment variable to the plug's LAN IP.
    Falls back to a no-op stub if neither the IP nor the library is available.
    """

    def __init__(self) -> None:
        import os
        self._ip: Optional[str] = os.environ.get("BATTERYOS_PLUG_IP")
        self._logger = get_logger(__name__)

        if not self._ip:
            self._logger.warning(
                "BATTERYOS_PLUG_IP not set — smart plug control is disabled."
            )

    def turn_off(self) -> None:
        """Cut power to the plug (stop charging physically)."""
        if self._ip:
            self._logger.info("Smart plug → OFF (%s)", self._ip)
            self._send_command(state=False)

    def turn_on(self) -> None:
        """Restore power to the plug (resume charging physically)."""
        if self._ip:
            self._logger.info("Smart plug → ON (%s)", self._ip)
            self._send_command(state=True)

    def _send_command(self, state: bool) -> None:
        """
        Send a Tasmota-compatible HTTP command.
        Replace with the python-kasa library for TP-Link devices.
        """
        import urllib.request
        cmd = "On" if state else "Off"
        url = f"http://{self._ip}/cm?cmnd=Power%20{cmd}"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                self._logger.debug("Plug response: %s", resp.read().decode())
        except Exception as exc:
            self._logger.warning("Smart plug command failed: %s", exc)
