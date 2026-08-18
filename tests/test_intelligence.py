"""
NeuroShell Unit Tests — Intelligence Layer
Tests for translator, safety, error_fixer, explainer, pipeline_builder, autocomplete.
"""

import os
import sys
import json
import tempfile
import csv
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSafetyChecker(unittest.TestCase):
    """Tests for intelligence/safety.py."""

    def setUp(self):
        from config import Config
        from intelligence.safety import SafetyChecker, RiskLevel
        self.config = Config.load()
        self.safety = SafetyChecker(self.config, llm_client=MagicMock())
        self.RiskLevel = RiskLevel

    def test_safe_command(self):
        """Test that safe commands pass."""
        result = self.safety.check("ls -la")
        self.assertEqual(result.risk_level, self.RiskLevel.SAFE)

    def test_dangerous_rm(self):
        """Test rm -rf / is blocked."""
        result = self.safety.check("rm -rf /")
        self.assertEqual(result.risk_level, self.RiskLevel.BLOCKED)

    def test_format_blocked(self):
        """Test format C: is blocked."""
        result = self.safety.check("format C:")
        self.assertEqual(result.risk_level, self.RiskLevel.BLOCKED)

    def test_echo_safe(self):
        """Test echo is safe."""
        result = self.safety.check("echo hello")
        self.assertEqual(result.risk_level, self.RiskLevel.SAFE)

    def test_fork_bomb_blocked(self):
        """Test fork bomb is blocked."""
        result = self.safety.check(":(){ :|:& };:")
        self.assertEqual(result.risk_level, self.RiskLevel.BLOCKED)

    def test_dd_blocked(self):
        """Test dd to /dev/ is blocked."""
        result = self.safety.check("dd if=/dev/zero of=/dev/sda")
        self.assertEqual(result.risk_level, self.RiskLevel.BLOCKED)

    def test_git_push_caution(self):
        """Test force push triggers caution or safety check."""
        result = self.safety.check("git push --force")
        # Force push is at least concerning
        self.assertIsNotNone(result.risk_level)

    def test_policy_state_defaults(self):
        """Safety checker should expose normalized default policy state."""
        state = self.safety.get_policy_state()
        self.assertIn(state["profile"], {"dev", "staging", "production"})
        self.assertIn(state["role"], {"admin", "developer", "operator", "viewer"})

    def test_production_viewer_blocks_non_safe(self):
        """Viewer role in production should block non-safe commands."""
        self.safety.set_policy_profile("production")
        self.safety.set_user_role("viewer")
        result = self.safety.check("rm notes.txt")
        self.assertEqual(result.risk_level, self.RiskLevel.BLOCKED)

    def test_production_developer_blocks_high_impact_danger(self):
        """Production developer should be blocked from high-impact danger commands."""
        self.safety.set_policy_profile("production")
        self.safety.set_user_role("developer")
        result = self.safety.check("terraform destroy")
        self.assertEqual(result.risk_level, self.RiskLevel.BLOCKED)

    def test_staging_escalates_recursive_caution(self):
        """Staging should escalate recursive caution commands for non-admin roles."""
        self.safety.set_policy_profile("staging")
        self.safety.set_user_role("operator")
        result = self.safety.check("rm -r ./tmp")
        self.assertIn(result.risk_level, {self.RiskLevel.DANGER, self.RiskLevel.BLOCKED})

    def test_audit_export_json(self):
        """Safety audit entries should export to JSON with policy metadata."""
        self.safety.set_policy_profile("production")
        self.safety.set_user_role("viewer")
        self.safety.check("rm notes.txt")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "audit.json")
            count = self.safety.export_audit_json(path, limit=10)
            self.assertGreaterEqual(count, 1)

            payload = json.loads(open(path, "r", encoding="utf-8").read())
            self.assertEqual(payload["profile"], "production")
            self.assertEqual(payload["role"], "viewer")
            self.assertTrue(len(payload["entries"]) >= 1)

    def test_audit_export_csv(self):
        """Safety audit entries should export to CSV for SIEM/report workflows."""
        self.safety.set_policy_profile("staging")
        self.safety.set_user_role("operator")
        self.safety.check("rm -r ./tmp")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "audit.csv")
            count = self.safety.export_audit_csv(path, limit=10)
            self.assertGreaterEqual(count, 1)

            with open(path, "r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertGreaterEqual(len(rows), 1)
            self.assertIn("entry_hash", rows[0])
            self.assertIn("prev_hash", rows[0])

    def test_audit_hash_chain_links_entries(self):
        """Audit entries should form a deterministic hash chain."""
        self.safety.check("rm notes.txt")
        self.safety.check("rm notes.txt")

        rows = self.safety.get_audit_log(limit=10)
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(rows[-1]["prev_hash"], rows[-2]["entry_hash"])
        self.assertTrue(len(rows[-1]["entry_hash"]) == 64)

    def test_verify_audit_export_json_passes(self):
        """Exported JSON should pass chain and digest verification."""
        self.safety.check("rm notes.txt")
        self.safety.check("rm notes.txt")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "audit.json")
            self.safety.export_audit_json(path, limit=10)
            self.safety.write_export_digest(path)

            result = self.safety.verify_audit_export(path)
            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["entries_checked"], 2)
            self.assertTrue(result["digest_ok"])

    def test_verify_audit_export_detects_tampering(self):
        """Verification should fail when exported payload is modified."""
        self.safety.check("rm notes.txt")
        self.safety.check("rm notes.txt")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "audit.json")
            self.safety.export_audit_json(path, limit=10)
            self.safety.write_export_digest(path)

            payload = json.loads(open(path, "r", encoding="utf-8").read())
            payload["entries"][0]["reason"] = "tampered"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f)

            result = self.safety.verify_audit_export(path)
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "entry_hash_mismatch")
            self.assertFalse(result["digest_ok"])


class TestTranslator(unittest.TestCase):
    """Tests for intelligence/translator.py."""

    def setUp(self):
        from intelligence.translator import Translator
        self.llm = MagicMock()
        self.context = MagicMock()
        self.history = MagicMock()
        self.context.get_context_summary.return_value = "os=Windows"
        self.history.search_commands.return_value = []
        self.history.get_recent.return_value = []
        self.translator = Translator(self.llm, self.context, self.history)

    def test_local_pattern_safe_input(self):
        """Simple pattern input should use fast local translator path."""
        result = self.translator.translate("create directory logs")
        self.assertEqual(result.source, "local")
        self.assertEqual(result.command, "mkdir logs")

    def test_local_pattern_rejects_shell_metacharacters(self):
        """Unsafe metacharacters should bypass local formatting and use LLM path."""
        self.llm.generate_json.return_value = {
            "command": "echo blocked",
            "confidence": 0.6,
            "explanation": "fallback",
            "is_destructive": False,
            "alternatives": [],
        }
        result = self.translator.translate("delete file report.txt;rm")
        self.assertNotEqual(result.source, "local")
        self.llm.generate_json.assert_called()

    def test_local_pattern_commit_message_is_quoted_safely(self):
        """Commit message with spaces should be rendered as a single safe argument."""
        result = self.translator.translate('commit with message "hello world"')
        self.assertEqual(result.source, "local")
        self.assertIn("git commit -m", result.command)
        self.assertIn("hello world", result.command)

    def test_local_pattern_find_uses_dynamic_builder(self):
        """Find command should be built by dynamic renderer with wildcard pattern."""
        result = self.translator.translate("find files named report")
        self.assertEqual(result.source, "local")
        self.assertTrue("find . -name" in result.command or "dir /s /b" in result.command)

    @patch("platform.system", return_value="Windows")
    def test_update_windows_not_misclassified_as_git_pull(self, _mock_system):
        """'update windows' should map to Windows update flow, not git pull."""
        result = self.translator.translate("update windows")
        self.assertEqual(result.source, "local")
        self.assertEqual(result.command, "winget upgrade --all")

    @patch("platform.system", return_value="Windows")
    def test_copy_folder_from_desktop_to_downloads_resolves_spaced_windows_paths(self, _mock_system):
        """Windows folder copy with spaces should resolve full paths and avoid robocopy arg splitting."""
        fake_engine = MagicMock()
        fake_engine.try_resolve.return_value = None
        fake_engine._resolve_folder.side_effect = lambda name: {
            "desktop": r"C:\Users\lenovo\Desktop",
            "downloads": r"C:\Users\lenovo\Downloads",
        }.get(name.lower())
        fake_engine._search_dir_for.side_effect = (
            lambda directory, name_lower: r"C:\Users\lenovo\Desktop\8th Wall"
            if directory == r"C:\Users\lenovo\Desktop" and name_lower == "8th wall"
            else None
        )
        fake_engine._fuzzy_find_folder.return_value = None
        self.translator._get_smart_open_engine = MagicMock(return_value=fake_engine)

        result = self.translator.translate(
            "make a copy of 8th Wall folder from desktop folder to downloads folder"
        )

        self.assertEqual(result.source, "local")
        self.assertIn("powershell -NoProfile -Command", result.command)
        self.assertIn("Copy-Item", result.command)
        self.assertIn(r"C:\Users\lenovo\Desktop\8th Wall", result.command)
        self.assertIn(r"C:\Users\lenovo\Downloads", result.command)
        self.assertIn("-Recurse -Force", result.command)
        self.assertNotIn("robocopy", result.command.lower())

    @patch("platform.system", return_value="Windows")
    def test_move_folder_from_desktop_to_downloads_resolves_spaced_windows_paths(self, _mock_system):
        """Windows folder move with spaces should resolve full paths and use Move-Item."""
        fake_engine = MagicMock()
        fake_engine.try_resolve.return_value = None
        fake_engine._resolve_folder.side_effect = lambda name: {
            "desktop": r"C:\Users\lenovo\Desktop",
            "downloads": r"C:\Users\lenovo\Downloads",
        }.get(name.lower())
        fake_engine._search_dir_for.side_effect = (
            lambda directory, name_lower: r"C:\Users\lenovo\Desktop\8th Wall"
            if directory == r"C:\Users\lenovo\Desktop" and name_lower == "8th wall"
            else None
        )
        fake_engine._fuzzy_find_folder.return_value = None
        self.translator._get_smart_open_engine = MagicMock(return_value=fake_engine)

        result = self.translator.translate(
            "move 8th wall folder from desktop folder to downloads folder"
        )

        self.assertEqual(result.source, "local")
        self.assertIn("powershell -NoProfile -Command", result.command)
        self.assertIn("Move-Item", result.command)
        self.assertIn(r"C:\Users\lenovo\Desktop\8th Wall", result.command)
        self.assertIn(r"C:\Users\lenovo\Downloads", result.command)
        self.assertIn("-Force", result.command)
        self.assertNotIn("robocopy", result.command.lower())

    @patch("platform.system", return_value="Windows")
    def test_copy_folder_from_desktop_to_downloads_without_repeating_folder_keyword(self, _mock_system):
        """Windows copy should match phrasing that omits repeated folder keywords for roots."""
        fake_engine = MagicMock()
        fake_engine.try_resolve.return_value = None
        fake_engine._resolve_folder.side_effect = lambda name: {
            "desktop": r"C:\Users\lenovo\Desktop",
            "downloads": r"C:\Users\lenovo\Downloads",
        }.get(name.lower())
        fake_engine._search_dir_for.return_value = None
        fake_engine._fuzzy_find_folder.side_effect = (
            lambda name_lower, search_root=None: r"C:\Users\lenovo\Desktop\8th Wall"
            if search_root == r"C:\Users\lenovo\Desktop" and name_lower == "8thwall"
            else None
        )
        self.translator._get_smart_open_engine = MagicMock(return_value=fake_engine)

        result = self.translator.translate(
            "copy 8thwall folder from desktop to downloads folder"
        )

        self.assertEqual(result.source, "local")
        self.assertIn("powershell -NoProfile -Command", result.command)
        self.assertIn("Copy-Item", result.command)
        self.assertIn(r"C:\Users\lenovo\Desktop\8th Wall", result.command)
        self.assertIn(r"C:\Users\lenovo\Downloads", result.command)
        self.assertIn("-Recurse -Force", result.command)
        self.assertNotIn("robocopy", result.command.lower())

    @patch("platform.system", return_value="Windows")
    def test_move_folder_from_desktop_to_downloads_without_repeating_folder_keyword(self, _mock_system):
        """Windows move should match phrasing that omits repeated folder keywords for roots."""
        fake_engine = MagicMock()
        fake_engine.try_resolve.return_value = None
        fake_engine._resolve_folder.side_effect = lambda name: {
            "desktop": r"C:\Users\lenovo\Desktop",
            "downloads": r"C:\Users\lenovo\Downloads",
        }.get(name.lower())
        fake_engine._search_dir_for.return_value = None
        fake_engine._fuzzy_find_folder.side_effect = (
            lambda name_lower, search_root=None: r"C:\Users\lenovo\Desktop\8th Wall"
            if search_root == r"C:\Users\lenovo\Desktop" and name_lower == "8thwall"
            else None
        )
        self.translator._get_smart_open_engine = MagicMock(return_value=fake_engine)

        result = self.translator.translate(
            "move 8thwall folder from desktop to downloads folder"
        )

        self.assertEqual(result.source, "local")
        self.assertIn("powershell -NoProfile -Command", result.command)
        self.assertIn("Move-Item", result.command)
        self.assertIn(r"C:\Users\lenovo\Desktop\8th Wall", result.command)
        self.assertIn(r"C:\Users\lenovo\Downloads", result.command)
        self.assertIn("-Force", result.command)
        self.assertNotIn("robocopy", result.command.lower())


class TestErrorFixer(unittest.TestCase):
    """Tests for intelligence/error_fixer.py."""

    def setUp(self):
        from intelligence.error_fixer import ErrorFixer
        self.fixer = ErrorFixer(
            llm_client=MagicMock(),
            history_store=MagicMock(),
            context_manager=MagicMock(),
        )
        self.fixer.history.find_fix.return_value = None

    def test_pip_install_fix(self):
        """Test Python module not found auto-fix."""
        error = "ModuleNotFoundError: No module named 'flask'"
        result = self.fixer.fix(error, "python app.py")
        self.assertIn("pip install", result.fix_command)
        self.assertIn("flask", result.fix_command)
        self.assertGreater(result.confidence, 0.8)

    def test_permission_denied_fix(self):
        """Test permission denied fix."""
        error = "PermissionError: [Errno 13] Permission denied"
        result = self.fixer.fix(error, "cat /etc/shadow")
        self.assertGreater(result.confidence, 0.7)

    def test_git_not_repo_fix(self):
        """Test git not-a-repo fix."""
        error = "fatal: not a git repository"
        result = self.fixer.fix(error, "git status")
        self.assertEqual(result.fix_command, "git init")

    def test_git_push_rejected_fix(self):
        """Test git push rejected fix."""
        error = "error: failed to push some refs to origin"
        result = self.fixer.fix(error, "git push origin main")
        self.assertIn("pull", result.fix_command)

    def test_docker_not_running_fix(self):
        """Test docker daemon not running fix."""
        error = "Cannot connect to the Docker daemon"
        result = self.fixer.fix(error, "docker ps")
        self.assertGreater(result.confidence, 0.9)

    def test_port_in_use_fix(self):
        """Test port in use fix."""
        error = "EADDRINUSE: address already in use :::3000"
        result = self.fixer.fix(error, "npm start")
        self.assertGreater(result.confidence, 0.8)

    def test_npm_module_fix(self):
        """Test missing node module fix."""
        error = "Error: Cannot find module 'express'"
        result = self.fixer.fix(error, "node server.js")
        self.assertIn("npm install", result.fix_command)

    def test_command_not_found_fix(self):
        """Test command not found fix."""
        error = "bash: cargo: command not found"
        result = self.fixer.fix(error, "cargo build")
        self.assertGreater(result.confidence, 0.7)

    def test_disk_full_fix(self):
        """Test disk full error fix."""
        error = "ENOSPC: no space left on device"
        result = self.fixer.fix(error, "npm install")
        self.assertGreater(result.confidence, 0.9)

    def test_ssl_error_fix(self):
        """Test SSL certificate error fix."""
        error = "SSL: CERTIFICATE_VERIFY_FAILED"
        result = self.fixer.fix(error, "pip install flask")
        self.assertGreater(result.confidence, 0.6)

    def test_connection_refused_fix(self):
        """Test connection refused fix."""
        error = "ConnectionRefusedError: [Errno 111] Connection refused"
        result = self.fixer.fix(error, "curl localhost:5000")
        self.assertGreater(result.confidence, 0.5)

    def test_import_error_fix(self):
        """Test import version mismatch fix."""
        error = "ImportError: cannot import name 'HTTPAdapter' from 'requests'"
        result = self.fixer.fix(error, "python script.py")
        self.assertIn("upgrade", result.fix_command.lower())

    def test_unknown_error_falls_to_llm(self):
        """Test that unknown errors fall through to LLM."""
        error = "Some completely unique error 12345"
        self.fixer.llm.generate_json.return_value = {
            "fix_command": "echo fixed",
            "explanation": "test fix",
            "confidence": 0.5,
        }
        result = self.fixer.fix(error, "some_cmd")
        self.fixer.llm.generate_json.assert_called()

    def test_session_stats(self):
        """Test fix session stats tracking."""
        error = "fatal: not a git repository"
        self.fixer.fix(error, "git status")
        stats = self.fixer.get_session_stats()
        self.assertEqual(stats["total"], 1)


class TestExplainer(unittest.TestCase):
    """Tests for intelligence/explainer.py."""

    def setUp(self):
        from intelligence.explainer import Explainer
        self.explainer = Explainer(llm_client=MagicMock(), context_manager=MagicMock())

    def test_offline_ls(self):
        """Test offline explanation for ls."""
        result = self.explainer.explain("ls -la")
        self.assertIsNotNone(result.summary)
        self.assertTrue(len(result.breakdown) > 0)
        self.assertEqual(result.source, "offline")

    def test_offline_git(self):
        """Test offline explanation for git."""
        result = self.explainer.explain("git commit -m 'test'")
        self.assertIsNotNone(result.summary)
        self.assertEqual(result.source, "offline")

    def test_offline_docker(self):
        """Test offline explanation for docker."""
        result = self.explainer.explain("docker run -it ubuntu bash")
        self.assertIsNotNone(result.summary)

    def test_explanation_has_summary(self):
        """Test explanations always have a summary."""
        result = self.explainer.explain("rm -rf /tmp/test")
        self.assertIsNotNone(result.summary)
        self.assertGreater(len(result.summary), 0)


class TestPipelineBuilder(unittest.TestCase):
    """Tests for intelligence/pipeline_builder.py."""

    def setUp(self):
        from intelligence.pipeline_builder import PipelineBuilder
        self.builder = PipelineBuilder(llm_client=MagicMock(), context_manager=MagicMock())

    def test_build_returns_result(self):
        """Test that build returns a PipelineResult."""
        self.builder.llm.generate_json.return_value = {
            "pipeline": "echo test | wc -l",
            "steps": [{"command": "echo test"}, {"command": "wc -l"}],
            "confidence": 0.5,
            "explanation": "test",
        }
        result = self.builder.build("analyze log errors from syslog")
        self.assertIsNotNone(result)

    def test_unknown_pipeline(self):
        """Test unknown pipeline returns something."""
        self.builder.llm.generate_json.return_value = {
            "pipeline": "find . -name '*.log'",
            "steps": [{"command": "find . -name '*.log'"}],
            "confidence": 0.5,
            "explanation": "search for log files",
        }
        result = self.builder.build("do something very specific and unique 12345")
        self.assertIsNotNone(result)


class TestAutocomplete(unittest.TestCase):
    """Tests for intelligence/autocomplete.py."""

    def setUp(self):
        from intelligence.autocomplete import Autocomplete
        self.ac = Autocomplete(history_store=MagicMock(), context_manager=MagicMock())
        self.ac.history.get_recent.return_value = []

    def test_complete_returns_list(self):
        """Test that completion returns a list."""
        results = self.ac.complete("gi")
        self.assertIsInstance(results, list)

    def test_empty_input(self):
        """Test completion with empty input."""
        results = self.ac.complete("")
        self.assertIsInstance(results, list)


class TestSmartOpen(unittest.TestCase):
    """Tests for intelligence/smart_open.py — Smart Open Engine."""

    def setUp(self):
        from intelligence.smart_open import SmartOpenEngine
        self.engine = SmartOpenEngine()

    @patch("platform.system", return_value="Windows")
    def test_open_current_folder(self, _):
        """'open current folder' should open cwd in explorer."""
        from intelligence.smart_open import SmartOpenEngine
        engine = SmartOpenEngine()
        result = engine.try_resolve("open current folder")
        self.assertIsNotNone(result)
        self.assertIn("-encodedcommand", result.command.lower())
        self.assertEqual(result.target_type, "folder")

    @patch("platform.system", return_value="Windows")
    def test_open_file_explorer(self, _):
        """'open file explorer' should launch explorer."""
        from intelligence.smart_open import SmartOpenEngine
        engine = SmartOpenEngine()
        result = engine.try_resolve("open file explorer")
        self.assertIsNotNone(result)
        self.assertEqual(result.target_type, "app")
        self.assertIn("-encodedcommand", result.command.lower())

    @patch("platform.system", return_value="Windows")
    def test_open_chrome(self, _):
        """'open chrome' should launch Chrome."""
        from intelligence.smart_open import SmartOpenEngine
        engine = SmartOpenEngine()
        result = engine.try_resolve("open chrome")
        self.assertIsNotNone(result)
        self.assertEqual(result.target_type, "app")
        self.assertIn("chrome", result.command.lower())

    @patch("platform.system", return_value="Windows")
    def test_open_github_url(self, _):
        """'open github' should open https://github.com."""
        from intelligence.smart_open import SmartOpenEngine
        engine = SmartOpenEngine()
        result = engine.try_resolve("open github")
        self.assertIsNotNone(result)
        self.assertEqual(result.target_type, "url")
        self.assertIn("github.com", result.command)

    @patch("platform.system", return_value="Windows")
    def test_open_explicit_url(self, _):
        """'open https://example.com' should open that URL."""
        from intelligence.smart_open import SmartOpenEngine
        engine = SmartOpenEngine()
        result = engine.try_resolve("open https://example.com")
        self.assertIsNotNone(result)
        self.assertEqual(result.target_type, "url")
        self.assertIn("example.com", result.command)

    @patch("platform.system", return_value="Windows")
    def test_open_settings(self, _):
        """'open settings' should open Windows Settings."""
        from intelligence.smart_open import SmartOpenEngine
        engine = SmartOpenEngine()
        result = engine.try_resolve("open settings")
        self.assertIsNotNone(result)
        self.assertEqual(result.target_type, "system")
        self.assertIn("ms-settings", result.command)

    @patch("platform.system", return_value="Windows")
    def test_open_task_manager(self, _):
        """'open task manager' should open taskmgr."""
        from intelligence.smart_open import SmartOpenEngine
        engine = SmartOpenEngine()
        result = engine.try_resolve("open task manager")
        self.assertIsNotNone(result)
        self.assertIn("taskmgr", result.command)

    @patch("platform.system", return_value="Windows")
    def test_lock_screen_power_command(self, _):
        """'lock screen' should lock the computer."""
        from intelligence.smart_open import SmartOpenEngine
        engine = SmartOpenEngine()
        result = engine.try_resolve("lock screen")
        self.assertIsNotNone(result)
        self.assertEqual(result.target_type, "power")
        self.assertIn("LockWorkStation", result.command)

    @patch("platform.system", return_value="Windows")
    def test_open_downloads_folder(self, _):
        """'open downloads folder' should resolve to Downloads."""
        from intelligence.smart_open import SmartOpenEngine
        engine = SmartOpenEngine()
        result = engine.try_resolve("open downloads folder")
        self.assertIsNotNone(result)
        self.assertEqual(result.target_type, "folder")
        self.assertIn("-encodedcommand", result.command.lower())

    @patch("platform.system", return_value="Windows")
    def test_zip_command(self, _):
        """'zip the logs folder' should generate Compress-Archive."""
        from intelligence.smart_open import SmartOpenEngine
        engine = SmartOpenEngine()
        result = engine.try_resolve("zip the logs folder")
        self.assertIsNotNone(result)
        self.assertIn("Compress-Archive", result.command)

    @patch("platform.system", return_value="Windows")
    def test_unzip_command(self, _):
        """'unzip archive.zip' should generate Expand-Archive."""
        from intelligence.smart_open import SmartOpenEngine
        engine = SmartOpenEngine()
        result = engine.try_resolve("unzip archive.zip")
        self.assertIsNotNone(result)
        self.assertIn("Expand-Archive", result.command)

    def test_non_open_returns_none(self):
        """Non-open inputs should return None."""
        result = self.engine.try_resolve("list all files")
        self.assertIsNone(result)


class TestTranslatorSmartOpen(unittest.TestCase):
    """Test that the translator correctly routes open commands through SmartOpenEngine."""

    def setUp(self):
        from intelligence.translator import Translator
        self.llm = MagicMock()
        self.context = MagicMock()
        self.history = MagicMock()
        self.context.get_context_summary.return_value = "os=Windows"
        self.history.search_commands.return_value = []
        self.history.get_recent.return_value = []
        self.translator = Translator(self.llm, self.context, self.history)

    @patch("platform.system", return_value="Windows")
    def test_open_command_uses_smart_open(self, _):
        """'open downloads folder' should use smart_open source, not LLM."""
        result = self.translator.translate("open downloads folder")
        self.assertEqual(result.source, "smart_open")
        self.assertIn("-encodedcommand", result.command.lower())
        self.assertGreater(result.confidence, 0.8)

    @patch("platform.system", return_value="Windows")
    def test_open_chrome_uses_smart_open(self, _):
        """'open chrome' should use smart_open, not LLM."""
        result = self.translator.translate("open chrome")
        self.assertEqual(result.source, "smart_open")
        self.assertIn("chrome", result.command.lower())

    @patch("platform.system", return_value="Windows")
    def test_lock_uses_smart_open(self, _):
        """'lock screen' power command should be handled by smart_open."""
        result = self.translator.translate("lock screen")
        self.assertEqual(result.source, "smart_open")
        self.assertIn("LockWorkStation", result.command)

    def test_non_open_still_uses_local_patterns(self, ):
        """'create directory logs' should still use local patterns."""
        result = self.translator.translate("create directory logs")
        self.assertEqual(result.source, "local")
        self.assertEqual(result.command, "mkdir logs")


if __name__ == "__main__":
    unittest.main()
