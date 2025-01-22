from core import ChargingController, NotificationManager
from win10toast import ToastNotifier

class WindowsChargingController(ChargingController):
    def disconnect_charging(self):
        # Windows-specific implementation
        # Example for some laptop models:
        import subprocess
        try:
            subprocess.run(['powercfg', '/setdcvalueindex', 'SCHEME_CURRENT', 'SUB_PROCESSOR', 'PROCTHROTTLEMAX', '99'])
            subprocess.run(['powercfg', '/setactive', 'SCHEME_CURRENT'])
        except Exception as e:
            logging.error(f"Failed to control charging: {e}")

class WindowsNotificationManager(NotificationManager):
    def __init__(self):
        self.toaster = ToastNotifier()

    def send_notification(self, title, message):
        self.toaster.show_toast(title, message, duration=10)
