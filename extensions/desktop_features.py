# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Desktop App Features
Command Palette, Snippet Manager, Theme Engine, Notebook Mode, Diff Preview, Autocomplete.
"""

import re
import os
import json
import time
import logging
import platform
import subprocess
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger("neuroshell.desktop")


# ═══════════════════════════════════════════════════════════
# Command Palette (Ctrl+P searchable command list)
# ═══════════════════════════════════════════════════════════

@dataclass
class PaletteEntry:
    """A searchable command in the palette."""
    name: str
    command: str
    category: str
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    score: float = 0  # search relevance


class CommandPalette:
    """Ctrl+P searchable palette of all 350+ patterns."""

    def __init__(self):
        self._entries: list[PaletteEntry] = []
        self._build_default_palette()

    def _build_default_palette(self):
        """Build palette from common commands."""
        commands = [
            ("List files", "ls -la", "Files", "Show all files including hidden", ["dir", "list"]),
            ("Find file by name", "find . -name '{name}'", "Files", "Search for file recursively", ["search", "locate"]),
            ("Disk usage", "du -sh *", "System", "Show folder sizes", ["size", "space"]),
            ("Free disk space", "df -h", "System", "Show available disk space", ["storage"]),
            ("Running processes", "ps aux", "System", "List all running processes", ["task", "proc"]),
            ("Kill process", "kill -9 {pid}", "System", "Force kill a process by PID", ["stop", "end"]),
            ("Process on port", "lsof -i :{port}", "Network", "Find process using a port", ["port", "listen"]),
            ("Check open ports", "netstat -tulpn", "Network", "List all listening ports", ["listen", "socket"]),
            ("Ping host", "ping {host}", "Network", "Test network connectivity", ["test", "connection"]),
            ("DNS lookup", "nslookup {domain}", "Network", "Resolve domain to IP", ["resolve"]),
            ("Git status", "git status", "Git", "Show working tree status", ["changes", "modified"]),
            ("Git log graph", "git log --oneline --graph --all", "Git", "Visual commit history", ["history", "tree"]),
            ("Git stash", "git stash", "Git", "Save uncommitted changes temporarily", ["save", "temp"]),
            ("Git diff", "git diff", "Git", "Show unstaged changes", ["changes", "compare"]),
            ("Docker containers", "docker ps", "Docker", "List running containers", ["running"]),
            ("Docker logs", "docker logs {container}", "Docker", "View container output", ["output"]),
            ("Docker cleanup", "docker system prune -f", "Docker", "Remove unused resources", ["clean", "prune"]),
            ("Install Python package", "pip install {package}", "Python", "Install from PyPI", ["pip", "add"]),
            ("Create virtual env", "python -m venv .venv", "Python", "Create isolated environment", ["venv", "virtualenv"]),
            ("Run tests", "python -m pytest -v", "Python", "Execute test suite", ["test", "pytest"]),
            ("NPM install", "npm install", "Node.js", "Install dependencies", ["add", "deps"]),
            ("NPM audit", "npm audit", "Node.js", "Check for vulnerabilities", ["security", "scan"]),
            ("System info", "uname -a", "System", "Show OS and kernel info", ["os", "kernel"]),
            ("Memory usage", "free -h", "System", "Show RAM usage", ["ram", "mem"]),
            ("CPU info", "lscpu", "System", "Show processor details", ["processor"]),
            ("Compress folder", "tar -czf archive.tar.gz {folder}", "Files", "Create gzip archive", ["zip", "tar"]),
            ("Extract archive", "tar -xzf {archive}", "Files", "Extract gzip archive", ["unzip", "decompress"]),
            ("SSH connect", "ssh {user}@{host}", "Network", "Remote shell login", ["remote", "connect"]),
            ("SCP copy", "scp {file} {user}@{host}:{path}", "Network", "Copy file to remote", ["transfer", "upload"]),
            ("Encrypt file", "openssl enc -aes-256-cbc -salt -in {file} -out {file}.enc", "Security", "AES encrypt", ["cipher"]),
            ("SHA256 hash", "sha256sum {file}", "Security", "File integrity check", ["checksum", "verify"]),
            ("Check SSL cert", "openssl s_client -connect {host}:443", "Security", "Verify SSL certificate", ["tls", "https"]),
            ("AWS S3 list", "aws s3 ls", "Cloud", "List S3 buckets", ["storage", "bucket"]),
            ("AWS EC2 list", "aws ec2 describe-instances --output table", "Cloud", "List EC2 instances", ["server", "vm"]),
            ("Terraform plan", "terraform plan", "Cloud", "Preview infrastructure changes", ["infra", "iac"]),
            ("K8s pods", "kubectl get pods", "Cloud", "List Kubernetes pods", ["kubernetes", "container"]),
        ]
        for name, cmd, cat, desc, kw in commands:
            self._entries.append(PaletteEntry(name=name, command=cmd, category=cat, description=desc, keywords=kw))

    def search(self, query: str, limit: int = 10) -> list[PaletteEntry]:
        """Fuzzy search palette entries."""
        if not query.strip():
            return self._entries[:limit]

        q = query.lower().strip()
        results = []
        for entry in self._entries:
            score = 0
            name_lower = entry.name.lower()
            if q in name_lower:
                score += 3
            if q in entry.command.lower():
                score += 2
            if q in entry.category.lower():
                score += 1
            if any(q in kw for kw in entry.keywords):
                score += 2
            if q in entry.description.lower():
                score += 1
            if score > 0:
                entry.score = score
                results.append(entry)

        results.sort(key=lambda e: e.score, reverse=True)
        return results[:limit]

    def add(self, name: str, command: str, category: str = "Custom", description: str = "", keywords: list[str] = None):
        self._entries.append(PaletteEntry(name=name, command=command, category=category, description=description, keywords=keywords or []))

    @property
    def count(self) -> int:
        return len(self._entries)


# ═══════════════════════════════════════════════════════════
# Snippet Manager
# ═══════════════════════════════════════════════════════════

@dataclass
class Snippet:
    name: str
    command: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    use_count: int = 0


class SnippetManager:
    """Save, organize, and share command snippets."""

    def __init__(self, config_dir: Optional[Path] = None):
        self._dir = config_dir or Path.home() / ".neuroshell"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "snippets.json"
        self._snippets: dict[str, Snippet] = {}
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                for k, v in data.items():
                    self._snippets[k] = Snippet(**v)
            except Exception:
                pass

    def _save(self):
        try:
            self._file.write_text(json.dumps({k: asdict(v) for k, v in self._snippets.items()}, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Snippet save failed: %s", e)

    def save(self, name: str, command: str, description: str = "", tags: list[str] = None) -> Snippet:
        s = Snippet(name=name, command=command, description=description, tags=tags or [])
        self._snippets[name] = s
        self._save()
        return s

    def get(self, name: str) -> Optional[Snippet]:
        s = self._snippets.get(name)
        if s:
            s.use_count += 1
            self._save()
        return s

    def search(self, query: str) -> list[Snippet]:
        q = query.lower()
        return [s for s in self._snippets.values() if q in s.name.lower() or q in s.description.lower() or any(q in t for t in s.tags)]

    def list_all(self) -> list[Snippet]:
        return sorted(self._snippets.values(), key=lambda s: s.use_count, reverse=True)

    def delete(self, name: str) -> bool:
        if name in self._snippets:
            del self._snippets[name]
            self._save()
            return True
        return False

    def export_json(self) -> str:
        return json.dumps({k: asdict(v) for k, v in self._snippets.items()}, indent=2)

    def import_json(self, data: str) -> int:
        try:
            imported = json.loads(data)
            count = 0
            for k, v in imported.items():
                if k not in self._snippets:
                    self._snippets[k] = Snippet(**v)
                    count += 1
            self._save()
            return count
        except Exception:
            return 0


# ═══════════════════════════════════════════════════════════
# Theme Engine
# ═══════════════════════════════════════════════════════════

BUILT_IN_THEMES = {
    "cyberpunk": {
        "name": "Cyberpunk", "primary": "#ff00ff", "secondary": "#00ffff",
        "bg": "#0d0d0d", "text": "#e0e0e0", "accent": "#ff6ec7",
        "error": "#ff4444", "success": "#00ff88", "warning": "#ffaa00",
        "prompt_icon": "⚡", "border_style": "bold magenta",
    },
    "nord": {
        "name": "Nord", "primary": "#88c0d0", "secondary": "#81a1c1",
        "bg": "#2e3440", "text": "#eceff4", "accent": "#8fbcbb",
        "error": "#bf616a", "success": "#a3be8c", "warning": "#ebcb8b",
        "prompt_icon": "❄️", "border_style": "bold blue",
    },
    "dracula": {
        "name": "Dracula", "primary": "#bd93f9", "secondary": "#ff79c6",
        "bg": "#282a36", "text": "#f8f8f2", "accent": "#50fa7b",
        "error": "#ff5555", "success": "#50fa7b", "warning": "#f1fa8c",
        "prompt_icon": "🧛", "border_style": "bold purple",
    },
    "solarized": {
        "name": "Solarized", "primary": "#268bd2", "secondary": "#2aa198",
        "bg": "#002b36", "text": "#839496", "accent": "#b58900",
        "error": "#dc322f", "success": "#859900", "warning": "#b58900",
        "prompt_icon": "☀️", "border_style": "bold cyan",
    },
    "matrix": {
        "name": "Matrix", "primary": "#00ff00", "secondary": "#008000",
        "bg": "#000000", "text": "#00ff00", "accent": "#00cc00",
        "error": "#ff0000", "success": "#00ff00", "warning": "#ffff00",
        "prompt_icon": "🟢", "border_style": "bold green",
    },
    "ocean": {
        "name": "Ocean", "primary": "#0077b6", "secondary": "#00b4d8",
        "bg": "#03045e", "text": "#caf0f8", "accent": "#90e0ef",
        "error": "#e63946", "success": "#06d6a0", "warning": "#ffd166",
        "prompt_icon": "🌊", "border_style": "bold cyan",
    },
}


class ThemeEngine:
    """Manage and apply terminal themes."""

    def __init__(self, config_dir: Optional[Path] = None):
        self._dir = config_dir or Path.home() / ".neuroshell"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._config_file = self._dir / "theme.json"
        self._current = "cyberpunk"
        self._custom_themes: dict = {}
        self._load()

    def _load(self):
        if self._config_file.exists():
            try:
                data = json.loads(self._config_file.read_text(encoding="utf-8"))
                self._current = data.get("current", "cyberpunk")
                self._custom_themes = data.get("custom", {})
            except Exception:
                pass

    def _save(self):
        self._config_file.write_text(json.dumps({"current": self._current, "custom": self._custom_themes}, indent=2), encoding="utf-8")

    def set_theme(self, name: str) -> bool:
        if name in BUILT_IN_THEMES or name in self._custom_themes:
            self._current = name
            self._save()
            return True
        return False

    def get_theme(self) -> dict:
        return BUILT_IN_THEMES.get(self._current) or self._custom_themes.get(self._current) or BUILT_IN_THEMES["cyberpunk"]

    def list_themes(self) -> list[str]:
        return list(BUILT_IN_THEMES.keys()) + list(self._custom_themes.keys())

    def create_theme(self, name: str, colors: dict):
        self._custom_themes[name] = colors
        self._save()

    @property
    def current_name(self) -> str:
        return self._current


# ═══════════════════════════════════════════════════════════
# Notebook Mode (Jupyter-like for terminal)
# ═══════════════════════════════════════════════════════════

@dataclass
class NotebookCell:
    cell_type: str  # "command" or "markdown"
    content: str
    output: str = ""
    exit_code: int = 0
    duration_ms: float = 0
    timestamp: float = field(default_factory=time.time)


class NotebookMode:
    """Mix commands + notes + outputs in a shareable document."""

    def __init__(self):
        self.cells: list[NotebookCell] = []
        self.title: str = "NeuroShell Notebook"
        self.created_at: float = time.time()

    def add_command(self, command: str, output: str = "", exit_code: int = 0, duration_ms: float = 0):
        self.cells.append(NotebookCell(cell_type="command", content=command, output=output, exit_code=exit_code, duration_ms=duration_ms))

    def add_note(self, text: str):
        self.cells.append(NotebookCell(cell_type="markdown", content=text))

    def export_markdown(self) -> str:
        """Export notebook as shareable Markdown."""
        lines = [f"# {self.title}", f"*Generated by NeuroShell on {time.strftime('%Y-%m-%d %H:%M')}*", ""]
        for i, cell in enumerate(self.cells, 1):
            if cell.cell_type == "markdown":
                lines.append(cell.content)
                lines.append("")
            else:
                icon = "✅" if cell.exit_code == 0 else "❌"
                lines.append(f"### Cell {i} {icon} ({cell.duration_ms:.0f}ms)")
                lines.append(f"```bash\n$ {cell.content}\n```")
                if cell.output:
                    lines.append(f"```\n{cell.output[:2000]}\n```")
                lines.append("")
        return "\n".join(lines)

    def save(self, path: Path):
        path.write_text(self.export_markdown(), encoding="utf-8")

    def load_json(self, path: Path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.title = data.get("title", self.title)
            self.cells = [NotebookCell(**c) for c in data.get("cells", [])]
        except Exception as e:
            logger.warning("Notebook load failed: %s", e)


# ═══════════════════════════════════════════════════════════
# Diff Preview Mode
# ═══════════════════════════════════════════════════════════

class DiffPreview:
    """Preview what a command would do before executing it."""

    DRY_RUN_MAP = {
        r"^rm\s": ("rm -i", "Will ask before each deletion"),
        r"^rsync\s": ("{cmd} --dry-run", "Shows what would be transferred"),
        r"^mv\s": ("{cmd} -i", "Will ask before overwriting"),
        r"^cp\s": ("{cmd} -i", "Will ask before overwriting"),
        r"^apt\s+(?:install|remove)": ("{cmd} --simulate", "Shows what would be installed/removed"),
        r"^pip\s+install": ("{cmd} --dry-run", "Shows what would be installed"),
        r"^npm\s+install": ("{cmd} --dry-run", "Shows what would be installed"),
        r"^docker\s+system\s+prune": ("docker system df", "Shows disk usage instead of pruning"),
        r"^git\s+push": ("git push --dry-run", "Shows what would be pushed"),
        r"^git\s+clean": ("git clean -n", "Shows what would be removed"),
        r"^terraform\s+apply": ("terraform plan", "Shows planned changes without applying"),
        r"^kubectl\s+delete": ("{cmd} --dry-run=client", "Shows what would be deleted"),
        r"^chmod\s": ("ls -la {target}", "Shows current permissions"),
        r"^chown\s": ("ls -la {target}", "Shows current ownership"),
    }

    WINDOWS_DRY_RUN = {
        r"^del\s": ("dir {target}", "Shows files that would be deleted"),
        r"^rmdir\s": ("dir /s {target}", "Shows directory contents"),
        r"^robocopy\s": ("{cmd} /L", "Lists files that would be copied"),
        r"^move\s": ("dir {target}", "Shows file that would be moved"),
    }

    def __init__(self):
        self.is_windows = platform.system() == "Windows"

    def get_preview(self, command: str) -> Optional[tuple[str, str]]:
        """Return (preview_command, explanation) or None."""
        maps = {**self.DRY_RUN_MAP, **(self.WINDOWS_DRY_RUN if self.is_windows else {})}
        for pattern, (template, explanation) in maps.items():
            if re.search(pattern, command.strip(), re.IGNORECASE):
                parts = command.strip().split()
                target = parts[-1] if len(parts) > 1 else ""
                preview_cmd = template.replace("{cmd}", command).replace("{target}", target)
                return preview_cmd, explanation
        return None


# ═══════════════════════════════════════════════════════════
# Smart Autocomplete
# ═══════════════════════════════════════════════════════════

class SmartAutocomplete:
    """AI-powered tab completion based on context and history."""

    def __init__(self, memory=None, palette=None):
        self._memory = memory
        self._palette = palette
        # Trie for fast prefix matching
        self._common_commands = [
            "git status", "git add .", "git commit -m", "git push", "git pull",
            "git log --oneline", "git branch", "git checkout", "git stash",
            "docker ps", "docker logs", "docker build", "docker compose up",
            "npm install", "npm start", "npm test", "npm run build",
            "pip install", "pip freeze", "python -m pytest",
            "ls -la", "cd ..", "cat", "grep -r", "find . -name",
            "kubectl get pods", "kubectl logs", "kubectl apply -f",
            "terraform plan", "terraform apply", "terraform init",
            "aws s3 ls", "aws ec2 describe-instances",
            "systemctl status", "systemctl restart",
        ]

    def complete(self, partial: str, cwd: str = ".", limit: int = 8) -> list[str]:
        """Return completion suggestions."""
        if not partial.strip():
            return []

        p = partial.lower().strip()
        results = []

        # 1. Memory-based suggestions (highest priority)
        if self._memory:
            for entry in self._memory.suggest(p, context=cwd, limit=3):
                if entry.command not in results:
                    results.append(entry.command)

        # 2. Common command prefix match
        for cmd in self._common_commands:
            if cmd.lower().startswith(p) and cmd not in results:
                results.append(cmd)

        # 3. Palette search
        if self._palette and len(results) < limit:
            for entry in self._palette.search(p, limit=3):
                if entry.command not in results:
                    results.append(entry.command)

        # 4. File/directory completion for common commands
        if len(results) < limit and any(partial.startswith(c) for c in ["cd ", "cat ", "ls ", "vim ", "code "]):
            try:
                prefix = partial.split()[-1] if len(partial.split()) > 1 else ""
                base_dir = Path(cwd)
                for item in base_dir.iterdir():
                    name = item.name
                    if name.lower().startswith(prefix.lower()):
                        suffix = "/" if item.is_dir() else ""
                        full = f"{partial.rsplit(' ', 1)[0]} {name}{suffix}"
                        if full not in results:
                            results.append(full)
            except Exception:
                pass

        return results[:limit]
