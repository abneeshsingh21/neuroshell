# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
#!/usr/bin/env python3
"""
NeuroShell CLI — Console Entry Point for VS Code Terminal Integration.

This is the console-mode launcher used by the VS Code extension to run
NeuroShell as an integrated terminal.  Unlike the GUI desktop_app.py
(which is built with console=False), this entry point keeps stdin/stdout
attached so VS Code can display the REPL output.

Usage:
    python neuroshell_cli.py          (development)
    NeuroShell-CLI.exe                (after PyInstaller build with console=True)
"""

import sys
import os

# ── Force UTF-8 on Windows BEFORE any other imports ──────────
# Without this, the default 'charmap' (cp1252) codec crashes on
# emoji and Unicode box-drawing characters used in the banner.
os.environ["PYTHONUTF8"] = "1"
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    """Launch the NeuroShell REPL."""
    try:
        from main import NeuroShell
        shell = NeuroShell()
        shell.run()
    except KeyboardInterrupt:
        print("\n  NeuroShell session ended.")
        sys.exit(0)
    except Exception as e:
        print(f"\n  ❌ NeuroShell failed to start: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
