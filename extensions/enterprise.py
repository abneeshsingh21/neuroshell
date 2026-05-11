# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Workflow Engine + Vulnerability Scanner + Audit Trail
Tier 1+2: Natural language workflows, security scanning, compliance logging.
"""

import re
import os
import json
import time
import platform
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime

logger = logging.getLogger("neuroshell.enterprise")

# ═══════════════════════════════════════════════════════════
# Natural Language Workflow Engine
# ═══════════════════════════════════════════════════════════

WORKFLOW_PATTERNS = {
    r"every\s+(\d+)\s+minutes?\s*,?\s*(.+)": ("interval_min", None),
    r"every\s+(\d+)\s+hours?\s*,?\s*(.+)": ("interval_hour", None),
    r"every\s+day\s+at\s+(\d{1,2}(?::\d{2})?)\s*(?:am|pm)?\s*,?\s*(.+)": ("daily", None),
    r"every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)\s*,?\s*(.+)": ("weekly", None),
    r"at\s+(\d{1,2}:\d{2})\s*,?\s*(.+)": ("once", None),
}

DAY_MAP = {"monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5, "saturday": 6, "sunday": 0}


@dataclass
class WorkflowTask:
    """A scheduled workflow task."""
    name: str
    schedule_type: str  # interval_min, daily, weekly, once
    schedule_value: str
    commands: list[str]
    cron_expression: str = ""
    schtasks_command: str = ""
    created_at: float = field(default_factory=time.time)


class WorkflowEngine:
    """Compile natural language schedules into cron/schtasks."""

    def __init__(self):
        self.is_windows = platform.system() == "Windows"
        self._workflows: list[WorkflowTask] = []

    def parse(self, user_input: str) -> Optional[WorkflowTask]:
        """Parse natural language workflow description."""
        user_lower = user_input.lower().strip()

        for pattern, (sched_type, _) in WORKFLOW_PATTERNS.items():
            match = re.search(pattern, user_lower)
            if not match:
                continue
            groups = match.groups()

            if sched_type == "interval_min":
                minutes, cmd_text = groups[0], groups[1]
                cron = f"*/{minutes} * * * *"
                schtasks = f'schtasks /create /tn "neuroshell_task" /tr "{cmd_text}" /sc minute /mo {minutes}'
                return self._build_task(f"Every {minutes}min", sched_type, minutes, cmd_text, cron, schtasks)

            elif sched_type == "interval_hour":
                hours, cmd_text = groups[0], groups[1]
                cron = f"0 */{hours} * * *"
                schtasks = f'schtasks /create /tn "neuroshell_task" /tr "{cmd_text}" /sc hourly /mo {hours}'
                return self._build_task(f"Every {hours}h", sched_type, hours, cmd_text, cron, schtasks)

            elif sched_type == "daily":
                time_str, cmd_text = groups[0], groups[1]
                hour, minute = self._parse_time(time_str)
                cron = f"{minute} {hour} * * *"
                schtasks = f'schtasks /create /tn "neuroshell_task" /tr "{cmd_text}" /sc daily /st {hour:02d}:{minute:02d}'
                return self._build_task(f"Daily at {hour}:{minute:02d}", sched_type, time_str, cmd_text, cron, schtasks)

            elif sched_type == "weekly":
                day, time_str, cmd_text = groups[0], groups[1], groups[2]
                hour, minute = self._parse_time(time_str)
                day_num = DAY_MAP.get(day, 0)
                cron = f"{minute} {hour} * * {day_num}"
                day_abbr = day[:3].upper()
                schtasks = f'schtasks /create /tn "neuroshell_task" /tr "{cmd_text}" /sc weekly /d {day_abbr} /st {hour:02d}:{minute:02d}'
                return self._build_task(f"Every {day} at {hour}:{minute:02d}", sched_type, f"{day} {time_str}", cmd_text, cron, schtasks)

        return None

    def _build_task(self, name, stype, sval, cmd_text, cron, schtasks) -> WorkflowTask:
        commands = [c.strip() for c in re.split(r",\s*(?:then\s+|and\s+)?", cmd_text) if c.strip()]
        task = WorkflowTask(name=name, schedule_type=stype, schedule_value=sval, commands=commands, cron_expression=cron, schtasks_command=schtasks)
        self._workflows.append(task)
        return task

    def get_install_command(self, task: WorkflowTask) -> str:
        """Get the OS-specific command to install the workflow."""
        if self.is_windows:
            return task.schtasks_command
        cmd_chain = " && ".join(task.commands)
        return f'(crontab -l 2>/dev/null; echo "{task.cron_expression} {cmd_chain}") | crontab -'

    def _parse_time(self, time_str: str) -> tuple[int, int]:
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return hour, minute


# ═══════════════════════════════════════════════════════════
# Vulnerability Scanner
# ═══════════════════════════════════════════════════════════

@dataclass
class ScanResult:
    tool: str
    status: str  # ok, warning, critical, error
    findings: list[str]
    command_used: str


class VulnerabilityScanner:
    """Scan project for security vulnerabilities using available tools."""

    def __init__(self):
        self.is_windows = platform.system() == "Windows"

    def get_scan_commands(self, cwd: str = ".") -> list[tuple[str, str]]:
        """Return list of (description, command) to run for scanning."""
        cwd_path = Path(cwd)
        scans = []

        # Python dependencies
        if (cwd_path / "requirements.txt").exists():
            scans.append(("Python dependency audit", "pip-audit 2>/dev/null || pip install pip-audit && pip-audit"))
            scans.append(("Python safety check", "safety check --file requirements.txt 2>/dev/null || pip install safety && safety check --file requirements.txt"))

        # Node dependencies
        if (cwd_path / "package.json").exists():
            scans.append(("NPM security audit", "npm audit --json 2>/dev/null | head -50"))
            scans.append(("NPM outdated packages", "npm outdated"))

        # Docker
        if (cwd_path / "Dockerfile").exists():
            scans.append(("Dockerfile security scan", "docker scout cves 2>/dev/null || echo 'Install docker scout for container scanning'"))

        # Git secrets
        if (cwd_path / ".git").is_dir():
            scans.append(("Git secrets detection", "git log --all --diff-filter=A --name-only --format='' | grep -iE '(password|secret|key|token|api_key|credentials)' | head -20"))

        # General file permission check
        if not self.is_windows:
            scans.append(("World-writable files", "find . -type f -perm -o+w 2>/dev/null | head -20"))
            scans.append(("Files with secrets", "grep -rl --include='*.py' --include='*.js' --include='*.env' -iE '(password|secret|api_key|token)\\s*=' . 2>/dev/null | head -20"))
        else:
            scans.append(("Files with secrets", 'findstr /s /i /m "password= secret= api_key= token=" *.py *.js *.env 2>nul'))

        # .env file exposure
        if (cwd_path / ".env").exists():
            git_ignore = cwd_path / ".gitignore"
            if git_ignore.exists():
                content = git_ignore.read_text()
                if ".env" not in content:
                    scans.append(("⚠️ .env not in .gitignore", "echo '.env' >> .gitignore"))
            else:
                scans.append(("⚠️ No .gitignore found", "echo '.env\nnode_modules/\n__pycache__/' > .gitignore"))

        return scans


# ═══════════════════════════════════════════════════════════
# Audit Trail & Compliance + RBAC
# ═══════════════════════════════════════════════════════════

class UserRole:
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"

ROLE_PERMISSIONS = {
    UserRole.ADMIN: {"execute", "delete", "install", "shutdown", "sudo", "config"},
    UserRole.DEVELOPER: {"execute", "install", "config"},
    UserRole.VIEWER: {"execute"},  # read-only commands only
}

DESTRUCTIVE_ACTIONS = {"delete", "shutdown", "sudo"}


@dataclass
class AuditEntry:
    timestamp: str
    user: str
    role: str
    command: str
    risk_score: int
    action: str  # executed, blocked, warned
    cwd: str
    duration_ms: float = 0
    exit_code: int = 0


class AuditTrail:
    """SOC2/ISO-compliant audit logging with RBAC enforcement."""

    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or Path.home() / ".neuroshell" / "audit"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_role = UserRole.ADMIN
        self._user = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))

    def set_role(self, role: str):
        if role in (UserRole.ADMIN, UserRole.DEVELOPER, UserRole.VIEWER):
            self._current_role = role

    def check_permission(self, command: str, risk_score: int = 0) -> tuple[bool, str]:
        """Check if current role can execute this command."""
        perms = ROLE_PERMISSIONS.get(self._current_role, set())
        cmd_lower = command.lower()

        if risk_score >= 8 and "sudo" not in perms:
            return False, f"Role '{self._current_role}' cannot run critical-risk commands (score {risk_score}/10)"
        if any(d in cmd_lower for d in ["rm -rf", "del /s", "format", "drop database"]) and "delete" not in perms:
            return False, f"Role '{self._current_role}' cannot run destructive commands"
        if ("sudo " in cmd_lower or "runas " in cmd_lower) and "sudo" not in perms:
            return False, f"Role '{self._current_role}' cannot use elevated privileges"
        if ("shutdown" in cmd_lower or "reboot" in cmd_lower) and "shutdown" not in perms:
            return False, f"Role '{self._current_role}' cannot shutdown/reboot"
        return True, "OK"

    def log(self, command: str, risk_score: int, action: str, cwd: str = ".",
            duration_ms: float = 0, exit_code: int = 0):
        """Log command execution for compliance."""
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            user=self._user, role=self._current_role,
            command=command, risk_score=risk_score,
            action=action, cwd=cwd,
            duration_ms=duration_ms, exit_code=exit_code,
        )
        # Append to daily log file
        log_file = self.log_dir / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry)) + "\n")
        except Exception as e:
            logger.warning("Audit log write failed: %s", e)

    def export_report(self, days: int = 30) -> str:
        """Export audit report for compliance review."""
        entries = []
        for log_file in sorted(self.log_dir.glob("audit_*.jsonl"))[-days:]:
            try:
                for line in log_file.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        entries.append(json.loads(line))
            except Exception:
                continue

        total = len(entries)
        blocked = sum(1 for e in entries if e.get("action") == "blocked")
        critical = sum(1 for e in entries if e.get("risk_score", 0) >= 8)

        report = [
            f"# NeuroShell Audit Report",
            f"Generated: {datetime.now().isoformat()}",
            f"Period: Last {days} days",
            f"",
            f"## Summary",
            f"- Total commands: {total}",
            f"- Blocked commands: {blocked}",
            f"- Critical risk commands: {critical}",
            f"- Unique users: {len(set(e.get('user', '') for e in entries))}",
            f"",
            f"## Recent Critical Actions",
        ]
        for e in entries[-20:]:
            if e.get("risk_score", 0) >= 5:
                report.append(f"  [{e['timestamp']}] {e['user']}({e['role']}) → {e['command'][:60]} [risk:{e['risk_score']}] [{e['action']}]")

        return "\n".join(report)

    def get_stats(self) -> dict:
        return {"role": self._current_role, "user": self._user, "log_dir": str(self.log_dir)}
