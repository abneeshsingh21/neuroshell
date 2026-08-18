# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Fuzzy Command Corrector
Levenshtein-based typo detection for 100+ common shell commands.
Suggests corrections like: "gti" → "git", "pythno" → "python"
"""

from dataclasses import dataclass


@dataclass
class CorrectionResult:
    """Result of a fuzzy correction attempt."""
    original: str
    corrected: str
    distance: int
    confidence: float
    is_correction: bool = True


# ═══════════════════════════════════════════════════════════
# Common commands database (120+ commands)
# ═══════════════════════════════════════════════════════════

COMMON_COMMANDS = [
    # Core shell
    "ls", "cd", "pwd", "mkdir", "rmdir", "rm", "cp", "mv", "cat", "echo",
    "touch", "head", "tail", "less", "more", "find", "grep", "sed", "awk",
    "sort", "uniq", "wc", "cut", "paste", "tr", "tee", "xargs", "which",
    "whereis", "whoami", "hostname", "uname", "date", "cal", "uptime",
    "clear", "history", "alias", "export", "source", "env", "printenv",
    # File ops
    "chmod", "chown", "chgrp", "ln", "stat", "diff", "file", "tar", "gzip",
    "gunzip", "zip", "unzip", "bzip2", "xz",
    # Network
    "ping", "curl", "wget", "ssh", "scp", "rsync", "netstat", "ifconfig",
    "ip", "nslookup", "dig", "traceroute", "telnet",
    # Process
    "ps", "top", "htop", "kill", "killall", "pkill", "bg", "fg", "jobs",
    "nohup", "nice", "renice",
    # Package managers
    "apt", "yum", "dnf", "brew", "pacman", "pip", "pip3", "npm", "npx",
    "yarn", "pnpm", "cargo", "gem", "composer",
    # Dev tools
    "git", "docker", "python", "python3", "node", "java", "javac", "gcc",
    "g++", "make", "cmake", "rustc", "go", "ruby", "perl",
    # Python tools
    "pytest", "flask", "django", "uvicorn", "gunicorn", "black", "pylint",
    "mypy", "ruff", "isort",
    # Node tools
    "next", "vite", "webpack", "eslint", "prettier", "tsc", "tsx",
    # System
    "systemctl", "service", "journalctl", "dmesg", "mount", "umount",
    "fdisk", "df", "du", "free", "lsblk", "lsof",
    # Windows
    "dir", "type", "copy", "move", "del", "ren", "cls", "ipconfig",
    "tasklist", "taskkill", "netsh", "powershell", "cmd",
]


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Damerau-Levenshtein distance (handles transpositions)."""
    len1, len2 = len(s1), len(s2)
    d = [[0] * (len2 + 1) for _ in range(len1 + 1)]

    for i in range(len1 + 1):
        d[i][0] = i
    for j in range(len2 + 1):
        d[0][j] = j

    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,       # deletion
                d[i][j - 1] + 1,       # insertion
                d[i - 1][j - 1] + cost  # substitution
            )
            # Transposition
            if i > 1 and j > 1 and s1[i - 1] == s2[j - 2] and s1[i - 2] == s2[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + cost)

    return d[len1][len2]


class FuzzyCorrector:
    """Fuzzy command corrector using Damerau-Levenshtein distance."""

    def __init__(self, extra_commands: list = None):
        self.commands = set(COMMON_COMMANDS)
        if extra_commands:
            self.commands.update(extra_commands)
        self._max_distance = 2  # Max typo distance to consider

    def correct(self, input_cmd: str) -> CorrectionResult | None:
        """
        Check if first word of input is a typo and suggest correction.
        Returns None if the command looks correct.
        """
        parts = input_cmd.strip().split()
        if not parts:
            return None

        first_word = parts[0].lower()

        # Already a known command — no correction needed
        if first_word in self.commands:
            return None

        # Find closest match with tie-breaking by length similarity
        best_match = None
        best_distance = float('inf')
        best_len_diff = float('inf')

        for cmd in self.commands:
            # Skip if length difference is too large
            if abs(len(cmd) - len(first_word)) > self._max_distance:
                continue

            dist = _levenshtein(first_word, cmd)
            len_diff = abs(len(cmd) - len(first_word))

            if dist <= self._max_distance:
                # Prefer lower distance, then closer length, then longer commands
                if (dist < best_distance or
                    (dist == best_distance and len_diff < best_len_diff) or
                    (dist == best_distance and len_diff == best_len_diff
                     and len(cmd) > len(best_match or ""))):
                    best_distance = dist
                    best_match = cmd
                    best_len_diff = len_diff

        if best_match and best_distance > 0:
            # Rebuild the full command with corrected first word
            corrected_parts = [best_match] + parts[1:]
            corrected_full = " ".join(corrected_parts)
            confidence = max(0.5, 1.0 - (best_distance * 0.25))

            return CorrectionResult(
                original=input_cmd,
                corrected=corrected_full,
                distance=best_distance,
                confidence=confidence,
            )

        return None

    def add_command(self, command: str):
        """Add a custom command to the known commands set."""
        self.commands.add(command.lower())
