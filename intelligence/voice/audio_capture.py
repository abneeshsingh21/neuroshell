# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Audio Capture
Records microphone buffers natively using OS commands like sox or sounddevice.
"""

import subprocess
import threading
import wave
import os

class AudioCapture:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.process = None
        self.is_recording = False
        self._buffer = bytearray()
        self._lock = threading.Lock()

    def start_recording(self):
        """Starts recording audio from default mic using SoX/rec."""
        if self.is_recording:
            return
            
        self.is_recording = True
        self._buffer.clear()
        
        args = [
            'rec', '-q', '-t', 'raw', '-r', str(self.sample_rate),
            '-e', 'signed', '-b', '16', '-c', '1', '-'
        ]
        
        try:
            import sys
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            self.process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **kwargs)
            threading.Thread(target=self._read_loop, daemon=True).start()
        except FileNotFoundError:
            self.is_recording = False
            raise RuntimeError("SoX (rec) not installed. Please install SoX to enable voice input.")

    def _read_loop(self):
        try:
            while self.is_recording and self.process:
                chunk = self.process.stdout.read(1024)
                if not chunk:
                    break
                with self._lock:
                    self._buffer.extend(chunk)
        except Exception:
            pass

    def stop_recording(self) -> bytes:
        """Stops recording and returns the raw PCM data."""
        self.is_recording = False
        if self.process:
            self.process.terminate()
            self.process = None
            
        with self._lock:
            data = bytes(self._buffer)
            
        return data

    def save_wav(self, pcm_data: bytes, path: str):
        """Helper to dump PCM buffer into a WAV file for STT APIs."""
        with wave.open(path, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm_data)
