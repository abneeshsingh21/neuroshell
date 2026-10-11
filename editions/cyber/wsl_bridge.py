"""
NeuroShell Cyber — WSL Kali & Native Linux Bridge.
Provides transparent execution of security toolchains across Windows (WSL2 Kali)
and Native Linux environments.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class WSLDistroInfo:
    available: bool
    distro_name: str
    is_kali: bool
    version: int = 2


class WSLKaliBridge:
    """
    Transparent execution bridge between Windows host and WSL Kali Linux,
    with automatic fallback to native Linux when running on bare-metal Kali/Ubuntu.
    """

    _cached_distro: Optional[WSLDistroInfo] = None

    @classmethod
    def is_windows(cls) -> bool:
        return platform.system().lower() == "windows"

    @classmethod
    def is_native_linux(cls) -> bool:
        return platform.system().lower() == "linux"

    @classmethod
    def is_native_kali(cls) -> bool:
        if not cls.is_native_linux():
            return False
        try:
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release", encoding="utf-8") as f:
                    content = f.read().lower()
                    return "id=kali" in content or "kali linux" in content
        except Exception:
            pass
        return False

    @classmethod
    def detect_wsl_distro(cls) -> WSLDistroInfo:
        """Detect installed WSL distributions, prioritizing Kali Linux."""
        if cls._cached_distro is not None:
            return cls._cached_distro

        if not cls.is_windows():
            cls._cached_distro = WSLDistroInfo(
                available=True,
                distro_name="native",
                is_kali=cls.is_native_kali(),
            )
            return cls._cached_distro

        # On Windows, check wsl.exe
        wsl_bin = shutil.which("wsl.exe") or shutil.which("wsl")
        if not wsl_bin:
            cls._cached_distro = WSLDistroInfo(available=False, distro_name="", is_kali=False)
            return cls._cached_distro

        try:
            # wsl -l -q outputs distro names (often UTF-16 on Windows)
            cp = subprocess.run(
                ["wsl.exe", "-l", "-q"],
                capture_output=True,
                timeout=5,
            )
            raw = cp.stdout
            text = ""
            for enc in ("utf-16-le", "utf-8", "ascii"):
                try:
                    text = raw.decode(enc)
                    if text.strip():
                        break
                except UnicodeDecodeError:
                    continue

            distros = [line.strip().replace("\x00", "") for line in text.splitlines() if line.strip()]

            # Look for kali-linux specifically
            for d in distros:
                if "kali" in d.lower():
                    cls._cached_distro = WSLDistroInfo(available=True, distro_name=d, is_kali=True)
                    return cls._cached_distro

            # If Kali not named explicitly, check if any distro exists
            if distros:
                cls._cached_distro = WSLDistroInfo(available=True, distro_name=distros[0], is_kali=False)
                return cls._cached_distro

        except Exception:
            pass

        cls._cached_distro = WSLDistroInfo(available=False, distro_name="", is_kali=False)
        return cls._cached_distro

    @classmethod
    def get_attacker_ip(cls, interface: str | None = None) -> str:
        """
        Dynamically determine the attacker host IP (tun0, eth0, or LAN IP).
        Prevents the user from ever needing to manually lookup or type LHOST.
        """
        # If in WSL or Linux, check IP tool directly
        if cls.is_native_linux():
            for iface in ([interface] if interface else ["tun0", "eth0", "wlan0"]):
                if not iface:
                    continue
                try:
                    cp = subprocess.run(
                        f"ip -4 addr show {iface} | grep -oP '(?<=inet\\s)\\d+(\\.\\d+){{3}}'",
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    ip = cp.stdout.strip()
                    if ip:
                        return ip
                except Exception:
                    pass

        # Windows or generic fallback via local socket lookup
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            # Doesn't actually send packet, just resolves outgoing route
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass

        return "127.0.0.1"

    @classmethod
    def build_exec_command(
        cls,
        command: str,
        as_root: bool = False,
        distro: str | None = None,
    ) -> list[str] | str:
        """
        Transform a command into an executable form for the current platform
        (either native Linux execution or routed via wsl.exe).
        """
        if cls.is_native_linux():
            if as_root and os.geteuid() != 0:
                return f"sudo {command}"
            return command

        distro_info = cls.detect_wsl_distro()
        target_distro = distro or distro_info.distro_name

        if not distro_info.available:
            # Fallback to direct Windows execution if WSL is missing
            return command

        cmd_list = ["wsl.exe"]
        if target_distro:
            cmd_list.extend(["-d", target_distro])
        if as_root:
            cmd_list.extend(["-u", "root"])
        cmd_list.extend(["--", "bash", "-c", command])
        return cmd_list

    @classmethod
    def execute(
        cls,
        command: str,
        as_root: bool = False,
        distro: str | None = None,
        timeout_s: int = 120,
    ) -> subprocess.CompletedProcess[str]:
        """
        Execute a security command seamlessly through WSL Kali or native Linux.
        """
        cmd = cls.build_exec_command(command, as_root=as_root, distro=distro)
        if isinstance(cmd, str):
            return subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )

    @classmethod
    def check_tool_installed(cls, tool_name: str) -> bool:
        """Verify whether a cybersecurity tool is installed (either natively or inside WSL)."""
        if cls.is_native_linux():
            return shutil.which(tool_name) is not None

        distro_info = cls.detect_wsl_distro()
        if not distro_info.available:
            return shutil.which(tool_name) is not None

        try:
            res = cls.execute(f"which {tool_name}", timeout_s=5)
            return res.returncode == 0 and bool(res.stdout.strip())
        except Exception:
            return False
