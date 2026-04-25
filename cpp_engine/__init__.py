# NeuroShell C++ Performance Engine
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
#
# Graceful fallback: tries the compiled C++ module first,
# falls back to the pure Python reference if unavailable.

_USING_CPP = False

try:
    from cpp_engine.cpp_engine_core import (  # type: ignore[import-not-found]
        FastParser,
        FuzzyMatcher,
        MarkovEngine,
        ParsedCommand,
    )
    _USING_CPP = True
except ImportError:
    from cpp_engine.engine import FastParser, FuzzyMatcher, MarkovEngine

__all__ = ["FastParser", "FuzzyMatcher", "MarkovEngine", "_USING_CPP"]
