/**
 * @file   battery_control.cpp
 * @brief  macOS battery control implementation (IOKit / CoreFoundation / SMC)
 *
 * Strategy
 * --------
 * Status queries:
 *   IOServiceGetMatchingService("AppleSmartBattery") →
 *   IORegistryEntryCreateCFProperties() →
 *   Extract typed CFDictionaryRef keys.
 *
 * Charge inhibit (stop / start):
 *   IOPMSetChargeInhibit() — available since macOS 10.7.
 *   Requires the process to run as root or hold the
 *   com.apple.private.iokit.batterycharge entitlement.
 *
 * Charge threshold (BCLM / BCLB SMC keys):
 *   Available on Apple Silicon and Intel T2 Macs (macOS 12+).
 *   Written via the AppleSMC IOService using IOConnectCallStructMethod
 *   with the documented SMC userspace protocol.
 *
 * Compilation:
 *   clang++ -std=c++17 -Wall -Wextra                           \
 *           -framework IOKit -framework CoreFoundation          \
 *           battery_control.cpp -o batteryos-macos
 */

#include "battery_control.h"

#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/ps/IOPSKeys.h>
#include <IOKit/ps/IOPowerSources.h>

#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstring>

// ---------------------------------------------------------------------------
// SMC userspace protocol
// (undocumented but stable; used by coconutBattery, AlDente, and bclm)
// ---------------------------------------------------------------------------

static const uint32_t KERNEL_INDEX_SMC     = 2;
static const uint8_t  SMC_CMD_READ_KEYINFO = 9;
static const uint8_t  SMC_CMD_WRITE_BYTES  = 6;

/** 'BCLM' — Battery Charge Level Maximum (0–100, uint8) */
static const uint32_t SMC_KEY_BCLM = 0x42434C4Du;
/** 'BCLB' — Battery Charge Level Bottom / start threshold (uint8) */
static const uint32_t SMC_KEY_BCLB = 0x42434C42u;

#pragma pack(push, 1)
struct SmcKeyInfo {
    uint32_t dataSize;
    uint32_t dataType;
    uint8_t  dataAttributes;
};

struct SmcKeyData {
    uint32_t   key;
    uint8_t    vers[6];        // SMCKeyData_vers_t
    uint8_t    pLimitData[12]; // SMCKeyData_pLimitData_t
    SmcKeyInfo keyInfo;
    uint8_t    result;
    uint8_t    status;
    uint8_t    data8;
    uint32_t   data32;
    uint8_t    bytes[32];
};
#pragma pack(pop)

// ---------------------------------------------------------------------------
// Module-level state
// ---------------------------------------------------------------------------

namespace {

io_service_t  g_battery_service = IO_OBJECT_NULL;
io_connect_t  g_smc_connect     = IO_OBJECT_NULL;

// ── CoreFoundation dictionary helpers ──────────────────────────────────────

bool cf_get_int32(CFDictionaryRef d, const char *key, int32_t &out) {
    CFStringRef k = CFStringCreateWithCString(kCFAllocatorDefault, key,
                                              kCFStringEncodingUTF8);
    CFTypeRef v = CFDictionaryGetValue(d, k);
    CFRelease(k);
    if (!v || CFGetTypeID(v) != CFNumberGetTypeID()) return false;
    return CFNumberGetValue(static_cast<CFNumberRef>(v),
                            kCFNumberSInt32Type, &out);
}

bool cf_get_bool(CFDictionaryRef d, const char *key, bool &out) {
    CFStringRef k = CFStringCreateWithCString(kCFAllocatorDefault, key,
                                              kCFStringEncodingUTF8);
    CFTypeRef v = CFDictionaryGetValue(d, k);
    CFRelease(k);
    if (!v || CFGetTypeID(v) != CFBooleanGetTypeID()) return false;
    out = CFBooleanGetValue(static_cast<CFBooleanRef>(v));
    return true;
}

bool cf_get_str(CFDictionaryRef d, const char *key, char *buf, size_t n) {
    CFStringRef k = CFStringCreateWithCString(kCFAllocatorDefault, key,
                                              kCFStringEncodingUTF8);
    CFTypeRef v = CFDictionaryGetValue(d, k);
    CFRelease(k);
    if (!v || CFGetTypeID(v) != CFStringGetTypeID()) return false;
    return CFStringGetCString(static_cast<CFStringRef>(v), buf,
                              static_cast<CFIndex>(n), kCFStringEncodingUTF8);
}

// ── SMC helpers ────────────────────────────────────────────────────────────

bool smc_open() {
    io_service_t svc = IOServiceGetMatchingService(
        kIOMainPortDefault, IOServiceMatching("AppleSMC"));
    if (svc == IO_OBJECT_NULL) return false;
    kern_return_t kr = IOServiceOpen(svc, mach_task_self(), 0, &g_smc_connect);
    IOObjectRelease(svc);
    return (kr == KERN_SUCCESS);
}

kern_return_t smc_call(SmcKeyData *in, SmcKeyData *out) {
    size_t sz = sizeof(SmcKeyData);
    return IOConnectCallStructMethod(g_smc_connect, KERNEL_INDEX_SMC,
                                     in, sz, out, &sz);
}

kern_return_t smc_read_key_info(uint32_t key, SmcKeyInfo &info) {
    SmcKeyData in{}, out{};
    in.key   = key;
    in.data8 = SMC_CMD_READ_KEYINFO;
    kern_return_t kr = smc_call(&in, &out);
    if (kr == KERN_SUCCESS) info = out.keyInfo;
    return kr;
}

/**
 * Write a single uint8 value to an SMC key.
 * Returns BAT_OK, BAT_ERR_NOT_SUPPORTED, or BAT_ERR_PERMISSION.
 */
BatteryResult smc_write_byte(uint32_t key, uint8_t value) {
    if (g_smc_connect == IO_OBJECT_NULL) return BAT_ERR_NOT_SUPPORTED;

    SmcKeyInfo info{};
    if (smc_read_key_info(key, info) != KERN_SUCCESS)
        return BAT_ERR_NOT_SUPPORTED;

    SmcKeyData in{}, out{};
    in.key      = key;
    in.keyInfo  = info;
    in.data8    = SMC_CMD_WRITE_BYTES;
    in.bytes[0] = value;

    kern_return_t kr = smc_call(&in, &out);
    if (kr != KERN_SUCCESS) return BAT_ERR_IOKIT;
    // result == 0x84 means "not authorised" on non-root callers
    if (out.result != 0) return BAT_ERR_PERMISSION;
    return BAT_OK;
}

} // namespace

// ---------------------------------------------------------------------------
// Init / cleanup
// ---------------------------------------------------------------------------

BatteryResult battery_init() {
    // 1. Locate the AppleSmartBattery IOService (name changed in macOS 13)
    g_battery_service = IOServiceGetMatchingService(
        kIOMainPortDefault, IOServiceMatching("AppleSmartBattery"));
    if (g_battery_service == IO_OBJECT_NULL) {
        g_battery_service = IOServiceGetMatchingService(
            kIOMainPortDefault, IOServiceMatching("IOPMPowerSource"));
    }
    if (g_battery_service == IO_OBJECT_NULL) return BAT_ERR_NO_BATTERY;

    // 2. Try to open the SMC — optional, failures are non-fatal
    if (!smc_open()) {
        // SMC unavailable: charge-limit writes will return NOT_SUPPORTED
        // but status reads will still work via IOKit.
        g_smc_connect = IO_OBJECT_NULL;
    }

    return BAT_OK;
}

void battery_cleanup() {
    if (g_battery_service != IO_OBJECT_NULL) {
        IOObjectRelease(g_battery_service);
        g_battery_service = IO_OBJECT_NULL;
    }
    if (g_smc_connect != IO_OBJECT_NULL) {
        IOServiceClose(g_smc_connect);
        g_smc_connect = IO_OBJECT_NULL;
    }
}

// ---------------------------------------------------------------------------
// Status query
// ---------------------------------------------------------------------------

BatteryResult battery_read_status(BatteryStatus *status) {
    if (!status)                             return BAT_ERR_SYSTEM;
    if (g_battery_service == IO_OBJECT_NULL) return BAT_ERR_NO_BATTERY;

    std::memset(status, 0, sizeof(*status));

    // Pull the full IORegistry property dictionary
    CFMutableDictionaryRef props = nullptr;
    kern_return_t kr = IORegistryEntryCreateCFProperties(
        g_battery_service, &props, kCFAllocatorDefault, 0);
    if (kr != KERN_SUCCESS || !props) return BAT_ERR_IOKIT;

    // ── Capacity ─────────────────────────────────────────────────────────
    int32_t cur_cap = 0, max_cap = 0, design_cap = 0;
    bool has_cur    = cf_get_int32(props, "CurrentCapacity",    cur_cap);
    bool has_max    = cf_get_int32(props, "MaxCapacity",        max_cap);
    bool has_design = cf_get_int32(props, "DesignCapacity",     design_cap);

    if (!has_cur || !has_max || max_cap <= 0) {
        CFRelease(props);
        return BAT_ERR_NO_BATTERY;
    }

    status->percent             = 100.0f * static_cast<float>(cur_cap)
                                         / static_cast<float>(max_cap);
    status->max_capacity_mah    = static_cast<uint32_t>(max_cap);
    status->design_capacity_mah = has_design
                                  ? static_cast<uint32_t>(design_cap) : 0u;

    if (has_design && design_cap > 0) {
        status->health_percent = 100.0f * static_cast<float>(max_cap)
                                        / static_cast<float>(design_cap);
    }

    // ── Charging / plugged-in state ───────────────────────────────────────
    bool is_charging = false, ext_connected = false;
    cf_get_bool(props, "IsCharging",         is_charging);
    cf_get_bool(props, "ExternalConnected",  ext_connected);
    status->charging   = is_charging;
    status->plugged_in = ext_connected;

    // ── Time remaining (minutes in IOKit → seconds here) ─────────────────
    int32_t time_rem = 0;
    if (cf_get_int32(props, "TimeRemaining", time_rem) && time_rem > 0) {
        // IOKit reports minutes; -1 means "calculating"
        status->time_left_seconds = static_cast<float>(time_rem) * 60.0f;
    }

    // ── Voltage (mV → V) ─────────────────────────────────────────────────
    int32_t voltage_mv = 0;
    if (cf_get_int32(props, "Voltage", voltage_mv)) {
        status->voltage_volts = static_cast<float>(voltage_mv) / 1000.0f;
    }

    // ── Amperage (mA) × voltage → watts ──────────────────────────────────
    int32_t amperage_ma = 0;
    if (cf_get_int32(props, "Amperage", amperage_ma) && voltage_mv > 0) {
        float watts = static_cast<float>(amperage_ma)
                    * static_cast<float>(voltage_mv) / 1'000'000.0f;
        status->power_watts = watts;   // positive = charging, negative = drain
    }

    // ── Temperature (hundredths of °C → °C) ──────────────────────────────
    int32_t temp_raw = 0;
    if (cf_get_int32(props, "Temperature", temp_raw)) {
        status->temperature_celsius = static_cast<float>(temp_raw) / 100.0f;
    }

    // ── Cycle count ───────────────────────────────────────────────────────
    int32_t cycles = 0;
    if (cf_get_int32(props, "CycleCount", cycles) && cycles >= 0) {
        status->cycle_count = static_cast<uint32_t>(cycles);
    }

    // ── Manufacturer & device name ────────────────────────────────────────
    cf_get_str(props, "Manufacturer", status->manufacturer,
               sizeof(status->manufacturer));
    cf_get_str(props, "DeviceName",   status->device_name,
               sizeof(status->device_name));

    CFRelease(props);
    return BAT_OK;
}

// ---------------------------------------------------------------------------
// Charge control — IOPMSetChargeInhibit
// ---------------------------------------------------------------------------

/**
 * IOPMSetChargeInhibit is a private IOKit API present since macOS 10.7.
 * Declaration is not in any public header so we declare it ourselves.
 * It requires root or the battery charge entitlement.
 */
extern "C" IOReturn IOPMSetChargeInhibit(bool inhibit);

BatteryResult battery_stop_charging() {
    // First try the SMC BCLM key (set to current percent to freeze charging)
    BatteryStatus snap{};
    if (battery_read_status(&snap) == BAT_OK) {
        uint8_t pct = static_cast<uint8_t>(snap.percent);
        BatteryResult r = smc_write_byte(SMC_KEY_BCLM, pct > 0 ? pct : 1u);
        if (r == BAT_OK) return BAT_OK;
    }

    // Fall back to IOPMSetChargeInhibit
    IOReturn ret = IOPMSetChargeInhibit(true);
    if (ret == kIOReturnSuccess)    return BAT_OK;
    if (ret == kIOReturnNotPrivileged) return BAT_ERR_PERMISSION;
    if (ret == kIOReturnUnsupported)   return BAT_ERR_NOT_SUPPORTED;
    return BAT_ERR_IOKIT;
}

BatteryResult battery_start_charging() {
    // Reset SMC threshold to 100 first
    BatteryResult r = smc_write_byte(SMC_KEY_BCLM, 100u);
    if (r == BAT_OK) {
        smc_write_byte(SMC_KEY_BCLB, 0u);   // best-effort min reset
        return BAT_OK;
    }

    IOReturn ret = IOPMSetChargeInhibit(false);
    if (ret == kIOReturnSuccess)       return BAT_OK;
    if (ret == kIOReturnNotPrivileged) return BAT_ERR_PERMISSION;
    if (ret == kIOReturnUnsupported)   return BAT_ERR_NOT_SUPPORTED;
    return BAT_ERR_IOKIT;
}

// ---------------------------------------------------------------------------
// Charge threshold — SMC BCLM / BCLB keys
// ---------------------------------------------------------------------------

BatteryResult battery_set_max_charge(uint8_t max_percent) {
    if (max_percent == 0 || max_percent > 100) return BAT_ERR_SYSTEM;
    return smc_write_byte(SMC_KEY_BCLM, max_percent);
}

BatteryResult battery_set_min_charge(uint8_t min_percent) {
    if (min_percent > 99) return BAT_ERR_SYSTEM;
    return smc_write_byte(SMC_KEY_BCLB, min_percent);
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

const char *battery_result_str(BatteryResult result) {
    switch (result) {
        case BAT_OK:                return "Success";
        case BAT_ERR_NO_BATTERY:    return "No battery detected (IOKit)";
        case BAT_ERR_PERMISSION:    return "Permission denied — run as root or with battery entitlement";
        case BAT_ERR_NOT_SUPPORTED: return "Feature not supported on this Mac model";
        case BAT_ERR_IOKIT:         return "IOKit / CoreFoundation error";
        case BAT_ERR_SYSTEM:        return "System error";
        default:                    return "Unknown error";
    }
}
