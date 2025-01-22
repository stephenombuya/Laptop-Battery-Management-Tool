class LinuxChargingController(ChargingController):
    def disconnect_charging(self):
        # Linux-specific implementation
        import subprocess
        try:
            # Example for ThinkPads
            subprocess.run(['echo', '1', '>', '/sys/bus/platform/drivers/ideapad_acpi/VPC2004:00/conservation_mode'])
        except Exception as e:
            logging.error(f"Failed to control charging: {e}")

class LinuxNotificationManager(NotificationManager):
    def send_notification(self, title, message):
        import subprocess
        subprocess.run(['notify-send', title, message])
