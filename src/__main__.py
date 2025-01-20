import sys
import platform
from core import BatteryMonitor
from gui import BatteryManagerGUI

def get_platform_specific_components():
    system = platform.system().lower()
    if system == 'windows':
        from platforms.windows import WindowsChargingController, WindowsNotificationManager
        return WindowsChargingController, WindowsNotificationManager
    elif system == 'linux':
        from platforms.linux import LinuxChargingController, LinuxNotificationManager
        return LinuxChargingController, LinuxNotificationManager
    elif system == 'darwin':
        from platforms.macos import MacOSChargingController, MacOSNotificationManager
        return MacOSChargingController, MacOSNotificationManager
    else:
        raise NotImplementedError(f"Platform {system} not supported")

def main():
    try:
        # Initialize core components
        monitor = BatteryMonitor()
        
        # Get platform-specific implementations
        ChargingController, NotificationManager = get_platform_specific_components()
        
        # Initialize controllers
        charging_controller = ChargingController(max_charge=80, min_charge=20)
        notification_manager = NotificationManager()
        
        # Attach observers
        monitor.attach_observer(charging_controller)
        monitor.attach_observer(notification_manager)
        
        # Initialize and run GUI
        gui = BatteryManagerGUI(monitor)
        gui.run()
        
    except Exception as e:
        print(f"Error starting Battery Manager: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
