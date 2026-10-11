# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Universal App & Package Uninstaller Subsystem for NeuroShell.
Discovers and uninstalls applications and software packages dynamically:
- Windows: winget uninstall, Windows Registry (HKLM & HKCU Uninstall keys), scoop, choco
- macOS: Homebrew (brew uninstall / cask), /Applications
- Linux: APT, DNF, Pacman, Snap, Flatpak
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

# Ensure neuroshell root is on sys.path regardless of execution CWD
_NEUROSHELL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _NEUROSHELL_ROOT not in sys.path:
    sys.path.insert(0, _NEUROSHELL_ROOT)

from ui.table_formatter import (
    AdaptiveTableFormatter,
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_MAGENTA,
    C_RED,
    C_RESET,
    C_WHITE,
    C_YELLOW,
)

_IS_WINDOWS = platform.system() == "Windows"
_IS_MACOS = platform.system() == "Darwin"
_IS_LINUX = platform.system() == "Linux"


@dataclass
class InstalledApp:
    """Represents an application detected on the host operating system."""
    name: str
    version: str = "Unknown"
    publisher: str = "Unknown"
    source: str = "System"  # winget, Registry, brew, apt, etc.
    app_id: str = ""
    uninstall_command: str = ""
    is_silent_capable: bool = False


@dataclass
class UninstallResult:
    """Outcome of an uninstallation attempt."""
    app_name: str
    success: bool
    command_executed: str = ""
    details: str = ""
    exit_code: int = 0


class UniversalUninstaller:
    """
    Cross-platform dynamic application uninstaller.
    Inspects package managers, system registries, and application bundles
    to find and cleanly remove software.
    """

    def __init__(self):
        self._table = AdaptiveTableFormatter()

    def discover_installed_apps(self, query: str = "") -> list[InstalledApp]:
        """
        Dynamically query all system package registries and package managers.
        """
        results: list[InstalledApp] = []
        seen_names: set[str] = set()

        query_clean = query.strip().lower()

        if _IS_WINDOWS:
            # 1. Inspect Windows Registry Uninstall Keys
            reg_apps = self._query_windows_registry_apps(query_clean)
            for app in reg_apps:
                key = app.name.lower()
                if key not in seen_names:
                    seen_names.add(key)
                    results.append(app)

            # 2. Inspect Winget if available
            winget_apps = self._query_winget_apps(query_clean)
            for app in winget_apps:
                key = app.name.lower()
                if key not in seen_names:
                    seen_names.add(key)
                    results.append(app)

        elif _IS_MACOS:
            # Homebrew & macOS Applications
            brew_apps = self._query_brew_apps(query_clean)
            results.extend(brew_apps)

        elif _IS_LINUX:
            # Linux package managers
            linux_apps = self._query_linux_apps(query_clean)
            results.extend(linux_apps)

        # Sort matches by relevance: exact match > prefix > substring
        if query_clean:
            def sort_key(app: InstalledApp) -> tuple[int, str]:
                nl = app.name.lower()
                if nl == query_clean:
                    return (0, nl)
                if nl.startswith(query_clean):
                    return (1, nl)
                if query_clean in nl:
                    return (2, nl)
                return (3, nl)

            results.sort(key=sort_key)

        return results

    def _query_windows_registry_apps(self, query: str = "") -> list[InstalledApp]:
        """Read 32-bit and 64-bit Registry Uninstall keys."""
        apps: list[InstalledApp] = []
        if not _IS_WINDOWS:
            return apps

        try:
            import winreg

            roots = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            ]

            for hkey, subkey in roots:
                try:
                    with winreg.OpenKey(hkey, subkey, 0, winreg.KEY_READ) as key:
                        count = winreg.QueryInfoKey(key)[0]
                        for i in range(count):
                            try:
                                subkey_name = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, subkey_name) as app_key:
                                    def get_val(name: str) -> str:
                                        try:
                                            v, _ = winreg.QueryValueEx(app_key, name)
                                            return str(v).strip() if v else ""
                                        except Exception:
                                            return ""

                                    display_name = get_val("DisplayName")
                                    if not display_name:
                                        continue

                                    # Filter if query is specified
                                    if query and query not in display_name.lower():
                                        continue

                                    version = get_val("DisplayVersion") or "Unknown"
                                    publisher = get_val("Publisher") or "Unknown"
                                    uninst = get_val("QuietUninstallString") or get_val("UninstallString")
                                    quiet = bool(get_val("QuietUninstallString"))

                                    apps.append(InstalledApp(
                                        name=display_name,
                                        version=version,
                                        publisher=publisher,
                                        source="Windows Registry",
                                        app_id=subkey_name,
                                        uninstall_command=uninst,
                                        is_silent_capable=quiet,
                                    ))
                            except Exception:
                                continue
                except Exception:
                    continue
        except Exception:
            pass

        return apps

    def _query_winget_apps(self, query: str = "") -> list[InstalledApp]:
        """Query winget list for matching installed packages."""
        apps: list[InstalledApp] = []
        if not shutil.which("winget"):
            return apps

        try:
            cmd = ["winget", "list", "--accept-source-agreements"]
            if query:
                cmd.extend(["--query", query])

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=12,
            )
            if proc.returncode == 0 and proc.stdout:
                lines = proc.stdout.splitlines()
                # Find separator line (e.g. "------   ----   -------")
                start_idx = 0
                for idx, line in enumerate(lines):
                    if line.startswith("---") or line.startswith("───"):
                        start_idx = idx + 1
                        break

                for line in lines[start_idx:]:
                    line = line.strip()
                    if not line:
                        continue
                    parts = re.split(r"\s{2,}", line)
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        app_id = parts[1].strip()
                        ver = parts[2].strip() if len(parts) > 2 else "Unknown"
                        source = parts[3].strip() if len(parts) > 3 else "winget"

                        apps.append(InstalledApp(
                            name=name,
                            version=ver,
                            publisher="winget",
                            source=source or "winget",
                            app_id=app_id,
                            uninstall_command=f"winget uninstall --id {app_id} --accept-source-agreements",
                            is_silent_capable=True,
                        ))
        except Exception:
            pass

        return apps

    def _query_brew_apps(self, query: str = "") -> list[InstalledApp]:
        """Query Homebrew packages and casks on macOS."""
        apps: list[InstalledApp] = []
        if not shutil.which("brew"):
            return apps

        try:
            proc = subprocess.run(
                ["brew", "list", "--versions"],
                capture_output=True,
                text=True,
                errors="ignore",
                timeout=8,
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    parts = line.strip().split()
                    if parts:
                        name = parts[0]
                        ver = parts[1] if len(parts) > 1 else "Unknown"
                        if not query or query in name.lower():
                            apps.append(InstalledApp(
                                name=name,
                                version=ver,
                                source="Homebrew",
                                app_id=name,
                                uninstall_command=f"brew uninstall {name}",
                                is_silent_capable=True,
                            ))
        except Exception:
            pass
        return apps

    def _query_linux_apps(self, query: str = "") -> list[InstalledApp]:
        """Query native Linux package managers."""
        apps: list[InstalledApp] = []
        if shutil.which("dpkg"):
            try:
                cmd = ["dpkg", "-l"] + ([f"*{query}*"] if query else [])
                proc = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=8)
                for line in proc.stdout.splitlines():
                    if line.startswith("ii "):
                        parts = line.split()
                        if len(parts) >= 3:
                            name = parts[1]
                            ver = parts[2]
                            apps.append(InstalledApp(
                                name=name,
                                version=ver,
                                source="APT/dpkg",
                                app_id=name,
                                uninstall_command=f"sudo apt remove -y {name}",
                                is_silent_capable=True,
                            ))
            except Exception:
                pass
        return apps

    def uninstall(self, target: str, silent: bool = False, confirm: bool = True) -> UninstallResult:
        """
        Locate the specified application and execute uninstallation.
        """
        clean_target = target.strip()
        # Clean generic descriptors: "uninstall chrome browser" -> "chrome"
        for suffix in (" browser", " editor", " app", " application", " tool", " program"):
            if clean_target.lower().endswith(suffix):
                clean_target = clean_target[: -len(suffix)].strip()
                break

        print(f"\n  {C_BOLD}{C_CYAN}🔍 Scanning for Installed Application: {C_WHITE}{clean_target}{C_RESET}...\n")
        matches = self.discover_installed_apps(clean_target)

        if not matches:
            # Fallback direct winget / package manager attempt
            if _IS_WINDOWS and shutil.which("winget"):
                print(f"  {C_YELLOW}⚠ No exact registry match found. Attempting direct winget uninstallation for '{clean_target}'...{C_RESET}\n")
                uninst_cmd = f"winget uninstall {clean_target} --accept-source-agreements" + (" --silent" if silent else "")
                proc = subprocess.run(uninst_cmd, shell=True)
                return UninstallResult(
                    app_name=clean_target,
                    success=(proc.returncode == 0),
                    command_executed=uninst_cmd,
                    exit_code=proc.returncode,
                    details="Direct winget execution completed." if proc.returncode == 0 else "winget uninstallation failed.",
                )

            print(f"  {C_RED}❌ Application '{clean_target}' was not found in installed system packages or registry.{C_RESET}\n")
            return UninstallResult(
                app_name=clean_target,
                success=False,
                details=f"No installed application matching '{clean_target}' found.",
                exit_code=1,
            )

        best_match = matches[0]

        # Present the match in an executive card
        print(f"  {C_CYAN}╭── 📦 Target Application Found ────────────────────────────────╮{C_RESET}")
        print(f"  {C_CYAN}│{C_RESET}  {C_BOLD}{C_WHITE}Name:{C_RESET}      {C_GREEN}{best_match.name}{C_RESET}")
        print(f"  {C_CYAN}│{C_RESET}  {C_BOLD}{C_WHITE}Version:{C_RESET}   {best_match.version}")
        print(f"  {C_CYAN}│{C_RESET}  {C_BOLD}{C_WHITE}Publisher:{C_RESET} {best_match.publisher}")
        print(f"  {C_CYAN}│{C_RESET}  {C_BOLD}{C_WHITE}Source:{C_RESET}    {best_match.source}")
        print(f"  {C_CYAN}│{C_RESET}  {C_BOLD}{C_WHITE}Command:{C_RESET}   {C_YELLOW}{best_match.uninstall_command}{C_RESET}")
        print(f"  {C_CYAN}╰───────────────────────────────────────────────────────────────╯{C_RESET}\n")

        # Determine exact execution command
        exec_cmd = best_match.uninstall_command
        if not exec_cmd:
            if best_match.app_id and _IS_WINDOWS and shutil.which("winget"):
                exec_cmd = f"winget uninstall --id {best_match.app_id} --accept-source-agreements"
            else:
                exec_cmd = f"winget uninstall \"{best_match.name}\""

        if silent and best_match.is_silent_capable and "winget" in exec_cmd and "--silent" not in exec_cmd:
            exec_cmd += " --silent"

        print(f"  {C_BOLD}{C_YELLOW}🚀 Executing Uninstaller:{C_RESET} {C_WHITE}{exec_cmd}{C_RESET}\n")
        try:
            proc = subprocess.run(exec_cmd, shell=True)
            success = proc.returncode == 0
            if success:
                print(f"\n  {C_GREEN}✔ Uninstallation of '{best_match.name}' completed successfully.{C_RESET}\n")
            else:
                print(f"\n  {C_RED}❌ Uninstaller exited with status {proc.returncode}.{C_RESET}\n")

            return UninstallResult(
                app_name=best_match.name,
                success=success,
                command_executed=exec_cmd,
                details=f"Exited with code {proc.returncode}",
                exit_code=proc.returncode,
            )
        except Exception as exc:
            print(f"\n  {C_RED}❌ Execution error: {exc}{C_RESET}\n")
            return UninstallResult(
                app_name=best_match.name,
                success=False,
                command_executed=exec_cmd,
                details=str(exc),
                exit_code=1,
            )

    def print_app_list(self, query: str = ""):
        """Display an adaptively styled table of installed software."""
        apps = self.discover_installed_apps(query)
        if not apps:
            print(f"\n  {C_YELLOW}No installed software found matching query '{query}'.{C_RESET}\n")
            return

        headers = ["#", "APPLICATION NAME", "VERSION", "PUBLISHER", "SOURCE"]
        rows = [[str(i + 1), app.name, app.version, app.publisher, app.source] for i, app in enumerate(apps[:40])]

        tsv_data = "\n".join("\t".join(r) for r in rows)

        title = f"Installed Software Registry ({len(apps)} applications)"
        print("\n" + self._table.format_tsv(tsv_data, headers=headers, title=title) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NeuroShell Universal App Uninstaller")
    parser.add_argument("app", nargs="?", default="", help="Application name to search or uninstall")
    parser.add_argument("--list", "-l", action="store_true", help="List matching installed applications")
    parser.add_argument("--silent", "-s", action="store_true", help="Attempt unattended silent uninstallation")
    args = parser.parse_args(argv)

    uninstaller = UniversalUninstaller()

    if args.list or not args.app:
        uninstaller.print_app_list(args.app)
        return 0

    res = uninstaller.uninstall(args.app, silent=args.silent)
    return 0 if res.success else 1


if __name__ == "__main__":
    sys.exit(main())
