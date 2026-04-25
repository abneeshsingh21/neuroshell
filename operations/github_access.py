# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Production GitHub access helpers powered by GitHub CLI (gh)."""

from __future__ import annotations

import json
import shutil
import subprocess
import re
from pathlib import Path


class GitHubAccessManager:
    """Wrap gh commands with structured output and safe error messages."""

    def __init__(self, workspace_root: Path, context_file: Path | None = None):
        self.workspace_root = Path(workspace_root)
        self.context_file = Path(context_file) if context_file else (self.workspace_root / ".neuroshell" / "github_context.json")
        self._default_repo = self._load_default_repo()

    @staticmethod
    def _validate_repo(repo: str) -> str:
        value = repo.strip()
        if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", value):
            raise ValueError("Repository must be in owner/name format")
        return value

    def _load_default_repo(self) -> str | None:
        try:
            if self.context_file.exists():
                data = json.loads(self.context_file.read_text(encoding="utf-8"))
                repo = (data.get("default_repo") or "").strip()
                return repo or None
        except Exception:
            return None
        return None

    def _save_default_repo(self, repo: str) -> None:
        self.context_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "default_repo": repo,
        }
        self.context_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def set_default_repo(self, repo: str) -> str:
        value = self._validate_repo(repo)
        self._default_repo = value
        self._save_default_repo(value)
        return value

    def get_default_repo(self) -> str | None:
        return self._default_repo

    @staticmethod
    def _gh_path() -> str | None:
        gh = shutil.which("gh")
        if gh:
            return gh

        # Support fresh installs where PATH is not refreshed in current shell.
        fallback_candidates = [
            Path("C:/Program Files/GitHub CLI/gh.exe"),
            Path("C:/Program Files (x86)/GitHub CLI/gh.exe"),
        ]
        for candidate in fallback_candidates:
            if candidate.exists():
                return str(candidate)

        return None

    def _run_gh(self, args: list[str], timeout_s: int = 60) -> subprocess.CompletedProcess:
        gh = self._gh_path()
        if gh is None:
            raise RuntimeError("GitHub CLI (gh) not found. Install from https://cli.github.com/")

        return subprocess.run(
            [gh] + args,
            cwd=str(self.workspace_root),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )

    @staticmethod
    def _with_repo(args: list[str], repo: str | None) -> list[str]:
        if repo:
            return args + ["--repo", repo]
        return args

    def _resolve_repo(self, repo: str | None) -> str | None:
        if repo:
            return self._validate_repo(repo)
        return self._default_repo

    def status(self) -> dict:
        gh = self._gh_path()
        if gh is None:
            return {"gh_installed": False, "authenticated": False, "detail": "gh not installed"}

        auth = self._run_gh(["auth", "status", "-h", "github.com"], timeout_s=20)
        return {
            "gh_installed": True,
            "authenticated": auth.returncode == 0,
            "default_repo": self._default_repo,
            "detail": (auth.stdout or auth.stderr).strip()[:500],
        }

    def repo_view(self, repo: str | None = None) -> dict:
        resolved_repo = self._resolve_repo(repo)
        args = ["repo", "view"]
        if resolved_repo:
            args.append(resolved_repo)
        args += ["--json", "nameWithOwner,url,defaultBranchRef"]
        cp = self._run_gh(args)
        if cp.returncode != 0:
            raise RuntimeError((cp.stderr or cp.stdout or "failed to view repo").strip())
        return json.loads(cp.stdout or "{}")

    def pr_list(self, state: str = "open", limit: int = 20, repo: str | None = None) -> list[dict]:
        resolved_repo = self._resolve_repo(repo)
        cp = self._run_gh(self._with_repo([
            "pr", "list", "--state", state, "--limit", str(limit),
            "--json", "number,title,author,headRefName,baseRefName,url,updatedAt"
        ], resolved_repo))
        if cp.returncode != 0:
            raise RuntimeError((cp.stderr or cp.stdout or "failed to list PRs").strip())
        return json.loads(cp.stdout or "[]")

    def pr_view(self, number: int, repo: str | None = None) -> dict:
        resolved_repo = self._resolve_repo(repo)
        cp = self._run_gh(self._with_repo([
            "pr", "view", str(number),
            "--json", "number,title,author,state,headRefName,baseRefName,url,mergeStateStatus,body"
        ], resolved_repo))
        if cp.returncode != 0:
            raise RuntimeError((cp.stderr or cp.stdout or "failed to view PR").strip())
        return json.loads(cp.stdout or "{}")

    def pr_create(
        self,
        title: str,
        body: str,
        base: str | None = None,
        head: str | None = None,
        repo: str | None = None,
    ) -> str:
        resolved_repo = self._resolve_repo(repo)
        args = ["pr", "create", "--title", title, "--body", body]
        if base:
            args += ["--base", base]
        if head:
            args += ["--head", head]

        cp = self._run_gh(self._with_repo(args, resolved_repo), timeout_s=90)
        if cp.returncode != 0:
            raise RuntimeError((cp.stderr or cp.stdout or "failed to create PR").strip())
        return (cp.stdout or "").strip()

    def issue_list(self, state: str = "open", limit: int = 20, repo: str | None = None) -> list[dict]:
        resolved_repo = self._resolve_repo(repo)
        cp = self._run_gh(self._with_repo([
            "issue", "list", "--state", state, "--limit", str(limit),
            "--json", "number,title,author,state,url,updatedAt"
        ], resolved_repo))
        if cp.returncode != 0:
            raise RuntimeError((cp.stderr or cp.stdout or "failed to list issues").strip())
        return json.loads(cp.stdout or "[]")

    def issue_create(self, title: str, body: str, repo: str | None = None) -> str:
        resolved_repo = self._resolve_repo(repo)
        cp = self._run_gh(
            self._with_repo(["issue", "create", "--title", title, "--body", body], resolved_repo),
            timeout_s=90,
        )
        if cp.returncode != 0:
            raise RuntimeError((cp.stderr or cp.stdout or "failed to create issue").strip())
        return (cp.stdout or "").strip()
