# battery_manager/core.py
import psutil
import logging
import time
from datetime import datetime
from abc import ABC, abstractmethod

class BatteryMonitor:
    def __init__(self):
        self.setup_logging()
        self._observers = []

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

    def attach_observer(self, observer):
        self._observers.append(observer)

    def notify_observers(self, status):
        for observer in self._observers:
            observer.update(status)

    def run(self, check_interval=300):
        logging.info("Battery Monitor started")
        while True:
            try:
                status = self.get_battery_status()
                if status:
                    self.notify_observers(status)
                time.sleep(check_interval)
            except KeyboardInterrupt:
                logging.info("Battery Monitor stopped by user")
                break
            except Exception as e:
                logging.error(f"Error in main loop: {str(e)}")
                time.sleep(check_interval)

class BatteryObserver(ABC):
    @abstractmethod
    def update(self, status):
        pass

class ChargingController(BatteryObserver):
    def __init__(self, max_charge=80, min_charge=20):
        self.max_charge = max_charge
        self.min_charge = min_charge

    def update(self, status):
        if status['power_plugged'] and status['percent'] >= self.max_charge:
            self.disconnect_charging()
        elif not status['power_plugged'] and status['percent'] <= self.min_charge:
            self.notify_low_battery()

    def disconnect_charging(self):
        # Implement platform-specific charging control
        logging.info(f"Battery reached {self.max_charge}%. Disconnecting charging.")

    def notify_low_battery(self):
        logging.info(f"Battery below {self.min_charge}%. Please connect charger.")

class NotificationManager(BatteryObserver):
    def update(self, status):
        if status['percent'] >= 80 and status['power_plugged']:
            self.send_notification("High Battery Alert", 
                                 f"Battery at {status['percent']}%. Consider unplugging.")
        elif status['percent'] <= 20 and not status['power_plugged']:
            self.send_notification("Low Battery Alert", 
                                 f"Battery at {status['percent']}%. Please connect charger.")

    def send_notification(self, title, message):
        # Implement platform-specific notifications
        logging.info(f"Notification: {title} - {message}")
