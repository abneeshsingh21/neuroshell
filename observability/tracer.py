# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Event Tracer
Correlation ID tracing across the full pipeline.
"""

import uuid
import time
from dataclasses import dataclass, field
from typing import Optional
from observability.logger import StructuredLogger


@dataclass
class TraceEvent:
    """A single event in a trace."""
    stage: str
    data: dict
    timestamp: float = field(default_factory=time.time)
    latency_ms: float = 0


@dataclass
class Trace:
    """A complete trace for one user input."""
    correlation_id: str
    start_time: float
    events: list[TraceEvent] = field(default_factory=list)
    completed: bool = False

    @property
    def total_latency_ms(self) -> float:
        return (time.time() - self.start_time) * 1000

    def summary(self) -> str:
        lines = []
        for e in self.events:
            data_str = " ".join(f"{k}={v}" for k, v in e.data.items())
            lines.append(f"[{self.correlation_id[:6]}] {e.stage:<12} {data_str}")
        return "\n".join(lines)


class EventTracer:
    """Manages traces with correlation IDs."""

    def __init__(self, logger: Optional[StructuredLogger] = None):
        self._traces: dict[str, Trace] = {}
        self._recent: list[str] = []  # Last N trace IDs
        self._max_traces = 100
        self._logger = logger or StructuredLogger("tracer")

    def start_trace(self) -> str:
        """Start a new trace. Returns correlation ID."""
        cid = uuid.uuid4().hex[:8]
        trace = Trace(correlation_id=cid, start_time=time.time())
        self._traces[cid] = trace
        self._recent.append(cid)

        # Evict old traces
        while len(self._recent) > self._max_traces:
            old_id = self._recent.pop(0)
            self._traces.pop(old_id, None)

        self._logger.set_correlation_id(cid)
        return cid

    def add_event(self, correlation_id: str, stage: str, **data):
        """Add an event to an existing trace."""
        trace = self._traces.get(correlation_id)
        if not trace:
            return

        latency = (time.time() - trace.start_time) * 1000
        event = TraceEvent(stage=stage, data=data, latency_ms=latency)
        trace.events.append(event)
        self._logger.info(stage, correlation_id=correlation_id, **data)

    def end_trace(self, correlation_id: str):
        """Mark a trace as complete."""
        trace = self._traces.get(correlation_id)
        if trace:
            trace.completed = True

    def get_trace(self, correlation_id: str) -> Optional[Trace]:
        """Get a specific trace."""
        return self._traces.get(correlation_id)

    def get_last_trace(self) -> Optional[Trace]:
        """Get the most recent trace."""
        if self._recent:
            return self._traces.get(self._recent[-1])
        return None

    def get_recent_traces(self, n: int = 10) -> list[Trace]:
        """Get the N most recent traces."""
        ids = self._recent[-n:]
        return [self._traces[cid] for cid in reversed(ids) if cid in self._traces]
