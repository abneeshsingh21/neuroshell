# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Event Bus
A lightweight, thread-safe Pub/Sub system for streaming 
backend telemetry (Swarm, Sandbox) directly to the UI.
"""

import threading
from typing import Callable, Dict, List, Any

class EventBus:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EventBus, cls).__new__(cls)
                cls._instance._subscribers = {}
        return cls._instance

    def subscribe(self, event_type: str, callback: Callable[[Any], None]):
        """Subscribe a callback to an event type."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[[Any], None]):
        """Unsubscribe a callback from an event type."""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                except ValueError:
                    pass

    def emit(self, event_type: str, payload: Any = None):
        """Emit an event payload to all subscribers."""
        with self._lock:
            # Copy the list to avoid mutations during iteration
            subs = list(self._subscribers.get(event_type, []))
        
        for callback in subs:
            # We don't try/except here so developer errors bubble up during dev, 
            # though for pure prod we could catch and log.
            callback(payload)

# Global singleton instance
neuro_events = EventBus()
