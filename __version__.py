# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
"""NeuroShell version information.

Single source of truth for the runtime version. Keep in sync with
`pyproject.toml` — the release pipeline asserts they match.
"""
__version__ = "5.7.1"
__version_info__ = tuple(int(x) for x in __version__.split("."))
