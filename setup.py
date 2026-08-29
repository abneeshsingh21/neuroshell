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

try:
    from pybind11.setup_helpers import Pybind11Extension, build_ext
    HAS_PYBIND11 = True
except ImportError:
    HAS_PYBIND11 = False

# Single source of truth: read the version from __version__.py
_version_file = Path(__file__).parent / "__version__.py"
_match = re.search(r'__version__\s*=\s*"([^"]+)"', _version_file.read_text(encoding="utf-8"))
VERSION = _match.group(1) if _match else "0.0.0"

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
