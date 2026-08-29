# NeuroShell C++ Engine Build Script
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
"""
Build the C++ performance engine as a Python extension module.
Usage:  pip install .          (auto-compiles C++)
        python setup.py build_ext --inplace   (manual build)
"""

import re
from pathlib import Path

from setuptools import find_packages, setup

# Single source of truth: read version from __version__.py
_version_text = Path(__file__).with_name("__version__.py").read_text(encoding="utf-8")
_m = re.search(r'__version__\s*=\s*"([^"]+)"', _version_text)
VERSION = _m.group(1) if _m else "0.0.0"

try:
    from pybind11.setup_helpers import Pybind11Extension, build_ext
    HAS_PYBIND11 = True
except ImportError:
    HAS_PYBIND11 = False

ext_modules = []
cmdclass = {}

if HAS_PYBIND11:
    ext_modules = [
        Pybind11Extension(
            "cpp_engine.cpp_engine_core",
            sources=["cpp_engine/engine.cpp"],
            cxx_std=17,
            define_macros=[("VERSION_INFO", VERSION)],
        ),
    ]
    cmdclass = {"build_ext": build_ext}

setup(
    name="neuroshell",
    version=VERSION,
    author="Abneesh Singh",
    author_email="singhabneesh250@gmail.com",
    description="NeuroShell — AI-Powered Intelligent Terminal",
    packages=find_packages(exclude=["tests*"]),
    ext_modules=ext_modules,
    cmdclass=cmdclass,
    python_requires=">=3.10",
)
