# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Unit tests for NeuroShell native terminal line editor (ui/terminal_editor.py).
"""

import sys
import pytest
from unittest.mock import patch, MagicMock

from ui.terminal_editor import TerminalLineEditor


def test_line_editor_history_recording():
    """Test TerminalLineEditor records commands to history."""
    editor = TerminalLineEditor()
    editor.add_history("git status")
    editor.add_history("git diff")
    
    hist = editor._get_history()
    assert "git status" in hist
    assert "git diff" in hist


def test_line_editor_ghost_text_prediction():
    """Test ghost text prediction from history."""
    editor = TerminalLineEditor()
    editor.add_history("docker container ls")
    
    pred = editor._get_prediction("docker con")
    assert pred == "tainer ls"


def test_line_editor_fallback_in_non_tty(monkeypatch):
    """Test fallback to standard input in non-interactive environment."""
    monkeypatch.setenv("NEUROSHELL_TEST_MODE", "1")
    editor = TerminalLineEditor()
    
    with patch("builtins.input", return_value="echo test_fallback"):
        line = editor.read_line("> ")
        assert line == "echo test_fallback"
