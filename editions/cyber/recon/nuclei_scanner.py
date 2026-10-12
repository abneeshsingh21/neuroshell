"""
NeuroShell Cyber — Nuclei Vulnerability Scanner Runner.
Orchestrates Nuclei template-based security auditing through WSL Kali Bridge or native Linux,
validating against ScopeGuard and recording vulnerabilities in TargetGraph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from editions.cyber.scope_guard import ScopeGuard
from editions.cyber.target_graph import TargetGraph
from editions.cyber.wsl_bridge import WSLKaliBridge


@dataclass
class NucleiFinding:
    template_id: str
    protocol: str
    severity: str
    target_url: str
    extracted_info: str = ""


@dataclass
class NucleiScanResult:
    target: str
    command: str
    success: bool
    returncode: int
    raw_stdout: str
    raw_stderr: str
    findings: list[NucleiFinding] = field(default_factory=list)
    formatted_output: str = ""
    error_message: Optional[str] = None


class NucleiScanner:
    """Orchestrates Nuclei vulnerability template scanning."""

    def __init__(
        self,
        scope_guard: Optional[ScopeGuard] = None,
        target_graph: Optional[TargetGraph] = None,
    ):
        self.scope_guard = scope_guard or ScopeGuard()
        self.target_graph = target_graph

    def scan(
        self,
        target: str,
        tags: str = "cve,misconfig,exposure",
        severity: str = "critical,high,medium",
        extra_flags: str = "",
        timeout_s: int = 300,
    ) -> NucleiScanResult:
        """Execute Nuclei vulnerability scan with automated scope enforcement."""
        # 1. Enforce Scope
        in_scope, reason = self.scope_guard.is_target_in_scope(target)
        if not in_scope:
            return NucleiScanResult(
                target=target,
                command="",
                success=False,
                returncode=-1,
                raw_stdout="",
                raw_stderr="",
                error_message=f"SCOPE VIOLATION: {reason}",
                formatted_output=f"\033[38;2;248;113;113m❌ Scope Violation: {reason}\033[0m",
            )

        cmd_parts = ["nuclei", "-u", target]
        if tags:
            cmd_parts.extend(["-tags", tags])
        if severity:
            cmd_parts.extend(["-severity", severity])
        if extra_flags:
            cmd_parts.append(extra_flags)

        cmd = " ".join(cmd_parts)

        # 2. Execute
        try:
            res = WSLKaliBridge.execute(cmd, timeout_s=timeout_s)
            stdout = res.stdout
            stderr = res.stderr
            rc = res.returncode
        except Exception as e:
            return NucleiScanResult(
                target=target,
                command=cmd,
                success=False,
                returncode=-1,
                raw_stdout="",
                raw_stderr=str(e),
                error_message=str(e),
                formatted_output=f"\033[38;2;248;113;113m❌ Execution failed: {e}\033[0m",
            )

        # 3. Parse findings
        # Format example: [cve-2023-xxxx] [http] [critical] https://target.com/path
        findings: list[NucleiFinding] = []
        for line in stdout.splitlines():
            m = re.match(r"^\[([\w\.\-]+)\]\s+\[([\w\-]+)\]\s+\[([\w\-]+)\]\s+(\S+)(?:\s+(.*))?", line.strip())
            if m:
                t_id, proto, sev, t_url, extra = m.groups()
                finding = NucleiFinding(
                    template_id=t_id,
                    protocol=proto,
                    severity=sev.lower(),
                    target_url=t_url,
                    extracted_info=(extra or "").strip(),
                )
                findings.append(finding)

                # Persist to TargetGraph
                if self.target_graph:
                    try:
                        m_host = re.search(r"://([^/:]+)", target)
                        host_key = m_host.group(1) if m_host else target
                        self.target_graph.record_finding(
                            ip=host_key,
                            finding_type=f"CVE / {sev.upper()}",
                            severity=sev.lower(),
                            title=t_id,
                            description=f"Nuclei match [{proto}]: {t_url} {extra or ''}".strip(),
                        )
                    except Exception:
                        pass

        # 4. Format ANSI display
        lines = [
            f"\033[38;2;74;222;128m╭── 🛡️ Nuclei Vulnerability Scan: \033[1m\033[38;2;241;245;249m{target}\033[0m\033[38;2;74;222;128m ───────────────────────╮\033[0m",
            f"\033[38;2;74;222;128m│ \033[1m\033[38;2;241;245;249m{'SEVERITY':<12} {'TEMPLATE ID':<25} {'PROTOCOL':<10} {'TARGET':<25}\033[0m\033[38;2;74;222;128m│\033[0m",
            f"\033[38;2;74;222;128m├─────────────────────────────────────────────────────────────────────────────┤\033[0m",
        ]

        sev_colors = {
            "critical": "\033[48;2;239;68;68;38;2;255;255;255m CRITICAL \033[0m",
            "high": "\033[38;2;248;113;113mHIGH     \033[0m",
            "medium": "\033[38;2;251;191;36mMEDIUM   \033[0m",
            "low": "\033[38;2;56;189;248mLOW      \033[0m",
            "info": "\033[38;2;100;116;139mINFO     \033[0m",
        }

        if findings:
            for f in findings:
                sev_badge = sev_colors.get(f.severity, f"{f.severity.upper():<9}")
                lines.append(
                    f"\033[38;2;74;222;128m│\033[0m {sev_badge} {f.template_id:<25} {f.protocol:<10} {f.target_url[:25]:<25} \033[38;2;74;222;128m│\033[0m"
                )
        else:
            lines.append(f"\033[38;2;74;222;128m│\033[0m \033[38;2;74;222;128m✔ No vulnerability templates triggered for {target}\033[0m")

        lines.append(f"\033[38;2;74;222;128m╰─────────────────────────────────────────────────────────────────────────────╯\033[0m")
        formatted = "\n".join(lines)

        return NucleiScanResult(
            target=target,
            command=cmd,
            success=(rc == 0),
            returncode=rc,
            raw_stdout=stdout,
            raw_stderr=stderr,
            findings=findings,
            formatted_output=formatted,
        )
