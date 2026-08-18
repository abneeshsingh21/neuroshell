# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Cleans up all old, obsolete, and temporary builds, leaving ONLY
the verified production-grade NeuroShell terminal.
"""

import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DIST_DIR = PROJECT_ROOT / "dist"

OBSOLETE_PATHS = [
    # In dist/
    DIST_DIR / "NeuroShell-CLI.exe",
    DIST_DIR / "NeuroShell-Terminal",
    DIST_DIR / "NeuroShell_Fast",
    DIST_DIR / "NeuroShell_v5.0.6_Windows_Portable",
    DIST_DIR / "NeuroShell_v5.0.6_Windows_Portable.zip",
    DIST_DIR / "neuroshell_native.exe",
    DIST_DIR / "test_mei",
    DIST_DIR / "resource.res",
    DIST_DIR / "NeuroShell_C++.exe",

    # In root
    PROJECT_ROOT / "build",
    PROJECT_ROOT / "build_fast",
    PROJECT_ROOT / "build_portable",
    PROJECT_ROOT / "build_term",
    PROJECT_ROOT / "dist_portable",
    PROJECT_ROOT / "main.obj",
    PROJECT_ROOT / "NeuroShell-Terminal.spec",
    PROJECT_ROOT / "NeuroShell_Fast.spec",
    PROJECT_ROOT / "test_mei.spec",
]


def clean():
    print("🧹 Cleaning obsolete builds and temporary directories...")
    removed = 0
    for p in OBSOLETE_PATHS:
        if p.exists():
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                print(f"  🗑️ Removed: {p.name}")
                removed += 1
            except Exception as e:
                print(f"  ⚠️ Could not remove {p.name}: {e}")

    print(f"\n✅ Cleaned {removed} obsolete items.")
    print("✨ ONLY the clean production-grade NeuroShell.exe remains in dist/!")


if __name__ == "__main__":
    clean()
