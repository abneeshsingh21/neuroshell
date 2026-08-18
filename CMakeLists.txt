cmake_minimum_required(VERSION 3.20)
project(NeuroShell LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(MSVC)
    add_compile_options(/W4 /O2 /permissive- /Zc:__cplusplus /utf-8)
else()
    add_compile_options(-Wall -Wextra -O3 -pthread)
endif()

if(APPLE)
    # Support Universal2 binary build (arm64 + x86_64) if requested
    if(NOT CMAKE_OSX_ARCHITECTURES)
        set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "Build architectures for macOS" FORCE)
    endif()
endif()

add_executable(neuroshell cpp_engine/launcher/main.cpp)

if(WIN32)
    target_link_libraries(neuroshell PRIVATE Shell32.lib User32.lib Advapi32.lib)
    set_target_properties(neuroshell PROPERTIES OUTPUT_NAME "NeuroShell")
endif()

install(TARGETS neuroshell DESTINATION bin)
