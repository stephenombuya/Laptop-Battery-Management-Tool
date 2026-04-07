"""
BatteryOS Core Service
======================
Cross-platform battery monitoring and intelligent charge control.

Modules:
    core  — BatteryManager: main monitoring loop and charge control logic
    utils — Logging, notifications, platform detection, config helpers
    gui   — Optional system-tray / tkinter status window
"""

from .core import BatteryManager
from .utils import get_logger, notify, detect_platform

__all__ = ["BatteryManager", "get_logger", "notify", "detect_platform"]
__version__ = "2.0.0"
__author__ = "Stephen Ombuya"
__license__ = "MIT"
