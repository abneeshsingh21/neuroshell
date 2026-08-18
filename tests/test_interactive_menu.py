# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Unit tests for NeuroShell interactive menu subsystem (ui/interactive_menu.py).
"""

import sys
import pytest
from unittest.mock import patch, MagicMock

from ui.interactive_menu import (
    select_menu, text_prompt, confirm_prompt, Key, _read_key
)


def test_select_menu_direct_digit_selection(monkeypatch):
    """Test select_menu selecting option via numeric shortcut."""
    options = [
        {"name": "GROQ", "desc": "Fast Cloud"},
        {"name": "OPENAI", "desc": "GPT-4o"},
        {"name": "OLLAMA", "desc": "Local"},
    ]
    # Simulate user pressing '2'
    with patch("ui.interactive_menu._read_key", return_value="2"):
        selected = select_menu("Select Provider", options, default_index=0)
        assert selected == 1  # 2nd item (index 1)


def test_select_menu_enter_selection(monkeypatch):
    """Test select_menu confirming current default with Enter."""
    options = ["Alpha", "Beta", "Gamma"]
    with patch("ui.interactive_menu._read_key", return_value=Key.ENTER):
        selected = select_menu("Select Greek Letter", options, default_index=2)
        assert selected == 2


def test_select_menu_cancel(monkeypatch):
    """Test select_menu cancelling with Escape."""
    options = ["Option 1", "Option 2"]
    with patch("ui.interactive_menu._read_key", return_value=Key.ESCAPE):
        selected = select_menu("Test Cancel", options)
        assert selected is None


def test_text_prompt_regular():
    """Test text_prompt reading normal input."""
    with patch("builtins.input", return_value="my_custom_value"):
        res = text_prompt("Enter parameter", default="fallback")
        assert res == "my_custom_value"


def test_text_prompt_default():
    """Test text_prompt falling back to default when empty."""
    with patch("builtins.input", return_value=""):
        res = text_prompt("Enter parameter", default="fallback")
        assert res == "fallback"


def test_confirm_prompt():
    """Test confirm_prompt with yes and no."""
    with patch("builtins.input", return_value="y"):
        assert confirm_prompt("Proceed?") is True

    with patch("builtins.input", return_value="n"):
        assert confirm_prompt("Proceed?") is False

    with patch("builtins.input", return_value=""):
        assert confirm_prompt("Proceed?", default=True) is True
        assert confirm_prompt("Proceed?", default=False) is False
