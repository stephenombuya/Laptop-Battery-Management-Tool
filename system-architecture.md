# BatteryOS — System Architecture

## Overview

BatteryOS is a layered, multi-process application. The **Electron desktop app**
is the user-facing shell. It spawns the **Python core-service** as a child
process, which drives all monitoring logic and delegates hardware-level charge
control to either the **platform adapters** (pure Python, sysfs / ioreg / WMI)
or the **native helper binaries** (compiled C++, for privileged OS calls).
The **Rust system-service** is an optional high-performance daemon that replaces
the Python poller in production deployments; it streams JSON snapshots over
stdout using the same protocol.

---

## Full Architecture Diagram

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                        USER  INTERFACE  LAYER                              ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │                  Electron Desktop App                               │    ║
║  │                  src/desktop-app/                                   │    ║
║  │                                                                     │    ║
║  │  ┌──────────────────────┐   ┌───────────────┐   ┌───────────────┐  │    ║
║  │  │   index.html         │   │   main.js     │   │  preload.js   │  │    ║
║  │  │   BatteryOS Dashboard│◄──│   Main Process│◄──│  ContextBridge│  │    ║
║  │  │   (HTML/CSS/JS UI)   │   │   BrowserWindow│  │  window.      │  │    ║
║  │  │                      │   │   Tray Icon   │   │  batteryOS.*  │  │    ║
║  │  │  • Live battery %    │   │   IPC handlers│   └───────────────┘  │    ║
║  │  │  • Charge history    │   │   Child spawn │          ▲            │    ║
║  │  │  • Threshold sliders │   └──────┬────────┘          │            │    ║
║  │  │  • Mode selector     │          │ IPC (invoke)      │            │    ║
║  │  │  • Event log         │   ┌──────▼────────┐          │            │    ║
║  │  │  • Smart toggles     │   │  renderer.js  │──────────┘            │    ║
║  │  └──────────────────────┘   │  Renderer Proc│                       │    ║
║  │                             │  applySnapshot│                       │    ║
║  │                             │  IPC bridge   │                       │    ║
║  │                             └───────────────┘                       │    ║
║  └──────────────────────────────────┬────────────────────────────────--┘    ║
║                                     │ stdout JSON lines / stdin commands    ║
╚═════════════════════════════════════╪════════════════════════════════════════╝
                                      │
                ┌─────────────────────┴──────────────────────┐
                │               PROCESS BOUNDARY              │
                │        (child_process.spawn / IPC)          │
                └─────────────────────┬──────────────────────┘
                                      │
╔═════════════════════════════════════╪════════════════════════════════════════╗
║                     CORE  SERVICE  LAYER  (Python)                          ║
║                     src/core-service/                                        ║
║                                                                              ║
║  ┌───────────────────────────────────────────────────────────────────────┐  ║
║  │  __main__.py  ─── CLI entry (argparse: --max --min --interval --gui)  │  ║
║  └──────────────────────────────┬────────────────────────────────────────┘  ║
║                                 │                                            ║
║  ┌──────────────────────────────▼────────────────────────────────────────┐  ║
║  │  core.py — BatteryManager                                             │  ║
║  │                                                                       │  ║
║  │   • Polling loop (configurable interval, thread-safe)                 │  ║
║  │   • BatterySnapshot dataclass (immutable, shareable)                  │  ║
║  │   • Threshold enforcement (min / max logic)                           │  ║
║  │   • Charging mode selection (Balanced / Travel / Storage / Custom)    │  ║
║  │   • Delegates status reads  ──►  Platform adapter                     │  ║
║  │   • Delegates charge control ──►  Platform adapter                    │  ║
║  │   • SmartPlugController (optional IoT physical cutoff)                │  ║
║  └──────┬────────────────────────────────────────────────────────────────┘  ║
║         │                                                                    ║
║  ┌──────▼────────────────────────────────────────────────────────────────┐  ║
║  │  utils.py                                                             │  ║
║  │   • get_logger()        — rotating file + stderr logger               │  ║
║  │   • notify()            — cross-platform desktop notifications        │  ║
║  │   • detect_platform()   — OS detection                                │  ║
║  │   • BatterySnapshot     — shared dataclass                            │  ║
║  │   • SmartPlugController — Tasmota / Kasa HTTP commands                │  ║
║  └───────────────────────────────────────────────────────────────────────┘  ║
║                                                                              ║
║  ┌───────────────────────────────────────────────────────────────────────┐  ║
║  │  gui.py — tkinter status window (optional, --no-gui to disable)       │  ║
║  │   • BatteryGUI: live % display, progress bar, charge toggle buttons   │  ║
║  │   • Runs BatteryManager on a daemon thread                            │  ║
║  └───────────────────────────────────────────────────────────────────────┘  ║
║                                                                              ║
║  ┌───────────────────────────────────────────────────────────────────────┐  ║
║  │  platforms/  — OS-specific adapters (BasePlatform ABC)                │  ║
║  │                                                                       │  ║
║  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐   │  ║
║  │  │  linux.py       │  │  macos.py       │  │  windows.py         │   │  ║
║  │  │  LinuxPlatform  │  │  MacOSPlatform  │  │  WindowsPlatform    │   │  ║
║  │  │                 │  │                 │  │                     │   │  ║
║  │  │ read_status()   │  │ read_status()   │  │ read_status()       │   │  ║
║  │  │  psutil +       │  │  psutil +       │  │  psutil +           │   │  ║
║  │  │  sysfs nodes    │  │  ioreg parse    │  │  WMI / powercfg     │   │  ║
║  │  │                 │  │                 │  │                     │   │  ║
║  │  │ stop/start_     │  │ stop/start_     │  │ stop/start_         │   │  ║
║  │  │ charging()      │  │ charging()      │  │ charging()          │   │  ║
║  │  │  sysfs thresh.  │  │  batteryos-macos│  │  batteryos-windows  │   │  ║
║  │  │  → batteryos-   │  │  → bclm (brew) │  │  → powercfg OEM     │   │  ║
║  │  │    linux helper │  │                 │  │  Requires Admin     │   │  ║
║  │  └─────────────────┘  └─────────────────┘  └─────────────────────┘   │  ║
║  │                                                                       │  ║
║  │  __init__.py — get_platform() factory, BasePlatform ABC               │  ║
║  └───────────────────────────────────────────────────────────────────────┘  ║
║                                                                              ║
╚══════════════════════════════════╪═══════════════════════════════════════════╝
                                   │  subprocess calls (argv: start/stop/status)
╔══════════════════════════════════╪═══════════════════════════════════════════╗
║              NATIVE  MODULE  LAYER  (C++17)                                  ║
║              src/native-modules/                                              ║
║                                                                              ║
║  ┌────────────────────────────────────────────────────────────────────────┐ ║
║  │  cli_main.cpp  — shared CLI entry point (start / stop / status → JSON) │ ║
║  └──────────────────────────────────┬─────────────────────────────────────┘ ║
║                                     │                                        ║
║  ┌──────────────────┐  ┌────────────▼──────────┐  ┌──────────────────────┐ ║
║  │  linux/          │  │  macos/               │  │  windows/            │ ║
║  │  battery_control │  │  battery_control      │  │  battery_control     │ ║
║  │  .h / .cpp       │  │  .h / .cpp            │  │  .h / .cpp           │ ║
║  │                  │  │                       │  │                      │ ║
║  │  sysfs read      │  │  IOKit / CF read      │  │  GetSystemPowerStatus│ ║
║  │  charge_stop_    │  │  IORegistryEntry       │  │  IOCTL_BATTERY_*     │ ║
║  │  threshold write │  │  CreateCFProperties   │  │  SetupDiGetClass     │ ║
║  │  charge_start_   │  │                       │  │                      │ ║
║  │  threshold write │  │  SMC BCLM key write   │  │  WMI OEM threshold   │ ║
║  │                  │  │  (charge max limit)   │  │  (Lenovo/Dell/ASUS)  │ ║
║  │  Output binary:  │  │  SMC BCLB key write   │  │                      │ ║
║  │  batteryos-linux │  │  (charge min limit)   │  │  Output binary:      │ ║
║  │                  │  │  IOPMSetChargeInhibit │  │  batteryos-windows   │ ║
║  │                  │  │                       │  │  (UAC manifest)      │ ║
║  │                  │  │  Output binary:       │  │                      │ ║
║  │                  │  │  batteryos-macos      │  │                      │ ║
║  └──────────────────┘  └───────────────────────┘  └──────────────────────┘ ║
║                                                                              ║
║  CMakeLists.txt — platform-guarded build, installs to /usr/local/bin        ║
╚══════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║           SYSTEM  SERVICE  LAYER  (Rust) — optional production daemon        ║
║           src/system-service/                                                ║
║                                                                              ║
║  ┌───────────────────────────────────────────────────────────────────────┐  ║
║  │  main.rs — Tokio async loop                                           │  ║
║  │   • Polls battery at configurable interval                            │  ║
║  │   • Emits BatterySnapshot as JSON line to stdout (same protocol as    │  ║
║  │     Python service — drop-in replacement for Electron main.js)        │  ║
║  │   • Enforces charge thresholds via sysfs / native helpers             │  ║
║  │   • Handles SIGTERM / SIGINT gracefully                               │  ║
║  └───────────────────────────────────────────────────────────────────────┘  ║
║                                                                              ║
║  ┌───────────────────────────────────────────────────────────────────────┐  ║
║  │  battery.rs — BatteryReader trait + platform impls                    │  ║
║  │                                                                       │  ║
║  │  ┌──────────────────┐  ┌─────────────────┐  ┌───────────────────┐    │  ║
║  │  │ LinuxReader      │  │ MacosReader     │  │ WindowsReader     │    │  ║
║  │  │ sysfs /sys/class │  │ ioreg subprocess│  │ GetSystemPower    │    │  ║
║  │  │ /power_supply/   │  │ + CF parsing    │  │ Status + IOCTL    │    │  ║
║  │  └──────────────────┘  └─────────────────┘  └───────────────────┘    │  ║
║  └───────────────────────────────────────────────────────────────────────┘  ║
║                                                                              ║
║  Cargo.toml — serde, tokio, tracing, platform-gated deps                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║                    EXTERNAL  INTEGRATIONS                                    ║
║                                                                              ║
║  ┌────────────────────────────────┐   ┌──────────────────────────────────┐  ║
║  │  IoT Smart Plug (optional)     │   │  OS Notification System          │  ║
║  │                                │   │                                  │  ║
║  │  SmartPlugController (utils.py)│   │  macOS: osascript AppleScript    │  ║
║  │  Tasmota HTTP API              │   │  Linux:  notify-send             │  ║
║  │  TP-Link Kasa (python-kasa)    │   │  Windows: win10toast ToastNotif. │  ║
║  │  BATTERYOS_PLUG_IP env var     │   │                                  │  ║
║  └────────────────────────────────┘   └──────────────────────────────────┘  ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## Data Flow

```
Hardware Battery
      │
      ▼
OS Kernel (sysfs / IOKit / WinAPI)
      │
      ├──► Platform Adapter (platforms/linux.py | macos.py | windows.py)
      │         │  psutil + OS-specific enrichment
      │         ▼
      │    BatterySnapshot (dataclass)
      │         │
      │    BatteryManager (core.py)
      │         │  threshold enforcement
      │         │  notification dispatch
      │         │  SmartPlug control
      │         │
      │    ┌────┴────────────────────────────────────┐
      │    │  stdout (JSON line per tick)             │
      │    ▼                                          ▼
      │  Electron main.js                        tkinter GUI
      │    │ IPC push                            (gui.py)
      │    ▼
      │  renderer.js → applySnapshot()
      │    ▼
      │  BatteryOS Dashboard (index.html)
      │
      └──► [charge control needed?]
                │
                ├── Platform Adapter (sysfs write / ioreg / WMI)
                └── Native Helper binary (privileged subprocess)
                          └── batteryos-linux / macos / windows
```

---

## Component Responsibility Matrix

| Component | Reads Battery | Controls Charging | Notifies User | Runs as Root |
|---|---|---|---|---|
| `platforms/linux.py` | ✅ sysfs + psutil | ✅ sysfs threshold | ❌ | Optional |
| `platforms/macos.py` | ✅ ioreg + psutil | ✅ via helper/bclm | ❌ | No (helper does) |
| `platforms/windows.py` | ✅ WMI + psutil | ✅ via helper | ❌ | Required |
| `native-modules/linux` | ✅ sysfs | ✅ sysfs write | ❌ | Optional (udev) |
| `native-modules/macos` | ✅ IOKit CFProps | ✅ SMC BCLM/BCLB | ❌ | Required |
| `native-modules/windows` | ✅ IOCTL_BATTERY | ⚠️ OEM WMI only | ❌ | Required |
| `core.py` | Delegates | Delegates | Via utils | No |
| `utils.py` | No | No | ✅ all platforms | No |
| `gui.py` | Via manager | Via platform | ❌ | No |
| `main.js` (Electron) | Via child proc | Via IPC | ❌ | No |
| `main.rs` (Rust) | ✅ native | ✅ sysfs/helper | ❌ | Optional |

---

## Process Architecture

```
┌─────────────────────────────────────────────────┐
│  OS Process: batteryos (Electron)               │
│                                                 │
│  Main Process (Node.js)                         │
│    ├── BrowserWindow (Chromium renderer)        │
│    ├── Tray icon                                │
│    └── IPC handlers                            │
│                                                 │
│  Child Process: python3 __main__.py             │
│    ├── BatteryManager thread                    │
│    ├── Platform adapter                         │
│    └── stdout → JSON snapshots                  │
│                                                 │
│  [Optional] Child Process: batteryos-service    │
│    └── Rust async poller (stdout JSON)          │
│                                                 │
│  [Optional] Subprocess: batteryos-linux/macos/  │
│             windows (privileged, short-lived)   │
└─────────────────────────────────────────────────┘
```

---

## Directory Structure (complete)

```
src/
├── core-service/                  Python monitoring engine
│   ├── platforms/
│   │   ├── __init__.py            BasePlatform ABC + get_platform() factory
│   │   ├── linux.py               LinuxPlatform  (sysfs + psutil)
│   │   ├── macos.py               MacOSPlatform  (ioreg + psutil + bclm)
│   │   └── windows.py             WindowsPlatform (WMI + psutil + powercfg)
│   ├── __init__.py                Package exports
│   ├── __main__.py                CLI entry (argparse)
│   ├── core.py                    BatteryManager loop + BatterySnapshot
│   ├── gui.py                     tkinter status window
│   ├── utils.py                   Logger, notify, SmartPlugController
│   └── requirements.txt
│
├── native-modules/                Privileged C++17 helper binaries
│   ├── linux/
│   │   ├── battery_control.h
│   │   └── battery_control.cpp    sysfs reads + threshold writes
│   ├── macos/
│   │   ├── battery_control.h
│   │   └── battery_control.cpp    IOKit + SMC BCLM/BCLB + IOPMSetChargeInhibit
│   ├── windows/
│   │   ├── battery_control.h
│   │   └── battery_control.cpp    WinAPI IOCTL_BATTERY_* + WMI OEM
│   ├── cli_main.cpp               Shared CLI wrapper (start/stop/status)
│   └── CMakeLists.txt             Platform-guarded CMake build
│
├── desktop-app/                   Electron shell
│   ├── src/
│   │   ├── index.html             BatteryOS dashboard (HTML/CSS/JS)
│   │   ├── main.js                Main process: window, tray, child spawn, IPC
│   │   ├── preload.js             contextBridge — window.batteryOS API
│   │   └── renderer.js            Wires live data into dashboard state
│   ├── package.json
│   └── webpack.config.js
│
├── system-service/                Optional Rust production daemon
│   ├── src/
│   │   ├── main.rs                Tokio loop, JSON stdout, SIGTERM handling
│   │   └── battery.rs             BatteryReader trait + Linux/macOS/Windows impls
│   └── Cargo.toml
│
└── README.md
```
