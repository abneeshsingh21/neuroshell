# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Session Memory Manager

Tracks the immediate rolling context for a conversation session.
Automatically compresses or discards oldest turns to maintain token limits.
"""

import json
import time
from typing import Any, Dict, List


class SessionMemory:
    def __init__(self, max_turns: int = 15):
        self.max_turns = max_turns
        self.turns: List[Dict[str, Any]] = []
        self.last_activity = time.time()

    def add_turn(self, role: str, content: str, metadata: dict = None):
        self.turns.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "metadata": metadata or {}
        })
        self.last_activity = time.time()
        self._enforce_limits()

    def _enforce_limits(self):
        """Discards older turns if exceeding limit.
        These discarded turns are exactly what AutoDream will process and consolidate!
        """
        if len(self.turns) > self.max_turns:
            discarded = self.turns[:-self.max_turns]
            self.turns = self.turns[-self.max_turns:]
            self._save_discarded_for_dreaming(discarded)

    def _save_discarded_for_dreaming(self, discarded_turns: List[Dict]):
        """Append discarded turns to a log file for AutoDream to process."""
        import os
        from pathlib import Path
        os.makedirs(str(Path.home() / ".neuroshell" / "memory"), exist_ok=True)
        # We append to a specific file that the daemon reads
        try:
            with open(str(Path.home() / ".neuroshell" / "memory" / "dream_queue.jsonl"), "a", encoding="utf-8") as f:
                for t in discarded_turns:
                    f.write(json.dumps(t) + "\n")
        except Exception:
            pass

    def get_context(self) -> List[Dict[str, Any]]:
        self.last_activity = time.time()
        return self.turns

    def get_idle_time(self) -> float:
        return time.time() - self.last_activity
