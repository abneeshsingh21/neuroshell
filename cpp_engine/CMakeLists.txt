cmake_minimum_required(VERSION 3.15)
project(neuroshell_cpp_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# ── Find pybind11 ──
find_package(pybind11 REQUIRED)

# ── Build the shared library ──
pybind11_add_module(cpp_engine_core
    engine.cpp
)

target_compile_options(cpp_engine_core PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:/O2 /W4>
    $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-O3 -Wall -Wextra -Wpedantic>
)

# Install into the cpp_engine package directory
install(TARGETS cpp_engine_core
    LIBRARY DESTINATION cpp_engine
    RUNTIME DESTINATION cpp_engine
)
