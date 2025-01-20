#pragma once
#include <windows.h>

extern "C" {
    __declspec(dllexport) bool initialize_battery_control();
    __declspec(dllexport) int get_battery_level();
    __declspec(dllexport) bool is_charging();
    __declspec(dllexport) bool set_charging_state(bool enable);
}
