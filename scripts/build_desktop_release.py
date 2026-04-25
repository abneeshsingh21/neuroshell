# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Cross-platform desktop build and packaging automation for NeuroShell."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


def build_command(project_root: Path, dist_dir: Path, work_dir: Path, system_name: str | None = None) -> list[str]:
    system_name = (system_name or platform.system()).lower()
    sep = ";" if system_name.startswith("win") else ":"

    icon_path = project_root / "assets" / "icon.ico"
    data_spec = f"{project_root / 'assets'}{sep}assets"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(project_root / "desktop_app.py"),
        "--name",
        "NeuroShell",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--add-data",
        data_spec,
    ]

    if icon_path.exists() and system_name.startswith("win"):
        cmd.extend(["--icon", str(icon_path)])

    return cmd


def run_build(project_root: Path, out_dir: Path) -> Path:
    dist_dir = out_dir / "dist"
    work_dir = out_dir / "build"
    dist_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    cmd = build_command(project_root=project_root, dist_dir=dist_dir, work_dir=work_dir)
    subprocess.run(cmd, check=True)

    system_name = platform.system().lower()
    exe = dist_dir / ("NeuroShell.exe" if system_name.startswith("win") else "NeuroShell")
    if not exe.exists():
        raise FileNotFoundError(f"built executable not found: {exe}")
    return exe


def package_artifact(binary_path: Path, release_dir: Path) -> Path:
    release_dir.mkdir(parents=True, exist_ok=True)
    system_name = platform.system().lower()

    if system_name.startswith("win"):
        archive = release_dir / "NeuroShell-windows-x64.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(binary_path, arcname=binary_path.name)
            for extra in ["README.md", "assets/logo.png", "assets/logo.svg", "assets/brand_guide.md"]:
                p = binary_path.parent.parent.parent / extra
                if p.exists():
                    zf.write(p, arcname=p.name if p.name != "brand_guide.md" else "BRAND_GUIDE.md")
    else:
        label = "macos" if system_name.startswith("darwin") else "linux"
        archive = release_dir / f"NeuroShell-{label}-x64.tar.gz"
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(binary_path, arcname=binary_path.name)

    return archive


def write_checksums(artifact: Path) -> Path:
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    checksum_file = artifact.with_suffix(artifact.suffix + ".sha256")
    checksum_file.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")
    return checksum_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and package NeuroShell desktop app")
    parser.add_argument("--output", default="release", help="Output directory for build artifacts")
    parser.add_argument("--msi", action="store_true", help="Also build MSI installer on Windows")
    parser.add_argument("--version", default="4.0.0", help="Version for MSI/update packaging metadata")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    out_dir = (project_root / args.output).resolve()

    if shutil.which("pyinstaller") is None:
        print("PyInstaller not found. Install with: pip install pyinstaller")
        return 2

    binary = run_build(project_root=project_root, out_dir=out_dir)
    artifact = package_artifact(binary_path=binary, release_dir=out_dir)
    checksum = write_checksums(artifact)

    msi_path = None
    if args.msi and platform.system().lower().startswith("win"):
        try:
            try:
                from scripts.build_windows_msi import build_msi
            except ModuleNotFoundError:
                msi_script = project_root / "scripts" / "build_windows_msi.py"
                spec = importlib.util.spec_from_file_location("build_windows_msi", msi_script)
                if spec is None or spec.loader is None:
                    raise RuntimeError(f"unable to load MSI builder module from {msi_script}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                build_msi = module.build_msi
            msi_path = build_msi(exe_path=binary, out_dir=out_dir, version=args.version)
        except Exception as exc:
            print(f"MSI build skipped/failed: {exc}")

    print(f"Built binary: {binary}")
    print(f"Release artifact: {artifact}")
    print(f"Checksum file: {checksum}")
    if msi_path:
        print(f"MSI artifact: {msi_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
