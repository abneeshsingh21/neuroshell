# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Session Recorder
Records terminal sessions to shareable replay files.
"""

import gzip
import json
import time
from dataclasses import dataclass, field

from config import NEUROSHELL_DIR

RECORDINGS_DIR = NEUROSHELL_DIR / "recordings"


@dataclass
class RecordingEvent:
    """A single event in a recording."""
    timestamp: float
    event_type: str  # input, output, info, error, translation, fix
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class SessionRecording:
    """A complete session recording."""
    session_id: str
    start_time: float
    events: list[RecordingEvent] = field(default_factory=list)
    end_time: float = 0
    description: str = ""

    @property
    def duration_s(self) -> float:
        end = self.end_time or time.time()
        return round(end - self.start_time, 1)

    @property
    def command_count(self) -> int:
        return sum(1 for e in self.events if e.event_type == "input")

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "description": self.description,
            "duration_s": self.duration_s,
            "command_count": self.command_count,
            "events": [
                {
                    "ts": round(e.timestamp - self.start_time, 3),
                    "type": e.event_type,
                    "content": e.content,
                    "meta": e.metadata,
                }
                for e in self.events
            ],
        }


class SessionRecorder:
    """Records and replays terminal sessions."""

    def __init__(self):
        self._active: SessionRecording | None = None
        self._recording = False
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self, session_id: str, description: str = "") -> bool:
        """Start recording a session."""
        if self._recording:
            return False

        self._active = SessionRecording(
            session_id=session_id,
            start_time=time.time(),
            description=description,
        )
        self._recording = True
        return True

    def stop(self) -> str | None:
        """Stop recording and save. Returns file path."""
        if not self._recording or not self._active:
            return None

        self._active.end_time = time.time()
        self._recording = False

        # Save to compressed JSON
        file_path = self._save(self._active)
        self._active = None
        return file_path

    def record_event(self, event_type: str, content: str, **metadata):
        """Record an event during active recording."""
        if not self._recording or not self._active:
            return

        event = RecordingEvent(
            timestamp=time.time(),
            event_type=event_type,
            content=content,
            metadata=metadata,
        )
        self._active.events.append(event)

    def record_input(self, command: str):
        self.record_event("input", command)

    def record_output(self, output: str, exit_code: int = 0):
        self.record_event("output", output[:2000], exit_code=exit_code)

    def record_translation(self, nl_input: str, command: str, confidence: float):
        self.record_event("translation", command, nl_input=nl_input, confidence=confidence)

    def record_fix(self, error: str, fix_command: str):
        self.record_event("fix", fix_command, error=error[:200])

    def list_recordings(self) -> list[dict]:
        """List all saved recordings."""
        recordings = []
        for file in sorted(RECORDINGS_DIR.glob("*.json.gz"), reverse=True):
            try:
                data = json.loads(gzip.decompress(file.read_bytes()).decode("utf-8"))
                recordings.append({
                    "file": file.name,
                    "session_id": data.get("session_id", ""),
                    "description": data.get("description", ""),
                    "duration_s": data.get("duration_s", 0),
                    "commands": data.get("command_count", 0),
                })
            except Exception:
                pass
        return recordings[:20]

    def load_recording(self, filename: str) -> dict | None:
        """Load a recorded session."""
        file = RECORDINGS_DIR / filename
        if not file.exists():
            return None

        try:
            data = json.loads(gzip.decompress(file.read_bytes()).decode("utf-8"))
            return data
        except Exception:
            return None

    def replay_text(self, filename: str) -> str | None:
        """Get human-readable text replay of a session."""
        data = self.load_recording(filename)
        if not data:
            return None

        lines = [
            f"Session: {data.get('session_id', '')}",
            f"Duration: {data.get('duration_s', 0)}s",
            f"Commands: {data.get('command_count', 0)}",
            "─" * 50,
        ]

        for event in data.get("events", []):
            ts = event.get("ts", 0)
            etype = event.get("type", "")
            content = event.get("content", "")

            if etype == "input":
                lines.append(f"\n[{ts:.1f}s] ❯ {content}")
            elif etype == "output":
                lines.append(f"  {content[:200]}")
            elif etype == "translation":
                nl = event.get("meta", {}).get("nl_input", "")
                lines.append(f"  🧠 '{nl}' → {content}")
            elif etype == "fix":
                lines.append(f"  🔧 Fix: {content}")

        return "\n".join(lines)

    def _save(self, recording: SessionRecording) -> str:
        """Save recording to compressed JSON."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = f"session_{recording.session_id}_{ts}.json.gz"
        file_path = RECORDINGS_DIR / filename

        data = json.dumps(recording.to_dict(), indent=2)
        file_path.write_bytes(gzip.compress(data.encode("utf-8")))

        return str(file_path)
