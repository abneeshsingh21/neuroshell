"""
NeuroShell Cyber — Engagement Scope Guard.
Prevents accidental scans or attacks against out-of-scope, unauthorized,
or public production targets. Ensures ethical, legal, and responsible operation.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from typing import Set
from urllib.parse import urlparse


@dataclass
class EngagementScope:
    allowed_cidrs: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = field(default_factory=list)
    allowed_ips: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = field(default_factory=set)
    allowed_domains: set[str] = field(default_factory=set)
    strict_mode: bool = True
    enabled: bool = True

    def __post_init__(self):
        # Localhost is always safe by default for local testing
        try:
            self.allowed_ips.add(ipaddress.ip_address("127.0.0.1"))
            self.allowed_ips.add(ipaddress.ip_address("::1"))
            self.allowed_cidrs.append(ipaddress.ip_network("127.0.0.0/8"))
        except Exception:
            pass


class ScopeGuard:
    """
    Validates engagement targets before tool execution.
    Acts as an ethical and legal guardrail.
    """

    _scope: EngagementScope = EngagementScope()

    # Regex patterns for detecting target IPs, URLs, and domains inside commands
    _IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b")
    _URL_PATTERN = re.compile(r"https?://[^\s\"'>]+")
    _DOMAIN_PATTERN = re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b")

    # Command tools that actively target remote hosts
    _TARGETED_TOOLS = {
        "nmap", "masscan", "gobuster", "ffuf", "dirb", "dirsearch",
        "sqlmap", "hydra", "medusa", "nikto", "nuclei", "wpscan",
        "commix", "arpspoof", "bettercap", "responder", "crackmapexec",
        "netexec", "impacket", "msfconsole", "smbclient", "rpcclient"
    }

    @classmethod
    def get_scope(cls) -> EngagementScope:
        return cls._scope

    @classmethod
    def set_enabled(cls, enabled: bool) -> None:
        cls._scope.enabled = enabled

    @classmethod
    def set_strict(cls, strict: bool) -> None:
        cls._scope.strict_mode = strict

    @classmethod
    def add_target(cls, target: str) -> bool:
        """Add an IP, CIDR, or domain to authorized engagement scope."""
        target = target.strip().lower()
        if not target:
            return False

        # 1. Try CIDR notation
        if "/" in target:
            try:
                net = ipaddress.ip_network(target, strict=False)
                cls._scope.allowed_cidrs.append(net)
                return True
            except ValueError:
                pass

        # 2. Try single IP
        try:
            ip = ipaddress.ip_address(target)
            cls._scope.allowed_ips.add(ip)
            return True
        except ValueError:
            pass

        # 3. Domain or hostname
        # Remove URL scheme if user pasted full URL
        if target.startswith("http://") or target.startswith("https://"):
            parsed = urlparse(target)
            target = parsed.netloc.split(":")[0]

        if cls._DOMAIN_PATTERN.match(target) or target in ("localhost", "target.local", "target.htb", "target.thm"):
            cls._scope.allowed_domains.add(target)
            return True

        return False

    @classmethod
    def remove_target(cls, target: str) -> bool:
        target = target.strip().lower()
        # Remove from domains
        if target in cls._scope.allowed_domains:
            cls._scope.allowed_domains.remove(target)
            return True

        # Remove from IPs
        try:
            ip = ipaddress.ip_address(target)
            if ip in cls._scope.allowed_ips:
                cls._scope.allowed_ips.remove(ip)
                return True
        except ValueError:
            pass

        # Remove from CIDRs
        try:
            net = ipaddress.ip_network(target, strict=False)
            if net in cls._scope.allowed_cidrs:
                cls._scope.allowed_cidrs.remove(net)
                return True
        except ValueError:
            pass

        return False

    @classmethod
    def clear_scope(cls) -> None:
        """Reset scope to default localhost only."""
        cls._scope = EngagementScope()

    @classmethod
    def is_in_scope(cls, target: str) -> bool:
        """Check if an IP or host is within authorized scope."""
        target = target.strip().lower()
        if not target or target == "localhost":
            return True

        # Check domain list
        if target in cls._scope.allowed_domains:
            return True

        # Check subdomains (e.g. *.target.com)
        for dom in cls._scope.allowed_domains:
            if dom.startswith("*.") and target.endswith(dom[1:]):
                return True
            if target.endswith("." + dom):
                return True

        # Check single IP
        try:
            ip = ipaddress.ip_address(target)
            if ip in cls._scope.allowed_ips:
                return True
            for cidr in cls._scope.allowed_cidrs:
                if ip in cidr:
                    return True
        except ValueError:
            pass

        return False

    @classmethod
    def extract_targets(cls, command: str) -> list[str]:
        """Extract candidate target hosts and IPs from a command line."""
        found: set[str] = set()

        # Extract URLs first
        for url in cls._URL_PATTERN.findall(command):
            try:
                host = urlparse(url).netloc.split(":")[0]
                if host:
                    found.add(host)
            except Exception:
                pass

        # Extract raw IPs
        for ip_match in cls._IP_PATTERN.findall(command):
            # Exclude netmasks or port-like segments
            found.add(ip_match.split("/")[0])

        # Extract domains
        words = command.split()
        for w in words:
            clean = w.strip("'\";,()[]{}")
            if clean in ("localhost", "target.htb", "target.thm"):
                found.add(clean)
            elif cls._DOMAIN_PATTERN.match(clean) and not clean.endswith((".py", ".sh", ".txt", ".exe", ".xml", ".json", ".conf")):
                found.add(clean)

        return list(found)

    @classmethod
    def validate_command(cls, command: str) -> tuple[bool, str]:
        """
        Validate whether a command targets authorized systems.
        Returns:
            (is_safe, message)
        """
        if not cls._scope.enabled:
            return True, "Scope guard disabled"

        # Check if the command uses any targeted offensive tool
        words = command.lower().split()
        tool_used = any(t in words or any(w.endswith("/" + t) for w in words) for t in cls._TARGETED_TOOLS)

        # If no scope defined other than localhost, and strict mode is on, warn
        has_custom_targets = bool(cls._scope.allowed_domains or (len(cls._scope.allowed_ips) > 2) or (len(cls._scope.allowed_cidrs) > 1))

        targets = cls.extract_targets(command)
        if not targets:
            # No specific host extracted (e.g. "hashcat -m 0 hash.txt")
            return True, "No remote host targeted"

        out_of_scope: list[str] = []
        for tgt in targets:
            if not cls.is_in_scope(tgt):
                out_of_scope.append(tgt)

        if out_of_scope:
            if not has_custom_targets and not cls._scope.strict_mode:
                return True, f"Warning: No explicit scope defined. Target: {', '.join(out_of_scope)}"

            return False, (
                f"[!] SCOPE GUARD VIOLATION: Target(s) {', '.join(out_of_scope)} are NOT in your "
                f"authorized engagement scope. Use 'scope add <target>' to authorize."
            )

        return True, "All targets verified in scope"
