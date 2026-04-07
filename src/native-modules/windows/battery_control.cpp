/**
 * @file   battery_control.cpp
 * @brief  Windows battery control implementation
 *
 * Uses GetSystemPowerStatus() for basic status and
 * IOCTL_BATTERY_QUERY_INFORMATION for extended data (voltage, health, cycles).
 * OEM charge-limit control is attempted via WMI (Lenovo / Dell / HP paths).
 *
 * Build:  cl /EHsc /W4 battery_control.cpp /link SetupAPI.lib PowrProf.lib
 */

#include "battery_control.h"

#include <windows.h>
#include <devguid.h>
#include <setupapi.h>
#include <batclass.h>   // IOCTL_BATTERY_QUERY_*
#include <poclass.h>
#include <wbemidl.h>

#include <cassert>
#include <cstring>

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------

namespace {

HANDLE g_battery_handle = INVALID_HANDLE_VALUE;

// Open the first enumerated battery device.
HANDLE open_battery_device() {
    HDEVINFO dev_info = SetupDiGetClassDevs(
        &GUID_DEVCLASS_BATTERY,
        nullptr,
        nullptr,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    );
    if (dev_info == INVALID_HANDLE_VALUE) return INVALID_HANDLE_VALUE;

    SP_DEVICE_INTERFACE_DATA iface_data{};
    iface_data.cbSize = sizeof(iface_data);

    HANDLE h = INVALID_HANDLE_VALUE;
    DWORD index = 0;

    while (SetupDiEnumDeviceInterfaces(
        dev_info, nullptr, &GUID_DEVINTERFACE_BATTERY, index++, &iface_data
    )) {
        DWORD required = 0;
        SetupDiGetDeviceInterfaceDetail(dev_info, &iface_data, nullptr, 0, &required, nullptr);
        if (required == 0) continue;

        auto *detail = reinterpret_cast<SP_DEVICE_INTERFACE_DETAIL_DATA *>(
            LocalAlloc(LPTR, required)
        );
        if (!detail) continue;
        detail->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA);

        if (SetupDiGetDeviceInterfaceDetail(
            dev_info, &iface_data, detail, required, nullptr, nullptr
        )) {
            h = CreateFile(
                detail->DevicePath,
                GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                nullptr, OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL, nullptr
            );
        }
        LocalFree(detail);
        if (h != INVALID_HANDLE_VALUE) break;
    }

    SetupDiDestroyDeviceInfoList(dev_info);
    return h;
}

} // namespace

// ---------------------------------------------------------------------------
// Init / cleanup
// ---------------------------------------------------------------------------

BatteryResult battery_init() {
    if (g_battery_handle != INVALID_HANDLE_VALUE) return BAT_OK; // already open

    g_battery_handle = open_battery_device();
    if (g_battery_handle == INVALID_HANDLE_VALUE) {
        DWORD err = GetLastError();
        return (err == ERROR_ACCESS_DENIED) ? BAT_ERR_PERMISSION : BAT_ERR_NO_BATTERY;
    }
    return BAT_OK;
}

void battery_cleanup() {
    if (g_battery_handle != INVALID_HANDLE_VALUE) {
        CloseHandle(g_battery_handle);
        g_battery_handle = INVALID_HANDLE_VALUE;
    }
}

// ---------------------------------------------------------------------------
// Status query
// ---------------------------------------------------------------------------

BatteryResult battery_read_status(BatteryStatus *status) {
    if (!status) return BAT_ERR_SYSTEM;
    std::memset(status, 0, sizeof(*status));

    // Basic status — always available, no elevated privileges required
    SYSTEM_POWER_STATUS sps{};
    if (!GetSystemPowerStatus(&sps)) return BAT_ERR_SYSTEM;

    if (sps.BatteryFlag == 128) return BAT_ERR_NO_BATTERY;   // 0x80 = no battery

    status->percent    = static_cast<float>(sps.BatteryLifePercent);
    status->plugged_in = (sps.ACLineStatus == 1);
    status->charging   = status->plugged_in && status->percent < 100.0f;
    status->time_left_seconds =
        (sps.BatteryLifeTime == BATTERY_UNKNOWN_TIME) ? 0 : sps.BatteryLifeTime;

    // Extended info via IOCTL — best-effort, failures are non-fatal
    if (g_battery_handle == INVALID_HANDLE_VALUE) return BAT_OK;

    BATTERY_QUERY_INFORMATION bqi{};
    BATTERY_WAIT_STATUS bws{};
    BATTERY_STATUS bs{};
    DWORD bytes_returned = 0;

    // Tag (required before any other query)
    DWORD tag = 0;
    BATTERY_QUERY_INFORMATION tag_query{};
    tag_query.InformationLevel = BatteryEstimatedTime;  // dummy, just need tag
    if (DeviceIoControl(
        g_battery_handle,
        IOCTL_BATTERY_QUERY_TAG,
        nullptr, 0,
        &tag, sizeof(tag),
        &bytes_returned, nullptr
    ) && tag) {
        bqi.BatteryTag = tag;
        bws.BatteryTag = tag;

        // Status (voltage, current)
        if (DeviceIoControl(
            g_battery_handle,
            IOCTL_BATTERY_QUERY_STATUS,
            &bws, sizeof(bws),
            &bs, sizeof(bs),
            &bytes_returned, nullptr
        )) {
            status->voltage_volts = static_cast<float>(bs.Voltage) / 1000.0f;
            // Rate is in mW; negative = discharging
            status->power_watts = static_cast<float>(bs.Rate) / 1000.0f;
        }

        // Design information (capacity, cycle count)
        BATTERY_INFORMATION bi{};
        bqi.InformationLevel = BatteryInformation;
        if (DeviceIoControl(
            g_battery_handle,
            IOCTL_BATTERY_QUERY_INFORMATION,
            &bqi, sizeof(bqi),
            &bi, sizeof(bi),
            &bytes_returned, nullptr
        )) {
            if (bi.DesignedCapacity > 0) {
                status->health_percent =
                    100.0f * static_cast<float>(bi.FullChargedCapacity) /
                    static_cast<float>(bi.DesignedCapacity);
            }
            status->cycle_count = bi.CycleCount;
        }
    }

    return BAT_OK;
}

// ---------------------------------------------------------------------------
// Charge control
// ---------------------------------------------------------------------------

BatteryResult battery_set_max_charge(uint8_t max_percent) {
    // Most OEMs expose a WMI method; provide a generic stub here.
    // Replace with vendor-specific implementation as needed.
    (void)max_percent;
    return BAT_ERR_NOT_SUPPORTED;
}

BatteryResult battery_set_min_charge(uint8_t min_percent) {
    (void)min_percent;
    return BAT_ERR_NOT_SUPPORTED;
}

BatteryResult battery_stop_charging() {
    // On Windows, physical charging can only be stopped via smart-plug or OEM
    // WMI interfaces.  Return NOT_SUPPORTED to signal the caller.
    return BAT_ERR_NOT_SUPPORTED;
}

BatteryResult battery_start_charging() {
    return BAT_ERR_NOT_SUPPORTED;
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

const char *battery_result_str(BatteryResult result) {
    switch (result) {
        case BAT_OK:               return "Success";
        case BAT_ERR_NO_BATTERY:   return "No battery present";
        case BAT_ERR_PERMISSION:   return "Insufficient privileges";
        case BAT_ERR_NOT_SUPPORTED:return "Feature not supported on this hardware";
        case BAT_ERR_SYSTEM:       return "System / OS error";
        default:                   return "Unknown error";
    }
}
