"""
NeuroShell Integration Tests
Config, resilience, help, learning, observability, UI, extensions.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConfigSystem(unittest.TestCase):
    """Tests for config.py."""

    def test_load_config(self):
        """Test config loads with defaults."""
        from config import Config
        config = Config.load()
        self.assertIsNotNone(config.llm.model)
        self.assertIsNotNone(config.default_shell)

    def test_config_defaults(self):
        """Test default values are sensible."""
        from config import Config
        config = Config()
        self.assertEqual(config.llm.model, "qwen3:4b")
        self.assertTrue(config.safety.enabled)
        self.assertEqual(config.ui.theme, "cyberpunk")

    def test_validation(self):
        """Test config validation clamps values."""
        from config import Config
        config = Config()
        config.llm.temperature = 99.0
        config._validate()
        self.assertLessEqual(config.llm.temperature, 2.0)

    def test_validation_min(self):
        """Test config validation min values."""
        from config import Config
        config = Config()
        config.llm.temperature = -5.0
        config._validate()
        self.assertGreaterEqual(config.llm.temperature, 0.0)

    def test_summary(self):
        """Test config summary."""
        from config import Config
        config = Config()
        summary = config.summary
        self.assertIn("model=", summary)
        self.assertIn("shell=", summary)

    def test_get_secret_fallback(self):
        """Test secret retrieval with fallback."""
        from config import Config
        config = Config()
        config._secrets = {}
        val = config.get_secret("nonexistent", "default_val")
        self.assertEqual(val, "default_val")


class TestResilienceLayer(unittest.TestCase):
    """Tests for resilience/resilience.py."""

    def test_circuit_breaker_closed(self):
        """Test circuit breaker starts closed."""
        from resilience.resilience import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test")
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_circuit_breaker_opens(self):
        """Test circuit breaker opens after failures."""
        from resilience.resilience import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            try:
                cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_rate_limiter(self):
        """Test rate limiter allows calls."""
        from resilience.resilience import RateLimiter
        rl = RateLimiter(max_calls=10, period_seconds=60)
        self.assertTrue(rl.acquire())

    def test_rate_limiter_blocks(self):
        """Test rate limiter blocks excess calls."""
        from resilience.resilience import RateLimiter
        rl = RateLimiter(max_calls=2, period_seconds=60)
        rl.acquire()
        rl.acquire()
        self.assertFalse(rl.acquire())

    def test_health_check(self):
        """Test health check runs."""
        from config import Config
        from resilience.resilience import HealthCheck
        config = Config.load()
        hc = HealthCheck(config)
        report = hc.run_all()
        self.assertIsNotNone(report)
        self.assertGreater(report.total_count, 0)

    def test_graceful_degradation(self):
        """Test graceful degradation tracking."""
        from resilience.resilience import GracefulDegradation
        gd = GracefulDegradation()
        gd.check_and_degrade("test_feature", False, "Feature unavailable")
        warnings = gd.get_warnings()
        self.assertTrue(len(warnings) > 0)

    def test_network_aware(self):
        """Test network awareness."""
        from resilience.resilience import NetworkAware
        na = NetworkAware()
        warning = na.warn_if_offline("curl https://example.com")
        self.assertIsInstance(warning, (str, type(None)))


class TestSafetyPolicyIntegration(unittest.TestCase):
    """Integration checks for safety policy profile and role wiring."""

    @patch.dict(os.environ, {
        "NEUROSHELL_POLICY_PROFILE": "production",
        "NEUROSHELL_USER_ROLE": "viewer",
    }, clear=False)
    def test_safety_policy_state_from_environment(self):
        from config import Config
        from intelligence.safety import SafetyChecker

        safety = SafetyChecker(Config.load(), llm_client=MagicMock())
        state = safety.get_policy_state()
        self.assertEqual(state["profile"], "production")
        self.assertEqual(state["role"], "viewer")


class TestHelpSystem(unittest.TestCase):
    """Tests for help/help_system.py."""

    def test_help_all_topics(self):
        """Test help system shows all topics."""
        from config import Config
        from help.help_system import HelpSystem
        hs = HelpSystem(Config())
        output = hs.get_help()
        self.assertIn("Topics", output)

    def test_help_specific_topic(self):
        """Test help for specific topic."""
        from config import Config
        from help.help_system import HelpSystem
        hs = HelpSystem(Config())
        output = hs.get_help("translate")
        self.assertIn("Translation", output)

    def test_help_unknown_topic(self):
        """Test help for unknown topic."""
        from config import Config
        from help.help_system import HelpSystem
        hs = HelpSystem(Config())
        output = hs.get_help("nonexistent_xyz")
        self.assertIn("Unknown", output)

    def test_help_policy_topic(self):
        """Test help for policy governance topic."""
        from config import Config
        from help.help_system import HelpSystem
        hs = HelpSystem(Config())
        output = hs.get_help("policy")
        self.assertIn("Profiles", output)
        self.assertIn("policy profile", output)

    def test_help_plugins_topic(self):
        """Test help for plugin trust/capability topic."""
        from config import Config
        from help.help_system import HelpSystem
        hs = HelpSystem(Config())
        output = hs.get_help("plugins")
        self.assertIn("trust-gated", output)
        self.assertIn("Capabilities", output)

    def test_help_deploy_topic(self):
        """Test help for deploy promotion/rollback topic."""
        from config import Config
        from help.help_system import HelpSystem
        hs = HelpSystem(Config())
        output = hs.get_help("deploy")
        self.assertIn("rollback", output.lower())
        self.assertIn("deploy promote", output)
        self.assertIn("deploy key add", output)
        self.assertIn("deploy audit verify", output)

    def test_hint(self):
        """Test contextual hints."""
        from config import Config
        from help.help_system import HelpSystem
        hs = HelpSystem(Config())
        hint = hs.get_hint("first_error")
        self.assertIsNotNone(hint)
        self.assertIn("fix", hint.lower())

    def test_hint_shown_once(self):
        """Test hints only shown once."""
        from config import Config
        from help.help_system import HelpSystem
        hs = HelpSystem(Config())
        h1 = hs.get_hint("first_error")
        h2 = hs.get_hint("first_error")
        self.assertIsNotNone(h1)
        self.assertIsNone(h2)


class TestLearningLayer(unittest.TestCase):
    """Tests for learning modules."""

    def test_metrics_counter(self):
        """Test metrics counter."""
        from learning.metrics import MetricsTracker
        m = MetricsTracker()
        m.count("test_metric", 5)
        stats = m.get_stats()
        self.assertEqual(stats["counters"]["test_metric"], 5)

    def test_metrics_latency(self):
        """Test metrics latency tracking."""
        from learning.metrics import MetricsTracker
        m = MetricsTracker()
        m.record_latency("test", 100.0)
        m.record_latency("test", 200.0)
        stats = m.get_stats()
        self.assertEqual(stats["latencies"]["test"]["avg_ms"], 150.0)

    def test_metrics_summary(self):
        """Test metrics summary."""
        from learning.metrics import MetricsTracker
        m = MetricsTracker()
        m.count("commands", 10)
        summary = m.summary()
        self.assertIn("commands", summary)

    def test_feedback_session_stats(self):
        """Test feedback loop session stats."""
        from learning.feedback_loop import FeedbackLoop
        fl = FeedbackLoop(MagicMock(), MagicMock())
        fl.history.store_feedback = MagicMock()
        fl.record_accept("translation", "input", "output")
        stats = fl.get_session_stats()
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["accept_rate"], 100.0)

    def test_predictor_empty(self):
        """Test predictor with no training data."""
        from learning.predictor import Predictor
        p = Predictor(MagicMock())
        p.history.get_recent.return_value = []
        p.train()
        result = p.predict("git status")
        self.assertEqual(result, [])


class TestObservability(unittest.TestCase):
    """Tests for observability modules."""

    def test_logger_creation(self):
        """Test structured logger creation."""
        from observability.logger import StructuredLogger
        logger = StructuredLogger("test")
        self.assertIsNotNone(logger)

    def test_provenance_tracker(self):
        """Test provenance tracking."""
        from observability.provenance import ProvenanceTracker, ProvenanceTag, ProvenanceSource
        pt = ProvenanceTracker()
        pt.record(ProvenanceTag(source=ProvenanceSource.LLM, confidence=0.9))
        pt.record(ProvenanceTag(source=ProvenanceSource.CACHED, confidence=0.95))
        stats = pt.get_stats()
        self.assertEqual(stats["total"], 2)

    def test_provenance_summary(self):
        """Test provenance summary."""
        from observability.provenance import ProvenanceTracker, ProvenanceTag, ProvenanceSource
        pt = ProvenanceTracker()
        pt.record(ProvenanceTag(source=ProvenanceSource.LLM, confidence=0.9))
        summary = pt.get_summary()
        self.assertIn("LLM", summary)

    def test_tracer(self):
        """Test event tracer."""
        from observability.tracer import EventTracer
        tracer = EventTracer()
        cid = tracer.start_trace()
        tracer.add_event(cid, "test_stage", data="value")
        tracer.end_trace(cid)
        trace = tracer.get_trace(cid)
        self.assertIsNotNone(trace)
        self.assertTrue(trace.completed)


class TestUILayer(unittest.TestCase):
    """Tests for UI modules."""

    def test_theme_manager(self):
        """Test theme manager initialization."""
        from ui.themes import ThemeManager
        tm = ThemeManager()
        active = tm.get_active()
        self.assertIsNotNone(active)

    def test_theme_names(self):
        """Test that built-in themes exist."""
        from ui.themes import ThemeManager
        tm = ThemeManager()
        themes = tm.list_themes()
        self.assertTrue(len(themes) >= 5)


class TestExtensions(unittest.TestCase):
    """Tests for extension modules."""

    def test_clipboard_import(self):
        """Test clipboard module imports."""
        from extensions.clipboard import ClipboardManager
        self.assertIsNotNone(ClipboardManager)

    def test_plugin_system_import(self):
        """Test plugin system imports."""
        from extensions.plugin_system import PluginSystem
        self.assertIsNotNone(PluginSystem)

    def test_session_recorder_import(self):
        """Test session recorder imports."""
        from extensions.session_recorder import SessionRecorder
        self.assertIsNotNone(SessionRecorder)


if __name__ == "__main__":
    unittest.main()
