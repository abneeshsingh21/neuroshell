# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Command Alias Manager
Persistent alias system for custom command shortcuts.
Supports alias/unalias/list with JSON persistence.
"""

import json
import os
from dataclasses import dataclass

from config import NEUROSHELL_DIR

ALIASES_FILE = NEUROSHELL_DIR / "aliases.json"


@dataclass
class AliasEntry:
    """A single alias definition."""
    name: str
    command: str
    description: str = ""
    usage_count: int = 0


class AliasManager:
    """
    Manages command aliases with persistence.

    Features:
    - Add, remove, and list custom aliases
    - Expand aliases before command execution
    - Built-in aliases for common patterns
    - Persistent storage in ~/.neuroshell/aliases.json
    - Usage tracking per alias
    """

    # Built-in default aliases
    DEFAULTS = {
        "ll": "ls -la",
        "la": "ls -A",
        "gs": "git status",
        "gp": "git push",
        "gl": "git log --oneline -10",
        "gd": "git diff",
        "ga": "git add .",
        "gc": "git commit -m",
        "gco": "git checkout",
        "gb": "git branch",
        "cls": "clear",
        "py": "python",
        "py3": "python3",
        "ipy": "ipython",
        "pir": "pip install -r requirements.txt",
        "venv": "python -m venv .venv",
        "activate": ".venv\\Scripts\\activate" if os.name == "nt" else "source .venv/bin/activate",
        "serve": "python -m http.server 8000",
        "ports": "netstat -tlnp" if os.name != "nt" else "netstat -ano",
        "myip": "curl -s ifconfig.me",
        "tree": "tree /F" if os.name == "nt" else "tree -L 2",
    }

    def __init__(self, load_defaults: bool = True):
        self._aliases: dict[str, AliasEntry] = {}
        self._load()

        # Add defaults if first run (empty file)
        if load_defaults and not self._aliases:
            for name, cmd in self.DEFAULTS.items():
                self._aliases[name] = AliasEntry(name=name, command=cmd, description="built-in")
            self._save()

    # ── Public API ──

    def add(self, name: str, command: str, description: str = "") -> bool:
        """
        Add or update an alias.
        Returns True if added, False if name conflicts with a shell built-in.
        """
        name = name.strip().lower()
        if not name or not command.strip():
            return False

        # Prevent recursive aliases
        if command.strip().split()[0] == name:
            return False

        self._aliases[name] = AliasEntry(
            name=name,
            command=command.strip(),
            description=description,
        )
        self._save()
        return True

    def remove(self, name: str) -> bool:
        """Remove an alias. Returns True if it existed."""
        name = name.strip().lower()
        if name in self._aliases:
            del self._aliases[name]
            self._save()
            return True
        return False

    def get(self, name: str) -> str | None:
        """Get the command for an alias, or None."""
        entry = self._aliases.get(name.strip().lower())
        return entry.command if entry else None

    def expand(self, input_cmd: str) -> str:
        """
        Expand the first word of a command if it's an alias.
        Returns the expanded command or the original if no alias matches.
        """
        parts = input_cmd.strip().split(None, 1)
        if not parts:
            return input_cmd

        first_word = parts[0].lower()
        entry = self._aliases.get(first_word)

        if entry:
            entry.usage_count += 1
            rest = parts[1] if len(parts) > 1 else ""
            expanded = f"{entry.command} {rest}".strip()
            return expanded

        return input_cmd

    def list_all(self) -> list[AliasEntry]:
        """Get all aliases sorted by name."""
        return sorted(self._aliases.values(), key=lambda a: a.name)

    def has_alias(self, name: str) -> bool:
        """Check if an alias exists."""
        return name.strip().lower() in self._aliases

    def get_formatted_list(self) -> str:
        """Get a formatted display of all aliases."""
        aliases = self.list_all()
        if not aliases:
            return "No aliases defined. Use 'alias <name>=<command>' to create one."

        lines = ["\n📋 Command Aliases:\n"]
        max_name = max(len(a.name) for a in aliases)
        for a in aliases:
            usage = f"({a.usage_count}x)" if a.usage_count > 0 else ""
            lines.append(f"  {a.name:<{max_name + 2}} → {a.command} {usage}")

        lines.append(f"\n  Total: {len(aliases)} aliases")
        return "\n".join(lines)

    def reset_to_defaults(self):
        """Reset aliases to built-in defaults only."""
        self._aliases.clear()
        for name, cmd in self.DEFAULTS.items():
            self._aliases[name] = AliasEntry(name=name, command=cmd, description="built-in")
        self._save()

    # ── Persistence ──

    def _save(self):
        """Save aliases to disk."""
        NEUROSHELL_DIR.mkdir(parents=True, exist_ok=True)
        data = {}
        for name, entry in self._aliases.items():
            data[name] = {
                "command": entry.command,
                "description": entry.description,
                "usage_count": entry.usage_count,
            }
        try:
            ALIASES_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load(self):
        """Load aliases from disk."""
        if not ALIASES_FILE.exists():
            return
        try:
            data = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
            for name, info in data.items():
                self._aliases[name] = AliasEntry(
                    name=name,
                    command=info.get("command", ""),
                    description=info.get("description", ""),
                    usage_count=info.get("usage_count", 0),
                )
        except Exception:
            pass

    @property
    def count(self) -> int:
        return len(self._aliases)
