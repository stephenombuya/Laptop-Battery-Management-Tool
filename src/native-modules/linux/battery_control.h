/**
 * @file   battery_control.h
 * @brief  Linux battery control interface (ACPI / sysfs)
 *
 * Reads battery state from the kernel's power_supply sysfs class and
 * controls charging via the charge_stop_threshold / charge_start_threshold
 * nodes supported by ThinkPad, ASUS, and similar OEMs.
 *
 * Requires read access to /sys/class/power_supply/ for queries;
 * write access (root or polkit rule) for charge-control operations.
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

/** @brief Snapshot of battery state. */
typedef struct {
    float    percent;               /**< 0–100                             */
    bool     charging;              /**< True while actively charging      */
    bool     plugged_in;            /**< True when AC adapter detected     */
    float    time_left_seconds;     /**< 0.0 = unknown                     */
    float    voltage_volts;         /**< Terminal voltage, 0.0 if unknown  */
    float    power_watts;           /**< Positive = charging, negative = discharge */
    uint32_t cycle_count;           /**< Lifetime cycles, 0 if unavailable */
    float    health_percent;        /**< full_charge / design × 100        */
    float    temperature_celsius;   /**< 0.0 if unavailable                */
} BatteryStatus;

/** @brief Return codes. */
typedef enum {
    BAT_OK              =  0,
    BAT_ERR_NO_BATTERY  = -1,
    BAT_ERR_PERMISSION  = -2,
    BAT_ERR_NOT_SUPPORTED = -3,
    BAT_ERR_SYSTEM      = -4,
} BatteryResult;

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

/**
 * @brief Detect and latch the sysfs path of the first battery.
 *
 * Searches /sys/class/power_supply/ for BAT0, BAT1, or any BAT* entry.
 * Must be called before any other function.
 *
 * @return BAT_OK or BAT_ERR_NO_BATTERY.
 */
BatteryResult battery_init(void);

/** @brief Release any resources held by the module. */
void battery_cleanup(void);

// ---------------------------------------------------------------------------
// Status query
// ---------------------------------------------------------------------------

/**
 * @brief Read current battery status into @p status.
 * @param[out] status  Caller-allocated struct to fill.
 * @return BAT_OK on success, BAT_ERR_* otherwise.
 */
BatteryResult battery_read_status(BatteryStatus *status);

// ---------------------------------------------------------------------------
// Charge control
// ---------------------------------------------------------------------------

/**
 * @brief Write the charge-stop threshold (max charge).
 *
 * Writes @p max_percent to the sysfs charge_stop_threshold node.
 * Requires write access to the node (typically root or a udev rule granting
 * group write permissions).
 *
 * @param max_percent  1–100
 * @return BAT_OK, BAT_ERR_NOT_SUPPORTED, or BAT_ERR_PERMISSION.
 */
BatteryResult battery_set_max_charge(uint8_t max_percent);

/**
 * @brief Write the charge-start threshold (min charge).
 * @param min_percent  0–99 (must be less than max)
 * @return BAT_OK or BAT_ERR_*.
 */
BatteryResult battery_set_min_charge(uint8_t min_percent);

/** @brief Immediately stop charging (sets stop threshold to current level). */
BatteryResult battery_stop_charging(void);

/** @brief Resume charging (resets thresholds to defaults). */
BatteryResult battery_start_charging(void);

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

/** @brief Translate a result code to a human-readable string. */
const char *battery_result_str(BatteryResult result);

#ifdef __cplusplus
}
#endif
