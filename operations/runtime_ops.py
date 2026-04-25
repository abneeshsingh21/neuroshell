# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Runtime monitoring, SLO evaluation, and alerting primitives."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass


@dataclass
class SLOTarget:
    name: str
    objective: float
    window_minutes: int


class RuntimeSLOMonitor:
    """Track SLI samples and evaluate SLO conformance for alerting."""

    def __init__(self):
        self._samples: dict[str, list[tuple[float, float]]] = {}
        self._errors: list[float] = []

    def record_latency_ms(self, operation: str, latency_ms: float, at: float | None = None):
        ts = at if at is not None else time.time()
        self._samples.setdefault(operation, []).append((ts, float(latency_ms)))

    def record_error(self, at: float | None = None):
        ts = at if at is not None else time.time()
        self._errors.append(ts)

    def summarize_latency(self, operation: str, window_minutes: int = 60) -> dict:
        window_start = time.time() - (window_minutes * 60)
        samples = [v for t, v in self._samples.get(operation, []) if t >= window_start]
        if not samples:
            return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "avg_ms": 0.0}

        sorted_samples = sorted(samples)
        idx_95 = max(0, min(len(sorted_samples) - 1, int(len(sorted_samples) * 0.95) - 1))
        return {
            "count": len(samples),
            "p50_ms": float(statistics.median(sorted_samples)),
            "p95_ms": float(sorted_samples[idx_95]),
            "avg_ms": float(statistics.fmean(samples)),
        }

    def error_budget_burn(self, target_availability: float, window_minutes: int = 60) -> dict:
        window_start = time.time() - (window_minutes * 60)
        total_events = 0
        for samples in self._samples.values():
            total_events += sum(1 for t, _ in samples if t >= window_start)

        errors = sum(1 for t in self._errors if t >= window_start)
        availability = 1.0 if total_events == 0 else max(0.0, 1.0 - (errors / total_events))
        budget = 1.0 - target_availability
        consumed = 0.0 if budget <= 0 else max(0.0, (target_availability - availability) / budget)

        return {
            "target": target_availability,
            "availability": availability,
            "errors": errors,
            "events": total_events,
            "budget_consumed_ratio": consumed,
        }

    def evaluate_alerts(self) -> list[dict]:
        alerts = []
        translate = self.summarize_latency("translate", window_minutes=15)
        execute = self.summarize_latency("execute", window_minutes=15)
        burn = self.error_budget_burn(target_availability=0.99, window_minutes=60)

        if translate["count"] >= 20 and translate["p95_ms"] > 1500:
            alerts.append({"severity": "warning", "code": "SLO_LATENCY_TRANSLATE", "message": "Translate p95 above 1500ms"})

        if execute["count"] >= 20 and execute["p95_ms"] > 3000:
            alerts.append({"severity": "warning", "code": "SLO_LATENCY_EXECUTE", "message": "Execute p95 above 3000ms"})

        if burn["budget_consumed_ratio"] > 1.0:
            alerts.append({"severity": "critical", "code": "SLO_BUDGET_EXHAUSTED", "message": "Availability error budget exhausted"})

        return alerts
