# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Packages the complete NeuroShell Native Terminal Application into a single
portable distribution folder and zip file for release.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path


def package_distribution():
    project_root = Path(__file__).parent.parent.resolve()
    dist_dir = project_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    # 1. Build the native host
    native_script = project_root / "scripts" / "build_native_host.py"
    subprocess.run([os.sys.executable, str(native_script)], check=True)

    native_exe = dist_dir / "neuroshell_native.exe"
    fast_dir = dist_dir / "NeuroShell_Fast"

    # Target release folder
    release_dir = dist_dir / "NeuroShell_v5.0.6_Windows_Portable"
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True, exist_ok=True)

    # Copy native binary as NeuroShell.exe
    target_exe = release_dir / "NeuroShell.exe"
    shutil.copy2(native_exe, target_exe)
    print(f"📦 Copied Native Host to {target_exe}")

    # Copy assets
    assets_src = project_root / "assets"
    if assets_src.exists():
        shutil.copytree(assets_src, release_dir / "assets")

    # If pre-extracted engine exists, package it
    if fast_dir.exists():
        engine_target = release_dir / "engine"
        if engine_target.exists():
            shutil.rmtree(engine_target)
        shutil.copytree(fast_dir, engine_target)
        print(f"📦 Packaged Fast Engine to {engine_target}")

    # Create README
    readme_content = """==================================================================
  🧠 NeuroShell v5.0.6 — AI-Powered Intelligent Terminal
  Authors: Abneesh Singh & Praveen Kumar Yadav
==================================================================

QUICK START:
1. Double-click 'NeuroShell.exe' to launch the terminal immediately (<2ms).
2. Set your AI provider & API key:
   Type '/api-key' and use arrow keys to pick your provider (Groq, OpenAI, Gemini, etc.).
3. Type plain English commands or standard shell commands:
   > find all python files modified today
   > kill process on port 8000
   > commit with message "first release"

All features are accessible via the '/' method (e.g. /model, /theme, /swarm, /help).
"""
    (release_dir / "README.txt").write_text(readme_content, encoding="utf-8")

    # Create Zip
    zip_path = dist_dir / "NeuroShell_v5.0.6_Windows_Portable.zip"
    print(f"🗜️  Creating release zip: {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(release_dir):
            for f in files:
                full_p = Path(root) / f
                rel_p = full_p.relative_to(release_dir)
                zf.write(full_p, arcname=rel_p)

    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"🎉 Production Package Complete: {zip_path} ({zip_size_mb:.1f} MB)")


if __name__ == "__main__":
    package_distribution()
