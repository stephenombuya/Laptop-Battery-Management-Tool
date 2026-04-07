/**
 * @file   cli_main.cpp
 * @brief  Thin CLI wrapper shared by all platform-specific helper binaries.
 *
 * Accepts a single argument: "start" or "stop".
 * Delegates to the platform battery_control API and exits with 0 on success
 * or a non-zero code on failure (so the Python / Rust caller can detect errors
 * via the subprocess return code).
 *
 * Usage
 * -----
 *   batteryos-linux  stop
 *   batteryos-linux  start
 *   batteryos-linux  status    # prints JSON to stdout
 */

#include <cstdio>
#include <cstring>

// The platform-specific header is resolved by CMake's include path
#include "battery_control.h"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static void print_usage(const char *prog) {
    std::fprintf(stderr,
        "Usage: %s <command>\n"
        "\n"
        "Commands:\n"
        "  start   Resume charging\n"
        "  stop    Halt charging\n"
        "  status  Print battery status as JSON (one line)\n"
        "\n"
        "Exit codes:\n"
        "  0  Success\n"
        "  1  Bad arguments\n"
        "  2  No battery detected\n"
        "  3  Permission denied\n"
        "  4  Feature not supported on this hardware\n"
        "  5  System error\n",
        prog
    );
}

/** Map a BatteryResult to a process exit code. */
static int result_to_exit(BatteryResult r) {
    switch (r) {
        case BAT_OK:                return 0;
        case BAT_ERR_NO_BATTERY:    return 2;
        case BAT_ERR_PERMISSION:    return 3;
        case BAT_ERR_NOT_SUPPORTED: return 4;
        case BAT_ERR_SYSTEM:        return 5;
        default:                    return 5;
    }
}

/** Print a BatteryStatus struct as a single JSON line to stdout. */
static void print_status_json(const BatteryStatus &s) {
    std::printf(
        "{"
        "\"percent\":%.1f,"
        "\"charging\":%s,"
        "\"plugged_in\":%s,"
        "\"time_left_seconds\":%.0f,"
        "\"voltage_volts\":%.3f,"
        "\"power_watts\":%.2f,"
        "\"cycle_count\":%u,"
        "\"health_percent\":%.1f,"
        "\"temperature_celsius\":%.1f"
        "}\n",
        static_cast<double>(s.percent),
        s.charging   ? "true" : "false",
        s.plugged_in ? "true" : "false",
        static_cast<double>(s.time_left_seconds),
        static_cast<double>(s.voltage_volts),
        static_cast<double>(s.power_watts),
        s.cycle_count,
        static_cast<double>(s.health_percent),
        static_cast<double>(s.temperature_celsius)
    );
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

int main(int argc, char *argv[]) {
    if (argc != 2) {
        print_usage(argv[0]);
        return 1;
    }

    const char *command = argv[1];

    // Initialise the platform module (opens device handles, detects sysfs path)
    BatteryResult init_result = battery_init();
    if (init_result != BAT_OK) {
        std::fprintf(stderr, "Error: battery_init() — %s\n",
                     battery_result_str(init_result));
        return result_to_exit(init_result);
    }

    BatteryResult result = BAT_OK;

    if (std::strcmp(command, "stop") == 0) {
        result = battery_stop_charging();
        if (result == BAT_OK) {
            std::fprintf(stderr, "Charging stopped.\n");
        }

    } else if (std::strcmp(command, "start") == 0) {
        result = battery_start_charging();
        if (result == BAT_OK) {
            std::fprintf(stderr, "Charging resumed.\n");
        }

    } else if (std::strcmp(command, "status") == 0) {
        BatteryStatus status{};
        result = battery_read_status(&status);
        if (result == BAT_OK) {
            print_status_json(status);
        }

    } else {
        std::fprintf(stderr, "Unknown command: '%s'\n\n", command);
        print_usage(argv[0]);
        battery_cleanup();
        return 1;
    }

    if (result != BAT_OK) {
        std::fprintf(stderr, "Error: %s\n", battery_result_str(result));
    }

    battery_cleanup();
    return result_to_exit(result);
}
