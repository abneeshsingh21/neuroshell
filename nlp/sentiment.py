# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Sentiment / Frustration Detector — Production Grade
Adaptive responses, success celebration, learning mode detection,
session tracking with decay, and proactive intervention.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    from nltk.sentiment.vader import SentimentIntensityAnalyzer
    HAS_VADER = True
except ImportError:
    HAS_VADER = False


@dataclass
class SentimentResult:
    state: str          # frustrated, confused, urgent, confident, exploring, celebrating, neutral
    score: float        # 0-1 intensity
    detail: str = ""
    suggestion: str = ""  # adaptive response suggestion


class SentimentDetector:
    """
    Production-grade sentiment detector.

    Features:
    - 7 emotional states with adaptive suggestions
    - Error streak amplification with decay
    - Learning/exploration mode detection
    - Success celebration after solving issues
    - Repetition detection (user stuck)
    - Verbosity recommendation based on state
    - Session analytics
    """

    FRUSTRATION_WORDS = {
        "ugh", "argh", "damn", "dammit", "wtf", "why",
        "broken", "stupid", "hate", "terrible", "awful",
        "again", "still", "not working", "doesn't work",
        "impossible", "useless", "waste", "annoying",
        "frustrated", "stuck", "confused",
    }

    CONFUSION_PATTERNS = [
        r"\?{2,}", r"^how\b", r"^why\b",
        r"\bi\s*don'?t\s*(know|understand|get)\b",
        r"\bconfused?\b", r"\bwhat\s+the\b", r"\bhelp\s+me\b",
        r"\bnot\s+sure\b", r"\bwhat\s+is\b",
    ]

    URGENCY_WORDS = {
        "quick", "quickly", "fast", "asap", "urgent",
        "hurry", "now", "immediately", "rush", "deadline",
        "production", "down", "broken", "emergency",
    }

    EXPLORING_PATTERNS = [
        r"^let me try\b", r"^what if\b", r"^try\b",
        r"^hmm\b", r"^maybe\b", r"^i wonder\b",
        r"^can i\b", r"^is it possible\b",
        r"let's see", r"let's try", r"how about",
    ]

    SUCCESS_WORDS = {
        "works", "working", "fixed", "solved", "great",
        "perfect", "thanks", "awesome", "nice", "finally",
        "yay", "yes", "done", "got it",
    }

    CONFIDENCE_PATTERNS = [
        r"^[a-z\-]+\s",
        r"^\S+$",
        r"^(git|pip|npm|docker|python|node|kubectl|terraform|make|cargo)\s",
    ]

    def __init__(self):
        self._vader: Optional[SentimentIntensityAnalyzer] = None
        self._error_streak: int = 0
        self._success_streak: int = 0
        self._session_frustration: float = 0.0
        self._last_inputs: list[str] = []
        self._last_was_error: bool = False
        self._session_start: float = time.time()
        self._total_commands: int = 0
        self._total_errors: int = 0

    def initialize(self) -> bool:
        if not HAS_VADER:
            return False
        try:
            self._vader = SentimentIntensityAnalyzer()
            return True
        except Exception:
            try:
                import nltk
                nltk.download("vader_lexicon", quiet=True)
                self._vader = SentimentIntensityAnalyzer()
                return True
            except Exception:
                return False

    def analyze(self, text: str, was_error: bool = False) -> SentimentResult:
        """Analyze user input with adaptive response suggestions."""
        text_lower = text.strip().lower()
        self._total_commands += 1

        # Update streaks
        if was_error:
            self._error_streak += 1
            self._success_streak = 0
            self._total_errors += 1
            self._session_frustration += 0.1
            self._last_was_error = True
        else:
            self._error_streak = max(0, self._error_streak - 1)
            self._session_frustration = max(0, self._session_frustration - 0.05)
            if self._last_was_error:
                self._success_streak += 1
            self._last_was_error = False

        self._last_inputs.append(text_lower)
        if len(self._last_inputs) > 30:
            self._last_inputs.pop(0)

        # Check success celebration (solved a streak)
        if self._success_streak >= 1 and self._check_success(text_lower):
            self._session_frustration = max(0, self._session_frustration - 0.3)
            return SentimentResult(
                state="celebrating", score=0.8,
                detail=f"Fixed after {self._error_streak + self._success_streak} attempts",
                suggestion="Great job! The issue seems resolved. 🎉",
            )

        # Check for exploring/learning mode
        if self._check_exploring(text_lower):
            return SentimentResult(
                state="exploring", score=0.7,
                detail="Experimental/learning input detected",
                suggestion="Feel free to experiment! I'll explain as we go.",
            )

        # Check urgency
        if self._check_urgency(text_lower):
            return SentimentResult(
                state="urgent", score=0.8,
                detail="Urgency keywords detected",
                suggestion="I'll prioritize speed. Here's the fastest approach.",
            )

        # Check frustration
        frustration = self._check_frustration(text_lower)
        if frustration > 0.5:
            suggestion = self._frustration_suggestion()
            return SentimentResult(
                state="frustrated", score=min(1.0, frustration),
                detail=f"Error streak: {self._error_streak}, session: {self._session_frustration:.1f}",
                suggestion=suggestion,
            )

        # Check confusion
        if self._check_confusion(text_lower):
            return SentimentResult(
                state="confused", score=0.7,
                detail="Question/help patterns detected",
                suggestion="Let me break this down step by step.",
            )

        # Check confidence
        if self._check_confidence(text_lower):
            return SentimentResult(
                state="confident", score=0.8,
                detail="Direct command input",
                suggestion="",  # minimal intervention
            )

        # VADER fallback
        if self._vader:
            scores = self._vader.polarity_scores(text)
            if scores["compound"] < -0.3:
                return SentimentResult(
                    state="frustrated", score=abs(scores["compound"]),
                    detail=f"VADER negative: {scores['compound']:.2f}",
                    suggestion="I notice this might be frustrating. Let me help!",
                )

        return SentimentResult(state="neutral", score=0.5)

    def get_verbosity_level(self) -> str:
        """Recommend verbosity based on emotional state."""
        if self._session_frustration > 0.6:
            return "verbose"     # more explanations when frustrated
        elif self._error_streak >= 3:
            return "verbose"     # proactive help
        elif self._session_frustration < 0.1 and self._error_streak == 0:
            return "concise"     # user is doing well
        return "normal"

    def record_error(self):
        self._error_streak += 1
        self._total_errors += 1
        self._session_frustration += 0.15

    def should_offer_help(self) -> bool:
        return self._error_streak >= 3 or self._session_frustration >= 0.5

    def get_session_state(self) -> dict:
        elapsed = time.time() - self._session_start
        return {
            "error_streak": self._error_streak,
            "success_streak": self._success_streak,
            "frustration_level": round(self._session_frustration, 2),
            "should_offer_help": self.should_offer_help(),
            "total_commands": self._total_commands,
            "total_errors": self._total_errors,
            "error_rate": round(self._total_errors / max(1, self._total_commands), 2),
            "session_minutes": round(elapsed / 60, 1),
            "verbosity": self.get_verbosity_level(),
        }

    def reset(self):
        self._error_streak = 0
        self._success_streak = 0
        self._session_frustration = 0.0
        self._last_inputs.clear()
        self._last_was_error = False
        self._total_commands = 0
        self._total_errors = 0
        self._session_start = time.time()

    # ── Detectors ─────────────────────────────────────────

    def _check_frustration(self, text: str) -> float:
        score = 0.0
        words = set(text.split())
        matches = words & self.FRUSTRATION_WORDS
        score += len(matches) * 0.2

        if self._error_streak >= 3:
            score += 0.3
        elif self._error_streak >= 2:
            score += 0.15

        score += self._session_frustration * 0.3

        # Repetition detection
        if len(self._last_inputs) >= 3:
            last_3 = self._last_inputs[-3:]
            if len(set(last_3)) == 1:
                score += 0.4

        score += text.count("!") * 0.1
        if text.isupper() and len(text) > 3:
            score += 0.3

        return min(1.0, score)

    def _check_confusion(self, text: str) -> bool:
        return any(re.search(p, text, re.IGNORECASE) for p in self.CONFUSION_PATTERNS)

    def _check_urgency(self, text: str) -> bool:
        return bool(set(text.split()) & self.URGENCY_WORDS)

    def _check_confidence(self, text: str) -> bool:
        return any(re.match(p, text) for p in self.CONFIDENCE_PATTERNS)

    def _check_exploring(self, text: str) -> bool:
        return any(re.search(p, text, re.IGNORECASE) for p in self.EXPLORING_PATTERNS)

    def _check_success(self, text: str) -> bool:
        return bool(set(text.split()) & self.SUCCESS_WORDS)

    def _frustration_suggestion(self) -> str:
        if self._error_streak >= 5:
            return "You've hit several errors in a row. Want me to suggest a different approach?"
        elif self._error_streak >= 3:
            return "Let me try a different angle to solve this."
        else:
            return "I see this is tricky. Let me provide more detail."
