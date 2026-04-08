/**
 * @file   battery_control.h
 * @brief  macOS battery control interface (IOKit / CoreFoundation)
 *
 * Provides functions to query battery status via IOKit's
 * AppleSmartBattery service and to issue charge-limit commands through
 * IOPMSetChargeInhibit and OEM SMC keys where the hardware supports it.
 *
 * Link against: IOKit.framework, CoreFoundation.framework
 *
 * Compilation:
 *   clang++ -std=c++17 -Wall -framework IOKit -framework CoreFoundation \
 *           battery_control.cpp -o batteryos-macos
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>
#include <stdint.h>

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** @brief Point-in-time snapshot of battery state. */
typedef struct {
    float    percent;               /**< Charge level 0–100                */
    bool     charging;              /**< True while actively charging      */
    bool     plugged_in;            /**< True when AC adapter connected    */
    float    time_left_seconds;     /**< Seconds remaining; 0.0 = unknown  */
    float    voltage_volts;         /**< Terminal voltage (mV → V)         */
    float    power_watts;           /**< Positive = charging, neg = drain  */
    uint32_t cycle_count;           /**< Lifetime charge cycles            */
    float    health_percent;        /**< MaxCapacity / DesignCapacity × 100*/
    float    temperature_celsius;   /**< Cell temperature (°C)             */
    uint32_t max_capacity_mah;      /**< Full-charge capacity in mAh       */
    uint32_t design_capacity_mah;   /**< OEM design capacity in mAh        */
    char     manufacturer[64];      /**< Battery manufacturer string       */
    char     device_name[64];       /**< Battery device/model name         */
} BatteryStatus;

/** @brief Return codes used by every function in this module. */
typedef enum {
    BAT_OK                = 0,
    BAT_ERR_NO_BATTERY    = -1,   /**< No battery service found in IOKit  */
    BAT_ERR_PERMISSION    = -2,   /**< Caller lacks required entitlement  */
    BAT_ERR_NOT_SUPPORTED = -3,   /**< Hardware does not support the op   */
    BAT_ERR_IOKIT         = -4,   /**< IOKit / CoreFoundation API error   */
    BAT_ERR_SYSTEM        = -5,   /**< Generic OS error                   */
} BatteryResult;

// ---------------------------------------------------------------------------
// Initialisation / teardown
// ---------------------------------------------------------------------------

/**
 * @brief Open a connection to the IOKit battery service.
 *
 * Must be called once before any other function.  Establishes the IOService
 * iterator and the IOPMPowerSource connection used by subsequent calls.
 *
 * @return BAT_OK, BAT_ERR_NO_BATTERY, or BAT_ERR_IOKIT.
 */
BatteryResult battery_init(void);

/**
 * @brief Release all IOKit handles opened by battery_init().
 */
void battery_cleanup(void);

// ---------------------------------------------------------------------------
// Status query
// ---------------------------------------------------------------------------

/**
 * @brief Read the current battery status into @p status.
 *
 * Queries the AppleSmartBattery IORegistry entry for all available fields.
 * Fields not supported by the hardware are left at their zero/empty values.
 *
 * @param[out] status  Caller-allocated struct to populate.
 * @return BAT_OK on success, BAT_ERR_* on failure.
 */
BatteryResult battery_read_status(BatteryStatus *status);

// ---------------------------------------------------------------------------
// Charge control
// ---------------------------------------------------------------------------

/**
 * @brief Inhibit charging (software AC adapter simulation).
 *
 * Calls IOPMSetChargeInhibit(true) which signals the SMC to stop accepting
 * charge.  This is the same mechanism used by coconutBattery and AlDente.
 * Requires that the calling process holds the
 * com.apple.private.iokit.batterycharge entitlement — granted by the
 * signed helper binary or via a privileged helper (SMJobBless).
 *
 * @return BAT_OK, BAT_ERR_PERMISSION, or BAT_ERR_NOT_SUPPORTED.
 */
BatteryResult battery_stop_charging(void);

/**
 * @brief Re-enable charging.
 * @return BAT_OK, BAT_ERR_PERMISSION, or BAT_ERR_NOT_SUPPORTED.
 */
BatteryResult battery_start_charging(void);

/**
 * @brief Set the maximum charge level via the SMC.
 *
 * Writes the BCLM (Battery Charge Level Maximum) SMC key on Apple Silicon
 * and Intel Macs running macOS 12+.  Falls back to IOPMSetChargeInhibit on
 * older hardware.
 *
 * @param max_percent  1–100
 * @return BAT_OK, BAT_ERR_NOT_SUPPORTED, or BAT_ERR_PERMISSION.
 */
BatteryResult battery_set_max_charge(uint8_t max_percent);

/**
 * @brief Set the charge-start threshold (minimum level before charging begins).
 *
 * Writes the BCLB (Battery Charge Level Bottom) SMC key where supported.
 *
 * @param min_percent  0–99 (must be < max)
 * @return BAT_OK, BAT_ERR_NOT_SUPPORTED, or BAT_ERR_PERMISSION.
 */
BatteryResult battery_set_min_charge(uint8_t min_percent);

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

/**
 * @brief Return a human-readable string for a BatteryResult code.
 * @param result  Any BatteryResult value.
 * @return Pointer to a static, null-terminated string.  Never NULL.
 */
const char *battery_result_str(BatteryResult result);

#ifdef __cplusplus
}
#endif
