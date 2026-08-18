# NeuroShell NLP Fast-Dictionary Engine
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Offline English→Shell translation without any LLM.

"""
Provides instant offline translation of 1000+ common English
terminal phrases to shell commands using TF-IDF vector matching.
Zero internet. Zero API calls. Maximum privacy.
"""

from __future__ import annotations

import math
import platform
import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_IS_WIN = platform.system() == "Windows"


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _resolve_platform_cmd(entry: tuple) -> tuple[str, str]:
    """Resolve (english, cmd) for current OS from 3-tuple or 4-tuple entry."""
    eng = entry[0]
    sys_name = platform.system()
    if sys_name == "Windows":
        cmd = entry[1]
    elif sys_name == "Darwin":
        if len(entry) >= 4:
            cmd = entry[3]
        else:
            # Smart macOS dynamic fallback
            cmd = entry[2]
            if cmd == "free -m": cmd = "vm_stat"
            elif "xclip" in cmd: cmd = cmd.replace("xclip -sel clip -o", "pbpaste").replace("| xclip -sel clip", "| pbcopy")
            elif "ip a" in cmd: cmd = "ifconfig"
    else:  # Linux / FreeBSD
        cmd = entry[2]
    return eng, cmd


class PhraseDictionary:
    """Fast offline English→Shell translator using TF-IDF cosine similarity."""

    def __init__(self):
        self._phrases: list[tuple] = []
        self._vocab: dict[str, int] = {}
        self._vectors: list[list[float]] = []
        self._built = False

    def load(self):
        """Load all phrase data and build the index."""
        from intelligence._phrase_data import PHRASES
        self._phrases = PHRASES
        self._build_index()

    def _build_index(self):
        vocab_set: set[str] = set()
        tokenized: list[list[str]] = []
        for entry in self._phrases:
            toks = _tokenize(entry[0])
            tokenized.append(toks)
            vocab_set.update(toks)

        self._vocab = {w: i for i, w in enumerate(sorted(vocab_set))}
        dim = len(self._vocab)

        # IDF weights
        doc_count = len(tokenized)
        df = [0] * dim
        for toks in tokenized:
            seen = set()
            for t in toks:
                idx = self._vocab.get(t)
                if idx is not None and idx not in seen:
                    df[idx] += 1
                    seen.add(idx)
        idf = [math.log((doc_count + 1) / (d + 1)) + 1.0 for d in df]

        # Build TF-IDF vectors
        self._vectors = []
        for toks in tokenized:
            vec = [0.0] * dim
            for t in toks:
                idx = self._vocab.get(t)
                if idx is not None:
                    vec[idx] += 1.0
            # Apply IDF
            for i in range(dim):
                vec[i] *= idf[i]
            # L2 normalize
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            self._vectors.append(vec)

        self._built = True

    def translate(self, query: str, threshold: float = 0.35) -> dict | None:
        """
        Translate English phrase to shell command.
        Returns dict with keys: command, english, confidence, or None.
        """
        if not self._built:
            self.load()

        toks = _tokenize(query)
        if not toks:
            return None

        dim = len(self._vocab)
        qvec = [0.0] * dim
        for t in toks:
            idx = self._vocab.get(t)
            if idx is not None:
                qvec[idx] += 1.0

        norm = math.sqrt(sum(v * v for v in qvec))
        if norm == 0:
            return None
        qvec = [v / norm for v in qvec]

        best_score = 0.0
        best_idx = -1
        for i, pvec in enumerate(self._vectors):
            score = sum(a * b for a, b in zip(qvec, pvec))
            if score > best_score:
                best_score = score
                best_idx = i

        if best_score < threshold or best_idx < 0:
            return None

        eng, cmd = _resolve_platform_cmd(self._phrases[best_idx])
        return {
            "command": cmd,
            "english": eng,
            "confidence": round(best_score, 3),
            "source": "offline-dictionary",
        }

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Return top-N matches above threshold."""
        if not self._built:
            self.load()

        toks = _tokenize(query)
        if not toks:
            return []

        dim = len(self._vocab)
        qvec = [0.0] * dim
        for t in toks:
            idx = self._vocab.get(t)
            if idx is not None:
                qvec[idx] += 1.0

        norm = math.sqrt(sum(v * v for v in qvec))
        if norm == 0:
            return []
        qvec = [v / norm for v in qvec]

        scored = []
        for i, pvec in enumerate(self._vectors):
            score = sum(a * b for a, b in zip(qvec, pvec))
            if score > 0.2:
                scored.append((i, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in scored[:limit]:
            eng, cmd = _resolve_platform_cmd(self._phrases[idx])
            results.append({
                "command": cmd,
                "english": eng,
                "confidence": round(score, 3),
            })
        return results

    @property
    def count(self) -> int:
        return len(self._phrases)
