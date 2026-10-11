"""
NeuroShell Cyber — Reverse Shell Listener & TTY Stabilizer.
Manages reverse shell listeners and provides automated TTY upgrade sequences.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Optional


@dataclass
class ListenerConfig:
    port: int
    tool: str = "nc"
    command: str = ""
    tty_upgrade_notes: list[str] = None


class ListenerManager:
    """
    Reverse shell multi-handler helper and TTY stabilization assistant.
    """

    @classmethod
    def build_listener_command(cls, port: int = 4444, tool: str | None = None) -> ListenerConfig:
        """
        Build the best available listener command based on installed tools (pwncat > rlwrap nc > nc).
        """
        chosen_tool = tool.lower() if tool else None

        if not chosen_tool:
            if shutil.which("pwncat-cs"):
                chosen_tool = "pwncat"
            elif shutil.which("rlwrap") and shutil.which("nc"):
                chosen_tool = "rlwrap"
            elif shutil.which("socat"):
                chosen_tool = "socat"
            else:
                chosen_tool = "nc"

        if chosen_tool == "pwncat":
            cmd = f"pwncat-cs -lp {port}"
        elif chosen_tool == "rlwrap":
            cmd = f"rlwrap nc -lvnp {port}"
        elif chosen_tool == "socat":
            cmd = f"socat file:`tty`,raw,echo=0 tcp-listen:{port}"
        else:
            cmd = f"nc -lvnp {port}"

        # Standard TTY stabilization steps
        tty_steps = [
            '1. Spawn PTY:   python3 -c "import pty; pty.spawn(\'/bin/bash\')"',
            "2. Background:  Press Ctrl + Z",
            "3. Raw Echo:    stty raw -echo; fg",
            "4. Reset TTY:   reset",
            "5. Set Terminal: export TERM=xterm-256color; export SHELL=/bin/bash",
        ]

        return ListenerConfig(
            port=port,
            tool=chosen_tool,
            command=cmd,
            tty_upgrade_notes=tty_steps,
        )

    @classmethod
    def get_pty_spawn_oneliner(cls) -> str:
        """One-liner to spawn full PTY."""
        return 'python3 -c "import pty; pty.spawn(\'/bin/bash\')"'
