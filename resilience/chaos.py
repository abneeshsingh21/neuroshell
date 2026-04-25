# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Fault injection utilities for chaos and resilience testing."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class ChaosPolicy:
    failure_rate: float = 0.0
    latency_ms_min: int = 0
    latency_ms_max: int = 0


class FaultInjector:
    """Inject probabilistic latency and failures around target operations."""

    def __init__(self, policy: ChaosPolicy | None = None):
        self.policy = policy or ChaosPolicy()

    def should_fail(self) -> bool:
        rate = max(0.0, min(1.0, self.policy.failure_rate))
        return random.random() < rate

    def maybe_delay(self):
        lo = max(0, int(self.policy.latency_ms_min))
        hi = max(lo, int(self.policy.latency_ms_max))
        if hi <= 0:
            return
        delay_ms = random.randint(lo, hi)
        time.sleep(delay_ms / 1000.0)

    def run(self, fn: Callable, *args, **kwargs):
        self.maybe_delay()
        if self.should_fail():
            raise RuntimeError("chaos fault injected")
        return fn(*args, **kwargs)
