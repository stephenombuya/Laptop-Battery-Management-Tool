import tkinter as tk
from tkinter import ttk
import threading

class BatteryManagerGUI:
    def __init__(self, battery_monitor):
        self.battery_monitor = battery_monitor
        self.root = tk.Tk()
        self.root.title("Battery Manager")
        self.setup_ui()

    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Battery status
        self.battery_label = ttk.Label(main_frame, text="Battery Status: --")
        self.battery_label.grid(row=0, column=0, pady=5)

        # Charging status
        self.charging_label = ttk.Label(main_frame, text="Charging Status: --")
        self.charging_label.grid(row=1, column=0, pady=5)

        # Settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="Settings", padding="5")
        settings_frame.grid(row=2, column=0, pady=10, sticky=(tk.W, tk.E))

        # Max charge setting
        ttk.Label(settings_frame, text="Max Charge %:").grid(row=0, column=0)
        self.max_charge_var = tk.StringVar(value="80")
        ttk.Entry(settings_frame, textvariable=self.max_charge_var, width=5).grid(row=0, column=1)

        # Min charge setting
        ttk.Label(settings_frame, text="Min Charge %:").grid(row=1, column=0)
        self.min_charge_var = tk.StringVar(value="20")
        ttk.Entry(settings_frame, textvariable=self.min_charge_var, width=5).grid(row=1, column=1)

        # Control buttons
        ttk.Button(main_frame, text="Start Monitoring", command=self.start_monitoring).grid(row=3, column=0, pady=5)
        ttk.Button(main_frame, text="Stop Monitoring", command=self.stop_monitoring).grid(row=4, column=0, pady=5)

    def update_status(self, status):
        self.battery_label.config(text=f"Battery Level: {status['percent']}%")
        charging_status = "Plugged In" if status['power_plugged'] else "On Battery"
        self.charging_label.config(text=f"Charging Status: {charging_status}")

    def start_monitoring(self):
        # Start battery monitoring in a separate thread
        self.monitor_thread = threading.Thread(target=self.battery_monitor.run)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def stop_monitoring(self):
        if hasattr(self, 'monitor_thread'):
            self.battery_monitor.stop()

    def run(self):
        self.root.mainloop()
