# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Pattern Learner
Detects recurring command sequences, time patterns, and error-fix pairs.
"""

import time
from collections import Counter, defaultdict
from typing import Optional
from dataclasses import dataclass


@dataclass
class Pattern:
    """A detected usage pattern."""
    pattern_type: str  # sequence, time, error_fix, directory
    data: dict
    frequency: int
    confidence: float


class PatternLearner:
    """Learns user command patterns for prediction."""

    def __init__(self, history_store):
        self.history = history_store
        self._sequence_counts: Counter = Counter()
        self._dir_commands: defaultdict = defaultdict(Counter)
        self._time_commands: defaultdict = defaultdict(Counter)

    def learn_from_history(self):
        """Analyze history to find patterns."""
        recent = self.history.get_recent(500)
        if len(recent) < 5:
            return

        # Learn command sequences (bigrams)
        for i in range(len(recent) - 1):
            pair = (recent[i].command, recent[i + 1].command)
            self._sequence_counts[pair] += 1

        # Learn directory-specific patterns
        for record in recent:
            self._dir_commands[record.cwd][record.command] += 1

        # Learn time-based patterns
        for record in recent:
            hour = time.strftime("%H", time.localtime(record.timestamp))
            self._time_commands[hour][record.command] += 1

    def get_patterns(self, min_frequency: int = 3) -> list[Pattern]:
        """Get all detected patterns above threshold."""
        patterns = []

        # Sequence patterns
        for (cmd1, cmd2), count in self._sequence_counts.most_common(20):
            if count >= min_frequency:
                patterns.append(Pattern(
                    pattern_type="sequence",
                    data={"first": cmd1, "then": cmd2},
                    frequency=count,
                    confidence=min(0.9, count / 10),
                ))

        # Directory patterns
        for cwd, cmds in self._dir_commands.items():
            for cmd, count in cmds.most_common(5):
                if count >= min_frequency:
                    patterns.append(Pattern(
                        pattern_type="directory",
                        data={"cwd": cwd, "command": cmd},
                        frequency=count,
                        confidence=min(0.8, count / 10),
                    ))

        return patterns

    def predict_next(self, last_command: str, cwd: str = "") -> Optional[str]:
        """Predict the most likely next command."""
        best_cmd = None
        best_score = 0

        for (cmd1, cmd2), count in self._sequence_counts.items():
            if cmd1 == last_command and count > best_score:
                best_cmd = cmd2
                best_score = count

        return best_cmd if best_score >= 2 else None
