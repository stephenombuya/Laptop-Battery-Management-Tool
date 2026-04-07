"""
Entry point — allows the package to be run as:
    python -m core_service [options]
"""

import argparse
import sys

from .core import BatteryManager
from .utils import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="batteryos",
        description="BatteryOS — Intelligent Laptop Battery Manager",
    )
    parser.add_argument(
        "--max", type=int, default=80, metavar="PCT",
        help="Maximum charge threshold in percent (default: 80)",
    )
    parser.add_argument(
        "--min", type=int, default=20, metavar="PCT",
        help="Minimum charge threshold in percent (default: 20)",
    )
    parser.add_argument(
        "--interval", type=int, default=300, metavar="SEC",
        help="Battery check interval in seconds (default: 300)",
    )
    parser.add_argument(
        "--no-gui", action="store_true",
        help="Run as a headless background service (no GUI)",
    )
    parser.add_argument(
        "--smart-plug", action="store_true",
        help="Enable IoT smart-plug integration for physical power cutoff",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Validate threshold range
    if not (0 <= args.min < args.max <= 100):
        logger.error(
            "Invalid thresholds: min=%d, max=%d. "
            "Ensure 0 ≤ min < max ≤ 100.",
            args.min, args.max,
        )
        sys.exit(1)

    manager = BatteryManager(
        max_charge_limit=args.max,
        min_charge_limit=args.min,
        check_interval=args.interval,
        smart_plug_enabled=args.smart_plug,
        log_level=args.log_level,
    )

    if args.no_gui:
        logger.info("Starting BatteryOS in headless mode.")
        manager.run()
    else:
        # Lazy-import GUI so headless environments never load tkinter
        from .gui import BatteryGUI
        gui = BatteryGUI(manager)
        gui.start()


if __name__ == "__main__":
    main()
