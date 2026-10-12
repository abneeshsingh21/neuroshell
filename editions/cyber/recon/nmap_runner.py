"""
NeuroShell Cyber — Nmap Reconnaissance Runner.
Executes network port and service discovery through WSL Kali Bridge or native Linux,
validating against the Engagement Scope Guard and recording entities into TargetGraph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from editions.cyber.cyber_formatter import CyberFormatter
from editions.cyber.scope_guard import ScopeGuard
from editions.cyber.target_graph import TargetGraph
from editions.cyber.wsl_bridge import WSLKaliBridge


@dataclass
class NmapScanResult:
    target: str
    command: str
    success: bool
    returncode: int
    raw_stdout: str
    raw_stderr: str
    open_ports: list[dict[str, str]] = field(default_factory=list)
    formatted_output: str = ""
    error_message: Optional[str] = None


class NmapRunner:
    """Orchestrates Nmap scanning with automated scope enforcement and target graph storage."""

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
        ports: str = "common",
        stealth: bool = False,
        service_version: bool = True,
        scripts: bool = False,
        extra_flags: str = "",
        timeout_s: int = 180,
    ) -> NmapScanResult:
        """
        Execute an Nmap scan against target.
        Enforces scope validation before executing any network packets.
        """
        # 1. Enforce Scope
        in_scope, reason = self.scope_guard.is_target_in_scope(target)
        if not in_scope:
            return NmapScanResult(
                target=target,
                command="",
                success=False,
                returncode=-1,
                raw_stdout="",
                raw_stderr="",
                error_message=f"SCOPE VIOLATION: {reason}",
                formatted_output=f"\033[38;2;248;113;113m❌ Scope Violation: {reason}\033[0m",
            )

        # 2. Build Nmap command
        cmd_parts = ["nmap"]
        if stealth:
            cmd_parts.append("-sS")
        if service_version:
            cmd_parts.append("-sV")
        if scripts:
            cmd_parts.append("-sC")

        if ports == "all":
            cmd_parts.append("-p-")
        elif ports == "top100":
            cmd_parts.append("--top-ports 100")
        elif ports == "top1000" or ports == "common":
            cmd_parts.append("--top-ports 1000")
        elif ports:
            cmd_parts.append(f"-p {ports}")

        if extra_flags:
            cmd_parts.append(extra_flags)

        cmd_parts.append(target)
        full_command = " ".join(cmd_parts)

        # 3. Execute via WSL Kali Bridge or native Linux
        try:
            res = WSLKaliBridge.execute(full_command, as_root=stealth, timeout_s=timeout_s)
            stdout = res.stdout
            stderr = res.stderr
            rc = res.returncode
        except Exception as e:
            return NmapScanResult(
                target=target,
                command=full_command,
                success=False,
                returncode=-1,
                raw_stdout="",
                raw_stderr=str(e),
                error_message=str(e),
                formatted_output=f"\033[38;2;248;113;113m❌ Execution failed: {e}\033[0m",
            )

        # 4. Parse open ports & services
        open_ports: list[dict[str, str]] = []
        for line in stdout.splitlines():
            m = re.match(r"^(\d+)/(tcp|udp)\s+(\w+)\s+([\w\.\-]+)(?:\s+(.*))?", line.strip())
            if m:
                p_num, p_proto, p_state, p_svc, p_ver = m.groups()
                if p_state.lower() == "open":
                    open_ports.append({
                        "port": p_num,
                        "protocol": p_proto,
                        "state": p_state,
                        "service": p_svc,
                        "version": (p_ver or "").strip(),
                    })

        # 5. Persist to TargetGraph if available
        if self.target_graph and open_ports:
            try:
                self.target_graph.record_host(
                    ip=target,
                    status="up",
                    notes=f"Scanned via Nmap ({len(open_ports)} open ports)",
                )
                for item in open_ports:
                    self.target_graph.record_port_service(
                        ip=target,
                        port=int(item["port"]),
                        protocol=item["protocol"],
                        state=item["state"],
                        service=item["service"],
                        version=item["version"],
                    )
            except Exception:
                pass

        formatted = CyberFormatter.format_nmap_scan(stdout, target=target)

        return NmapScanResult(
            target=target,
            command=full_command,
            success=(rc == 0),
            returncode=rc,
            raw_stdout=stdout,
            raw_stderr=stderr,
            open_ports=open_ports,
            formatted_output=formatted,
        )
