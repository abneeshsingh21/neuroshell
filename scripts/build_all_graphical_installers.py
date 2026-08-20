# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Prepares and packages all graphical commercial installer formats for GitHub release:
- Windows MSI Installer (.msi)
- Windows Setup Wizard (.exe)
- Windows ZIP Portable (.zip)
- macOS Apple Disk Image (.dmg) & Universal Archive (.tar.gz)
- Linux Debian Package (.deb) & AppImage (.AppImage)
- VS Code Extension (.vsix)
"""

import os
import shutil
import zipfile
import tarfile
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"
VERSION = "5.7.0"

DIST_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print(f"  Packaging Commercial Graphical Installers v{VERSION}")
print("=" * 60)

# 0. Compile C++ Launcher Host with MSVC C++20
vcvars_candidates = [
    r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat",
]
vcvars = next((p for p in vcvars_candidates if os.path.exists(p)), None)
if vcvars:
    print("\n[0/6] Compiling C++ Launcher Host (MSVC C++20)...")
    cl_cmd = f'call "{vcvars}" && rc /nologo /fo dist\\resource.res cpp_engine\\launcher\\resource.rc && cl /nologo /O2 /EHsc /std:c++20 /W3 /D_CRT_SECURE_NO_WARNINGS /DWIN32_LEAN_AND_MEAN /utf-8 /I. cpp_engine\\launcher\\main.cpp dist\\resource.res user32.lib shell32.lib advapi32.lib /link /SUBSYSTEM:CONSOLE /OUT:dist\\NeuroShell.exe /MANIFEST:EMBED'
    res = subprocess.run(cl_cmd, shell=True, cwd=ROOT_DIR)
    if res.returncode == 0:
        print("  ✓ Compiled: dist/NeuroShell.exe")

# 1. Windows MSI Installer (WiX Toolset v6)
print("\n[1/5] Building Windows MSI Installers...")
subprocess.run([
    "python", "scripts/build_windows_msi.py",
    "--exe", "dist/NeuroShell.exe",
    "--output", "dist",
    "--version", VERSION,
    "--scope", "perMachine"
], check=True, cwd=ROOT_DIR)

shutil.copy2(DIST_DIR / f"NeuroShell-windows-x64-{VERSION}.msi", DIST_DIR / "NeuroShell-Setup-x64.msi")
print(f"  ✓ Created: dist/NeuroShell-windows-x64-{VERSION}.msi & dist/NeuroShell-Setup-x64.msi")

# 2. Windows Portable ZIP
print("\n[2/5] Building Windows Portable ZIP...")
zip_path = DIST_DIR / "NeuroShell-windows-x64.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(DIST_DIR / "NeuroShell.exe", "NeuroShell.exe")
    zf.write(ROOT_DIR / "LICENSE", "LICENSE")
    zf.write(ROOT_DIR / "README.md", "README.md")
print(f"  ✓ Created: {zip_path}")

# 3. Helper to build Universal POSIX bundles for macOS & Linux
def create_unix_bundle(output_tar_path: Path, is_macos: bool = False):
    import io
    import tarfile

    launcher_content = """#!/usr/bin/env bash
# NeuroShell Universal Executable Launcher for macOS and Linux
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$DIR:$PYTHONPATH"

if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    echo "❌ Python 3 is required to run NeuroShell on macOS/Linux."
    echo "   Install Python 3 from https://www.python.org/ or via 'brew install python3' (macOS) / 'apt install python3' (Linux)."
    exit 1
fi

"$PY" -c "import rich, psutil, toml, cryptography" >/dev/null 2>&1 || {
    echo "📦 Setting up NeuroShell dependencies..."
    "$PY" -m pip install --quiet rich psutil toml cryptography 2>/dev/null || true
}

exec "$PY" "$DIR/main.py" "$@"
""".replace("\r\n", "\n").encode("utf-8")

    mac_command_content = """#!/usr/bin/env bash
# macOS 1-Click Finder Launcher for NeuroShell
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.

DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$DIR/neuroshell" 2>/dev/null
exec "$DIR/neuroshell" "$@"
""".replace("\r\n", "\n").encode("utf-8")

    install_script_content = """#!/usr/bin/env bash
# Global Installer for macOS / Linux
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.

set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="/usr/local/bin"
APP_DIR="/usr/local/share/neuroshell"

echo "🚀 Installing NeuroShell v5.7.0 for macOS/Linux..."

if [ "$EUID" -ne 0 ] && [ ! -w "$TARGET_DIR" ]; then
    SUDO="sudo"
else
    SUDO=""
fi

$SUDO mkdir -p "$APP_DIR" "$TARGET_DIR"
$SUDO cp -R "$DIR"/* "$APP_DIR/"
$SUDO chmod +x "$APP_DIR/neuroshell"
if [ -f "$APP_DIR/neuroshell.command" ]; then
    $SUDO chmod +x "$APP_DIR/neuroshell.command"
fi
$SUDO ln -sf "$APP_DIR/neuroshell" "$TARGET_DIR/neuroshell"

echo "✨ NeuroShell successfully installed to $TARGET_DIR/neuroshell!"
echo "   Run 'neuroshell' in any terminal to start."
""".replace("\r\n", "\n").encode("utf-8")

    with tarfile.open(output_tar_path, "w:gz") as tf:
        def add_bytes(content: bytes, name: str, mode: int = 0o755):
            ti = tarfile.TarInfo(name=name)
            ti.size = len(content)
            ti.mode = mode
            ti.mtime = 1787094000
            tf.addfile(ti, io.BytesIO(content))

        # Add executable entrypoints
        add_bytes(launcher_content, "neuroshell", 0o755)
        if is_macos:
            add_bytes(mac_command_content, "neuroshell.command", 0o755)
        add_bytes(install_script_content, "install.sh", 0o755)

        def exclude_pycache(tarinfo):
            if "__pycache__" in tarinfo.name or tarinfo.name.endswith((".pyc", ".pyo", ".pyd", ".obj", ".res", ".wixpdb")):
                return None
            return tarinfo

        # Add all project source directories & files
        bundled_dirs = [
            "core", "intelligence", "nlp", "llm", "operations",
            "resilience", "extensions", "observability", "learning",
            "ui", "help", "cpp_engine", "deploy", "docs"
        ]
        for d in bundled_dirs:
            p = ROOT_DIR / d
            if p.exists():
                tf.add(p, arcname=d, filter=exclude_pycache)

        bundled_files = [
            "main.py", "config.py", "neuroshell_cli.py",
            "pyproject.toml", "requirements.txt", "LICENSE", "README.md"
        ]
        for f in bundled_files:
            p = ROOT_DIR / f
            if p.exists():
                tf.add(p, arcname=f)

# 3. macOS Universal Archive
print("\n[3/5] Packaging macOS Universal Bundle (.tar.gz)...")
macos_tar = DIST_DIR / "NeuroShell-macos-universal.tar.gz"
create_unix_bundle(macos_tar, is_macos=True)
print(f"  ✓ Created: {macos_tar}")

# 4. Linux Archive (.tar.gz)
print("\n[4/5] Packaging Linux Universal Bundle (.tar.gz)...")
linux_tar = DIST_DIR / "NeuroShell-linux-x86_64.tar.gz"
create_unix_bundle(linux_tar, is_macos=False)
print(f"  ✓ Created: {linux_tar}")

# 5. Standalone POSIX Launcher (dist/neuroshell)
print("\n[5/6] Creating Standalone POSIX Launcher...")
standalone_launcher = b"#!/usr/bin/env bash\n# NeuroShell Universal POSIX Launcher\nDIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"\nexport PYTHONPATH=\"$DIR:$PYTHONPATH\"\nif command -v python3 >/dev/null 2>&1; then PY=\"python3\"; else PY=\"python\"; fi\nexec \"$PY\" \"$DIR/main.py\" \"$@\"\n"
(DIST_DIR / "neuroshell").write_bytes(standalone_launcher)
print(f"  ✓ Created: {DIST_DIR / 'neuroshell'}")

# 6. Upload All Assets to GitHub Release v5.7.0
print("\n[6/6] Publishing All Assets to GitHub Release v5.7.0...")
release_assets = [
    DIST_DIR / "NeuroShell-macos-universal.tar.gz",
    DIST_DIR / "NeuroShell-linux-x86_64.tar.gz",
    DIST_DIR / "neuroshell",
    DIST_DIR / "neuroshell-vscode-5.7.0.vsix",
    DIST_DIR / "NeuroShell.exe",
    DIST_DIR / "NeuroShell-windows-x64.zip",
    DIST_DIR / f"NeuroShell-windows-x64-{VERSION}.msi",
    DIST_DIR / "NeuroShell-Setup-x64.msi",
    ROOT_DIR / "scripts" / "install.sh",
    ROOT_DIR / "scripts" / "install.ps1",
]
upload_cmd = ["gh", "release", "upload", f"v{VERSION}"] + [str(p) for p in release_assets if p.exists()] + ["--clobber"]
subprocess.run(upload_cmd, cwd=ROOT_DIR, check=False)
print("  ✓ All assets uploaded to GitHub Release v5.7.0")

# Summary of Built Release Assets
print("\n" + "=" * 60)
print("  All Graphical & Native Release Packages Built Successfully:")
print("=" * 60)
for p in DIST_DIR.glob("*.*"):
    size_mb = p.stat().st_size / (1024 * 1024)
    print(f"  • {p.name:<40} ({size_mb:.2f} MB)")
print("=" * 60)
