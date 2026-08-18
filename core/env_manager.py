# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Environment Variable Manager
View, set, unset, and search environment variables from the REPL.
"""

import os
import re
from dataclasses import dataclass


@dataclass
class EnvVar:
    """An environment variable entry."""
    name: str
    value: str
    source: str = "system"  # system, session, user


class EnvManager:
    """
    Environment variable manager for the REPL.

    Features:
    - View all or filtered environment variables
    - Set/unset variables within the session
    - Search variables by name or value
    - Track session-modified variables
    - Format output for display
    """

    def __init__(self):
        self._session_vars: dict[str, str] = {}  # Vars set during this session
        self._unset_vars: set[str] = set()  # Vars unset during this session

    def get(self, name: str) -> str | None:
        """Get an environment variable value."""
        name = name.upper()
        if name in self._unset_vars:
            return None
        if name in self._session_vars:
            return self._session_vars[name]
        return os.environ.get(name)

    def set_var(self, name: str, value: str) -> bool:
        """Set an environment variable for the current session."""
        name = name.strip()
        if not name:
            return False

        os.environ[name] = value
        self._session_vars[name] = value
        self._unset_vars.discard(name)
        return True

    def unset_var(self, name: str) -> bool:
        """Unset an environment variable."""
        name = name.strip()
        if name in os.environ:
            del os.environ[name]
            self._unset_vars.add(name)
            self._session_vars.pop(name, None)
            return True
        return False

    def search(self, query: str) -> list[EnvVar]:
        """Search environment variables by name or value (case-insensitive)."""
        query_lower = query.lower()
        results = []

        for name, value in sorted(os.environ.items()):
            if name in self._unset_vars:
                continue
            if query_lower in name.lower() or query_lower in value.lower():
                source = "session" if name in self._session_vars else "system"
                results.append(EnvVar(name=name, value=value, source=source))

        return results

    def list_all(self, filter_pattern: str = "") -> list[EnvVar]:
        """List all environment variables, optionally filtered by name pattern."""
        env_vars = []

        for name, value in sorted(os.environ.items()):
            if name in self._unset_vars:
                continue
            if filter_pattern and filter_pattern.lower() not in name.lower():
                continue
            source = "session" if name in self._session_vars else "system"
            env_vars.append(EnvVar(name=name, value=value, source=source))

        return env_vars

    def get_session_changes(self) -> dict:
        """Get all variables changed in this session."""
        return {
            "set": dict(self._session_vars),
            "unset": list(self._unset_vars),
        }

    def get_formatted_list(self, filter_pattern: str = "", max_value_len: int = 80) -> str:
        """Get a formatted display of environment variables."""
        env_vars = self.list_all(filter_pattern)

        if not env_vars:
            if filter_pattern:
                return f"No environment variables matching '{filter_pattern}'"
            return "No environment variables found."

        lines = [f"\n🔧 Environment Variables ({len(env_vars)} total):\n"]

        for var in env_vars:
            value_display = var.value
            if len(value_display) > max_value_len:
                value_display = value_display[:max_value_len] + "..."
            marker = " 🔸" if var.source == "session" else ""
            lines.append(f"  {var.name}={value_display}{marker}")

        session_count = sum(1 for v in env_vars if v.source == "session")
        if session_count:
            lines.append(f"\n  🔸 = modified this session ({session_count} changes)")

        return "\n".join(lines)

    def get_formatted_var(self, name: str) -> str:
        """Get formatted display of a single variable."""
        value = self.get(name)
        if value is None:
            return f"❌ '{name}' is not set"

        source = "session" if name in self._session_vars else "system"
        lines = [
            f"\n🔧 {name}",
            f"   Value:  {value}",
            f"   Source: {source}",
        ]

        # Special formatting for PATH-like variables
        if name.upper() in ("PATH", "PYTHONPATH", "NODE_PATH", "CLASSPATH"):
            sep = ";" if os.name == "nt" else ":"
            paths = value.split(sep)
            lines.append(f"   Entries ({len(paths)}):")
            for i, p in enumerate(paths[:20], 1):
                lines.append(f"     {i:2}. {p}")
            if len(paths) > 20:
                lines.append(f"     ... and {len(paths) - 20} more")

        return "\n".join(lines)

    def parse_set_command(self, input_str: str) -> tuple[str, str] | None:
        """Parse 'KEY=VALUE' or 'KEY VALUE' format."""
        # Try KEY=VALUE format
        match = re.match(r'^(\w+)=(.*)$', input_str.strip())
        if match:
            return match.group(1), match.group(2)

        # Try KEY VALUE format
        parts = input_str.strip().split(None, 1)
        if len(parts) == 2:
            return parts[0], parts[1]

        return None

    @property
    def session_change_count(self) -> int:
        return len(self._session_vars) + len(self._unset_vars)
