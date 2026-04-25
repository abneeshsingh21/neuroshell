# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Whisper Bridge
Routes WAV data to STT models like Groq's Whisper API for near-instant transcription.
"""

import httpx
import os

class WhisperBridge:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.url = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe_audio(self, wav_path: str) -> str:
        """Sends the audio file to Groq Whisper for transcription."""
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is required for voice transcription.")
            
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        async with httpx.AsyncClient() as client:
            with open(wav_path, "rb") as audio_file:
                files = {
                    "file": ("audio.wav", audio_file, "audio/wav")
                }
                data = {
                    "model": "whisper-large-v3",
                    "response_format": "text"
                }
                
                resp = await client.post(self.url, headers=headers, files=files, data=data, timeout=10.0)
                resp.raise_for_status()
                return resp.text.strip()
