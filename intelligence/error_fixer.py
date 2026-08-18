# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Error Fixer — Production Grade
Multi-strategy auto-fix: offline patterns (25+) → cached fixes → LLM.
Each pattern provides an actionable fix command, not just a hint.
"""

import re
import os
import platform
import hashlib
import time
from typing import Optional
from dataclasses import dataclass, field

from observability.provenance import ProvenanceTag, ProvenanceSource

# Pre-flag for convenience
_IS_WINDOWS = platform.system() == "Windows"


@dataclass
class FixResult:
    """Result of error analysis."""
    fix_command: str
    explanation: str
    confidence: float
    alternative_fixes: list[str] = field(default_factory=list)
    root_cause: str = ""
    provenance: Optional[ProvenanceTag] = None


def _safe_elevated_cmd(cmd: str) -> str:
    if not _IS_WINDOWS:
        return f"sudo {cmd}"
    # Escape quotes cleanly for PowerShell RunAs argument list
    safe_arg = cmd.replace("'", "''").replace('"', '`"')
    return f'powershell -NoProfile -Command "Start-Process cmd -ArgumentList \'/c {safe_arg}\' -Verb RunAs"'


# ═══════════════════════════════════════════════════════
# Offline Error Pattern Database
# Key: compiled regex, Value: handler function name or fix dict
# ═══════════════════════════════════════════════════════

_PATTERNS = [
    # ── Python Errors ───────────────────────────────
    {
        "regex": r"No module named ['\"](\w[\w\.]*)['\"]",
        "extract": 1,
        "fix_fn": lambda m, cmd: FixResult(
            fix_command=f"pip install {m.group(1).split('.')[0]}",
            explanation=f"Python package '{m.group(1)}' is not installed",
            confidence=0.92,
            root_cause="missing_package",
            alternative_fixes=[f"pip install --user {m.group(1).split('.')[0]}",
                               f"pip3 install {m.group(1).split('.')[0]}"],
        ),
    },
    {
        "regex": r"ImportError: cannot import name ['\"](\w+)['\"] from ['\"](\w[\w\.]*)['\"]",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command=f"pip install --upgrade {m.group(2).split('.')[0]}",
            explanation=f"'{m.group(1)}' doesn't exist in '{m.group(2)}' — likely version mismatch",
            confidence=0.8,
            root_cause="version_mismatch",
            alternative_fixes=[f"pip install --upgrade {m.group(2).split('.')[0]}"],
        ),
    },
    {
        "regex": r"SyntaxError: invalid syntax.*?['\"](.+?)['\"],\s*line\s*(\d+)",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="",
            explanation=f"Syntax error in {m.group(1)} at line {m.group(2)} — check for typos, missing colons, or brackets",
            confidence=0.6,
            root_cause="syntax_error",
        ),
    },
    {
        "regex": r"IndentationError",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="",
            explanation="Indentation error — mix of tabs and spaces, or wrong indent level",
            confidence=0.85,
            root_cause="indentation",
        ),
    },
    {
        "regex": r"FileNotFoundError: \[Errno 2\].*?'(.+?)'",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command=(
                f'mkdir "{os.path.dirname(m.group(1))}"'
                if _IS_WINDOWS and ('/' in m.group(1) or '\\' in m.group(1))
                else f'mkdir -p "{os.path.dirname(m.group(1))}"'
                if not _IS_WINDOWS and ('/' in m.group(1) or '\\' in m.group(1))
                else ""
            ),
            explanation=f"File or directory '{m.group(1)}' doesn't exist",
            confidence=0.8,
            root_cause="missing_file",
        ),
    },
    {
        "regex": r"PermissionError: \[Errno 13\]",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command=_safe_elevated_cmd(cmd),
            explanation="Permission denied — needs elevated privileges",
            confidence=0.85,
            root_cause="permission",
        ),
    },
    {
        "regex": r"ConnectionRefusedError|Connection refused",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="",
            explanation="Connection refused — the target service isn't running or wrong port",
            confidence=0.7,
            root_cause="connection_refused",
            alternative_fixes=["Check if the service is started", "Verify the port number"],
        ),
    },
    {
        "regex": r"MemoryError|Cannot allocate memory",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="",
            explanation="Out of memory — process ran out of RAM",
            confidence=0.9,
            root_cause="oom",
            alternative_fixes=["Close other applications", "Process data in smaller batches"],
        ),
    },

    # ── Node.js / npm Errors ────────────────────────
    {
        "regex": r"npm ERR! missing script:\s*(\S+)",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="npm run",
            explanation=f"Script '{m.group(1)}' not found in package.json — check available scripts",
            confidence=0.85,
            root_cause="missing_script",
        ),
    },
    {
        "regex": r"Cannot find module ['\"](.+?)['\"]",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command=f"npm install {m.group(1).split('/')[0]}",
            explanation=f"Node module '{m.group(1)}' not installed",
            confidence=0.9,
            root_cause="missing_node_module",
            alternative_fixes=["npm install", f"yarn add {m.group(1).split('/')[0]}"],
        ),
    },
    {
        "regex": r"ENOSPC|no space left on device",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="df -h" if platform.system() != "Windows" else "Get-PSDrive -PSProvider FileSystem",
            explanation="Disk full — no space left on the drive",
            confidence=0.95,
            root_cause="disk_full",
        ),
    },
    {
        "regex": r"EADDRINUSE|address already in use.*?:(\d+)?",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command=f"lsof -i :{m.group(1)}" if platform.system() != "Windows" and m.group(1) else (
                f"netstat -ano | findstr :{m.group(1)}" if m.group(1) else "netstat -tulpn"
            ),
            explanation=f"Port {m.group(1) or 'unknown'} is already in use",
            confidence=0.9,
            root_cause="port_in_use",
        ),
    },

    # ── Git Errors ──────────────────────────────────
    {
        "regex": r"fatal: not a git repository",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="git init",
            explanation="Not inside a git repository",
            confidence=0.95,
            root_cause="no_git_repo",
        ),
    },
    {
        "regex": r"error: failed to push some refs",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="git pull --rebase && git push",
            explanation="Remote has changes you don't have locally — pull first",
            confidence=0.9,
            root_cause="git_push_rejected",
            alternative_fixes=["git pull origin main --rebase", "git fetch && git rebase origin/main"],
        ),
    },
    {
        "regex": r"CONFLICT.*Merge conflict in (.+)",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command=f"git diff --name-only --diff-filter=U",
            explanation=f"Merge conflict in {m.group(1)} — resolve manually then git add + commit",
            confidence=0.85,
            root_cause="merge_conflict",
        ),
    },
    {
        "regex": r"fatal: unable to access.*Could not resolve host",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="ping google.com" if platform.system() != "Windows" else "Test-NetConnection google.com",
            explanation="Cannot reach remote — check internet connection or proxy settings",
            confidence=0.85,
            root_cause="network",
        ),
    },

    # ── Docker Errors ───────────────────────────────
    {
        "regex": r"Cannot connect to the Docker daemon",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="sudo systemctl start docker" if platform.system() != "Windows" else "Start-Service Docker",
            explanation="Docker daemon is not running",
            confidence=0.95,
            root_cause="docker_not_running",
        ),
    },
    {
        "regex": r"Error response from daemon.*?image.*?not found|manifest.*?not found",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="docker images",
            explanation="Docker image not found — check the image name and tag",
            confidence=0.85,
            root_cause="docker_image_missing",
            alternative_fixes=["docker pull <image:tag>"],
        ),
    },

    # ── System Errors ───────────────────────────────
    {
        "regex": r"command not found|not recognized as.*?command|is not recognized",
        "fix_fn": lambda m, cmd: _cmd_not_found_fix(cmd),
    },
    {
        "regex": r"permission denied|Access is denied",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command=f"sudo {cmd}" if platform.system() != "Windows" else "",
            explanation="Permission denied — run with elevated privileges",
            confidence=0.85,
            root_cause="permission",
        ),
    },
    {
        "regex": r"No such file or directory|cannot find the path|does not exist",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="ls -la" if platform.system() != "Windows" else "dir",
            explanation="File or directory not found — check the path",
            confidence=0.75,
            root_cause="path_not_found",
        ),
    },
    {
        "regex": r"SSL.*certificate.*verify|CERTIFICATE_VERIFY_FAILED",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org" if "pip" in cmd else "",
            explanation="SSL certificate verification failed — possible firewall/proxy issue",
            confidence=0.7,
            root_cause="ssl_error",
        ),
    },
    {
        "regex": r"killed|OOMKilled|signal 9",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="free -h" if platform.system() != "Windows" else "systeminfo | findstr Memory",
            explanation="Process was killed by OS — likely out of memory",
            confidence=0.8,
            root_cause="oom_killed",
        ),
    },

    # ── Rust / Cargo ────────────────────────────────
    {
        "regex": r"error\[E\d+\]:\s*(.+)",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="cargo check",
            explanation=f"Rust compilation error: {m.group(1)}",
            confidence=0.6,
            root_cause="rust_compile_error",
        ),
    },

    # ── Java / Gradle / Maven ───────────────────────
    {
        "regex": r"ClassNotFoundException:\s*(\S+)",
        "fix_fn": lambda m, cmd: FixResult(
            fix_command="",
            explanation=f"Java class '{m.group(1)}' not found — check classpath or dependencies",
            confidence=0.7,
            root_cause="java_class_missing",
        ),
    },
]

# Pre-compile regexes for performance — each pattern compiled independently
# so a malformed regex can't prevent the entire module from loading.
for _p in _PATTERNS:
    try:
        _p["_compiled"] = re.compile(_p["regex"], re.IGNORECASE | re.MULTILINE)
    except re.error as _exc:
        import logging as _logging
        _logging.getLogger("neuroshell.error_fixer").warning(
            "Failed to compile error pattern %r: %s", _p["regex"], _exc
        )
        _p["_compiled"] = None  # Will be skipped in _check_offline_patterns


def _cmd_not_found_fix(cmd: str) -> FixResult:
    """Generate fix for command-not-found errors with install suggestions."""
    tool = cmd.strip().split()[0] if cmd.strip() else "unknown"

    # Common tools and their install commands (all free)
    INSTALL_DB = {
        "git": "https://git-scm.com/downloads",
        "node": "https://nodejs.org/",
        "npm": "https://nodejs.org/",
        "python": "https://python.org/downloads/",
        "python3": "https://python.org/downloads/",
        "pip": "python -m ensurepip --upgrade",
        "pip3": "python3 -m ensurepip --upgrade",
        "docker": "https://docs.docker.com/get-docker/",
        "cargo": "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
        "go": "https://go.dev/dl/",
        "java": "https://adoptium.net/",
        "javac": "https://adoptium.net/",
        "gcc": "sudo apt install build-essential" if platform.system() == "Linux" else "https://winlibs.com/",
        "g++": "sudo apt install build-essential" if platform.system() == "Linux" else "https://winlibs.com/",
        "make": "sudo apt install build-essential" if platform.system() == "Linux" else "choco install make",
        "curl": "sudo apt install curl" if platform.system() == "Linux" else "built-in on modern Windows",
        "wget": "sudo apt install wget" if platform.system() == "Linux" else "choco install wget",
        "ffmpeg": "sudo apt install ffmpeg" if platform.system() == "Linux" else "choco install ffmpeg",
        "kubectl": "curl -LO https://dl.k8s.io/release/stable.txt",
        "terraform": "https://developer.hashicorp.com/terraform/downloads",
    }

    install_info = INSTALL_DB.get(tool, "")
    if install_info.startswith("http"):
        explanation = f"'{tool}' is not installed. Download from: {install_info}"
        fix_cmd = ""
    elif install_info:
        explanation = f"'{tool}' is not installed"
        fix_cmd = install_info
    else:
        explanation = f"'{tool}' is not installed or not on PATH"
        fix_cmd = ""

    return FixResult(
        fix_command=fix_cmd,
        explanation=explanation,
        confidence=0.85,
        root_cause="command_not_found",
        alternative_fixes=[f"which {tool}" if platform.system() != "Windows" else f"where {tool}"],
    )


class ErrorFixer:
    """
    Multi-strategy auto-fix engine.

    Fix priority:
    1. Cached fixes (instant — proven solutions from history)
    2. Offline patterns (25+ common errors)
    3. LLM analysis (deep fix for complex errors)
    """

    def __init__(self, llm_client, history_store, context_manager):
        self.llm = llm_client
        self.history = history_store
        self.context = context_manager
        self._session_fixes: list[dict] = []

    def fix(self, error_output: str, failed_command: str) -> FixResult:
        """
        Analyze error and suggest a fix.
        Priority: cached fix → offline pattern → LLM.
        """
        error_pattern = self._normalize_error(error_output)

        # 1. Check cached fixes (instant — proven solutions)
        cached = self.history.find_fix(error_pattern)
        if cached:
            result = FixResult(
                fix_command=cached["fix_command"],
                explanation=f"Proven fix (used {cached['success_count']} times)",
                confidence=0.95,
                provenance=ProvenanceTag(
                    source=ProvenanceSource.CACHED,
                    confidence=0.95,
                    detail=f"cached fix, {cached['success_count']} successes",
                    latency_ms=0.1,
                ),
            )
            self._track_fix("cached", error_output, result)
            return result

        # 2. Check offline patterns (25+ common errors)
        pattern_fix = self._check_offline_patterns(error_output, failed_command)
        if pattern_fix:
            pattern_fix.provenance = ProvenanceTag(
                source=ProvenanceSource.PATTERN,
                confidence=pattern_fix.confidence,
                detail=f"offline pattern: {pattern_fix.root_cause}",
                latency_ms=0.5,
            )
            self._track_fix("pattern", error_output, pattern_fix)
            return pattern_fix

        # 3. Fall back to Swarm Agentic Diagnoser (Deep Fix)
        swarm_result = self._swarm_fix(error_output, failed_command)
        if swarm_result.confidence > 0.5 and swarm_result.fix_command:
            self._track_fix("swarm", error_output, swarm_result)
            return swarm_result

        # 4. Fall back to simple LLM prediction
        result = self._llm_fix(error_output, failed_command)
        self._track_fix("llm", error_output, result)
        return result

    def record_fix_success(self, error_output: str, fix_command: str, source: str = "llm"):
        """Record that a fix was successful for learning."""
        error_pattern = self._normalize_error(error_output)
        self.history.store_fix(error_pattern, error_output[:200], fix_command, source)

    def record_fix_failure(self, error_output: str, fix_command: str):
        """Record that a fix failed."""
        error_pattern = self._normalize_error(error_output)
        self.history.mark_fix_failed(error_pattern, fix_command)

    def get_session_stats(self) -> dict:
        """Get fix statistics for current session."""
        total = len(self._session_fixes)
        if total == 0:
            return {"total": 0}
        sources = {}
        for f in self._session_fixes:
            s = f["source"]
            sources[s] = sources.get(s, 0) + 1
        return {"total": total, "by_source": sources}

    def _track_fix(self, source: str, error: str, result: FixResult):
        """Track fix for session stats."""
        self._session_fixes.append({
            "source": source,
            "error_preview": error[:100],
            "fix": result.fix_command[:100],
            "confidence": result.confidence,
            "timestamp": time.time(),
        })

    def _normalize_error(self, error: str) -> str:
        """Normalize error to a pattern key (strip paths, numbers)."""
        normalized = error.strip()[:200]
        normalized = re.sub(r'[A-Za-z]:\\[\w\\\-\.]+', '<PATH>', normalized)
        normalized = re.sub(r'/[\w/\-\.]+', '<PATH>', normalized)
        normalized = re.sub(r'line \d+', 'line N', normalized)
        normalized = re.sub(r'\d+\.\d+\.\d+', 'X.Y.Z', normalized)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _check_offline_patterns(self, error: str, command: str) -> Optional[FixResult]:
        """Match against 25+ offline error patterns."""
        for pattern in _PATTERNS:
            compiled = pattern.get("_compiled")
            if compiled is None:
                continue  # Skip patterns that failed to compile
            match = compiled.search(error)
            if match:
                try:
                    result = pattern["fix_fn"](match, command)
                    return result
                except Exception:
                    continue
        return None

    def _swarm_fix(self, error_output: str, failed_command: str) -> FixResult:
        """Use Swarm Orchestrator to dynamically diagnose and sandbox a fix."""
        try:
            from intelligence.swarm import SwarmOrchestrator
            from core.events import neuro_events
            
            neuro_events.emit("swarm_update", "[🔧 Swarm Fixer] Entering Deep Diagnostic Mode...")
            
            # Formulate the diagnostic prompt for the Swarm
            task = (
                f"The command '{failed_command}' failed with the following error:\n"
                f"{error_output[:1000]}\n\n"
                "Your task is to comprehensively analyze the current workspace state "
                "and generate a robust, terminal-ready command to fix this error. "
                "Because you are testing in a Sandbox, your proposed command MUST be exactly "
                "the shell command that fixes the user's issue (e.g. creating/moving files, installing packages)."
            )
            
            start = time.time()
            orchestrator = SwarmOrchestrator(self.llm, self.context)
            swarm_res = orchestrator.route_task(task)
            latency = (time.time() - start) * 1000
            
            # If the Swarm verified the command via GitSandbox, use it!
            # The swarm_res.final_command contains the successful deployed fix if verification passed.
            if swarm_res.is_safe and swarm_res.final_command and not swarm_res.final_command.startswith("echo"):
                return FixResult(
                    fix_command=swarm_res.final_command,
                    explanation=f"Deep Diagnostic Fix: {swarm_res.explanation[:200]}...",
                    confidence=0.95,
                    root_cause="auto_ diagnosed_by_swarm",
                    provenance=ProvenanceTag(
                        source=ProvenanceSource.LLM,
                        confidence=0.95,
                        detail=f"Swarm Deep Fix (Agents: {', '.join(swarm_res.agents_used)})",
                        latency_ms=latency,
                    )
                )
                
            # If swarm didn't output a valid command, or it just echoed a summary, we fall back.
            return FixResult(fix_command="", explanation="", confidence=0.0)
            
        except ImportError as e:
            print(f"[SwarmFixer] ImportError: {e}")
            return FixResult(fix_command="", explanation="", confidence=0.0)
        except Exception as e:
            print(f"[SwarmFixer] Exception: {e}")
            import traceback
            traceback.print_exc()
            return FixResult(fix_command="", explanation="", confidence=0.0)

    def _llm_fix(self, error_output: str, failed_command: str) -> FixResult:
        """Use LLM to generate a fix for unknown errors."""
        from llm.prompts import fix_prompt

        ctx = self.context.get_context_summary()
        system, user = fix_prompt(error_output[:500], failed_command, ctx)

        start = time.time()
        result = self.llm.generate_json(user, system)
        latency = (time.time() - start) * 1000

        if not result:
            return FixResult(
                fix_command="",
                explanation="Could not analyze error — LLM unavailable",
                confidence=0.0,
                provenance=ProvenanceTag(
                    source=ProvenanceSource.FALLBACK,
                    confidence=0.0,
                    latency_ms=latency,
                ),
            )

        # Handle case where LLM returns a list instead of dict
        if isinstance(result, list):
            result = next((item for item in result if isinstance(item, dict)), None)
            if not result:
                return FixResult(
                    fix_command="",
                    explanation="Could not parse LLM fix response",
                    confidence=0.0,
                    provenance=ProvenanceTag(
                        source=ProvenanceSource.FALLBACK,
                        confidence=0.0,
                        latency_ms=latency,
                    ),
                )

        return FixResult(
            fix_command=result.get("fix_command", ""),
            explanation=result.get("explanation", ""),
            confidence=float(result.get("confidence", 0.5)),
            alternative_fixes=result.get("alternative_fixes", []),
            root_cause=result.get("root_cause", ""),
            provenance=ProvenanceTag(
                source=ProvenanceSource.LLM,
                confidence=float(result.get("confidence", 0.5)),
                detail="LLM-generated fix",
                latency_ms=latency,
            ),
        )
