# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Smart Command Chaining
Parses multi-step natural language into sequential execution plans.
Handles "then", "and", "after that" keywords for chained commands.
"""

import os
import re
from dataclasses import dataclass, field


@dataclass
class ChainStep:
    """A single step in a command chain."""
    order: int
    command: str
    description: str = ""
    is_destructive: bool = False
    condition: str = ""  # e.g., "on_success", "always"
    status: str = "pending"  # pending, running, success, failed, skipped


@dataclass
class ChainPlan:
    """A full execution plan."""
    steps: list[ChainStep] = field(default_factory=list)
    description: str = ""
    abort_on_failure: bool = True
    source: str = "pattern"  # "pattern" or "llm"

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    def summary(self) -> str:
        lines = [f"📋 Execution Plan ({self.total_steps} steps):"]
        for step in self.steps:
            icon = {"pending": "⬜", "running": "🔄", "success": "✅", "failed": "❌", "skipped": "⏭️"}
            lines.append(f"  {icon.get(step.status, '⬜')} [{step.order}] {step.command}")
            if step.description:
                lines.append(f"      └─ {step.description}")
        return "\n".join(lines)


# Chain keyword patterns
CHAIN_PATTERNS = [
    r'\bthen\b', r'\band then\b', r'\bafter that\b', r'\bfollowed by\b',
    r'\bnext\b', r'\bfinally\b', r'\bfirst\b.*\bthen\b',
]

# Splitter regex
CHAIN_SPLITTER = re.compile(
    r'\s*(?:,?\s*(?:and\s+)?then\s+|,?\s*after\s+that\s+|,?\s*followed\s+by\s+'
    r'|,?\s*next\s+|,?\s*finally\s+|,?\s*and\s+also\s+|,\s+)\s*',
    re.IGNORECASE
)


class ChainBuilder:
    """Build execution plans from multi-step natural language."""

    def __init__(self, llm_client=None, translator=None):
        self.llm = llm_client
        self.translator = translator

    def is_chain_request(self, user_input: str) -> bool:
        """Detect if input contains chaining keywords."""
        lower = user_input.lower()
        return any(re.search(p, lower) for p in CHAIN_PATTERNS)

    def build(self, user_input: str) -> ChainPlan | None:
        """Build a chain plan from natural language."""
        # Split into sub-tasks
        parts = CHAIN_SPLITTER.split(user_input)
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) < 2:
            return None

        steps = []
        for i, part in enumerate(parts):
            # Try to translate each part
            command = part
            description = part

            if self.translator:
                try:
                    result = self.translator.translate(part)
                    if result.command:
                        command = result.command
                        description = result.explanation or part
                except Exception:
                    pass

            steps.append(ChainStep(
                order=i + 1,
                command=command,
                description=description,
                condition="on_success" if i > 0 else "always",
            ))

        return ChainPlan(
            steps=steps,
            description=f"Chain: {user_input[:60]}...",
            abort_on_failure=True,
            source="pattern",
        )

    def build_with_llm(self, user_input: str) -> ChainPlan | None:
        """Use LLM for complex chain planning."""
        if not self.llm:
            return self.build(user_input)

        system_prompt = (
            "You are a shell command planner. Break the user's request into sequential shell commands.\n"
            f"OS: {os.name}, Shell: {'powershell' if os.name == 'nt' else 'bash'}\n"
            "Respond as JSON: {\"steps\": [{\"command\": \"...\", \"description\": \"...\"}]}"
        )

        result = self.llm.generate_json(user_input, system_prompt)
        if not result or "steps" not in result:
            return self.build(user_input)

        steps = []
        for i, step_data in enumerate(result["steps"]):
            steps.append(ChainStep(
                order=i + 1,
                command=step_data.get("command", ""),
                description=step_data.get("description", ""),
                condition="on_success" if i > 0 else "always",
            ))

        return ChainPlan(
            steps=steps,
            description=f"LLM Plan: {user_input[:60]}...",
            abort_on_failure=True,
            source="llm",
        )
