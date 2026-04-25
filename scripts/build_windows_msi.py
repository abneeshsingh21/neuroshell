# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Build a Windows MSI installer for NeuroShell using WiX Toolset v4."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
from pathlib import Path

APP_NAME = "NeuroShell"
MANUFACTURER = "Abneesh Singh"
UPGRADE_CODE = "{3AABDE41-223D-4DE2-96F2-5A2F1F8D43A1}"


def _text_to_rtf(text: str) -> str:
    """Convert plain text to a minimal RTF document for WiX license UI."""
    escaped = (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    escaped = escaped.replace("\n", r"\par " + "\n")
    return "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Calibri;}}\\f0\\fs22\n" + escaped + "\n}"


def _prepare_license_rtf(license_text_path: Path, out_dir: Path) -> Path:
    """Create an RTF license file consumed by WiX standard dialogs."""
    if not license_text_path.exists():
        raise FileNotFoundError(f"License file not found: {license_text_path}")

    license_text = license_text_path.read_text(encoding="utf-8")
    rtf_path = out_dir / "LICENSE.rtf"
    rtf_path.write_text(_text_to_rtf(license_text), encoding="utf-8")
    return rtf_path


def render_wxs(
    exe_path: Path,
    wxs_path: Path,
    version: str,
    scope: str = "perMachine",
    license_rtf_path: Path | None = None,
) -> Path:
    """Render WiX v4 source file for full one-folder MSI packaging."""
    app_dir = exe_path.parent.resolve()
    include_glob = f"{app_dir.as_posix()}/**"
    if scope not in {"perMachine", "perUser"}:
        raise ValueError("scope must be 'perMachine' or 'perUser'")

    if scope == "perUser":
        root_dir_id = "LocalAppDataFolder"
        install_parent_dir = "USERPROGRAMSFOLDER"
        install_subdir = APP_NAME
    else:
        root_dir_id = "ProgramFiles64Folder"
        install_parent_dir = None
        install_subdir = APP_NAME

    if install_parent_dir:
        install_dir_xml = (
            f'    <StandardDirectory Id="{root_dir_id}">\n'
            f'      <Directory Id="{install_parent_dir}" Name="Programs">\n'
            f'        <Directory Id="INSTALLFOLDER" Name="{install_subdir}" />\n'
            f'      </Directory>\n'
            f'    </StandardDirectory>'
        )
    else:
        install_dir_xml = (
            f'    <StandardDirectory Id="{root_dir_id}">\n'
            f'      <Directory Id="INSTALLFOLDER" Name="{install_subdir}" />\n'
            f'    </StandardDirectory>'
        )

    license_var_xml = ""
    ui_xml = ""
    if license_rtf_path is not None:
        license_var_xml = (
            f'    <WixVariable Id="WixUILicenseRtf" Value="{license_rtf_path.resolve().as_posix()}" />\n'
        )
        ui_xml = (
            '    <ui:WixUI Id="WixUI_InstallDir" InstallDirectory="INSTALLFOLDER" />\n'
        )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs" xmlns:ui="http://wixtoolset.org/schemas/v4/wxs/ui">
  <Package
      Name="{APP_NAME}"
      Manufacturer="{MANUFACTURER}"
      Version="{version}"
      UpgradeCode="{UPGRADE_CODE}"
      Scope="{scope}"
      Language="1033"
      Compressed="yes">

    <MajorUpgrade DowngradeErrorMessage="A newer version of {APP_NAME} is already installed." />
    <MediaTemplate EmbedCab="yes" />
{license_var_xml}{ui_xml}

{install_dir_xml}

    <ComponentGroup Id="AppFiles" Directory="INSTALLFOLDER">
      <Files Include="{include_glob}" />
    </ComponentGroup>

    <Feature Id="MainFeature" Title="{APP_NAME}" Level="1">
      <ComponentGroupRef Id="AppFiles" />
    </Feature>
  </Package>
</Wix>
"""
    wxs_path.parent.mkdir(parents=True, exist_ok=True)
    wxs_path.write_text(xml, encoding="utf-8")
    return wxs_path


def build_msi(exe_path: Path, out_dir: Path, version: str = "4.0.0") -> Path:
    """Build MSI if WiX CLI is installed."""
    if platform.system().lower() != "windows":
        raise RuntimeError("MSI build is only supported on Windows")

    wix = shutil.which("wix")
    if wix is None:
        # Support fresh installations where PATH is not updated in the current shell.
        fallback_candidates = [
            Path("C:/Program Files/WiX Toolset v6.0/bin/wix.exe"),
            Path("C:/Program Files/WiX Toolset v5.0/bin/wix.exe"),
            Path("C:/Program Files/WiX Toolset v4.0/bin/wix.exe"),
        ]
        for candidate in fallback_candidates:
            if candidate.exists():
                wix = str(candidate)
                break
    if wix is None:
        raise RuntimeError("WiX CLI not found. Install WiX Toolset v4+ and ensure 'wix' is in PATH")

    out_dir.mkdir(parents=True, exist_ok=True)
    wxs = render_wxs(exe_path=exe_path, wxs_path=out_dir / "neuroshell-installer.wxs", version=version)
    msi_path = out_dir / f"{APP_NAME}-windows-x64-{version}.msi"

    cmd = [wix, "build", str(wxs), "-o", str(msi_path)]
    subprocess.run(cmd, check=True)

    if not msi_path.exists():
        raise FileNotFoundError(f"MSI build did not produce expected file: {msi_path}")
    return msi_path


def build_msi_with_scope(exe_path: Path, out_dir: Path, version: str = "4.0.0", scope: str = "perMachine") -> Path:
    """Build MSI with install scope control."""
    if platform.system().lower() != "windows":
        raise RuntimeError("MSI build is only supported on Windows")

    wix = shutil.which("wix")
    if wix is None:
        fallback_candidates = [
            Path("C:/Program Files/WiX Toolset v6.0/bin/wix.exe"),
            Path("C:/Program Files/WiX Toolset v5.0/bin/wix.exe"),
            Path("C:/Program Files/WiX Toolset v4.0/bin/wix.exe"),
        ]
        for candidate in fallback_candidates:
            if candidate.exists():
                wix = str(candidate)
                break
    if wix is None:
        raise RuntimeError("WiX CLI not found. Install WiX Toolset v4+ and ensure 'wix' is in PATH")

    out_dir.mkdir(parents=True, exist_ok=True)
    license_txt = Path("LICENSE.txt").resolve()
    license_rtf = _prepare_license_rtf(license_txt, out_dir)

    wxs = render_wxs(
        exe_path=exe_path,
        wxs_path=out_dir / "neuroshell-installer.wxs",
        version=version,
        scope=scope,
        license_rtf_path=license_rtf,
    )
    suffix = "user" if scope == "perUser" else "x64"
    msi_path = out_dir / f"{APP_NAME}-windows-{suffix}-{version}.msi"

    cmd = [
        wix,
        "build",
        str(wxs),
        "-ext",
        "WixToolset.UI.wixext",
        "-o",
        str(msi_path),
    ]
    subprocess.run(cmd, check=True)

    if not msi_path.exists():
        raise FileNotFoundError(f"MSI build did not produce expected file: {msi_path}")
    return msi_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build NeuroShell MSI installer")
    parser.add_argument("--exe", required=True, help="Path to built NeuroShell.exe")
    parser.add_argument("--output", default="release", help="Directory to place MSI outputs")
    parser.add_argument("--version", default="4.0.0", help="MSI product version")
    parser.add_argument("--scope", choices=["perMachine", "perUser"], default="perMachine", help="Install scope")
    args = parser.parse_args()

    exe_path = Path(args.exe).resolve()
    if not exe_path.exists():
        print(f"Executable not found: {exe_path}")
        return 2

    try:
        msi = build_msi_with_scope(
            exe_path=exe_path,
            out_dir=Path(args.output).resolve(),
            version=args.version,
            scope=args.scope,
        )
    except Exception as exc:
        print(f"MSI build failed: {exc}")
        return 3

    print(f"MSI built: {msi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
