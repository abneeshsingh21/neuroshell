"""
NeuroShell Cyber — Payload Obfuscator & Encoding Utilities.
Provides standard safe string transformations (Base64, Hex, URL encoding,
PowerShell UTF-16LE -EncodedCommand wrappers) for security assessment testing.
"""

from __future__ import annotations

import base64
import urllib.parse


class PayloadObfuscator:
    """Safe encoding and wrapper transformations for security commands and payloads."""

    @staticmethod
    def to_base64(text: str) -> str:
        """Encode UTF-8 string to standard Base64."""
        return base64.b64encode(text.encode("utf-8")).decode("ascii")

    @staticmethod
    def to_hex(text: str, prefix: str = "\\x") -> str:
        """Encode string to escaped hex format (e.g. \\x41\\x42)."""
        return "".join(f"{prefix}{b:02x}" for b in text.encode("utf-8"))

    @staticmethod
    def to_url_encoded(text: str, full: bool = False) -> str:
        """URL-encode string. If full is True, encodes all characters."""
        if full:
            return "".join(f"%{b:02x}" for b in text.encode("utf-8"))
        return urllib.parse.quote(text)

    @staticmethod
    def to_powershell_encoded_command(cmd: str) -> str:
        """
        Encode a command into PowerShell's UTF-16LE Base64 format
        for use with `powershell -NoP -NonI -W Hidden -Enc <BASE64>`.
        """
        utf16_bytes = cmd.encode("utf-16-le")
        b64 = base64.b64encode(utf16_bytes).decode("ascii")
        return f"powershell.exe -NoP -NonI -W Hidden -Exec Bypass -Enc {b64}"

    @staticmethod
    def to_bash_base64_wrap(cmd: str) -> str:
        """Encode bash command into `echo <b64> | base64 -d | bash` wrapper."""
        b64 = base64.b64encode(cmd.encode("utf-8")).decode("ascii")
        return f"echo {b64} | base64 -d | bash"

    @staticmethod
    def to_python_base64_wrap(code: str) -> str:
        """Encode python code into `python -c "import base64;exec(base64.b64decode('...'))"`."""
        b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
        return f'python3 -c "import base64;exec(base64.b64decode(\'{b64}\').decode())"'
