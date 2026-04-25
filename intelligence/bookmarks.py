# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Command Bookmarks & Snippets
Save, recall, and manage favorite commands with variable substitution.
Commands: !save, !run, !list, !delete
"""

import time
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Bookmark:
    """A saved command bookmark."""
    name: str
    command: str
    description: str = ""
    created: float = 0
    use_count: int = 0
    tags: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)  # extracted {var} placeholders

    def display(self) -> str:
        tags_str = f" [{', '.join(self.tags)}]" if self.tags else ""
        vars_str = f" (vars: {', '.join(self.variables)})" if self.variables else ""
        return f"  📌 {self.name}{tags_str}: {self.command}{vars_str}"


class BookmarkManager:
    """Manage command bookmarks with SQLite storage."""

    def __init__(self, history_store=None):
        self.history = history_store
        self._bookmarks: dict[str, Bookmark] = {}
        self._load_from_aliases()

    def _load_from_aliases(self):
        """Load bookmarks from existing alias storage."""
        if self.history:
            try:
                aliases = self.history.list_aliases()
                for name, expansion, created, use_count in aliases:
                    variables = re.findall(r'\{(\w+)\}', expansion)
                    self._bookmarks[name] = Bookmark(
                        name=name, command=expansion,
                        created=created, use_count=use_count,
                        variables=variables,
                    )
            except Exception:
                pass

    def save(self, name: str, command: str, description: str = "") -> Bookmark:
        """Save a new bookmark."""
        variables = re.findall(r'\{(\w+)\}', command)
        bookmark = Bookmark(
            name=name, command=command, description=description,
            created=time.time(), variables=variables,
        )
        self._bookmarks[name] = bookmark

        # Persist via history aliases
        if self.history:
            try:
                self.history.set_alias(name, command)
            except Exception:
                pass

        return bookmark

    def run(self, name: str, variables: dict = None) -> Optional[str]:
        """Get a bookmark's command, with variable substitution."""
        bookmark = self._bookmarks.get(name)
        if not bookmark:
            # Try alias store
            if self.history:
                cmd = self.history.get_alias(name)
                if cmd:
                    return cmd
            return None

        command = bookmark.command
        bookmark.use_count += 1

        # Variable substitution
        if variables:
            for key, value in variables.items():
                command = command.replace(f"{{{key}}}", str(value))

        return command

    def delete(self, name: str) -> bool:
        """Delete a bookmark."""
        if name in self._bookmarks:
            del self._bookmarks[name]
            if self.history:
                try:
                    self.history.remove_alias(name)
                except Exception:
                    pass
            return True
        return False

    def list_all(self) -> list[Bookmark]:
        """List all bookmarks."""
        return sorted(self._bookmarks.values(), key=lambda b: b.use_count, reverse=True)

    def search(self, query: str) -> list[Bookmark]:
        """Search bookmarks by name or command content."""
        query = query.lower()
        return [
            b for b in self._bookmarks.values()
            if query in b.name.lower() or query in b.command.lower()
        ]

    def parse_command(self, user_input: str) -> tuple[str, dict]:
        """
        Parse a bookmark command like '!run deploy branch=main'.
        Returns (action, params_dict).
        """
        parts = user_input.strip().split()
        if not parts:
            return "", {}

        action = parts[0].lstrip("!")

        if action == "save" and len(parts) >= 3:
            name = parts[1]
            command = " ".join(parts[2:])
            return "save", {"name": name, "command": command}

        elif action == "run" and len(parts) >= 2:
            name = parts[1]
            variables = {}
            for part in parts[2:]:
                if "=" in part:
                    key, value = part.split("=", 1)
                    variables[key] = value
            return "run", {"name": name, "variables": variables}

        elif action == "delete" and len(parts) >= 2:
            return "delete", {"name": parts[1]}

        elif action == "list":
            return "list", {}

        return action, {}
