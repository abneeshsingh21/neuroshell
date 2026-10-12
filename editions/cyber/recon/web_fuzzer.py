"""
NeuroShell Cyber — Web Application Fuzzer Runner.
Orchestrates Gobuster and FFuF web directory/file discovery through WSL Kali Bridge
or native Linux, enforcing ScopeGuard and recording discovered endpoints into TargetGraph.
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
class FuzzResult:
    target_url: str
    command: str
    success: bool
    returncode: int
    raw_stdout: str
    raw_stderr: str
    endpoints: list[dict[str, str]] = field(default_factory=list)
    formatted_output: str = ""
    error_message: Optional[str] = None


class WebFuzzer:
    """Orchestrates web directory and endpoint fuzzing with automated scope checks."""

    DEFAULT_WORDLISTS = [
        "/usr/share/wordlists/dirb/common.txt",
        "/usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt",
        "/usr/share/seclists/Discovery/Web-Content/common.txt",
    ]

    def __init__(
        self,
        scope_guard: Optional[ScopeGuard] = None,
        target_graph: Optional[TargetGraph] = None,
    ):
        self.scope_guard = scope_guard or ScopeGuard()
        self.target_graph = target_graph

    def fuzz_directories(
        self,
        target_url: str,
        wordlist: str | None = None,
        extensions: str = "php,html,txt,json",
        threads: int = 20,
        extra_flags: str = "",
        timeout_s: int = 180,
    ) -> FuzzResult:
        """
        Fuzz web directories using Gobuster or FFuF with automated scope validation.
        """
        # 1. Enforce Scope
        in_scope, reason = self.scope_guard.is_target_in_scope(target_url)
        if not in_scope:
            return FuzzResult(
                target_url=target_url,
                command="",
                success=False,
                returncode=-1,
                raw_stdout="",
                raw_stderr="",
                error_message=f"SCOPE VIOLATION: {reason}",
                formatted_output=f"\033[38;2;248;113;113m❌ Scope Violation: {reason}\033[0m",
            )

        wl = wordlist or self.DEFAULT_WORDLISTS[0]

        # 2. Prefer gobuster if available, else ffuf
        use_gobuster = WSLKaliBridge.check_tool_installed("gobuster")
        use_ffuf = WSLKaliBridge.check_tool_installed("ffuf")

        if use_gobuster:
            cmd = f"gobuster dir -u {target_url} -w {wl} -t {threads} -q"
            if extensions:
                cmd += f" -x {extensions}"
            if extra_flags:
                cmd += f" {extra_flags}"
        elif use_ffuf:
            u = target_url.rstrip("/") + "/FUZZ"
            cmd = f"ffuf -u {u} -w {wl} -t {threads} -s"
            if extra_flags:
                cmd += f" {extra_flags}"
        else:
            # Fallback representation
            cmd = f"gobuster dir -u {target_url} -w {wl} -t {threads} -q"

        # 3. Execute
        try:
            res = WSLKaliBridge.execute(cmd, timeout_s=timeout_s)
            stdout = res.stdout
            stderr = res.stderr
            rc = res.returncode
        except Exception as e:
            return FuzzResult(
                target_url=target_url,
                command=cmd,
                success=False,
                returncode=-1,
                raw_stdout="",
                raw_stderr=str(e),
                error_message=str(e),
                formatted_output=f"\033[38;2;248;113;113m❌ Execution failed: {e}\033[0m",
            )

        # 4. Parse endpoints
        endpoints: list[dict[str, str]] = []
        for line in stdout.splitlines():
            # Match gobuster: /admin (Status: 200) [Size: 1234]
            m = re.search(r"(/[\w\.\-\_/]+)\s+\(Status:\s*(\d+)\)(?:\s+\[Size:\s*(\d+)\])?", line)
            if m:
                path, status, size = m.groups()
                endpoints.append({"path": path, "status": status, "size": size or ""})
            else:
                # Match ffuf output: path [Status: 200, Size: 1234]
                m_f = re.search(r"(\S+)\s+\[Status:\s*(\d+)", line)
                if m_f:
                    p_f, s_f = m_f.groups()
                    endpoints.append({"path": "/" + p_f.lstrip("/"), "status": s_f, "size": ""})

        # 5. Persist to TargetGraph
        if self.target_graph and endpoints:
            # Extract host IP or domain from URL
            m_host = re.search(r"://([^/:]+)", target_url)
            host_key = m_host.group(1) if m_host else target_url
            for ep in endpoints:
                try:
                    self.target_graph.record_web_endpoint(
                        ip=host_key,
                        path=ep["path"],
                        status_code=int(ep["status"]) if ep["status"].isdigit() else 200,
                        method="GET",
                    )
                except Exception:
                    pass

        formatted = CyberFormatter.format_gobuster_scan(stdout, target=target_url)

        return FuzzResult(
            target_url=target_url,
            command=cmd,
            success=(rc == 0),
            returncode=rc,
            raw_stdout=stdout,
            raw_stderr=stderr,
            endpoints=endpoints,
            formatted_output=formatted,
        )
