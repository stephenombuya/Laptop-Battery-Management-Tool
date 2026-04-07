//! battery.rs
//! ===========
//! Cross-platform battery state reader.
//!
//! Each platform implements the same [`BatteryReader`] trait so the rest of
//! the codebase stays platform-agnostic.
//!
//! Supported platforms
//! -------------------
//! * **Linux**   — reads `/sys/class/power_supply/BAT*` sysfs nodes
//! * **macOS**   — queries IOKit via `ioreg` (subprocess, no unsafe FFI)
//! * **Windows** — calls `GetSystemPowerStatus` from the Win32 API

use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};

// ---------------------------------------------------------------------------
// Shared data model
// ---------------------------------------------------------------------------

/// A point-in-time snapshot of battery state.
/// Serialises to JSON for IPC / stdout streaming.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BatterySnapshot {
    /// Charge level, 0.0 – 100.0
    pub percent: f64,

    /// True while the battery is actively accepting charge
    pub charging: bool,

    /// True when an AC adapter is connected (may be full but still plugged in)
    pub plugged_in: bool,

    /// Estimated seconds remaining (None = unknown)
    pub time_left_seconds: Option<f64>,

    /// Instantaneous power draw in watts (negative = discharging)
    pub power_watts: Option<f64>,

    /// Battery temperature in °C
    pub temperature_celsius: Option<f64>,

    /// Battery health as a percentage of design capacity
    pub health_percent: Option<f64>,

    /// Charge cycle count
    pub cycle_count: Option<u32>,

    /// Terminal voltage in volts
    pub voltage_volts: Option<f64>,

    /// Unix timestamp of when this snapshot was taken
    pub timestamp: f64,
}

impl BatterySnapshot {
    /// Construct a snapshot with all optional fields set to `None`.
    pub fn minimal(percent: f64, charging: bool, plugged_in: bool) -> Self {
        Self {
            percent,
            charging,
            plugged_in,
            time_left_seconds: None,
            power_watts: None,
            temperature_celsius: None,
            health_percent: None,
            cycle_count: None,
            voltage_volts: None,
            timestamp: unix_now(),
        }
    }
}

fn unix_now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

// ---------------------------------------------------------------------------
// Trait
// ---------------------------------------------------------------------------

/// Platform-specific battery reader.
pub trait BatteryReader: Send + Sync {
    /// Read the current battery state.  Returns `None` if no battery is present
    /// (e.g., the process is running on a desktop).
    fn read(&self) -> anyhow::Result<Option<BatterySnapshot>>;
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/// Return the correct [`BatteryReader`] for the current platform.
pub fn platform_reader() -> Box<dyn BatteryReader> {
    #[cfg(target_os = "linux")]
    return Box::new(LinuxReader::new());

    #[cfg(target_os = "macos")]
    return Box::new(MacosReader::new());

    #[cfg(target_os = "windows")]
    return Box::new(WindowsReader::new());

    #[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
    compile_error!("BatteryOS only supports Linux, macOS, and Windows.");
}

// ---------------------------------------------------------------------------
// Linux implementation — sysfs
// ---------------------------------------------------------------------------

#[cfg(target_os = "linux")]
mod linux {
    use super::{BatteryReader, BatterySnapshot};
    use std::fs;
    use std::path::{Path, PathBuf};

    pub struct LinuxReader {
        bat_path: Option<PathBuf>,
    }

    impl LinuxReader {
        pub fn new() -> Self {
            let bat_path = Self::find_battery();
            if bat_path.is_none() {
                tracing::warn!("No battery found under /sys/class/power_supply/");
            }
            Self { bat_path }
        }

        fn find_battery() -> Option<PathBuf> {
            // Prefer BAT0, then BAT1, then any BAT* entry
            for name in ["BAT0", "BAT1"] {
                let p = PathBuf::from(format!("/sys/class/power_supply/{}", name));
                if p.exists() {
                    return Some(p);
                }
            }
            // Generic fallback
            fs::read_dir("/sys/class/power_supply")
                .ok()?
                .filter_map(|e| e.ok())
                .map(|e| e.path())
                .find(|p| p.file_name().and_then(|n| n.to_str()).map_or(false, |n| n.starts_with("BAT")))
        }

        fn read_node(&self, node: &str) -> Option<String> {
            let path = self.bat_path.as_ref()?.join(node);
            fs::read_to_string(&path).ok().map(|s| s.trim().to_owned())
        }

        fn read_f64(&self, node: &str) -> Option<f64> {
            self.read_node(node)?.parse().ok()
        }

        fn read_i64(&self, node: &str) -> Option<i64> {
            self.read_node(node)?.parse().ok()
        }
    }

    impl BatteryReader for LinuxReader {
        fn read(&self) -> anyhow::Result<Option<BatterySnapshot>> {
            if self.bat_path.is_none() {
                return Ok(None);
            }

            let status   = self.read_node("status").unwrap_or_default();
            let plugged  = matches!(status.as_str(), "Charging" | "Full");
            let charging = status == "Charging";

            let capacity = match self.read_f64("capacity") {
                Some(v) => v,
                None    => return Ok(None),
            };

            // Energy in µWh → Wh
            let energy_now  = self.read_f64("energy_now").map(|v| v / 1_000_000.0);
            let energy_full = self.read_f64("energy_full").map(|v| v / 1_000_000.0);
            let power_now   = self.read_f64("power_now").map(|v| v / 1_000_000.0);

            let health = match (energy_full, self.read_f64("energy_full_design")) {
                (Some(full), Some(design)) if design > 0.0 => Some((full / design) * 100.0),
                _ => None,
            };

            let time_left = match (energy_now, power_now) {
                (Some(e), Some(p)) if p > 0.0 => Some((e / p) * 3600.0),
                _ => None,
            };

            // Temperature in tenths of °C
            let temp = self.read_f64("temp").map(|t| t / 10.0);

            let voltage = self.read_i64("voltage_now").map(|v| v as f64 / 1_000_000.0);
            let cycles  = self.read_node("cycle_count").and_then(|s| s.parse().ok());

            let mut snap = BatterySnapshot::minimal(capacity, charging, plugged);
            snap.time_left_seconds    = time_left;
            snap.power_watts          = power_now.map(|p| if charging { p } else { -p });
            snap.temperature_celsius  = temp;
            snap.health_percent       = health;
            snap.cycle_count          = cycles;
            snap.voltage_volts        = voltage;

            Ok(Some(snap))
        }
    }
}

#[cfg(target_os = "linux")]
use linux::LinuxReader;

// ---------------------------------------------------------------------------
// macOS implementation — ioreg subprocess
// ---------------------------------------------------------------------------

#[cfg(target_os = "macos")]
mod macos {
    use super::{BatteryReader, BatterySnapshot};
    use std::process::Command;

    pub struct MacosReader;

    impl MacosReader {
        pub fn new() -> Self {
            Self
        }

        /// Run `ioreg -rn AppleSmartBattery` and parse key-value pairs.
        fn ioreg_output() -> anyhow::Result<String> {
            let output = Command::new("ioreg")
                .args(["-rn", "AppleSmartBattery"])
                .output()?;
            Ok(String::from_utf8_lossy(&output.stdout).into_owned())
        }

        fn parse_value<T: std::str::FromStr>(output: &str, key: &str) -> Option<T> {
            output
                .lines()
                .find(|l| l.contains(key))
                .and_then(|l| l.split('=').nth(1))
                .and_then(|v| v.trim().parse().ok())
        }

        fn parse_bool(output: &str, key: &str) -> Option<bool> {
            output
                .lines()
                .find(|l| l.contains(key))
                .and_then(|l| l.split('=').nth(1))
                .map(|v| v.trim().eq_ignore_ascii_case("yes"))
        }
    }

    impl BatteryReader for MacosReader {
        fn read(&self) -> anyhow::Result<Option<BatterySnapshot>> {
            let raw = Self::ioreg_output()?;

            let max_cap: Option<f64>  = Self::parse_value(&raw, "MaxCapacity");
            let cur_cap: Option<f64>  = Self::parse_value(&raw, "CurrentCapacity");
            let design_cap: Option<f64> = Self::parse_value(&raw, "DesignCapacity");

            let (percent, health) = match (cur_cap, max_cap, design_cap) {
                (Some(cur), Some(max), Some(design)) if max > 0.0 && design > 0.0 => {
                    ((cur / max * 100.0), Some(max / design * 100.0))
                }
                _ => return Ok(None),
            };

            let charging  = Self::parse_bool(&raw, "IsCharging").unwrap_or(false);
            let plugged   = Self::parse_bool(&raw, "ExternalConnected").unwrap_or(false);
            let cycles: Option<u32> = Self::parse_value(&raw, "CycleCount");
            let voltage   = Self::parse_value::<f64>(&raw, "Voltage").map(|v| v / 1000.0);
            let temp      = Self::parse_value::<f64>(&raw, "Temperature").map(|t| t / 100.0);
            let time_rem: Option<f64> = Self::parse_value::<f64>(&raw, "TimeRemaining")
                .map(|m| m * 60.0);

            let mut snap = BatterySnapshot::minimal(percent, charging, plugged);
            snap.health_percent      = health;
            snap.cycle_count         = cycles;
            snap.voltage_volts       = voltage;
            snap.temperature_celsius = temp;
            snap.time_left_seconds   = time_rem;

            Ok(Some(snap))
        }
    }
}

#[cfg(target_os = "macos")]
use macos::MacosReader;

// ---------------------------------------------------------------------------
// Windows implementation — GetSystemPowerStatus
// ---------------------------------------------------------------------------

#[cfg(target_os = "windows")]
mod windows_impl {
    use super::{BatteryReader, BatterySnapshot};
    use windows::Win32::System::Power::{GetSystemPowerStatus, SYSTEM_POWER_STATUS};

    pub struct WindowsReader;

    impl WindowsReader {
        pub fn new() -> Self {
            Self
        }
    }

    impl BatteryReader for WindowsReader {
        fn read(&self) -> anyhow::Result<Option<BatterySnapshot>> {
            let mut status = SYSTEM_POWER_STATUS::default();
            unsafe { GetSystemPowerStatus(&mut status)? };

            // 255 = no battery
            if status.BatteryFlag == 128 {
                return Ok(None);
            }

            let percent  = status.BatteryLifePercent as f64;
            let plugged  = status.ACLineStatus == 1;
            let charging = plugged && percent < 100.0;

            let time_left = match status.BatteryLifeTime {
                u32::MAX => None,
                secs     => Some(secs as f64),
            };

            let mut snap = BatterySnapshot::minimal(percent, charging, plugged);
            snap.time_left_seconds = time_left;

            Ok(Some(snap))
        }
    }
}

#[cfg(target_os = "windows")]
use windows_impl::WindowsReader;
