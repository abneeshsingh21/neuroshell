# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
"""
NeuroShell Zero-Trust Corporate Policy & RBAC Engine.
Enforces role-based command allowlisting/denylisting, confirmation guardrails,
and SOC2 compliance rules across enterprise deployments.
"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class UserRole(str, Enum):
    ADMIN = "admin"
    DEVOPS = "devops"
    DEVELOPER = "developer"
    CONTRACTOR = "contractor"
    GUEST = "guest"


@dataclass
class PolicyDecision:
    allowed: bool
    requires_confirmation: bool = False
    reason: str = ""
    matched_rule: str = ""


class PolicyEngine:
    """Zero-Trust Policy Evaluator for Enterprise Command Guardrails."""

    def __init__(self, role: UserRole = UserRole.DEVELOPER, policy_config: Optional[Dict[str, Any]] = None):
        self.role = role
        self.policy_config = policy_config or self._default_policy()

    @classmethod
    def from_config_file(cls, path: str | Path) -> "PolicyEngine":
        """Load policy from TOML or JSON file."""
        p = Path(path)
        if not p.exists():
            return cls()
        
        try:
            import toml
            data = toml.load(str(p))
            role_str = data.get("enterprise", {}).get("user_role", "developer")
            role = UserRole(role_str) if role_str in UserRole._value2member_map_ else UserRole.DEVELOPER
            return cls(role=role, policy_config=data)
        except Exception:
            return cls()

    def _default_policy(self) -> Dict[str, Any]:
        return {
            "enterprise": {
                "organization": "Default Organization",
                "enforce_rbac": True,
                "user_role": self.role.value
            },
            "guardrails": {
                "admin": {
                    "blocked_patterns": [r"^\s*format\s+[a-z]:", r"^\s*mkfs\."],
                    "require_confirmation": [r"rm\s+-rf\s+/", r"del\s+/f\s+/s\s+C:\\"]
                },
                "devops": {
                    "blocked_patterns": [r"^\s*format\s+[a-z]:", r"^\s*mkfs\."],
                    "require_confirmation": [r"kubectl\s+delete\s+namespace", r"terraform\s+destroy", r"git\s+push\s+.*--force"]
                },
                "developer": {
                    "blocked_patterns": [
                        r"terraform\s+destroy",
                        r"kubectl\s+delete\s+namespace",
                        r"drop\s+database",
                        r"^\s*format\s+[a-z]:"
                    ],
                    "require_confirmation": [
                        r"docker\s+system\s+prune",
                        r"git\s+push\s+.*--force",
                        r"npm\s+publish"
                    ]
                },
                "contractor": {
                    "blocked_patterns": [
                        r"terraform",
                        r"kubectl",
                        r"aws\s+s3\s+rm",
                        r"git\s+push\s+.*--force",
                        r"drop\s+database"
                    ],
                    "require_confirmation": [
                        r"git\s+push",
                        r"npm\s+install",
                        r"pip\s+install"
                    ]
                }
            }
        }

    def evaluate(self, command: str, user_role: Optional[UserRole] = None) -> PolicyDecision:
        """Evaluate command against corporate guardrails."""
        role = user_role or self.role
        role_rules = self.policy_config.get("guardrails", {}).get(role.value, {})
        
        blocked = role_rules.get("blocked_patterns", [])
        for pat in blocked:
            if re.search(pat, command, re.IGNORECASE):
                return PolicyDecision(
                    allowed=False,
                    requires_confirmation=False,
                    reason=f"Command is BLOCKED for role '{role.value}' by corporate security policy.",
                    matched_rule=pat
                )

        confirm = role_rules.get("require_confirmation", [])
        for pat in confirm:
            if re.search(pat, command, re.IGNORECASE):
                return PolicyDecision(
                    allowed=True,
                    requires_confirmation=True,
                    reason=f"Operation requires explicit confirmation under role '{role.value}'.",
                    matched_rule=pat
                )

        return PolicyDecision(allowed=True, requires_confirmation=False, reason="Compliant with Zero-Trust policy.")
