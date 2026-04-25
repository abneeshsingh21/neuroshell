# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Smart Suggestions — Context-Aware Command Recommender
Suggests commands based on project type, git status, history patterns,
and current working directory state.
"""

import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


# ═══════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════

@dataclass
class Suggestion:
    """A single command suggestion."""
    command: str
    reason: str
    category: str = ""       # git, project, workflow, system
    priority: float = 0.5    # 0.0–1.0: higher = more relevant
    is_destructive: bool = False

    def display(self) -> str:
        icon = {
            "git": "🔀", "project": "📦", "workflow": "🔁",
            "system": "🖥️", "file": "📄", "docker": "🐳",
        }.get(self.category, "💡")
        return f"{icon} {self.command}  — {self.reason}"


@dataclass
class SuggestionContext:
    """Captured context for generating suggestions."""
    cwd: str = ""
    project_type: str = ""       # python, node, rust, java, go, etc.
    git_dirty: bool = False
    git_branch: str = ""
    git_untracked: int = 0
    git_staged: int = 0
    git_conflicts: int = 0
    last_commands: list[str] = field(default_factory=list)
    last_exit_code: int = 0
    has_dockerfile: bool = False
    has_makefile: bool = False
    has_tests: bool = False


# ═══════════════════════════════════════════════════════════
# Project Detectors
# ═══════════════════════════════════════════════════════════

PROJECT_MARKERS = {
    "python":     ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"],
    "node":       ["package.json", "tsconfig.json", "yarn.lock", "pnpm-lock.yaml"],
    "rust":       ["Cargo.toml"],
    "go":         ["go.mod"],
    "java":       ["pom.xml", "build.gradle", "build.gradle.kts"],
    "dotnet":     ["*.csproj", "*.fsproj", "*.sln"],
    "ruby":       ["Gemfile", "Rakefile"],
    "php":        ["composer.json"],
    "c_cpp":      ["CMakeLists.txt", "Makefile", "meson.build"],
}


# ═══════════════════════════════════════════════════════════
# Per-Project Suggestions
# ═══════════════════════════════════════════════════════════

PROJECT_SUGGESTIONS: dict[str, list[dict]] = {
    "python": [
        {"cmd": "python -m pytest -v", "reason": "Run test suite", "cat": "project"},
        {"cmd": "pip install -e .", "reason": "Install package in dev mode", "cat": "project"},
        {"cmd": "python -m flake8 .", "reason": "Lint with flake8", "cat": "project"},
        {"cmd": "python -m mypy .", "reason": "Type-check with mypy", "cat": "project"},
        {"cmd": "pip freeze > requirements.txt", "reason": "Freeze dependencies", "cat": "project"},
        {"cmd": "python -m black .", "reason": "Auto-format code", "cat": "project"},
    ],
    "node": [
        {"cmd": "npm test", "reason": "Run test suite", "cat": "project"},
        {"cmd": "npm run build", "reason": "Build the project", "cat": "project"},
        {"cmd": "npm run dev", "reason": "Start dev server", "cat": "project"},
        {"cmd": "npm audit", "reason": "Check for vulnerabilities", "cat": "project"},
        {"cmd": "npx eslint .", "reason": "Lint JavaScript/TypeScript", "cat": "project"},
        {"cmd": "npm outdated", "reason": "Check for outdated packages", "cat": "project"},
    ],
    "rust": [
        {"cmd": "cargo build", "reason": "Build project", "cat": "project"},
        {"cmd": "cargo test", "reason": "Run tests", "cat": "project"},
        {"cmd": "cargo clippy", "reason": "Lint with Clippy", "cat": "project"},
        {"cmd": "cargo fmt", "reason": "Format code", "cat": "project"},
    ],
    "go": [
        {"cmd": "go build ./...", "reason": "Build project", "cat": "project"},
        {"cmd": "go test ./...", "reason": "Run tests", "cat": "project"},
        {"cmd": "go vet ./...", "reason": "Vet code for issues", "cat": "project"},
        {"cmd": "go mod tidy", "reason": "Clean up dependencies", "cat": "project"},
    ],
    "java": [
        {"cmd": "mvn clean install", "reason": "Build with Maven", "cat": "project"},
        {"cmd": "mvn test", "reason": "Run tests", "cat": "project"},
        {"cmd": "gradle build", "reason": "Build with Gradle", "cat": "project"},
    ],
    "c_cpp": [
        {"cmd": "cmake --build build", "reason": "Build project", "cat": "project"},
        {"cmd": "make -j$(nproc)", "reason": "Build with Make", "cat": "project"},
        {"cmd": "ctest --test-dir build", "reason": "Run tests", "cat": "project"},
    ],
}


# ═══════════════════════════════════════════════════════════
# Smart Suggestions Engine
# ═══════════════════════════════════════════════════════════

class SmartSuggester:
    """
    Context-aware command suggestion engine.

    Analyzes project type, git state, command history, and file system
    to proactively suggest the most relevant next commands.
    """

    def __init__(self, history_store=None, context_manager=None):
        self.history = history_store
        self.context = context_manager
        self._last_suggestions: list[Suggestion] = []

    # ── Public API ───────────────────────────────────────

    def suggest(self, limit: int = 6) -> list[Suggestion]:
        """Generate context-aware suggestions."""
        ctx = self._capture_context()
        suggestions: list[Suggestion] = []

        # 1. Git-aware suggestions (highest priority)
        suggestions.extend(self._git_suggestions(ctx))

        # 2. Project-type suggestions
        suggestions.extend(self._project_suggestions(ctx))

        # 3. Workflow pattern suggestions
        suggestions.extend(self._workflow_suggestions(ctx))

        # 4. System/environment suggestions
        suggestions.extend(self._system_suggestions(ctx))

        # 5. Docker suggestions
        if ctx.has_dockerfile:
            suggestions.extend(self._docker_suggestions(ctx))

        # Deduplicate by command
        seen = set()
        unique = []
        for s in suggestions:
            if s.command not in seen:
                seen.add(s.command)
                unique.append(s)

        # Sort by priority (highest first)
        unique.sort(key=lambda s: s.priority, reverse=True)

        self._last_suggestions = unique[:limit]
        return self._last_suggestions

    def get_formatted(self, limit: int = 6) -> str:
        """Get formatted suggestion list."""
        suggestions = self.suggest(limit)
        if not suggestions:
            return "  💡 No context-specific suggestions right now.\n  Try running some commands first!"

        lines = ["  ╔══════════════════════════════════════════════╗",
                 "  ║       💡 Smart Suggestions                   ║",
                 "  ╚══════════════════════════════════════════════╝", ""]

        for i, s in enumerate(suggestions, 1):
            lines.append(f"  {i}. {s.display()}")

        lines.append("")
        lines.append("  Type a suggestion number or any command.")
        return "\n".join(lines)

    def get_suggestion_by_index(self, index: int) -> Optional[str]:
        """Get a suggestion command by its display index (1-based)."""
        if 1 <= index <= len(self._last_suggestions):
            return self._last_suggestions[index - 1].command
        return None

    # ── Context Capture ──────────────────────────────────

    def _capture_context(self) -> SuggestionContext:
        """Capture current project and environment context."""
        ctx = SuggestionContext()
        ctx.cwd = os.getcwd()

        # Detect project type
        ctx.project_type = self._detect_project_type(ctx.cwd)

        # Check for special files
        cwd_path = Path(ctx.cwd)
        ctx.has_dockerfile = (cwd_path / "Dockerfile").exists() or (cwd_path / "docker-compose.yml").exists()
        ctx.has_makefile = (cwd_path / "Makefile").exists()
        ctx.has_tests = any(
            (cwd_path / d).exists() for d in ["tests", "test", "spec", "__tests__"]
        )

        # Git state
        self._capture_git_state(ctx)

        # Recent commands from history
        if self.history:
            try:
                recent = self.history.get_recent(10)
                ctx.last_commands = [r.command for r in recent]
                if recent:
                    ctx.last_exit_code = recent[0].exit_code
            except Exception:
                pass

        return ctx

    def _detect_project_type(self, cwd: str) -> str:
        """Detect project type from file markers."""
        cwd_path = Path(cwd)
        for project_type, markers in PROJECT_MARKERS.items():
            for marker in markers:
                if "*" in marker:
                    if list(cwd_path.glob(marker)):
                        return project_type
                elif (cwd_path / marker).exists():
                    return project_type
        return ""

    def _capture_git_state(self, ctx: SuggestionContext):
        """Capture git repository state."""
        try:
            # Check if in a git repo
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True, timeout=3,
                cwd=ctx.cwd,
            )
            if result.returncode != 0:
                return

            # Get branch
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, timeout=3,
                cwd=ctx.cwd,
            )
            ctx.git_branch = branch.stdout.strip()

            # Get status
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, timeout=3,
                cwd=ctx.cwd,
            )
            lines = [l for l in status.stdout.strip().splitlines() if l.strip()]
            ctx.git_dirty = len(lines) > 0
            ctx.git_untracked = sum(1 for l in lines if l.startswith("??"))
            ctx.git_staged = sum(1 for l in lines if l[0] in "MADR")
            ctx.git_conflicts = sum(1 for l in lines if l.startswith("UU"))

        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass

    # ── Suggestion Generators ────────────────────────────

    def _git_suggestions(self, ctx: SuggestionContext) -> list[Suggestion]:
        """Generate git-aware suggestions."""
        suggestions = []

        if not ctx.git_branch:
            return suggestions

        if ctx.git_conflicts > 0:
            suggestions.append(Suggestion(
                command="git diff --name-only --diff-filter=U",
                reason=f"{ctx.git_conflicts} merge conflict(s) — list conflicted files",
                category="git", priority=1.0,
            ))
            suggestions.append(Suggestion(
                command="git mergetool",
                reason="Open merge tool to resolve conflicts",
                category="git", priority=0.95,
            ))

        if ctx.git_dirty and ctx.git_staged == 0:
            suggestions.append(Suggestion(
                command="git add -A",
                reason="Stage all changes for commit",
                category="git", priority=0.85,
            ))
            suggestions.append(Suggestion(
                command="git diff",
                reason="Review uncommitted changes",
                category="git", priority=0.8,
            ))

        if ctx.git_staged > 0:
            suggestions.append(Suggestion(
                command='git commit -m ""',
                reason=f"{ctx.git_staged} file(s) staged — ready to commit",
                category="git", priority=0.9,
            ))

        if ctx.git_untracked > 0:
            suggestions.append(Suggestion(
                command="git status",
                reason=f"{ctx.git_untracked} untracked file(s)",
                category="git", priority=0.65,
            ))

        # Suggest push if on a feature branch
        if ctx.git_branch and ctx.git_branch != "main" and ctx.git_branch != "master":
            if not ctx.git_dirty:
                suggestions.append(Suggestion(
                    command=f"git push origin {ctx.git_branch}",
                    reason=f"Push '{ctx.git_branch}' to remote",
                    category="git", priority=0.6,
                ))

        return suggestions

    def _project_suggestions(self, ctx: SuggestionContext) -> list[Suggestion]:
        """Generate project-type-specific suggestions."""
        suggestions = []
        templates = PROJECT_SUGGESTIONS.get(ctx.project_type, [])

        for tmpl in templates:
            suggestions.append(Suggestion(
                command=tmpl["cmd"],
                reason=tmpl["reason"],
                category=tmpl.get("cat", "project"),
                priority=0.5,
            ))

        return suggestions

    def _workflow_suggestions(self, ctx: SuggestionContext) -> list[Suggestion]:
        """Suggest next command based on recent command patterns."""
        suggestions = []
        if not ctx.last_commands:
            return suggestions

        last = ctx.last_commands[0] if ctx.last_commands else ""
        last_lower = last.lower()

        # Common workflow continuations
        PATTERNS = {
            "git add":     [("git commit -m ''", "Commit staged changes", 0.9)],
            "git commit":  [("git push", "Push committed changes", 0.85)],
            "git pull":    [("git log --oneline -5", "Review pulled commits", 0.6)],
            "git merge":   [("git push", "Push merge result", 0.7)],
            "npm install": [("npm run dev", "Start dev server", 0.7)],
            "npm test":    [("npm run build", "Build for production", 0.6)],
            "pip install": [("python -m pytest", "Run tests after install", 0.6)],
            "docker build":[("docker run", "Run the built image", 0.8)],
            "make":        [("make test", "Run tests", 0.7)],
            "mkdir":       [("cd", "Enter the new directory", 0.7)],
        }

        for prefix, continuations in PATTERNS.items():
            if last_lower.startswith(prefix):
                for cmd, reason, prio in continuations:
                    suggestions.append(Suggestion(
                        command=cmd, reason=reason,
                        category="workflow", priority=prio,
                    ))
                break

        # If last command failed, suggest fix
        if ctx.last_exit_code != 0:
            suggestions.append(Suggestion(
                command="fix",
                reason="Auto-fix the last error",
                category="workflow", priority=0.95,
            ))

        return suggestions

    def _system_suggestions(self, ctx: SuggestionContext) -> list[Suggestion]:
        """General system suggestions."""
        suggestions = []

        if ctx.has_makefile:
            suggestions.append(Suggestion(
                command="make",
                reason="Makefile detected — run default target",
                category="system", priority=0.55,
            ))

        return suggestions

    def _docker_suggestions(self, ctx: SuggestionContext) -> list[Suggestion]:
        """Docker-specific suggestions."""
        return [
            Suggestion(
                command="docker compose up -d",
                reason="Start containers (docker-compose.yml found)",
                category="docker", priority=0.7,
            ),
            Suggestion(
                command="docker compose logs -f",
                reason="Follow container logs",
                category="docker", priority=0.5,
            ),
            Suggestion(
                command="docker ps",
                reason="List running containers",
                category="docker", priority=0.45,
            ),
        ]
