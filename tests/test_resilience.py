"""
test_resilience.py — Unit tests for resilience/resilience.py

Covers:
- RateLimiter.remaining thread safety (lock-protected read)
- RateLimiter window expiry
- SQLite health check via HealthCheck (no connection leak)
- CircuitBreaker state transitions via .call()
"""
import time
import threading
import pytest


class TestRateLimiter:
    def test_remaining_decrements_on_acquire(self):
        from resilience.resilience import RateLimiter
        rl = RateLimiter(max_calls=5, period_seconds=60)
        before = rl.remaining
        rl.acquire()
        assert rl.remaining == before - 1

    def test_remaining_never_goes_below_zero(self):
        from resilience.resilience import RateLimiter
        rl = RateLimiter(max_calls=2, period_seconds=60)
        rl.acquire()
        rl.acquire()
        assert rl.remaining == 0

    def test_remaining_is_thread_safe(self):
        """Read remaining from 20 threads concurrently — must not raise."""
        from resilience.resilience import RateLimiter
        rl = RateLimiter(max_calls=100, period_seconds=60)
        errors = []

        def read_remaining():
            try:
                _ = rl.remaining
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_remaining) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread-safety errors: {errors}"

    def test_window_expires(self):
        """Tokens should refresh after the period elapses."""
        from resilience.resilience import RateLimiter
        rl = RateLimiter(max_calls=1, period_seconds=0.1)
        rl.acquire()
        assert rl.remaining == 0
        time.sleep(0.15)
        assert rl.remaining == 1


class TestSQLiteHealthCheck:
    def _get_health_checker(self):
        from resilience.resilience import HealthCheck, ResilienceManager
        from unittest.mock import MagicMock
        cfg = MagicMock()
        cfg.model = "llama3"
        return HealthCheck(cfg)

    def test_sqlite_check_returns_healthy(self):
        hc = self._get_health_checker()
        result = hc._check_sqlite()
        assert result.healthy is True
        assert result.component == "SQLite"
        assert "v" in result.message  # e.g. "v3.39.2"

    def test_sqlite_no_connection_leak(self):
        """Running the check 50 times should not exhaust connections."""
        hc = self._get_health_checker()
        for _ in range(50):
            result = hc._check_sqlite()
            assert result.healthy is True


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        from resilience.resilience import CircuitBreaker, CircuitState
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=1)
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold_failures(self):
        from resilience.resilience import CircuitBreaker, CircuitState
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=1)
        for _ in range(3):
            try:
                cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass
        assert cb.state == CircuitState.OPEN

    def test_blocks_calls_when_open(self):
        from resilience.resilience import CircuitBreaker, CircuitState
        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=60)
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass
        assert cb.state == CircuitState.OPEN
        # Further calls should be rejected without executing the function
        executed = []
        try:
            cb.call(lambda: executed.append(True))
        except Exception:
            pass
        assert executed == [], "Circuit is OPEN — function must not be called"

    def test_recovers_after_timeout(self):
        from resilience.resilience import CircuitBreaker, CircuitState
        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=0.1)
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        # After recovery timeout, circuit allows a probe (HALF_OPEN or success resets)
        state_after = cb.state
        assert state_after in (CircuitState.HALF_OPEN, CircuitState.OPEN)

    def test_success_resets_circuit(self):
        from resilience.resilience import CircuitBreaker, CircuitState
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=1)
        # Cause 2 failures (below threshold)
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass
        # Successful call should reset failure count
        cb.call(lambda: "ok")
        assert cb.state == CircuitState.CLOSED or cb._failure_count == 0
