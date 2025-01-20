import psutil
import time
import sys
import logging
from datetime import datetime

class BatteryManager:
    def __init__(self, max_charge_limit=100, min_charge_limit=95):
        self.max_charge_limit = max_charge_limit
        self.min_charge_limit = min_charge_limit
        self.setup_logging()

    def setup_logging(self):
        logging.basicConfig(
            filename='battery_manager.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def get_battery_status(self):
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                raise Exception("No battery detected")
            return {
                'percent': battery.percent,
                'power_plugged': battery.power_plugged,
                'seconds_left': battery.secsleft
            }
        except Exception as e:
            logging.error(f"Error getting battery status: {str(e)}")
            return None

    def notify_user(self, message):
        # Windows notification
        if sys.platform.startswith('win'):
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast("Battery Manager", message, duration=10)
        # Linux notification
        elif sys.platform.startswith('linux'):
            import subprocess
            subprocess.run(['notify-send', "Battery Manager", message])
        # macOS notification
        elif sys.platform.startswith('darwin'):
            import os
            os.system(f"""
                osascript -e 'display notification "{message}" with title "Battery Manager"'
            """)

    def control_charging(self):
        """
        Note: This function requires appropriate system permissions and may need 
        different implementations for different laptop manufacturers/models
        """
        status = self.get_battery_status()
        if not status:
            return

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if status['power_plugged'] and status['percent'] >= self.max_charge_limit:
            message = f"Battery reached {status['percent']}%. Disconnecting charging."
            logging.info(message)
            self.notify_user(message)
            # Here you would add manufacturer-specific commands to control charging
            # Example for some Lenovo laptops:
            # subprocess.run(['echo', '0', '>', '/sys/bus/platform/drivers/ideapad_acpi/VPC2004:00/conservation_mode'])

        elif not status['power_plugged'] and status['percent'] <= self.min_charge_limit:
            message = f"Battery below {self.min_charge_limit}%. Please connect charger."
            logging.info(message)
            self.notify_user(message)

    def run(self, check_interval=300):  # 5 minutes default interval
        logging.info("Battery Manager started")
        while True:
            try:
                self.control_charging()
                time.sleep(check_interval)
            except KeyboardInterrupt:
                logging.info("Battery Manager stopped by user")
                break
            except Exception as e:
                logging.error(f"Error in main loop: {str(e)}")
                time.sleep(check_interval)

if __name__ == "__main__":
    manager = BatteryManager(max_charge_limit=80, min_charge_limit=20)
    manager.run()
