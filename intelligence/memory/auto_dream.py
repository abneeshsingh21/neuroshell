# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
AutoDream Daemon — Background Memory Consolidation

Monitors system idle time. When the user stops typing, this daemon activates,
reading discarded conversation turns from the SessionMemory queue and using
a fast LLM to summarize and permanently compress them into long-term storage.
This exactly mirrors the `services/autoDream` pattern in Claude Code.
"""

import threading
import time
import json
import os
from pathlib import Path

class AutoDreamDaemon:
    def __init__(self, session_memory, llm_client, magic_docs=None, ui_callback=None):
        self.session = session_memory
        self.llm = llm_client
        self.magic_docs = magic_docs
        self.ui_callback = ui_callback
        self.is_running = False
        self._thread = None
        self.idle_threshold_seconds = 15  # Wait 15s of idle before dreaming
        self.min_queue_size = 3          # Trigger if at least 3 turns in queue
        
        # We need a directory to put long term memory
        self.memory_dir = Path.home() / ".neuroshell" / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.queue_file = self.memory_dir / "dream_queue.jsonl"
        self.long_term_file = self.memory_dir / "long_term.md"

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._dream_loop, daemon=True, name="AutoDream")
        self._thread.start()

    def stop(self):
        self.is_running = False
        
    def _dream_loop(self):
        while self.is_running:
            time.sleep(5) # Tick every 5 seconds
            
            idle_time = self.session.get_idle_time()
            if idle_time < self.idle_threshold_seconds:
                continue
                
            # System is idle! Let's check the queue.
            queue = self._read_queue()
            if len(queue) >= self.min_queue_size:
                if self.ui_callback:
                    self.ui_callback("AutoDream initialized: consolidating memory...")
                self._process_queue(queue)

    def _read_queue(self) -> list:
        if not self.queue_file.exists():
            return []
            
        try:
            with open(self.queue_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return [json.loads(line) for line in lines if line.strip()]
        except Exception:
            return []
            
    def _clear_queue(self):
        try:
            if self.queue_file.exists():
                self.queue_file.write_text("")
        except Exception:
            pass

    def _process_queue(self, queue: list):
        """Pass the queue to the LLM to get a compressed summary fact sheet."""
        
        # Build prompt from turns
        transcript = []
        for i, turn in enumerate(queue):
            role = turn.get("role", "user")
            content = turn.get("content", "")
            transcript.append(f"[{role}]: {content}")
            
        prompt = (
            "You are a background memory daemon. Provide a highly compressed bullet-point "
            "summary of facts, technical details, code structural decisions, or user preferences "
            "mentioned in the following transcript snippet. Omit small talk. Keep it brief.\n\n"
            + "\n".join(transcript)
        )
        
        try:
            # We use process_llm synchronously since we're already in a background thread
            # and want to ensure it completes before clearing queue
            # Note: you should route this to a cheap model explicitly string (e.g. llama3 8b)
            summary = self.llm.generate(prompt, "You are a data compression AI.")
            
            if summary:
                # Append to Long Term Markdown
                with open(self.long_term_file, "a", encoding="utf-8") as f:
                    f.write(f"\n### AutoDream Consolidation - {time.ctime()}\n")
                    f.write(summary.strip() + "\n")
                    
                self._clear_queue()
                
                if self.ui_callback:
                    self.ui_callback("AutoDream active: 🧠 Memory compressed.")
                    
                # Cascade hook into MagicDocs
                if self.magic_docs:
                    if self.ui_callback:
                        self.ui_callback("AutoDream delegating to MagicDocs structural scan...")
                    self.magic_docs.update_magic_doc("\n".join(transcript), ui_callback=self.ui_callback)
                    
        except Exception as e:
            if self.ui_callback:
                self.ui_callback(f"AutoDream warn: Memory synthesis failed - {e}")
