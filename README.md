# Laptop Battery Management Tool

A Python-based tool for intelligent laptop battery management that helps extend battery life by preventing overcharging and providing timely notifications.

![Battery Status](https://img.shields.io/badge/Battery-Protected-green)
![Python Version](https://img.shields.io/badge/python-3.6%2B-blue)
![License](https://img.shields.io/badge/license-MIT-blue)

## 🔋 Features

- Automatic monitoring of battery charge levels
- Smart charging control to prevent overcharging
- Cross-platform support (Windows, macOS, Linux)
- Customizable charging thresholds
- Desktop notifications for battery events
- Detailed logging system for monitoring and debugging
- Manufacturer-specific charging control support

## 📋 Prerequisites

- Python 3.6 or higher
- Administrative privileges (for charging control)
- Compatible laptop with charging control capabilities

## ⚡ Installation

1. Clone the repository:
```bash
git clone https://github.com/stephenombuya/Laptop-Battery-Management-Tool
cd laptop-battery-manager
```

2. Install required packages:
```bash
# For Windows
pip install psutil win10toast

# For Linux/macOS
pip install psutil
```

## 🚀 Usage

1. Basic usage with default settings:
```bash
python battery_manager.py
```

2. Configure custom charging thresholds by modifying the initialization:
```python
manager = BatteryManager(max_charge_limit=80, min_charge_limit=20)
manager.run()
```

## ⚙️ Configuration

The tool can be configured by adjusting the following parameters:

- `max_charge_limit`: Maximum battery percentage before charging is disabled (default: 80%)
- `min_charge_limit`: Minimum battery percentage when charging notification is triggered (default: 20%)
- `check_interval`: Time between battery checks in seconds (default: 300 seconds)

## 🔧 Manufacturer-Specific Setup

### Lenovo Laptops
```python
# Example for Lenovo ideapad
subprocess.run(['echo', '0', '>', '/sys/bus/platform/drivers/ideapad_acpi/VPC2004:00/conservation_mode'])
```

### Dell Laptops
```python
# Implementation varies by model
# Refer to Dell Command Configure documentation
```

### HP Laptops
```python
# Implementation varies by model
# Refer to HP BIOS Configuration Utility documentation
```

## 📝 Logging

The tool maintains a detailed log file (`battery_manager.log`) containing:
- Battery status changes
- Charging events
- Error messages
- System notifications

Example log entry:
```
2025-01-20 14:30:15 - INFO - Battery Manager started
2025-01-20 14:30:15 - INFO - Battery reached 80%. Disconnecting charging.
```

## ⚠️ Important Notes

1. **Hardware Compatibility**: 
   - Not all laptops support programmatic charging control
   - Manufacturer-specific implementations may be required
   - Some features may require BIOS/UEFI support

2. **Safety Considerations**:
   - Test thoroughly before regular use
   - Monitor battery behavior during initial setup
   - Keep default charging thresholds unless specifically needed

3. **Permissions**:
   - Administrative privileges required for charging control
   - System-level access needed for hardware interaction

## 🐛 Troubleshooting

Common issues and solutions:

1. **No Battery Detected**
   - Verify psutil installation
   - Check system permissions
   - Ensure battery is properly connected

2. **Charging Control Not Working**
   - Verify admin privileges
   - Check manufacturer-specific implementation
   - Confirm hardware support for charging control

3. **Notifications Not Showing**
   - Verify notification package installation
   - Check system notification settings
   - Ensure proper permissions

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Thanks to the psutil team for the excellent battery monitoring capabilities
- Contributors to platform-specific notification systems
- Laptop manufacturer documentation for charging control specifications

---
Made with ❤️ for laptop batteries everywhere
