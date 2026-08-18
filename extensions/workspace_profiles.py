# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Workspace Profiles
Per-directory configuration overrides for different project types.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from config import NEUROSHELL_DIR
from observability.logger import StructuredLogger

PROFILES_DIR = NEUROSHELL_DIR / "profiles"


@dataclass
class WorkspaceProfile:
    """A workspace-specific configuration profile."""
    name: str
    directory: str
    shell: str = ""              # Override default shell
    aliases: dict = field(default_factory=dict)  # Custom aliases
    env_vars: dict = field(default_factory=dict)  # Extra env vars
    startup_commands: list[str] = field(default_factory=list)
    blocked_commands: list[str] = field(default_factory=list)
    plugins: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "directory": self.directory,
            "shell": self.shell,
            "aliases": self.aliases,
            "env_vars": self.env_vars,
            "startup_commands": self.startup_commands,
            "blocked_commands": self.blocked_commands,
            "plugins": self.plugins,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkspaceProfile":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class WorkspaceProfileManager:
    """Manages per-directory workspace profiles."""

    def __init__(self):
        self._profiles: dict[str, WorkspaceProfile] = {}
        self._active: WorkspaceProfile | None = None
        self._logger = StructuredLogger("profiles")
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        self._load_all()

    def _load_all(self):
        """Load all saved profiles."""
        for file in PROFILES_DIR.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                profile = WorkspaceProfile.from_dict(data)
                self._profiles[profile.directory] = profile
            except Exception:
                pass

    def create(self, name: str, directory: str, **kwargs) -> WorkspaceProfile:
        """Create a new workspace profile."""
        directory = str(Path(directory).resolve())
        profile = WorkspaceProfile(name=name, directory=directory, **kwargs)
        self._profiles[directory] = profile
        self._save(profile)
        self._logger.info("profile_created", name=name, directory=directory)
        return profile

    def get(self, directory: str) -> WorkspaceProfile | None:
        """Get profile for a directory (checks parents too)."""
        directory = str(Path(directory).resolve())

        # Exact match
        if directory in self._profiles:
            return self._profiles[directory]

        # Check parent directories
        path = Path(directory)
        for parent in path.parents:
            parent_str = str(parent)
            if parent_str in self._profiles:
                return self._profiles[parent_str]

        return None

    def activate(self, directory: str) -> WorkspaceProfile | None:
        """Activate profile for current directory."""
        profile = self.get(directory)
        if profile:
            self._active = profile
            self._logger.info("profile_activated", name=profile.name)
        return profile

    def get_active(self) -> WorkspaceProfile | None:
        """Get currently active profile."""
        return self._active

    def update(self, directory: str, **kwargs) -> bool:
        """Update an existing profile."""
        profile = self._profiles.get(str(Path(directory).resolve()))
        if not profile:
            return False

        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        self._save(profile)
        return True

    def delete(self, directory: str) -> bool:
        """Delete a profile."""
        directory = str(Path(directory).resolve())
        if directory not in self._profiles:
            return False

        del self._profiles[directory]

        # Remove file
        safe_name = directory.replace(":", "").replace("\\", "_").replace("/", "_")
        file = PROFILES_DIR / f"{safe_name}.json"
        file.unlink(missing_ok=True)
        return True

    def list_all(self) -> list[dict]:
        """List all profiles."""
        return [p.to_dict() for p in self._profiles.values()]

    def resolve_alias(self, command: str) -> str:
        """Resolve command alias from active profile."""
        if not self._active:
            return command

        first_word = command.strip().split()[0]
        if first_word in self._active.aliases:
            replacement = self._active.aliases[first_word]
            return command.replace(first_word, replacement, 1)
        return command

    def is_blocked(self, command: str) -> bool:
        """Check if command is blocked in active profile."""
        if not self._active:
            return False
        return any(blocked in command for blocked in self._active.blocked_commands)

    def _save(self, profile: WorkspaceProfile):
        """Save profile to disk."""
        safe_name = profile.directory.replace(":", "").replace("\\", "_").replace("/", "_")
        file = PROFILES_DIR / f"{safe_name}.json"
        file.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
