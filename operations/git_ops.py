# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Git Operations  (Production Grade)
=============================================
Wraps the system `git` CLI with structured, safe output.
Used by the undo handler, branch switcher, and commit pipeline.

Requires: git must be on PATH (standard on all platforms).
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger("neuroshell.operations.git_ops")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CloneResult:
    """Result of a git clone operation."""
    url: str
    destination: str
    full_name: str = ""
    stars: int = 0
    description: str = ""

    def __str__(self) -> str:
        parts = [f"Cloned: {self.url} → {self.destination}"]
        if self.full_name:
            parts.append(f"  Repo: {self.full_name}")
        if self.stars:
            parts.append(f"  ★ {self.stars:,} stars")
        if self.description:
            parts.append(f"  {self.description[:100]}")
        return "\n".join(parts)


@dataclass
class CommitInfo:
    """Metadata for a single git commit."""
    sha: str
    short_sha: str
    author: str
    email: str
    date: str
    message: str
    files_changed: int = 0

    def __str__(self) -> str:
        return f"{self.short_sha} {self.date[:10]}  {self.author}  {self.message[:72]}"


@dataclass
class GitStatus:
    """Output of `git status`."""
    branch: str
    ahead: int
    behind: int
    staged: list[str] = field(default_factory=list)
    unstaged: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    is_clean: bool = True

    def summary(self) -> str:
        parts = [f"branch={self.branch}"]
        if self.ahead:
            parts.append(f"↑{self.ahead}")
        if self.behind:
            parts.append(f"↓{self.behind}")
        if self.staged:
            parts.append(f"{len(self.staged)} staged")
        if self.unstaged:
            parts.append(f"{len(self.unstaged)} modified")
        if self.untracked:
            parts.append(f"{len(self.untracked)} untracked")
        return "  ".join(parts) if parts else "clean"


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class GitOps:
    """
    Production-grade git operations manager.

    All methods raise ``RuntimeError`` on non-zero exit and return
    structured data rather than raw strings.
    """

    def __init__(self, cwd: str | Path | None = None):
        self.cwd = Path(cwd) if cwd else Path.cwd()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _git_path() -> str:
        git = shutil.which("git")
        if git is None:
            raise RuntimeError("git not found on PATH. Install git from https://git-scm.com/")
        return git

    def _run(self, args: list[str], timeout_s: int = 30) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self._git_path()] + args,
            cwd=str(self.cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )

    def _check(self, cp: subprocess.CompletedProcess, op: str) -> str:
        if cp.returncode != 0:
            err = (cp.stderr or cp.stdout or "No output").strip()
            raise RuntimeError(f"git {op} failed (exit {cp.returncode}): {err}")
        return (cp.stdout or "").strip()

    # ------------------------------------------------------------------
    # Repository state
    # ------------------------------------------------------------------

    def is_inside_repo(self) -> bool:
        """Return True if `cwd` is inside a git repository."""
        cp = self._run(["rev-parse", "--is-inside-work-tree"])
        return cp.returncode == 0 and cp.stdout.strip() == "true"

    def root(self) -> Path:
        """Return the root of the current git repository."""
        cp = self._run(["rev-parse", "--show-toplevel"])
        return Path(self._check(cp, "rev-parse --show-toplevel"))

    def current_branch(self) -> str:
        """Return the name of the current branch."""
        cp = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        return self._check(cp, "branch name")

    def status(self) -> GitStatus:
        """Return a structured ``GitStatus`` for the working tree."""
        # Porcelain v2 for machine-readable output
        cp = self._run(["status", "--porcelain=v1", "-b"])
        lines = (cp.stdout or "").splitlines()

        branch = "unknown"
        ahead = behind = 0
        staged: list[str] = []
        unstaged: list[str] = []
        untracked: list[str] = []

        for line in lines:
            if line.startswith("## "):
                header = line[3:]
                m = re.match(r"(.+?)(?:\.\.\.(.+?))?(?:\s+\[(.+)\])?$", header)
                if m:
                    branch = m.group(1).strip()
                    tracking = m.group(3) or ""
                    ahead_m = re.search(r"ahead (\d+)", tracking)
                    behind_m = re.search(r"behind (\d+)", tracking)
                    if ahead_m:
                        ahead = int(ahead_m.group(1))
                    if behind_m:
                        behind = int(behind_m.group(1))
                continue

            if len(line) < 3:
                continue
            xy = line[:2]
            fname = line[3:]
            if xy.startswith("?"):
                untracked.append(fname)
            elif xy[0] != " " and xy[0] != "?":
                staged.append(fname)
            if xy[1] != " " and xy[1] != "?":
                unstaged.append(fname)

        return GitStatus(
            branch=branch,
            ahead=ahead,
            behind=behind,
            staged=staged,
            unstaged=unstaged,
            untracked=untracked,
            is_clean=not staged and not unstaged and not untracked,
        )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def log(self, max_count: int = 20, branch: str = "") -> list[CommitInfo]:
        """Return recent commit history as structured ``CommitInfo`` objects."""
        fmt = "%H|%h|%an|%ae|%aI|%s"
        args = ["log", f"--format={fmt}", f"-n{max_count}"]
        if branch:
            args.append(branch)
        cp = self._run(args)
        commits: list[CommitInfo] = []
        for line in (cp.stdout or "").splitlines():
            parts = line.split("|", 5)
            if len(parts) < 6:
                continue
            sha, short, author, email, date, msg = parts
            commits.append(CommitInfo(
                sha=sha, short_sha=short,
                author=author, email=email,
                date=date, message=msg,
            ))
        return commits

    def last_commit(self) -> CommitInfo | None:
        """Return the most recent commit, or None in an empty repo."""
        commits = self.log(max_count=1)
        return commits[0] if commits else None

    # ------------------------------------------------------------------
    # Undo / rollback
    # ------------------------------------------------------------------

    def undo_last_commit(self, mode: str = "soft") -> str:
        """
        Un-commit the latest commit.

        Args:
            mode: ``"soft"``  — keep changes staged (default, safe)
                  ``"mixed"`` — keep changes unstaged
                  ``"hard"``  — discard all changes (destructive!)
        """
        if mode not in ("soft", "mixed", "hard"):
            raise ValueError(f"mode must be soft|mixed|hard, got {mode!r}")
        cp = self._run(["reset", f"--{mode}", "HEAD~1"])
        return self._check(cp, f"reset --{mode} HEAD~1")

    def restore_file(self, path: str) -> str:
        """Discard working-tree changes to `path` (like git checkout -- path)."""
        cp = self._run(["restore", "--", path])
        return self._check(cp, f"restore {path}")

    def stash(self, message: str = "neuroshell-autostash") -> str:
        """Stash all current changes."""
        cp = self._run(["stash", "push", "-m", message])
        return self._check(cp, "stash push")

    def stash_pop(self) -> str:
        """Pop the most recent stash."""
        cp = self._run(["stash", "pop"])
        return self._check(cp, "stash pop")

    # ------------------------------------------------------------------
    # Branches
    # ------------------------------------------------------------------

    def branches(self, include_remote: bool = False) -> list[str]:
        """Return list of branch names."""
        args = ["branch", "--format=%(refname:short)"]
        if include_remote:
            args.append("-a")
        cp = self._run(args)
        return [b.strip() for b in (cp.stdout or "").splitlines() if b.strip()]

    def switch_branch(self, branch: str, create: bool = False) -> str:
        """Switch to `branch`. Optionally create it if it doesn't exist."""
        args = ["switch", "--", branch]
        if create:
            args = ["switch", "-c", branch, "--"]
        cp = self._run(args)
        return self._check(cp, f"switch {branch}")

    def merge(self, branch: str, fast_forward_only: bool = True) -> str:
        """Merge `branch` into the current branch."""
        args = ["merge"]
        if fast_forward_only:
            args.append("--ff-only")
        args.extend(["--", branch])
        cp = self._run(args)
        return self._check(cp, f"merge {branch}")

    # ------------------------------------------------------------------
    # Staging & commits
    # ------------------------------------------------------------------

    def add(self, paths: str | list[str] = ".") -> str:
        """Stage files for commit."""
        if isinstance(paths, str):
            paths = [paths]
        cp = self._run(["add", "--"] + paths)
        return self._check(cp, "add")

    def commit(self, message: str, allow_empty: bool = False) -> str:
        """Create a commit. Returns the short SHA."""
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        cp = self._run(args, timeout_s=60)
        self._check(cp, "commit")
        # Extract short SHA from output
        m = re.search(r"\[.+?\s+([0-9a-f]{5,40})\]", cp.stdout or "")
        return m.group(1) if m else "?"

    def push(self, remote: str = "origin", branch: str = "", force: bool = False) -> str:
        """Push to remote."""
        if not branch:
            branch = self.current_branch()
        args = ["push", remote, branch]
        if force:
            args.append("--force-with-lease")
        cp = self._run(args, timeout_s=120)
        return self._check(cp, f"push {remote} {branch}")

    def pull(self, remote: str = "origin", branch: str = "") -> str:
        """Pull from remote."""
        if not branch:
            branch = self.current_branch()
        cp = self._run(["pull", remote, branch], timeout_s=120)
        return self._check(cp, f"pull {remote} {branch}")

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def tags(self) -> list[str]:
        """Return all tags sorted by version descending."""
        cp = self._run(["tag", "--sort=-version:refname"])
        return [t.strip() for t in (cp.stdout or "").splitlines() if t.strip()]

    def create_tag(self, name: str, message: str = "", commit: str = "HEAD") -> str:
        """Create an annotated tag."""
        args = ["tag", "-a", name, commit, "-m", message or name]
        cp = self._run(args)
        return self._check(cp, f"tag {name}")

    # ------------------------------------------------------------------
    # Diff helpers
    # ------------------------------------------------------------------

    def diff(self, ref_a: str = "HEAD~1", ref_b: str = "HEAD", stat_only: bool = False) -> str:
        """Return diff between two refs."""
        args = ["diff", ref_a, ref_b]
        if stat_only:
            args.append("--stat")
        cp = self._run(args, timeout_s=10)
        return (cp.stdout or "").strip()

    def show(self, ref: str = "HEAD") -> str:
        """Show a commit's patch."""
        cp = self._run(["show", ref, "--stat"], timeout_s=10)
        return (cp.stdout or "").strip()

    # ------------------------------------------------------------------
    # Clone
    # ------------------------------------------------------------------

    def clone(self, url: str, destination=None, timeout_s: int = 300) -> CloneResult:
        """
        Clone a remote repository.

        Args:
            url:          HTTPS or SSH URL, or owner/repo shorthand.
            destination:  Local directory to clone into (optional).
            timeout_s:    Max seconds to wait (default 5 min for large repos).

        Returns:
            CloneResult with clone metadata.
        """
        import re as _re
        # Expand owner/repo shorthand to full HTTPS URL
        if _re.match(r"^[\w.-]+/[\w.-]+$", url) and not url.startswith("http"):
            url = f"https://github.com/{url}.git"

        args = ["clone", url]
        if destination:
            args.append(str(destination))

        cp = self._run(args, timeout_s=timeout_s)
        self._check(cp, f"clone {url}")

        dest_name = (
            str(destination)
            if destination
            else url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        )
        return CloneResult(url=url, destination=dest_name)

    @staticmethod
    def search_github_repo(query: str, limit: int = 5) -> list:
        """
        Search GitHub's public API for repositories matching `query`.

        Returns a list of dicts with keys:
            full_name, clone_url, stars, description, html_url, language

        Network errors are silenced and an empty list is returned.
        """
        try:
            import json as _json
            import urllib.parse
            import urllib.request

            q = urllib.parse.quote(query)
            api_url = (
                "https://api.github.com/search/repositories"
                f"?q={q}&sort=stars&order=desc&per_page={min(limit, 10)}"
            )
            req = urllib.request.Request(
                api_url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "NeuroShell/4.2",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json.loads(resp.read().decode())

            results = []
            for item in data.get("items", [])[:limit]:
                results.append({
                    "full_name":   item.get("full_name", ""),
                    "clone_url":   item.get("clone_url", ""),
                    "html_url":    item.get("html_url", ""),
                    "stars":       item.get("stargazers_count", 0),
                    "description": item.get("description") or "",
                    "language":    item.get("language") or "",
                })
            return results

        except Exception as exc:
            _log.debug("GitHub search failed for %r: %s", query, exc)
            return []

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        try:
            branch = self.current_branch()
        except Exception:
            branch = "?"
        return f"GitOps(cwd={self.cwd}, branch={branch!r})"

import asyncio
import sys
from collections.abc import AsyncGenerator
from typing import Any, Dict

# Add NeuroShell root to path to resolve intelligence module if run independently
_root = str(Path(__file__).parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

try:
    from intelligence.tools.base_tool import BaseTool
except ImportError:
    class BaseTool: pass  # Graceful fallback if intelligence module is unresolvable

class GitTool(BaseTool):
    """
    Agentic interface for GitHub and Git operations.
    Conforms to the BaseTool streaming protocol.
    """
    def __init__(self, git_ops: GitOps | None = None):
        self.git_ops = git_ops or GitOps()

    @property
    def name(self) -> str:
        return "git_tool"

    @property
    def description(self) -> str:
        return "Execute Git operations like clone, status, log, commit, push, and pull. Supports GitHub searching."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "clone", "search", "log", "push", "pull", "commit"],
                    "description": "The git operation to perform."
                },
                "url": {"type": "string", "description": "Repository URL or name for clone/search."},
                "destination": {"type": "string", "description": "Local path for clone destination."},
                "message": {"type": "string", "description": "Commit message."},
            },
            "required": ["action"]
        }

    def can_use_tool(self, **kwargs) -> bool:
        # Clone, status, search, and log are safe.
        # Push, pull, and commit mutate state and might need permission.
        action = kwargs.get("action")
        if action in ["push", "commit"]:
            return False  # Requires explicit approval
        return True

    async def call(self, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        action = kwargs.get("action")
        url = kwargs.get("url")
        destination = kwargs.get("destination")
        message = kwargs.get("message")

        yield {"type": "progress", "message": f"Initializing Git {action}..."}

        git = GitOps()
        loop = asyncio.get_running_loop()

        def _run_action():
            if action == "status":
                return git.status().summary()
            elif action == "clone":
                if not url:
                    raise ValueError("URL is required for clone.")
                return str(git.clone(url, destination))
            elif action == "search":
                if not url:
                    raise ValueError("Query (url parameter) is required for search.")
                results = git.search_github_repo(url)
                if not results:
                    return f"No results found for '{url}'."
                best = results[0]
                return f"Found {best['full_name']} ({best['stars']} stars): {best['clone_url']}"
            elif action == "log":
                commits = git.log(max_count=5)
                return "\n".join(str(c) for c in commits)
            elif action == "commit":
                if not message:
                    raise ValueError("Message is required for commit.")
                git.add(".")
                sha = git.commit(message)
                return f"Committed: {sha}"
            elif action == "push":
                return git.push()
            elif action == "pull":
                return git.pull()
            else:
                raise ValueError(f"Unknown action: {action}")

        try:
            # Tell the UI we are actively waiting on the subprocess
            yield {"type": "progress", "message": f"Executing 'git {action}'..."}
            result_data = await loop.run_in_executor(None, _run_action)
            yield {"type": "result", "data": result_data}
        except Exception as e:
            yield {"type": "error", "message": str(e)}
