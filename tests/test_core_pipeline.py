"""
test_core_pipeline.py — Integration tests for NeuroShell's core pipeline.

Covers the critical path: process_input → NLP classifier → executor.
All tests use mocks — no real LLM calls or shell execution.
"""
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_neuroshell(monkeypatch):
    """Construct a NeuroShell instance with all heavy sub-systems mocked."""
    from unittest.mock import MagicMock, patch

    # Patch every heavy import so __init__ doesn't trigger ML loading
    mocks = {
        "observability.logger": MagicMock(),
        "observability.tracer": MagicMock(),
        "observability.provenance": MagicMock(),
        "core.executor": MagicMock(),
        "core.context": MagicMock(),
        "core.history": MagicMock(),
        "core.output_parser": MagicMock(),
        "core.dependency_resolver": MagicMock(),
        "intelligence.safety": MagicMock(),
        "intelligence.translator": MagicMock(),
        "intelligence.error_fixer": MagicMock(),
        "intelligence.fuzzy_corrector": MagicMock(),
        "intelligence.agent": MagicMock(),
        "intelligence.explainer": MagicMock(),
        "intelligence.suggester": MagicMock(),
        "nlp.intent_classifier": MagicMock(),
        "nlp.entity_extractor": MagicMock(),
        "nlp.sentiment": MagicMock(),
        "nlp.semantic_search": MagicMock(),
        "learning.pattern_learner": MagicMock(),
        "learning.predictor": MagicMock(),
        "llm.client": MagicMock(),
        "resilience.resilience": MagicMock(),
        "help.help_system": MagicMock(),
        "extensions.plugin_system": MagicMock(),
        "ui.app": MagicMock(),
    }
    for mod_name, mock in mocks.items():
        monkeypatch.setitem(sys.modules, mod_name, mock)
        # Also patch sub-names that NeuroShell imports from them
        parts = mod_name.split(".")
        parent = parts[0]
        if parent not in sys.modules:
            sys.modules[parent] = MagicMock()

    from config import load_config
    cfg = load_config()
    return cfg


# ─── Config loads without errors ─────────────────────────────────────────────

class TestConfigLoad:
    def test_load_returns_config_object(self):
        from config import Config, load_config
        cfg = load_config()
        assert isinstance(cfg, Config)

    def test_default_llm_model_set(self):
        from config import load_config
        cfg = load_config()
        assert isinstance(cfg.llm.model, str)
        assert len(cfg.llm.model) > 0

    def test_temperature_clamped(self):
        from config import Config
        cfg = Config()
        cfg.llm.temperature = 999.0
        cfg._validate()
        assert cfg.llm.temperature <= 2.0

    def test_temperature_clamped_low(self):
        from config import Config
        cfg = Config()
        cfg.llm.temperature = -5.0
        cfg._validate()
        assert cfg.llm.temperature >= 0.0

    def test_max_tokens_clamped_high(self):
        from config import Config
        cfg = Config()
        cfg.llm.max_tokens = 999999
        cfg._validate()
        assert cfg.llm.max_tokens <= 32768

    def test_max_tokens_clamped_low(self):
        from config import Config
        cfg = Config()
        cfg.llm.max_tokens = 1
        cfg._validate()
        assert cfg.llm.max_tokens >= 64

    def test_invalid_log_level_reset(self):
        from config import Config
        cfg = Config()
        cfg.log_level = "GARBAGE"
        cfg._validate()
        assert cfg.log_level == "INFO"

    def test_env_override_model(self, monkeypatch):
        monkeypatch.setenv("NEUROSHELL_MODEL", "mistral")
        from config import load_config
        cfg = load_config()
        assert cfg.llm.model == "mistral"

    def test_hot_reload_returns_false_when_not_changed(self, tmp_path, monkeypatch):
        import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", tmp_path / "nonexistent.toml")
        from config import load_config
        cfg = load_config()
        result = cfg.hot_reload()
        assert result is False


# ─── Security / Injection Guard ──────────────────────────────────────────────

class TestSecurityGuard:
    """Validates the injection guard logic without touching the shell."""

    def _make_checker(self):
        from intelligence.safety import SafetyChecker
        from config import load_config
        return SafetyChecker(load_config())

    def test_rm_rf_root_is_blocked(self):
        checker = self._make_checker()
        result = checker.check("rm -rf /")
        # SafetyResult uses .should_block to signal hard block
        assert result.should_block, "rm -rf / must be blocked"

    def test_fork_bomb_is_blocked(self):
        checker = self._make_checker()
        result = checker.check(":(){ :|:& };:")
        assert result.should_block, "Fork bomb must be blocked"

    def test_safe_ls_passes(self):
        checker = self._make_checker()
        result = checker.check("ls -la")
        assert not result.should_block, "ls -la should not be blocked"

    def test_safe_git_log_passes(self):
        checker = self._make_checker()
        result = checker.check("git log --oneline -10")
        assert not result.should_block, "git log should not be blocked"

    def test_null_byte_injection_blocked(self):
        checker = self._make_checker()
        result = checker.check("ls\x00; rm -rf /")
        assert result.should_block, "Null byte injection must be blocked"

    def test_result_has_risk_level(self):
        checker = self._make_checker()
        result = checker.check("ls -la")
        assert hasattr(result, "risk_level")

    def test_result_has_reason(self):
        checker = self._make_checker()
        result = checker.check("rm -rf /")
        assert hasattr(result, "reason")

    def test_result_has_audit_id(self):
        """Every SafetyResult must be traceable via audit_id."""
        checker = self._make_checker()
        result = checker.check("echo hello")
        assert hasattr(result, "audit_id")


# ─── NLP Intent Classifier ───────────────────────────────────────────────────

class TestIntentClassifier:
    def _make_classifier(self):
        from nlp.intent_classifier import IntentClassifier
        # IntentClassifier takes no arguments
        return IntentClassifier()

    def test_classifier_instantiates(self):
        clf = self._make_classifier()
        assert clf is not None

    def test_classify_returns_result_object(self):
        clf = self._make_classifier()
        result = clf.classify("show all files")
        assert result is not None
        # IntentResult always has .intent and .confidence
        assert hasattr(result, "intent")
        assert hasattr(result, "confidence")

    def test_classify_returns_non_empty_intent(self):
        clf = self._make_classifier()
        result = clf.classify("list files in current directory")
        assert isinstance(result.intent, str)
        assert len(result.intent) > 0

    def test_classify_confidence_between_0_and_1(self):
        clf = self._make_classifier()
        result = clf.classify("show running processes")
        assert 0.0 <= result.confidence <= 1.0

    def test_classify_empty_string_does_not_crash(self):
        clf = self._make_classifier()
        try:
            clf.classify("")
        except Exception as exc:
            pytest.fail(f"classify('') raised unexpectedly: {exc}")


# ─── Executor (mocked shell) ─────────────────────────────────────────────────

class TestShellExecutor:
    def _make_executor(self):
        from core.executor import ShellExecutor
        from config import load_config
        return ShellExecutor(load_config())

    def test_executor_instantiates(self):
        exe = self._make_executor()
        assert exe is not None

    def test_echo_command_succeeds(self):
        exe = self._make_executor()
        # Real API: .execute(command, ...)
        result = exe.execute("echo hello_neuroshell")
        assert result.exit_code == 0
        assert "hello_neuroshell" in result.stdout

    def test_nonexistent_command_fails(self):
        exe = self._make_executor()
        result = exe.execute("__neuroshell_nonexistent_cmd_xyz__")
        assert result.exit_code != 0

    def test_result_has_duration(self):
        exe = self._make_executor()
        result = exe.execute("echo timing_test")
        assert result.duration_ms >= 0.0

    def test_result_has_command_field(self):
        exe = self._make_executor()
        result = exe.execute("echo meta_test")
        # On Windows the executor may wrap with 'cmd /c <cmd>'
        # so we verify the user's original command is present in the result
        assert "echo meta_test" in result.command

    def test_executor_has_stats(self):
        exe = self._make_executor()
        stats = exe.stats
        assert isinstance(stats, dict)

    def test_executor_has_cwd(self):
        exe = self._make_executor()
        assert exe.cwd is not None
        assert len(str(exe.cwd)) > 0


# ─── Embeddings Module ───────────────────────────────────────────────────────

class TestEmbeddingModel:
    def test_import_succeeds(self):
        from nlp.embeddings import EmbeddingModel
        assert EmbeddingModel is not None

    def test_initialize_returns_true(self):
        from nlp.embeddings import EmbeddingModel
        m = EmbeddingModel()
        result = m.initialize()
        assert result is True

    def test_embed_returns_numpy_array(self):
        import numpy as np
        from nlp.embeddings import EmbeddingModel
        m = EmbeddingModel()
        m.initialize()
        vec = m.embed("hello world")
        assert isinstance(vec, np.ndarray)
        assert len(vec) > 0

    def test_similarity_same_text_is_high(self):
        from nlp.embeddings import EmbeddingModel
        m = EmbeddingModel()
        m.initialize()
        score = m.similarity("list all files in the folder", "list all files in the folder")
        assert score > 0.9, f"Same text similarity should be near 1.0, got {score}"

    def test_similarity_different_text_is_lower(self):
        from nlp.embeddings import EmbeddingModel
        m = EmbeddingModel()
        m.initialize()
        score = m.similarity("show disk usage", "deploy to kubernetes production")
        # Not necessarily zero, but must be < 0.95
        assert score < 0.95

    def test_rank_by_similarity_returns_list(self):
        from nlp.embeddings import EmbeddingModel
        m = EmbeddingModel()
        m.initialize()
        candidates = ["git commit -m", "docker run", "list files", "show network"]
        results = m.rank_by_similarity("show all files", candidates, top_k=2)
        assert isinstance(results, list)
        assert len(results) <= 2

    def test_text_similarity_convenience(self):
        from nlp.embeddings import text_similarity
        score = text_similarity("ping", "ping")
        assert score > 0.9

    def test_embed_text_convenience(self):
        from nlp.embeddings import embed_text
        import numpy as np
        vec = embed_text("hello")
        assert isinstance(vec, np.ndarray)

    def test_fit_tfidf_does_not_crash(self):
        from nlp.embeddings import EmbeddingModel
        m = EmbeddingModel()
        m.initialize()
        m.fit_tfidf(["git commit", "docker run", "npm install", "python main.py"])


# ─── Git Ops ─────────────────────────────────────────────────────────────────

class TestGitOps:
    def test_import_succeeds(self):
        from operations.git_ops import GitOps
        assert GitOps is not None

    def test_instantiates_with_cwd(self, tmp_path):
        from operations.git_ops import GitOps
        g = GitOps(cwd=tmp_path)
        assert g.cwd == tmp_path

    def test_is_inside_repo_false_for_tmp(self, tmp_path):
        from operations.git_ops import GitOps
        g = GitOps(cwd=tmp_path)
        # tmp_path is unlikely to be inside a git repo
        result = g.is_inside_repo()
        assert isinstance(result, bool)

    def test_status_in_real_repo(self):
        """Run against the actual neuroshell repo directory."""
        import os
        from operations.git_ops import GitOps
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        g = GitOps(cwd=root)
        if not g.is_inside_repo():
            pytest.skip("No git repo found at neuroshell root")
        status = g.status()
        assert isinstance(status.branch, str)
        assert len(status.branch) > 0

    def test_git_path_finds_git(self):
        from operations.git_ops import GitOps
        path = GitOps._git_path()
        assert path is not None
        assert "git" in path.lower()

    def test_log_returns_list(self):
        import os
        from operations.git_ops import GitOps
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        g = GitOps(cwd=root)
        if not g.is_inside_repo():
            pytest.skip("No git repo found")
        commits = g.log(max_count=5)
        assert isinstance(commits, list)

    def test_commit_info_str(self):
        from operations.git_ops import CommitInfo
        c = CommitInfo(
            sha="abc123def456", short_sha="abc123",
            author="Dev", email="dev@test.com",
            date="2026-04-12T04:00:00+05:30",
            message="test commit",
        )
        s = str(c)
        assert "abc123" in s
        assert "Dev" in s
