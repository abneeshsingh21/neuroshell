# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Context Manager — Production Grade
Deep environment intelligence: Docker, virtual envs, project detection,
git branch/stash/remote info, package manager awareness, and IDE integration.
"""

import os
import platform
import shutil
import socket
import subprocess
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import time

try:
    import psutil
except ImportError:
    psutil = None


# ═══════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════

@dataclass
class GitContext:
    """Comprehensive git repository context."""
    is_repo: bool = False
    branch: str = ""
    has_changes: bool = False
    remote_url: str = ""
    ahead: int = 0
    behind: int = 0
    staged_count: int = 0
    unstaged_count: int = 0
    untracked_count: int = 0
    stash_count: int = 0
    last_commit_msg: str = ""
    last_commit_age: str = ""
    remotes: list = field(default_factory=list)
    active_merge: bool = False
    active_rebase: bool = False

    @property
    def status_line(self) -> str:
        """One-line git status."""
        if not self.is_repo:
            return "not a git repo"
        parts = [self.branch]
        if self.ahead:
            parts.append(f"↑{self.ahead}")
        if self.behind:
            parts.append(f"↓{self.behind}")
        if self.staged_count:
            parts.append(f"+{self.staged_count}")
        if self.unstaged_count:
            parts.append(f"~{self.unstaged_count}")
        if self.untracked_count:
            parts.append(f"?{self.untracked_count}")
        if self.stash_count:
            parts.append(f"⚑{self.stash_count}")
        if self.active_merge:
            parts.append("MERGE")
        if self.active_rebase:
            parts.append("REBASE")
        return " ".join(parts)


@dataclass
class ContainerContext:
    """Docker/container environment context."""
    is_inside_container: bool = False
    docker_available: bool = False
    running_containers: int = 0
    compose_file: str = ""
    compose_services: list = field(default_factory=list)
    active_images: list = field(default_factory=list)


@dataclass
class VirtualEnvContext:
    """Virtual environment context."""
    active: bool = False
    type: str = ""        # venv, conda, pyenv, poetry, pipenv, nvm
    name: str = ""
    path: str = ""
    python_version: str = ""
    node_version: str = ""


@dataclass
class SystemResources:
    """System resource snapshot."""
    cpu_percent: float = 0.0
    cpu_cores: int = 0
    ram_total_gb: float = 0.0
    ram_used_gb: float = 0.0
    ram_available_gb: float = 0.0
    ram_percent: float = 0.0
    disk_total_gb: float = 0.0
    disk_free_gb: float = 0.0
    disk_percent: float = 0.0
    load_avg: tuple = ()
    swap_used_gb: float = 0.0
    process_count: int = 0

    @property
    def is_high_load(self) -> bool:
        return self.cpu_percent > 80 or self.ram_percent > 85

    @property
    def summary(self) -> str:
        return f"CPU:{self.cpu_percent:.0f}% RAM:{self.ram_percent:.0f}% Disk:{self.disk_percent:.0f}%"


@dataclass
class NetworkStatus:
    """Network connectivity status."""
    is_online: bool = False
    last_check: float = 0.0
    latency_ms: float = 0.0
    dns_working: bool = False
    public_ip: str = ""

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.last_check) > 30


@dataclass
class ProjectContext:
    """Detected project/workspace context."""
    type: str = ""                    # python, node, rust, go, java, cpp, docker, terraform
    name: str = ""                    # project name from config
    version: str = ""                 # project version from config
    manager: str = ""                 # pip, npm, yarn, cargo, maven, gradle
    entry_point: str = ""             # main.py, index.js, main.rs
    scripts: list = field(default_factory=list)    # available scripts/commands
    dependencies_count: int = 0
    has_tests: bool = False
    has_ci: bool = False
    has_dockerfile: bool = False
    has_makefile: bool = False
    readme_exists: bool = False
    license_exists: bool = False


@dataclass
class ContextSnapshot:
    """Full system context at a point in time."""
    timestamp: float = field(default_factory=time.time)
    cwd: str = ""
    os_name: str = ""
    os_version: str = ""
    shell: str = ""
    python_version: str = ""
    git: GitContext = field(default_factory=GitContext)
    container: ContainerContext = field(default_factory=ContainerContext)
    virtualenv: VirtualEnvContext = field(default_factory=VirtualEnvContext)
    project: ProjectContext = field(default_factory=ProjectContext)
    resources: SystemResources = field(default_factory=SystemResources)
    network: NetworkStatus = field(default_factory=NetworkStatus)
    available_tools: list = field(default_factory=list)
    env_vars: dict = field(default_factory=dict)
    files_in_cwd: list = field(default_factory=list)
    hostname: str = ""
    username: str = ""
    workspace_type: Optional[str] = None


# ═══════════════════════════════════════════════════════════
# Context Manager — Production Engine
# ═══════════════════════════════════════════════════════════

class ContextManager:
    """
    Production-grade context manager with deep environment intelligence.

    Features:
    - Comprehensive git context (ahead/behind, stash, merge/rebase state)
    - Docker/container environment detection
    - Virtual environment detection (venv, conda, pyenv, poetry, nvm)
    - Project type and package manager intelligence
    - System resource monitoring with high-load alerts
    - Network status with DNS verification
    - Tool availability caching
    - LLM-optimized context summary
    """

    TOOL_CACHE_TTL = 120           # 2 minutes
    CONTEXT_CACHE_TTL = 5          # 5 seconds for full context
    GIT_TIMEOUT = 5                # seconds

    # Extended tool detection list
    KNOWN_TOOLS = [
        # Core
        "git", "python", "python3", "pip", "pip3",
        # Node.js
        "node", "npm", "npx", "yarn", "pnpm", "bun", "deno",
        # Container
        "docker", "docker-compose", "podman", "kubectl", "helm",
        # Cloud
        "aws", "az", "gcloud", "terraform", "pulumi",
        # Languages
        "gcc", "g++", "clang", "cmake", "make", "cargo", "rustc",
        "go", "java", "javac", "mvn", "gradle",
        "dotnet", "ruby", "php", "swift",
        # macOS / Darwin
        "brew", "launchctl", "ioreg", "vm_stat", "pbcopy", "pbpaste", "osascript", "sw_vers",
        # Linux / System
        "systemctl", "journalctl", "apt", "dnf", "pacman", "zypper", "apk", "wl-copy", "wl-paste", "xclip",
        # Tools
        "curl", "wget", "ssh", "scp", "rsync", "tar", "zip", "unzip",
        "jq", "yq", "rg", "fd", "fzf", "bat", "exa", "htop",
        "tmux", "screen", "vim", "nvim", "code",
        # Database
        "psql", "mysql", "mongosh", "redis-cli", "sqlite3",
    ]

    def __init__(self, config):
        self.config = config
        self._network = NetworkStatus()
        self._tool_cache: Optional[list[str]] = None
        self._tool_cache_time: float = 0
        self._context_cache: Optional[ContextSnapshot] = None
        self._context_cache_time: float = 0

    def get_context(self, cwd: Optional[str] = None) -> ContextSnapshot:
        """Get full system context snapshot with caching."""
        cwd = cwd or os.getcwd()

        # Return cache if fresh
        if (self._context_cache
            and not self._is_cache_stale()
            and self._context_cache.cwd == cwd):
            return self._context_cache

        ctx = ContextSnapshot(
            cwd=cwd,
            os_name=platform.system(),
            os_version=platform.version(),
            shell=getattr(self.config, "default_shell", self._detect_shell()),
            python_version=platform.python_version(),
            hostname=platform.node(),
            username=os.environ.get("USER", os.environ.get("USERNAME", "")),
            git=self._get_git_context(cwd),
            container=self._get_container_context(cwd),
            virtualenv=self._get_virtualenv_context(),
            project=self._detect_project(cwd),
            resources=self._get_resources(),
            network=self._get_network_status(),
            available_tools=self._get_available_tools(),
            env_vars=self._get_safe_env_vars(),
            files_in_cwd=self._get_cwd_files(cwd),
        )
        ctx.workspace_type = ctx.project.type or None

        self._context_cache = ctx
        self._context_cache_time = time.time()
        return ctx

    def get_context_summary(self, cwd: Optional[str] = None) -> str:
        """Get a compact, LLM-optimized context string."""
        ctx = self.get_context(cwd)
        parts = [
            f"OS: {ctx.os_name}",
            f"Shell: {ctx.shell}",
            f"CWD: {ctx.cwd}",
        ]

        if ctx.git.is_repo:
            parts.append(f"Git: {ctx.git.status_line}")

        if ctx.project.type:
            project_info = f"Project: {ctx.project.type}"
            if ctx.project.manager:
                project_info += f"/{ctx.project.manager}"
            if ctx.project.name:
                project_info += f" ({ctx.project.name})"
            parts.append(project_info)

        if ctx.virtualenv.active:
            parts.append(f"Env: {ctx.virtualenv.type}:{ctx.virtualenv.name}")

        if ctx.container.is_inside_container:
            parts.append("Container: yes")
        elif ctx.container.running_containers > 0:
            parts.append(f"Docker: {ctx.container.running_containers} running")

        parts.append(f"Net: {'online' if ctx.network.is_online else 'offline'}")

        if ctx.resources.is_high_load:
            parts.append(f"⚠ {ctx.resources.summary}")

        # Key files
        notable = [f for f in ctx.files_in_cwd if f in (
            "Makefile", "Dockerfile", "docker-compose.yml", ".env", "README.md"
        )]
        if notable:
            parts.append(f"Files: {', '.join(notable)}")

        return " | ".join(parts)

    def get_prompt_context(self, cwd: Optional[str] = None) -> dict:
        """Get structured context optimized for LLM prompt injection."""
        ctx = self.get_context(cwd)
        return {
            "os": ctx.os_name,
            "shell": ctx.shell,
            "cwd": ctx.cwd,
            "git_branch": ctx.git.branch if ctx.git.is_repo else None,
            "git_dirty": ctx.git.has_changes if ctx.git.is_repo else None,
            "project_type": ctx.project.type,
            "package_manager": ctx.project.manager,
            "virtual_env": ctx.virtualenv.name if ctx.virtualenv.active else None,
            "tools": ctx.available_tools[:20],
            "online": ctx.network.is_online,
            "key_files": ctx.files_in_cwd[:20],
        }

    def _is_cache_stale(self) -> bool:
        return (time.time() - self._context_cache_time) > self.CONTEXT_CACHE_TTL

    # ═══════════════════════════════════════════════════════
    # Git Context
    # ═══════════════════════════════════════════════════════

    def _get_git_context(self, cwd: str) -> GitContext:
        """Comprehensive git repository context."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=cwd, capture_output=True, text=True, timeout=self.GIT_TIMEOUT,
            )
            if result.returncode != 0:
                return GitContext()

            git_dir = Path(cwd)
            ctx = GitContext(is_repo=True)

            # Branch
            ctx.branch = self._git_cmd(cwd, "branch", "--show-current") or "HEAD"

            # Status counts
            status = self._git_cmd(cwd, "status", "--porcelain")
            if status:
                for line in status.split("\n"):
                    if line.startswith("??"):
                        ctx.untracked_count += 1
                    elif line[0] != " ":
                        ctx.staged_count += 1
                    if line[1:2] not in (" ", "?"):
                        ctx.unstaged_count += 1
                ctx.has_changes = True

            # Ahead/behind
            ab = self._git_cmd(cwd, "rev-list", "--left-right", "--count", f"HEAD...@{{u}}")
            if ab and "\t" in ab:
                parts = ab.split("\t")
                ctx.ahead = int(parts[0])
                ctx.behind = int(parts[1])

            # Remote URL
            ctx.remote_url = self._git_cmd(cwd, "remote", "get-url", "origin") or ""

            # Stash count
            stash = self._git_cmd(cwd, "stash", "list")
            ctx.stash_count = len(stash.split("\n")) if stash else 0

            # Last commit
            ctx.last_commit_msg = self._git_cmd(cwd, "log", "-1", "--format=%s") or ""
            ctx.last_commit_age = self._git_cmd(cwd, "log", "-1", "--format=%cr") or ""

            # Remotes
            remotes = self._git_cmd(cwd, "remote")
            ctx.remotes = remotes.split("\n") if remotes else []

            # Merge/rebase state
            git_dir_path = self._git_cmd(cwd, "rev-parse", "--git-dir")
            if git_dir_path:
                gd = Path(cwd) / git_dir_path
                ctx.active_merge = (gd / "MERGE_HEAD").exists()
                ctx.active_rebase = (gd / "rebase-merge").exists() or (gd / "rebase-apply").exists()

            return ctx
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return GitContext()

    def _git_cmd(self, cwd: str, *args) -> str:
        """Run a git subcommand and return stdout."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=cwd, capture_output=True, text=True, timeout=self.GIT_TIMEOUT,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""

    # ═══════════════════════════════════════════════════════
    # Container Context
    # ═══════════════════════════════════════════════════════

    def _get_container_context(self, cwd: str) -> ContainerContext:
        """Detect Docker/container environment."""
        ctx = ContainerContext()

        # Am I inside a container?
        ctx.is_inside_container = (
            os.path.exists("/.dockerenv")
            or os.environ.get("CONTAINER", "") != ""
            or os.environ.get("KUBERNETES_SERVICE_HOST", "") != ""
        )

        # Docker available?
        ctx.docker_available = shutil.which("docker") is not None

        if ctx.docker_available:
            try:
                result = subprocess.run(
                    ["docker", "ps", "-q"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    containers = result.stdout.strip().split("\n")
                    ctx.running_containers = len([c for c in containers if c])
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        # Compose file detection
        compose_files = ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]
        for cf in compose_files:
            if (Path(cwd) / cf).exists():
                ctx.compose_file = cf
                try:
                    import yaml
                    data = yaml.safe_load((Path(cwd) / cf).read_text())
                    if data and "services" in data:
                        ctx.compose_services = list(data["services"].keys())
                except Exception:
                    pass
                break

        return ctx

    # ═══════════════════════════════════════════════════════
    # Virtual Environment Context
    # ═══════════════════════════════════════════════════════

    def _get_virtualenv_context(self) -> VirtualEnvContext:
        """Detect active virtual environments."""
        ctx = VirtualEnvContext()

        # Python venv
        venv = os.environ.get("VIRTUAL_ENV", "")
        if venv:
            ctx.active = True
            ctx.type = "venv"
            ctx.name = Path(venv).name
            ctx.path = venv
            ctx.python_version = platform.python_version()
            return ctx

        # Conda
        conda = os.environ.get("CONDA_DEFAULT_ENV", "")
        if conda:
            ctx.active = True
            ctx.type = "conda"
            ctx.name = conda
            ctx.path = os.environ.get("CONDA_PREFIX", "")
            ctx.python_version = platform.python_version()
            return ctx

        # Poetry
        if os.environ.get("POETRY_ACTIVE", ""):
            ctx.active = True
            ctx.type = "poetry"
            ctx.name = "poetry"
            return ctx

        # Pyenv
        pyenv = os.environ.get("PYENV_VERSION", "")
        if pyenv:
            ctx.active = True
            ctx.type = "pyenv"
            ctx.name = pyenv
            return ctx

        # nvm / Node
        nvm = os.environ.get("NVM_DIR", "")
        if nvm:
            node_ver = self._cmd_output("node", "--version")
            if node_ver:
                ctx.active = True
                ctx.type = "nvm"
                ctx.name = node_ver.strip()
                ctx.node_version = node_ver.strip()

        return ctx

    # ═══════════════════════════════════════════════════════
    # Project Detection
    # ═══════════════════════════════════════════════════════

    def _detect_project(self, cwd: str) -> ProjectContext:
        """Deep project type and structure detection."""
        p = Path(cwd)
        ctx = ProjectContext()

        # Check common files
        ctx.has_dockerfile = (p / "Dockerfile").exists() or any(p.glob("Dockerfile*"))
        ctx.has_makefile = (p / "Makefile").exists()
        ctx.readme_exists = any((p / f).exists() for f in ("README.md", "README.rst", "README.txt", "README"))
        ctx.license_exists = any((p / f).exists() for f in ("LICENSE", "LICENSE.md", "LICENSE.txt"))
        ctx.has_ci = any((p / d).exists() for d in (".github/workflows", ".gitlab-ci.yml", ".circleci", "Jenkinsfile", ".travis.yml"))
        ctx.has_tests = any((p / d).exists() for d in ("tests", "test", "__tests__", "spec"))

        # ─── Python ───
        if (p / "pyproject.toml").exists():
            ctx.type = "python"
            try:
                import tomllib
                data = tomllib.loads((p / "pyproject.toml").read_text(encoding="utf-8"))
                project = data.get("project", data.get("tool", {}).get("poetry", {}))
                ctx.name = project.get("name", "")
                ctx.version = project.get("version", "")
                deps = project.get("dependencies", {})
                ctx.dependencies_count = len(deps) if isinstance(deps, (dict, list)) else 0
                scripts = data.get("project", {}).get("scripts", {})
                ctx.scripts = list(scripts.keys())[:10]
            except Exception:
                pass
            if (p / "poetry.lock").exists():
                ctx.manager = "poetry"
            elif (p / "Pipfile").exists():
                ctx.manager = "pipenv"
            else:
                ctx.manager = "pip"
            ctx.entry_point = self._find_entry_point(p, ["main.py", "app.py", "__main__.py", "manage.py", "wsgi.py"])
            return ctx

        if any((p / f).exists() for f in ("setup.py", "requirements.txt", "Pipfile")):
            ctx.type = "python"
            ctx.manager = "pipenv" if (p / "Pipfile").exists() else "pip"
            if (p / "requirements.txt").exists():
                try:
                    lines = (p / "requirements.txt").read_text().strip().split("\n")
                    ctx.dependencies_count = len([l for l in lines if l.strip() and not l.startswith("#")])
                except Exception:
                    pass
            ctx.entry_point = self._find_entry_point(p, ["main.py", "app.py", "__main__.py"])
            return ctx

        # ─── Node.js ───
        if (p / "package.json").exists():
            ctx.type = "node"
            try:
                pkg = json.loads((p / "package.json").read_text(encoding="utf-8"))
                ctx.name = pkg.get("name", "")
                ctx.version = pkg.get("version", "")
                ctx.entry_point = pkg.get("main", "index.js")
                ctx.scripts = list(pkg.get("scripts", {}).keys())[:15]
                deps = pkg.get("dependencies", {})
                dev_deps = pkg.get("devDependencies", {})
                ctx.dependencies_count = len(deps) + len(dev_deps)
            except Exception:
                pass
            if (p / "yarn.lock").exists():
                ctx.manager = "yarn"
            elif (p / "pnpm-lock.yaml").exists():
                ctx.manager = "pnpm"
            elif (p / "bun.lockb").exists():
                ctx.manager = "bun"
            else:
                ctx.manager = "npm"
            return ctx

        # ─── Rust ───
        if (p / "Cargo.toml").exists():
            ctx.type = "rust"
            ctx.manager = "cargo"
            try:
                text = (p / "Cargo.toml").read_text()
                for line in text.split("\n"):
                    if line.startswith("name"):
                        ctx.name = line.split("=")[1].strip().strip('"')
                    if line.startswith("version"):
                        ctx.version = line.split("=")[1].strip().strip('"')
            except Exception:
                pass
            ctx.entry_point = self._find_entry_point(p, ["src/main.rs", "src/lib.rs"])
            return ctx

        # ─── Go ───
        if (p / "go.mod").exists():
            ctx.type = "go"
            ctx.manager = "go"
            try:
                text = (p / "go.mod").read_text()
                first_line = text.strip().split("\n")[0]
                if first_line.startswith("module"):
                    ctx.name = first_line.split()[-1]
            except Exception:
                pass
            ctx.entry_point = self._find_entry_point(p, ["main.go", "cmd/main.go"])
            return ctx

        # ─── Java ───
        if (p / "pom.xml").exists():
            ctx.type = "java"
            ctx.manager = "maven"
            return ctx
        if (p / "build.gradle").exists() or (p / "build.gradle.kts").exists():
            ctx.type = "java"
            ctx.manager = "gradle"
            return ctx

        # ─── C/C++ ───
        if (p / "CMakeLists.txt").exists():
            ctx.type = "cpp"
            ctx.manager = "cmake"
            return ctx
        if ctx.has_makefile:
            if any(p.glob("*.c")) or any(p.glob("*.cpp")) or any(p.glob("*.h")):
                ctx.type = "cpp"
                ctx.manager = "make"
                return ctx

        # ─── Terraform ───
        if any(p.glob("*.tf")):
            ctx.type = "terraform"
            ctx.manager = "terraform"
            return ctx

        return ctx

    def _find_entry_point(self, project_dir: Path, candidates: list) -> str:
        """Find the project entry point from a list of candidates."""
        for candidate in candidates:
            if (project_dir / candidate).exists():
                return candidate
        return ""

    # ═══════════════════════════════════════════════════════
    # System Resources
    # ═══════════════════════════════════════════════════════

    def _get_resources(self) -> SystemResources:
        """Get system resource usage."""
        if psutil is None:
            return SystemResources()

        try:
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(os.getcwd())
            swap = psutil.swap_memory()
            load = os.getloadavg() if hasattr(os, "getloadavg") else ()

            return SystemResources(
                cpu_percent=psutil.cpu_percent(interval=0.1),
                cpu_cores=psutil.cpu_count() or 1,
                ram_total_gb=round(mem.total / (1024**3), 1),
                ram_used_gb=round(mem.used / (1024**3), 1),
                ram_available_gb=round(mem.available / (1024**3), 1),
                ram_percent=mem.percent,
                disk_total_gb=round(disk.total / (1024**3), 1),
                disk_free_gb=round(disk.free / (1024**3), 1),
                disk_percent=disk.percent,
                load_avg=load,
                swap_used_gb=round(swap.used / (1024**3), 1),
                process_count=len(psutil.pids()),
            )
        except Exception:
            return SystemResources()

    # ═══════════════════════════════════════════════════════
    # Network
    # ═══════════════════════════════════════════════════════

    def _get_network_status(self) -> NetworkStatus:
        """Check network connectivity with DNS verification."""
        if not self._network.is_stale:
            return self._network

        try:
            start = time.time()
            socket.create_connection(("8.8.8.8", 53), timeout=3).close()
            latency = (time.time() - start) * 1000

            # DNS check
            dns_working = False
            try:
                socket.getaddrinfo("google.com", 443, type=socket.SOCK_STREAM)
                dns_working = True
            except socket.gaierror:
                pass

            self._network = NetworkStatus(
                is_online=True,
                last_check=time.time(),
                latency_ms=round(latency, 1),
                dns_working=dns_working,
            )
        except (socket.timeout, OSError):
            self._network = NetworkStatus(
                is_online=False,
                last_check=time.time(),
            )

        return self._network

    def check_network(self) -> bool:
        """Force-check network status."""
        self._network.last_check = 0
        return self._get_network_status().is_online

    # ═══════════════════════════════════════════════════════
    # Tools
    # ═══════════════════════════════════════════════════════

    def _get_available_tools(self) -> list[str]:
        """Detect available CLI tools with caching."""
        if self._tool_cache and (time.time() - self._tool_cache_time) < self.TOOL_CACHE_TTL:
            return self._tool_cache

        tools = []
        for tool in self.KNOWN_TOOLS:
            if shutil.which(tool):
                tools.append(tool)

        self._tool_cache = tools
        self._tool_cache_time = time.time()
        return tools

    # ═══════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════

    def _get_safe_env_vars(self) -> dict[str, str]:
        """Get environment variables filtered for safety (no secrets)."""
        safe_keys = [
            "PATH", "HOME", "USER", "USERNAME", "SHELL", "TERM", "LANG",
            "VIRTUAL_ENV", "CONDA_DEFAULT_ENV", "CONDA_PREFIX",
            "GOPATH", "GOROOT", "JAVA_HOME", "NODE_ENV",
            "DOCKER_HOST", "KUBECONFIG",
            "EDITOR", "VISUAL", "PAGER",
            "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
            "CI", "GITHUB_ACTIONS", "GITLAB_CI",
            "WSL_DISTRO_NAME",
        ]
        return {k: os.environ.get(k, "") for k in safe_keys if os.environ.get(k)}

    def _get_cwd_files(self, cwd: str, max_files: int = 80) -> list[str]:
        """List files in CWD with type indicators."""
        try:
            entries = sorted(os.listdir(cwd))
            result = []
            for entry in entries[:max_files]:
                full = os.path.join(cwd, entry)
                if os.path.isdir(full):
                    result.append(f"{entry}/")
                else:
                    result.append(entry)
            return result
        except PermissionError:
            return []

    def _cmd_output(self, *args) -> str:
        """Run a command and return stdout, or empty string on failure."""
        try:
            result = subprocess.run(
                list(args), capture_output=True, text=True, timeout=3,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except Exception:
            return ""

    def _detect_shell(self) -> str:
        """Detect default shell."""
        if platform.system() == "Windows":
            return "powershell"
        return os.path.basename(os.environ.get("SHELL", "/bin/bash"))

    def invalidate_cache(self):
        """Force cache invalidation."""
        self._context_cache = None
        self._context_cache_time = 0
        self._tool_cache = None
        self._tool_cache_time = 0
        self._network.last_check = 0
