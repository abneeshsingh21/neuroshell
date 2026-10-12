"""
NeuroShell Cyber — Beautiful Output Formatter & Table Transformer.
Parses raw terminal text from Nmap, Gobuster, FFuF, Nuclei, SQLmap, Hashcat, and Nikto,
and renders aligned ANSI tables, colored vulnerability cards, and Plain-English Smart Errors.
"""

from __future__ import annotations

import re


class CyberFormatter:
    """
    Transforms raw security CLI output walls-of-text into clean, readable ANSI tables
    and Plain-English actionable error explanations.
    """

    C_RESET = "\033[0m"
    C_BOLD = "\033[1m"
    C_RED = "\033[38;2;239;68;68m"
    C_ORANGE = "\033[38;2;249;115;22m"
    C_YELLOW = "\033[38;2;234;179;8m"
    C_GREEN = "\033[38;2;34;197;94m"
    C_CYAN = "\033[38;2;6;182;212m"
    C_BLUE = "\033[38;2;59;130;246m"
    C_MAGENTA = "\033[38;2;168;85;247m"
    C_MUTED = "\033[38;2;148;163;184m"
    C_WHITE = "\033[38;2;248;250;252m"
    C_BG_DARK = "\033[48;2;15;23;42m"

    @classmethod
    def auto_format(cls, command: str, raw_output: str) -> str:
        """
        Auto-detect the appropriate tool from command or output signature
        and return the structured, formatted table.
        """
        if not raw_output or not raw_output.strip():
            return raw_output

        cmd_lower = command.lower().strip()
        out_lower = raw_output.lower()

        # 1. Public External IP lookup (ipify, icanhazip, ifconfig.me)
        if "ipify" in cmd_lower or "ifconfig.me" in cmd_lower or "icanhazip" in cmd_lower:
            formatted = cls.format_public_ip(raw_output)
            if formatted != raw_output:
                return formatted

        # 2. Network & Device Discovery (arp -a, ip neigh, arp-scan, nmap -sn)
        if "arp" in cmd_lower or "neigh" in cmd_lower or "-sn" in cmd_lower or "interface:" in out_lower:
            formatted = cls.format_network_discovery(raw_output, command)
            if formatted != raw_output:
                return formatted

        # 3. Single external IP string detector
        single_ip = raw_output.strip()
        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", single_ip):
            formatted = cls.format_public_ip(raw_output)
            if formatted != raw_output:
                return formatted

        # 4. Nmap port & service scans
        if "nmap" in cmd_lower or ("port" in out_lower and "state" in out_lower and "service" in out_lower):
            formatted = cls.format_nmap(raw_output)
            if formatted != raw_output:
                return formatted

        # 5. Gobuster / FFuF directory & parameter fuzzing
        if "gobuster" in cmd_lower or "ffuf" in cmd_lower or "(status:" in out_lower:
            formatted = cls.format_gobuster(raw_output)
            if formatted != raw_output:
                return formatted

        # 6. Nuclei vulnerability scans
        if "nuclei" in cmd_lower or ("[cve-" in out_lower or "[critical]" in out_lower or "[high]" in out_lower):
            formatted = cls.format_nuclei(raw_output)
            if formatted != raw_output:
                return formatted

        # 7. SQLmap automated injection
        if "sqlmap" in cmd_lower or ("parameter:" in out_lower and "type:" in out_lower):
            formatted = cls.format_sqlmap(raw_output)
            if formatted != raw_output:
                return formatted

        # 8. Hashcat / John password cracking
        if "hashcat" in cmd_lower or "john" in cmd_lower or "recovered" in out_lower:
            formatted = cls.format_hashcat(raw_output)
            if formatted != raw_output:
                return formatted

        # 9. Nikto web scanner
        if "nikto" in cmd_lower or "osvdb" in out_lower:
            formatted = cls.format_nikto(raw_output)
            if formatted != raw_output:
                return formatted

        # 10. Universal Kali tool formatter fallback (wpscan, hydra, searchsploit, etc.)
        formatted = cls.format_kali_generic(raw_output, command)
        if formatted != raw_output:
            return formatted

        return raw_output

    @classmethod
    def format_nmap(cls, raw_output: str) -> str:
        """Parse Nmap port table and reformat into an elegant ANSI table."""
        lines = raw_output.splitlines()
        port_lines: list[tuple[str, str, str, str]] = []

        in_ports = False
        target_host = "Target"
        for line in lines:
            line_str = line.strip()
            if "Nmap scan report for" in line_str:
                target_host = line_str.replace("Nmap scan report for", "").strip()
            if line_str.startswith("PORT") and "STATE" in line_str and "SERVICE" in line_str:
                in_ports = True
                continue
            if in_ports:
                if not line_str or line_str.startswith("Nmap done:") or line_str.startswith("Service Info:") or line_str.startswith("MAC Address:"):
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

        out: list[str] = [
            f"\n  {cls.C_BOLD}{cls.C_CYAN}╭── 🔍 Discovered Ports & Services ({target_host}) ──────────────────╮{cls.C_RESET}",
            f"  {cls.C_CYAN}│ {cls.C_BOLD}{'PORT':<12} {'STATE':<10} {'SERVICE':<15} {'VERSION':<25}{cls.C_CYAN}│{cls.C_RESET}",
            f"  {cls.C_CYAN}├──────────────────────────────────────────────────────────────────────┤{cls.C_RESET}",
        ]

        for port, state, service, version in port_lines:
            st_color = cls.C_GREEN if "open" in state.lower() else (cls.C_YELLOW if "filtered" in state.lower() else cls.C_RED)
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
            # Gobuster: /path (Status: 200) [Size: 1234]
            m = re.search(r"(\S+)\s+\(Status:\s*(\d+)\)(?:\s+\[Size:\s*(\d+)\])?", line_str)
            if m:
                endpoints.append((m.group(1), m.group(2), m.group(3) or "-"))
                continue
            # FFuF format: path [Status: 200, Size: 1234, ...]
            m2 = re.search(r"(\S+)\s+\[Status:\s*(\d+),\s*Size:\s*(\d+)", line_str)
            if m2:
                endpoints.append((m2.group(1), m2.group(2), m2.group(3) or "-"))

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

    @classmethod
    def format_nuclei(cls, raw_output: str) -> str:
        """Parse Nuclei vulnerability scanner output into a structured findings table."""
        lines = raw_output.splitlines()
        findings: list[tuple[str, str, str, str]] = []

        # Nuclei standard output: [cve-2021-44228] [http] [critical] https://target.com [extra]
        pattern = re.compile(r"\[([^\]]+)\]\s+\[([^\]]+)\]\s+\[([^\]]+)\]\s+(\S+)")

        for line in lines:
            line_str = line.strip()
            # Strip ANSI color codes from raw input for clean parsing
            clean = re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", line_str)
            m = pattern.search(clean)
            if m:
                vuln_id = m.group(1)
                protocol = m.group(2)
                severity = m.group(3).upper()
                target_url = m.group(4)
                findings.append((vuln_id, protocol, severity, target_url))

        if not findings:
            return raw_output

        out: list[str] = [
            f"\n  {cls.C_BOLD}{cls.C_RED}╭── 🛡️ Nuclei Vulnerability Assessment ({len(findings)} Findings) ───────────────╮{cls.C_RESET}",
            f"  {cls.C_RED}│ {cls.C_BOLD}{'SEVERITY':<12} {'TEMPLATE / CVE':<24} {'PROTO':<8} {'TARGET URL':<22}{cls.C_RED}│{cls.C_RESET}",
            f"  {cls.C_RED}├──────────────────────────────────────────────────────────────────────┤{cls.C_RESET}",
        ]

        for vuln_id, proto, sev, url in findings:
            if "CRITICAL" in sev:
                sev_color = cls.C_RED
            elif "HIGH" in sev:
                sev_color = cls.C_ORANGE
            elif "MEDIUM" in sev:
                sev_color = cls.C_YELLOW
            elif "LOW" in sev:
                sev_color = cls.C_BLUE
            else:
                sev_color = cls.C_MUTED

            short_url = url if len(url) <= 22 else url[:19] + "..."
            short_id = vuln_id if len(vuln_id) <= 24 else vuln_id[:21] + "..."

            out.append(
                f"  {cls.C_RED}│ {sev_color}{sev:<12}{cls.C_RESET} {cls.C_WHITE}{short_id:<24} {cls.C_CYAN}{proto:<8} {cls.C_MUTED}{short_url:<22}{cls.C_RED}│{cls.C_RESET}"
            )

        out.append(f"  {cls.C_RED}╰──────────────────────────────────────────────────────────────────────╯{cls.C_RESET}\n")
        return "\n".join(out)

    @classmethod
    def format_sqlmap(cls, raw_output: str) -> str:
        """Parse SQLmap injection parameters and DBMS backend into a clean summary card."""
        lines = raw_output.splitlines()
        parameter = ""
        inj_type = ""
        dbms = ""
        payload = ""

        for line in lines:
            line_str = line.strip()
            if "Parameter:" in line_str:
                parameter = line_str.replace("Parameter:", "").strip()
            elif "Type:" in line_str and not inj_type:
                inj_type = line_str.replace("Type:", "").strip()
            elif "Title:" in line_str and not inj_type:
                inj_type = line_str.replace("Title:", "").strip()
            elif "Payload:" in line_str and not payload:
                payload = line_str.replace("Payload:", "").strip()
            elif "back-end DBMS:" in line_str:
                dbms = line_str.replace("back-end DBMS:", "").strip()

        if not parameter and not dbms:
            return raw_output

        out: list[str] = [
            f"\n  {cls.C_BOLD}{cls.C_YELLOW}╭── 💉 SQL Injection Verification (SQLmap) ───────────────────────────╮{cls.C_RESET}",
            f"  {cls.C_YELLOW}│ {cls.C_BOLD}{'PARAMETER:':<16} {cls.C_WHITE}{parameter:<50}{cls.C_YELLOW}│{cls.C_RESET}",
            f"  {cls.C_YELLOW}│ {cls.C_BOLD}{'DBMS BACKEND:':<16} {cls.C_GREEN}{dbms or 'Identified':<50}{cls.C_YELLOW}│{cls.C_RESET}",
            f"  {cls.C_YELLOW}│ {cls.C_BOLD}{'INJECTION TYPE:':<16} {cls.C_CYAN}{inj_type or 'Boolean-based blind / Error-based':<50}{cls.C_YELLOW}│{cls.C_RESET}",
        ]
        if payload:
            short_pay = payload if len(payload) <= 48 else payload[:45] + "..."
            out.append(f"  {cls.C_YELLOW}│ {cls.C_BOLD}{'PAYLOAD:':<16} {cls.C_MUTED}{short_pay:<50}{cls.C_YELLOW}│{cls.C_RESET}")

        out.append(f"  {cls.C_YELLOW}╰──────────────────────────────────────────────────────────────────────╯{cls.C_RESET}\n")
        return "\n".join(out)

    @classmethod
    def format_hashcat(cls, raw_output: str) -> str:
        """Parse Hashcat or John cracked hashes into an aligned credential table."""
        lines = raw_output.splitlines()
        cracked: list[tuple[str, str]] = []

        for line in lines:
            line_str = line.strip()
            if ":" in line_str and not line_str.startswith("Hash.Mode") and not line_str.startswith("Time."):
                parts = line_str.split(":", 1)
                # Filter out status messages
                if len(parts[0]) >= 8 and len(parts[1]) > 0 and not parts[0].startswith("http"):
                    cracked.append((parts[0], parts[1]))

        if not cracked:
            return raw_output

        out: list[str] = [
            f"\n  {cls.C_BOLD}{cls.C_GREEN}╭── 🔓 Recovered Credentials ({len(cracked)} Cracked) ───────────────────────╮{cls.C_RESET}",
            f"  {cls.C_GREEN}│ {cls.C_BOLD}{'HASH':<42} {'PLAINTEXT PASSWORD':<24}{cls.C_GREEN}│{cls.C_RESET}",
            f"  {cls.C_GREEN}├──────────────────────────────────────────────────────────────────────┤{cls.C_RESET}",
        ]

        for h, pw in cracked:
            short_h = h if len(h) <= 40 else h[:37] + "..."
            out.append(
                f"  {cls.C_GREEN}│ {cls.C_MUTED}{short_h:<42} {cls.C_BOLD}{cls.C_WHITE}{pw:<24}{cls.C_GREEN}│{cls.C_RESET}"
            )

        out.append(f"  {cls.C_GREEN}╰──────────────────────────────────────────────────────────────────────╯{cls.C_RESET}\n")
        return "\n".join(out)

    @classmethod
    def format_nikto(cls, raw_output: str) -> str:
        """Parse Nikto web server scan findings into a structured issue list."""
        lines = raw_output.splitlines()
        items: list[tuple[str, str]] = []

        for line in lines:
            line_str = line.strip()
            if line_str.startswith("+") and ":" in line_str:
                content = line_str.lstrip("+ ").strip()
                m = re.match(r"(OSVDB-\d+|[A-Z0-9_-]+)?:\s*(.+)", content)
                if m:
                    ref = m.group(1) or "VULN"
                    desc = m.group(2)
                    items.append((ref, desc))
                else:
                    items.append(("INFO", content))

        if not items:
            return raw_output

        out: list[str] = [
            f"\n  {cls.C_BOLD}{cls.C_CYAN}╭── 🌐 Nikto Web Security Findings ({len(items)} Items) ──────────────────╮{cls.C_RESET}",
            f"  {cls.C_CYAN}│ {cls.C_BOLD}{'REFERENCE':<14} {'DESCRIPTION':<52}{cls.C_CYAN}│{cls.C_RESET}",
            f"  {cls.C_CYAN}├──────────────────────────────────────────────────────────────────────┤{cls.C_RESET}",
        ]

        for ref, desc in items[:25]:  # Top 25
            short_desc = desc if len(desc) <= 50 else desc[:47] + "..."
            out.append(
                f"  {cls.C_CYAN}│ {cls.C_YELLOW}{ref:<14}{cls.C_RESET} {cls.C_WHITE}{short_desc:<52}{cls.C_CYAN}│{cls.C_RESET}"
            )

        out.append(f"  {cls.C_CYAN}╰──────────────────────────────────────────────────────────────────────╯{cls.C_RESET}\n")
        return "\n".join(out)

    @classmethod
    def format_smart_error(cls, command: str, error_text: str, exit_code: int = 1) -> str:
        """
        Translates raw execution errors and stack traces into an aligned,
        Plain-English diagnosis card with root cause and actionable fix command.
        """
        err_lower = (error_text or "").lower()

        # Default fallback diagnosis
        diagnosis = "The command exited with a non-zero exit code."
        root_cause = "Subprocess failure."
        suggestion = "Review the command flags and target parameters."
        fix_cmd = ""

        # Common Cyber & System Error Signatures
        if "blocking our ping probes" in err_lower or "host seems down" in err_lower:
            diagnosis = "Target host firewall is dropping ICMP ping probes."
            root_cause = "Host firewall or IDS/IPS packet filter active."
            suggestion = "Bypass ICMP ping check by adding the -Pn flag."
            fix_cmd = f"{command} -Pn" if "-Pn" not in command else command
        elif "429 too many requests" in err_lower or "waf" in err_lower:
            diagnosis = "Web Application Firewall (WAF) or server rate limit triggered."
            root_cause = "Request rate threshold exceeded (Cloudflare/Akamai/ModSecurity)."
            suggestion = "Throttle request speed and add inter-request delay."
            fix_cmd = f"{command} --delay 200ms" if "--delay" not in command else command
        elif "permission denied" in err_lower or "operation not permitted" in err_lower:
            diagnosis = "Insufficient administrative permissions to execute raw socket or privileged action."
            root_cause = "Requires root or administrative elevation (CAP_NET_RAW / sudo)."
            suggestion = "Execute the operation with elevated privileges."
            fix_cmd = f"sudo {command}" if not command.startswith("sudo") else command
        elif "address already in use" in err_lower or "bind failed" in err_lower:
            diagnosis = "The requested local port is already occupied by another running process."
            root_cause = "Socket port collision."
            suggestion = "Identify and terminate the existing listener or select a different port."
            fix_cmd = "fuser -k <port>/tcp"
        elif "connection refused" in err_lower:
            diagnosis = "The target server actively rejected the TCP connection."
            root_cause = "Target service is not running or port is closed on the target host."
            suggestion = "Verify target IP and confirm the service port is open via Nmap."
            fix_cmd = "nmap -sS -p- <target>"
        elif "no route to host" in err_lower or "network is unreachable" in err_lower:
            diagnosis = "Network route to the target IP address does not exist."
            root_cause = "Routing table misconfiguration or target IP is unreachable."
            suggestion = "Verify default gateway and network connectivity."
            fix_cmd = "ping -c 3 8.8.8.8"
        elif "out of memory" in err_lower or "cuda out of memory" in err_lower:
            diagnosis = "System or GPU memory allocation exhausted."
            root_cause = "Insufficient VRAM or system RAM."
            suggestion = "Reduce batch size or use CPU offloading / INT8 quantization."
            fix_cmd = "export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True"
        elif "command not found" in err_lower or "not recognized as an internal or external command" in err_lower:
            pkg = error_text.split(":")[0].strip() if ":" in error_text else (command.split()[0] if command else "tool")
            diagnosis = f"Binary '{pkg}' is not installed on PATH or in WSL."
            root_cause = "Missing dependency package in active environment."
            suggestion = f"Install the package via system package manager or WSL Kali."
            fix_cmd = f"wsl -d kali-linux sudo apt update && wsl -d kali-linux sudo apt install -y {pkg}"

        out: list[str] = [
            f"\n  {cls.C_BOLD}{cls.C_RED}╭── ❌ Smart Error Diagnosis (Exit Code {exit_code}) ────────────────────────╮{cls.C_RESET}",
            f"  {cls.C_RED}│ {cls.C_BOLD}{'DIAGNOSIS:':<14} {cls.C_WHITE}{diagnosis:<52}{cls.C_RED}│{cls.C_RESET}",
            f"  {cls.C_RED}│ {cls.C_BOLD}{'ROOT CAUSE:':<14} {cls.C_MUTED}{root_cause:<52}{cls.C_RED}│{cls.C_RESET}",
            f"  {cls.C_RED}│ {cls.C_BOLD}{'SOLUTION:':<14} {cls.C_CYAN}{suggestion:<52}{cls.C_RED}│{cls.C_RESET}",
        ]
        if fix_cmd:
            out.append(f"  {cls.C_RED}│ {cls.C_BOLD}{'FIX COMMAND:':<14} {cls.C_BOLD}{cls.C_GREEN}{fix_cmd:<52}{cls.C_RED}│{cls.C_RESET}")

        out.append(f"  {cls.C_RED}╰──────────────────────────────────────────────────────────────────────╯{cls.C_RESET}\n")
        return "\n".join(out)

    @classmethod
    def format_public_ip(cls, raw_output: str) -> str:
        """Parse and explain public WAN IP output so the user knows whose IP it is."""
        clean = raw_output.strip()
        m = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", clean)
        if not m:
            return raw_output
        ip = m.group(1)

        out: list[str] = [
            f"\n  {cls.C_BOLD}{cls.C_CYAN}╭── 🌐 Public External WAN IP Address ───────────────────────────────╮{cls.C_RESET}",
            f"  {cls.C_CYAN}│ {cls.C_BOLD}{'PUBLIC IP:':<16} {cls.C_BOLD}{cls.C_GREEN}{ip:<50}{cls.C_CYAN}│{cls.C_RESET}",
            f"  {cls.C_CYAN}│ {cls.C_BOLD}{'ASSIGNED BY:':<16} {cls.C_WHITE}{'Your Internet Service Provider (ISP / WAN Gateway)':<50}{cls.C_CYAN}│{cls.C_RESET}",
            f"  {cls.C_CYAN}│ {cls.C_BOLD}{'VISIBILITY:':<16} {cls.C_YELLOW}{'Public Internet (Visible to remote websites & servers)':<50}{cls.C_CYAN}│{cls.C_RESET}",
            f"  {cls.C_CYAN}│ {cls.C_BOLD}{'SCOPE NOTE:':<16} {cls.C_MUTED}{'This is NOT a local Wi-Fi device or private subnet IP':<50}{cls.C_CYAN}│{cls.C_RESET}",
            f"  {cls.C_CYAN}╰────────────────────────────────────────────────────────────────────╯{cls.C_RESET}\n",
        ]
        return "\n".join(out)

    @classmethod
    def format_network_discovery(cls, raw_output: str, command: str = "") -> str:
        """
        Parse ARP tables, IP neighbor lists, and Nmap subnet sweeps into a crystal-clear,
        aligned inventory distinguishing your host, the Wi-Fi router, and other devices.
        """
        lines = raw_output.splitlines()
        interface_ip = ""
        entries: list[dict] = []

        # 1. Regex patterns for various OS discovery tools
        # Windows arp -a: "Interface: 192.168.29.110 --- 0xc"
        # "  192.168.29.1          70-97-41-e0-98-66     dynamic"
        # Linux ip neigh: "192.168.29.1 dev eth0 lladdr 70:97:41:e0:98:66 REACHABLE"
        # Nmap -sn: "Nmap scan report for 192.168.29.1" / "MAC Address: 70:97:41:E0:98:66 (Vendor)"

        cur_ip = ""
        cur_mac = ""

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Detect Windows interface banner
            if "interface:" in line_str.lower():
                m_if = re.search(r"interface:\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line_str, re.IGNORECASE)
                if m_if:
                    interface_ip = m_if.group(1)
                continue

            # Check Nmap report
            if "nmap scan report for" in line_str.lower():
                m_nmap = re.search(r"for\s+(?:(\S+)\s+\()?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\)?", line_str, re.IGNORECASE)
                if m_nmap:
                    cur_ip = m_nmap.group(2)
                continue
            if "mac address:" in line_str.lower() and cur_ip:
                m_mac = re.search(r"([0-9a-fA-F:]{17})\s*(?:\((.*?)\))?", line_str)
                if m_mac:
                    entries.append({
                        "ip": cur_ip,
                        "mac": m_mac.group(1),
                        "type": m_mac.group(2) or "dynamic",
                    })
                    cur_ip = ""
                continue

            # Check Linux ip neigh
            m_neigh = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+dev\s+\S+\s+lladdr\s+([0-9a-fA-F:-]{17})\s+(\w+)", line_str)
            if m_neigh:
                entries.append({
                    "ip": m_neigh.group(1),
                    "mac": m_neigh.group(2),
                    "type": m_neigh.group(3).lower(),
                })
                continue

            # Check Windows ARP table line
            m_arp = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+([0-9a-fA-F:-]{17})\s+(\w+)", line_str)
            if m_arp:
                entries.append({
                    "ip": m_arp.group(1),
                    "mac": m_arp.group(2),
                    "type": m_arp.group(3).lower(),
                })
                continue

        if not entries:
            return raw_output

        # Role classifier
        peer_count = 0
        formatted_rows: list[str] = []

        # If interface_ip not found in output, inspect local address from first subnet
        first_ip = entries[0]["ip"]
        subnet_prefix = ".".join(first_ip.split(".")[:3]) + "." if first_ip else ""

        for item in entries:
            ip = item["ip"]
            mac = item["mac"].replace("-", ":").upper()
            typ = item["type"]

            # Classify device role
            is_broadcast = (
                ip.endswith(".255")
                or ip == "255.255.255.255"
                or ip.startswith("224.")
                or ip.startswith("239.")
                or mac == "FF:FF:FF:FF:FF:FF"
            )
            is_gateway = ip.endswith(".1") or (subnet_prefix and ip == subnet_prefix + "1")
            is_me = (ip == interface_ip) if interface_ip else False

            if is_me:
                role = "🖥️  THIS MACHINE (Your Device)"
                role_col = cls.C_CYAN
            elif is_gateway:
                role = "📶 WI-FI ROUTER / GATEWAY"
                role_col = cls.C_GREEN
            elif is_broadcast:
                role = "📡 BROADCAST / MULTICAST"
                role_col = cls.C_MUTED
            else:
                peer_count += 1
                role = f"📱 CONNECTED DEVICE (Peer #{peer_count})"
                role_col = cls.C_YELLOW

            # Vendor heuristic from OUI
            vendor = ""
            if mac.startswith("00:15:5D"):
                vendor = "[Hyper-V / WSL2]"
            elif mac.startswith("F0:18:98") or mac.startswith("AC:DE:48"):
                vendor = "[Apple]"
            elif mac.startswith("B8:27:EB") or mac.startswith("DC:A6:32"):
                vendor = "[Raspberry Pi]"
            elif typ and typ not in ("dynamic", "static"):
                vendor = f"[{typ[:14]}]"

            role_str = f"{role} {cls.C_MUTED}{vendor}".strip()
            formatted_rows.append(
                f"  {cls.C_CYAN}│ {cls.C_WHITE}{ip:<17} {cls.C_MUTED}{mac:<19} {role_col}{role_str:<30}{cls.C_CYAN}│{cls.C_RESET}"
            )

        if_hdr = f"Interface: {interface_ip}" if interface_ip else "Local Broadcast Domain"
        subnet_hdr = f"Subnet: {subnet_prefix}0/24" if subnet_prefix else "Local Network"

        out: list[str] = [
            f"\n  {cls.C_BOLD}{cls.C_CYAN}╭── 📡 Local Wi-Fi & Network Device Inventory ────────────────────────╮{cls.C_RESET}",
            f"  {cls.C_CYAN}│ {cls.C_BOLD}{if_hdr:<32} {subnet_hdr:<36}{cls.C_CYAN}│{cls.C_RESET}",
            f"  {cls.C_CYAN}├──────────────────────────────────────────────────────────────────────┤{cls.C_RESET}",
            f"  {cls.C_CYAN}│ {cls.C_BOLD}{'IP ADDRESS':<17} {'MAC ADDRESS':<19} {'ROLE / IDENTIFICATION':<30}{cls.C_CYAN}│{cls.C_RESET}",
            f"  {cls.C_CYAN}├──────────────────────────────────────────────────────────────────────┤{cls.C_RESET}",
        ]
        out.extend(formatted_rows)
        out.append(f"  {cls.C_CYAN}╰──────────────────────────────────────────────────────────────────────╯{cls.C_RESET}")
        out.append(f"  {cls.C_BOLD}{cls.C_GREEN}✔ Found {peer_count} other active device(s) on your Wi-Fi network.{cls.C_RESET}\n")
        return "\n".join(out)

    @classmethod
    def format_kali_generic(cls, raw_output: str, command: str = "") -> str:
        """
        Universal fallback formatter for all Kali / security command-line outputs.
        Extracts status markers ([+], [*], [-], [!], vulnerabilities, targets).
        """
        lines = raw_output.splitlines()
        findings: list[tuple[str, str]] = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Standard Kali CLI prefixes: [+] found, [*] status, [!] warning, [-] failed
            if line_str.startswith("[+]"):
                findings.append(("SUCCESS", line_str[3:].strip()))
            elif line_str.startswith("[*]"):
                findings.append(("INFO", line_str[3:].strip()))
            elif line_str.startswith("[!]"):
                findings.append(("ALERT", line_str[3:].strip()))
            elif line_str.startswith("[-]"):
                findings.append(("FAILURE", line_str[3:].strip()))
            elif "vulnerable" in line_str.lower() or "cve-" in line_str.lower():
                findings.append(("ALERT", line_str))

        if len(findings) < 2:
            return raw_output

        tool_name = command.split()[0].upper() if command else "SECURITY TOOL"
        out: list[str] = [
            f"\n  {cls.C_BOLD}{cls.C_MAGENTA}╭── 🛡️ {tool_name} Structured Execution Output ──────────────────────╮{cls.C_RESET}",
            f"  {cls.C_MAGENTA}│ {cls.C_BOLD}{'STATUS':<12} {'DETAILS':<56}{cls.C_MAGENTA}│{cls.C_RESET}",
            f"  {cls.C_MAGENTA}├──────────────────────────────────────────────────────────────────────┤{cls.C_RESET}",
        ]

        for status, detail in findings[:30]:
            col = cls.C_GREEN if status == "SUCCESS" else (cls.C_RED if status == "ALERT" else (cls.C_YELLOW if status == "FAILURE" else cls.C_CYAN))
            short_det = detail if len(detail) <= 54 else detail[:51] + "..."
            out.append(f"  {cls.C_MAGENTA}│ {col}{status:<12}{cls.C_RESET} {cls.C_WHITE}{short_det:<56}{cls.C_MAGENTA}│{cls.C_RESET}")

        out.append(f"  {cls.C_MAGENTA}╰──────────────────────────────────────────────────────────────────────╯{cls.C_RESET}\n")
        return "\n".join(out)
