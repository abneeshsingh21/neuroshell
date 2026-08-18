# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Auto-Documentation Generator
Generates markdown docs from command history, patterns, and session logs.
"""

import time

from config import NEUROSHELL_DIR

DOCS_DIR = NEUROSHELL_DIR / "docs"


class AutoDocsGenerator:
    """Generates documentation from user's command patterns and history."""

    def __init__(self, history_store, pattern_learner):
        self.history = history_store
        self.patterns = pattern_learner
        DOCS_DIR.mkdir(parents=True, exist_ok=True)

    def generate_cheatsheet(self, cwd: str = "", limit: int = 50) -> str:
        """Generate a command cheatsheet from frequent commands."""
        frequent = self.history.get_frequent(limit)
        if not frequent:
            return "No command history yet."

        lines = [
            "# NeuroShell Command Cheatsheet",
            f"_Generated: {time.strftime('%Y-%m-%d %H:%M')}_\n",
        ]

        # Group by category (first word of command)
        categories: dict[str, list] = {}
        for cmd, count in frequent:
            first_word = cmd.strip().split()[0]
            if first_word not in categories:
                categories[first_word] = []
            categories[first_word].append((cmd, count))

        for category, cmds in sorted(categories.items()):
            lines.append(f"\n## {category}")
            lines.append("| Command | Uses |")
            lines.append("|---------|------|")
            for cmd, count in sorted(cmds, key=lambda x: x[1], reverse=True):
                lines.append(f"| `{cmd}` | {count} |")

        return "\n".join(lines)

    def generate_workflow_doc(self) -> str:
        """Generate workflow documentation from learned patterns."""
        self.patterns.learn_from_history()
        patterns = self.patterns.get_patterns(min_frequency=2)

        if not patterns:
            return "No patterns detected yet. Keep using NeuroShell!"

        lines = [
            "# Detected Workflows",
            f"_Generated: {time.strftime('%Y-%m-%d %H:%M')}_\n",
        ]

        # Sequence patterns
        sequences = [p for p in patterns if p.pattern_type == "sequence"]
        if sequences:
            lines.append("\n## Common Command Sequences\n")
            for i, p in enumerate(sequences[:20], 1):
                lines.append(f"{i}. `{p.data['first']}` → `{p.data['then']}` ({p.frequency}x)")

        # Directory patterns
        dir_patterns = [p for p in patterns if p.pattern_type == "directory"]
        if dir_patterns:
            lines.append("\n## Directory-Specific Commands\n")
            current_dir = ""
            for p in dir_patterns[:20]:
                d = p.data.get("cwd", "")
                if d != current_dir:
                    lines.append(f"\n### `{d}`")
                    current_dir = d
                lines.append(f"- `{p.data['command']}` ({p.frequency}x)")

        return "\n".join(lines)

    def generate_error_playbook(self) -> str:
        """Generate error fix playbook from cached solutions."""
        fixes = self.history.get_all_fixes()
        if not fixes:
            return "No error fixes recorded yet."

        lines = [
            "# Error Fix Playbook",
            f"_Generated: {time.strftime('%Y-%m-%d %H:%M')}_\n",
        ]

        for fix in fixes[:30]:
            lines.append("\n### Error Pattern")
            lines.append(f"**Error:** `{fix.get('error_preview', '')[:100]}`")
            lines.append(f"**Fix:** `{fix.get('fix_command', '')}`")
            lines.append(f"**Source:** {fix.get('source', '')} | **Successes:** {fix.get('success_count', 0)}")
            lines.append("---")

        return "\n".join(lines)

    def save_doc(self, content: str, filename: str) -> str:
        """Save generated documentation to file."""
        file_path = DOCS_DIR / filename
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def generate_all(self) -> dict[str, str]:
        """Generate all docs and return file paths."""
        docs = {}

        cheatsheet = self.generate_cheatsheet()
        docs["cheatsheet"] = self.save_doc(cheatsheet, "cheatsheet.md")

        workflows = self.generate_workflow_doc()
        docs["workflows"] = self.save_doc(workflows, "workflows.md")

        playbook = self.generate_error_playbook()
        docs["error_playbook"] = self.save_doc(playbook, "error_playbook.md")

        return docs
