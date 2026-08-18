# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Interactive Terminal Menu Subsystem
Zero-dependency, high-performance, cross-platform ANSI interactive prompts.
Provides arrow-key navigation menus, masked text prompts, confirm toggles, and multi-select.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Optional, Callable, Any, List, Dict

# TrueColor & ANSI styling tokens
C_CYAN = "\033[38;2;56;189;248m"
C_MAGENTA = "\033[38;2;192;132;252m"
C_GREEN = "\033[38;2;74;222;128m"
C_YELLOW = "\033[38;2;251;191;36m"
C_RED = "\033[38;2;248;113;113m"
C_GRAY = "\033[38;2;148;163;184m"
C_MUTED = "\033[38;2;100;116;139m"
C_WHITE = "\033[38;2;241;245;249m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RESET = "\033[0m"

# Cursor controls
CURSOR_HIDE = "\033[?25l"
CURSOR_SHOW = "\033[?25h"
CLEAR_LINE = "\r\033[2K"


def enable_windows_vt_support():
    """Enable Virtual Terminal Processing on Windows console."""
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            STD_OUTPUT_HANDLE = -11
            h_out = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            mode_out = ctypes.c_ulong()
            if kernel32.GetConsoleMode(h_out, ctypes.byref(mode_out)):
                kernel32.SetConsoleMode(h_out, mode_out.value | 0x0004 | 0x0008)
        except Exception:
            pass

enable_windows_vt_support()


class Key:
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    ENTER = "ENTER"
    ESCAPE = "ESCAPE"
    BACKSPACE = "BACKSPACE"
    TAB = "TAB"
    SPACE = "SPACE"
    CTRL_C = "CTRL_C"
    CTRL_D = "CTRL_D"


def _read_key() -> str:
    """
    Read a single keystroke cross-platform without echo.
    Works on Windows (msvcrt) and Unix (termios/tty).
    """
    if os.name == "nt":
        import msvcrt
        try:
            ch = msvcrt.getwch()
        except (KeyboardInterrupt, EOFError):
            return Key.CTRL_C

        if ch in ("\x00", "\xe0"):
            # Scan code prefix
            try:
                code = msvcrt.getwch()
            except Exception:
                return ""
            if code == "H":
                return Key.UP
            elif code == "P":
                return Key.DOWN
            elif code == "K":
                return Key.LEFT
            elif code == "M":
                return Key.RIGHT
            return ""
        elif ch in ("\r", "\n"):
            return Key.ENTER
        elif ch == "\x1b":
            return Key.ESCAPE
        elif ch in ("\x08", "\x7f"):
            return Key.BACKSPACE
        elif ch == "\t":
            return Key.TAB
        elif ch == " ":
            return Key.SPACE
        elif ch == "\x03":
            return Key.CTRL_C
        elif ch == "\x04":
            return Key.CTRL_D
        return ch
    else:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                # Check for escape sequence
                next_ch = sys.stdin.read(1)
                if next_ch == "[":
                    code = sys.stdin.read(1)
                    if code == "A":
                        return Key.UP
                    elif code == "B":
                        return Key.DOWN
                    elif code == "C":
                        return Key.RIGHT
                    elif code == "D":
                        return Key.LEFT
                return Key.ESCAPE
            elif ch in ("\r", "\n"):
                return Key.ENTER
            elif ch in ("\x08", "\x7f"):
                return Key.BACKSPACE
            elif ch == "\t":
                return Key.TAB
            elif ch == " ":
                return Key.SPACE
            elif ch == "\x03":
                return Key.CTRL_C
            elif ch == "\x04":
                return Key.CTRL_D
            return ch
        except (KeyboardInterrupt, EOFError):
            return Key.CTRL_C
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def select_menu(
    title: str,
    options: list[str | dict[str, str]],
    default_index: int = 0,
    description: str = "",
    badge_map: Optional[dict[int, str]] = None,
) -> Optional[int]:
    """
    Interactive arrow-key selection menu rendered in-place.
    
    Args:
        title: Header text for the menu
        options: List of string titles, or dicts with 'name', 'desc', 'badge'
        default_index: Initially highlighted option
        description: Subtitle explanation
        badge_map: Dict mapping index to badge string (e.g. {0: "(Active)"})
        
    Returns:
        Selected option index (0-based), or None if cancelled.
    """
    if not options:
        return None

    # Normalize options
    items = []
    for opt in options:
        if isinstance(opt, dict):
            items.append(opt)
        else:
            items.append({"name": str(opt), "desc": "", "badge": ""})

    current_idx = max(0, min(default_index, len(items) - 1))
    lines_rendered = 0

    # Hide cursor
    sys.stdout.write(CURSOR_HIDE)
    sys.stdout.flush()

    try:
        while True:
            # Move cursor up to overwrite previous frame
            if lines_rendered > 0:
                sys.stdout.write(f"\033[{lines_rendered}A")

            buffer = []
            # Title bar
            buffer.append(f"{CLEAR_LINE}  {C_CYAN}┌── {C_BOLD}{title}{C_RESET}{C_CYAN} {'─' * max(2, 45 - len(title))}┐{C_RESET}")
            if description:
                buffer.append(f"{CLEAR_LINE}  {C_CYAN}│{C_RESET}  {C_MUTED}{description}{C_RESET}")
                buffer.append(f"{CLEAR_LINE}  {C_CYAN}├──────────────────────────────────────────────────────┤{C_RESET}")

            # Options
            for idx, item in enumerate(items):
                is_active = (idx == current_idx)
                badge = item.get("badge", "")
                if badge_map and idx in badge_map:
                    badge = badge_map[idx]

                badge_str = f" {C_GREEN}{badge}{C_RESET}" if badge else ""
                desc_str = f" {C_MUTED}• {item['desc']}{C_RESET}" if item.get("desc") else ""

                if is_active:
                    pointer = f"{C_CYAN}❯{C_RESET}"
                    num = f"{C_BOLD}{C_CYAN}[{idx + 1}]{C_RESET}"
                    label = f"{C_BOLD}{C_WHITE}{item['name']}{C_RESET}"
                    line = f"{CLEAR_LINE}  {C_CYAN}│{C_RESET}  {pointer} {num} {label}{badge_str}{desc_str}"
                else:
                    pointer = " "
                    num = f"{C_MUTED}[{idx + 1}]{C_RESET}"
                    label = f"{C_GRAY}{item['name']}{C_RESET}"
                    line = f"{CLEAR_LINE}  {C_CYAN}│{C_RESET}  {pointer} {num} {label}{badge_str}{desc_str}"

                buffer.append(line)

            # Footer
            buffer.append(f"{CLEAR_LINE}  {C_CYAN}└──────────────────────────────────────────────────────┘{C_RESET}")
            buffer.append(f"{CLEAR_LINE}  {C_MUTED}(Use ↑/↓ or 1-{len(items)} to navigate, Enter to select, Esc to cancel){C_RESET}")

            lines_rendered = len(buffer)
            sys.stdout.write("\n".join(buffer) + "\n")
            sys.stdout.flush()

            # Read keystroke
            key = _read_key()

            if key == Key.UP:
                current_idx = (current_idx - 1) % len(items)
            elif key == Key.DOWN:
                current_idx = (current_idx + 1) % len(items)
            elif key in (Key.ENTER, Key.SPACE):
                # Selection confirmed
                # Clear menu lines
                sys.stdout.write(f"\033[{lines_rendered}A")
                for _ in range(lines_rendered):
                    sys.stdout.write(f"{CLEAR_LINE}\n")
                sys.stdout.write(f"\033[{lines_rendered}A")
                sys.stdout.write(f"{CLEAR_LINE}  {C_GREEN}✔{C_RESET} {C_BOLD}{title}:{C_RESET} {C_CYAN}{items[current_idx]['name']}{C_RESET}\n")
                sys.stdout.flush()
                return current_idx
            elif key in (Key.ESCAPE, Key.CTRL_C, Key.CTRL_D):
                # Cancelled
                sys.stdout.write(f"\033[{lines_rendered}A")
                for _ in range(lines_rendered):
                    sys.stdout.write(f"{CLEAR_LINE}\n")
                sys.stdout.write(f"\033[{lines_rendered}A")
                sys.stdout.write(f"{CLEAR_LINE}  {C_YELLOW}⚠{C_RESET} {C_MUTED}Selection cancelled{C_RESET}\n")
                sys.stdout.flush()
                return None
            elif key.isdigit() and 1 <= int(key) <= len(items):
                current_idx = int(key) - 1
                # Auto select on digit
                sys.stdout.write(f"\033[{lines_rendered}A")
                for _ in range(lines_rendered):
                    sys.stdout.write(f"{CLEAR_LINE}\n")
                sys.stdout.write(f"\033[{lines_rendered}A")
                sys.stdout.write(f"{CLEAR_LINE}  {C_GREEN}✔{C_RESET} {C_BOLD}{title}:{C_RESET} {C_CYAN}{items[current_idx]['name']}{C_RESET}\n")
                sys.stdout.flush()
                return current_idx

    finally:
        sys.stdout.write(CURSOR_SHOW)
        sys.stdout.flush()


def text_prompt(
    prompt_text: str,
    default: str = "",
    password: bool = False,
    validator: Optional[Callable[[str], bool]] = None,
) -> Optional[str]:
    """
    Clean interactive inline text/password prompt.
    """
    sys.stdout.write(f"  {C_CYAN}❯{C_RESET} {C_BOLD}{prompt_text}{C_RESET}")
    if default:
        sys.stdout.write(f" {C_MUTED}[{default}]{C_RESET}")
    sys.stdout.write(": ")
    sys.stdout.flush()

    if password:
        # Masked input
        chars = []
        try:
            while True:
                key = _read_key()
                if key == Key.ENTER:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    break
                elif key in (Key.ESCAPE, Key.CTRL_C):
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return None
                elif key == Key.BACKSPACE:
                    if chars:
                        chars.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                elif len(key) == 1 and ord(key) >= 32:
                    chars.append(key)
                    sys.stdout.write(f"{C_CYAN}•{C_RESET}")
                    sys.stdout.flush()
            val = "".join(chars)
            return val if val else default
        except Exception:
            return default
    else:
        try:
            val = input().strip()
            return val if val else default
        except (KeyboardInterrupt, EOFError):
            print()
            return None


def confirm_prompt(question: str, default: bool = True) -> bool:
    """
    Interactive confirmation prompt.
    """
    hint = f"{C_BOLD}Y{C_RESET}{C_MUTED}/n{C_RESET}" if default else f"{C_MUTED}y/{C_RESET}{C_BOLD}N{C_RESET}"
    sys.stdout.write(f"  {C_YELLOW}?{C_RESET} {question} [{hint}]: ")
    sys.stdout.flush()

    try:
        val = input().strip().lower()
        if not val:
            return default
        return val in ("y", "yes", "true", "1")
    except (KeyboardInterrupt, EOFError):
        print()
        return False
