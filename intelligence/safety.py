# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Safety Checker — Production Grade
Four-layer safety: pattern matching → chain analysis → scope estimation → LLM audit.
Includes audit logging, whitelisting, dry-run simulation, and impact estimation.
"""

import re
import os
import time
import json
import csv
import hashlib
import platform
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from observability.provenance import ProvenanceTag, ProvenanceSource


# ═══════════════════════════════════════════════════════════
# Enums & Data Models
# ═══════════════════════════════════════════════════════════

class RiskLevel(Enum):
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    DANGER = "DANGER"
    BLOCKED = "BLOCKED"


@dataclass
class AffectedScope:
    """Estimated scope of impact."""
    files: list[str] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    estimated_file_count: int = 0
    recursive: bool = False
    system_wide: bool = False

    @property
    def summary(self) -> str:
        parts = []
        if self.files:
            parts.append(f"{len(self.files)} file(s)")
        if self.directories:
            parts.append(f"{len(self.directories)} dir(s)")
        if self.services:
            parts.append(f"{len(self.services)} service(s)")
        if self.recursive:
            parts.append("RECURSIVE")
        if self.system_wide:
            parts.append("SYSTEM-WIDE")
        return ", ".join(parts) if parts else "minimal"


@dataclass
class SafetyResult:
    """Comprehensive safety analysis result."""
    risk_level: RiskLevel
    reason: str
    affected: AffectedScope = field(default_factory=AffectedScope)
    is_reversible: bool = True
    needs_confirmation: bool = False
    badge: str = ""
    chain_risks: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    dry_run_available: bool = False
    dry_run_command: str = ""
    audit_id: str = ""

    _BADGE_MAP = {
        RiskLevel.SAFE: "✅ SAFE",
        RiskLevel.CAUTION: "⚠️ CAUTION",
        RiskLevel.DANGER: "⛔ DANGER",
        RiskLevel.BLOCKED: "🚫 BLOCKED",
    }

    def __post_init__(self):
        self.badge = self._BADGE_MAP.get(self.risk_level, "")

    def _refresh_badge(self):
        """Recompute badge after risk_level mutation (e.g. policy escalation)."""
        self.badge = self._BADGE_MAP.get(self.risk_level, "")

    @property
    def should_block(self) -> bool:
        return self.risk_level == RiskLevel.BLOCKED


@dataclass
class AuditEntry:
    """An entry in the audit log."""
    timestamp: float
    command: str
    risk_level: str
    reason: str
    user_action: str = ""  # approved, rejected, modified
    scope_summary: str = ""
    prev_hash: str = ""
    entry_hash: str = ""


# ═══════════════════════════════════════════════════════════
# Safety Checker — Production Engine
# ═══════════════════════════════════════════════════════════

class SafetyChecker:
    """
    Production-grade four-layer safety system.

    Features:
    - Layer 1: Instant pattern matching for known dangerous commands
    - Layer 2: Chain analysis for piped/sequential commands
    - Layer 3: Scope estimation (affected files, directories, services)
    - Layer 4: LLM analysis for ambiguous commands
    - Audit logging for all safety decisions
    - Command whitelist for pre-approved commands
    - Dry-run suggestion for destructive commands
    - Impact estimation with recursive detection
    """

    MAX_AUDIT_LOG = 1000
    VALID_PROFILES = {"dev", "staging", "production"}
    VALID_ROLES = {"admin", "developer", "operator", "viewer"}
    HIGH_IMPACT_MARKERS = [
        "terraform", "kubectl", "systemctl", "service ", "drop database",
        "drop table", "truncate table", "iptables", "docker system prune", "format ",
    ]

    # ── Layer 1: BLOCKED Patterns (never allow without override) ──

    BLOCKED_PATTERNS = [
        (r"rm\s+-rf\s+/\s*$", "Recursive delete of root filesystem"),
        (r"rm\s+-rf\s+~\s*$", "Recursive delete of home directory"),
        (r"rm\s+-rf\s+\$HOME\b", "Recursive delete of user home directory"),
        (r"rm\s+-rf\s+/(?:etc|usr|var|bin|sbin|lib|lib64|opt|boot|root|System|Library|Volumes)(?:/|\s*$)", "Recursive delete of critical OS directory"),
        (r"rm\s+-rf\s+/\s", "Recursive delete from root path"),
        (r"rm\s+-rf\s+\*\s*$", "Recursive delete of all files"),
        (r"format\s+[a-zA-Z]:", "Disk format command"),
        (r"del\s+/[sS]\s+/[qQ]\s+[cC]:\\", "Recursive quiet delete of C drive"),
        (r"mkfs\.", "Filesystem format"),
        (r"dd\s+if=.+of=/dev/", "Raw disk write"),
        (r">\s*/dev/sda", "Write to raw disk"),
        (r":\(\)\{\s*:\|:\s*&\s*\};:", "Fork bomb"),
        (r"chmod\s+-R\s+777\s+/\s*$", "Recursive chmod 777 on root"),
        (r"chown\s+-R\s+.+\s+/\s*$", "Recursive chown on root"),
        # ChatML / Prompt Injection Special Tokens
        (r"<\|(?:im_start|im_end|begin_of_text|end_of_text)\|>", "ChatML model prompt injection detected"),
        (r"\[INST\]|\[/INST\]|<<SYS>>", "LLM control template injection detected"),
        # Pipe-to-interpreter: cover all common shells and language runtimes.
        (r"curl\s+.+\|\s*(?:ba|z|k|fi|c|pw)?sh\b", "Piped remote script execution"),
        (r"wget\s+.+\|\s*(?:ba|z|k|fi|c|pw)?sh\b", "Piped remote script execution"),
        (r"curl\s+.+\|\s*(?:python|python3|node|perl|ruby|php|lua)\b", "Piped remote code to interpreter"),
        (r"wget\s+.+\|\s*(?:python|python3|node|perl|ruby|php|lua)\b", "Piped remote code to interpreter"),
        (r"\beval\s+[\"']?\$\(\s*(?:curl|wget|fetch)\b", "Remote code evaluation"),
        (r"/dev/null\s*>\s*/etc/", "Overwrite system config"),
        (r"iptables\s+-F", "Flush all firewall rules"),
        (r"systemctl\s+disable\s+firewalld", "Disable firewall"),
    ]

    # ── Layer 1: DANGER Patterns (heavy confirmation) ──

    DANGER_PATTERNS = [
        (r"rm\s+-rf\s+", "Recursive force delete"),
        (r"rm\s+-r\s+", "Recursive delete"),
        (r"del\s+/[sS]\s+", "Recursive delete (Windows)"),
        (r"git\s+reset\s+--hard", "Hard git reset — data loss risk"),
        (r"git\s+push\s+--force", "Force push — remote history rewrite"),
        (r"git\s+push\s+-f\s+", "Force push — remote history rewrite"),
        (r"git\s+clean\s+-fd", "Git clean – removes untracked files"),
        (r"drop\s+database\b", "Database drop — permanent data loss"),
        (r"drop\s+table\b", "Table drop — permanent data loss"),
        (r"truncate\s+table\b", "Table truncation — data loss"),
        (r"DELETE\s+FROM\s+\w+\s*$", "Unbounded DELETE — no WHERE clause"),
        (r"UPDATE\s+\w+\s+SET\s+.+$", "Unbounded UPDATE — no WHERE clause"),
        (r"docker\s+system\s+prune\s+-a", "Remove ALL Docker data"),
        (r"docker\s+rm\s+-f", "Force remove running containers"),
        (r"kubectl\s+delete\s+--all", "Delete all Kubernetes resources"),
        (r"terraform\s+destroy", "Terraform destroy — infrastructure teardown"),
        (r"npm\s+publish", "npm publish to registry"),
        (r"systemctl\s+stop\s+", "Stop a system service"),
    ]

    # ── Layer 1: CAUTION Patterns (confirmation if configured) ──

    CAUTION_PATTERNS = [
        (r"\brm\s+", "File deletion"),
        (r"\bdel\s+", "File deletion"),
        (r"\brmdir\s+", "Directory deletion"),
        (r"Remove-Item\b", "File deletion (PowerShell)"),
        (r"\bchmod\b", "Permission change"),
        (r"\bchown\b", "Ownership change"),
        (r"\bsudo\b", "Elevated privileges"),
        (r"\bkill\s+", "Process termination"),
        (r"\bkill\s+-9\b", "Force kill process"),
        (r"\bshutdown\b", "System shutdown"),
        (r"\breboot\b", "System reboot"),
        (r"\breg\s+delete\b", "Registry deletion"),
        (r"\bstop-service\b", "Service stop (PowerShell)"),
        (r"pip\s+install\b", "Package installation"),
        (r"npm\s+install\s+-g\b", "Global package installation"),
        (r"\bgit\s+stash\s+drop\b", "Stash drop"),
        (r"\bgit\s+branch\s+-[dD]\b", "Branch deletion"),
        (r"\btar\s+.*--delete\b", "Archive deletion"),
        (r"\biptables\b", "Firewall modification"),
        (r"\bnetsh\b", "Network configuration"),
        # Match output-overwrite redirection: a single `>` (not `>>`, not `&>`,
        # not numeric fd-redirect like `2>`) followed by a file path token.
        # Skips stderr-merges (`2>&1`) and append (`>>`).
        (r"(?<![>&0-9])>(?!>)\s*[^\s&|]+", "File overwrite (redirect)"),
        (r"\|\s*tee\s+", "File overwrite via tee"),
    ]

    # Dry-run equivalents
    DRY_RUN_MAP = {
        "rm": "rm -i",
        "rmdir": "rmdir -p",
        "git push": "git push --dry-run",
        "git clean": "git clean -n",
        "terraform apply": "terraform plan",
        "terraform destroy": "terraform plan -destroy",
        "docker system prune": "docker system prune --dry-run",
        "kubectl delete": "kubectl delete --dry-run=client",
        "kubectl apply": "kubectl apply --dry-run=client",
        "rsync": "rsync --dry-run",
    }

    def __init__(self, config, llm_client=None):
        self.config = getattr(config, 'safety', config)
        self.llm = llm_client
        self._audit_log: list[AuditEntry] = []
        self._last_audit_hash = ""
        self._whitelist: set[str] = set()
        self._policy_profile = self._normalize_profile(
            os.environ.get("NEUROSHELL_POLICY_PROFILE", getattr(self.config, "policy_profile", "dev"))
        )
        self._user_role = self._normalize_role(
            os.environ.get("NEUROSHELL_USER_ROLE", getattr(self.config, "user_role", "developer"))
        )

    # ═══════════════════════════════════════════════════════
    # Main API
    # ═══════════════════════════════════════════════════════

    def _normalize_for_safety(self, command: str) -> str:
        """Strip obfuscation quotes, backslashes, and normalize flags for AST safety checking."""
        if not command:
            return ""
        norm = command.strip()
        # Strip internal empty quotes: d""el -> del, r'm' -> rm
        norm = re.sub(r"['\"]{2,}", "", norm)
        norm = re.sub(r"(?<=\w)['\"](?=\w)", "", norm)
        # Normalize escaped characters: \r\m -> rm
        norm = re.sub(r"\\([a-zA-Z0-9])", r"\1", norm)
        # Normalize rm flag permutations: rm -fr -> rm -rf, rm -r -f -> rm -rf
        norm = re.sub(r"\brm\s+-fr\b", "rm -rf", norm)
        norm = re.sub(r"\brm\s+-r\s+-f\b", "rm -rf", norm)
        norm = re.sub(r"\brm\s+-f\s+-r\b", "rm -rf", norm)
        # Normalize root wildcards: rm -rf /* -> rm -rf /
        norm = re.sub(r"\brm\s+-rf\s+/\*\s*$", "rm -rf /", norm)
        # Normalize windows del flags: del /q /s -> del /s /q
        norm = re.sub(r"\bdel\s+/[qQ]\s+/[sS]\b", "del /s /q", norm)
        return norm

    def check(self, command: str) -> SafetyResult:
        """Run comprehensive four-layer safety check."""
        if not self.config.enabled:
            return SafetyResult(risk_level=RiskLevel.SAFE, reason="Safety disabled")

        # Whitelist bypass
        cmd_normalized = command.strip().lower()
        if cmd_normalized in self._whitelist:
            return SafetyResult(risk_level=RiskLevel.SAFE, reason="Whitelisted command")

        norm_cmd = self._normalize_for_safety(command)
        cmds_to_test = [command] if norm_cmd == command else [command, norm_cmd]

        # Layer 1: BLOCKED patterns
        for c in cmds_to_test:
            for pattern, reason in self.BLOCKED_PATTERNS:
                if re.search(pattern, c, re.IGNORECASE):
                    result = SafetyResult(
                        risk_level=RiskLevel.BLOCKED,
                        reason=f"🚫 BLOCKED: {reason}",
                        is_reversible=False,
                        needs_confirmation=True,
                        affected=self._estimate_scope(command),
                    )
                    result = self._apply_policy_overrides(command, result)
                    self._log_audit(command, result)
                    return result

        # Layer 2: Chain analysis (pipes, &&, ;)
        chain_risks = self._analyze_chain(command)

        # Layer 1 continued: DANGER patterns
        for pattern, reason in self.DANGER_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                scope = self._estimate_scope(command)
                dry_run = self._suggest_dry_run(command)
                suggestions = self._suggest_safer(command)

                result = SafetyResult(
                    risk_level=RiskLevel.DANGER,
                    reason=f"⛔ {reason}",
                    affected=scope,
                    is_reversible=False,
                    needs_confirmation=True,
                    chain_risks=chain_risks,
                    suggestions=suggestions,
                    dry_run_available=bool(dry_run),
                    dry_run_command=dry_run,
                )
                result = self._apply_policy_overrides(command, result)
                self._log_audit(command, result)
                return result

        # Layer 1 continued: CAUTION patterns
        caution_reasons = []
        for pattern, reason in self.CAUTION_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                caution_reasons.append(reason)

        if caution_reasons or chain_risks:
            scope = self._estimate_scope(command)
            dry_run = self._suggest_dry_run(command)
            all_reasons = caution_reasons + chain_risks

            is_irreversible = any(
                r in caution_reasons for r in [
                    "Force kill process", "Branch deletion", "Stash drop"
                ]
            )

            result = SafetyResult(
                risk_level=RiskLevel.CAUTION,
                reason=f"⚠️ {'; '.join(all_reasons[:4])}",
                affected=scope,
                is_reversible=not is_irreversible,
                needs_confirmation=self.config.confirm_destructive,
                chain_risks=chain_risks,
                dry_run_available=bool(dry_run),
                dry_run_command=dry_run,
            )
            result = self._apply_policy_overrides(command, result)
            self._log_audit(command, result)
            return result

        # Layer 4: LLM analysis for ambiguous commands
        if self.llm and self._is_ambiguous(command):
            result = self._llm_safety_check(command)
            result = self._apply_policy_overrides(command, result)
            self._log_audit(command, result)
            return result

        result = SafetyResult(
            risk_level=RiskLevel.SAFE,
            reason="✅ No risks detected",
        )
        result = self._apply_policy_overrides(command, result)
        return result

    def check_batch(self, commands: list[str]) -> list[SafetyResult]:
        """Check multiple commands. Returns results in same order."""
        return [self.check(cmd) for cmd in commands]

    # ═══════════════════════════════════════════════════════
    # Layer 2: Chain Analysis
    # ═══════════════════════════════════════════════════════

    def _analyze_chain(self, command: str) -> list[str]:
        """Analyze piped and chained commands for hidden risks."""
        risks = []

        # Split by pipes, &&, ;
        segments = re.split(r'\||\&\&|;', command)
        if len(segments) <= 1:
            return risks

        for i, segment in enumerate(segments):
            seg = segment.strip()

            # Piped execution
            if i > 0 and re.search(r'\b(sh|bash|zsh|pwsh|python|node|eval)\b', seg):
                risks.append(f"Segment {i+1} executes piped input: '{seg[:40]}'")

            # Piped to file overwrite
            if i > 0 and re.search(r'>\s*/', seg):
                risks.append(f"Segment {i+1} redirects to system path")

            # Variable expansion in middle of chain
            if "$(" in seg or "`" in seg:
                risks.append(f"Segment {i+1} contains command substitution")

            # xargs with destructive commands
            if "xargs" in seg and any(d in seg for d in ["rm", "del", "kill"]):
                risks.append(f"Segment {i+1} uses xargs with destructive command")

        return risks

    # ═══════════════════════════════════════════════════════
    # Layer 3: Scope Estimation
    # ═══════════════════════════════════════════════════════

    def _estimate_scope(self, command: str) -> AffectedScope:
        """Estimate the scope of impact."""
        scope = AffectedScope()

        # Detect recursion flags
        scope.recursive = bool(re.search(r'\s-[rR]f?\s|\s--recursive\s|\s/[sS]\s', command))

        # Detect system-wide operations
        system_markers = [
            "/etc", "/usr", "/var", "/bin", "/sbin", "/lib", "/opt", "/boot",
            "/root", "/System", "/Library", "/Volumes", "C:\\Windows", "HKLM\\", "/dev/"
        ]
        scope.system_wide = any(m in command for m in system_markers)

        # Extract affected paths
        parts = command.split()
        for part in parts[1:]:
            if part.startswith("-"):
                continue
            if "/" in part or "\\" in part or "." in part:
                part_clean = part.rstrip(";").rstrip("&")
                if os.path.isdir(part_clean):
                    scope.directories.append(part_clean)
                    if scope.recursive:
                        try:
                            count = 0
                            for _ in Path(part_clean).rglob("*"):
                                count += 1
                                if count >= 1000:
                                    break
                            scope.estimated_file_count += count
                        except (PermissionError, OSError):
                            scope.estimated_file_count += 100  # estimate
                elif os.path.isfile(part_clean):
                    scope.files.append(part_clean)
                    scope.estimated_file_count += 1
                else:
                    # Might be a glob or non-existent path
                    scope.files.append(part_clean)

        # Detect service names
        service_patterns = [
            (r"systemctl\s+\w+\s+(\S+)", 1),
            (r"service\s+(\S+)\s+", 1),
            (r"docker\s+(stop|rm|restart)\s+(\S+)", 2),
            (r"kubectl\s+delete\s+\w+\s+(\S+)", 1),
        ]
        for pattern, group in service_patterns:
            match = re.search(pattern, command)
            if match:
                scope.services.append(match.group(group))

        return scope

    # ═══════════════════════════════════════════════════════
    # Dry-run & Safer Alternatives
    # ═══════════════════════════════════════════════════════

    def _suggest_dry_run(self, command: str) -> str:
        """Suggest a dry-run equivalent."""
        for cmd_prefix, dry_cmd in self.DRY_RUN_MAP.items():
            if command.strip().startswith(cmd_prefix):
                return command.replace(cmd_prefix, dry_cmd, 1)
        return ""

    def _suggest_safer(self, command: str) -> list[str]:
        """Suggest safer alternatives."""
        suggestions = []

        if "rm -rf" in command:
            # Suggest trash instead
            suggestions.append(f"Use trash-cli: trash-put {command.split()[-1]}")
            suggestions.append("Add -i for interactive confirmation: " + command.replace("-rf", "-ri"))

        if "git push --force" in command or "git push -f" in command:
            suggestions.append("Use --force-with-lease for safer force push")

        if "git reset --hard" in command:
            suggestions.append("Consider git stash first to preserve changes")
            suggestions.append("Use git reset --soft or --mixed for reversible reset")

        if re.search(r"DELETE\s+FROM\s+\w+\s*$", command, re.IGNORECASE):
            suggestions.append("Add a WHERE clause to limit scope")
            suggestions.append("Run SELECT first to verify matching rows")

        if "docker system prune -a" in command:
            suggestions.append("Run without -a to keep tagged images")

        if "chmod 777" in command:
            suggestions.append("Use more restrictive permissions like 755 or 644")

        return suggestions

    # ═══════════════════════════════════════════════════════
    # Layer 4: LLM Analysis
    # ═══════════════════════════════════════════════════════

    def _is_ambiguous(self, command: str) -> bool:
        """Check if command needs LLM analysis."""
        if "|" in command and len(command) > 50:
            return True
        if "$(" in command or "`" in command:
            return True
        if command.count(";") > 2:
            return True
        if re.search(r"\beval\b", command):
            return True
        return False

    def _llm_safety_check(self, command: str) -> SafetyResult:
        """Use LLM for ambiguous safety analysis."""
        from llm.prompts import safety_prompt
        ctx = platform.system()
        system, user = safety_prompt(command, ctx)
        result = self.llm.generate_json(user, system)

        if not result:
            return SafetyResult(
                risk_level=RiskLevel.CAUTION,
                reason="⚠️ Could not verify safety (LLM unavailable)",
                needs_confirmation=True,
            )

        risk = result.get("risk_level", "CAUTION").upper()
        try:
            risk_level = RiskLevel(risk)
        except ValueError:
            risk_level = RiskLevel.CAUTION

        return SafetyResult(
            risk_level=risk_level,
            reason=result.get("reason", "LLM analysis"),
            affected=AffectedScope(files=result.get("affected_files", [])),
            is_reversible=result.get("is_reversible", True),
            needs_confirmation=risk_level != RiskLevel.SAFE,
        )

    # ═══════════════════════════════════════════════════════
    # Whitelist
    # ═══════════════════════════════════════════════════════

    def whitelist_add(self, command: str):
        """Add a command to the whitelist."""
        self._whitelist.add(command.strip().lower())

    def whitelist_remove(self, command: str):
        """Remove a command from the whitelist."""
        self._whitelist.discard(command.strip().lower())

    def whitelist_list(self) -> list[str]:
        """List all whitelisted commands."""
        return sorted(self._whitelist)

    def set_policy_profile(self, profile: str):
        """Set policy profile (dev, staging, production)."""
        self._policy_profile = self._normalize_profile(profile)

    def set_user_role(self, role: str):
        """Set caller role (admin, developer, operator, viewer)."""
        self._user_role = self._normalize_role(role)

    def get_policy_state(self) -> dict:
        """Return active policy and role context."""
        return {
            "profile": self._policy_profile,
            "role": self._user_role,
        }

    # ═══════════════════════════════════════════════════════
    # Audit Log
    # ═══════════════════════════════════════════════════════

    def _log_audit(self, command: str, result: SafetyResult):
        """Log safety decision to audit trail."""
        entry = AuditEntry(
            timestamp=time.time(),
            command=command,
            risk_level=result.risk_level.value,
            reason=result.reason,
            scope_summary=result.affected.summary,
            prev_hash=self._last_audit_hash,
        )
        entry.entry_hash = self._compute_audit_hash(entry)
        self._audit_log.append(entry)
        self._last_audit_hash = entry.entry_hash

        # Trim audit log
        if len(self._audit_log) > self.MAX_AUDIT_LOG:
            self._audit_log = self._audit_log[-self.MAX_AUDIT_LOG:]
            self._rebuild_audit_chain(start_index=0)

    def record_user_action(self, command: str, action: str):
        """Record user's response to a safety prompt."""
        for idx in range(len(self._audit_log) - 1, -1, -1):
            entry = self._audit_log[idx]
            if entry.command == command:
                entry.user_action = action
                self._rebuild_audit_chain(start_index=idx)
                break

    def get_audit_log(self, limit: int = 50) -> list[dict]:
        """Get recent audit log entries."""
        return [
            {
                "timestamp": e.timestamp,
                "command": e.command,
                "risk_level": e.risk_level,
                "reason": e.reason,
                "user_action": e.user_action,
                "scope": e.scope_summary,
                "prev_hash": e.prev_hash,
                "entry_hash": e.entry_hash,
            }
            for e in self._audit_log[-limit:]
        ]

    def export_audit_json(self, file_path: str, limit: int = 500) -> int:
        """Export recent audit entries to a JSON file. Returns count exported."""
        rows = self.get_audit_log(limit=limit)
        payload = {
            "exported_at": time.time(),
            "profile": self._policy_profile,
            "role": self._user_role,
            "count": len(rows),
            "entries": rows,
        }

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return len(rows)

    def export_audit_csv(self, file_path: str, limit: int = 500) -> int:
        """Export recent audit entries to CSV. Returns count exported."""
        rows = self.get_audit_log(limit=limit)
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "timestamp",
                    "command",
                    "risk_level",
                    "reason",
                    "user_action",
                    "scope",
                    "prev_hash",
                    "entry_hash",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        return len(rows)

    def write_export_digest(self, file_path: str) -> str:
        """Write SHA256 sidecar digest for an exported audit file."""
        path = Path(file_path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        sidecar = path.with_suffix(path.suffix + ".sha256")
        sidecar.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
        return digest

    def verify_audit_export(self, file_path: str) -> dict:
        """Verify exported audit file chain integrity and optional sidecar digest."""
        path = Path(file_path)
        if not path.exists():
            return {"ok": False, "reason": "file_not_found", "entries_checked": 0, "digest_ok": None}

        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("entries", []) if isinstance(payload, dict) else []
        elif path.suffix.lower() == ".csv":
            with open(path, "r", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        else:
            return {"ok": False, "reason": "unsupported_extension", "entries_checked": 0, "digest_ok": None}

        prev_hash = ""
        checked = 0
        for row in rows:
            command = row.get("command", "")
            risk_level = row.get("risk_level", "")
            reason = row.get("reason", "")
            user_action = row.get("user_action", "")
            scope_summary = row.get("scope", row.get("scope_summary", ""))
            row_prev_hash = row.get("prev_hash", "")
            entry_hash = row.get("entry_hash", "")

            if row_prev_hash != prev_hash:
                return {"ok": False, "reason": "broken_prev_hash_chain", "entries_checked": checked, "digest_ok": self._verify_export_digest(path)}

            timestamp_raw = row.get("timestamp", 0)
            try:
                timestamp = float(timestamp_raw)
            except (TypeError, ValueError):
                return {"ok": False, "reason": "invalid_timestamp", "entries_checked": checked, "digest_ok": self._verify_export_digest(path)}

            expected = self._compute_audit_hash_from_parts(
                timestamp=timestamp,
                command=command,
                risk_level=risk_level,
                reason=reason,
                user_action=user_action,
                scope_summary=scope_summary,
                prev_hash=row_prev_hash,
            )
            if entry_hash != expected:
                return {"ok": False, "reason": "entry_hash_mismatch", "entries_checked": checked, "digest_ok": self._verify_export_digest(path)}

            prev_hash = entry_hash
            checked += 1

        return {
            "ok": True,
            "reason": "ok",
            "entries_checked": checked,
            "digest_ok": self._verify_export_digest(path),
        }

    def _compute_audit_hash(self, entry: AuditEntry) -> str:
        """Compute deterministic tamper-evident hash for an audit entry."""
        return self._compute_audit_hash_from_parts(
            timestamp=entry.timestamp,
            command=entry.command,
            risk_level=entry.risk_level,
            reason=entry.reason,
            user_action=entry.user_action,
            scope_summary=entry.scope_summary,
            prev_hash=entry.prev_hash,
        )

    def _compute_audit_hash_from_parts(
        self,
        timestamp: float,
        command: str,
        risk_level: str,
        reason: str,
        user_action: str,
        scope_summary: str,
        prev_hash: str,
    ) -> str:
        """Compute deterministic hash from normalized audit fields."""
        payload = "|".join([
            f"{float(timestamp):.6f}",
            command,
            risk_level,
            reason,
            user_action,
            scope_summary,
            prev_hash,
        ])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _verify_export_digest(self, path: Path) -> Optional[bool]:
        """Verify optional sidecar digest. Returns None when no sidecar exists."""
        sidecar = path.with_suffix(path.suffix + ".sha256")
        if not sidecar.exists():
            return None

        try:
            line = sidecar.read_text(encoding="utf-8").strip().splitlines()[0]
            expected = line.split()[0]
            current = hashlib.sha256(path.read_bytes()).hexdigest()
            return expected == current
        except Exception:
            return False

    def _rebuild_audit_chain(self, start_index: int = 0):
        """Rebuild hash chain from a given index after audit mutation."""
        if not self._audit_log:
            self._last_audit_hash = ""
            return

        if start_index <= 0:
            prev_hash = ""
            start = 0
        else:
            start = min(start_index, len(self._audit_log) - 1)
            prev_hash = self._audit_log[start - 1].entry_hash

        for i in range(start, len(self._audit_log)):
            self._audit_log[i].prev_hash = prev_hash
            self._audit_log[i].entry_hash = self._compute_audit_hash(self._audit_log[i])
            prev_hash = self._audit_log[i].entry_hash

        self._last_audit_hash = self._audit_log[-1].entry_hash

    def get_audit_stats(self) -> dict:
        """Get audit log statistics."""
        if not self._audit_log:
            return {"total": 0}

        total = len(self._audit_log)
        by_level = {}
        approved = 0
        rejected = 0

        for entry in self._audit_log:
            by_level[entry.risk_level] = by_level.get(entry.risk_level, 0) + 1
            if entry.user_action == "approved":
                approved += 1
            elif entry.user_action == "rejected":
                rejected += 1

        return {
            "total": total,
            "by_level": by_level,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": round(approved / max(1, approved + rejected) * 100, 1),
        }

    # ═══════════════════════════════════════════════════════
    # Utility
    # ═══════════════════════════════════════════════════════

    def _detect_affected_files(self, command: str) -> list[str]:
        """Detect files from command — legacy compatibility."""
        return self._estimate_scope(command).files

    def _normalize_profile(self, profile: str) -> str:
        p = (profile or "dev").strip().lower()
        return p if p in self.VALID_PROFILES else "dev"

    def _normalize_role(self, role: str) -> str:
        r = (role or "developer").strip().lower()
        return r if r in self.VALID_ROLES else "developer"

    def _has_high_impact_markers(self, command: str) -> bool:
        cmd = command.lower()
        return any(marker in cmd for marker in self.HIGH_IMPACT_MARKERS)

    def _apply_policy_overrides(self, command: str, result: SafetyResult) -> SafetyResult:
        """Apply profile and role governance to baseline safety result."""
        profile = self._policy_profile
        role = self._user_role

        # Dev profile keeps baseline behavior for flexibility.
        if profile == "dev":
            return result

        # Staging profile: upgrade caution to danger for non-admin users on recursive/system-wide ops.
        if profile == "staging":
            if result.risk_level == RiskLevel.CAUTION and role != "admin":
                if result.affected.recursive or result.affected.system_wide:
                    result.risk_level = RiskLevel.DANGER
                    result.needs_confirmation = True
                    result.reason = f"⛔ [staging/{role}] Escalated from CAUTION: {result.reason}"
                    result._refresh_badge()
            return result

        # Production profile: strict governance with role-based blocking.
        if profile == "production":
            if role == "viewer":
                if result.risk_level != RiskLevel.SAFE:
                    result.risk_level = RiskLevel.BLOCKED
                    result.needs_confirmation = True
                    result.reason = f"🚫 [production/viewer] Non-read-only command blocked: {result.reason}"
                    result._refresh_badge()
                    return result

            if role in {"developer", "operator"}:
                if result.risk_level == RiskLevel.CAUTION and (result.affected.recursive or result.affected.system_wide):
                    result.risk_level = RiskLevel.DANGER
                    result.needs_confirmation = True
                    result.reason = f"⛔ [production/{role}] Escalated from CAUTION: {result.reason}"
                    result._refresh_badge()

                if result.risk_level == RiskLevel.DANGER and self._has_high_impact_markers(command):
                    result.risk_level = RiskLevel.BLOCKED
                    result.needs_confirmation = True
                    result.reason = f"🚫 [production/{role}] High-impact command blocked by policy"
                    result._refresh_badge()

            # Admin retains explicit confirmation but is not auto-blocked by profile escalations.
            if role == "admin" and result.risk_level in {RiskLevel.CAUTION, RiskLevel.DANGER}:
                result.needs_confirmation = True

        return result
