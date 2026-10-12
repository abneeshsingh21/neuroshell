"""
NeuroShell Cyber — Payloads package.
Provides multi-language reverse shell synthesis, web shells, and safe encoding utilities.
"""

from editions.cyber.payloads.generator import PayloadGenerator, PayloadResult
from editions.cyber.payloads.obfuscator import PayloadObfuscator
from editions.cyber.payloads.web_shells import WebShellGenerator

__all__ = [
    "PayloadGenerator",
    "PayloadResult",
    "PayloadObfuscator",
    "WebShellGenerator",
]
