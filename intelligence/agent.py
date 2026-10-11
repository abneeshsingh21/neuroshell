# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell AI Agent Mode 2.0
Multi-step autonomous task planning, execution, and self-healing.
- Git workspace state snapshotting before execution
- Decomposes complex tasks into numbered steps with safety approval
- Dynamic Self-Healing Feedback Loop: catches non-zero exit codes,
  diagnoses root cause, executes remediation, and retries automatically
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class AgentStep:
    """A single step in an agent plan."""
    order: int
    action: str  # "shell", "create_file", "check", "install"
    command: str
    description: str = ""
    expected_output: str = ""
    status: str = "pending"  # pending, running, success, healed, failed, skipped
    output: str = ""
    duration_ms: float = 0
    is_destructive: bool = False
    attempts: int = 1
    remediation_cmd: str = ""


@dataclass
class AgentPlan:
    """A complete multi-step agent plan."""
    task: str
    steps: list[AgentStep] = field(default_factory=list)
    status: str = "planned"  # planned, running, completed, failed, aborted
    created: float = field(default_factory=time.time)
    completed_steps: int = 0
    git_snapshot_ref: str = ""

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def progress_pct(self) -> float:
        if not self.steps:
            return 0.0
        return (self.completed_steps / len(self.steps)) * 100.0

    def display(self) -> str:
        lines = [f"\n🤖 Agent Plan: {self.task}", f"   {self.total_steps} steps | {self.status.upper()}", ""]
        icons = {
            "pending": "⬜",
            "running": "🔄",
            "success": "✅",
            "healed": "⚡",
            "failed": "❌",
            "skipped": "⏭️",
        }
        for step in self.steps:
            icon = icons.get(step.status, "⬜")
            healed_tag = " (AUTO-HEALED)" if step.status == "healed" else ""
            lines.append(f"  {icon} Step {step.order}: {step.description}{healed_tag}")
            lines.append(f"     $ {step.command}")
            if step.remediation_cmd:
                lines.append(f"     ↳ Remediation: {step.remediation_cmd}")
        return "\n".join(lines)


class AgentPlanner:
    """AI Agent that plans, executes, and self-heals multi-step developer workflows."""

    def __init__(self, llm_client=None, executor=None, safety_checker=None):
        self.llm = llm_client
        self.executor = executor
        self.safety = safety_checker

    def plan(self, task_description: str) -> AgentPlan | None:
        """Create an execution plan for a complex task."""
        if not self.llm:
            return self._offline_plan(task_description)

        system_prompt = (
            "You are a shell automation agent. Break the user's task into sequential shell commands.\n"
            f"OS: {os.name}, Shell: {'powershell' if os.name == 'nt' else 'bash'}\n"
            "Current directory: " + os.getcwd() + "\n"
            "Respond as JSON:\n"
            '{"steps": [{"command": "...", "description": "...", "action": "shell", "is_destructive": false}]}\n'
            "Keep steps minimal and safe. Max 10 steps."
        )

        try:
            result = self.llm.generate_json(task_description, system_prompt)
        except Exception:
            result = None

        if not result or "steps" not in result:
            return self._offline_plan(task_description)

        steps = []
        for i, step_data in enumerate(result["steps"][:10]):
            steps.append(AgentStep(
                order=i + 1,
                action=step_data.get("action", "shell"),
                command=step_data.get("command", ""),
                description=step_data.get("description", ""),
                is_destructive=step_data.get("is_destructive", False),
            ))

        return AgentPlan(task=task_description, steps=steps)

    def _offline_plan(self, task: str) -> AgentPlan:
        """Create a basic plan without LLM."""
        return AgentPlan(
            task=task,
            steps=[AgentStep(
                order=1,
                action="shell",
                command=task,
                description="Execute directly (no LLM available for planning)",
            )],
        )

    def _capture_git_snapshot(self) -> str:
        """Capture dirty git workspace state before running agent modifications."""
        try:
            res = subprocess.run(
                ["git", "stash", "create", "neuroshell-agent-snapshot"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return res.stdout.strip()
        except Exception:
            return ""

    def _diagnose_and_heal(self, failed_cmd: str, error_output: str) -> str | None:
        """
        Synthesize automatic remediation command from failure output.
        Handles missing python modules, npm packages, missing directories, ports, etc.
        """
        err_lower = error_output.lower()

        # 1. Python missing module: ModuleNotFoundError: No module named 'xyz'
        m = re.search(r"ModuleNotFoundError:\s+No module named ['\"]([^'\"]+)['\"]", error_output)
        if m:
            pkg = m.group(1).split(".")[0]
            return f"pip install {pkg}"

        # 2. Python missing package: ImportError: cannot import name 'xyz'
        m = re.search(r"ImportError:\s+cannot import name.*from ['\"]([^'\"]+)['\"]", error_output)
        if m:
            return f"pip install --upgrade {m.group(1)}"

        # 3. NPM missing module: Cannot find module 'xyz'
        m = re.search(r"Cannot find module ['\"]([^'\"]+)['\"]", error_output)
        if m:
            return f"npm install {m.group(1)}"

        # 4. Directory missing: No such file or directory
        m = re.search(r"(?:No such file or directory|cannot find the path specified).*?['\"]?([a-zA-Z0-9_./\\]+)['\"]?", error_output)
        if m and ("mkdir" not in failed_cmd):
            path_part = m.group(1).rstrip("/\\")
            parent = os.path.dirname(path_part)
            if parent:
                return f"mkdir -p {parent}" if os.name != "nt" else f"mkdir {parent}"

        # 5. Git unstaged changes preventing pull/checkout
        if "please commit your changes or stash them" in err_lower:
            return "git stash"

        # 6. Port already in use
        if "address already in use" in err_lower or "only one usage of each socket address" in err_lower:
            m = re.search(r":(\d{2,5})", error_output)
            if m:
                port = m.group(1)
                if os.name == "nt":
                    return f"netstat -ano | findstr :{port}"
                return f"lsof -ti:{port} | xargs kill -9"

        # 7. LLM error diagnosis fallback
        if self.llm:
            try:
                diag = self.llm.generate(
                    f"Command: {failed_cmd}\nError: {error_output[:800]}\n"
                    "Output single shell command to fix this error, or NONE:",
                    "You are an expert DevOps debugger. Output only the shell command."
                )
                if diag and "NONE" not in diag and len(diag.strip()) < 100:
                    return diag.strip().strip("`$ ")
            except Exception:
                pass

        return None

    def execute_plan(
        self,
        plan: AgentPlan,
        confirm_each: bool = False,
        auto_heal: bool = True,
        max_retries: int = 3,
        callback: Callable[[AgentStep, str], Any] | None = None,
    ) -> AgentPlan:
        """
        Execute an agent plan with Git state protection and autonomous self-healing.
        """
        plan.status = "running"
        plan.git_snapshot_ref = self._capture_git_snapshot()

        for step in plan.steps:
            # 1. Safety check
            if self.safety:
                safety_result = self.safety.check(step.command)
                if hasattr(safety_result, "risk_level") and \
                   getattr(safety_result.risk_level, "value", str(safety_result.risk_level)) in ("BLOCKED", "DANGER"):
                    step.status = "skipped"
                    step.output = f"Blocked by safety: {getattr(safety_result, 'reason', 'High risk')}"
                    if callback:
                        callback(step, "blocked")
                    continue

            # 2. Per-step confirmation
            if confirm_each and callback:
                if not callback(step, "confirm"):
                    step.status = "skipped"
                    plan.status = "aborted"
                    break

            # 3. Execution & Self-Healing Loop
            step.status = "running"
            if callback:
                callback(step, "running")

            if not self.executor:
                step.status = "skipped"
                step.output = "No executor available"
                continue

            success = False
            for attempt in range(1, max_retries + 1):
                step.attempts = attempt
                start = time.time()
                result = self.executor.execute(step.command)
                step.duration_ms = (time.time() - start) * 1000
                step.output = (result.stdout or result.stderr or "")[:1000]

                if result.exit_code == 0:
                    step.status = "healed" if attempt > 1 else "success"
                    plan.completed_steps += 1
                    success = True
                    break

                # Step failed: Attempt Self-Healing
                if auto_heal and attempt < max_retries:
                    err_out = result.stderr or result.stdout or ""
                    remediation = self._diagnose_and_heal(step.command, err_out)
                    if remediation:
                        step.remediation_cmd = remediation
                        if callback:
                            callback(step, f"healing:{remediation}")
                        # Execute remediation fix
                        remedy_res = self.executor.execute(remediation)
                        if remedy_res.exit_code == 0:
                            # Re-attempt the failed step
                            continue

                # If cannot heal or reached max retries
                step.status = "failed"
                break

            if not success:
                if callback:
                    callback(step, "failed")
                plan.status = "failed"
                break

            if callback:
                callback(step, step.status)

        if plan.status == "running":
            plan.status = "completed"

        return plan
