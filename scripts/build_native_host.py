# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Compiles the ultra-fast (<2ms startup) native Windows Host for NeuroShell
with the embedded production NeuroShell logo (assets/icon.ico).
"""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

CSC_PATH = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


def build_native_host():
    project_root = Path(__file__).parent.parent.resolve()
    dist_dir = project_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    src_file = project_root / "native_host" / "Program.cs"
    icon_file = project_root / "assets" / "icon.ico"
    out_exe = dist_dir / "neuroshell_native.exe"

    if not CSC_PATH.exists():
        print(f"❌ csc.exe not found at {CSC_PATH}")
        sys.exit(1)

    cmd = [
        str(CSC_PATH),
        "/target:exe",
        "/platform:x64",
        "/optimize+",
        f"/win32icon:{icon_file}",
        f"/out:{out_exe}",
        str(src_file)
    ]

    print(f"🚀 Compiling native host with embedded icon: {icon_file.name}")
    print(f"Command: {' '.join(cmd)}")

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"❌ Compilation failed:\n{res.stderr}\n{res.stdout}")
        sys.exit(1)

    size_kb = out_exe.stat().st_size / 1024
    print(f"✅ Successfully compiled native host: {out_exe} ({size_kb:.1f} KB)")
    return out_exe


if __name__ == "__main__":
    build_native_host()
