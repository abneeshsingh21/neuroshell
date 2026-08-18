# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Command Timer
Precise execution timing and session performance statistics.
"""

import time
from dataclasses import dataclass


@dataclass
class TimingResult:
    """Result of a timed command execution."""
    command: str
    wall_time_ms: float
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""

    @property
    def wall_time_display(self) -> str:
        """Human-readable wall time."""
        ms = self.wall_time_ms
        if ms < 1000:
            return f"{ms:.0f}ms"
        elif ms < 60_000:
            return f"{ms / 1000:.2f}s"
        else:
            minutes = int(ms // 60_000)
            seconds = (ms % 60_000) / 1000
            return f"{minutes}m {seconds:.1f}s"

    def display(self) -> str:
        status = "✅" if self.exit_code == 0 else "❌"
        return f"\n⏱️  {status} {self.command}\n   Wall time: {self.wall_time_display}"


class CommandTimer:
    """
    Wraps shell execution with precise timing.

    Features:
    - Precise wall-clock timing for any command
    - Session-level statistics (total time, avg, fastest, slowest)
    - History of timed commands
    """

    def __init__(self, executor=None):
        self.executor = executor
        self._timed_results: list[TimingResult] = []
        self._session_start = time.time()
        self._total_commands = 0
        self._total_errors = 0
        self._total_time_ms = 0

    def time_command(self, command: str) -> TimingResult:
        """Execute a command and return timing result."""
        start = time.perf_counter()

        if self.executor:
            result = self.executor.execute(command)
            elapsed_ms = (time.perf_counter() - start) * 1000

            timing = TimingResult(
                command=command,
                wall_time_ms=round(elapsed_ms, 2),
                exit_code=result.exit_code if result else 1,
                stdout=result.stdout[:500] if result else "",
                stderr=result.stderr[:500] if result else "",
            )
        else:
            elapsed_ms = (time.perf_counter() - start) * 1000
            timing = TimingResult(
                command=command,
                wall_time_ms=round(elapsed_ms, 2),
            )

        self._timed_results.append(timing)
        self._total_commands += 1
        self._total_time_ms += timing.wall_time_ms
        if timing.exit_code != 0:
            self._total_errors += 1

        return timing

    def record_execution(self, command: str, duration_ms: float, exit_code: int = 0):
        """Record a command execution without timing it (already executed)."""
        self._total_commands += 1
        self._total_time_ms += duration_ms
        if exit_code != 0:
            self._total_errors += 1

    def get_session_stats(self) -> dict:
        """Get comprehensive session statistics."""
        uptime = time.time() - self._session_start

        stats = {
            "uptime_s": round(uptime, 1),
            "uptime_display": self._format_duration(uptime),
            "total_commands": self._total_commands,
            "total_errors": self._total_errors,
            "success_rate": round(
                (self._total_commands - self._total_errors) / max(self._total_commands, 1) * 100, 1
            ),
            "total_time_ms": round(self._total_time_ms, 1),
            "avg_time_ms": round(
                self._total_time_ms / max(self._total_commands, 1), 1
            ),
        }

        if self._timed_results:
            times = [t.wall_time_ms for t in self._timed_results]
            stats["timed_commands"] = len(self._timed_results)
            stats["fastest_ms"] = round(min(times), 1)
            stats["slowest_ms"] = round(max(times), 1)
            stats["fastest_cmd"] = min(self._timed_results, key=lambda t: t.wall_time_ms).command
            stats["slowest_cmd"] = max(self._timed_results, key=lambda t: t.wall_time_ms).command

        return stats

    def get_formatted_stats(self, metrics_tracker=None) -> str:
        """Get formatted session statistics display."""
        s = self.get_session_stats()

        lines = [
            "\n📊 Session Statistics:\n",
            f"  ⏰ Uptime:         {s['uptime_display']}",
            f"  📝 Commands:       {s['total_commands']}",
            f"  ✅ Success rate:   {s['success_rate']}%",
            f"  ⚡ Avg latency:    {s['avg_time_ms']}ms",
        ]

        if "timed_commands" in s:
            lines.extend([
                f"\n  ⏱️  Timed Commands ({s['timed_commands']}):",
                f"     Fastest: {s['fastest_ms']}ms — {s['fastest_cmd'][:40]}",
                f"     Slowest: {s['slowest_ms']}ms — {s['slowest_cmd'][:40]}",
            ])

        if s["total_errors"] > 0:
            lines.append(f"  ❌ Errors:         {s['total_errors']}")

        # Include metrics tracker data if available
        if metrics_tracker:
            metrics = metrics_tracker.get_stats()
            for name, count in metrics.get("counters", {}).items():
                lines.append(f"  📈 {name}: {count}")
            for name, lat in metrics.get("latencies", {}).items():
                lines.append(f"  ⏱️  {name}: avg {lat['avg_ms']}ms")

        return "\n".join(lines)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format seconds into human-readable duration."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            m = int(seconds // 60)
            s = int(seconds % 60)
            return f"{m}m {s}s"
        else:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            return f"{h}h {m}m"
