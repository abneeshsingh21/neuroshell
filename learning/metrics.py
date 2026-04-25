# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Performance Metrics Tracker
Tracks latency, success rates, and feature usage.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class MetricSnapshot:
    """A metric data point."""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)


class MetricsTracker:
    """Tracks system performance metrics."""

    def __init__(self):
        self._counters: defaultdict = defaultdict(int)
        self._latencies: defaultdict = defaultdict(list)
        self._start_time = time.time()

    def count(self, metric: str, amount: int = 1):
        """Increment a counter."""
        self._counters[metric] += amount

    def record_latency(self, metric: str, ms: float):
        """Record a latency measurement."""
        self._latencies[metric].append(ms)
        # Keep last 1000
        if len(self._latencies[metric]) > 1000:
            self._latencies[metric] = self._latencies[metric][-500:]

    def get_stats(self) -> dict:
        """Get all tracked metrics."""
        uptime = time.time() - self._start_time

        stats = {
            "uptime_s": round(uptime, 1),
            "counters": dict(self._counters),
            "latencies": {},
        }

        for metric, values in self._latencies.items():
            if values:
                stats["latencies"][metric] = {
                    "avg_ms": round(sum(values) / len(values), 1),
                    "min_ms": round(min(values), 1),
                    "max_ms": round(max(values), 1),
                    "count": len(values),
                }

        return stats

    def summary(self) -> str:
        """Human-readable metrics summary."""
        s = self.get_stats()
        parts = [f"Uptime: {s['uptime_s']}s"]

        for name, count in s["counters"].items():
            parts.append(f"{name}: {count}")

        for name, lat in s["latencies"].items():
            parts.append(f"{name}: avg {lat['avg_ms']}ms")

        return " | ".join(parts)
