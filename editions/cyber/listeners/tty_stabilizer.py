"""
NeuroShell Cyber — TTY Stabilizer module.
Provides automated TTY / PTY interactive terminal upgrade sequences for reverse shells.
"""

from __future__ import annotations

from editions.cyber.listeners.listener_daemon import ListenerManager


class TTYStabilizer:
    """Automates reverse shell TTY stabilization sequences."""

    @staticmethod
    def get_python_pty_sequence() -> list[str]:
        """Step-by-step sequence for upgrading a dumb netcat shell to full PTY."""
        return ListenerManager.tty_upgrade_sequence()

    @staticmethod
    def get_script_upgrade_sequence() -> str:
        """Script utility upgrade for systems without Python."""
        return "/usr/bin/script -qc /bin/bash /dev/null"

    @staticmethod
    def get_socat_stabilized_listener(port: int = 4444) -> str:
        """Generate socat listener command with raw PTY allocation."""
        return f"socat file:`tty`,raw,echo=0 tcp-listen:{port}"
