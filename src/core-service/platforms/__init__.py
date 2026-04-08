"""
platforms/__init__.py
=====================
Platform adapter package for BatteryOS core-service.

Each sub-module exposes a single class — ``LinuxPlatform``,
``MacOSPlatform``, or ``WindowsPlatform`` — that implements the
``BasePlatform`` interface defined in this file.

``get_platform()`` auto-detects the OS and returns the correct adapter.
The rest of the codebase imports *only* from this package, so platform
logic never leaks into ``core.py`` or ``utils.py``.

Usage
-----
    from .platforms import get_platform

    platform = get_platform()
    platform.stop_charging()
    snap = platform.read_status()
"""

from __future__ import annotations

import platform as _platform
import sys
from abc import ABC, abstractmethod
from typing import Optional

# Re-export for convenience
from ..utils import BatterySnapshot, get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Abstract base — every platform adapter must implement this contract
# ---------------------------------------------------------------------------

class BasePlatform(ABC):
    """
    Abstract interface that every platform adapter must satisfy.

    All methods are synchronous and designed to be called from the
    BatteryManager monitoring thread.
    """

    # ── Status ───────────────────────────────────────────────────────────

    @abstractmethod
    def read_status(self) -> Optional[BatterySnapshot]:
        """
        Return the current battery snapshot, or ``None`` if no battery
        is detected (e.g. a desktop machine).

        Must never raise; exceptions should be caught internally and
        logged, returning ``None`` on failure.
        """

    # ── Charge control ────────────────────────────────────────────────────

    @abstractmethod
    def stop_charging(self) -> None:
        """
        Halt battery charging immediately.
        Implementations should log a warning on failure rather than raising.
        """

    @abstractmethod
    def start_charging(self) -> None:
        """
        Resume battery charging.
        """

    @abstractmethod
    def set_charge_thresholds(self, min_pct: int, max_pct: int) -> None:
        """
        Set the start (min) and stop (max) charge thresholds.

        Parameters
        ----------
        min_pct : int
            Battery percentage at which charging should resume (0–99).
        max_pct : int
            Battery percentage at which charging should stop (1–100).
        """

    # ── Identification ────────────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable platform name, e.g. ``'Linux'``."""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_platform() -> BasePlatform:
    """
    Detect the current OS and return the appropriate platform adapter.

    Returns
    -------
    BasePlatform
        A fully initialised platform adapter for the running OS.

    Raises
    ------
    RuntimeError
        If the OS is not Windows, macOS, or Linux.
    """
    system = _platform.system().lower()

    if system == "linux":
        from .linux import LinuxPlatform
        adapter: BasePlatform = LinuxPlatform()

    elif system == "darwin":
        from .macos import MacOSPlatform
        adapter = MacOSPlatform()

    elif system == "windows":
        from .windows import WindowsPlatform
        adapter = WindowsPlatform()

    else:
        raise RuntimeError(
            f"Unsupported operating system: '{_platform.system()}'. "
            "BatteryOS supports Linux, macOS, and Windows."
        )

    logger.info("Platform adapter loaded: %s", adapter.name)
    return adapter


__all__ = ["BasePlatform", "get_platform"]
