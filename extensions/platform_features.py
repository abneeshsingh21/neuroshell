# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Voice Command + Notifications + REST API + Terminal Sharing
Tier 1+4: Voice input, desktop notifications, API server, session sharing.
"""

import os
import json
import time
import logging
import platform
import threading
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable

logger = logging.getLogger("neuroshell.platform")


# ═══════════════════════════════════════════════════════════
# Voice Command Mode
# ═══════════════════════════════════════════════════════════

class VoiceCommandEngine:
    """
    Tier 1: Speak commands instead of typing.
    Uses speech_recognition library with multiple backend support.
    """

    def __init__(self):
        self._recognizer = None
        self._microphone = None
        self._available = False
        self._init_engine()

    def _init_engine(self):
        try:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            self._microphone = sr.Microphone
            self._available = True
            logger.info("Voice engine initialized (speech_recognition)")
        except ImportError:
            logger.info("Voice engine unavailable — install: pip install SpeechRecognition pyaudio")

    @property
    def available(self) -> bool:
        return self._available

    def listen(self, timeout: int = 5, phrase_time_limit: int = 10) -> Optional[str]:
        """Listen for voice input and return transcribed text."""
        if not self._available:
            return None
        import speech_recognition as sr
        try:
            with self._microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                logger.info("Listening...")
                audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)

            # Try Google Speech Recognition (free, no API key)
            text = self._recognizer.recognize_google(audio)
            logger.info("Voice recognized: %s", text)
            return text.strip()

        except Exception as e:
            logger.warning("Voice recognition failed: %s", e)
            return None

    def listen_with_whisper(self, timeout: int = 5) -> Optional[str]:
        """Use OpenAI Whisper for offline recognition (higher accuracy)."""
        if not self._available:
            return None
        import speech_recognition as sr
        try:
            with self._microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self._recognizer.listen(source, timeout=timeout)
            text = self._recognizer.recognize_whisper(audio, model="base", language="english")
            return text.strip()
        except Exception as e:
            logger.warning("Whisper recognition failed: %s", e)
            return None

    @staticmethod
    def install_hint() -> str:
        return "pip install SpeechRecognition pyaudio openai-whisper"


# ═══════════════════════════════════════════════════════════
# Smart Desktop Notifications
# ═══════════════════════════════════════════════════════════

class SmartNotifications:
    """Tier 2 Desktop App: Send desktop notifications for long-running commands."""

    def __init__(self):
        self._system = platform.system()
        self._threshold_ms = 5000  # Notify if command takes > 5s

    def notify(self, title: str, message: str, urgency: str = "normal"):
        """Send cross-platform desktop notification."""
        try:
            if self._system == "Windows":
                self._notify_windows(title, message)
            elif self._system == "Darwin":
                self._notify_macos(title, message)
            else:
                self._notify_linux(title, message, urgency)
        except Exception as e:
            logger.debug("Notification failed: %s", e)

    def _notify_windows(self, title: str, message: str):
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, message, duration=5, threaded=True)
        except ImportError:
            # PowerShell fallback
            ps = f'''
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $template.GetElementsByTagName("text")[0].AppendChild($template.CreateTextNode("{title}")) | Out-Null
            $template.GetElementsByTagName("text")[1].AppendChild($template.CreateTextNode("{message}")) | Out-Null
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("NeuroShell").Show($template)
            '''
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps], creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)

    def _notify_macos(self, title: str, message: str):
        subprocess.Popen(["osascript", "-e", f'display notification "{message}" with title "{title}"'])

    def _notify_linux(self, title: str, message: str, urgency: str = "normal"):
        subprocess.Popen(["notify-send", f"--urgency={urgency}", title, message])

    def should_notify(self, duration_ms: float) -> bool:
        return duration_ms >= self._threshold_ms

    def on_command_complete(self, command: str, exit_code: int, duration_ms: float):
        """Auto-notify when long-running command finishes."""
        if not self.should_notify(duration_ms):
            return
        if exit_code == 0:
            self.notify("NeuroShell ✅", f"Command completed: {command[:50]}...")
        else:
            self.notify("NeuroShell ❌", f"Command failed (exit {exit_code}): {command[:50]}...")


# ═══════════════════════════════════════════════════════════
# REST API Mode
# ═══════════════════════════════════════════════════════════

class NeuroShellAPI:
    """
    Tier 4: Expose NeuroShell as a REST API.
    Other tools send English → get commands back.
    """

    def __init__(self, translator=None, host: str = "127.0.0.1", port: int = 9876):
        self.translator = translator
        self.host = host
        self.port = port
        self._server_thread = None

    def start(self):
        """Start API server in background thread."""
        try:
            from http.server import HTTPServer, BaseHTTPRequestHandler
            import json as _json

            translator = self.translator

            class Handler(BaseHTTPRequestHandler):
                def do_POST(self):
                    if self.path == "/translate":
                        length = int(self.headers.get("Content-Length", 0))
                        body = _json.loads(self.rfile.read(length)) if length else {}
                        query = body.get("query", "")
                        if not query:
                            self._respond(400, {"error": "Missing 'query' field"})
                            return
                        try:
                            result = translator.translate(query)
                            self._respond(200, {"command": result.command, "confidence": result.confidence, "provenance": str(getattr(result.provenance, 'source', 'unknown'))})
                        except Exception as e:
                            self._respond(500, {"error": str(e)})
                    elif self.path == "/health":
                        self._respond(200, {"status": "ok", "version": "5.1.3"})
                    else:
                        self._respond(404, {"error": "Not found"})

                def do_GET(self):
                    if self.path == "/health":
                        self._respond(200, {"status": "ok", "version": "5.1.3"})
                    else:
                        self._respond(404, {"error": "Not found. POST to /translate with {\"query\": \"your command\"}"})

                def _respond(self, code, data):
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(_json.dumps(data).encode())

                def log_message(self, format, *args):
                    logger.debug("API: %s", format % args)

            server = HTTPServer((self.host, self.port), Handler)
            self._server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            self._server_thread.start()
            logger.info("NeuroShell API running on http://%s:%d", self.host, self.port)
            return True
        except Exception as e:
            logger.error("API server failed: %s", e)
            return False

    @staticmethod
    def usage_hint() -> str:
        return 'curl -X POST http://127.0.0.1:9876/translate -H "Content-Type: application/json" -d \'{"query": "list all files"}\''


# ═══════════════════════════════════════════════════════════
# Multi-Machine Sync
# ═══════════════════════════════════════════════════════════

class MachineSync:
    """Tier 2: Sync aliases, patterns, corrections across machines via file export."""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path.home() / ".neuroshell"

    def export_config(self, output_path: Optional[Path] = None) -> Path:
        """Export all learnable config to a single JSON file."""
        export = {"exported_at": time.time(), "machine": platform.node(), "data": {}}

        sync_files = ["corrections.json", "aliases.json", "memory/session_memory.json", "snippets.json"]
        for f in sync_files:
            fpath = self.config_dir / f
            if fpath.exists():
                try:
                    export["data"][f] = json.loads(fpath.read_text(encoding="utf-8"))
                except Exception:
                    pass

        out = output_path or self.config_dir / "neuroshell_sync.json"
        out.write_text(json.dumps(export, indent=2), encoding="utf-8")
        return out

    def import_config(self, sync_path: Path) -> dict:
        """Import config from sync file, merging with local."""
        try:
            data = json.loads(sync_path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"error": str(e)}

        imported = {}
        for filename, content in data.get("data", {}).items():
            target = self.config_dir / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                try:
                    local = json.loads(target.read_text(encoding="utf-8"))
                    if isinstance(local, dict) and isinstance(content, dict):
                        local.update(content)
                        content = local
                except Exception:
                    pass
            target.write_text(json.dumps(content, indent=2), encoding="utf-8")
            imported[filename] = "merged" if target.exists() else "created"

        return {"imported": imported, "from_machine": data.get("machine", "unknown")}
