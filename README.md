#  Laptop Battery Management Tool

A production-grade, cross-platform battery management system designed to monitor laptop battery health, enforce intelligent charge thresholds, and
extend battery longevity through proactive charge control and real-time notifications.

[![Battery Status](https://img.shields.io/badge/Battery-Protected-green)](https://github.com/stephenombuya/Laptop-Battery-Management-Tool)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![Electron](https://img.shields.io/badge/Electron-30-47848F)](https://www.electronjs.org/)
[![Rust](https://img.shields.io/badge/Rust-1.75%2B-orange)](https://www.rust-lang.org/)
[![C++](https://img.shields.io/badge/C%2B%2B-17-blue)](https://isocpp.org/)
[![License](https://img.shields.io/badge/License-MIT-blue)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()

<div>

  <!-- Repository Analytics -->
![GitHub repo size](https://img.shields.io/github/repo-size/stephenombuya/Laptop-Battery-Management-Tool)
![GitHub language count](https://img.shields.io/github/languages/count/stephenombuya/Laptop-Battery-Management-Tool)
![GitHub top language](https://img.shields.io/github/languages/top/stephenombuya/Laptop-Battery-Management-Tool)
![GitHub last commit](https://img.shields.io/github/last-commit/stephenombuya/Laptop-Battery-Management-Tool)
![GitHub contributors](https://img.shields.io/github/contributors/stephenombuya/Laptop-Battery-Management-Tool)

</div>


## Table of Contents

- [Features](#-features)
- [Architecture Overview](#-architecture-overview)
- [Technology Stack](#-technology-stack)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Usage](#-usage)
- [Configuration](#-configuration)
- [Platform-Specific Notes](#-platform-specific-notes)
- [Charging Modes](#-charging-modes)
- [IoT Smart Plug Integration](#-iot-smart-plug-integration)
- [Logging](#-logging)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)

---

##  Features

- **Real-time battery monitoring** — live percentage, voltage, temperature, health, power draw, and time remaining
- **Intelligent charge limiting** — automatically stops and resumes charging at configurable thresholds
- **Four charging modes** — Balanced (80%), Travel (100%), Storage (50%), and Custom
- **Cross-platform** — full support for Windows, macOS, and Linux with platform-native APIs
- **Electron dashboard** — rich dark-themed UI with live charge history chart, event log, and threshold sliders
- **Python core service** — lightweight monitoring daemon with optional tkinter status window
- **Rust system service** — high-performance optional background daemon for production deployments
- **C++ native modules** — privileged helper binaries for hardware-level charge control (SMC / sysfs / WinAPI)
- **Desktop notifications** — OS-native alerts on threshold events and temperature warnings
- **IoT smart plug integration** — physical power cutoff via Tasmota or TP-Link Kasa HTTP API
- **Detailed rotating logs** — structured event log at `~/.batteryos/logs/battery_manager.log`

---

##  Architecture Overview

BatteryOS uses a layered multi-process architecture:

```
┌─────────────────────────────────────┐
│   Electron Desktop App (UI shell)   │
│   dashboard · tray icon · IPC       │
└──────────────┬──────────────────────┘
               │ stdout JSON / stdin commands
┌──────────────▼──────────────────────┐
│   Python Core Service               │
│   BatteryManager + Platform adapters│
│   platforms/ linux · macos · windows│
└──────────────┬──────────────────────┘
               │ subprocess (privileged, short-lived)
┌──────────────▼──────────────────────┐
│   C++ Native Helpers                │
│   batteryos-linux / macos / windows │
│   sysfs · IOKit+SMC · WinAPI        │
└─────────────────────────────────────┘

[Optional: Rust system-service replaces Python poller in production]
```

See [system-architecture.md](system-architecture.md) for the full layered
diagram, data-flow chart, and component responsibility matrix.

---

##  Technology Stack

### Electron Desktop App (`src/desktop-app/`)

| File | Responsibility |
|---|---|
| `main.js` | Main process: BrowserWindow, system tray, child-process spawn, IPC handlers |
| `preload.js` | Secure `contextBridge` exposing `window.batteryOS.*` to renderer |
| `renderer.js` | Wires live backend snapshots into dashboard state; disables simulation |
| `index.html` | Full BatteryOS dashboard — HTML/CSS/JS, zero framework dependencies |
| `webpack.config.js` | Bundles renderer only; main/preload run in Node directly |

### Python Core Service (`src/core-service/`)

| File | Responsibility |
|---|---|
| `core.py` | `BatteryManager`: thread-safe polling loop, `BatterySnapshot` dataclass, threshold enforcement |
| `utils.py` | Rotating logger, cross-platform notifications, `SmartPlugController` |
| `gui.py` | Optional tkinter status window; manager runs on a daemon thread |
| `__main__.py` | CLI entry: `--max`, `--min`, `--interval`, `--no-gui`, `--smart-plug` |
| `platforms/__init__.py` | `BasePlatform` ABC + `get_platform()` auto-detecting factory |
| `platforms/linux.py` | `LinuxPlatform`: sysfs enrichment + `charge_stop_threshold` writes |
| `platforms/macos.py` | `MacOSPlatform`: `ioreg` parsing + `bclm`/native helper charge control |
| `platforms/windows.py` | `WindowsPlatform`: WMI enrichment + `powercfg` + native helper, Admin check |

### C++ Native Modules (`src/native-modules/`)

| File | Responsibility |
|---|---|
| `linux/battery_control.cpp` | sysfs reads + `charge_stop_threshold` / `charge_start_threshold` writes |
| `macos/battery_control.cpp` | IOKit `AppleSmartBattery` reads + SMC `BCLM`/`BCLB` writes + `IOPMSetChargeInhibit` |
| `windows/battery_control.cpp` | `GetSystemPowerStatus` + `IOCTL_BATTERY_QUERY_*` + WMI OEM thresholds |
| `cli_main.cpp` | Shared CLI dispatcher: `start` / `stop` / `status` (→ JSON stdout) |
| `CMakeLists.txt` | Platform-guarded CMake build; installs binary to system PATH |

### Rust System Service (`src/system-service/`)

| File | Responsibility |
|---|---|
| `battery.rs` | `BatteryReader` trait + `LinuxReader` (sysfs) / `MacosReader` (ioreg) / `WindowsReader` (WinAPI) |
| `main.rs` | Tokio async loop, JSON-line streaming to stdout, SIGTERM/SIGINT handling |
| `Cargo.toml` | `serde`, `tokio`, `tracing`; platform-gated deps (`windows` crate, `core-foundation`) |

---

##  Project Structure

```
src/
├── core-service/
│   ├── platforms/
│   │   ├── __init__.py          BasePlatform ABC + get_platform() factory
│   │   ├── linux.py             LinuxPlatform  — sysfs + psutil
│   │   ├── macos.py             MacOSPlatform  — ioreg + psutil + bclm
│   │   └── windows.py           WindowsPlatform — WMI + psutil + powercfg
│   ├── __init__.py
│   ├── __main__.py              CLI entry point (argparse)
│   ├── core.py                  BatteryManager + BatterySnapshot
│   ├── gui.py                   tkinter status window
│   ├── utils.py                 Logger, notify, SmartPlugController
│   └── requirements.txt
│
├── native-modules/
│   ├── linux/
│   │   ├── battery_control.h
│   │   └── battery_control.cpp
│   ├── macos/
│   │   ├── battery_control.h
│   │   └── battery_control.cpp  IOKit + SMC BCLM/BCLB + IOPMSetChargeInhibit
│   ├── windows/
│   │   ├── battery_control.h
│   │   └── battery_control.cpp
│   ├── cli_main.cpp             Shared CLI wrapper (start/stop/status → JSON)
│   └── CMakeLists.txt
│
├── desktop-app/
│   ├── src/
│   │   ├── index.html           BatteryOS dashboard
│   │   ├── main.js              Electron main process
│   │   ├── preload.js           contextBridge window.batteryOS API
│   │   └── renderer.js          Live data wiring + simulation override
│   ├── package.json
│   └── webpack.config.js
│
├── system-service/
│   ├── src/
│   │   ├── main.rs              Tokio async daemon
│   │   └── battery.rs           Cross-platform BatteryReader trait
│   └── Cargo.toml
│
├── system-architecture.md
└── README.md
```

---

##  Prerequisites

### All platforms
- [Node.js](https://nodejs.org/) 20+ (Electron app)
- Python 3.8+
- Administrative / root privileges for charge control
- A laptop with a supported battery

### Linux
- Kernel 4.2+ (standard `power_supply` sysfs class)
- `sudo apt install acpi libnotify-bin` (notifications + ACPI diagnostics)
- For rootless threshold writes: add a udev rule (see [Platform Notes](#linux-1))

### macOS
- macOS 12 Monterey+ recommended (SMC BCLM key support)
- `brew install bclm` — charge-limit fallback tool
- Xcode Command Line Tools for native module compilation

### Windows
- Windows 10 / 11
- Run as Administrator for all charge control operations
- [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/) for native modules

### Development only
- Rust toolchain via [rustup](https://rustup.rs/)
- CMake 3.20+ and GCC/Clang/MSVC for C++ modules

---

##  Installation

### 1. Clone

```bash
git clone https://github.com/stephenombuya/Laptop-Battery-Management-Tool
cd Laptop-Battery-Management-Tool
```

### 2. Python core service

```bash
cd src/core-service
pip install -r requirements.txt
```

### 3. Native modules (required for charge control)

```bash
cd src/native-modules
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
sudo cmake --install .        # Linux / macOS
# cmake --install .           # Windows (Admin terminal)
```

### 4. Electron desktop app

```bash
cd src/desktop-app
npm install
```

### 5. Rust system service (optional)

```bash
cd src/system-service
cargo build --release
```

---

##  Usage

### Electron app (recommended)

```bash
cd src/desktop-app
npm start                          # production
NODE_ENV=development npm run dev   # with DevTools open
```

### Python service — headless (systemd / server)

```bash
python -m core_service --no-gui

# Custom thresholds and faster polling
python -m core_service --min 25 --max 75 --interval 60 --no-gui

# With IoT smart plug
BATTERYOS_PLUG_IP=192.168.1.42 python -m core_service --smart-plug --no-gui
```

### Python service — with GUI

```bash
python -m core_service --max 80 --min 20
```

### Rust daemon (drop-in replacement for Python poller)

```bash
./src/system-service/target/release/batteryos-service \
    --max 80 --min 20 --interval 300
```

### Native helper directly

```bash
batteryos-linux status       # JSON snapshot to stdout
batteryos-linux stop         # halt charging now
batteryos-linux start        # resume charging
```

### Programmatic API

```python
from core_service import BatteryManager

manager = BatteryManager(
    max_charge_limit=80,
    min_charge_limit=20,
    check_interval=300,
    smart_plug_enabled=False,
)
manager.run()   # blocks; call manager.stop() from another thread to exit

# Update thresholds at runtime
manager.update_thresholds(min_limit=25, max_limit=75)

# Read latest snapshot (thread-safe)
snap = manager.snapshot
print(f"{snap.percent}% — {snap.time_left_human}")
```

---

##  Configuration

| Parameter | CLI flag | Default | Description |
|---|---|---|---|
| Max charge | `--max` | `80` | Stop charging at this % |
| Min charge | `--min` | `20` | Alert / resume at this % |
| Poll interval | `--interval` | `300` | Seconds between checks |
| GUI | `--no-gui` | GUI on | Run headless |
| Smart plug | `--smart-plug` | Off | Enable IoT physical cutoff |
| Log level | `--log-level` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

---

##  Platform-Specific Notes

### Linux

Charge control uses sysfs kernel nodes:

```
/sys/class/power_supply/BAT0/charge_stop_threshold
/sys/class/power_supply/BAT0/charge_start_threshold
```

**Supported OEMs:** ThinkPad (thinkpad-acpi), ASUS (asus-nb-wmi), Huawei (huawei-wmi).

**Rootless writes — udev rule** (`/etc/udev/rules.d/99-batteryos.rules`):

```udev
SUBSYSTEM=="power_supply", KERNEL=="BAT[0-9]", \
  ATTR{charge_stop_threshold}=="*", \
  RUN+="/bin/chmod 666 /sys%p/charge_stop_threshold"
SUBSYSTEM=="power_supply", KERNEL=="BAT[0-9]", \
  ATTR{charge_start_threshold}=="*", \
  RUN+="/bin/chmod 666 /sys%p/charge_start_threshold"
```

```bash
sudo udevadm control --reload && sudo udevadm trigger
```

**Unsupported hardware:** Use the IoT smart plug integration or install [TLP](https://linrunner.de/tlp/).

### macOS

Two charge-control mechanisms, tried in order:

1. **SMC BCLM/BCLB keys** (native helper) — Apple Silicon + Intel T2, macOS 12+. Requires root.
2. **bclm Homebrew tool** — max-charge fallback: `brew install bclm && sudo bclm write 80 && sudo bclm persist`

**Pre-T2 Intel Macs:** Only `IOPMSetChargeInhibit` is available (freezes at current level). Use the smart plug for configurable threshold control.

### Windows

- Always run as **Administrator** for charge control.
- OEM threshold support:
  - **Lenovo ThinkPad** — BatteryThreshold WMI class ✅
  - **Dell** — `smbios-battery-ctl` or Dell Command | Power Manager ✅
  - **ASUS** — ATKACPI WMI interface ✅
  - **Other OEMs** — smart plug integration recommended

Generate a full battery report:

```python
from core_service.platforms.windows import WindowsPlatform
WindowsPlatform().generate_battery_report("battery_report.html")
```

---

##  Charging Modes

| Mode | Max % | Min % | Best for |
|---|---|---|---|
| **Balanced** | 80 | 20 | Daily use — maximum long-term health |
| **Travel** | 100 | 20 | Long trips where full capacity is needed |
| **Storage** | 55 | 45 | Weeks of storage — holds near 50% |
| **Custom** | User-defined | User-defined | Fine-grained control |

---

##  IoT Smart Plug Integration

For hardware without native charge-stop support, BatteryOS can physically cut power via a smart plug.

```bash
export BATTERYOS_PLUG_IP=192.168.1.42
python -m core_service --smart-plug --no-gui
```

**Supported protocols:**
- **Tasmota** — HTTP `/cm?cmnd=Power%20Off` (any Tasmota-flashed plug)
- **TP-Link Kasa** — replace `SmartPlugController._send_command()` in `utils.py` with `python-kasa`

---

##  Logging

Logs rotate at 5 MB × 3 backups in `~/.batteryos/logs/battery_manager.log`:

```
2026-04-08 11:42:00  INFO     batteryos.core — Battery: 74.0% | discharging | time left: 2h 34m
2026-04-08 11:42:05  WARNING  batteryos.core — Battery at 80.1% — reached max limit (80%). Stopping charging.
2026-04-08 11:42:05  INFO     batteryos.utils — Halting charging via platform adapter (linux).
```

Set verbosity: `python -m core_service --log-level DEBUG`

---

##  Troubleshooting

**Battery not detected**
- Linux: `ls /sys/class/power_supply/` — confirm `BAT0` or `BAT1` exists
- macOS: `ioreg -rn AppleSmartBattery` — must return output
- Windows: `powercfg /batteryreport` — verify Windows sees the battery

**Charge control has no effect**
- Linux: Check `cat /sys/class/power_supply/BAT0/charge_stop_threshold`. If file missing — hardware unsupported, use smart plug.
- macOS: `sudo batteryos-macos status`. Install `bclm` as fallback.
- Windows: Relaunch as Administrator. Run `batteryos-windows status` in Admin terminal.

**Native helper not found**
```bash
cd src/native-modules && mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . && sudo cmake --install .
```

**Notifications not appearing**
- Linux: `sudo apt install libnotify-bin`
- macOS: System Settings → Notifications → Allow BatteryOS
- Windows: `pip install win10toast`

**Electron app can't connect to Python**
- Verify: `python3 --version` (must be 3.8+)
- Test manually: `python -m core_service --no-gui --log-level DEBUG`
- Open DevTools: `NODE_ENV=development npm run dev`

---

##  Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feature/amazing-feature`
3. Coding standards:
   - **Python:** PEP 8, type hints, docstrings on all public APIs
   - **C++:** C++17, clang-format Google style, all headers documented
   - **Rust:** `rustfmt` + `clippy` clean, doc-comments on public items
   - **JS:** ESLint, JSDoc on exported functions
4. Test on at least one platform
5. Commit: `git commit -m 'feat: add amazing feature'`
6. Push and open a Pull Request

---

##  License

Licensed under the **MIT License** — see [LICENSE](LICENSE) for details.
