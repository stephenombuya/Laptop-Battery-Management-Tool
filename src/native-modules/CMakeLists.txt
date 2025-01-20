cmake_minimum_required(VERSION 3.10)
project(BatteryControl)

if(WIN32)
    add_library(battery_control SHARED
        windows/battery_control.cpp
    )
else()
    add_library(battery_control SHARED
        linux/battery_control.cpp
    )
endif()
