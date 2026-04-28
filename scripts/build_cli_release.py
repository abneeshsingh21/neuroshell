# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Cross-platform CLI build and packaging automation for NeuroShell."""

from __future__ import annotations

import argparse
import hashlib
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

    # Build the PyInstaller command for the CLI
    binary_name = "NeuroShell-CLI" if system_name.startswith("win") else "neuroshell"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(project_root / "neuroshell_cli.py"),
        "--name",
        binary_name,
        "--noconfirm",
        "--clean",
        "--onefile",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
    ]

    # Include hidden imports for CLI
    cmd.extend([
        "--hidden-import", "rich",
        "--collect-all", "torch",
        "--collect-all", "transformers",
        "--collect-all", "sentence_transformers",
        "--collect-all", "spacy"
    ])

    return cmd


def run_build(project_root: Path, out_dir: Path) -> Path:
    dist_dir = out_dir / "dist_cli"
    work_dir = out_dir / "build_cli"
    dist_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    cmd = build_command(project_root=project_root, dist_dir=dist_dir, work_dir=work_dir)
    print("Running PyInstaller:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    system_name = platform.system().lower()
    exe_name = "NeuroShell-CLI.exe" if system_name.startswith("win") else "neuroshell"
    exe = dist_dir / exe_name
    
    if not exe.exists():
        raise FileNotFoundError(f"built executable not found: {exe}")
    return exe


def package_artifact(binary_path: Path, release_dir: Path) -> Path:
    release_dir.mkdir(parents=True, exist_ok=True)
    system_name = platform.system().lower()

    if system_name.startswith("win"):
        archive = release_dir / "NeuroShell-CLI-windows-x64.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(binary_path, arcname=binary_path.name)
            for extra in ["README.md"]:
                p = binary_path.parent.parent.parent / extra
                if p.exists():
                    zf.write(p, arcname=p.name)
    else:
        label = "macos" if system_name.startswith("darwin") else "linux"
        archive = release_dir / f"neuroshell-cli-{label}-x64.tar.gz"
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(binary_path, arcname=binary_path.name)
            for extra in ["README.md"]:
                p = binary_path.parent.parent.parent / extra
                if p.exists():
                    tf.add(p, arcname=p.name)

    return archive


def write_checksums(artifact: Path) -> Path:
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    checksum_file = artifact.with_suffix(artifact.suffix + ".sha256")
    checksum_file.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")
    return checksum_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and package NeuroShell CLI")
    parser.add_argument("--output", default="release", help="Output directory for build artifacts")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    out_dir = (project_root / args.output).resolve()

    if shutil.which("pyinstaller") is None:
        print("PyInstaller not found. Install with: pip install pyinstaller")
        return 2

    print("Building NeuroShell CLI...")
    binary = run_build(project_root=project_root, out_dir=out_dir)
    
    print(f"Packaging {binary}...")
    artifact = package_artifact(binary_path=binary, release_dir=out_dir)
    
    print("Writing checksums...")
    checksum = write_checksums(artifact)

    print(f"Built binary: {binary}")
    print(f"Release artifact: {artifact}")
    print(f"Checksum file: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
