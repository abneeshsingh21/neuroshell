"""
NeuroShell Unit Tests — Extensions + Learning
Tests for plugin system, pattern learner, predictor, clipboard, themes.
"""

import os
import sys
import json
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPatternLearner(unittest.TestCase):
    """Tests for learning/pattern_learner.py."""

    def test_predict_next(self):
        """Test next command prediction from patterns."""
        from learning.pattern_learner import PatternLearner

        mock_history = MagicMock()

        # Simulate history records
        class Record:
            def __init__(self, command, cwd=".", timestamp=0):
                self.command = command
                self.cwd = cwd
                self.timestamp = timestamp

        mock_history.get_recent.return_value = [
            Record("git add ."),
            Record("git commit -m 'update'"),
            Record("git push"),
            Record("git add ."),
            Record("git commit -m 'update'"),
            Record("git push"),
            Record("git add ."),
            Record("git commit -m 'update'"),
        ]

        learner = PatternLearner(mock_history)
        learner.learn_from_history()

        prediction = learner.predict_next("git add .")
        self.assertIsNotNone(prediction)
        self.assertIn("git commit", prediction)


class TestPredictor(unittest.TestCase):
    """Tests for learning/predictor.py."""

    def test_markov_prediction(self):
        """Test Markov chain prediction."""
        from learning.predictor import Predictor

        mock_history = MagicMock()

        class Record:
            def __init__(self, command):
                self.command = command

        mock_history.get_recent.return_value = [
            Record("cd project"),
            Record("git pull"),
            Record("npm install"),
            Record("cd project"),
            Record("git pull"),
            Record("npm install"),
        ]

        predictor = Predictor(mock_history)
        predictor.train()

        predictions = predictor.predict("cd project")
        self.assertTrue(len(predictions) > 0)
        self.assertEqual(predictions[0][0], "git pull")


class TestMetrics(unittest.TestCase):
    """Tests for learning/metrics.py."""

    def test_counter(self):
        """Test counter metric."""
        from learning.metrics import MetricsTracker
        m = MetricsTracker()
        m.count("commands")
        m.count("commands")
        stats = m.get_stats()
        self.assertEqual(stats["counters"]["commands"], 2)

    def test_latency(self):
        """Test latency recording."""
        from learning.metrics import MetricsTracker
        m = MetricsTracker()
        m.record_latency("nlp", 3.5)
        m.record_latency("nlp", 4.5)
        stats = m.get_stats()
        self.assertEqual(stats["latencies"]["nlp"]["avg_ms"], 4.0)


class TestThemes(unittest.TestCase):
    """Tests for ui/themes.py."""

    def test_builtin_themes(self):
        """Test built-in theme availability."""
        from ui.themes import ThemeManager
        manager = ThemeManager()
        themes = manager.list_themes()
        names = [t["name"] for t in themes]
        self.assertIn("cyberpunk", names)
        self.assertIn("dracula", names)
        self.assertIn("matrix", names)

    def test_set_theme(self):
        """Test theme switching."""
        from ui.themes import ThemeManager
        manager = ThemeManager()
        self.assertTrue(manager.set_theme("dracula"))
        self.assertEqual(manager.get_active().name, "dracula")

    def test_invalid_theme(self):
        """Test invalid theme name."""
        from ui.themes import ThemeManager
        manager = ThemeManager()
        self.assertFalse(manager.set_theme("nonexistent"))

    def test_theme_colors(self):
        """Test theme color access."""
        from ui.themes import Theme
        theme = Theme(name="test", colors={"primary": "#ff0000"})
        self.assertEqual(theme.get("primary"), "#ff0000")
        # Default fallback
        self.assertIsNotNone(theme.get("success"))


class TestFuzzyMatcher(unittest.TestCase):
    """Tests for cpp_engine/engine.py FuzzyMatcher."""

    def test_levenshtein(self):
        """Test Levenshtein algorithm."""
        from cpp_engine.engine import FuzzyMatcher
        self.assertEqual(FuzzyMatcher._levenshtein("", ""), 0)
        self.assertEqual(FuzzyMatcher._levenshtein("abc", ""), 3)
        self.assertEqual(FuzzyMatcher._levenshtein("abc", "abc"), 0)
        self.assertEqual(FuzzyMatcher._levenshtein("abc", "abd"), 1)


class TestHelpSystem(unittest.TestCase):
    """Tests for help/help_system.py."""

    def test_list_topics(self):
        """Test help topic listing."""
        from help.help_system import HelpSystem
        mock_config = MagicMock()
        mock_config.hints_enabled = True
        help_sys = HelpSystem(mock_config)
        output = help_sys.get_help()
        self.assertIn("translate", output)
        self.assertIn("fix", output)

    def test_specific_topic(self):
        """Test specific help topic."""
        from help.help_system import HelpSystem
        mock_config = MagicMock()
        mock_config.hints_enabled = True
        help_sys = HelpSystem(mock_config)
        output = help_sys.get_help("safety")
        self.assertIn("Safety", output)

    def test_unknown_topic(self):
        """Test unknown help topic."""
        from help.help_system import HelpSystem
        mock_config = MagicMock()
        help_sys = HelpSystem(mock_config)
        output = help_sys.get_help("nonexistent")
        self.assertIn("Unknown", output)


class TestPluginSystemSecurity(unittest.TestCase):
    """Security tests for extensions/plugin_system.py trust model."""

    def setUp(self):
        import extensions.plugin_system as ps
        self.ps = ps
        self.temp_root = tempfile.mkdtemp(prefix="neuroshell_plugins_")
        self.plugins_dir = Path(self.temp_root) / "plugins"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.trusted_file = Path(self.temp_root) / "trusted_plugins.json"

        self._orig_plugins_dir = ps.PLUGINS_DIR
        self._orig_trusted_file = ps.TRUSTED_PLUGINS_FILE
        ps.PLUGINS_DIR = self.plugins_dir
        ps.TRUSTED_PLUGINS_FILE = self.trusted_file

        self._orig_allow_untrusted = os.environ.get("NEUROSHELL_ALLOW_UNTRUSTED_PLUGINS")
        os.environ.pop("NEUROSHELL_ALLOW_UNTRUSTED_PLUGINS", None)

        plugin_source = """
PLUGIN_META = {
    'version': '1.0.0',
    'commands': ['ping']
}

def execute(command, args):
    return f\"ok:{command}\"
"""
        (self.plugins_dir / "demo.py").write_text(plugin_source, encoding="utf-8")

    def tearDown(self):
        self.ps.PLUGINS_DIR = self._orig_plugins_dir
        self.ps.TRUSTED_PLUGINS_FILE = self._orig_trusted_file

        if self._orig_allow_untrusted is None:
            os.environ.pop("NEUROSHELL_ALLOW_UNTRUSTED_PLUGINS", None)
        else:
            os.environ["NEUROSHELL_ALLOW_UNTRUSTED_PLUGINS"] = self._orig_allow_untrusted

        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_untrusted_plugin_blocked_by_default(self):
        """Plugins should be blocked until explicitly trusted."""
        manager = self.ps.PluginSystem()
        loaded = manager.load("demo")
        self.assertFalse(loaded)

    def test_trusted_plugin_loads(self):
        """Trusting by name should allow plugin loading."""
        manager = self.ps.PluginSystem()
        manager.trust_plugin("demo")
        loaded = manager.load("demo")
        self.assertTrue(loaded)
        self.assertIn("demo", [p["name"] for p in manager.list_plugins()])

    def test_env_override_allows_untrusted(self):
        """Explicit env override should permit untrusted plugin loading."""
        os.environ["NEUROSHELL_ALLOW_UNTRUSTED_PLUGINS"] = "true"
        manager = self.ps.PluginSystem()
        loaded = manager.load("demo")
        self.assertTrue(loaded)

    def test_command_capability_enforced(self):
        """Plugin command execution should enforce declared command list."""
        manager = self.ps.PluginSystem()
        manager.trust_plugin("demo")
        self.assertTrue(manager.load("demo"))

        ok = manager.execute_command("demo", "ping", [])
        blocked = manager.execute_command("demo", "pong", [])

        self.assertEqual(ok, "ok:ping")
        self.assertIn("not allowed", blocked)

    def test_hook_registration_requires_hooks_capability(self):
        """Plugin hooks are blocked unless hooks capability is declared."""
        hook_source = """
PLUGIN_META = {
    'version': '1.0.0',
    'commands': ['ping'],
    'capabilities': ['execute']
}

def register_hooks(plugin_system):
    plugin_system.register_hook('before_execute', on_before)

def on_before(**kwargs):
    return 'hooked'
"""
        (self.plugins_dir / "hooky.py").write_text(hook_source, encoding="utf-8")

        manager = self.ps.PluginSystem()
        manager.trust_plugin("hooky")
        self.assertTrue(manager.load("hooky"))
        self.assertEqual(manager.trigger_hook("before_execute"), [])


if __name__ == "__main__":
    unittest.main()
