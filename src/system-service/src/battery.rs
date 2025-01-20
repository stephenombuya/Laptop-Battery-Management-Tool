use battery::Battery;
use serde::Serialize;

#[derive(Serialize)]
pub struct BatteryStatus {
    level: f32,
    charging: bool,
    time_remaining: Option<u64>,
}

impl BatteryStatus {
    pub fn from_battery(battery: &Battery) -> Self {
        Self {
            level: battery.state_of_charge().value * 100.0,
            charging: battery.state().is_charging(),
            time_remaining: None, // Implement time calculation
        }
    }
}
