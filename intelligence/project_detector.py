# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Project Detector
Auto-detects project types (Python, Node, Rust, Go, Docker, Java)
and provides context-aware suggestions.
"""

import fnmatch
import json
import os
import time
from dataclasses import dataclass, field

try:
    import toml as _toml
except ImportError:
    _toml = None


@dataclass
class ProjectInfo:
    """Detected project information."""
    project_type: str = "unknown"
    name: str = ""
    language: str = ""
    package_manager: str = ""
    test_command: str = ""
    run_command: str = ""
    build_command: str = ""
    lint_command: str = ""
    has_docker: bool = False
    has_git: bool = False
    has_ci: bool = False
    suggestions: list[str] = field(default_factory=list)
    files_found: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        parts = [f"📁 {self.project_type.title()} project"]
        if self.name:
            parts[0] += f": {self.name}"
        if self.has_docker:
            parts.append("🐳 Docker")
        if self.has_git:
            parts.append("🔀 Git")
        return " │ ".join(parts)


# ═══════════════════════════════════════════════════════════
# Detection rules
# ═══════════════════════════════════════════════════════════

PROJECT_SIGNATURES = [
    {
        "type": "python",
        "files": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile", "poetry.lock"],
        "language": "Python",
        "package_manager": "pip",
        "test_command": "pytest",
        "run_command": "python main.py",
        "build_command": "python -m build",
        "lint_command": "ruff check .",
        "suggestions": [
            "💡 Run tests: pytest -v",
            "💡 Install editable: pip install -e .",
            "💡 Format code: black .",
            "💡 Check types: mypy .",
        ],
    },
    {
        "type": "node",
        "files": ["package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
        "language": "JavaScript/TypeScript",
        "package_manager": "npm",
        "test_command": "npm test",
        "run_command": "npm start",
        "build_command": "npm run build",
        "lint_command": "npx eslint .",
        "suggestions": [
            "💡 Install deps: npm install",
            "💡 Run dev server: npm run dev",
            "💡 Run tests: npm test",
            "💡 Build: npm run build",
        ],
    },
    {
        "type": "rust",
        "files": ["Cargo.toml", "Cargo.lock"],
        "language": "Rust",
        "package_manager": "cargo",
        "test_command": "cargo test",
        "run_command": "cargo run",
        "build_command": "cargo build --release",
        "lint_command": "cargo clippy",
        "suggestions": [
            "💡 Build: cargo build",
            "💡 Run: cargo run",
            "💡 Test: cargo test",
            "💡 Lint: cargo clippy",
        ],
    },
    {
        "type": "go",
        "files": ["go.mod", "go.sum"],
        "language": "Go",
        "package_manager": "go",
        "test_command": "go test ./...",
        "run_command": "go run .",
        "build_command": "go build .",
        "lint_command": "golangci-lint run",
        "suggestions": [
            "💡 Run: go run .",
            "💡 Test: go test ./...",
            "💡 Build: go build .",
            "💡 Tidy deps: go mod tidy",
        ],
    },
    {
        "type": "java",
        "files": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "language": "Java",
        "package_manager": "maven/gradle",
        "test_command": "mvn test",
        "run_command": "mvn exec:java",
        "build_command": "mvn package",
        "lint_command": "mvn checkstyle:check",
        "suggestions": [
            "💡 Build: mvn package",
            "💡 Test: mvn test",
            "💡 Run: mvn exec:java",
        ],
    },
    {
        "type": "dotnet",
        "files": ["*.csproj", "*.sln", "*.fsproj"],
        "language": "C#/F#",
        "package_manager": "dotnet",
        "test_command": "dotnet test",
        "run_command": "dotnet run",
        "build_command": "dotnet build",
        "lint_command": "dotnet format",
        "suggestions": [
            "💡 Build: dotnet build",
            "💡 Run: dotnet run",
            "💡 Test: dotnet test",
        ],
    },
]


class ProjectDetector:
    """Detect project type and provide contextual suggestions."""

    # Cache TTL: 60 seconds — ensures stale entries are refreshed after `cd` + project changes
    CACHE_TTL_S = 60.0

    def __init__(self):
        self._cache: dict[str, tuple[ProjectInfo, float]] = {}  # path → (info, timestamp)

    def detect(self, directory: str = None) -> "ProjectInfo":
        """Detect project type in the given directory."""
        directory = directory or os.getcwd()
        abs_dir = os.path.abspath(directory)
        now = time.time()

        # Cache hit (within TTL)
        if abs_dir in self._cache:
            cached_info, cached_at = self._cache[abs_dir]
            if now - cached_at < self.CACHE_TTL_S:
                return cached_info

        info = ProjectInfo()

        # Check for git
        if os.path.isdir(os.path.join(abs_dir, ".git")):
            info.has_git = True

        # Check for Docker
        if os.path.isfile(os.path.join(abs_dir, "Dockerfile")) or \
           os.path.isfile(os.path.join(abs_dir, "docker-compose.yml")) or \
           os.path.isfile(os.path.join(abs_dir, "docker-compose.yaml")):
            info.has_docker = True

        # Check for CI
        ci_dirs = [".github", ".gitlab-ci.yml", ".circleci", "Jenkinsfile", ".travis.yml"]
        for ci in ci_dirs:
            if os.path.exists(os.path.join(abs_dir, ci)):
                info.has_ci = True
                break

        # Detect project type
        try:
            dir_files = set(os.listdir(abs_dir))
        except OSError:
            return info

        for sig in PROJECT_SIGNATURES:
            matched_files = []
            for pattern in sig["files"]:
                if "*" in pattern:
                    matched_files.extend(f for f in dir_files if fnmatch.fnmatch(f, pattern))
                elif pattern in dir_files:
                    matched_files.append(pattern)

            if matched_files:
                info.project_type = sig["type"]
                info.language = sig["language"]
                info.package_manager = sig["package_manager"]
                info.test_command = sig["test_command"]
                info.run_command = sig["run_command"]
                info.build_command = sig["build_command"]
                info.lint_command = sig["lint_command"]
                info.suggestions = sig["suggestions"]
                info.files_found = matched_files

                # Try to extract project name
                info.name = self._extract_name(abs_dir, sig["type"], dir_files)
                break

        # Cache result with timestamp
        self._cache[abs_dir] = (info, time.time())
        return info

    def get_startup_message(self, directory: str = None) -> str:
        """Get a startup suggestion message for the current project."""
        info = self.detect(directory)
        if info.project_type == "unknown":
            return ""

        lines = [info.summary_line()]
        # Show max 2 suggestions
        for tip in info.suggestions[:2]:
            lines.append(f"  {tip}")
        return "\n".join(lines)

    def _extract_name(self, directory: str, project_type: str, files: set) -> str:
        """Try to extract the project name from config files."""

        if project_type == "node" and "package.json" in files:
            try:
                with open(os.path.join(directory, "package.json")) as f:
                    data = json.load(f)
                    return data.get("name", "")
            except Exception:
                pass
        elif project_type == "python" and "pyproject.toml" in files:
            try:
                if _toml is not None:
                    with open(os.path.join(directory, "pyproject.toml")) as f:
                        data = _toml.load(f)
                        return data.get("project", {}).get("name", "")
            except Exception:
                pass
        elif project_type == "rust" and "Cargo.toml" in files:
            try:
                if _toml is not None:
                    with open(os.path.join(directory, "Cargo.toml")) as f:
                        data = _toml.load(f)
                        return data.get("package", {}).get("name", "")
            except Exception:
                pass

        return os.path.basename(directory)

    def invalidate_cache(self, directory: str = None):
        """Invalidate cached project info."""
        if directory:
            self._cache.pop(os.path.abspath(directory), None)
        else:
            self._cache.clear()
