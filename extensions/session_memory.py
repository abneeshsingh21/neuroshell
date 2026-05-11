# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Session Memory + Command History Timeline
Tier 2: Persistent learning across sessions with similarity search.
"""

import json
import time
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger("neuroshell.memory")


@dataclass
class MemoryEntry:
    """Single command memory record."""
    input_text: str
    command: str
    success: bool
    timestamp: float
    duration_ms: float = 0
    context: str = ""  # cwd, git branch, project type
    frequency: int = 1
    tags: list[str] = field(default_factory=list)

    @property
    def entry_hash(self) -> str:
        return hashlib.md5(f"{self.input_text}:{self.command}".encode()).hexdigest()[:12]


class SessionMemory:
    """
    Production-grade session memory with cross-session persistence.
    
    Features:
    - SQLite-free (JSON file) for zero-dependency portability
    - Frequency-based suggestion ranking
    - Context-aware recall (cwd, project type)
    - Automatic deduplication
    - Configurable max history size
    """

    MAX_ENTRIES = 5000
    SIMILARITY_THRESHOLD = 0.6

    def __init__(self, memory_dir: Optional[Path] = None):
        self.memory_dir = memory_dir or Path.home() / ".neuroshell" / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self.memory_dir / "session_memory.json"
        self._entries: dict[str, MemoryEntry] = {}
        self._load()

    def _load(self):
        """Load memory from disk."""
        if self._db_path.exists():
            try:
                data = json.loads(self._db_path.read_text(encoding="utf-8"))
                for key, entry_data in data.items():
                    self._entries[key] = MemoryEntry(**entry_data)
                logger.info("Loaded %d memory entries", len(self._entries))
            except Exception as e:
                logger.warning("Memory load failed: %s", e)
                self._entries = {}

    def _save(self):
        """Persist memory to disk."""
        try:
            data = {k: asdict(v) for k, v in self._entries.items()}
            self._db_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Memory save failed: %s", e)

    def record(self, input_text: str, command: str, success: bool,
               duration_ms: float = 0, context: str = ""):
        """Record a command execution."""
        entry = MemoryEntry(
            input_text=input_text, command=command, success=success,
            timestamp=time.time(), duration_ms=duration_ms, context=context,
        )
        key = entry.entry_hash
        if key in self._entries:
            self._entries[key].frequency += 1
            self._entries[key].timestamp = time.time()
            self._entries[key].success = success
        else:
            self._entries[key] = entry

        # Evict oldest if over limit
        if len(self._entries) > self.MAX_ENTRIES:
            oldest = sorted(self._entries.items(), key=lambda x: x[1].timestamp)
            for k, _ in oldest[:len(self._entries) - self.MAX_ENTRIES]:
                del self._entries[k]

        self._save()

    def suggest(self, partial_input: str, context: str = "", limit: int = 5) -> list[MemoryEntry]:
        """Suggest commands based on partial input and context."""
        partial_lower = partial_input.lower().strip()
        if not partial_lower:
            return []

        scored: list[tuple[float, MemoryEntry]] = []
        for entry in self._entries.values():
            score = 0.0
            input_lower = entry.input_text.lower()

            # Exact prefix match
            if input_lower.startswith(partial_lower):
                score += 0.5
            # Substring match
            elif partial_lower in input_lower:
                score += 0.3
            # Word overlap
            else:
                words_input = set(partial_lower.split())
                words_entry = set(input_lower.split())
                overlap = len(words_input & words_entry) / max(len(words_input), 1)
                if overlap > 0.3:
                    score += overlap * 0.4

            if score <= 0:
                continue

            # Boost by frequency and recency
            score += min(entry.frequency * 0.05, 0.3)
            age_hours = (time.time() - entry.timestamp) / 3600
            if age_hours < 24:
                score += 0.1
            # Context match bonus
            if context and entry.context == context:
                score += 0.15
            # Success bonus
            if entry.success:
                score += 0.05

            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    def get_timeline(self, limit: int = 50) -> list[MemoryEntry]:
        """Get recent command history as a timeline."""
        entries = sorted(self._entries.values(), key=lambda e: e.timestamp, reverse=True)
        return entries[:limit]

    def get_frequent(self, limit: int = 20) -> list[MemoryEntry]:
        """Get most frequently used commands."""
        entries = sorted(self._entries.values(), key=lambda e: e.frequency, reverse=True)
        return entries[:limit]

    def get_stats(self) -> dict:
        """Get memory statistics."""
        total = len(self._entries)
        successes = sum(1 for e in self._entries.values() if e.success)
        return {
            "total_entries": total,
            "success_rate": f"{successes/max(total,1)*100:.1f}%",
            "unique_commands": len(set(e.command for e in self._entries.values())),
            "db_size_kb": round(self._db_path.stat().st_size / 1024, 1) if self._db_path.exists() else 0,
        }

    def clear(self):
        """Clear all memory."""
        self._entries.clear()
        self._save()
