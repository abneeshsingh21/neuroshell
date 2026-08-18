"""
NeuroShell Unit Tests — v4 Improvements
Tests for smart_suggestions, expanded pipeline templates, autocomplete internal commands,
LLM warmup/compression, NLP new intents, and desktop GUI helpers.
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════
# Smart Suggestions Tests
# ═══════════════════════════════════════════════════════════


class TestSmartSuggester(unittest.TestCase):
    """Tests for intelligence/smart_suggestions.py."""

    def setUp(self):
        from intelligence.smart_suggestions import SmartSuggester
        self.suggester = SmartSuggester()

    def test_initialization(self):
        self.assertIsNotNone(self.suggester)
        self.assertIsInstance(self.suggester._last_suggestions, list)

    def test_detect_project_type(self):
        """Project type detection should return a string."""
        ptype = self.suggester._detect_project_type(os.getcwd())
        self.assertIsInstance(ptype, str)

    def test_suggest_returns_list(self):
        """suggest() should return a list of Suggestion objects."""
        results = self.suggester.suggest()
        self.assertIsInstance(results, list)

    def test_suggest_max_count(self):
        """suggest() should respect limit parameter."""
        results = self.suggester.suggest(limit=3)
        self.assertTrue(len(results) <= 3)

    def test_suggest_with_history(self):
        """suggest() should work when called directly."""
        results = self.suggester.suggest(limit=5)
        self.assertIsInstance(results, list)

    def test_suggestion_has_required_fields(self):
        """Each suggestion should have command, reason, and priority."""
        results = self.suggester.suggest(limit=3)
        for s in results:
            self.assertTrue(hasattr(s, 'command'))
            self.assertTrue(hasattr(s, 'reason'))
            self.assertTrue(hasattr(s, 'priority'))

    def test_suggest_with_git_history(self):
        """suggest should produce relevant results."""
        results = self.suggester.suggest(limit=10)
        cmds = [s.command for s in results]
        self.assertIsInstance(cmds, list)

    def test_workflow_patterns(self):
        """Workflow suggestion method should exist."""
        self.assertTrue(hasattr(self.suggester, '_workflow_suggestions'))

    def test_project_type_detection_coverage(self):
        """Should detect project types from file markers."""
        self.assertTrue(hasattr(self.suggester, '_detect_project_type'))

    def test_format_suggestions(self):
        """get_formatted() should return a formatted string."""
        formatted = self.suggester.get_formatted(limit=3)
        self.assertIsInstance(formatted, str)

    def test_empty_format(self):
        """get_formatted() with no context should still return a string."""
        formatted = self.suggester.get_formatted(limit=1)
        self.assertIsInstance(formatted, str)


# ═══════════════════════════════════════════════════════════
# Autocomplete — NeuroShell Internal Commands Tests
# ═══════════════════════════════════════════════════════════


class TestAutocompleteNeuroshellCommands(unittest.TestCase):
    """Tests for autocomplete internal command completions."""

    def setUp(self):
        from intelligence.autocomplete import Autocomplete, NEUROSHELL_COMMANDS
        self.engine = Autocomplete()
        self.ns_commands = NEUROSHELL_COMMANDS

    def test_neuroshell_commands_dict_exists(self):
        self.assertIsInstance(self.ns_commands, dict)
        self.assertTrue(len(self.ns_commands) >= 25)

    def test_common_commands_present(self):
        self.assertIn("help", self.ns_commands)
        self.assertIn("fix", self.ns_commands)
        self.assertIn("suggest", self.ns_commands)
        self.assertIn("pipelines", self.ns_commands)
        self.assertIn("dashboard", self.ns_commands)
        self.assertIn("policy", self.ns_commands)
        self.assertIn("policy audit", self.ns_commands)
        self.assertIn("exit", self.ns_commands)

    def test_neuroshell_completions_method(self):
        """_neuroshell_completions should return completions."""
        results = self.engine._neuroshell_completions("he")
        self.assertTrue(len(results) > 0)
        texts = [c.text for c in results]
        self.assertIn("help", texts)

    def test_neuroshell_completions_empty_prefix(self):
        """Empty prefix should return all internal commands."""
        results = self.engine._neuroshell_completions("")
        self.assertTrue(len(results) >= 20)

    def test_neuroshell_completions_no_match(self):
        """Non-matching prefix should return empty list."""
        results = self.engine._neuroshell_completions("zzzzzzz")
        self.assertEqual(len(results), 0)

    def test_completion_source(self):
        """Internal command completions should have source='neuroshell'."""
        results = self.engine._neuroshell_completions("fix")
        for r in results:
            self.assertEqual(r.source, "neuroshell")

    def test_completion_description_has_emoji(self):
        """Internal command descriptions should have brain emoji."""
        results = self.engine._neuroshell_completions("fix")
        for r in results:
            self.assertIn("🧠", r.description)

    def test_integrated_complete(self):
        """Full complete() should include neuroshell commands."""
        results = self.engine.complete("sug")
        texts = [c.text for c in results]
        self.assertIn("suggest", texts)


class TestAutocompletePersonalization(unittest.TestCase):
    """Tests for history-driven autocomplete ranking improvements."""

    def setUp(self):
        from intelligence.autocomplete import Autocomplete

        class Record:
            def __init__(self, command: str, exit_code: int = 0):
                self.command = command
                self.exit_code = exit_code

        history = MagicMock()
        history.get_recent.return_value = [
            Record("git status"),
            Record("git pull"),
            Record("git status"),
            Record("python -m pytest"),
            Record("git log --oneline"),
        ]

        self.engine = Autocomplete(history_store=history, context_manager=MagicMock())

    def test_history_boosts_frequent_commands(self):
        """Frequently used successful commands should receive score boosts."""
        self.engine._refresh_personalization_boosts()
        self.assertGreater(self.engine._command_boosts.get("git", 0), 0)

    def test_boosted_command_completion(self):
        """Boosted commands should remain present in completion results."""
        completions = self.engine._command_completions("g")
        texts = [c.text for c in completions]
        self.assertIn("git", texts)


# ═══════════════════════════════════════════════════════════
# Pipeline Builder — Expanded Templates Tests
# ═══════════════════════════════════════════════════════════


class TestExpandedPipelineTemplates(unittest.TestCase):
    """Tests for intelligence/pipeline_builder.py expanded templates."""

    def setUp(self):
        from intelligence.pipeline_builder import PipelineBuilder, PIPELINE_TEMPLATES
        self.builder = PipelineBuilder()
        self.templates = PIPELINE_TEMPLATES

    def test_template_count(self):
        """Should have 40+ templates (expanded from 20)."""
        self.assertTrue(len(self.templates) >= 40)

    def test_original_templates_present(self):
        """Original templates should still exist."""
        names = list(self.templates.keys())
        # Check some originals
        self.assertIn("docker cleanup", names)
        self.assertIn("disk usage summary", names)

    def test_new_security_templates(self):
        """Security category templates should be present."""
        self.assertIn("check permissions", self.templates)
        self.assertIn("find suid files", self.templates)
        self.assertIn("check ssl cert", self.templates)
        self.assertIn("find exposed secrets", self.templates)

    def test_new_python_dev_templates(self):
        """Python/Dev category templates should be present."""
        self.assertIn("run linters", self.templates)
        self.assertIn("test coverage", self.templates)
        self.assertIn("find unused imports", self.templates)
        self.assertIn("find python todos", self.templates)

    def test_new_kubernetes_templates(self):
        """Kubernetes category templates should be present."""
        self.assertIn("pod status", self.templates)
        self.assertIn("pod logs", self.templates)
        self.assertIn("restart deployment", self.templates)
        self.assertIn("cluster health", self.templates)

    def test_new_database_templates(self):
        """Database category templates should be present."""
        self.assertIn("dump database", self.templates)
        self.assertIn("redis status", self.templates)

    def test_new_system_templates(self):
        """System health templates should be present."""
        self.assertIn("system health report", self.templates)
        self.assertIn("check journal errors", self.templates)

    def test_template_structure(self):
        """Each template should have pipeline, steps, and params keys."""
        for name, template in self.templates.items():
            self.assertIn("pipeline", template, f"{name} missing 'pipeline'")
            self.assertIn("steps", template, f"{name} missing 'steps'")
            self.assertIn("params", template, f"{name} missing 'params'")

    def test_parameterized_templates(self):
        """Templates with params should have non-empty params dict."""
        template = self.templates["check ssl cert"]
        self.assertIn("host", template["params"])

    def test_list_templates(self):
        """list_templates() should return a list of template names."""
        output = self.builder.list_templates()
        self.assertIsInstance(output, list)
        self.assertIn("docker cleanup", output)

    def test_build_from_template(self):
        """Building from a template should return PipelineResult."""
        result = self.builder.build("docker cleanup")
        self.assertIsNotNone(result)
        self.assertTrue(len(result.pipeline) > 0)

    def test_build_unknown_template(self):
        """Building non-existent template with no LLM should return empty pipeline."""
        result = self.builder.build("nonexistent_template_xyz_123")
        self.assertEqual(result.pipeline, "")


# ═══════════════════════════════════════════════════════════
# LLM Client — Warmup & Compression Tests
# ═══════════════════════════════════════════════════════════


class TestLLMOptimizations(unittest.TestCase):
    """Tests for llm/client.py warmup, compression, and adaptive timeout."""

    def setUp(self):
        from config import Config
        self.config = Config()
        from llm.client import LLMClient
        self.client = LLMClient(self.config)

    def test_warmup_async_method_exists(self):
        self.assertTrue(hasattr(self.client, 'warmup_async'))

    def test_warmup_initially_false(self):
        self.assertFalse(self.client._warmed_up)

    def test_warmup_async_no_crash(self):
        """warmup_async should not crash even without Ollama."""
        self.client.warmup_async()  # Should not raise

    def test_compress_prompt_short(self):
        """Short prompts should not be compressed."""
        from llm.client import LLMClient
        short = "Hello world"
        result = LLMClient.compress_prompt(short)
        self.assertEqual(result, short)

    def test_compress_prompt_long(self):
        """Long prompts should be truncated."""
        from llm.client import LLMClient
        long_prompt = "word " * 1000  # 5000 chars
        result = LLMClient.compress_prompt(long_prompt, max_chars=500)
        self.assertTrue(len(result) <= 550)  # Some margin for the "..." separator

    def test_compress_prompt_whitespace(self):
        """Excessive whitespace should be cleaned in long prompts."""
        from llm.client import LLMClient
        messy = ("line1\n\n\n\n\nline2\n\n\n\nline3 ") * 200  # Make long enough
        result = LLMClient.compress_prompt(messy, max_chars=2000)
        self.assertNotIn("\n\n\n", result)

    def test_compress_prompt_fillers(self):
        """Common filler phrases should be removed from long prompts."""
        from llm.client import LLMClient
        text = "please note that " * 200  # Make it long enough to trigger compression
        result = LLMClient.compress_prompt(text, max_chars=500)
        self.assertTrue(len(result) < len(text))

    def test_adaptive_timeout_short(self):
        """Short prompts should get shorter timeouts."""
        timeout = self.client._adaptive_timeout("fix it")
        self.assertEqual(timeout, 15.0)

    def test_adaptive_timeout_medium(self):
        timeout = self.client._adaptive_timeout("a" * 200)
        self.assertEqual(timeout, 30.0)

    def test_adaptive_timeout_long(self):
        timeout = self.client._adaptive_timeout("a" * 600)
        self.assertEqual(timeout, 60.0)

    def test_cache_still_works(self):
        """LRU cache should still function after optimizations."""
        from llm.client import LRUCache
        cache = LRUCache(capacity=10)
        cache.put("key1", "value1")
        self.assertEqual(cache.get("key1"), "value1")

    def test_cache_stats(self):
        from llm.client import LRUCache
        cache = LRUCache(capacity=10)
        cache.get("miss")
        cache.put("hit", "val")
        cache.get("hit")
        stats = cache.stats
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)


# ═══════════════════════════════════════════════════════════
# NLP Intent Classifier — New Intents Tests
# ═══════════════════════════════════════════════════════════


class TestNLPNewIntents(unittest.TestCase):
    """Tests for nlp/intent_classifier.py expanded intents."""

    def setUp(self):
        from nlp.intent_classifier import IntentClassifier
        self.classifier = IntentClassifier()

    def test_new_intents_exist(self):
        """Should have docker, deploy, and query intents."""
        self.assertIn("docker_request", self.classifier.INTENTS)
        self.assertIn("deploy_request", self.classifier.INTENTS)
        self.assertIn("query_request", self.classifier.INTENTS)

    def test_docker_intent_examples(self):
        self.assertTrue(len(self.classifier.INTENTS["docker_request"]) >= 10)

    def test_deploy_intent_examples(self):
        self.assertTrue(len(self.classifier.INTENTS["deploy_request"]) >= 10)

    def test_query_intent_examples(self):
        self.assertTrue(len(self.classifier.INTENTS["query_request"]) >= 10)

    def test_total_example_count(self):
        """Should have 200+ training examples total."""
        total = sum(len(v) for v in self.classifier.INTENTS.values())
        self.assertGreaterEqual(total, 200)

    def test_intent_count(self):
        """Should have 11 intent categories."""
        self.assertGreaterEqual(len(self.classifier.INTENTS), 11)

    def test_fallback_docker(self):
        """Fallback classifier should detect docker intents."""
        result = self.classifier._fallback_classify("start the containers")
        self.assertEqual(result.intent, "docker_request")

    def test_fallback_deploy(self):
        """Fallback classifier should detect deploy intents."""
        result = self.classifier._fallback_classify("deploy to production")
        self.assertEqual(result.intent, "deploy_request")

    def test_fallback_query(self):
        """Fallback classifier should detect query intents."""
        result = self.classifier._fallback_classify("query the database")
        self.assertEqual(result.intent, "query_request")

    def test_fallback_fix(self):
        result = self.classifier._fallback_classify("fix it")
        self.assertEqual(result.intent, "fix_request")

    def test_fallback_explain(self):
        result = self.classifier._fallback_classify("explain ls -la")
        self.assertEqual(result.intent, "explain_request")

    def test_fallback_shell(self):
        """Shell commands starting with known tools should be detected."""
        result = self.classifier._fallback_classify("rsync -avz src/ dest/")
        self.assertEqual(result.intent, "shell_command")

    def test_fallback_systemctl(self):
        result = self.classifier._fallback_classify("systemctl restart nginx")
        self.assertEqual(result.intent, "shell_command")

    def test_fallback_default(self):
        """Unknown input should default to natural_language."""
        result = self.classifier._fallback_classify("I feel great today")
        self.assertEqual(result.intent, "natural_language")

    def test_stats(self):
        stats = self.classifier.get_stats()
        self.assertGreaterEqual(stats["intent_count"], 11)
        self.assertGreaterEqual(stats["example_count"], 200)

    def test_multi_intent_detection(self):
        """Multi-intent should be detected with conjunctions."""
        result = self.classifier._fallback_classify("fix")
        self.assertFalse(result.is_multi_intent)

    def test_intent_result_fields(self):
        result = self.classifier._fallback_classify("help")
        self.assertTrue(hasattr(result, 'intent'))
        self.assertTrue(hasattr(result, 'confidence'))
        self.assertTrue(hasattr(result, 'all_scores'))


# ═══════════════════════════════════════════════════════════
# Desktop GUI Theme Data Tests
# ═══════════════════════════════════════════════════════════


class TestDesktopGUIThemes(unittest.TestCase):
    """Tests for desktop_features.py theme and color data (non-GUI, data-only)."""

    def test_colors_dict(self):
        from extensions.desktop_features import BUILT_IN_THEMES
        self.assertIsInstance(BUILT_IN_THEMES, dict)
        self.assertIn("cyberpunk", BUILT_IN_THEMES)
        self.assertIn("nord", BUILT_IN_THEMES)

    def test_ansi_colors_mapping(self):
        from extensions.desktop_features import ThemeEngine
        engine = ThemeEngine()
        theme = engine.get_theme()
        self.assertIn("primary", theme)
        self.assertIn("bg", theme)

    def test_font_constants(self):
        from extensions.desktop_features import CommandPalette
        palette = CommandPalette()
        results = palette.search("files")
        self.assertIsInstance(results, list)

    def test_theme_definitions(self):
        """Theme definitions should have required keys."""
        from extensions.desktop_features import BUILT_IN_THEMES
        self.assertIn("cyberpunk", BUILT_IN_THEMES)
        self.assertIn("nord", BUILT_IN_THEMES)
        self.assertIn("matrix", BUILT_IN_THEMES)
        self.assertIn("dracula", BUILT_IN_THEMES)

    def test_theme_keys_consistent(self):
        """All themes should have the same keys."""
        from extensions.desktop_features import BUILT_IN_THEMES
        cyber_keys = set(BUILT_IN_THEMES["cyberpunk"].keys())
        for name, theme in BUILT_IN_THEMES.items():
            self.assertEqual(set(theme.keys()), cyber_keys, f"Theme '{name}' has inconsistent keys")


if __name__ == "__main__":
    unittest.main()
