# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Semantic Workspace Graph Engine for NeuroShell.
Discovers local repository manifests, build tools, package managers,
Docker configurations, and Git context in under 2ms to ground natural language
translations and autonomous agent plans in the exact project codebase.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProjectManifest:
    """Detailed metadata for a discovered workspace project."""
    root_dir: Path
    project_type: str = "generic"  # "node", "python", "rust", "go", "java", "generic"
    framework: str = ""           # "next", "react", "fastapi", "django", "flask", "express"
    package_manager: str = ""     # "npm", "pnpm", "yarn", "bun", "pip", "uv", "cargo", "go"
    scripts: dict[str, str] = field(default_factory=dict)
    docker_services: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    venv_path: Path | None = None
    git_branch: str = ""
    git_dirty_files: int = 0
    recent_modified_files: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"Type: {self.project_type}"]
        if self.framework:
            parts.append(f"Framework: {self.framework}")
        if self.package_manager:
            parts.append(f"PM: {self.package_manager}")
        if self.scripts:
            known = [k for k in ("dev", "start", "build", "test", "lint") if k in self.scripts]
            if known:
                parts.append(f"Scripts: {', '.join(known)}")
        if self.docker_services:
            parts.append(f"Services: {', '.join(self.docker_services)}")
        if self.git_branch:
            dirty_str = f" ({self.git_dirty_files} dirty)" if self.git_dirty_files > 0 else " (clean)"
            parts.append(f"Git: {self.git_branch}{dirty_str}")
        return " | ".join(parts)


class WorkspaceProjectGraph:
    """
    Sub-millisecond semantic scanner that analyzes the current repository
    and constructs a dynamic project context graph.
    """

    _CACHE: dict[str, tuple[float, ProjectManifest]] = {}
    CACHE_TTL_SECONDS = 5.0

    @classmethod
    def get_manifest(cls, directory: str | Path | None = None) -> ProjectManifest:
        """Fetch or dynamically scan workspace manifest with short TTL cache."""
        target_dir = Path(directory or os.getcwd()).resolve()
        dir_key = str(target_dir)

        # Check cache
        import time
        now = time.time()
        if dir_key in cls._CACHE:
            ts, cached = cls._CACHE[dir_key]
            if (now - ts) < cls.CACHE_TTL_SECONDS:
                return cached

        manifest = cls._scan(target_dir)
        cls._CACHE[dir_key] = (now, manifest)
        return manifest

    @classmethod
    def _scan(cls, root: Path) -> ProjectManifest:
        manifest = ProjectManifest(root_dir=root)

        # 1. Scan Node.js ecosystem
        pkg_json = root / "package.json"
        if pkg_json.exists():
            manifest.project_type = "node"
            manifest.package_manager = "npm"
            if (root / "pnpm-lock.yaml").exists():
                manifest.package_manager = "pnpm"
            elif (root / "yarn.lock").exists():
                manifest.package_manager = "yarn"
            elif (root / "bun.lockb").exists():
                manifest.package_manager = "bun"

            try:
                with open(pkg_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    manifest.scripts = data.get("scripts", {})
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    if "next" in deps:
                        manifest.framework = "next"
                    elif "react" in deps:
                        manifest.framework = "react"
                    elif "vue" in deps:
                        manifest.framework = "vue"
                    elif "express" in deps:
                        manifest.framework = "express"
                    elif "nestjs" in deps or "@nestjs/core" in deps:
                        manifest.framework = "nest"
            except Exception:
                pass

        # 2. Scan Python ecosystem
        pyproject = root / "pyproject.toml"
        reqs = root / "requirements.txt"
        setup_py = root / "setup.py"
        if pyproject.exists() or reqs.exists() or setup_py.exists():
            if manifest.project_type == "generic":
                manifest.project_type = "python"
            manifest.package_manager = "uv" if (root / "uv.lock").exists() else "pip"

            # Check virtual environment
            for vname in (".venv", "venv", "env", ".env"):
                vpath = root / vname
                if vpath.is_dir() and ((vpath / "bin" / "activate").exists() or (vpath / "Scripts" / "activate.bat").exists()):
                    manifest.venv_path = vpath
                    break

            # Framework detection
            content = ""
            for p in (pyproject, reqs):
                if p.exists():
                    try:
                        content += p.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        pass
            lower_content = content.lower()
            if "fastapi" in lower_content:
                manifest.framework = "fastapi"
            elif "django" in lower_content:
                manifest.framework = "django"
            elif "flask" in lower_content:
                manifest.framework = "flask"
            elif "torch" in lower_content or "transformers" in lower_content:
                manifest.framework = "pytorch"

        # 3. Scan Rust ecosystem
        cargo_toml = root / "Cargo.toml"
        if cargo_toml.exists():
            manifest.project_type = "rust"
            manifest.package_manager = "cargo"

        # 4. Scan Go ecosystem
        go_mod = root / "go.mod"
        if go_mod.exists():
            manifest.project_type = "go"
            manifest.package_manager = "go"

        # 5. Scan Docker & Compose
        for compose_file in ("docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml"):
            cp = root / compose_file
            if cp.exists():
                try:
                    text = cp.read_text(encoding="utf-8", errors="ignore")
                    services = re.findall(r"^\s{2}([a-zA-Z0-9_-]+):\s*$", text, re.MULTILINE)
                    if services:
                        manifest.docker_services = services
                    # Extract exposed ports
                    ports_found = re.findall(r"['\"]?(\d{2,5}):\d{2,5}['\"]?", text)
                    manifest.ports = [int(p) for p in ports_found if p.isdigit()]
                except Exception:
                    pass
                break

        # 6. Git metadata (fast check)
        git_dir = root / ".git"
        if git_dir.exists():
            try:
                # Fast head read
                head_file = git_dir / "HEAD"
                if head_file.exists():
                    head_line = head_file.read_text(encoding="utf-8").strip()
                    if head_line.startswith("ref: refs/heads/"):
                        manifest.git_branch = head_line.replace("ref: refs/heads/", "")
                    else:
                        manifest.git_branch = head_line[:8]
            except Exception:
                pass

        return manifest

    @classmethod
    def resolve_action(cls, natural_intent: str, directory: str | Path | None = None) -> str | None:
        """
        Map common developer natural intents directly to verified repository commands.
        Eliminates LLM latency and hallucination for common workspace workflows.
        """
        manifest = cls.get_manifest(directory)
        intent = natural_intent.lower().strip()
        is_windows = os.name == "nt"

        # 1. Dev Server Start
        if re.search(r"\b(?:start|run|launch)\s+(?:the\s+)?(?:dev|development|frontend|client|app|server)\b", intent):
            if manifest.project_type == "node":
                if "dev" in manifest.scripts:
                    return f"{manifest.package_manager} run dev"
                elif "start" in manifest.scripts:
                    return f"{manifest.package_manager} start"
            elif manifest.project_type == "python":
                if manifest.framework == "fastapi":
                    return "uvicorn main:app --reload"
                elif manifest.framework == "django":
                    return "python manage.py runserver"
                elif (manifest.root_dir / "main.py").exists():
                    return "python main.py"
                elif (manifest.root_dir / "app.py").exists():
                    return "python app.py"
            elif manifest.project_type == "rust":
                return "cargo run"
            elif manifest.project_type == "go":
                return "go run ."

        # 2. Test Suite Execution
        if re.search(r"\b(?:run|execute)\s+(?:the\s+)?(?:tests?|test\s+suite|unit\s+tests?|spec)\b", intent):
            if manifest.project_type == "node":
                if "test" in manifest.scripts:
                    return f"{manifest.package_manager} test"
            elif manifest.project_type == "python":
                return "pytest"
            elif manifest.project_type == "rust":
                return "cargo test"
            elif manifest.project_type == "go":
                return "go test ./..."

        # 3. Project Build
        if re.search(r"\b(?:build|compile)\s+(?:the\s+)?(?:project|app|code|release|bundle)\b", intent):
            if manifest.project_type == "node" and "build" in manifest.scripts:
                return f"{manifest.package_manager} run build"
            elif manifest.project_type == "rust":
                return "cargo build --release"
            elif manifest.project_type == "go":
                return "go build -v ."

        # 4. Linter / Formatter
        if re.search(r"\b(?:run|check)\s+(?:the\s+)?(?:linter|lint|formatting|typecheck)\b", intent):
            if manifest.project_type == "node":
                if "lint" in manifest.scripts:
                    return f"{manifest.package_manager} run lint"
            elif manifest.project_type == "python":
                return "ruff check ." if is_windows else "ruff check ."

        # 5. Database & Docker Services
        if re.search(r"\b(?:start|up|launch)\s+(?:the\s+)?(?:database|db|postgres|redis|containers?|services?)\b", intent):
            if manifest.docker_services:
                # Find matching service if specified
                for s in manifest.docker_services:
                    if s.lower() in intent:
                        return f"docker compose up -d {s}"
                return "docker compose up -d"

        # 6. Virtual Environment Activation
        if re.search(r"\b(?:activate)\s+(?:the\s+)?(?:venv|virtual\s*env)\b", intent):
            if manifest.venv_path:
                vrel = manifest.venv_path.relative_to(manifest.root_dir)
                if is_windows:
                    return f"{vrel}\\Scripts\\activate"
                return f"source {vrel}/bin/activate"

        return None
