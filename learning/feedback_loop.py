# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Feedback Loop Engine
Captures accept/reject/edit signals to drive real learning calibration.
"""

import time
from dataclasses import dataclass


@dataclass
class FeedbackEvent:
    """A single feedback event."""
    signal: str  # accept, reject, edit
    suggestion_type: str  # translation, fix, prediction
    original_input: str
    suggested_output: str
    user_correction: str | None = None
    timestamp: float = 0


class FeedbackLoop:
    """Captures user feedback signals and uses them for calibration."""

    def __init__(self, history_store, intent_classifier=None):
        self.history = history_store
        self.intent_classifier = intent_classifier
        self._session_events: list[FeedbackEvent] = []

    def record_accept(self, suggestion_type: str, original: str, suggested: str, source: str = ""):
        """User accepted a suggestion."""
        event = FeedbackEvent(
            signal="accept",
            suggestion_type=suggestion_type,
            original_input=original,
            suggested_output=suggested,
            timestamp=time.time(),
        )
        self._session_events.append(event)
        self.history.store_feedback(
            suggestion_type, original, suggested, "accept", source=source,
        )

    def record_reject(self, suggestion_type: str, original: str, suggested: str, source: str = ""):
        """User rejected a suggestion."""
        event = FeedbackEvent(
            signal="reject",
            suggestion_type=suggestion_type,
            original_input=original,
            suggested_output=suggested,
            timestamp=time.time(),
        )
        self._session_events.append(event)
        self.history.store_feedback(
            suggestion_type, original, suggested, "reject", source=source,
        )

    def record_edit(self, suggestion_type: str, original: str,
                    suggested: str, corrected: str, source: str = ""):
        """User edited a suggestion (most valuable signal)."""
        event = FeedbackEvent(
            signal="edit",
            suggestion_type=suggestion_type,
            original_input=original,
            suggested_output=suggested,
            user_correction=corrected,
            timestamp=time.time(),
        )
        self._session_events.append(event)
        self.history.store_feedback(
            suggestion_type, original, suggested, "edit",
            user_correction=corrected, source=source,
        )

        # Feed correction to NLP classifier for retraining
        if self.intent_classifier and suggestion_type == "intent":
            self.intent_classifier.add_correction(original, corrected)

    def get_session_stats(self) -> dict:
        """Get feedback stats for current session."""
        total = len(self._session_events)
        if total == 0:
            return {"total": 0, "accept_rate": 0}

        accepts = sum(1 for e in self._session_events if e.signal == "accept")
        edits = sum(1 for e in self._session_events if e.signal == "edit")
        rejects = sum(1 for e in self._session_events if e.signal == "reject")

        return {
            "total": total,
            "accept_rate": round(accepts / total * 100, 1),
            "edit_rate": round(edits / total * 100, 1),
            "reject_rate": round(rejects / total * 100, 1),
        }

    def get_overall_stats(self) -> dict:
        """Get overall feedback stats from DB."""
        return self.history.get_feedback_stats()
