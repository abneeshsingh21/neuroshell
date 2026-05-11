# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Autonomous Agent Mode + Smart Error Auto-Recovery
Tier 1 Features: Multi-step task execution and automatic error diagnosis.
"""

import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger("neuroshell.agent")


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RECOVERED = "recovered"


@dataclass
class AgentStep:
    """Single step in an autonomous task."""
    description: str
    command: str
    status: StepStatus = StepStatus.PENDING
    output: str = ""
    error: str = ""
    duration_ms: float = 0
    retry_count: int = 0
    fix_applied: str = ""


@dataclass
class AgentPlan:
    """Full execution plan for an autonomous task."""
    goal: str
    steps: list[AgentStep] = field(default_factory=list)
    current_step: int = 0
    total_duration_ms: float = 0
    auto_recovery: bool = True
    max_retries: int = 2


# ── Common error patterns and their fixes ──
ERROR_FIXES = {
    # Python
    r"ModuleNotFoundError: No module named '(\S+)'": "pip install {0}",
    r"command not found: (\S+)": "which {0} || echo '{0} is not installed'",
    r"Permission denied": "sudo !!",
    r"EACCES: permission denied": "sudo !!",
    r"port.*already in use|Address already in use": "lsof -i :{port} | grep LISTEN",
    r"No such file or directory: '(.+)'": "mkdir -p $(dirname '{0}')",
    r"fatal: not a git repository": "git init",
    r"npm ERR! missing script: (\S+)": "cat package.json | grep scripts",
    r"ENOENT.*package\.json": "npm init -y",
    r"Could not find a version that satisfies": "pip install --upgrade pip",
    r"error: failed to push some refs": "git pull --rebase && git push",
    r"CONFLICT.*Merge conflict": "git status",
    r"docker: Cannot connect to the Docker daemon": "sudo systemctl start docker",
    r"connection refused.*5432": "sudo systemctl start postgresql",
    r"connection refused.*3306": "sudo systemctl start mysql",
    r"connection refused.*6379": "sudo systemctl start redis",
    r"error TS\d+": "npx tsc --noEmit 2>&1 | head -20",
    r"SyntaxError": "python -m py_compile {file}",
    r"ENOMEM|Cannot allocate memory": "free -h && echo 'System is out of memory'",
    r"disk.*full|No space left on device": "df -h && du -sh /tmp/* | sort -rh | head",
}

# Windows-specific error fixes
WINDOWS_ERROR_FIXES = {
    r"is not recognized as an internal or external command": 'where {0} 2>nul || echo "{0} not found in PATH"',
    r"Access is denied": "runas /user:Administrator {cmd}",
    r"The process cannot access the file": "handle {file}",
    r"port.*already in use|actively refused": "netstat -ano | findstr :{port}",
    r"docker: error.*Cannot connect": "net start com.docker.service",
}


class SmartErrorRecovery:
    """Tier 1: Automatic error diagnosis and recovery."""

    def __init__(self, is_windows: bool = False):
        self.is_windows = is_windows
        self._error_history: list[dict] = []

    def diagnose(self, command: str, stderr: str, exit_code: int) -> Optional[str]:
        """Analyze stderr and return a fix command, or None."""
        if exit_code == 0 or not stderr:
            return None

        fixes = {**ERROR_FIXES, **(WINDOWS_ERROR_FIXES if self.is_windows else {})}

        for pattern, fix_template in fixes.items():
            match = re.search(pattern, stderr, re.IGNORECASE)
            if match:
                try:
                    fix = fix_template.format(*match.groups()) if match.groups() else fix_template
                    fix = fix.replace("{cmd}", command)
                    self._error_history.append({
                        "command": command, "error": stderr[:200],
                        "fix": fix, "time": time.time(),
                    })
                    logger.info("Auto-recovery: %s → %s", pattern, fix)
                    return fix
                except (IndexError, KeyError):
                    continue
        return None

    def get_recovery_stats(self) -> dict:
        return {
            "total_recoveries": len(self._error_history),
            "recent": self._error_history[-5:] if self._error_history else [],
        }


class AutonomousAgent:
    """Tier 1: Execute multi-step tasks from a single English description."""

    # ── Pre-built task templates ──
    TASK_TEMPLATES = {
        r"set\s*up\s+(?:a\s+)?django\s+project(?:\s+(?:called|named)\s+(\S+))?": [
            ("Create virtual environment", "python -m venv .venv"),
            ("Activate venv", ".venv/Scripts/activate" if __import__("platform").system() == "Windows" else "source .venv/bin/activate"),
            ("Install Django", "pip install django"),
            ("Create Django project", "django-admin startproject {0} ."),
            ("Run initial migration", "python manage.py migrate"),
            ("Create superuser prompt", "python manage.py createsuperuser --noinput --username admin --email admin@local.dev"),
        ],
        r"set\s*up\s+(?:a\s+)?react\s+(?:app|project)(?:\s+(?:called|named)\s+(\S+))?": [
            ("Create React app", "npx create-react-app {0}"),
            ("Enter project directory", "cd {0}"),
            ("Install dependencies", "npm install"),
            ("Start dev server", "npm start"),
        ],
        r"set\s*up\s+(?:a\s+)?node(?:\.?js)?\s+(?:api|server|project)(?:\s+(?:called|named)\s+(\S+))?": [
            ("Create project directory", "mkdir {0} && cd {0}"),
            ("Initialize npm", "npm init -y"),
            ("Install Express", "npm install express"),
            ("Create server file", 'echo "const express = require(\'express\'); const app = express(); app.get(\'/\', (req,res) => res.json({status:\'ok\'})); app.listen(3000, () => console.log(\'Server on :3000\'));" > index.js'),
            ("Start server", "node index.js"),
        ],
        r"set\s*up\s+(?:a\s+)?flask\s+(?:api|app|project)(?:\s+(?:called|named)\s+(\S+))?": [
            ("Create virtual environment", "python -m venv .venv"),
            ("Install Flask", "pip install flask flask-cors"),
            ("Create app file", 'echo "from flask import Flask, jsonify\\napp = Flask(__name__)\\n@app.route(\'/\')\\ndef index(): return jsonify(status=\'ok\')\\nif __name__==\'__main__\': app.run(debug=True)" > app.py'),
            ("Run Flask", "python app.py"),
        ],
        r"(?:init|initialize|set\s*up)\s+git\s+(?:repo|repository)": [
            ("Initialize git", "git init"),
            ("Create .gitignore", 'echo "node_modules/\\n.venv/\\n__pycache__/\\n*.pyc\\n.env\\ndist/\\nbuild/" > .gitignore'),
            ("Initial commit", "git add -A && git commit -m 'Initial commit'"),
        ],
        r"deploy\s+(?:to\s+)?docker": [
            ("Build Docker image", "docker build -t app ."),
            ("Run container", "docker run -d -p 8080:8080 --name app app"),
            ("Check status", "docker ps"),
            ("Show logs", "docker logs app"),
        ],
        r"clean\s+(?:up\s+)?(?:this\s+)?(?:project|repo|directory)": [
            ("Remove node_modules", "rm -rf node_modules"),
            ("Remove Python cache", "find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; find . -name '*.pyc' -delete 2>/dev/null"),
            ("Remove build artifacts", "rm -rf dist build *.egg-info .pytest_cache .mypy_cache"),
            ("Show cleaned size", "du -sh ."),
        ],
        r"run\s+(?:full\s+)?(?:test|testing)\s+suite": [
            ("Check for pytest", "python -m pytest --version 2>/dev/null || pip install pytest"),
            ("Run tests with coverage", "python -m pytest -v --tb=short"),
            ("Show test summary", "python -m pytest --co -q 2>/dev/null | tail -5"),
        ],
    }

    def __init__(self, executor: Optional[Callable] = None, recovery: Optional[SmartErrorRecovery] = None):
        self.executor = executor
        self.recovery = recovery or SmartErrorRecovery()
        self._plans: list[AgentPlan] = []

    def plan(self, user_input: str) -> Optional[AgentPlan]:
        """Create execution plan from user input."""
        for pattern, steps_template in self.TASK_TEMPLATES.items():
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                name = match.group(1) if match.groups() and match.group(1) else "myapp"
                steps = []
                for desc, cmd in steps_template:
                    resolved = cmd.replace("{0}", name)
                    steps.append(AgentStep(description=desc, command=resolved))
                plan = AgentPlan(goal=user_input, steps=steps)
                self._plans.append(plan)
                return plan
        return None

    def execute_plan(self, plan: AgentPlan, executor: Callable, ui=None) -> AgentPlan:
        """Execute all steps in plan sequentially with auto-recovery."""
        start = time.time()
        for i, step in enumerate(plan.steps):
            plan.current_step = i
            step.status = StepStatus.RUNNING
            if ui:
                ui.toast(f"Step {i+1}/{len(plan.steps)}: {step.description}", "info")
            try:
                step_start = time.time()
                result = executor(step.command)
                step.duration_ms = (time.time() - step_start) * 1000
                step.output = getattr(result, 'stdout', '') or ''
                step.error = getattr(result, 'stderr', '') or ''
                exit_code = getattr(result, 'exit_code', 0)

                if exit_code == 0:
                    step.status = StepStatus.SUCCESS
                else:
                    step.status = StepStatus.FAILED
                    if plan.auto_recovery and step.retry_count < plan.max_retries:
                        fix = self.recovery.diagnose(step.command, step.error, exit_code)
                        if fix:
                            step.fix_applied = fix
                            step.retry_count += 1
                            fix_result = executor(fix)
                            if getattr(fix_result, 'exit_code', 1) == 0:
                                step.status = StepStatus.RECOVERED
                                if ui:
                                    ui.toast(f"Auto-fixed: {fix}", "success")
            except Exception as e:
                step.status = StepStatus.FAILED
                step.error = str(e)

        plan.total_duration_ms = (time.time() - start) * 1000
        return plan

    def get_plan_summary(self, plan: AgentPlan) -> str:
        """Get human-readable plan summary."""
        lines = [f"🤖 Agent Plan: {plan.goal}", ""]
        for i, step in enumerate(plan.steps, 1):
            icon = {"success": "✅", "failed": "❌", "recovered": "🔧",
                    "running": "⏳", "pending": "⬜", "skipped": "⏭️"}
            status = icon.get(step.status.value, "⬜")
            lines.append(f"  {status} Step {i}: {step.description}")
            lines.append(f"     $ {step.command}")
            if step.fix_applied:
                lines.append(f"     🔧 Auto-fix: {step.fix_applied}")
        succeeded = sum(1 for s in plan.steps if s.status in (StepStatus.SUCCESS, StepStatus.RECOVERED))
        lines.append(f"\n  Result: {succeeded}/{len(plan.steps)} steps succeeded ({plan.total_duration_ms:.0f}ms)")
        return "\n".join(lines)
