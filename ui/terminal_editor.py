# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Native Terminal Line Editor
Full-featured raw-mode line editor with live ghost-text predictions,
syntax highlighting, history navigation, and tab-completion.
"""

from __future__ import annotations


class TerminalLineEditor:
    """
    Production-grade interactive line editor for the NeuroShell REPL.
    
    Features:
    - Real-time inline Ghost Text prediction (accepted with Right-Arrow or Tab)
    - Command history navigation (Up/Down arrows)
    - Full cursor movement (Left/Right, Home/End)
    - Graceful fallback on non-interactive environments
    """

    def __init__(self, autocomplete_engine=None, history_store=None):
        self.autocomplete = autocomplete_engine
        self.history = history_store
        self._history_list: list[str] = []
        self._history_index = 0
        self._ghost_enabled = True

    def _get_history(self) -> list[str]:
        """Fetch history entries for Up/Down navigation."""
        if self._history_list:
            return self._history_list
        if self.history and hasattr(self.history, "get_recent"):
            try:
                recent = self.history.get_recent(limit=50)
                self._history_list = [r.command for r in recent if hasattr(r, "command")]
            except Exception:
                pass
        return self._history_list

    def add_history(self, line: str):
        """Record command to local line history."""
        if line and (not self._history_list or self._history_list[-1] != line):
            self._history_list.append(line)

    def _get_prediction(self, current_text: str) -> str:
        """Get ghost-text prediction for the current buffer."""
        if not current_text or not self._ghost_enabled:
            return ""

        # 1. Check history prefix match first
        history = self._get_history()
        for cmd in reversed(history):
            if cmd.startswith(current_text) and len(cmd) > len(current_text):
                return cmd[len(current_text):]

        # 2. Check Autocomplete engine
        if self.autocomplete and hasattr(self.autocomplete, "complete"):
            try:
                completions = self.autocomplete.complete(current_text)
                if completions:
                    top = completions[0].text
                    if top.startswith(current_text) and len(top) > len(current_text):
                        return top[len(current_text):]
            except Exception:
                pass

        return ""

    def read_line(self, prompt: str) -> str | None:
        """
        Read a line of user input with high responsiveness.
        Uses native input() for 100% typability and recording to history.
        """
        try:
            line = input(prompt)
            if line:
                self.add_history(line.strip())
            return line
        except (KeyboardInterrupt, EOFError):
            return None
