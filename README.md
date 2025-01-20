# Laptop Battery Management Tool

A cross-platform battery management solution designed to monitor laptop battery levels and prevent overcharging through intelligent charging control and notifications.

![Battery Status](https://img.shields.io/badge/Battery-Protected-green)
![Python Version](https://img.shields.io/badge/python-3.6%2B-blue)
![License](https://img.shields.io/badge/license-MIT-blue)

## 🔋 Features

- Real-time battery monitoring and status tracking
- Intelligent charging control to prevent overcharging
- Cross-platform support (Windows, macOS, Linux)
- Customizable charging thresholds
- Desktop notifications for battery events
- Detailed logging system for monitoring and debugging
- Manufacturer-specific charging control support
- Optional IoT smart plug integration for physical power control

## 💻 Technology Stack

### Core Implementation (Python)
- Uses `psutil` for battery status monitoring
- `subprocess` for OS-specific commands
- Cross-platform GUI support with `tkinter` or `PyQt`
- Comprehensive logging and notification system

### Alternative Implementations

#### C/C++ Version
- Direct hardware access through system APIs
- Windows API integration for Windows
- ACPI/sysfs interface for Linux
- IOKit integration for macOS

#### Java Version
- Cross-platform GUI using JavaFX/Swing
- OS-level battery monitoring
- Platform-independent implementation

#### Electron Version
- Modern UI implementation
- Node.js backend for system interaction
- Cross-platform desktop application

---

## **Project Structure**

Here is the overview of how the files are arranged in the repository:
```
src/
├── core-service/              # Python core service
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── core.py
│   │   └── utils.py
│   │   ├── gui.py
│   └── requirements.txt
│
├── native-modules/           # C/C++ hardware interface
│   ├── windows/
│   │   ├── battery_control.cpp
│   │   └── battery_control.h
│   ├── linux/
│   │   ├── battery_control.cpp
│   │   └── battery_control.h
│   └── CMakeLists.txt
│
├── desktop-app/             # Electron frontend
│   ├── src/
│   │   ├── index.html
│   │   ├── main.js
│   │   └── renderer.js
│   ├── package.json
│   └── webpack.config.js
│
├── system-service/          # Rust background service
│   ├── src/
│   │   ├── main.rs
│   │   └── battery.rs
│   └── Cargo.toml
│
└── README.md

```

## 📋 Prerequisites

- Python 3.6 or higher
- Administrative privileges (for charging control)
- Compatible laptop with charging control capabilities
- Optional: Development tools for alternative implementations:
  - GCC/Clang for C/C++
  - Java JDK
  - Node.js
  - Rust toolchain (for high-performance service)

## ⚡ Installation

1. Clone the repository:
```bash
git clone https://github.com/stephenombuya/Laptop-Battery-Management-Tool
cd laptop-battery-manager
```

2. Install required packages:
```bash
# Core Python service
cd core-service
pip install -r requirements.txt

# Native modules
cd ../native-modules
cmake .
make

# Electron app
cd ../desktop-app
npm install

# Rust service
cd ../system-service
cargo build
```

## 🚀 Usage

1. Basic usage with default settings:
```bash
python battery_manager.py
```

2. Configure custom charging thresholds:
```python
manager = BatteryManager(max_charge_limit=80, min_charge_limit=20)
manager.run()
```

---

## System Architecture

<ANTARTIFACTLINK identifier="system-architecture" type="text/markdown" title="system-architecture.md" isClosed="true" />

For the detailed system architecture, see [System Architecture](https://github.com/stephenombuya/Laptop-Battery-Management-Tool/blob/main/system-architecture.md)

---

## ⚙️ Configuration

Customize the tool with these parameters:

- `max_charge_limit`: Maximum battery percentage (default: 80%)
- `min_charge_limit`: Minimum battery percentage (default: 20%)
- `check_interval`: Battery check frequency in seconds (default: 300)
- `smart_plug_enabled`: Enable/disable IoT smart plug integration

## 🔧 Platform-Specific Implementation

### Windows
```python
# Using Windows API
import psutil
battery = psutil.sensors_battery()
if battery.percent == 100:
    notify_user("Battery fully charged!")
```

### Linux
```python
# Using ACPI
import subprocess
status = subprocess.check_output(['acpi', '-b']).decode('utf-8')
print(f"Battery Status: {status}")
```

### macOS
```python
# Using IOKit integration
# Implementation varies by system
```

## 📝 Logging

Maintains detailed logs in `battery_manager.log`:
- Battery status changes
- Charging events
- Error messages
- System notifications

## ⚠️ Important Notes

1. **Hardware Compatibility**: 
   - Verify laptop support for charging control
   - Check manufacturer-specific requirements
   - Consider BIOS/UEFI settings

2. **Safety Considerations**:
   - Test thoroughly before deployment
   - Monitor battery behavior
   - Follow manufacturer guidelines

3. **Permissions**:
   - Requires administrative access
   - System-level permissions needed

## 🐛 Troubleshooting

Common issues and solutions:

1. **Battery Detection Issues**
   - Verify psutil installation
   - Check system permissions
   - Confirm battery connection

2. **Charging Control Problems**
   - Verify administrative privileges
   - Check manufacturer support
   - Review hardware compatibility

3. **Notification Issues**
   - Verify notification system
   - Check system settings
   - Confirm permissions

## 🤝 Contributing

Contributions welcome! Please follow these steps:

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- psutil development team
- Platform-specific API documentation
- Open-source community contributors
- IoT integration partners

---
Made with ❤️ for laptop batteries everywhere
