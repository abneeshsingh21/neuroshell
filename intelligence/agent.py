# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell AI Agent Mode
Multi-step autonomous task planning and execution.
Decomposes complex tasks into numbered steps with approval before execution.
"""

import os
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentStep:
    """A single step in an agent plan."""
    order: int
    action: str  # "shell", "create_file", "check", "install"
    command: str
    description: str = ""
    expected_output: str = ""
    status: str = "pending"
    output: str = ""
    duration_ms: float = 0
    is_destructive: bool = False


@dataclass
class AgentPlan:
    """A complete multi-step agent plan."""
    task: str
    steps: list[AgentStep] = field(default_factory=list)
    status: str = "planned"  # planned, running, completed, failed, aborted
    created: float = field(default_factory=time.time)
    completed_steps: int = 0

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def progress_pct(self) -> float:
        if not self.steps:
            return 0
        return (self.completed_steps / len(self.steps)) * 100

    def display(self) -> str:
        lines = [f"\n🤖 Agent Plan: {self.task}", f"   {self.total_steps} steps | {self.status}", ""]
        for step in self.steps:
            icons = {"pending": "⬜", "running": "🔄", "success": "✅", "failed": "❌", "skipped": "⏭️"}
            icon = icons.get(step.status, "⬜")
            lines.append(f"  {icon} Step {step.order}: {step.description}")
            lines.append(f"     $ {step.command}")
        return "\n".join(lines)


class AgentPlanner:
    """AI Agent that plans and executes multi-step tasks."""

    def __init__(self, llm_client=None, executor=None, safety_checker=None):
        self.llm = llm_client
        self.executor = executor
        self.safety = safety_checker

    def plan(self, task_description: str) -> Optional[AgentPlan]:
        """Create an execution plan for a complex task."""
        if not self.llm:
            return self._offline_plan(task_description)

        system_prompt = (
            "You are a shell automation agent. Break the user's task into sequential shell commands.\n"
            f"OS: {os.name}, Shell: {'powershell' if os.name == 'nt' else 'bash'}\n"
            "Current directory: " + os.getcwd() + "\n"
            "Respond as JSON:\n"
            '{"steps": [{"command": "...", "description": "...", "action": "shell"}]}\n'
            "Keep steps minimal and safe. Max 10 steps."
        )

        result = self.llm.generate_json(task_description, system_prompt)
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

    def execute_plan(self, plan: AgentPlan, confirm_each: bool = False,
                     callback=None) -> AgentPlan:
        """
        Execute a plan step by step.
        Returns the updated plan with results.
        """
        plan.status = "running"

        for step in plan.steps:
            # Safety check
            if self.safety:
                safety_result = self.safety.check(step.command)
                if hasattr(safety_result, 'risk_level') and \
                   safety_result.risk_level.value in ("BLOCKED", "DANGER"):
                    step.status = "skipped"
                    step.output = f"Blocked by safety: {safety_result.reason}"
                    if callback:
                        callback(step, "blocked")
                    continue

            # Per-step confirmation
            if confirm_each and callback:
                if not callback(step, "confirm"):
                    step.status = "skipped"
                    plan.status = "aborted"
                    break

            # Execute
            step.status = "running"
            if callback:
                callback(step, "running")

            if self.executor:
                start = time.time()
                result = self.executor.execute(step.command)
                step.duration_ms = (time.time() - start) * 1000
                step.output = (result.stdout or result.stderr or "")[:500]

                if result.exit_code == 0:
                    step.status = "success"
                    plan.completed_steps += 1
                else:
                    step.status = "failed"
                    if callback:
                        callback(step, "failed")
                    plan.status = "failed"
                    break
            else:
                step.status = "skipped"
                step.output = "No executor available"

            if callback:
                callback(step, step.status)

        if plan.status == "running":
            plan.status = "completed"

        return plan
