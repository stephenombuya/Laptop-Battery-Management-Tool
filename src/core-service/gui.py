"""
gui.py
======
Optional tkinter-based status window and system-tray icon for BatteryOS.

The GUI runs on the main thread (required by Tk) and drives the
BatteryManager on a background daemon thread so the UI stays responsive.

Usage (internal)
----------------
    from .gui import BatteryGUI
    gui = BatteryGUI(manager)
    gui.start()   # blocks until window is closed
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING

from .utils import get_logger

if TYPE_CHECKING:
    from .core import BatteryManager

logger = get_logger(__name__)

# Refresh the display every 5 seconds
_REFRESH_MS = 5_000


class BatteryGUI:
    """
    Minimal status window displaying live battery information.

    Parameters
    ----------
    manager : BatteryManager
        A fully configured (but not yet running) BatteryManager instance.
    """

    def __init__(self, manager: BatteryManager) -> None:
        self._manager = manager
        self._root: tk.Tk | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Build the window and launch the manager on a background thread."""
        self._start_manager_thread()
        self._build_ui()
        self._root.mainloop()

    # ------------------------------------------------------------------
    # Manager thread
    # ------------------------------------------------------------------

    def _start_manager_thread(self) -> None:
        thread = threading.Thread(
            target=self._manager.run,
            name="BatteryManager",
            daemon=True,
        )
        thread.start()
        logger.info("BatteryManager background thread started.")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = tk.Tk()
        root.title("BatteryOS")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root = root

        # ── Styles ──────────────────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Header.TLabel", font=("Helvetica", 16, "bold"), foreground="#3dffa0")
        style.configure("Value.TLabel",  font=("Courier New", 13))
        style.configure("Dim.TLabel",    font=("Helvetica", 10), foreground="#888888")

        pad = {"padx": 12, "pady": 6}

        # ── Header ──────────────────────────────────────────────────────
        ttk.Label(root, text="🔋  BatteryOS", style="Header.TLabel").grid(
            row=0, column=0, columnspan=2, **pad, sticky="w"
        )
        ttk.Separator(root, orient="horizontal").grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=12
        )

        # ── Status rows ─────────────────────────────────────────────────
        labels = [
            ("Charge level",   "_lbl_percent"),
            ("Status",         "_lbl_status"),
            ("Time remaining", "_lbl_time"),
            ("Platform",       "_lbl_platform"),
            ("Max limit",      "_lbl_max"),
            ("Min limit",      "_lbl_min"),
        ]

        for idx, (caption, attr) in enumerate(labels, start=2):
            ttk.Label(root, text=caption, style="Dim.TLabel").grid(
                row=idx, column=0, **pad, sticky="w"
            )
            lbl = ttk.Label(root, text="—", style="Value.TLabel")
            lbl.grid(row=idx, column=1, **pad, sticky="w")
            setattr(self, attr, lbl)

        # ── Progress bar ─────────────────────────────────────────────────
        self._progress = ttk.Progressbar(root, length=260, maximum=100)
        self._progress.grid(
            row=len(labels) + 2, column=0, columnspan=2, **pad, sticky="ew"
        )

        # ── Controls ─────────────────────────────────────────────────────
        btn_frame = ttk.Frame(root)
        btn_frame.grid(row=len(labels) + 3, column=0, columnspan=2, **pad)

        ttk.Button(btn_frame, text="Stop Charging",  command=self._stop_charging).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Start Charging", command=self._start_charging).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Quit",           command=self._on_close).pack(side="right", padx=4)

        # Kick off the periodic refresh
        self._schedule_refresh()

    # ------------------------------------------------------------------
    # Periodic refresh
    # ------------------------------------------------------------------

    def _schedule_refresh(self) -> None:
        self._refresh()
        if self._root:
            self._root.after(_REFRESH_MS, self._schedule_refresh)

    def _refresh(self) -> None:
        """Pull the latest snapshot from the manager and update labels."""
        snap = self._manager.snapshot
        pct  = snap.percent

        self._lbl_percent.config(text=f"{pct:.1f}%")
        self._lbl_time.config(text=snap.time_left_human)
        self._lbl_platform.config(text=self._manager.platform.capitalize())
        self._lbl_max.config(text=f"{self._manager.max_charge_limit}%")
        self._lbl_min.config(text=f"{self._manager.min_charge_limit}%")
        self._progress["value"] = pct

        if snap.charging:
            self._lbl_status.config(text="⚡ Charging", foreground="#3dffa0")
        elif snap.plugged_in:
            self._lbl_status.config(text="✔ Plugged in (full)", foreground="#00c8ff")
        else:
            colour = "#ff4d6a" if pct <= self._manager.min_charge_limit else "#ffbe3d"
            self._lbl_status.config(text="🔋 Discharging", foreground=colour)

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------

    def _stop_charging(self) -> None:
        from .utils import stop_charging
        stop_charging(self._manager.platform)

    def _start_charging(self) -> None:
        from .utils import start_charging
        start_charging(self._manager.platform)

    def _on_close(self) -> None:
        if messagebox.askokcancel("Quit", "Stop BatteryOS monitoring?"):
            logger.info("GUI closed by user — stopping manager.")
            self._manager.stop()
            if self._root:
                self._root.destroy()
                self._root = None
