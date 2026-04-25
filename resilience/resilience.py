# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Resilience Layer — Production Grade
Circuit breaker, rate limiting, crash recovery, graceful degradation,
and comprehensive health checks with retry policies.
"""

import socket
import time
import platform
import shutil
import os
import json
import logging
import threading
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

_resilience_log = logging.getLogger("neuroshell.resilience")


# ═══════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════

@dataclass
class HealthStatus:
    """Component health status."""
    component: str
    healthy: bool
    message: str = ""
    latency_ms: float = 0
    details: dict = field(default_factory=dict)


@dataclass
class HealthReport:
    """Full system health report."""
    timestamp: float = field(default_factory=time.time)
    checks: list[HealthStatus] = field(default_factory=list)
    overall_healthy: bool = True
    degraded_features: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = []
        for check in self.checks:
            icon = "✅" if check.healthy else "❌"
            lines.append(f"  {icon} {check.component}: {check.message}")
        if self.degraded_features:
            lines.append(f"\n  ⚠️ Degraded: {', '.join(self.degraded_features)}")
        return "\n".join(lines)

    @property
    def healthy_count(self) -> int:
        return sum(1 for c in self.checks if c.healthy)

    @property
    def total_count(self) -> int:
        return len(self.checks)


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failures exceeded threshold, blocking calls
    HALF_OPEN = "half_open" # Testing if service recovered


# ═══════════════════════════════════════════════════════════
# Circuit Breaker
# ═══════════════════════════════════════════════════════════

class CircuitBreaker:
    """
    Circuit breaker pattern for external service calls.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests are blocked
    - HALF_OPEN: Testing recovery, one request allowed
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
            return self._state

    def call(self, func: Callable, *args, **kwargs):
        """Execute a function through the circuit breaker."""
        state = self.state

        if state == CircuitState.OPEN:
            raise CircuitOpenError(f"Circuit '{self.name}' is OPEN — service unavailable")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED

    def _on_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN

    def reset(self):
        """Manually reset the circuit breaker."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0

    @property
    def status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
        }


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


# ═══════════════════════════════════════════════════════════
# Rate Limiter
# ═══════════════════════════════════════════════════════════

class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, max_calls: int = 60, period_seconds: float = 60.0):
        self.max_calls = max_calls
        self.period = period_seconds
        self._calls: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        """Try to acquire a rate limit token. Returns True if allowed."""
        now = time.time()
        with self._lock:
            # Remove expired calls
            self._calls = [t for t in self._calls if now - t < self.period]

            if len(self._calls) < self.max_calls:
                self._calls.append(now)
                return True
            return False

    def wait_and_acquire(self, timeout: float = 10.0) -> bool:
        """Wait up to timeout seconds for a rate limit token."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.acquire():
                return True
            time.sleep(0.1)
        return False

    @property
    def remaining(self) -> int:
        now = time.time()
        with self._lock:
            active = sum(1 for t in self._calls if now - t < self.period)
        return max(0, self.max_calls - active)

    @property
    def stats(self) -> dict:
        return {
            "max_calls": self.max_calls,
            "period_seconds": self.period,
            "remaining": self.remaining,
            "current_usage": len(self._calls),
        }


# ═══════════════════════════════════════════════════════════
# Crash Recovery
# ═══════════════════════════════════════════════════════════

class CrashRecovery:
    """
    Manages session state persistence for crash recovery.

    Saves session state periodically so that after a crash,
    the user can resume from the last checkpoint.
    """

    def __init__(self, sessions_dir: Path = None):
        from config import SESSIONS_DIR
        self.sessions_dir = sessions_dir or SESSIONS_DIR
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self.sessions_dir / "last_state.json"

    def save_state(self, state: dict):
        """Save current session state for recovery."""
        state["_saved_at"] = time.time()
        state["_pid"] = os.getpid()
        try:
            self._state_file.write_text(json.dumps(state, default=str), encoding="utf-8")
        except Exception as exc:
            _resilience_log.warning("Failed to save session state: %s", exc)

    def recover_state(self) -> Optional[dict]:
        """Try to recover state from last session."""
        if not self._state_file.exists():
            return None
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            return data
        except Exception as exc:
            _resilience_log.warning("Failed to recover session state: %s", exc)
            return None

    def clear_state(self):
        """Clear saved state (clean shutdown)."""
        try:
            if self._state_file.exists():
                self._state_file.unlink()
        except Exception as exc:
            _resilience_log.warning("Failed to clear session state: %s", exc)

    def has_recovery_data(self) -> bool:
        """Check if there's crash recovery data available."""
        return self._state_file.exists()


# ═══════════════════════════════════════════════════════════
# Network Awareness
# ═══════════════════════════════════════════════════════════

class NetworkAware:
    """Detects connectivity and warns before net-dependent commands."""

    NET_COMMANDS = {
        "pip install", "npm install", "apt install", "brew install",
        "yum install", "dnf install", "pacman -S",
        "git clone", "git push", "git pull", "git fetch",
        "curl", "wget", "ssh", "scp", "rsync",
        "docker pull", "docker push",
        "pip download", "npm publish",
        "kubectl apply", "helm install", "terraform apply",
        "aws ", "az ", "gcloud ",
    }

    def __init__(self):
        self._is_online = False
        self._last_check = 0
        self._dns_working = False

    def check(self) -> bool:
        """Check network status (cached 30s)."""
        if time.time() - self._last_check < 30:
            return self._is_online

        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3).close()
            self._is_online = True
        except (socket.timeout, OSError):
            self._is_online = False

        # DNS check
        try:
            socket.getaddrinfo("google.com", 443, type=socket.SOCK_STREAM)
            self._dns_working = True
        except socket.gaierror:
            self._dns_working = False

        self._last_check = time.time()
        return self._is_online

    def needs_network(self, command: str) -> bool:
        """Check if command needs network."""
        cmd_lower = command.strip().lower()
        return any(cmd_lower.startswith(net_cmd) for net_cmd in self.NET_COMMANDS)

    def warn_if_offline(self, command: str) -> Optional[str]:
        """Return warning if offline and command needs network."""
        if self.needs_network(command) and not self.check():
            return f"⚠️ '{command.split()[0]}' requires network — you appear to be offline"
        return None

    @property
    def status(self) -> dict:
        return {
            "online": self._is_online,
            "dns_working": self._dns_working,
            "last_check": self._last_check,
        }


# ═══════════════════════════════════════════════════════════
# Health Check System
# ═══════════════════════════════════════════════════════════

class HealthCheck:
    """Comprehensive startup health check panel."""

    def __init__(self, config):
        self.config = config

    def run_all(self) -> HealthReport:
        """Run all health checks."""
        report = HealthReport()

        report.checks.append(self._check_python())
        report.checks.append(self._check_shell())
        report.checks.append(self._check_sqlite())
        report.checks.append(self._check_network())
        report.checks.append(self._check_ollama())
        report.checks.append(self._check_disk())
        report.checks.append(self._check_memory())
        report.checks.append(self._check_dependencies())
        report.checks.append(self._check_config_dir())

        report.overall_healthy = all(c.healthy for c in report.checks
                                     if c.component not in ("Network", "Ollama LLM"))
        return report

    def _check_python(self) -> HealthStatus:
        import sys
        return HealthStatus(
            component="Python",
            healthy=sys.version_info >= (3, 10),
            message=f"v{platform.python_version()}",
            details={"version": platform.python_version()},
        )

    def _check_shell(self) -> HealthStatus:
        shell = self.config.default_shell
        found = shutil.which(shell) or shutil.which("cmd")
        return HealthStatus(
            component="Shell",
            healthy=bool(found),
            message=f"{shell} {'available' if found else 'NOT FOUND'}",
        )

    def _check_sqlite(self) -> HealthStatus:
        try:
            import sqlite3
            with sqlite3.connect(":memory:") as conn:
                version = conn.execute("SELECT sqlite_version()").fetchone()[0]
            return HealthStatus(component="SQLite", healthy=True, message=f"v{version}")
        except Exception as e:
            return HealthStatus(component="SQLite", healthy=False, message=str(e))

    def _check_network(self) -> HealthStatus:
        na = NetworkAware()
        online = na.check()
        return HealthStatus(
            component="Network",
            healthy=True,
            message="online" if online else "offline (degraded mode)",
            details=na.status,
        )

    def _check_ollama(self) -> HealthStatus:
        start = time.time()
        try:
            import ollama
            models = ollama.list()
            latency = (time.time() - start) * 1000
            model_names = [m.get("name", "") for m in models.get("models", [])]
            has_model = any(self.config.llm.model in n for n in model_names)
            return HealthStatus(
                component="Ollama LLM",
                healthy=True,
                message=f"{'model loaded' if has_model else 'running, model not found'}",
                latency_ms=round(latency, 1),
                details={"models": model_names[:5], "has_model": has_model},
            )
        except Exception:
            return HealthStatus(
                component="Ollama LLM",
                healthy=False,
                message="not running (AI features limited)",
            )

    def _check_disk(self) -> HealthStatus:
        try:
            usage = shutil.disk_usage(os.getcwd())
            free_gb = round(usage.free / (1024**3), 1)
            total_gb = round(usage.total / (1024**3), 1)
            return HealthStatus(
                component="Disk Space",
                healthy=free_gb > 1,
                message=f"{free_gb} GB free / {total_gb} GB total",
                details={"free_gb": free_gb, "total_gb": total_gb},
            )
        except Exception:
            return HealthStatus(component="Disk Space", healthy=True, message="unknown")

    def _check_memory(self) -> HealthStatus:
        try:
            import psutil
            mem = psutil.virtual_memory()
            avail_gb = round(mem.available / (1024**3), 1)
            return HealthStatus(
                component="Memory",
                healthy=mem.percent < 90,
                message=f"{avail_gb} GB available ({100 - mem.percent:.0f}% free)",
                details={"available_gb": avail_gb, "percent_used": mem.percent},
            )
        except ImportError:
            return HealthStatus(component="Memory", healthy=True, message="psutil not available")

    def _check_dependencies(self) -> HealthStatus:
        deps = {
            "rich": False, "toml": False, "psutil": False,
        }
        for dep in deps:
            try:
                __import__(dep)
                deps[dep] = True
            except ImportError:
                pass

        all_ok = all(deps.values())
        missing = [d for d, ok in deps.items() if not ok]
        return HealthStatus(
            component="Dependencies",
            healthy=all_ok,
            message="all installed" if all_ok else f"missing: {', '.join(missing)}",
            details=deps,
        )

    def _check_config_dir(self) -> HealthStatus:
        from config import NEUROSHELL_DIR, DB_FILE
        exists = NEUROSHELL_DIR.exists()
        db_exists = DB_FILE.exists()
        return HealthStatus(
            component="Config Directory",
            healthy=exists,
            message=f"{'exists' if exists else 'created'}, DB: {'exists' if db_exists else 'new'}",
        )


# ═══════════════════════════════════════════════════════════
# Graceful Degradation
# ═══════════════════════════════════════════════════════════

class GracefulDegradation:
    """Manages feature availability based on system state."""

    def __init__(self):
        self._disabled_features: set = set()
        self._warnings: list[str] = []
        self._fallbacks: dict[str, str] = {}

    def check_and_degrade(self, feature: str, available: bool, fallback_msg: str = "", fallback_feature: str = ""):
        """Check if a feature is available; disable and warn if not."""
        if not available:
            self._disabled_features.add(feature)
            if fallback_msg:
                self._warnings.append(fallback_msg)
            if fallback_feature:
                self._fallbacks[feature] = fallback_feature

    def is_available(self, feature: str) -> bool:
        return feature not in self._disabled_features

    def get_fallback(self, feature: str) -> Optional[str]:
        """Get fallback feature for a disabled feature."""
        return self._fallbacks.get(feature)

    def restore(self, feature: str):
        """Re-enable a previously degraded feature."""
        self._disabled_features.discard(feature)
        self._fallbacks.pop(feature, None)

    def get_warnings(self) -> list[str]:
        return list(self._warnings)

    def status(self) -> dict:
        return {
            "disabled_features": list(self._disabled_features),
            "fallbacks": dict(self._fallbacks),
            "warnings": self._warnings,
        }


# ═══════════════════════════════════════════════════════════
# Resilience Manager (Facade)
# ═══════════════════════════════════════════════════════════

class ResilienceManager:
    """
    Central resilience orchestrator.

    Combines circuit breaker, rate limiter, network awareness,
    health checks, crash recovery, and graceful degradation.
    """

    def __init__(self, config):
        self.config = config
        self.network = NetworkAware()
        self.health = HealthCheck(config)
        self.degradation = GracefulDegradation()
        self.crash_recovery = CrashRecovery()

        # Circuit breakers for external services
        self.circuits = {
            "ollama": CircuitBreaker("ollama", failure_threshold=3, recovery_timeout=30),
            "network": CircuitBreaker("network", failure_threshold=5, recovery_timeout=60),
        }

        # Rate limiter for LLM calls
        self.llm_rate_limiter = RateLimiter(max_calls=60, period_seconds=60)

    def pre_flight_check(self) -> HealthReport:
        """Run pre-flight checks and configure degradation."""
        report = self.health.run_all()

        for check in report.checks:
            if not check.healthy:
                self.degradation.check_and_degrade(
                    check.component.lower().replace(" ", "_"),
                    False,
                    f"{check.component}: {check.message}",
                )
                report.degraded_features.append(check.component)

        return report

    def full_status(self) -> dict:
        """Get full resilience status."""
        return {
            "network": self.network.status,
            "degradation": self.degradation.status(),
            "circuits": {name: cb.status for name, cb in self.circuits.items()},
            "rate_limiter": self.llm_rate_limiter.stats,
            "crash_recovery": self.crash_recovery.has_recovery_data(),
        }
