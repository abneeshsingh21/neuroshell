cmake_minimum_required(VERSION 3.20)
project(NeuroShell LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

option(NEUROSHELL_HARDENING "Enable compiler/linker security hardening" ON)
option(NEUROSHELL_SANITIZERS "Build with ASan/UBSan (Debug diagnostics)" OFF)
option(NEUROSHELL_LTO "Enable link-time optimization for Release builds" ON)

if(MSVC)
    add_compile_options(/W4 /permissive- /Zc:__cplusplus /utf-8)
    add_compile_options("$<$<CONFIG:Release>:/O2>")
    if(NEUROSHELL_HARDENING)
        # Control Flow Guard + Spectre mitigations + secure exception handling
        add_compile_options(/guard:cf /sdl)
        add_link_options(/guard:cf /DYNAMICBASE /NXCOMPAT /HIGHENTROPYVA)
    endif()
else()
    add_compile_options(-Wall -Wextra -Wpedantic -pthread)
    add_compile_options("$<$<CONFIG:Release>:-O2>")
    if(NEUROSHELL_HARDENING)
        # Stack protector, FORTIFY, full RELRO, PIE, no lazy binding
        add_compile_options(
            -fstack-protector-strong
            -D_FORTIFY_SOURCE=2
            -fPIE
        )
        if(NOT APPLE)
            add_link_options(-pie -Wl,-z,relro -Wl,-z,now -Wl,-z,noexecstack)
        endif()
    endif()
    if(NEUROSHELL_SANITIZERS)
        add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer -g)
        add_link_options(-fsanitize=address,undefined)
    endif()
endif()

if(APPLE)
    # Support Universal2 binary build (arm64 + x86_64) if requested
    if(NOT CMAKE_OSX_ARCHITECTURES)
        set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "Build architectures for macOS" FORCE)
    endif()
endif()

add_executable(neuroshell cpp_engine/launcher/main.cpp)
target_link_libraries(neuroshell PRIVATE $<$<NOT:$<PLATFORM_ID:Windows>>:pthread>)

if(NEUROSHELL_LTO AND NOT NEUROSHELL_SANITIZERS)
    include(CheckIPOSupported)
    check_ipo_supported(RESULT ipo_ok OUTPUT ipo_msg)
    if(ipo_ok)
        set_property(TARGET neuroshell PROPERTY INTERPROCEDURAL_OPTIMIZATION_RELEASE TRUE)
    endif()
endif()

if(WIN32)
    target_link_libraries(neuroshell PRIVATE Shell32.lib User32.lib Advapi32.lib Crypt32.lib)
    set_target_properties(neuroshell PROPERTIES OUTPUT_NAME "NeuroShell")
endif()

# POSIX shared-memory ring requires librt on older glibc
if(UNIX AND NOT APPLE)
    target_link_libraries(neuroshell PRIVATE rt)
endif()

install(TARGETS neuroshell DESTINATION bin)

# ─── Native unit tests (ctest) ──────────────────────────────
option(NEUROSHELL_BUILD_TESTS "Build native C++ unit tests" ON)
if(NEUROSHELL_BUILD_TESTS)
    enable_testing()
    add_executable(neuroshell_native_tests cpp_engine/tests/native_tests.cpp)
    target_include_directories(neuroshell_native_tests PRIVATE cpp_engine/launcher)
    target_link_libraries(neuroshell_native_tests PRIVATE $<$<NOT:$<PLATFORM_ID:Windows>>:pthread>)
    if(UNIX AND NOT APPLE)
        target_link_libraries(neuroshell_native_tests PRIVATE rt)
    endif()
    add_test(NAME native_unit_tests COMMAND neuroshell_native_tests)
endif()
