//! main.rs — BatteryOS System Service
//! ====================================
//! High-performance background daemon written in Rust.
//!
//! Responsibilities
//! ----------------
//! * Poll battery state at a configurable interval via platform-native APIs.
//! * Stream [`BatterySnapshot`] JSON objects (one per line) to stdout so the
//!   Electron main process can consume them without polling.
//! * Enforce charge thresholds by writing to sysfs / calling native helpers.
//! * Handle SIGTERM / SIGINT gracefully so the service unregisters cleanly.
//!
//! Usage
//! -----
//! ```text
//! batteryos-service [--max <pct>] [--min <pct>] [--interval <sec>]
//! ```

mod battery;

use battery::{platform_reader, BatterySnapshot};
use std::{sync::Arc, time::Duration};
use tokio::{signal, time};
use tracing::{error, info, warn};
use tracing_subscriber::{fmt, EnvFilter};

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
struct Config {
    max_charge_limit: u8,
    min_charge_limit: u8,
    check_interval_secs: u64,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            max_charge_limit:    80,
            min_charge_limit:    20,
            check_interval_secs: 300,
        }
    }
}

impl Config {
    fn from_env_and_args() -> Self {
        let mut cfg = Self::default();
        let args: Vec<String> = std::env::args().collect();
        let mut i = 1;
        while i < args.len() {
            match args[i].as_str() {
                "--max" if i + 1 < args.len() => {
                    if let Ok(v) = args[i + 1].parse::<u8>() {
                        cfg.max_charge_limit = v;
                        i += 1;
                    }
                }
                "--min" if i + 1 < args.len() => {
                    if let Ok(v) = args[i + 1].parse::<u8>() {
                        cfg.min_charge_limit = v;
                        i += 1;
                    }
                }
                "--interval" if i + 1 < args.len() => {
                    if let Ok(v) = args[i + 1].parse::<u64>() {
                        cfg.check_interval_secs = v;
                        i += 1;
                    }
                }
                _ => {}
            }
            i += 1;
        }
        cfg
    }

    fn validate(&self) -> Result<(), String> {
        if self.min_charge_limit >= self.max_charge_limit {
            return Err(format!(
                "min ({}) must be strictly less than max ({})",
                self.min_charge_limit, self.max_charge_limit
            ));
        }
        if self.max_charge_limit > 100 {
            return Err(format!("max ({}) cannot exceed 100", self.max_charge_limit));
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

#[tokio::main(flavor = "current_thread")]
async fn main() {
    // Initialise logging — honours RUST_LOG env var, defaults to INFO
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .with_writer(std::io::stderr)   // logs to stderr; JSON snapshots go to stdout
        .init();

    let config = Config::from_env_and_args();

    if let Err(e) = config.validate() {
        error!("Invalid configuration: {}", e);
        std::process::exit(1);
    }

    info!(
        max  = config.max_charge_limit,
        min  = config.min_charge_limit,
        interval = config.check_interval_secs,
        "BatteryOS service starting."
    );

    let config = Arc::new(config);
    let reader = platform_reader();

    // Track whether we have already acted on the current threshold event
    // to avoid spamming the charging-control command every tick.
    let mut charging_halted = false;

    let interval = Duration::from_secs(config.check_interval_secs);
    let mut ticker = time::interval(interval);

    loop {
        tokio::select! {
            _ = ticker.tick() => {
                match reader.read() {
                    Ok(Some(snap)) => {
                        emit_snapshot(&snap);
                        enforce_limits(&snap, &config, &mut charging_halted);
                    }
                    Ok(None) => {
                        warn!("No battery detected — is this a desktop?");
                    }
                    Err(e) => {
                        error!("Failed to read battery state: {:#}", e);
                    }
                }
            }

            _ = signal::ctrl_c() => {
                info!("SIGINT received — shutting down.");
                break;
            }
        }
    }

    info!("BatteryOS service stopped.");
}

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------

/// Serialise the snapshot to JSON and write it as a single line to stdout.
/// The Electron main process reads stdout line-by-line.
fn emit_snapshot(snap: &BatterySnapshot) {
    match serde_json::to_string(snap) {
        Ok(json) => println!("{}", json),
        Err(e)   => error!("Failed to serialise snapshot: {}", e),
    }
}

// ---------------------------------------------------------------------------
// Charge enforcement
// ---------------------------------------------------------------------------

fn enforce_limits(snap: &BatterySnapshot, config: &Config, charging_halted: &mut bool) {
    let pct = snap.percent as u8;

    if snap.plugged_in && pct >= config.max_charge_limit && snap.charging {
        if !*charging_halted {
            warn!(
                percent = pct,
                limit   = config.max_charge_limit,
                "Max charge limit reached — halting charging."
            );
            halt_charging();
            *charging_halted = true;
        }
    } else if !snap.plugged_in && pct <= config.min_charge_limit {
        warn!(
            percent = pct,
            limit   = config.min_charge_limit,
            "Battery at minimum threshold — please connect charger."
        );
        *charging_halted = false;
    } else if snap.plugged_in && !snap.charging && pct < config.min_charge_limit {
        info!(
            percent = pct,
            "Battery below min while plugged in — resuming charging."
        );
        resume_charging();
        *charging_halted = false;
    } else if !snap.charging {
        // Reset the flag when we're back to discharging
        *charging_halted = false;
    }
}

// ---------------------------------------------------------------------------
// Charging control stubs
// (In production these call the native module helpers.)
// ---------------------------------------------------------------------------

#[cfg(target_os = "linux")]
fn halt_charging() {
    use std::fs;
    for path in [
        "/sys/class/power_supply/BAT0/charge_stop_threshold",
        "/sys/class/power_supply/BAT1/charge_stop_threshold",
    ] {
        if std::path::Path::new(path).exists() {
            if let Err(e) = fs::write(path, "0\n") {
                error!("sysfs write failed ({}): {}", path, e);
            }
            return;
        }
    }
    run_helper("batteryos-linux", "stop");
}

#[cfg(target_os = "linux")]
fn resume_charging() {
    run_helper("batteryos-linux", "start");
}

#[cfg(target_os = "macos")]
fn halt_charging() {
    run_helper("batteryos-macos", "stop");
}

#[cfg(target_os = "macos")]
fn resume_charging() {
    run_helper("batteryos-macos", "start");
}

#[cfg(target_os = "windows")]
fn halt_charging() {
    run_helper("batteryos-windows.exe", "stop");
}

#[cfg(target_os = "windows")]
fn resume_charging() {
    run_helper("batteryos-windows.exe", "start");
}

/// Invoke a platform native helper binary with a single argument.
fn run_helper(binary: &str, arg: &str) {
    use std::process::Command;
    match Command::new(binary).arg(arg).status() {
        Ok(s) if s.success() => info!("{} {} succeeded.", binary, arg),
        Ok(s) => warn!("{} {} exited with status {}.", binary, arg, s),
        Err(e) => error!("Failed to run {} {}: {}", binary, arg, e),
    }
}
