# CMakeLists.txt — BatteryOS Native Modules
# ==========================================
# Builds a thin platform-specific helper binary (batteryos-<platform>) that
# the Python core-service and Rust system-service invoke as a subprocess for
# charge-control operations that require native OS APIs or elevated privileges.
#
# Usage
# -----
#   mkdir build && cd build
#   cmake ..                        # auto-detect platform
#   cmake --build . --config Release
#
# Output
# ------
#   build/batteryos-linux    (Linux)
#   build/batteryos-macos    (macOS)
#   build/batteryos-windows  (Windows)

cmake_minimum_required(VERSION 3.20)

project(
    batteryos-native
    VERSION 2.0.0
    DESCRIPTION "BatteryOS platform-specific battery control helpers"
    LANGUAGES CXX
)

# ---------------------------------------------------------------------------
# Global settings
# ---------------------------------------------------------------------------

set(CMAKE_CXX_STANDARD          17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS        OFF)

# Place all output binaries in build/ regardless of subdirectory
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")

# Compiler warning flags
if(MSVC)
    add_compile_options(/W4 /WX /permissive-)
else()
    add_compile_options(-Wall -Wextra -Wpedantic -Werror)
endif()

# Release build by default when not specified
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
    set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS Debug Release RelWithDebInfo MinSizeRel)
endif()

# ---------------------------------------------------------------------------
# Shared CLI wrapper source
# ---------------------------------------------------------------------------
# Each platform helper links against its native library and this thin CLI
# wrapper that dispatches argv[1] ("start" / "stop") to the C API.

set(CLI_WRAPPER_SRC "${CMAKE_CURRENT_SOURCE_DIR}/cli_main.cpp")

# ---------------------------------------------------------------------------
# Linux target
# ---------------------------------------------------------------------------

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    add_executable(batteryos-linux
        "${CLI_WRAPPER_SRC}"
        "${CMAKE_CURRENT_SOURCE_DIR}/linux/battery_control.cpp"
    )
    target_include_directories(batteryos-linux PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/linux"
    )
    target_compile_definitions(batteryos-linux PRIVATE BATTERYOS_PLATFORM_LINUX)
    install(TARGETS batteryos-linux RUNTIME DESTINATION bin)
endif()

# ---------------------------------------------------------------------------
# macOS target
# ---------------------------------------------------------------------------

if(CMAKE_SYSTEM_NAME STREQUAL "Darwin")
    add_executable(batteryos-macos
        "${CLI_WRAPPER_SRC}"
        "${CMAKE_CURRENT_SOURCE_DIR}/macos/battery_control.cpp"
    )
    target_include_directories(batteryos-macos PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/macos"
    )
    target_compile_definitions(batteryos-macos PRIVATE BATTERYOS_PLATFORM_MACOS)

    # Link IOKit and CoreFoundation for battery access
    find_library(IOKIT_LIB IOKit REQUIRED)
    find_library(COREFOUNDATION_LIB CoreFoundation REQUIRED)
    target_link_libraries(batteryos-macos PRIVATE
        "${IOKIT_LIB}"
        "${COREFOUNDATION_LIB}"
    )
    install(TARGETS batteryos-macos RUNTIME DESTINATION bin)
endif()

# ---------------------------------------------------------------------------
# Windows target
# ---------------------------------------------------------------------------

if(CMAKE_SYSTEM_NAME STREQUAL "Windows")
    add_executable(batteryos-windows
        "${CLI_WRAPPER_SRC}"
        "${CMAKE_CURRENT_SOURCE_DIR}/windows/battery_control.cpp"
    )
    target_include_directories(batteryos-windows PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/windows"
    )
    target_compile_definitions(batteryos-windows PRIVATE BATTERYOS_PLATFORM_WINDOWS)
    target_link_libraries(batteryos-windows PRIVATE
        SetupAPI
        PowrProf
    )
    # Request UAC elevation via manifest
    set_target_properties(batteryos-windows PROPERTIES
        LINK_FLAGS "/MANIFESTUAC:\"level='requireAdministrator' uiAccess='false'\""
    )
    install(TARGETS batteryos-windows RUNTIME DESTINATION bin)
endif()

# ---------------------------------------------------------------------------
# Tests (optional — requires GoogleTest)
# ---------------------------------------------------------------------------

option(BATTERYOS_BUILD_TESTS "Build unit tests (requires GoogleTest)" OFF)

if(BATTERYOS_BUILD_TESTS)
    enable_testing()
    find_package(GTest REQUIRED)

    add_executable(batteryos-tests
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/battery_control_test.cpp"
    )
    target_link_libraries(batteryos-tests PRIVATE GTest::gtest_main)
    include(GoogleTest)
    gtest_discover_tests(batteryos-tests)
endif()

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

message(STATUS "")
message(STATUS "BatteryOS Native Modules — Configuration Summary")
message(STATUS "  Platform   : ${CMAKE_SYSTEM_NAME}")
message(STATUS "  Build type : ${CMAKE_BUILD_TYPE}")
message(STATUS "  C++ std    : ${CMAKE_CXX_STANDARD}")
message(STATUS "  Output dir : ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}")
message(STATUS "  Tests      : ${BATTERYOS_BUILD_TESTS}")
message(STATUS "")
