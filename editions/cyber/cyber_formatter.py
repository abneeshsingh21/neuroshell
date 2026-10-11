"""
NeuroShell Cyber — Beautiful Output Formatter & Table Transformer.
Parses raw terminal text from Nmap, Gobuster, FFuF, Nuclei, and SQLmap
and renders aligned ANSI tables and colored vulnerability cards.
"""

from __future__ import annotations

import re


class CyberFormatter:
    """
    Transforms raw security CLI output walls-of-text into clean, readable ANSI tables.
    """

    C_RESET = "\033[0m"
    C_BOLD = "\033[1m"
    C_RED = "\033[31m"
    C_GREEN = "\033[32m"
    C_YELLOW = "\033[33m"
    C_CYAN = "\033[36m"
    C_MAGENTA = "\033[35m"
    C_MUTED = "\033[90m"
    C_WHITE = "\033[37m"

    @classmethod
    def format_nmap(cls, raw_output: str) -> str:
        """Parse Nmap port table and reformat into an elegant ANSI table."""
        lines = raw_output.splitlines()
        port_lines: list[tuple[str, str, str, str]] = []

        in_ports = False
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("PORT") and "STATE" in line_str and "SERVICE" in line_str:
                in_ports = True
                continue
            if in_ports:
                if not line_str or line_str.startswith("Nmap done:") or line_str.startswith("Service Info:"):
                    break
                parts = line_str.split(None, 3)
                if len(parts) >= 3:
                    port = parts[0]
                    state = parts[1]
                    service = parts[2]
                    version = parts[3] if len(parts) > 3 else ""
                    port_lines.append((port, state, service, version))

        if not port_lines:
            return raw_output

        # Render styled table
        out: list[str] = [
            f"\n  {cls.C_BOLD}{cls.C_CYAN}╭── 🔍 NeuroShell Cyber: Discovered Ports & Services ─────────────────╮{cls.C_RESET}",
            f"  {cls.C_CYAN}│ {cls.C_BOLD}{'PORT':<12} {'STATE':<10} {'SERVICE':<15} {'VERSION':<25}{cls.C_CYAN}│{cls.C_RESET}",
            f"  {cls.C_CYAN}├──────────────────────────────────────────────────────────────────────┤{cls.C_RESET}",
        ]

        for port, state, service, version in port_lines:
            st_color = cls.C_GREEN if "open" in state else (cls.C_YELLOW if "filtered" in state else cls.C_RED)
            out.append(
                f"  {cls.C_CYAN}│ {cls.C_WHITE}{port:<12} {st_color}{state:<10}{cls.C_RESET} {cls.C_CYAN}{service:<15} {cls.C_MUTED}{version:<25}{cls.C_CYAN}│{cls.C_RESET}"
            )

        out.append(f"  {cls.C_CYAN}╰──────────────────────────────────────────────────────────────────────╯{cls.C_RESET}\n")
        return "\n".join(out)

    @classmethod
    def format_gobuster(cls, raw_output: str) -> str:
        """Parse Gobuster / FFuF output and format into a clean endpoint list."""
        lines = raw_output.splitlines()
        endpoints: list[tuple[str, str, str]] = []

        for line in lines:
            line_str = line.strip()
            # Match Gobuster format: /path (Status: 200) [Size: 1234]
            m = re.search(r"(\S+)\s+\(Status:\s*(\d+)\)(?:\s+\[Size:\s*(\d+)\])?", line_str)
            if m:
                endpoints.append((m.group(1), m.group(2), m.group(3) or "-"))

        if not endpoints:
            return raw_output

        out: list[str] = [
            f"\n  {cls.C_BOLD}{cls.C_MAGENTA}╭── 🌐 Discovered Web Endpoints ({len(endpoints)} Found) ─────────────────────╮{cls.C_RESET}",
            f"  {cls.C_MAGENTA}│ {cls.C_BOLD}{'STATUS':<10} {'ENDPOINT':<40} {'SIZE':<15}{cls.C_MAGENTA}│{cls.C_RESET}",
            f"  {cls.C_MAGENTA}├──────────────────────────────────────────────────────────────────────┤{cls.C_RESET}",
        ]

        for path, status, size in endpoints:
            st_color = cls.C_GREEN if status.startswith("2") else (cls.C_YELLOW if status.startswith("3") else cls.C_RED)
            out.append(
                f"  {cls.C_MAGENTA}│ {st_color}{status:<10}{cls.C_RESET} {cls.C_WHITE}{path:<40} {cls.C_MUTED}{size:<15}{cls.C_MAGENTA}│{cls.C_RESET}"
            )

        out.append(f"  {cls.C_MAGENTA}╰──────────────────────────────────────────────────────────────────────╯{cls.C_RESET}\n")
        return "\n".join(out)
