# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Dependency Resolver
Proactively checks if prerequisites exist before command execution.
"""

import shutil
import subprocess
import re
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class DependencyCheck:
    """Result of a dependency check."""
    needed: str           # what's needed (e.g., "pytest")
    is_available: bool
    fix_command: Optional[str] = None  # suggested install command
    message: str = ""
    version_found: str = ""
    version_needed: str = ""


class DependencyResolver:
    """Checks command prerequisites before execution."""

    # Tools and their install commands
    INSTALL_HINTS = {
        "pytest": "pip install pytest",
        "flask": "pip install flask",
        "django": "pip install django",
        "numpy": "pip install numpy",
        "pandas": "pip install pandas",
        "requests": "pip install requests",
        "fastapi": "pip install fastapi uvicorn",
        "node_modules": "npm install",
        "venv": "python -m venv venv",
        "docker": "Install Docker from https://docker.com",
        "gcc": "Install MinGW/GCC",
        "cmake": "pip install cmake",
        "cargo": "Install Rust from https://rustup.rs",
        "go": "Install Go from https://go.dev",
    }

    # Command → dependency mappings
    COMMAND_DEPS = {
        "pytest": [("pytest", "pip install pytest")],
        "python -m pytest": [("pytest", "pip install pytest")],
        "flask run": [("flask", "pip install flask")],
        "uvicorn": [("uvicorn", "pip install uvicorn")],
        "npm start": [("node_modules/", None)],
        "npm test": [("node_modules/", None)],
        "npm run": [("node_modules/", None)],
        "cargo build": [("cargo", None)],
        "cargo run": [("cargo", None)],
        "docker-compose up": [("docker", None)],
        "docker compose up": [("docker", None)],
        "kubectl": [("kubectl", None)],
        "terraform": [("terraform", None)],
        "python manage.py": [("django", "pip install django")],
    }

    def __init__(self, context_manager=None):
        self.context = context_manager

    def check_command(self, command: str, cwd: Optional[str] = None) -> list[DependencyCheck]:
        """Check all dependencies for a command."""
        cwd = cwd or os.getcwd()
        checks = []

        # 1. Check if the base command tool exists
        base_tool = command.strip().split()[0] if command.strip() else ""
        if base_tool and not self._is_builtin(base_tool):
            tool_check = self._check_tool_exists(base_tool)
            if not tool_check.is_available:
                checks.append(tool_check)

        # 2. Check known command dependencies
        for prefix, deps in self.COMMAND_DEPS.items():
            if command.strip().startswith(prefix):
                for dep_name, install_cmd in deps:
                    if dep_name.endswith("/"):
                        # It's a directory check
                        dir_check = self._check_directory(dep_name.rstrip("/"), cwd)
                        if not dir_check.is_available:
                            checks.append(dir_check)
                    else:
                        pkg_check = self._check_python_package(dep_name)
                        if not pkg_check.is_available:
                            if install_cmd:
                                pkg_check.fix_command = install_cmd
                            checks.append(pkg_check)

        # 3. Check Python version if specified
        version_check = self._check_python_version(command)
        if version_check:
            checks.append(version_check)

        # 4. Check if it's a pip install without pip
        if command.strip().startswith("pip ") and not shutil.which("pip"):
            checks.append(DependencyCheck(
                needed="pip",
                is_available=False,
                fix_command="python -m ensurepip",
                message="pip not found on PATH",
            ))

        return checks

    def _check_tool_exists(self, tool: str) -> DependencyCheck:
        """Check if a CLI tool is available."""
        path = shutil.which(tool)
        if path:
            version = self._get_tool_version(tool)
            return DependencyCheck(
                needed=tool,
                is_available=True,
                version_found=version,
            )

        fix = self.INSTALL_HINTS.get(tool)
        return DependencyCheck(
            needed=tool,
            is_available=False,
            fix_command=fix,
            message=f"'{tool}' not found on PATH",
        )

    def _check_python_package(self, package: str) -> DependencyCheck:
        """Check if a Python package is installed."""
        try:
            result = subprocess.run(
                ["python", "-m", "pip", "show", package],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                version = ""
                for line in result.stdout.split("\n"):
                    if line.startswith("Version:"):
                        version = line.split(":")[1].strip()
                        break
                return DependencyCheck(
                    needed=package,
                    is_available=True,
                    version_found=version,
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return DependencyCheck(
            needed=package,
            is_available=False,
            fix_command=f"pip install {package}",
            message=f"Python package '{package}' not installed",
        )

    def _check_directory(self, dirname: str, cwd: str) -> DependencyCheck:
        """Check if a required directory exists."""
        dir_path = Path(cwd) / dirname
        if dir_path.is_dir():
            return DependencyCheck(needed=dirname, is_available=True)

        install_cmd = None
        if dirname == "node_modules":
            install_cmd = "npm install"
        elif dirname == "venv" or dirname == ".venv":
            install_cmd = "python -m venv venv"

        return DependencyCheck(
            needed=dirname,
            is_available=False,
            fix_command=install_cmd,
            message=f"Directory '{dirname}' not found in {cwd}",
        )

    def _check_python_version(self, command: str) -> Optional[DependencyCheck]:
        """Check if a specific Python version is requested."""
        match = re.match(r"python(\d+\.?\d*)", command.strip().split()[0])
        if not match:
            return None

        requested = match.group(1)
        if not shutil.which(f"python{requested}"):
            # Find what's available
            current = subprocess.run(
                ["python", "--version"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()

            return DependencyCheck(
                needed=f"python{requested}",
                is_available=False,
                fix_command=f"python {' '.join(command.strip().split()[1:])}",
                message=f"Python {requested} not found. Available: {current}",
            )
        return None

    def _get_tool_version(self, tool: str) -> str:
        """Try to get tool version."""
        for flag in ["--version", "-V", "version"]:
            try:
                result = subprocess.run(
                    [tool, flag],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().split("\n")[0][:50]
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue
        return ""

    def _is_builtin(self, cmd: str) -> bool:
        """Check if command is a shell builtin."""
        builtins = {
            "cd", "dir", "echo", "set", "cls", "clear", "exit", "type",
            "mkdir", "rmdir", "copy", "move", "del", "ren", "pushd", "popd",
            "ls", "cat", "pwd", "cp", "mv", "rm", "touch", "chmod",
            "export", "source", "alias", "history", "which", "where",
            "Get-ChildItem", "Set-Location", "Write-Output", "Remove-Item",
            "Copy-Item", "Move-Item", "New-Item", "Get-Content",
        }
        return cmd in builtins
