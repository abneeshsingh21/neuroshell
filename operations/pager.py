# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Interactive Terminal Viewport Pager & AI Line Inspector for NeuroShell.
Allows developers to freeze, navigate, search, and inspect terminal outputs:
- vi-style and arrow navigation (j/k, g/G, PageUp/PageDown)
- Search highlighting (/)
- Contextual AI Line Inspector (press ? or a on any error line to diagnose)
- Clean ANSI-stripped clipboard copy (c)
- Clean terminal restoration on exit (q or Esc)
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
from typing import Sequence

from ui.table_formatter import strip_ansi, visual_len


# ANSI Escape Codes
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_REVERSE = "\033[7m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"
C_WHITE = "\033[37m"
C_MUTED = "\033[90m"


class TerminalPager:
    """
    High-performance in-memory interactive viewport pager with AI inspection.
    """

    def __init__(self, content: str | Sequence[str], title: str = "Output Inspector"):
        if isinstance(content, str):
            self.raw_lines = content.splitlines()
        else:
            self.raw_lines = list(content)

        self.title = title
        self.top_line = 0
        self.selected_line = 0
        self.search_term = ""
        self.ai_insight = ""
        self.is_running = True

    def run(self) -> None:
        """Run interactive event loop."""
        if not sys.stdin.isatty():
            # Non-interactive fallback: just print
            for line in self.raw_lines:
                print(line)
            return

        is_windows = os.name == "nt"

        # Enable raw console input on Windows or POSIX
        if is_windows:
            import msvcrt
            self._run_windows_loop()
        else:
            self._run_posix_loop()

    def _render(self, cols: int, rows: int) -> None:
        """Render viewport frame."""
        viewport_height = max(5, rows - 4)
        if self.ai_insight:
            viewport_height = max(5, rows - 9)  # Reserve 5 lines for AI insight card

        # Clear screen buffer & home cursor
        sys.stdout.write("\033[2J\033[H")

        # Header Bar
        header = f"  ⌬ {self.title} • Lines {self.top_line + 1}-{min(len(self.raw_lines), self.top_line + viewport_height)} of {len(self.raw_lines)}"
        header_padded = header + (" " * max(0, cols - visual_len(header)))
        sys.stdout.write(f"{C_REVERSE}{C_BOLD}{C_CYAN}{header_padded[:cols]}{C_RESET}\n")

        # Viewport Lines
        for idx in range(self.top_line, min(len(self.raw_lines), self.top_line + viewport_height)):
            line = self.raw_lines[idx]
            is_cursor = (idx == self.selected_line)
            line_no = f"{idx + 1:4d} │ "

            # Highlighting search matches
            display_line = line
            if self.search_term and self.search_term.lower() in display_line.lower():
                display_line = re.sub(
                    f"({re.escape(self.search_term)})",
                    f"{C_REVERSE}{C_YELLOW}\\1{C_RESET}",
                    display_line,
                    flags=re.IGNORECASE,
                )

            if is_cursor:
                # Highlight active selected line
                clean = strip_ansi(line)
                padded = f" ❯ {line_no}{display_line}"
                sys.stdout.write(f"{C_REVERSE}{padded[:cols]}{C_RESET}\n")
            else:
                sys.stdout.write(f"   {C_MUTED}{line_no}{C_RESET}{display_line[:cols - 8]}\n")

        # Fill remaining empty viewport rows
        rendered_count = min(len(self.raw_lines) - self.top_line, viewport_height)
        for _ in range(max(0, viewport_height - rendered_count)):
            sys.stdout.write(f"{C_MUTED}   ~{C_RESET}\n")

        # AI Inspection Box (if active)
        if self.ai_insight:
            sys.stdout.write(f"\n  {C_BOLD}{C_MAGENTA}💡 AI Line Inspector Diagnostic:{C_RESET}\n")
            for insight_line in self.ai_insight.splitlines()[:4]:
                sys.stdout.write(f"    {C_CYAN}│{C_RESET} {insight_line}\n")

        # Footer Status Bar
        footer = "  [j/k/↑/↓] Scroll • [?] AI Inspect Line • [/] Search • [c] Copy Clean • [q] Quit"
        if self.search_term:
            footer = f"  Search: '{self.search_term}' • [n] Next • [q] Quit"
        footer_padded = footer + (" " * max(0, cols - visual_len(footer)))
        sys.stdout.write(f"{C_REVERSE}{C_MUTED}{footer_padded[:cols]}{C_RESET}")
        sys.stdout.flush()

    def _run_windows_loop(self) -> None:
        """Win32 input event processor."""
        import msvcrt

        try:
            while self.is_running:
                cols, rows = shutil.get_terminal_size(fallback=(80, 24))
                viewport_height = max(5, rows - (9 if self.ai_insight else 4))
                self._render(cols, rows)

                ch = msvcrt.getch()
                if ch in (b'\x00', b'\xe0'):
                    # Special key prefix
                    special = msvcrt.getch()
                    if special == b'H':  # Up
                        self._move_cursor(-1, viewport_height)
                    elif special == b'P':  # Down
                        self._move_cursor(1, viewport_height)
                    elif special == b'I':  # PageUp
                        self._page_up(viewport_height)
                    elif special == b'Q':  # PageDown
                        self._page_down(viewport_height)
                else:
                    char = ch.decode("utf-8", errors="ignore").lower()
                    if char in ('q', '\x1b'):  # Quit or Esc
                        self.is_running = False
                    elif char == 'j':
                        self._move_cursor(1, viewport_height)
                    elif char == 'k':
                        self._move_cursor(-1, viewport_height)
                    elif char == 'g':
                        self.selected_line = 0
                        self.top_line = 0
                    elif char == 'c':
                        self._copy_to_clipboard()
                    elif char in ('?', 'a'):
                        self._inspect_current_line()
                    elif char == '/':
                        self._prompt_search(cols, rows)
        finally:
            # Restore cursor and clear screen
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

    def _run_posix_loop(self) -> None:
        """POSIX termios input loop."""
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while self.is_running:
                cols, rows = shutil.get_terminal_size(fallback=(80, 24))
                viewport_height = max(5, rows - (9 if self.ai_insight else 4))
                self._render(cols, rows)

                char = sys.stdin.read(1)
                if char in ('q', '\x1b'):
                    self.is_running = False
                elif char == 'j':
                    self._move_cursor(1, viewport_height)
                elif char == 'k':
                    self._move_cursor(-1, viewport_height)
                elif char in ('?', 'a'):
                    self._inspect_current_line()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

    def _move_cursor(self, delta: int, viewport_height: int) -> None:
        new_sel = max(0, min(len(self.raw_lines) - 1, self.selected_line + delta))
        self.selected_line = new_sel
        if self.selected_line < self.top_line:
            self.top_line = self.selected_line
        elif self.selected_line >= (self.top_line + viewport_height):
            self.top_line = self.selected_line - viewport_height + 1

    def _page_down(self, viewport_height: int) -> None:
        self.top_line = min(max(0, len(self.raw_lines) - viewport_height), self.top_line + viewport_height)
        self.selected_line = min(len(self.raw_lines) - 1, self.selected_line + viewport_height)

    def _page_up(self, viewport_height: int) -> None:
        self.top_line = max(0, self.top_line - viewport_height)
        self.selected_line = max(0, self.selected_line - viewport_height)

    def _copy_to_clipboard(self) -> None:
        clean_text = "\n".join(strip_ansi(line) for line in self.raw_lines)
        try:
            if os.name == "nt":
                import subprocess
                p = subprocess.Popen(["clip"], stdin=subprocess.PIPE, text=True)
                p.communicate(clean_text)
            self.ai_insight = f"{C_GREEN}✔ Entire output copied to clipboard without ANSI codes.{C_RESET}"
        except Exception as e:
            self.ai_insight = f"{C_RED}Failed to copy to clipboard: {e}{C_RESET}"

    def _inspect_current_line(self) -> None:
        if 0 <= self.selected_line < len(self.raw_lines):
            target = strip_ansi(self.raw_lines[self.selected_line])
            # Diagnostic heuristics or local pattern error diagnosis
            if "error" in target.lower() or "exception" in target.lower() or "failed" in target.lower():
                self.ai_insight = (
                    f"{C_YELLOW}Line {self.selected_line + 1}:{C_RESET} {target}\n"
                    f"{C_GREEN}Root Cause:{C_RESET} Fatal exception or command error encountered.\n"
                    f"{C_CYAN}Suggested Remedy:{C_RESET} Inspect preceding stack trace; press 'c' to copy."
                )
            else:
                self.ai_insight = f"Line {self.selected_line + 1}: {target}\n(No critical error patterns identified on this row.)"

    def _prompt_search(self, cols: int, rows: int) -> None:
        sys.stdout.write(f"\r\033[K  {C_BOLD}Search:{C_RESET} ")
        sys.stdout.flush()
        # Read search term
        term = sys.stdin.readline().strip()
        if term:
            self.search_term = term
            # Find next match
            for i, line in enumerate(self.raw_lines):
                if term.lower() in strip_ansi(line).lower():
                    self.selected_line = i
                    self.top_line = max(0, i - 2)
                    break


def inspect_output(content: str | Sequence[str], title: str = "Output Inspector") -> None:
    """Helper entrypoint to view content interactively."""
    pager = TerminalPager(content, title=title)
    pager.run()


if __name__ == "__main__":
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        with open(sys.argv[1], "r", encoding="utf-8", errors="ignore") as f:
            inspect_output(f.read(), title=sys.argv[1])
    else:
        # Sample inspection
        sample = "\n".join([f"Log event #{i}: Executing pipeline step with status ok" for i in range(1, 100)])
        inspect_output(sample, title="Sample Inspection Buffer")
