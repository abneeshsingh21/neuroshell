"""
NeuroShell Cyber — Plain-English Security Patterns & Intent Translator.
Translates penetration testing intents (scans, fuzzing, payloads, listeners,
wordlists, and privesc) into precise tool commands.
"""

from __future__ import annotations

import re
from typing import Optional

CYBER_PATTERNS: dict[str, str] = {
    # ── Scope Management ──
    r"(?:scope\s+add|authorize\s+target|add\s+scope)\s+(\S+)": "scope add {0}",
    r"(?:scope\s+set|set\s+scope)\s+(\S+)": "scope set {0}",
    r"(?:scope\s+show|show\s+scope|view\s+scope|scope\s+status)": "scope show",
    r"(?:clear\s+scope|reset\s+scope)": "scope clear",

    # ── Payload Generation ──
    r"(?:create|generate|make)\s+(?:a\s+)?(?:reverse\s+shell|payload)\s+(?:for|in)\s+(\w+)(?:\s+(?:on|port)\s+(\d+))?": "payload {0} {1}",
    r"(?:create|generate|make)\s+(?:a\s+)?(\w+)\s+(?:reverse\s+shell|payload)(?:\s+(?:on|port)\s+(\d+))?": "payload {0} {1}",
    r"(?:create|generate|make)\s+(?:a\s+)?(\w+)\s+web\s*shell": "webshell {0}",

    # ── Staging & Hosting ──
    r"(?:host|serve|share)\s+(\S+)(?:\s+(?:on|port)\s+(\d+))?": "stage {0} {1}",
    r"(?:start|run)\s+(?:a\s+)?(?:web|http|staging)\s+server(?:\s+(?:on|port)\s+(\d+))?": "stage . {0}",

    # ── Listeners & Multi-Handlers ──
    r"(?:start|catch|listen)\s+(?:a\s+)?(?:reverse\s+shell\s+)?(?:listener|handler)(?:\s+(?:on|port)\s+(\d+))?": "listen {0}",
    r"(?:listen|catch)\s+(?:on\s+)?(?:port\s+)?(\d+)": "listen {0}",

    # ── Reconnaissance & Port Scanning ──
    r"(?:stealth\s+syn\s+scan|syn\s+scan)\s+(\S+)": "nmap -sS -Pn {0}",
    r"(?:aggressive|full)\s+scan\s+(\S+)": "nmap -A -p- -T4 {0}",
    r"(?:scan|detect)\s+(?:service\s+)?versions?\s+(?:on\s+)?(\S+)": "nmap -sV -sC {0}",
    r"(?:quick|fast)\s+scan\s+(\S+)": "nmap --top-ports 100 -T4 {0}",
    r"(?:scan\s+all\s+ports|full\s+port\s+scan)\s+(?:on\s+)?(\S+)": "nmap -p- -T4 {0}",

    # ── Web Fuzzing & Directory Bruteforce ──
    r"(?:fuzz|brute\s*force|find)\s+(?:web\s+)?directories\s+(?:on\s+)?(\S+)": "gobuster dir -u {0} -w /usr/share/wordlists/dirb/common.txt -b 404",
    r"(?:fuzz|bruteforce)\s+endpoints\s+(?:on\s+)?(\S+)": "ffuf -u {0}/FUZZ -w /usr/share/wordlists/dirb/common.txt -mc 200,301,302",

    # ── Vulnerability & Web Exploitation ──
    r"(?:test|scan)\s+(?:for\s+)?sql\s*injection\s+(?:on\s+)?(\S+)": "sqlmap -u \"{0}\" --batch --dbs",
    r"(?:run\s+)?nuclei\s+(?:scan\s+)?(?:on\s+)?(\S+)": "nuclei -u {0}",
    r"(?:scan\s+with\s+)?nikto\s+(?:on\s+)?(\S+)": "nikto -h {0}",

    # ── Password Cracking ──
    r"(?:crack\s+hash|crack\s+hashes)\s+(\S+)(?:\s+(?:with|using)\s+rockyou)?": "john --wordlist=/usr/share/wordlists/rockyou.txt {0}",
    r"(?:crack\s+sha256\s+hash)\s+(\S+)": "hashcat -m 1400 -a 0 {0} /usr/share/wordlists/rockyou.txt",
    r"(?:crack\s+ntlm\s+hash)\s+(\S+)": "hashcat -m 1000 -a 0 {0} /usr/share/wordlists/rockyou.txt",

    # ── Privilege Escalation ──
    r"(?:find|search\s+for)\s+suid\s+binaries": "find / -perm -4000 -type f -exec ls -la {} + 2>/dev/null",
    r"(?:find|check)\s+sudo\s+privileges": "sudo -l",
    r"(?:find|check)\s+internal\s+listening\s+ports": "ss -tulpn",

    # ── Information Gathering & Subdomain Enumeration ──
    r"(?:find|enumerate)\s+subdomains\s+(?:for|on)\s+(\S+)": "subfinder -d {0} || amass enum -d {0}",
    r"(?:masscan|fast\s+syn\s+scan)\s+(\S+)": "masscan -p1-65535 {0} --rate=1000",
    r"(?:whois|lookup\s+whois)\s+(?:for|on\s+)?(\S+)": "whois {0}",
    r"(?:lookup\s+dns|dns\s+lookup)\s+(?:for|on\s+)?(\S+)": "dig +short {0} ANY",

    # ── Vulnerability Search & CMS Assessment ──
    r"(?:search\s+exploits?\s+for|searchsploit)\s+(.+)": "searchsploit {0}",
    r"(?:scan|audit)\s+wordpress\s+(?:site\s+)?(?:on\s+)?(\S+)": "wpscan --url {0} --enumerate p,t,u",

    # ── Sniffing, Spoofing & Network Interception ──
    r"(?:sniff|capture)\s+packets?\s+(?:on\s+)?(\S+)": "tcpdump -i {0} -n",
    r"(?:start\s+responder\s+on)\s+(\S+)": "responder -I {0} -dwv",

    # ── Post-Exploitation & Active Directory ──
    r"(?:dump\s+hashes|secretsdump)\s+(?:from|on)\s+(\S+)": "impacket-secretsdump {0}",
    r"(?:kerberoast|get\s+user\s+spns)\s+(?:on|for)\s+(\S+)": "impacket-GetUserSPNs {0} -request",

    # ── Reporting & Engagement Documentation ──
    r"(?:generate|export|create)\s+(?:engagement\s+)?report": "/report",
    r"(?:export|dump)\s+targets?\s+(?:to\s+)?json": "/report json",
    r"(?:show|view|display)\s+(?:targets?|target\s+graph|topology)": "/target",
}


def translate_cyber_intent(user_input: str) -> str | None:
    """Match plain English cyber intents against parameterized patterns."""
    clean = user_input.strip()
    for pattern, template in CYBER_PATTERNS.items():
        m = re.match(pattern + "$", clean, re.IGNORECASE)
        if m:
            groups = [g for g in m.groups() if g is not None]
            if "{0}" in template and groups:
                if "{1}" in template and len(groups) > 1:
                    return template.format(groups[0], groups[1])
                return template.format(groups[0])
            return template
    return None
