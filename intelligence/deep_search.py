# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

# Cyberpunk ANSI Theme
COLOR_PRIMARY = "\033[38;2;56;189;248m"  # Cyan
COLOR_SECONDARY = "\033[38;2;188;140;255m" # Purple
COLOR_SUCCESS = "\033[38;2;63;185;80m"    # Green
COLOR_WARNING = "\033[38;2;210;153;34m"   # Yellow
COLOR_TEXT = "\033[38;2;230;237;243m"     # Dim White
COLOR_MUTED = "\033[38;2;139;148;158m"    # Gray
COLOR_RESET = "\033[0m"

# Aggressively ignore heavy/irrelevant system caches & builds
IGNORED_DIRS = {
    "node_modules", ".git", "__pycache__", "venv", "env", ".env",
    ".vscode", ".idea", "AppData", "Windows", "Program Files",
    "Program Files (x86)", "dist", "build", "target", ".next"
}

def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

def print_header(query: str, start_dir: str):
    print(f"\n{COLOR_SECONDARY}◈◈ N-SEARCH PROTOCOL INITIATED ◈◈{COLOR_RESET}")
    print(f"{COLOR_MUTED}Query:{COLOR_RESET} {COLOR_PRIMARY}{query}{COLOR_RESET}")
    print(f"{COLOR_MUTED}Root:{COLOR_RESET} {COLOR_TEXT}{start_dir}{COLOR_RESET}")
    # Table Header
    print(f"{COLOR_PRIMARY}TYPE{COLOR_RESET} | {COLOR_SUCCESS}SIZE{COLOR_RESET}      | {COLOR_SECONDARY}MATCH{COLOR_RESET}")
    print(f"{COLOR_MUTED}{'-'*65}{COLOR_RESET}")

def print_result(is_dir: bool, size: str, path: str, name: str, query: str):
    # Highlight the matching part in the name exactly
    highlighted_name = re.sub(
        f"({re.escape(query)})",
        f"{COLOR_WARNING}\\1{COLOR_TEXT}",
        name,
        flags=re.IGNORECASE
    )

    # Path formatting
    parent = os.path.dirname(path)
    if len(parent) > 50:
        parent = "..." + parent[-47:]

    type_str = f"{COLOR_SECONDARY}[DIR]{COLOR_RESET} " if is_dir else f"{COLOR_PRIMARY}[FILE]{COLOR_RESET}"
    size_str = f"{size:>8}"

    print(f"{type_str} | {COLOR_SUCCESS}{size_str}{COLOR_RESET} | {COLOR_TEXT}{highlighted_name}{COLOR_RESET}")
    print(f"       |          | {COLOR_MUTED}↳ {parent}{COLOR_RESET}")

def scan_directory(directory: str, query: str, results: list, start_time: float, timeout: int = 10):
    """Recursively scan directories avoiding junk."""
    if time.time() - start_time > timeout:
        return # Bail out if taking too long

    try:
        query_lower = query.lower()
        subdirs = []

        with os.scandir(directory) as entries:
            for entry in entries:
                name = entry.name
                is_dir = entry.is_dir()

                # Check match
                if query_lower in name.lower():
                    size_str = "-"
                    if not is_dir:
                        try:
                            size_str = format_size(entry.stat().st_size)
                        except OSError:
                            size_str = "Unknown"

                    results.append((is_dir, size_str, entry.path, name))

                    # Hard cap at 50 results to prevent terminal flood
                    if len(results) >= 50:
                        return

                # Queue subdirs if not ignored
                if is_dir and name not in IGNORED_DIRS and not name.startswith("."):
                    subdirs.append(entry.path)

        # Recurse
        for subdir in subdirs:
            if len(results) >= 50:
                break
            scan_directory(subdir, query, results, start_time, timeout)

    except OSError:
        pass # Skip unreadable dirs

class DeepSearch:
    """Programmatic deep search interface."""

    def __init__(self, default_timeout: int = 10):
        self.default_timeout = default_timeout

    def search(self, query: str, directory: str | None = None, timeout: int | None = None) -> list[tuple[bool, str, str, str]]:
        """Search recursively for matches."""
        target_dir = directory or os.getcwd()
        limit_timeout = timeout if timeout is not None else self.default_timeout
        results = []
        start_time = time.time()
        scan_directory(target_dir, query, results, start_time, timeout=limit_timeout)
        results.sort(key=lambda x: (not x[0], x[3].lower()))
        return results

    def format_results(self, query: str, results: list, start_dir: str = "", elapsed: float = 0.0) -> str:
        """Format search results for terminal display."""
        lines = [
            f"\n{COLOR_SECONDARY}◈◈ N-SEARCH RESULTS ◈◈{COLOR_RESET}",
            f"{COLOR_MUTED}Query:{COLOR_RESET} {COLOR_PRIMARY}{query}{COLOR_RESET}",
            f"{COLOR_PRIMARY}TYPE{COLOR_RESET} | {COLOR_SUCCESS}SIZE{COLOR_RESET}      | {COLOR_SECONDARY}MATCH{COLOR_RESET}",
            f"{COLOR_MUTED}{'-'*65}{COLOR_RESET}",
        ]
        for is_dir, size, path, name in results:
            highlighted_name = re.sub(
                f"({re.escape(query)})",
                f"{COLOR_WARNING}\\1{COLOR_TEXT}",
                name,
                flags=re.IGNORECASE,
            )
            parent = os.path.dirname(path)
            if len(parent) > 50:
                parent = "..." + parent[-47:]
            type_str = f"{COLOR_SECONDARY}[DIR]{COLOR_RESET} " if is_dir else f"{COLOR_PRIMARY}[FILE]{COLOR_RESET}"
            size_str = f"{size:>8}"
            lines.append(f"{type_str} | {COLOR_SUCCESS}{size_str}{COLOR_RESET} | {COLOR_TEXT}{highlighted_name}{COLOR_RESET}")
            lines.append(f"       |          | {COLOR_MUTED}↳ {parent}{COLOR_RESET}")

        lines.append(f"{COLOR_MUTED}{'-'*65}{COLOR_RESET}")
        lines.append(f"{COLOR_PRIMARY}◈ Found {len(results)} matches in {elapsed:.2f}s{COLOR_RESET}\n")
        return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(f"{COLOR_WARNING}[!] No query provided.{COLOR_RESET}")
        return

    query = " ".join(sys.argv[1:])

    # Define start locations: prioritize current dir, then user home
    cwd = os.getcwd()
    user_home = str(Path.home())

    roots_to_search = [cwd]
    if not cwd.startswith(user_home) and cwd != user_home:
        roots_to_search.append(user_home)

    print_header(query, cwd)

    results = []
    start_time = time.time()

    # Execute search
    for root in roots_to_search:
        if len(results) < 50:
            scan_directory(root, query, results, start_time, timeout=15)

    elapsed = time.time() - start_time

    # Sort results: Dirs first, then name
    results.sort(key=lambda x: (not x[0], x[3].lower()))

    # Print results
    for res in results:
        print_result(res[0], res[1], res[2], res[3], query)

    print(f"\n{COLOR_MUTED}{'-'*65}{COLOR_RESET}")
    if len(results) >= 50:
        print(f"{COLOR_WARNING}◈ Found {len(results)}+ matches in {elapsed:.2f}s (Capped at 50){COLOR_RESET}\n")
    else:
        print(f"{COLOR_PRIMARY}◈ Found {len(results)} matches in {elapsed:.2f}s{COLOR_RESET}\n")

if __name__ == "__main__":
    main()

