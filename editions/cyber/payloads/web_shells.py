"""
NeuroShell Cyber — Web Shell Generator module.
Re-exports and provides convenient generation of web shells for authorized security testing.
"""

from __future__ import annotations

from dataclasses import dataclass

from editions.cyber.payloads.generator import PayloadGenerator


@dataclass
class WebShellResult:
    shell_type: str
    param: str
    raw_payload: str
    success: bool = True


class WebShellGenerator:
    """Convenience wrapper for generating web shell artifacts."""

    @staticmethod
    def generate_php(param: str = "cmd") -> WebShellResult:
        code = PayloadGenerator.generate_webshell("php", param=param)
        return WebShellResult(shell_type="php", param=param, raw_payload=code, success=True)

    @staticmethod
    def generate_jsp(param: str = "cmd") -> WebShellResult:
        code = PayloadGenerator.generate_webshell("jsp", param=param)
        return WebShellResult(shell_type="jsp", param=param, raw_payload=code, success=True)

    @staticmethod
    def generate_aspx(param: str = "cmd") -> WebShellResult:
        code = PayloadGenerator.generate_webshell("aspx", param=param)
        return WebShellResult(shell_type="aspx", param=param, raw_payload=code, success=True)
