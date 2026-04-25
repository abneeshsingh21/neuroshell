"""
NeuroShell Unit Tests — New Feature Modules
Tests for alias_manager, env_manager, model_manager, config_editor,
command timer, banner, history export/text, and cpp_engine modules.
"""

import os
import sys
import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════
# Alias Manager Tests
# ═══════════════════════════════════════════════════════════


class TestAliasManager(unittest.TestCase):
    """Tests for extensions/alias_manager.py."""

    def setUp(self):
        """Create alias manager with temp storage."""
        # Patch ALIASES_FILE to temp location
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()

        import extensions.alias_manager as am
        self._orig_file = am.ALIASES_FILE
        am.ALIASES_FILE = Path(self.tmp.name)
        # Write empty file to prevent loading defaults
        Path(self.tmp.name).write_text("{}", encoding="utf-8")

        from extensions.alias_manager import AliasManager
        self.manager = AliasManager(load_defaults=False)

    def tearDown(self):
        import extensions.alias_manager as am
        am.ALIASES_FILE = self._orig_file
        try:
            os.unlink(self.tmp.name)
        except Exception:
            pass

    def test_add_and_get(self):
        self.manager.add("gs", "git status")
        self.assertEqual(self.manager.get("gs"), "git status")

    def test_remove(self):
        self.manager.add("foo", "bar")
        self.assertTrue(self.manager.remove("foo"))
        self.assertIsNone(self.manager.get("foo"))

    def test_remove_nonexistent(self):
        self.assertFalse(self.manager.remove("nonexistent"))

    def test_expand(self):
        self.manager.add("gs", "git status")
        result = self.manager.expand("gs -s")
        self.assertEqual(result, "git status -s")

    def test_expand_no_alias(self):
        result = self.manager.expand("ls -la")
        self.assertEqual(result, "ls -la")

    def test_prevent_recursive(self):
        result = self.manager.add("foo", "foo bar")
        self.assertFalse(result)

    def test_list_all(self):
        self.manager.add("a", "alpha")
        self.manager.add("b", "beta")
        aliases = self.manager.list_all()
        names = [a.name for a in aliases]
        self.assertIn("a", names)
        self.assertIn("b", names)

    def test_has_alias(self):
        self.manager.add("gs", "git status")
        self.assertTrue(self.manager.has_alias("gs"))
        self.assertFalse(self.manager.has_alias("nope"))

    def test_formatted_list(self):
        self.manager.add("gs", "git status")
        output = self.manager.get_formatted_list()
        self.assertIn("gs", output)
        self.assertIn("git status", output)

    def test_empty_formatted_list(self):
        output = self.manager.get_formatted_list()
        self.assertIn("No aliases", output)

    def test_usage_tracking(self):
        self.manager.add("gs", "git status")
        self.manager.expand("gs")
        aliases = self.manager.list_all()
        self.assertEqual(aliases[0].usage_count, 1)

    def test_persistence(self):
        """Test that aliases persist to file."""
        self.manager.add("test_persist", "echo hello")
        # Read the file
        data = json.loads(Path(self.tmp.name).read_text(encoding="utf-8"))
        self.assertIn("test_persist", data)

    def test_reset_to_defaults(self):
        self.manager.add("custom", "echo custom")
        self.manager.reset_to_defaults()
        self.assertIsNone(self.manager.get("custom"))
        # Should have default aliases
        self.assertTrue(self.manager.count > 0)

    def test_count(self):
        self.assertEqual(self.manager.count, 0)
        self.manager.add("a", "alpha")
        self.assertEqual(self.manager.count, 1)


# ═══════════════════════════════════════════════════════════
# Environment Manager Tests
# ═══════════════════════════════════════════════════════════


class TestEnvManager(unittest.TestCase):
    """Tests for core/env_manager.py."""

    def setUp(self):
        from core.env_manager import EnvManager
        self.mgr = EnvManager()

    def test_get_system_var(self):
        os.environ["TEST_NEURO_VAR"] = "hello"
        self.assertEqual(self.mgr.get("TEST_NEURO_VAR"), "hello")
        del os.environ["TEST_NEURO_VAR"]

    def test_set_var(self):
        self.mgr.set_var("MY_TEST_VAR", "world")
        self.assertEqual(os.environ["MY_TEST_VAR"], "world")
        self.assertEqual(self.mgr.get("MY_TEST_VAR"), "world")
        del os.environ["MY_TEST_VAR"]

    def test_unset_var(self):
        os.environ["TO_UNSET"] = "temp"
        self.assertTrue(self.mgr.unset_var("TO_UNSET"))
        self.assertNotIn("TO_UNSET", os.environ)

    def test_unset_nonexistent(self):
        self.assertFalse(self.mgr.unset_var("DEFINITELY_NOT_SET_12345"))

    def test_search(self):
        os.environ["NEURO_SEARCH_TEST"] = "findme"
        results = self.mgr.search("NEURO_SEARCH")
        names = [r.name for r in results]
        self.assertIn("NEURO_SEARCH_TEST", names)
        del os.environ["NEURO_SEARCH_TEST"]

    def test_list_all(self):
        results = self.mgr.list_all()
        self.assertTrue(len(results) > 0)

    def test_list_filtered(self):
        os.environ["NEURO_FILTER_TEST"] = "yes"
        results = self.mgr.list_all("NEURO_FILTER")
        self.assertTrue(any(r.name == "NEURO_FILTER_TEST" for r in results))
        del os.environ["NEURO_FILTER_TEST"]

    def test_session_changes(self):
        self.mgr.set_var("SESSION_TEST", "value")
        changes = self.mgr.get_session_changes()
        self.assertIn("SESSION_TEST", changes["set"])
        del os.environ["SESSION_TEST"]

    def test_formatted_var(self):
        os.environ["FMT_TEST"] = "formatted"
        output = self.mgr.get_formatted_var("FMT_TEST")
        self.assertIn("formatted", output)
        del os.environ["FMT_TEST"]

    def test_formatted_var_not_found(self):
        output = self.mgr.get_formatted_var("DEFINITELY_NOT_SET_XYZ")
        self.assertIn("not set", output)

    def test_parse_equals_format(self):
        result = self.mgr.parse_set_command("KEY=VALUE")
        self.assertEqual(result, ("KEY", "VALUE"))

    def test_parse_space_format(self):
        result = self.mgr.parse_set_command("KEY VALUE")
        self.assertEqual(result, ("KEY", "VALUE"))


# ═══════════════════════════════════════════════════════════
# Model Manager Tests
# ═══════════════════════════════════════════════════════════


class TestModelManager(unittest.TestCase):
    """Tests for llm/model_manager.py."""

    def setUp(self):
        from llm.model_manager import ModelManager
        self.config = MagicMock()
        self.config.llm.model = "qwen3:4b"
        self.manager = ModelManager(self.config)

    def test_current_model(self):
        self.assertEqual(self.manager.current_model(), "qwen3:4b")

    def test_list_models_no_ollama(self):
        """Test graceful handling when ollama not available."""
        # Force refresh with no ollama running
        models = self.manager.list_models(force_refresh=True)
        self.assertIsInstance(models, list)

    def test_switch_model_not_found(self):
        """Test switching to a non-existent model."""
        self.manager._last_models = []
        self.manager._last_check = time.time()
        success, msg = self.manager.switch_model("nonexistent")
        self.assertFalse(success)

    def test_formatted_list_no_models(self):
        """Test formatted list when no models available."""
        self.manager._last_models = []
        self.manager._last_check = time.time()
        output = self.manager.get_formatted_list()
        self.assertIsInstance(output, str)


# ═══════════════════════════════════════════════════════════
# Config Editor Tests
# ═══════════════════════════════════════════════════════════


class TestConfigEditor(unittest.TestCase):
    """Tests for extensions/config_editor.py."""

    def setUp(self):
        from config import Config
        from extensions.config_editor import ConfigEditor
        self.config = Config()
        self.editor = ConfigEditor(self.config)

    def test_show(self):
        output = self.editor.show()
        self.assertIn("Configuration", output)

    def test_show_section(self):
        output = self.editor.show("llm")
        self.assertIn("model", output)

    def test_show_invalid_section(self):
        output = self.editor.show("nonexistent")
        self.assertIn("Unknown", output)

    def test_set_value_bool(self):
        ok, msg = self.editor.set_value("safety.enabled", "false")
        self.assertTrue(ok)
        self.assertFalse(self.config.safety.enabled)
        # Reset
        self.config.safety.enabled = True

    def test_set_value_int(self):
        ok, msg = self.editor.set_value("llm.max_tokens", "1024")
        self.assertTrue(ok)
        self.assertEqual(self.config.llm.max_tokens, 1024)

    def test_set_value_float(self):
        ok, msg = self.editor.set_value("llm.temperature", "0.5")
        self.assertTrue(ok)
        self.assertAlmostEqual(self.config.llm.temperature, 0.5)

    def test_set_unknown_key(self):
        ok, msg = self.editor.set_value("nonexistent.key", "value")
        self.assertFalse(ok)
        self.assertIn("Unknown", msg)

    def test_set_invalid_type(self):
        ok, msg = self.editor.set_value("llm.max_tokens", "not_a_number")
        self.assertFalse(ok)

    def test_list_editable(self):
        output = self.editor.list_editable()
        self.assertIn("llm.model", output)
        self.assertIn("safety.enabled", output)

    def test_reset_to_defaults(self):
        self.config.llm.temperature = 0.99
        msg = self.editor.reset_to_defaults()
        self.assertIn("reset", msg.lower())


# ═══════════════════════════════════════════════════════════
# Command Timer Tests
# ═══════════════════════════════════════════════════════════


class TestCommandTimer(unittest.TestCase):
    """Tests for core/timer.py."""

    def setUp(self):
        from core.timer import CommandTimer
        self.timer = CommandTimer()

    def test_record_execution(self):
        self.timer.record_execution("echo hi", 100, 0)
        stats = self.timer.get_session_stats()
        self.assertEqual(stats["total_commands"], 1)
        self.assertEqual(stats["total_time_ms"], 100)

    def test_session_stats(self):
        self.timer.record_execution("cmd1", 50, 0)
        self.timer.record_execution("cmd2", 150, 1)
        stats = self.timer.get_session_stats()
        self.assertEqual(stats["total_commands"], 2)
        self.assertEqual(stats["total_errors"], 1)
        self.assertEqual(stats["success_rate"], 50.0)

    def test_formatted_stats(self):
        self.timer.record_execution("echo hi", 100, 0)
        output = self.timer.get_formatted_stats()
        self.assertIn("Session Statistics", output)
        self.assertIn("1", output)

    def test_timing_result_display(self):
        from core.timer import TimingResult
        tr = TimingResult(command="echo hi", wall_time_ms=42, exit_code=0)
        display = tr.display()
        self.assertIn("42ms", display)
        self.assertIn("✅", display)

    def test_timing_result_display_error(self):
        from core.timer import TimingResult
        tr = TimingResult(command="bad cmd", wall_time_ms=100, exit_code=1)
        self.assertIn("❌", tr.display())

    def test_wall_time_seconds(self):
        from core.timer import TimingResult
        tr = TimingResult(command="slow", wall_time_ms=2500)
        self.assertIn("2.50s", tr.wall_time_display)

    def test_wall_time_minutes(self):
        from core.timer import TimingResult
        tr = TimingResult(command="very slow", wall_time_ms=90_000)
        self.assertIn("1m", tr.wall_time_display)

    def test_format_duration(self):
        from core.timer import CommandTimer
        self.assertEqual(CommandTimer._format_duration(30), "30s")
        self.assertEqual(CommandTimer._format_duration(90), "1m 30s")
        self.assertEqual(CommandTimer._format_duration(3661), "1h 1m")


# ═══════════════════════════════════════════════════════════
# Banner Tests
# ═══════════════════════════════════════════════════════════


class TestBanner(unittest.TestCase):
    """Tests for ui/banner.py."""

    def test_get_banner_default(self):
        from ui.banner import get_banner
        banner = get_banner()
        # ASCII art banner contains the text in styled form
        self.assertTrue(len(banner) > 10)
        self.assertIn("_", banner)  # ASCII art has underscores

    def test_get_banner_themed(self):
        from ui.banner import get_banner
        banner = get_banner("cyberpunk")
        self.assertIn("SHELL", banner)

    def test_system_info(self):
        from ui.banner import get_system_info
        config = MagicMock()
        config.llm.model = "qwen3:4b"
        config.default_shell = "powershell"
        config.ui.theme = "cyberpunk"
        info = get_system_info(config)
        self.assertIn("qwen3:4b", info)
        self.assertIn("powershell", info)

    def test_render_banner(self):
        from ui.banner import render_startup_banner
        config = MagicMock()
        config.llm.model = "test"
        config.default_shell = "bash"
        config.ui.theme = "default"
        result = render_startup_banner(config, show_health=False)
        self.assertTrue(len(result) > 50)  # Banner is substantial text
        self.assertIn("test", result)  # Model name appears in system info

    def test_tips(self):
        from ui.banner import get_tips
        tip = get_tips()
        self.assertIn("💡", tip)


# ═══════════════════════════════════════════════════════════
# History Export/Text Tests
# ═══════════════════════════════════════════════════════════


class TestHistoryExportText(unittest.TestCase):
    """Tests for history.py export_text and get_all_fixes methods."""

    def setUp(self):
        from core.history import HistoryStore, CommandRecord
        self.tmpdir = tempfile.mkdtemp()
        self.history = HistoryStore(db_path=Path(self.tmpdir) / "test.db")
        # Add some test data
        for i in range(3):
            record = CommandRecord(
                command=f"echo test{i}",
                exit_code=0,
                timestamp=time.time() - i,
                cwd="/tmp",
            )
            self.history.add_command(record)

    def tearDown(self):
        self.history.close()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_export_text(self):
        filepath = Path(self.tmpdir) / "export.txt"
        count = self.history.export_text(filepath)
        self.assertEqual(count, 3)
        content = filepath.read_text(encoding="utf-8")
        self.assertIn("echo test0", content)
        self.assertIn("✓", content)

    def test_export_text_with_limit(self):
        filepath = Path(self.tmpdir) / "export_limited.txt"
        count = self.history.export_text(filepath, limit=2)
        self.assertEqual(count, 2)

    def test_get_all_fixes_empty(self):
        fixes = self.history.get_all_fixes()
        self.assertEqual(fixes, [])

    def test_get_all_fixes_with_data(self):
        self.history.store_fix("err1", "Error message 1", "fix_cmd_1", "llm")
        fixes = self.history.get_all_fixes()
        self.assertEqual(len(fixes), 1)
        self.assertEqual(fixes[0]["fix_command"], "fix_cmd_1")


# ═══════════════════════════════════════════════════════════
# Cpp Engine Additional Tests
# ═══════════════════════════════════════════════════════════


class TestCppEngineFastParser(unittest.TestCase):
    """Tests for cpp_engine/engine.py FastParser."""

    def setUp(self):
        from cpp_engine.engine import FastParser
        self.parser = FastParser()

    def test_parse_simple(self):
        result = self.parser.parse("ls -la /home")
        self.assertEqual(result.program, "ls")
        self.assertIn("-la", result.flags)
        self.assertIn("/home", result.arguments)

    def test_parse_pipe(self):
        result = self.parser.parse("cat file.txt | grep error | wc -l")
        self.assertTrue(result.is_compound)
        self.assertEqual(len(result.pipes), 3)

    def test_parse_redirect(self):
        result = self.parser.parse("echo hello > output.txt")
        self.assertTrue(len(result.redirects) > 0)

    def test_parse_empty(self):
        result = self.parser.parse("")
        self.assertEqual(result.program, "")

    def test_parse_flags(self):
        result = self.parser.parse("git commit -m 'initial'")
        self.assertEqual(result.program, "git")
        self.assertIn("-m", result.flags)


class TestCppEngineMarkovEngine(unittest.TestCase):
    """Tests for cpp_engine/engine.py MarkovEngine."""

    def test_train_and_predict(self):
        from cpp_engine.engine import MarkovEngine
        engine = MarkovEngine()
        # train takes list of sequences (list of lists)
        sequences = [["git add", "git commit", "git push", "git add", "git commit", "git push"]]
        engine.train(sequences)
        predictions = engine.predict("git add")
        self.assertTrue(len(predictions) > 0)
        self.assertEqual(predictions[0][0], "git commit")

    def test_predict_unknown(self):
        from cpp_engine.engine import MarkovEngine
        engine = MarkovEngine()
        predictions = engine.predict("unknown_command")
        self.assertEqual(predictions, [])

    def test_stats(self):
        from cpp_engine.engine import MarkovEngine
        engine = MarkovEngine()
        engine.train([["a", "b", "c"]])
        stats = engine.stats
        self.assertEqual(stats["states"], 2)
        self.assertEqual(stats["transitions"], 2)


class TestCppEngineFuzzyMatcher(unittest.TestCase):
    """Tests for cpp_engine/engine.py FuzzyMatcher."""

    def test_exact_prefix_match(self):
        from cpp_engine.engine import FuzzyMatcher
        matcher = FuzzyMatcher(["git", "grep", "gcc", "gdb"])
        matches = matcher.match("gi")
        self.assertTrue(len(matches) > 0)
        self.assertEqual(matches[0][0], "git")
        self.assertEqual(matches[0][1], 0)  # prefix = distance 0

    def test_did_you_mean(self):
        from cpp_engine.engine import FuzzyMatcher
        matcher = FuzzyMatcher(["git", "grep", "gcc"])
        suggestion = matcher.did_you_mean("gti")
        self.assertEqual(suggestion, "git")

    def test_no_match(self):
        from cpp_engine.engine import FuzzyMatcher
        matcher = FuzzyMatcher(["git"])
        matches = matcher.match("zzzzzzzz", max_distance=1)
        self.assertEqual(len(matches), 0)


if __name__ == "__main__":
    unittest.main()
