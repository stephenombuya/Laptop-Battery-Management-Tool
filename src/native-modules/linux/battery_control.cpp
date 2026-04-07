/**
 * @file   battery_control.cpp
 * @brief  Linux battery control implementation (ACPI / sysfs)
 *
 * Reads battery state from /sys/class/power_supply/BAT* sysfs nodes and
 * writes charge thresholds via charge_stop_threshold / charge_start_threshold.
 *
 * Build (standalone test):
 *   g++ -std=c++17 -Wall -Wextra -o battery_control battery_control.cpp
 */

#include "battery_control.h"

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <string>

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------

namespace {

/** Absolute sysfs path to the detected battery, e.g. /sys/class/power_supply/BAT0 */
std::string g_bat_path;

// ---------------------------------------------------------------------------
// sysfs helpers
// ---------------------------------------------------------------------------

/**
 * Read a sysfs text node and return its trimmed content.
 * Returns an empty string on any error.
 */
std::string read_node(const std::string &bat_path, const char *node) {
    std::string path = bat_path + "/" + node;
    char buf[256] = {};
    int fd = ::open(path.c_str(), O_RDONLY);
    if (fd < 0) return {};
    ssize_t n = ::read(fd, buf, sizeof(buf) - 1);
    ::close(fd);
    if (n <= 0) return {};
    // Trim trailing whitespace / newlines
    std::string s(buf, static_cast<size_t>(n));
    while (!s.empty() && (s.back() == '\n' || s.back() == '\r' || s.back() == ' '))
        s.pop_back();
    return s;
}

/**
 * Write a value to a sysfs node.
 * @return true on success, false on failure (sets errno).
 */
bool write_node(const std::string &bat_path, const char *node, const std::string &value) {
    std::string path = bat_path + "/" + node;
    int fd = ::open(path.c_str(), O_WRONLY);
    if (fd < 0) return false;
    ssize_t written = ::write(fd, value.c_str(), value.size());
    ::close(fd);
    return written == static_cast<ssize_t>(value.size());
}

/** Parse a sysfs node as a double (µWh, µW, µV → divided by caller). */
bool read_double(const std::string &bat_path, const char *node, double &out) {
    std::string s = read_node(bat_path, node);
    if (s.empty()) return false;
    char *end = nullptr;
    out = std::strtod(s.c_str(), &end);
    return end != s.c_str();
}

/** Parse a sysfs node as an unsigned 32-bit integer. */
bool read_u32(const std::string &bat_path, const char *node, uint32_t &out) {
    std::string s = read_node(bat_path, node);
    if (s.empty()) return false;
    char *end = nullptr;
    unsigned long v = std::strtoul(s.c_str(), &end, 10);
    if (end == s.c_str()) return false;
    out = static_cast<uint32_t>(v);
    return true;
}

// ---------------------------------------------------------------------------
// Battery detection
// ---------------------------------------------------------------------------

/**
 * Search /sys/class/power_supply/ for the first BAT* directory.
 * Prefers BAT0, then BAT1, then any BAT* entry.
 */
std::string find_battery() {
    static const char *preferred[] = {"BAT0", "BAT1", nullptr};
    const std::string base = "/sys/class/power_supply/";

    for (int i = 0; preferred[i]; ++i) {
        std::string path = base + preferred[i];
        struct stat st{};
        if (::stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode))
            return path;
    }

    // Generic scan for any BAT* entry
    DIR *dir = ::opendir(base.c_str());
    if (!dir) return {};
    struct dirent *entry;
    std::string found;
    while ((entry = ::readdir(dir)) != nullptr) {
        if (std::strncmp(entry->d_name, "BAT", 3) == 0) {
            found = base + entry->d_name;
            break;
        }
    }
    ::closedir(dir);
    return found;
}

} // namespace

// ---------------------------------------------------------------------------
// Init / cleanup
// ---------------------------------------------------------------------------

BatteryResult battery_init() {
    g_bat_path = find_battery();
    if (g_bat_path.empty()) return BAT_ERR_NO_BATTERY;
    return BAT_OK;
}

void battery_cleanup() {
    g_bat_path.clear();
}

// ---------------------------------------------------------------------------
// Status query
// ---------------------------------------------------------------------------

BatteryResult battery_read_status(BatteryStatus *status) {
    if (!status)           return BAT_ERR_SYSTEM;
    if (g_bat_path.empty()) return BAT_ERR_NO_BATTERY;

    std::memset(status, 0, sizeof(*status));

    // ── Charge level ───────────────────────────────────────────────────────
    double capacity = 0.0;
    if (!read_double(g_bat_path, "capacity", capacity))
        return BAT_ERR_NO_BATTERY;   // capacity is the one mandatory node
    status->percent = static_cast<float>(capacity);

    // ── Charge status ──────────────────────────────────────────────────────
    std::string charging_status = read_node(g_bat_path, "status");
    status->plugged_in = (charging_status == "Charging" || charging_status == "Full");
    status->charging   = (charging_status == "Charging");

    // ── Energy (µWh) ───────────────────────────────────────────────────────
    double energy_now    = 0.0;
    double energy_full   = 0.0;
    double energy_design = 0.0;

    bool has_energy_now    = read_double(g_bat_path, "energy_now",          energy_now);
    bool has_energy_full   = read_double(g_bat_path, "energy_full",         energy_full);
    bool has_energy_design = read_double(g_bat_path, "energy_full_design",  energy_design);

    // µWh → Wh
    if (has_energy_now)    energy_now    /= 1'000'000.0;
    if (has_energy_full)   energy_full   /= 1'000'000.0;
    if (has_energy_design) energy_design /= 1'000'000.0;

    // ── Power draw (µW → W) ────────────────────────────────────────────────
    double power_now = 0.0;
    if (read_double(g_bat_path, "power_now", power_now)) {
        power_now /= 1'000'000.0;
        // Positive when charging, negative when discharging
        status->power_watts = static_cast<float>(status->charging ? power_now : -power_now);
    }

    // ── Time remaining ─────────────────────────────────────────────────────
    if (has_energy_now && power_now > 0.0) {
        if (status->charging && has_energy_full) {
            double to_full = energy_full - energy_now;
            status->time_left_seconds = static_cast<float>((to_full / power_now) * 3600.0);
        } else if (!status->charging) {
            status->time_left_seconds = static_cast<float>((energy_now / power_now) * 3600.0);
        }
    }

    // ── Health ─────────────────────────────────────────────────────────────
    if (has_energy_full && has_energy_design && energy_design > 0.0) {
        status->health_percent = static_cast<float>(
            (energy_full / energy_design) * 100.0
        );
    }

    // ── Voltage (µV → V) ───────────────────────────────────────────────────
    double voltage_now = 0.0;
    if (read_double(g_bat_path, "voltage_now", voltage_now)) {
        status->voltage_volts = static_cast<float>(voltage_now / 1'000'000.0);
    }

    // ── Temperature (tenths of °C) ─────────────────────────────────────────
    double temp = 0.0;
    if (read_double(g_bat_path, "temp", temp)) {
        status->temperature_celsius = static_cast<float>(temp / 10.0);
    }

    // ── Cycle count ────────────────────────────────────────────────────────
    uint32_t cycles = 0;
    if (read_u32(g_bat_path, "cycle_count", cycles)) {
        status->cycle_count = cycles;
    }

    return BAT_OK;
}

// ---------------------------------------------------------------------------
// Charge control
// ---------------------------------------------------------------------------

BatteryResult battery_set_max_charge(uint8_t max_percent) {
    if (g_bat_path.empty()) return BAT_ERR_NO_BATTERY;

    // Clamp to valid range
    if (max_percent == 0 || max_percent > 100) return BAT_ERR_SYSTEM;

    std::string value = std::to_string(max_percent) + "\n";
    if (!write_node(g_bat_path, "charge_stop_threshold", value)) {
        return (errno == EACCES || errno == EPERM)
            ? BAT_ERR_PERMISSION
            : BAT_ERR_NOT_SUPPORTED;
    }
    return BAT_OK;
}

BatteryResult battery_set_min_charge(uint8_t min_percent) {
    if (g_bat_path.empty()) return BAT_ERR_NO_BATTERY;

    std::string value = std::to_string(min_percent) + "\n";
    if (!write_node(g_bat_path, "charge_start_threshold", value)) {
        return (errno == EACCES || errno == EPERM)
            ? BAT_ERR_PERMISSION
            : BAT_ERR_NOT_SUPPORTED;
    }
    return BAT_OK;
}

BatteryResult battery_stop_charging() {
    if (g_bat_path.empty()) return BAT_ERR_NO_BATTERY;

    // Read current level and set that as the stop threshold
    double current = 0.0;
    if (!read_double(g_bat_path, "capacity", current)) return BAT_ERR_SYSTEM;

    auto pct = static_cast<uint8_t>(current);
    return battery_set_max_charge(pct > 0 ? pct : 1);
}

BatteryResult battery_start_charging() {
    if (g_bat_path.empty()) return BAT_ERR_NO_BATTERY;

    // Reset thresholds to allow full charging
    BatteryResult r = battery_set_max_charge(100);
    if (r != BAT_OK && r != BAT_ERR_NOT_SUPPORTED) return r;
    battery_set_min_charge(0);   // best-effort
    return BAT_OK;
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

const char *battery_result_str(BatteryResult result) {
    switch (result) {
        case BAT_OK:                return "Success";
        case BAT_ERR_NO_BATTERY:    return "No battery present";
        case BAT_ERR_PERMISSION:    return "Insufficient privileges (run as root)";
        case BAT_ERR_NOT_SUPPORTED: return "Feature not supported on this hardware";
        case BAT_ERR_SYSTEM:        return "System / OS error";
        default:                    return "Unknown error";
    }
}
