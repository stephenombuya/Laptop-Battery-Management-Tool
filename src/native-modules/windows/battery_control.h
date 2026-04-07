/**
 * @file   battery_control.h
 * @brief  Windows battery control interface (WinAPI / ACPI)
 *
 * Provides functions to query battery status and toggle charging limits on
 * Windows using the Win32 Power API and IOCTL_BATTERY_* device I/O controls.
 *
 * Link against: SetupAPI.lib, PowrProf.lib
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

#include <windows.h>
#include <stdbool.h>
#include <stdint.h>

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * @brief Snapshot of battery state returned by battery_read_status().
 */
typedef struct {
    float    percent;               /**< Charge level, 0–100              */
    bool     charging;              /**< True while actively charging      */
    bool     plugged_in;            /**< True when AC adapter is present   */
    uint32_t time_left_seconds;     /**< 0 = unknown / not applicable      */
    float    voltage_volts;         /**< Terminal voltage, or 0.0          */
    float    power_watts;           /**< Draw (negative) or charge (pos.)  */
    uint32_t cycle_count;           /**< Lifetime charge cycles, or 0      */
    float    health_percent;        /**< Design-capacity ratio × 100, 0.0  */
    float    temperature_celsius;   /**< Cell temperature, or 0.0          */
} BatteryStatus;

/**
 * @brief Return codes used by all functions in this module.
 */
typedef enum {
    BAT_OK              =  0,  /**< Success                               */
    BAT_ERR_NO_BATTERY  = -1,  /**< No battery present                    */
    BAT_ERR_PERMISSION  = -2,  /**< Insufficient privileges               */
    BAT_ERR_NOT_SUPPORTED = -3,/**< Hardware does not support the feature  */
    BAT_ERR_SYSTEM      = -4,  /**< Generic OS / API error                */
} BatteryResult;

// ---------------------------------------------------------------------------
// Initialisation / teardown
// ---------------------------------------------------------------------------

/**
 * @brief Initialise the battery control subsystem.
 *
 * Must be called once before any other function in this module.
 * Opens a handle to the first battery device.
 *
 * @return BAT_OK on success, BAT_ERR_* on failure.
 */
BatteryResult battery_init(void);

/**
 * @brief Release all resources acquired by battery_init().
 */
void battery_cleanup(void);

// ---------------------------------------------------------------------------
// Status query
// ---------------------------------------------------------------------------

/**
 * @brief Read the current battery status into @p status.
 *
 * @param[out] status  Caller-allocated struct to populate.
 * @return BAT_OK on success, BAT_ERR_* on failure.
 */
BatteryResult battery_read_status(BatteryStatus *status);

// ---------------------------------------------------------------------------
// Charge control
// ---------------------------------------------------------------------------

/**
 * @brief Set the maximum charge level threshold.
 *
 * On supported hardware this writes the threshold via OEM-specific ACPI
 * methods exposed through WMI or a battery IOCTL.  On unsupported hardware
 * BAT_ERR_NOT_SUPPORTED is returned and charging is unaffected.
 *
 * @param max_percent  Target maximum charge level (1–100).
 * @return BAT_OK or BAT_ERR_*.
 */
BatteryResult battery_set_max_charge(uint8_t max_percent);

/**
 * @brief Set the minimum charge level threshold (start-charging point).
 *
 * @param min_percent  Target minimum charge level (0–99, must be < max).
 * @return BAT_OK or BAT_ERR_*.
 */
BatteryResult battery_set_min_charge(uint8_t min_percent);

/**
 * @brief Immediately stop charging (software-only command).
 * @return BAT_OK or BAT_ERR_*.
 */
BatteryResult battery_stop_charging(void);

/**
 * @brief Resume charging.
 * @return BAT_OK or BAT_ERR_*.
 */
BatteryResult battery_start_charging(void);

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

/**
 * @brief Translate a BatteryResult code to a human-readable string.
 * @param result  Code returned by any function in this module.
 * @return Pointer to a static, null-terminated string.
 */
const char *battery_result_str(BatteryResult result);

#ifdef __cplusplus
}
#endif
