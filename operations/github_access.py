# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Production GitHub access helpers powered by GitHub CLI (gh)."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
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

    def repo_list(self, user_or_org: str | None = None, limit: int = 30) -> list[dict]:
        """List GitHub repositories owned by authenticated user or any public user/org."""
        args = ["repo", "list"]
        if user_or_org:
            args.append(user_or_org)
        args += ["--limit", str(limit), "--json", "nameWithOwner,isPrivate,isFork,updatedAt,description"]
        cp = self._run_gh(args)
        if cp.returncode != 0:
            raise RuntimeError((cp.stderr or cp.stdout or "failed to list repositories").strip())
        return json.loads(cp.stdout or "[]")

    def repo_readme(self, repo: str) -> str:
        """Fetch and return the README of any GitHub repository in markdown format."""
        resolved = self._resolve_repo(repo) or repo
        cp = self._run_gh(["repo", "view", resolved])
        if cp.returncode != 0:
            raise RuntimeError((cp.stderr or cp.stdout or f"Failed to view README for {repo}").strip())
        return cp.stdout

    def repo_tree(self, repo: str) -> list[str]:
        """Fetch the list of files in any repository without cloning."""
        resolved = self._resolve_repo(repo) or repo
        cp = self._run_gh(["api", f"repos/{resolved}/git/trees/HEAD?recursive=1", "--jq", ".tree[].path"])
        if cp.returncode == 0 and cp.stdout.strip():
            return [line.strip() for line in cp.stdout.splitlines() if line.strip()]
        return []

    def repo_security_audit(self, repo: str) -> dict:
        """Perform a quick Zero-Trust security scan of any local or remote repository."""
        resolved = self._resolve_repo(repo) or repo
        tree = self.repo_tree(resolved)

        has_ci = any(".github/workflows" in f for f in tree)
        has_security_md = any("SECURITY" in f.upper() for f in tree)
        has_license = any("LICENSE" in f.upper() for f in tree)

        deps = []
        if any("requirements.txt" in f or "pyproject.toml" in f for f in tree):
            deps.append("Python")
        if any("package.json" in f for f in tree):
            deps.append("Node.js / JavaScript")
        if any("Cargo.toml" in f for f in tree):
            deps.append("Rust")
        if any("go.mod" in f for f in tree):
            deps.append("Go")

        score = 80
        if has_ci:
            score += 10
        if has_security_md:
            score += 5
        if has_license:
            score += 5

        return {
            "repository": resolved,
            "file_count": len(tree),
            "ecosystems": deps,
            "has_ci": has_ci,
            "has_security_policy": has_security_md,
            "has_license": has_license,
            "security_score": min(score, 100)
        }

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


# ═══════════════════════════════════════════════════════════
# Dynamic GitHub Identity & CLI Environment Resolver
# ═══════════════════════════════════════════════════════════

@dataclass
class GitHubIdentity:
    """Live GitHub environment and user identity representation."""
    cli_installed: bool = False
    cli_path: str | None = None
    cli_version: str | None = None
    authenticated: bool = False
    username: str | None = None
    profile_url: str | None = None
    display_name: str | None = None
    email: str | None = None
    default_repo: str | None = None
    origin_repo: str | None = None
    install_command: str = ""

    def summary(self) -> str:
        if self.cli_installed and self.authenticated and self.username:
            repo_info = f" | Current Repo: {self.origin_repo}" if self.origin_repo else ""
            return (
                f"GitHub CLI: Available (Authenticated as @{self.username}{repo_info})\n"
                f"Profile URL: {self.profile_url or f'https://github.com/{self.username}'}"
            )
        elif self.cli_installed and self.authenticated:
            return "GitHub CLI: Available (Authenticated)\nProfile URL: https://github.com"
        elif self.cli_installed:
            return f"GitHub CLI: Installed ({self.cli_version or 'detected'}), but not authenticated. Run 'gh auth login' to connect your GitHub."
        elif self.username:
            return (
                f"GitHub CLI: Not installed (Detected git user @{self.username})\n"
                f"Profile URL: {self.profile_url or f'https://github.com/{self.username}'}\n"
                f"Install CLI: {self.install_command}"
            )
        else:
            return f"GitHub CLI: Not installed\nInstall CLI: {self.install_command}"


class GitHubIdentityResolver:
    """Cached, zero-latency resolver for GitHub CLI status and user identity."""
    _cached_identity: GitHubIdentity | None = None
    _last_resolved: float = 0.0
    _CACHE_TTL_SECONDS: float = 300.0  # 5 minutes

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached identity."""
        cls._cached_identity = None
        cls._last_resolved = 0.0

    @classmethod
    def get_install_command(cls) -> str:
        system = platform.system()
        if system == "Windows":
            return "winget install --id GitHub.cli --accept-source-agreements --accept-package-agreements"
        elif system == "Darwin":
            return "brew install gh"
        else:
            # Linux distro detection
            if shutil.which("apt") or shutil.which("apt-get"):
                return "sudo apt update && sudo apt install -y gh"
            elif shutil.which("dnf"):
                return "sudo dnf install -y gh"
            elif shutil.which("pacman"):
                return "sudo pacman -S --noconfirm github-cli"
            return "sudo apt install -y gh"

    @classmethod
    def resolve(cls, workspace_root: Path | None = None, force_refresh: bool = False) -> GitHubIdentity:
        now = time.time()
        if not force_refresh and cls._cached_identity is not None and (now - cls._last_resolved) < cls._CACHE_TTL_SECONDS:
            return cls._cached_identity

        ws = workspace_root or Path.cwd()
        install_cmd = cls.get_install_command()
        identity = GitHubIdentity(install_command=install_cmd)

        # 1. Detect gh executable
        gh_path = GitHubAccessManager._gh_path()
        if gh_path:
            identity.cli_installed = True
            identity.cli_path = gh_path

            # Detect version
            try:
                cp_ver = subprocess.run([gh_path, "--version"], capture_output=True, text=True, timeout=3)
                if cp_ver.returncode == 0:
                    ver_line = cp_ver.stdout.splitlines()[0] if cp_ver.stdout else ""
                    m = re.search(r"gh version (\S+)", ver_line)
                    if m:
                        identity.cli_version = m.group(1)
            except Exception:
                pass

            # Detect authenticated user via gh api user
            try:
                cp_user = subprocess.run(
                    [gh_path, "api", "user", "--jq", "{login: .login, html_url: .html_url, name: .name, email: .email}"],
                    cwd=str(ws),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if cp_user.returncode == 0 and cp_user.stdout.strip():
                    user_data = json.loads(cp_user.stdout)
                    identity.authenticated = True
                    identity.username = user_data.get("login")
                    identity.profile_url = user_data.get("html_url")
                    identity.display_name = user_data.get("name")
                    identity.email = user_data.get("email")
            except Exception:
                pass

            # Fallback auth check via gh auth status if user API had transient error
            if not identity.authenticated:
                try:
                    cp_auth = subprocess.run(
                        [gh_path, "auth", "status", "-h", "github.com"],
                        cwd=str(ws),
                        capture_output=True,
                        text=True,
                        timeout=4,
                    )
                    if cp_auth.returncode == 0:
                        identity.authenticated = True
                        combined = cp_auth.stdout + "\n" + cp_auth.stderr
                        m_user = re.search(r"Logged in to github\.com account (\S+)", combined)
                        if m_user:
                            identity.username = m_user.group(1)
                            identity.profile_url = f"https://github.com/{identity.username}"
                except Exception:
                    pass

        # 2. Extract git repo and user fallbacks from local workspace
        try:
            cp_remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(ws), capture_output=True, text=True, timeout=3)
            if cp_remote.returncode == 0 and cp_remote.stdout.strip():
                raw_url = cp_remote.stdout.strip()
                # Parse owner/repo from URL
                m_repo = re.search(r"github\.com[:/](?:[^/@]+@)?([^/]+)/([^/\.]+)", raw_url)
                if m_repo:
                    repo_owner = m_repo.group(1)
                    repo_name = m_repo.group(2)
                    identity.origin_repo = f"{repo_owner}/{repo_name}"
                    if not identity.username:
                        identity.username = repo_owner
                    if not identity.profile_url:
                        identity.profile_url = f"https://github.com/{repo_owner}"
        except Exception:
            pass

        # 3. Extract git user.name if username still empty
        if not identity.username:
            try:
                cp_name = subprocess.run(["git", "config", "--get", "user.name"], cwd=str(ws), capture_output=True, text=True, timeout=2)
                if cp_name.returncode == 0 and cp_name.stdout.strip():
                    identity.display_name = cp_name.stdout.strip()
            except Exception:
                pass

        if identity.username and not identity.profile_url:
            identity.profile_url = f"https://github.com/{identity.username}"

        cls._cached_identity = identity
        cls._last_resolved = now
        return identity


def get_cached_github_identity(workspace_root: Path | None = None, force_refresh: bool = False) -> GitHubIdentity:
    """Retrieve the cached GitHub environment and user identity."""
    return GitHubIdentityResolver.resolve(workspace_root=workspace_root, force_refresh=force_refresh)


get_github_identity = get_cached_github_identity


def get_github_install_command() -> str:
    """Return the package manager command to install GitHub CLI on this OS."""
    return GitHubIdentityResolver.get_install_command()


def install_github_cli() -> subprocess.CompletedProcess:
    """Execute the platform package manager to install GitHub CLI."""
    cmd = get_github_install_command()
    shell = platform.system() == "Windows"
    res = subprocess.run(cmd, shell=True, capture_output=False, text=True)
    # Clear cache so next check sees newly installed binary
    GitHubIdentityResolver._cached_identity = None
    GitHubIdentityResolver._last_resolved = 0.0
    return res

