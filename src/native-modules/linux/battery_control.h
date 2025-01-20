#pragma once

extern "C" {
    bool initialize_battery_control();
    int get_battery_level();
    bool is_charging();
    bool set_charging_state(bool enable);
}
