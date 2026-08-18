# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Clipboard Integration
Copy commands, outputs, and AI suggestions to clipboard.
"""

import re
from typing import Optional

try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False


class ClipboardManager:
    """Cross-platform clipboard integration."""

    def __init__(self):
        self._last_copied: str = ""
        self._history: list[str] = []

    @property
    def available(self) -> bool:
        """Check if clipboard is available."""
        if not HAS_PYPERCLIP:
            return False
        try:
            pyperclip.paste()
            return True
        except Exception:
            return False

    def copy(self, text: str) -> bool:
        """Copy text to clipboard with in-memory fallback."""
        self._last_copied = text
        self._history.append(text)
        if len(self._history) > 50:
            self._history.pop(0)

        if HAS_PYPERCLIP:
            try:
                pyperclip.copy(text)
            except Exception:
                pass
        return True

    def paste(self) -> Optional[str]:
        """Get text from clipboard or memory fallback."""
        if HAS_PYPERCLIP:
            try:
                val = pyperclip.paste()
                if val:
                    return val
            except Exception:
                pass
        return self._last_copied if self._last_copied else None

    def copy_command(self, command: str) -> bool:
        """Copy a command to clipboard (strips leading/trailing whitespace)."""
        return self.copy(command.strip())

    def copy_output(self, output: str, max_length: int = 5000) -> bool:
        """Copy command output to clipboard (with length limit)."""
        if len(output) > max_length:
            output = output[:max_length] + f"\n\n... (truncated {len(output) - max_length} chars)"
        return self.copy(output)

    def copy_block(self, text: str, format_type: str = "plain") -> bool:
        """Copy text with optional formatting."""
        if format_type == "markdown":
            text = f"```\n{text}\n```"
        elif format_type == "quoted":
            text = "\n".join(f"> {line}" for line in text.split("\n"))
        return self.copy(text)

    def get_history(self, limit: int = 10) -> list[str]:
        """Get clipboard copy history."""
        return list(reversed(self._history[-limit:]))

    def detect_command_in_clipboard(self) -> Optional[str]:
        """Check if clipboard contains something that looks like a command."""
        content = self.paste()
        if not content:
            return None

        content = content.strip()
        # Skip multi-line content
        if "\n" in content:
            return None

        # Skip very long content
        if len(content) > 200:
            return None

        # Check if it looks like a command
        command_starters = [
            "git", "pip", "npm", "docker", "python", "node", "cargo",
            "ls", "cd", "dir", "cat", "grep", "find", "mkdir", "rm",
            "curl", "ssh", "kubectl", "terraform", "make",
        ]
        first_word = content.split()[0].lower() if content.split() else ""
        if first_word in command_starters:
            return content

        # Check for path-like content
        if content.startswith(("/", "./", "C:\\", "~/")):
            return content

        return None
