"""
NeuroShell Recursive Learning Engine.
Analyzes executed command failures (stdout, stderr, exit code, WAF rate-limits, network filters),
synthesizes corrected delta commands with 1-key auto-fix, and consolidates successful outcomes
into SQLite WAL memory (AutoDream) for sub-0.1ms repeat query recall.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class FailureCategory(str, Enum):
    NETWORK_FILTERED = "network_filtered"
    WAF_RATE_LIMIT = "waf_rate_limit"
    SYNTAX_COLLISION = "syntax_collision"
    AUTHENTICATION_DENIED = "authentication_denied"
    PORT_TIMEOUT = "port_timeout"
    TOOL_NOT_FOUND = "tool_not_found"
    GIT_CONFLICT = "git_conflict"
    COMPILATION_ERROR = "compilation_error"
    GENERIC_FAILURE = "generic_failure"


@dataclass
class CorrectionDelta:
    original_command: str
    suggested_command: str
    failure_category: FailureCategory
    explanation: str
    confidence: float
    diff_summary: str = ""
    requires_elevation: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class RecursiveLearner:
    """
    Autonomous self-correction and recursive learning loop for terminal execution.
    Monitors process streams, diagnoses failures, computes delta fixes,
    and consolidates successful patterns into permanent local memory.
    """

    def __init__(self, db_path: Optional[Path | str] = None):
        if db_path is None:
            mem_dir = Path.home() / ".neuroshell" / "memory"
            mem_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = mem_dir / "learned_patterns.db"
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    @contextmanager
    def _connection(self):
        """Context manager guaranteeing connection closure to avoid Windows file locks."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize SQLite WAL database for learned patterns."""
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS learned_patterns (
                    pattern_id TEXT PRIMARY KEY,
                    intent_or_signature TEXT NOT NULL,
                    original_command TEXT NOT NULL,
                    success_command TEXT NOT NULL,
                    category TEXT NOT NULL,
                    success_count INTEGER NOT NULL DEFAULT 1,
                    last_used REAL NOT NULL
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pattern_sig ON learned_patterns(intent_or_signature);
            """)
            conn.commit()

    @staticmethod
    def _compute_signature(text: str) -> str:
        """Normalize intent or command into a deterministic signature hash."""
        clean = re.sub(r"\s+", " ", text.strip().lower())
        # Replace specific IP addresses with placeholder for generalized pattern recall
        clean = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<IP>", clean)
        return hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]

    def get_cached_fix(self, intent_or_command: str) -> Optional[str]:
        """
        Check if an identical failure or intent has previously been resolved and consolidated.
        Returns the cached successful command in sub-0.1ms.
        """
        sig = self._compute_signature(intent_or_command)
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT success_command FROM learned_patterns
                WHERE intent_or_signature = ?
                ORDER BY success_count DESC, last_used DESC
                LIMIT 1;
            """, (sig,))
            row = cursor.fetchone()
            if row:
                return row[0]
        return None

    def consolidate_success(
        self,
        intent_or_command: str,
        original_command: str,
        final_command: str,
        category: str = "general",
    ) -> None:
        """
        Consolidate a successful execution outcome into permanent memory (AutoDream).
        Reinforces patterns that user executed or approved.
        """
        sig = self._compute_signature(intent_or_command)
        pattern_id = f"pat_{sig}_{int(time.time())}"
        now = time.time()

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT pattern_id, success_count FROM learned_patterns
                WHERE intent_or_signature = ? AND success_command = ?;
            """, (sig, final_command))
            row = cursor.fetchone()
            if row:
                pid, cnt = row
                cursor.execute("""
                    UPDATE learned_patterns
                    SET success_count = ?, last_used = ?
                    WHERE pattern_id = ?;
                """, (cnt + 1, now, pid))
            else:
                cursor.execute("""
                    INSERT INTO learned_patterns
                    (pattern_id, intent_or_signature, original_command, success_command, category, success_count, last_used)
                    VALUES (?, ?, ?, ?, ?, 1, ?);
                """, (pattern_id, sig, original_command, final_command, category, now))
            conn.commit()

    def analyze_result(
        self,
        command: str,
        returncode: int,
        stdout: str,
        stderr: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[CorrectionDelta]:
        """
        Inspect command execution result. If non-zero exit code or soft failure detected,
        synthesize a corrected delta command with structured explanation.
        """
        # If exit code 0 and no soft error signatures, no correction needed
        combined_output = f"{stdout}\n{stderr}"

        # 1. First check if a cached consolidated fix exists
        cached = self.get_cached_fix(command)
        if cached and cached != command and returncode != 0:
            return CorrectionDelta(
                original_command=command,
                suggested_command=cached,
                failure_category=FailureCategory.GENERIC_FAILURE,
                explanation="Applied previously consolidated successful command from AutoDream memory.",
                confidence=0.98,
                diff_summary=self._generate_diff(command, cached),
            )

        # 2. Heuristic Pattern Diagnostics

        # Diagnostic A: Nmap Ping Probe Blocked (-Pn)
        if "nmap" in command.lower() and (
            "host seems down" in combined_output.lower()
            or "blocking our ping probes, try -pn" in combined_output.lower()
            or "note: host seems down" in combined_output.lower()
        ):
            if "-Pn" not in command and "-pn" not in command:
                suggested = self._inject_flag(command, "-Pn")
                return CorrectionDelta(
                    original_command=command,
                    suggested_command=suggested,
                    failure_category=FailureCategory.NETWORK_FILTERED,
                    explanation="Target firewall is dropping ICMP ping probes. Added -Pn to skip host discovery.",
                    confidence=0.95,
                    diff_summary=self._generate_diff(command, suggested),
                )

        # Diagnostic B: Web Fuzzing WAF / Rate Limiting (429 Too Many Requests / 403 Forbidden)
        if any(tool in command.lower() for tool in ("gobuster", "ffuf", "wfuzz", "curl")):
            if "429" in combined_output or "too many requests" in combined_output.lower():
                suggested = command
                if "gobuster" in suggested:
                    suggested = self._inject_flag(suggested, "--delay 200ms -t 5")
                elif "ffuf" in suggested:
                    suggested = self._inject_flag(suggested, "-rate 10 -p 0.2")
                return CorrectionDelta(
                    original_command=command,
                    suggested_command=suggested,
                    failure_category=FailureCategory.WAF_RATE_LIMIT,
                    explanation="Target WAF is rate-limiting probes (HTTP 429). Throttled concurrency and added request delay.",
                    confidence=0.92,
                    diff_summary=self._generate_diff(command, suggested),
                )

        # Diagnostic C: Permission Denied / Requires Root
        if (
            "permission denied" in combined_output.lower()
            or "must be root" in combined_output.lower()
            or "operation not permitted" in combined_output.lower()
            or "requires administrative privileges" in combined_output.lower()
        ):
            if not command.strip().startswith("sudo "):
                suggested = f"sudo {command.strip()}"
                return CorrectionDelta(
                    original_command=command,
                    suggested_command=suggested,
                    failure_category=FailureCategory.AUTHENTICATION_DENIED,
                    explanation="Command requires elevated root/administrator privileges. Injected sudo prefix.",
                    confidence=0.90,
                    requires_elevation=True,
                    diff_summary=self._generate_diff(command, suggested),
                )

        # Diagnostic D: Git Push Rejected / Fetch First
        if "git push" in command.lower() and (
            "fetch first" in combined_output.lower()
            or "non-fast-forward" in combined_output.lower()
            or "failed to push some refs" in combined_output.lower()
        ):
            suggested = "git pull --rebase && " + command
            return CorrectionDelta(
                original_command=command,
                suggested_command=suggested,
                failure_category=FailureCategory.GIT_CONFLICT,
                explanation="Remote repository contains commits not in local branch. Added git pull --rebase before push.",
                confidence=0.88,
                diff_summary=self._generate_diff(command, suggested),
            )

        # Diagnostic E: Git Detached HEAD Warning
        if "you are in 'detached head' state" in combined_output.lower():
            suggested = "git switch -c recovery-branch"
            return CorrectionDelta(
                original_command=command,
                suggested_command=suggested,
                failure_category=FailureCategory.GIT_CONFLICT,
                explanation="Repository is currently in detached HEAD state. Suggested creating a recovery branch.",
                confidence=0.85,
                diff_summary=self._generate_diff(command, suggested),
            )

        # Diagnostic F: C++ Compiler Missing C++20 Flag
        if any(cc in command for cc in ("g++", "clang++")) and (
            "requires c++20" in combined_output.lower()
            or "std::ranges" in combined_output.lower()
            or "concepts" in combined_output.lower()
        ):
            if "-std=c++20" not in command:
                suggested = self._inject_flag(command, "-std=c++20")
                return CorrectionDelta(
                    original_command=command,
                    suggested_command=suggested,
                    failure_category=FailureCategory.COMPILATION_ERROR,
                    explanation="Code utilizes modern C++20 features. Injected -std=c++20 compiler dialect flag.",
                    confidence=0.94,
                    diff_summary=self._generate_diff(command, suggested),
                )

        # Diagnostic G: Missing Python Module
        m_mod = re.search(r"ModuleNotFoundError:\s+No module named ['\"]([^'\"]+)['\"]", combined_output)
        if m_mod:
            missing_pkg = m_mod.group(1)
            suggested = f"pip install {missing_pkg} && {command}"
            return CorrectionDelta(
                original_command=command,
                suggested_command=suggested,
                failure_category=FailureCategory.TOOL_NOT_FOUND,
                explanation=f"Missing Python package '{missing_pkg}'. Prepend pip install before re-executing.",
                confidence=0.89,
                diff_summary=self._generate_diff(command, suggested),
            )

        # Diagnostic H: Unrecognized Option / Did you mean
        m_opt = re.search(r"(?:unrecognized option|unknown option|invalid option)\s+['\"]?(--?[\w\-]+)['\"]?", combined_output, re.IGNORECASE)
        m_dym = re.search(r"Did you mean\s+['\"]?(--?[\w\-]+)['\"]?", combined_output, re.IGNORECASE)
        if m_opt and m_dym:
            bad_flag = m_opt.group(1)
            good_flag = m_dym.group(1)
            suggested = command.replace(bad_flag, good_flag)
            return CorrectionDelta(
                original_command=command,
                suggested_command=suggested,
                failure_category=FailureCategory.SYNTAX_COLLISION,
                explanation=f"Flag '{bad_flag}' unrecognized by tool. Replaced with closest valid flag '{good_flag}'.",
                confidence=0.96,
                diff_summary=self._generate_diff(command, suggested),
            )

        # If returncode is non-zero but no specific heuristic matched
        if returncode != 0:
            return None

        return None

    @staticmethod
    def _inject_flag(command: str, flag: str) -> str:
        """Inject a flag right after the main binary name in command string."""
        parts = command.strip().split(None, 1)
        if len(parts) == 1:
            return f"{parts[0]} {flag}"
        return f"{parts[0]} {flag} {parts[1]}"

    @staticmethod
    def _generate_diff(orig: str, sugg: str) -> str:
        """Generate a compact ANSI colored diff representation."""
        differ = difflib.ndiff([orig], [sugg])
        diff_lines = []
        for line in differ:
            if line.startswith("- "):
                diff_lines.append(f"\033[38;2;248;113;113m- {line[2:]}\033[0m")
            elif line.startswith("+ "):
                diff_lines.append(f"\033[38;2;74;222;128m+ {line[2:]}\033[0m")
        return "\n".join(diff_lines) if diff_lines else f"\033[38;2;74;222;128m➜ {sugg}\033[0m"

    @classmethod
    def format_correction_card(cls, delta: CorrectionDelta) -> str:
        """Render high-visibility ANSI card prompting user with 1-key auto-fix."""
        category_labels = {
            FailureCategory.NETWORK_FILTERED: "🛡️ Firewall / Ping Filter Detected",
            FailureCategory.WAF_RATE_LIMIT: "⚠️ WAF Rate-Limit / Blocking Detected",
            FailureCategory.AUTHENTICATION_DENIED: "🔒 Root / Elevation Required",
            FailureCategory.SYNTAX_COLLISION: "⚙️ Command Syntax Collision",
            FailureCategory.GIT_CONFLICT: "🌿 Git Repository Conflict",
            FailureCategory.COMPILATION_ERROR: "🛠️ Compiler Configuration Error",
            FailureCategory.TOOL_NOT_FOUND: "📦 Missing Utility / Dependency",
            FailureCategory.GENERIC_FAILURE: "🧠 AutoDream Self-Correction",
        }

        cat_title = category_labels.get(delta.failure_category, "🧠 Auto-Correction")
        pct = int(delta.confidence * 100)

        lines = [
            f"\033[38;2;251;191;36m╭── {cat_title} ({pct}% confidence) ───────────────────────╮\033[0m",
            f"\033[38;2;251;191;36m│\033[0m \033[1mDiagnosis:\033[0m   {delta.explanation}",
            f"\033[38;2;251;191;36m│\033[0m \033[1mOriginal:\033[0m    \033[38;2;248;113;113m{delta.original_command}\033[0m",
            f"\033[38;2;251;191;36m│\033[0m \033[1mCorrected:\033[0m   \033[1m\033[38;2;74;222;128m{delta.suggested_command}\033[0m",
            f"\033[38;2;251;191;36m├─────────────────────────────────────────────────────────────────────────────┤\033[0m",
            f"\033[38;2;251;191;36m│\033[0m Press \033[1m\033[38;2;74;222;128m[y]\033[0m to run corrected command, or press \033[1m\033[38;2;248;113;113m[n]\033[0m to cancel",
            f"\033[38;2;251;191;36m╰─────────────────────────────────────────────────────────────────────────────╯\033[0m",
        ]
        return "\n".join(lines)
