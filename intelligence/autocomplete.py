# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Autocomplete — Production Grade
Context-aware command completion with fuzzy matching, weighted scoring,
git-aware suggestions, argument completion, and real-time ranking.
"""

import os
import subprocess
import time
from dataclasses import dataclass, field

# ═══════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════

@dataclass
class Completion:
    """A single autocomplete suggestion."""
    text: str
    display: str = ""
    description: str = ""
    score: float = 0.0
    source: str = ""      # history, file, git, arg, command, alias
    category: str = ""    # command, path, branch, flag, env

    def __post_init__(self):
        if not self.display:
            self.display = self.text


@dataclass
class CompletionContext:
    """Context for generating completions."""
    line: str              # full input line
    prefix: str            # word being completed
    cursor_pos: int = 0
    preceding_words: list = field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# Command Knowledge Base
# ═══════════════════════════════════════════════════════════

# Common command flags for argument completion
COMMAND_FLAGS = {
    "git": {
        "commit": ["-m", "--message", "-a", "--all", "--amend", "--no-edit", "-s", "--signoff"],
        "push": ["--force", "-f", "--set-upstream", "-u", "--tags", "--dry-run", "--no-verify"],
        "pull": ["--rebase", "--no-rebase", "--ff-only", "--no-ff"],
        "checkout": ["-b", "--branch", "--orphan", "-t", "--track"],
        "log": ["--oneline", "--graph", "--stat", "-n", "--author", "--since", "--until"],
        "diff": ["--staged", "--cached", "--stat", "--name-only", "--word-diff"],
        "stash": ["push", "pop", "list", "apply", "drop", "show"],
        "branch": ["-d", "-D", "-m", "-a", "--list", "--all", "-r", "--remote"],
        "remote": ["add", "remove", "rename", "-v", "--verbose"],
        "rebase": ["-i", "--interactive", "--continue", "--abort", "--skip"],
        "merge": ["--no-ff", "--squash", "--abort", "--continue"],
        "reset": ["--soft", "--mixed", "--hard", "HEAD~1"],
        "clone": ["--depth", "--branch", "--single-branch", "--recursive"],
        "tag": ["-a", "-m", "-d", "-l", "--list"],
    },
    "docker": {
        "run": ["-d", "--detach", "-p", "--publish", "-v", "--volume", "--name", "--rm", "-e", "--env", "-it", "--network"],
        "build": ["-t", "--tag", "-f", "--file", "--no-cache", "--pull"],
        "exec": ["-it", "-d", "--detach"],
        "ps": ["-a", "--all", "-q", "--quiet", "--format"],
        "compose": ["up", "down", "build", "ps", "logs", "restart", "exec"],
        "images": ["-a", "--all", "-q", "--quiet", "--format"],
        "logs": ["-f", "--follow", "--tail", "--since"],
    },
    "kubectl": {
        "get": ["pods", "services", "deployments", "nodes", "namespaces", "-o", "yaml", "json", "wide", "-n", "--all-namespaces", "-A"],
        "apply": ["-f", "--filename", "-k", "--kustomize"],
        "delete": ["-f", "--filename", "--all", "--force"],
        "describe": ["pod", "service", "deployment", "node"],
        "logs": ["-f", "--follow", "-c", "--container", "--tail", "--previous"],
        "exec": ["-it", "-c", "--container"],
    },
    "pip": {
        "install": ["-r", "--requirement", "-U", "--upgrade", "-e", "--editable", "--user", "--no-cache-dir"],
        "uninstall": ["-y", "--yes"],
        "freeze": [">", "--all"],
        "list": ["--outdated", "--uptodate", "--format"],
    },
    "npm": {
        "install": ["--save", "--save-dev", "-D", "-g", "--global", "--legacy-peer-deps"],
        "run": [],  # populated dynamically
        "start": [],
        "test": ["--coverage", "--watch"],
        "build": [],
        "init": ["-y", "--yes"],
    },
    "python": {
        "": ["-m", "-c", "-u", "-i", "-V", "--version", "-O"],
        "-m": ["pytest", "pip", "venv", "http.server", "json.tool", "unittest", "mypy", "black", "flake8"],
    },
    "cargo": {
        "": ["build", "run", "test", "check", "clippy", "fmt", "doc", "publish", "new"],
        "build": ["--release", "--target", "--features"],
        "test": ["--release", "--lib", "--doc"],
    },
    "make": {
        "": ["clean", "build", "test", "install", "all", "help"],
    },
}

# Common environment variable names
COMMON_ENV_VARS = [
    "PATH", "HOME", "USER", "SHELL", "TERM", "EDITOR",
    "VIRTUAL_ENV", "CONDA_DEFAULT_ENV", "NODE_ENV",
    "DOCKER_HOST", "KUBECONFIG", "AWS_PROFILE",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "JAVA_HOME", "GOPATH", "GOROOT", "CARGO_HOME",
    "DATABASE_URL", "REDIS_URL", "PORT", "HOST",
    "API_KEY", "SECRET_KEY", "DEBUG",
]

# NeuroShell internal commands for completion
NEUROSHELL_COMMANDS = {
    # Slash Commands (Primary TUI)
    "/api-key":     "Configure and encrypt LLM API keys interactively",
    "/apikey":      "Configure and encrypt LLM API keys interactively",
    "/model":       "List and switch active LLM models",
    "/swarm":       "Multi-agent parallel task orchestrator with sandbox",
    "/agent":       "Autonomous multi-step agent planner with recovery",
    "/plan":        "Enter or manage safe architecture plan mode",
    "/backup":      "Create, restore, or validate ops backups and retention",
    "/record":      "Record, list, or replay terminal sessions",
    "/clip":        "Copy, paste, or inspect cross-platform clipboard",
    "/profile":     "Manage per-directory workspace configuration profiles",
    "/jobs":        "List, monitor, or terminate background processes",
    "/snapshots":   "View file snapshots and perform instant undo",
    "/search":      "Deep recursive file and repository search",
    "/find":        "Deep recursive file and repository search",
    "/voice":       "Voice-to-command transcription engine",
    "/git":         "Structured Git operations and GitHub search",
    "/plugins":     "Discover, load, reload, and trust extension plugins",
    "/dream":       "AutoDream memory consolidation and status",
    "/update":      "Cryptographic update channel and binary manager",
    "/notebook":    "Interactive session notebook and markdown export",
    "/scan":        "Run project vulnerability and security scans",
    "/security":    "Safety policy, RBAC profiles, and audit verification",
    "/theme":       "List and switch terminal cyberpunk themes",
    "/config":      "Interactive TOML config editor and key viewer",
    "/stats":       "Session runtime metrics, latencies, and timers",
    "/help":        "Show comprehensive NeuroShell command directory",

    # Standard Commands
    "help":         "Show help for a topic",
    "fix":          "Auto-fix the last error",
    "explain:":     "Explain a command",
    "suggest":      "Smart context-aware suggestions",
    "aliases":      "List all aliases",
    "alias":        "Create a command alias",
    "unalias":      "Remove an alias",
    "env":          "Show environment variables",
    "setenv":       "Set an environment variable",
    "unsetenv":     "Unset an environment variable",
    "models":       "List available LLM models",
    "model":        "Switch LLM model",
    "config":       "View/edit configuration",
    "policy":       "View/set safety policy profile and role",
    "policy audit": "Show recent safety audit entries",
    "policy audit export": "Export safety audit entries to JSON/CSV",
    "policy audit verify": "Verify exported audit integrity and hash chain",
    "deploy status": "Show active deployment stage/version",
    "deploy promote": "Promote verified release using manifest/checksums/signature",
    "deploy rollback": "Rollback to previous deployment",
    "deploy drift": "Check config drift against active deployment",
    "deploy canary": "Canary promote with SLO-based auto rollback",
    "deploy key add": "Add trusted public key fingerprint for deployments",
    "deploy key list": "List trusted deployment key fingerprints",
    "deploy audit": "Show deployment audit events",
    "deploy audit export": "Export deployment audit chain to JSON",
    "deploy audit verify": "Verify exported deployment audit integrity",
    "browser status": "Show browser automation capability status",
    "browser open": "Open URL in default browser",
    "browser fetch": "Fetch raw HTML from URL",
    "browser extract": "Extract readable text from URL",
    "browser screenshot": "Capture page screenshot via Playwright",
    "github status": "Show GitHub CLI install/auth status",
    "github repo set": "Set default repository (owner/name) for GitHub commands",
    "github repo current": "Show default repository used by GitHub commands",
    "github repo": "Show active GitHub repository metadata",
    "github pr list": "List pull requests",
    "github pr view": "View pull request details",
    "github pr create": "Create pull request",
    "github issue list": "List issues",
    "github issue create": "Create issue",
    "stats":        "Show session statistics",
    "time":         "Time a command execution",
    "history":      "View/export command history",
    "dashboard":    "Open the dashboard",
    "docs":         "Generate documentation",
    "cheatsheet":   "Generate command cheatsheet",
    "playbook":     "Generate error fix playbook",
    "pipelines":    "List pipeline templates",
    "pipe:":        "Build a pipeline from description",
    "chain:":       "Build a command chain",
    "agent:":       "Run agent for a task",
    "script:":      "Generate a shell script",
    "bookmark":     "Save/list bookmarks",
    "project":      "Detect project type",
    "clear":        "Clear the terminal",
    "exit":         "Exit NeuroShell",
    "quit":         "Exit NeuroShell",
}


# ═══════════════════════════════════════════════════════════
# Autocomplete Engine — Production Grade
# ═══════════════════════════════════════════════════════════

class Autocomplete:
    """
    Production-grade autocomplete engine.

    Features:
    - Fuzzy matching with Levenshtein distance scoring
    - Weighted multi-source ranking (history, files, git, commands)
    - Git-aware completions (branches, remotes, stash)
    - Command argument/flag completion for 9+ tools
    - Environment variable completion
    - Path completion with type indicators
    - Alias expansion
    - Real-time re-ranking as user types
    """

    # Scoring weights
    WEIGHT_EXACT = 100
    WEIGHT_PREFIX = 80
    WEIGHT_FUZZY = 50
    WEIGHT_HISTORY_RECENCY = 30
    WEIGHT_HISTORY_FREQUENCY = 20
    WEIGHT_CONTEXT = 15

    MAX_SUGGESTIONS = 15
    PERSONALIZATION_TTL_S = 20

    def __init__(self, history_store=None, context_manager=None):
        self.history = history_store
        self.context = context_manager
        self._alias_cache: dict[str, str] = {}
        self._command_boosts: dict[str, float] = {}
        self._boosts_updated_at = 0.0

    def complete(self, line: str, cursor_pos: int = None) -> list[Completion]:
        """
        Generate completions for the current input line.

        Args:
            line: Full input line
            cursor_pos: Cursor position (defaults to end)

        Returns:
            Sorted list of Completion objects
        """
        if cursor_pos is None:
            cursor_pos = len(line)
        ctx = self._parse_context(line, cursor_pos)

        completions: list[Completion] = []

        if not ctx.prefix and not ctx.preceding_words:
            # Empty line — show recent commands and common ones
            completions.extend(self._history_completions("", limit=10))
            return self._dedupe_and_sort(completions)

        # First word → complete command names + NeuroShell internals
        if not ctx.preceding_words:
            completions.extend(self._command_completions(ctx.prefix))
            completions.extend(self._neuroshell_completions(ctx.prefix))
            completions.extend(self._alias_completions(ctx.prefix))
            completions.extend(self._history_completions(ctx.prefix))
        else:
            base_cmd = ctx.preceding_words[0].lower()
            sub_cmd = ctx.preceding_words[1] if len(ctx.preceding_words) > 1 else ""

            # Path completion for any position
            completions.extend(self._path_completions(ctx.prefix))

            # Command-specific argument completion
            completions.extend(self._argument_completions(base_cmd, sub_cmd, ctx.prefix))

            # Git-specific completions
            if base_cmd == "git":
                completions.extend(self._git_completions(sub_cmd, ctx.prefix))

            # Environment variable completion
            if ctx.prefix.startswith("$"):
                completions.extend(self._env_completions(ctx.prefix[1:]))

            # History-based completions
            completions.extend(self._history_completions(ctx.prefix, context_cmd=base_cmd))

        return self._dedupe_and_sort(completions)[:self.MAX_SUGGESTIONS]

    # ═══════════════════════════════════════════════════════
    # Completion Sources
    # ═══════════════════════════════════════════════════════

    def _command_completions(self, prefix: str) -> list[Completion]:
        """Complete command names from PATH."""
        completions = []
        seen = set()
        self._refresh_personalization_boosts()

        # Common commands first
        common = [
            "git", "docker", "python", "pip", "npm", "node",
            "cd", "ls", "cat", "grep", "find", "mkdir", "rm", "cp", "mv",
            "echo", "curl", "wget", "ssh", "tar", "zip", "unzip",
            "make", "cargo", "go", "code", "vim",
        ]

        for cmd in common:
            if self._fuzzy_match(cmd, prefix):
                score = self.WEIGHT_EXACT if cmd.startswith(prefix) else self.WEIGHT_FUZZY
                score += self._command_boosts.get(cmd, 0.0)
                completions.append(Completion(
                    text=cmd, description="command", score=score,
                    source="command", category="command",
                ))
                seen.add(cmd)

        # PATH commands
        if prefix and len(prefix) >= 2:
            for cmd in self._get_path_commands(prefix):
                if cmd not in seen:
                    score = self.WEIGHT_PREFIX + self._command_boosts.get(cmd, 0.0)
                    completions.append(Completion(
                        text=cmd, description="command", score=score,
                        source="command", category="command",
                    ))
                    seen.add(cmd)

        return completions

    def _neuroshell_completions(self, prefix: str) -> list[Completion]:
        """Complete NeuroShell internal commands."""
        completions = []
        for cmd, desc in NEUROSHELL_COMMANDS.items():
            if self._fuzzy_match(cmd, prefix):
                score = self.WEIGHT_EXACT + 10 if cmd.startswith(prefix) else self.WEIGHT_FUZZY + 10
                completions.append(Completion(
                    text=cmd, description=f"🧠 {desc}",
                    score=score,
                    source="neuroshell", category="command",
                ))
        return completions

    def _alias_completions(self, prefix: str) -> list[Completion]:
        """Complete from aliases."""
        completions = []
        if self.history:
            try:
                for alias in self.history.list_aliases():
                    name = alias["name"]
                    if self._fuzzy_match(name, prefix):
                        completions.append(Completion(
                            text=name,
                            display=f"{name} → {alias['expansion'][:30]}",
                            description="alias",
                            score=self.WEIGHT_EXACT + 5,
                            source="alias", category="command",
                        ))
            except Exception:
                pass
        return completions

    def _path_completions(self, prefix: str) -> list[Completion]:
        """Complete file/directory paths."""
        completions = []

        # Expand ~ and resolve base
        expanded = os.path.expanduser(prefix)
        if os.path.isabs(expanded):
            base_dir = os.path.dirname(expanded)
            partial = os.path.basename(expanded)
        else:
            base_dir = os.path.dirname(expanded) if os.path.dirname(expanded) else "."
            partial = os.path.basename(expanded)

        try:
            if os.path.isdir(base_dir):
                entries = os.listdir(base_dir)
                for entry in sorted(entries)[:50]:
                    if not partial or entry.lower().startswith(partial.lower()):
                        full_path = os.path.join(base_dir, entry)
                        is_dir = os.path.isdir(full_path)
                        display_entry = entry + ("/" if is_dir else "")

                        # Build completion path
                        if prefix.startswith("~") or os.path.dirname(prefix):
                            text = os.path.join(os.path.dirname(prefix), display_entry)
                        else:
                            text = display_entry

                        completions.append(Completion(
                            text=text,
                            display=display_entry,
                            description="dir" if is_dir else "file",
                            score=self.WEIGHT_PREFIX + (5 if is_dir else 0),
                            source="file", category="path",
                        ))
        except (PermissionError, FileNotFoundError):
            pass

        return completions

    def _argument_completions(self, base_cmd: str, sub_cmd: str, prefix: str) -> list[Completion]:
        """Complete command arguments/flags."""
        completions = []

        cmd_flags = COMMAND_FLAGS.get(base_cmd, {})
        if not cmd_flags:
            return completions

        # Get flags for subcommand, else for base command
        flags = cmd_flags.get(sub_cmd, cmd_flags.get("", []))

        # If no subcommand and prefix is not a flag, suggest subcommands
        if not prefix.startswith("-") and not sub_cmd:
            for subcmd in cmd_flags.keys():
                if subcmd and self._fuzzy_match(subcmd, prefix):
                    completions.append(Completion(
                        text=subcmd, description=f"{base_cmd} subcommand",
                        score=self.WEIGHT_PREFIX + 10,
                        source="arg", category="flag",
                    ))

        for flag in flags:
            if self._fuzzy_match(flag, prefix):
                score = self.WEIGHT_EXACT if flag.startswith(prefix) else self.WEIGHT_FUZZY
                completions.append(Completion(
                    text=flag, description=f"{base_cmd} flag",
                    score=score,
                    source="arg", category="flag",
                ))

        return completions

    def _git_completions(self, sub_cmd: str, prefix: str) -> list[Completion]:
        """Git-specific completions: branches, remotes, stash."""
        completions = []

        if sub_cmd in ("checkout", "switch", "merge", "rebase", "branch", "diff", "log"):
            # Branch names
            for branch in self._get_git_branches():
                if self._fuzzy_match(branch, prefix):
                    completions.append(Completion(
                        text=branch, description="branch",
                        score=self.WEIGHT_PREFIX + 15,
                        source="git", category="branch",
                    ))

        if sub_cmd in ("push", "pull", "fetch"):
            # Remote names
            for remote in self._get_git_remotes():
                if self._fuzzy_match(remote, prefix):
                    completions.append(Completion(
                        text=remote, description="remote",
                        score=self.WEIGHT_PREFIX + 10,
                        source="git", category="branch",
                    ))

        if sub_cmd == "stash" and prefix:
            for i in range(5):
                ref = f"stash@{{{i}}}"
                if self._fuzzy_match(ref, prefix):
                    completions.append(Completion(
                        text=ref, description=f"stash #{i}",
                        score=self.WEIGHT_PREFIX,
                        source="git", category="branch",
                    ))

        return completions

    def _env_completions(self, prefix: str) -> list[Completion]:
        """Complete environment variable names."""
        completions = []
        all_vars = set(COMMON_ENV_VARS) | set(os.environ.keys())

        for var in sorted(all_vars):
            if self._fuzzy_match(var, prefix):
                value = os.environ.get(var, "")
                preview = value[:30] + "..." if len(value) > 30 else value
                completions.append(Completion(
                    text=f"${var}", display=f"${var}",
                    description=preview or "env",
                    score=self.WEIGHT_PREFIX,
                    source="env", category="env",
                ))

        return completions

    def _history_completions(self, prefix: str, context_cmd: str = "", limit: int = 8) -> list[Completion]:
        """Complete from command history with recency/frequency scoring."""
        completions = []
        if not self.history:
            return completions

        try:
            recent = self.history.get_recent(50)
            seen_cmds = set()

            for i, record in enumerate(recent):
                cmd = record.command
                if cmd in seen_cmds:
                    continue
                seen_cmds.add(cmd)

                # Match against prefix
                if prefix and not self._fuzzy_match(cmd, prefix) and prefix.lower() not in cmd.lower():
                    continue

                # Context match bonus
                context_bonus = self.WEIGHT_CONTEXT if (context_cmd and cmd.startswith(context_cmd)) else 0

                # Recency scoring (newer = higher)
                recency_score = max(0, self.WEIGHT_HISTORY_RECENCY - i)

                # Success bonus
                success_bonus = 5 if record.exit_code == 0 else -5

                # Prefer context token continuity when typing later arguments.
                continuity_bonus = 0
                if context_cmd:
                    first_token = cmd.split()[0].lower() if cmd.split() else ""
                    continuity_bonus = 12 if first_token == context_cmd.lower() else 0

                score = recency_score + context_bonus + success_bonus + continuity_bonus

                completions.append(Completion(
                    text=cmd,
                    description="history" + (" ✓" if record.exit_code == 0 else " ✗"),
                    score=score,
                    source="history", category="command",
                ))

                if len(completions) >= limit:
                    break

        except Exception:
            pass

        return completions

    # ═══════════════════════════════════════════════════════
    # Matching & Scoring
    # ═══════════════════════════════════════════════════════

    def _fuzzy_match(self, candidate: str, prefix: str) -> bool:
        """Check if candidate matches prefix (fuzzy)."""
        if not prefix:
            return True
        if candidate.lower().startswith(prefix.lower()):
            return True

        # Subsequence match
        p_lower = prefix.lower()
        c_lower = candidate.lower()
        p_idx = 0
        for char in c_lower:
            if p_idx < len(p_lower) and char == p_lower[p_idx]:
                p_idx += 1
        if p_idx == len(p_lower):
            return True

        # Levenshtein distance for short strings
        if len(prefix) >= 3 and len(candidate) >= 3:
            dist = self._levenshtein(prefix.lower()[:6], candidate.lower()[:6])
            return dist <= 2

        return False

    @staticmethod
    def _levenshtein(s1: str, s2: str) -> int:
        """Compute Levenshtein distance."""
        if len(s1) < len(s2):
            return Autocomplete._levenshtein(s2, s1)
        if len(s2) == 0:
            return len(s1)

        prev_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            curr_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = prev_row[j + 1] + 1
                deletions = curr_row[j] + 1
                substitutions = prev_row[j] + (c1 != c2)
                curr_row.append(min(insertions, deletions, substitutions))
            prev_row = curr_row

        return prev_row[-1]

    def _dedupe_and_sort(self, completions: list[Completion]) -> list[Completion]:
        """Deduplicate and sort completions by score."""
        seen = {}
        for c in completions:
            key = c.text.lower()
            if key not in seen or c.score > seen[key].score:
                seen[key] = c
        return sorted(seen.values(), key=lambda c: c.score, reverse=True)

    def _refresh_personalization_boosts(self):
        """Refresh command frequency boosts from recent successful history."""
        if not self.history:
            return

        now = time.time()
        if now - self._boosts_updated_at < self.PERSONALIZATION_TTL_S:
            return

        try:
            recent = self.history.get_recent(200)
        except Exception:
            return

        counts: dict[str, int] = {}
        for record in recent:
            cmd = (getattr(record, "command", "") or "").strip()
            if not cmd:
                continue
            if getattr(record, "exit_code", 1) != 0:
                continue
            token = cmd.split()[0].lower()
            if token:
                counts[token] = counts.get(token, 0) + 1

        max_count = max(counts.values()) if counts else 0
        boosts = {}
        if max_count > 0:
            for cmd, cnt in counts.items():
                boosts[cmd] = round((cnt / max_count) * 15.0, 2)

        self._command_boosts = boosts
        self._boosts_updated_at = now

    # ═══════════════════════════════════════════════════════
    # Context Parsing
    # ═══════════════════════════════════════════════════════

    def _parse_context(self, line: str, cursor_pos: int) -> CompletionContext:
        """Parse the input line into completion context."""
        text = line[:cursor_pos]
        words = text.split()
        prefix = words[-1] if words and not text.endswith(" ") else ""
        preceding = words[:-1] if prefix else words

        return CompletionContext(
            line=line,
            prefix=prefix,
            cursor_pos=cursor_pos,
            preceding_words=preceding,
        )

    # ═══════════════════════════════════════════════════════
    # System Queries
    # ═══════════════════════════════════════════════════════

    def _get_path_commands(self, prefix: str, limit: int = 20) -> list[str]:
        """Get matching commands from PATH."""
        commands = set()
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)

        for path_dir in path_dirs:
            try:
                if os.path.isdir(path_dir):
                    for entry in os.listdir(path_dir):
                        if entry.lower().startswith(prefix.lower()):
                            commands.add(entry.split(".")[0] if os.name == "nt" else entry)
                            if len(commands) >= limit:
                                return sorted(commands)
            except (PermissionError, OSError):
                continue

        return sorted(commands)

    def _get_git_branches(self) -> list[str]:
        """Get git branch names."""
        try:
            result = subprocess.run(
                ["git", "branch", "-a", "--format=%(refname:short)"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                return [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]
        except Exception:
            pass
        return []

    def _get_git_remotes(self) -> list[str]:
        """Get git remote names."""
        try:
            result = subprocess.run(
                ["git", "remote"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                return [r.strip() for r in result.stdout.strip().split("\n") if r.strip()]
        except Exception:
            pass
        return ["origin"]

    def register_alias(self, name: str, expansion: str):
        """Register an alias for completion."""
        self._alias_cache[name] = expansion
