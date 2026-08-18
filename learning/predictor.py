# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Predictor
Markov chain next-command prediction for ghost-text suggestions.
"""

from collections import defaultdict


class Predictor:
    """Markov chain predictor for next-command suggestions."""

    def __init__(self, history_store):
        self.history = history_store
        self._transitions: defaultdict = defaultdict(lambda: defaultdict(int))
        self._total: defaultdict = defaultdict(int)
        self._trained = False

    def train(self):
        """Build Markov chain from command history in chronological order."""
        recent = self.history.get_recent(1000)
        if len(recent) < 2:
            return

        ts0 = getattr(recent[0], "timestamp", None)
        ts1 = getattr(recent[-1], "timestamp", None)
        if isinstance(ts0, (int, float)) and isinstance(ts1, (int, float)) and ts0 > ts1:
            chronological = list(reversed(recent))
        else:
            chronological = list(recent)

        for i in range(len(chronological) - 1):
            current = chronological[i].command
            next_cmd = chronological[i + 1].command
            self._transitions[current][next_cmd] += 1
            self._total[current] += 1

        self._trained = True

    def predict(self, current_command: str, top_k: int = 3) -> list[tuple[str, float]]:
        """
        Predict next commands with probabilities.
        Returns: [(command, probability), ...]
        """
        if not self._trained or current_command not in self._transitions:
            return []

        total = self._total[current_command]
        if total == 0:
            return []
        predictions = []

        for cmd, count in sorted(
            self._transitions[current_command].items(),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]:
            prob = round(count / total, 3)
            predictions.append((cmd, prob))

        return predictions

    def get_ghost_text(self, current_command: str) -> str | None:
        """Get single best prediction for ghost-text display."""
        preds = self.predict(current_command, top_k=1)
        if preds and preds[0][1] >= 0.3:  # Only show if >= 30% probable
            return preds[0][0]
        return None
