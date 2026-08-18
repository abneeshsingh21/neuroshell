# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Structured Logger — Production Grade
Performance tracing, structured errors, log sampling, console handler.
"""

import contextvars
import functools
import json
import logging
import os
import random
import sys
import time
import traceback
from collections.abc import Callable
from logging.handlers import RotatingFileHandler

from config import LOG_DIR

_CORRELATION_VAR: contextvars.ContextVar[str | None] = contextvars.ContextVar("neuroshell_correlation_id", default=None)


class SafeRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler resilient against Windows file locking errors (WinError 32)."""
    def doRollover(self):
        try:
            super().doRollover()
        except (PermissionError, OSError):
            # On Windows, if another process or thread holds the log file open, ignore rollover failure
            pass


class StructuredLogger:
    """
    Production-grade structured logger.

    Features:
    - JSON-structured log entries
    - Performance tracing via @trace decorator
    - Structured error context with stack traces
    - Log sampling for verbose debug logs
    - Optional stderr console handler for debug mode
    - Correlation IDs for request tracing (ContextVar-backed)
    - Log level filtering per component
    """

    _instances: dict[str, "StructuredLogger"] = {}

    def __init__(self, component: str, log_level: str = "INFO", console: bool = False, sample_rate: float = 1.0):
        self.component = component
        self._sample_rate = max(0.0, min(1.0, sample_rate))  # 0.0 = no logs, 1.0 = all logs
        self._perf_traces: list[dict] = []

        LOG_DIR.mkdir(parents=True, exist_ok=True)

        self._logger = logging.getLogger(f"neuroshell.{component}")
        self._logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        self._logger.propagate = False

        if not self._logger.handlers:
            # File handler with safe rotation (10MB, keep 5)
            fh = SafeRotatingFileHandler(
                LOG_DIR / "neuroshell.log",
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            fh.setFormatter(JsonFormatter(component))
            self._logger.addHandler(fh)

            # Console handler for debug mode
            if console or os.environ.get("NEUROSHELL_DEBUG"):
                ch = logging.StreamHandler(sys.stderr)
                ch.setLevel(logging.DEBUG)
                ch.setFormatter(ConsoleFormatter(component))
                self._logger.addHandler(ch)

        StructuredLogger._instances[component] = self

    @classmethod
    def get(cls, component: str) -> "StructuredLogger":
        """Get or create a logger instance."""
        if component in cls._instances:
            return cls._instances[component]
        return cls(component)

    def set_correlation_id(self, cid: str):
        _CORRELATION_VAR.set(cid)

    @property
    def correlation_id(self) -> str | None:
        return _CORRELATION_VAR.get()

    def debug(self, event: str, **data):
        if self._should_sample():
            self._log("DEBUG", event, data)

    def info(self, event: str, **data):
        self._log("INFO", event, data)

    def warn(self, event: str, **data):
        self._log("WARNING", event, data)

    def error(self, event: str, **data):
        self._log("ERROR", event, data)

    def critical(self, event: str, **data):
        self._log("CRITICAL", event, data)

    def exception(self, event: str, exc: Exception | None = None, **data):
        """Log error with full structured exception context."""
        if exc:
            data["exception_type"] = type(exc).__name__
            data["exception_msg"] = str(exc)
            data["traceback"] = traceback.format_exception(type(exc), exc, exc.__traceback__)
            # Capture local variables from the innermost frame
            tb = exc.__traceback__
            if tb:
                while tb.tb_next:
                    tb = tb.tb_next
                frame_locals = {k: repr(v)[:200] for k, v in tb.tb_frame.f_locals.items()
                                if not k.startswith("_")}
                data["frame_locals"] = frame_locals
        self._log("ERROR", event, data)

    def trace(self, func: Callable | None = None, *, name: str = ""):
        """Decorator for automatic performance tracing."""
        def decorator(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                fn_name = name or f"{fn.__module__}.{fn.__qualname__}"
                start = time.perf_counter()
                try:
                    result = fn(*args, **kwargs)
                    elapsed = (time.perf_counter() - start) * 1000
                    self._record_trace(fn_name, elapsed, success=True)
                    return result
                except Exception as e:
                    elapsed = (time.perf_counter() - start) * 1000
                    self._record_trace(fn_name, elapsed, success=False, error=str(e))
                    raise
            return wrapper

        if func is not None:
            return decorator(func)
        return decorator

    def get_perf_stats(self) -> dict:
        """Get performance statistics from traced functions."""
        if not self._perf_traces:
            return {"total_traces": 0}

        stats = {}
        for trace in self._perf_traces[-100:]:  # Last 100 traces
            name = trace["name"]
            if name not in stats:
                stats[name] = {"count": 0, "total_ms": 0, "errors": 0, "min_ms": float("inf"), "max_ms": 0}
            s = stats[name]
            s["count"] += 1
            s["total_ms"] += trace["elapsed_ms"]
            s["min_ms"] = min(s["min_ms"], trace["elapsed_ms"])
            s["max_ms"] = max(s["max_ms"], trace["elapsed_ms"])
            if not trace["success"]:
                s["errors"] += 1

        for s in stats.values():
            s["avg_ms"] = round(s["total_ms"] / s["count"], 2)
            s["total_ms"] = round(s["total_ms"], 2)
            s["min_ms"] = round(s["min_ms"], 2) if s["min_ms"] != float("inf") else 0
            s["max_ms"] = round(s["max_ms"], 2)

        return {"total_traces": len(self._perf_traces), "functions": stats}

    # ── Internal ──

    def _log(self, level: str, event: str, data: dict):
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "level": level,
            "component": self.component,
            "event": event,
        }
        cid = self.correlation_id
        if cid:
            record["cid"] = cid
        if data:
            record["data"] = data

        log_method = getattr(self._logger, level.lower(), self._logger.info)
        log_method(json.dumps(record, default=str))

    def _should_sample(self) -> bool:
        return self._sample_rate >= 1.0 or random.random() < self._sample_rate

    def _record_trace(self, name: str, elapsed_ms: float, success: bool, error: str = ""):
        trace = {"name": name, "elapsed_ms": round(elapsed_ms, 2), "success": success, "ts": time.time()}
        if error:
            trace["error"] = error
        self._perf_traces.append(trace)

        # Log slow operations
        if elapsed_ms > 1000:
            self.warn("slow_operation", name=name, elapsed_ms=round(elapsed_ms, 2))

        # Keep bounded
        if len(self._perf_traces) > 500:
            self._perf_traces = self._perf_traces[-200:]


class JsonFormatter(logging.Formatter):
    """JSON pass-through formatter."""
    def __init__(self, component: str):
        super().__init__()
        self.component = component

    def format(self, record):
        return record.getMessage()


class ConsoleFormatter(logging.Formatter):
    """Colored console formatter for debug mode."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, component: str):
        super().__init__()
        self.component = component

    def format(self, record):
        color = self.COLORS.get(record.levelname, "")
        try:
            data = json.loads(record.getMessage())
            event = data.get("event", "")
            return f"{color}[{record.levelname[0]}]{self.RESET} [{self.component}] {event}"
        except (json.JSONDecodeError, AttributeError):
            return f"{color}[{record.levelname[0]}]{self.RESET} [{self.component}] {record.getMessage()}"
