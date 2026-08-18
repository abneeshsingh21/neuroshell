# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell C++ Performance Engine
Pure Python fallback for fast_parser, fuzzy_matcher, and command tokenizer.
Designed to be replaced with pybind11 C++ bindings for production.
"""

import re
from typing import Optional
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════
# Fast Command Parser (Python reference — replace with C++)
# ═══════════════════════════════════════════════════════════

@dataclass
class ParsedCommand:
    """Parsed command structure."""
    program: str = ""
    arguments: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    pipes: list[str] = field(default_factory=list)
    redirects: list[dict] = field(default_factory=list)
    is_compound: bool = False
    is_background: bool = False
    subcommands: list[str] = field(default_factory=list)


class FastParser:
    """
    Fast command parser — pure Python reference implementation.
    
    In production, this would be a pybind11 wrapper around a C++ parser
    for sub-microsecond parsing. The Python version handles all functionality
    for development and testing.
    """

    CONNECTORS = {"&&", "||", ";", "|", "&"}

    def parse(self, command: str) -> ParsedCommand:
        """Parse a shell command into structured components."""
        command = command.strip()
        result = ParsedCommand()

        if not command:
            return result

        # Check for pipes
        if "|" in command and "||" not in command:
            result.pipes = [p.strip() for p in command.split("|")]
            result.is_compound = True
            # Parse the first command
            self._parse_single(result.pipes[0], result)
            return result

        # Check for compound commands
        for conn in ("&&", "||", ";"):
            if conn in command:
                result.subcommands = [s.strip() for s in command.split(conn)]
                result.is_compound = True
                self._parse_single(result.subcommands[0], result)
                return result

        # Single command
        self._parse_single(command, result)
        return result

    def _parse_single(self, command: str, result: ParsedCommand):
        """Parse a single (non-compound) command."""
        # Check for background
        if command.endswith("&") and not command.endswith("&&"):
            command = command[:-1].strip()
            result.is_background = True

        # Check for redirects
        redirects, command = self._extract_redirects(command)
        result.redirects = redirects

        # Tokenize
        tokens = self._tokenize(command)
        if not tokens:
            return

        result.program = tokens[0]

        for token in tokens[1:]:
            if token.startswith("-"):
                result.flags.append(token)
            else:
                result.arguments.append(token)

    def _tokenize(self, command: str) -> list[str]:
        """Tokenize command respecting quotes."""
        tokens = []
        current = []
        in_single_quote = False
        in_double_quote = False
        escape_next = False

        for char in command:
            if escape_next:
                current.append(char)
                escape_next = False
            elif char == "\\":
                escape_next = True
            elif char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == " " and not in_single_quote and not in_double_quote:
                if current:
                    tokens.append("".join(current))
                    current = []
            else:
                current.append(char)

        if current:
            tokens.append("".join(current))

        return tokens

    tokenize = _tokenize

    def _extract_redirects(self, command: str) -> tuple[list[dict], str]:
        """Extract redirect operators from command taking quotes into account."""
        tokens = self._tokenize(command)
        redirects = []
        clean_tokens = []
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            # Standalone redirect token (e.g. > file.txt or >> log.txt)
            match = re.match(r'^(2?)(>>?|<)$', tok)
            if match:
                fd = match.group(1) or "1"
                op = match.group(2)
                if i + 1 < len(tokens):
                    target = tokens[i + 1]
                    redirects.append({
                        "fd": int(fd) if fd.isdigit() else 1,
                        "mode": "append" if ">>" in op else ("read" if "<" in op else "write"),
                        "target": target,
                    })
                    i += 2
                    continue
            # Combined redirect token (e.g. >file.txt or 2>err.log)
            comb = re.match(r'^(2?)(>>?|<)(\S+)$', tok)
            if comb and not (tok.startswith("'") or tok.startswith('"')):
                fd = comb.group(1) or "1"
                op = comb.group(2)
                target = comb.group(3)
                redirects.append({
                    "fd": int(fd) if fd.isdigit() else 1,
                    "mode": "append" if ">>" in op else ("read" if "<" in op else "write"),
                    "target": target,
                })
                i += 1
                continue
            clean_tokens.append(tok)
            i += 1

        return redirects, " ".join(clean_tokens)


# ═══════════════════════════════════════════════════════════
# Fuzzy Matcher (Levenshtein + prefix matching)
# ═══════════════════════════════════════════════════════════

class FuzzyMatcher:
    """
    Levenshtein distance + prefix fuzzy matching.
    
    In production, this would use a C++ implementation for
    sub-millisecond matching across thousands of candidates.
    """

    def __init__(self, candidates: list[str] = None):
        self._candidates = candidates or []

    def set_candidates(self, candidates: list[str]):
        """Set the candidate list for matching."""
        self._candidates = candidates

    def match(self, query: str, max_distance: int = 3, limit: int = 5) -> list[tuple[str, int]]:
        """
        Find closest matches to query.
        
        Returns: [(candidate, distance), ...] sorted by distance.
        """
        if not query or not self._candidates:
            return []

        scored = []
        query_lower = query.lower()

        for candidate in self._candidates:
            cand_lower = candidate.lower()

            # Exact prefix match gets distance 0
            if cand_lower.startswith(query_lower):
                scored.append((candidate, 0))
                continue

            # Contains match gets distance 1
            if query_lower in cand_lower:
                scored.append((candidate, 1))
                continue

            # Levenshtein distance
            dist = self._levenshtein(query_lower, cand_lower)
            if dist <= max_distance:
                scored.append((candidate, dist))

        scored.sort(key=lambda x: x[1])
        return scored[:limit]

    def best_match(self, query: str, max_distance: int = 3) -> Optional[str]:
        """Get single best match."""
        matches = self.match(query, max_distance, limit=1)
        return matches[0][0] if matches else None

    def did_you_mean(self, query: str) -> Optional[str]:
        """Suggest correction for typos."""
        matches = self.match(query, max_distance=2, limit=1)
        if matches and matches[0][1] > 0:
            return matches[0][0]
        return None

    @staticmethod
    def _levenshtein(s1: str, s2: str) -> int:
        """Compute Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return FuzzyMatcher._levenshtein(s2, s1)

        if len(s2) == 0:
            return len(s1)

        prev_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            curr_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = prev_row[j + 1] + 1
                deletions = curr_row[j] + 1
                substitutions = prev_row[j] + (c1 != c2)
                curr_row.append(min(insertions, deletions, substitutions))
            prev_row = curr_row

        return prev_row[-1]


# ═══════════════════════════════════════════════════════════
# Markov Engine (Fast transition lookup)
# ═══════════════════════════════════════════════════════════

class MarkovEngine:
    """
    Fast Markov chain engine for command prediction.
    
    In production, backed by C++ hash maps for O(1) lookup
    across tens of thousands of transitions.
    """

    def __init__(self):
        self._transitions: dict[str, dict[str, int]] = {}
        self._totals: dict[str, int] = {}

    def train(self, sequences: list[list[str]]):
        """Train from sequences of commands."""
        for seq in sequences:
            for i in range(len(seq) - 1):
                current = seq[i]
                next_cmd = seq[i + 1]

                if current not in self._transitions:
                    self._transitions[current] = {}
                    self._totals[current] = 0

                self._transitions[current][next_cmd] = \
                    self._transitions[current].get(next_cmd, 0) + 1
                self._totals[current] += 1

    def predict(self, current: str, top_k: int = 3) -> list[tuple[str, float]]:
        """Predict next commands with probabilities."""
        if current not in self._transitions:
            return []

        total = self._totals[current]
        predictions = [
            (cmd, round(count / total, 3))
            for cmd, count in sorted(
                self._transitions[current].items(),
                key=lambda x: x[1],
                reverse=True,
            )[:top_k]
        ]
        return predictions

    @property
    def stats(self) -> dict:
        return {
            "states": len(self._transitions),
            "transitions": sum(len(v) for v in self._transitions.values()),
        }
