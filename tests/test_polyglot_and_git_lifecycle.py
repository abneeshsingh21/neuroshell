# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Test Suite for NeuroShell Universal Polyglot Code Runner,
Advanced Git Lifecycle Operations, and Plain-English Intent Translation.
"""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from intelligence.translator import Translator
from operations.code_runner import UniversalCodeRunner
from operations.git_ops import GitOps
from operations.github_access import GitHubAccessManager


class TestUniversalCodeRunner:
    """Validates multi-language detection, compilation, and execution."""

    @pytest.fixture
    def test_workspace(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="neuroshell_runner_test_"))
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_identify_all_major_languages(self):
        runner = UniversalCodeRunner()
        assert runner.identify_language("script.py") == "python"
        assert runner.identify_language("main.cpp") == "cpp"
        assert runner.identify_language("source.cc") == "cpp"
        assert runner.identify_language("file.c") == "c"
        assert runner.identify_language("App.java") == "java"
        assert runner.identify_language("main.rs") == "rust"
        assert runner.identify_language("server.go") == "go"
        assert runner.identify_language("index.ts") == "typescript"
        assert runner.identify_language("app.tsx") == "typescript"
        assert runner.identify_language("script.js") == "javascript"
        assert runner.identify_language("Program.cs") == "csharp"
        assert runner.identify_language("main.kt") == "kotlin"
        assert runner.identify_language("app.dart") == "dart"
        assert runner.identify_language("unknown.xyz") == "unknown"

    def test_run_python_file(self, test_workspace):
        runner = UniversalCodeRunner(cwd=test_workspace)
        py_file = test_workspace / "hello.py"
        py_file.write_text("import sys\nprint(f'Hello {sys.argv[1] if len(sys.argv) > 1 else \"World\"}')\n")

        res = runner.run("hello.py", args=["NeuroShell"], interactive=False)
        assert res.success is True
        assert res.exit_code == 0
        assert "Hello NeuroShell" in res.output

    def test_run_non_existent_file(self, test_workspace):
        runner = UniversalCodeRunner(cwd=test_workspace)
        res = runner.run("does_not_exist.py", interactive=False)
        assert res.success is False
        assert res.exit_code == 1
        assert "not found" in res.error.lower()


class TestGitLifecycleOperations:
    """Validates commit, rollback, revert, discard, and reflog operations."""

    @pytest.fixture
    def git_repo(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="neuroshell_git_test_"))
        git = GitOps(cwd=temp_dir)
        git._run(["init"])
        git._run(["config", "user.name", "NeuroShell Test"])
        git._run(["config", "user.email", "test@neuroshell.ai"])

        # Initial commit
        (temp_dir / "file1.txt").write_text("initial version")
        git._run(["add", "."])
        git._run(["commit", "-m", "initial commit"])

        yield git, temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_commit_all_and_soft_undo(self, git_repo):
        git, repo_path = git_repo

        # Create new file and commit all
        (repo_path / "feature.txt").write_text("new feature")
        sha = git.commit_all("feat: add feature file")
        assert sha != "?"

        # Verify commit exists in log
        commits = git.log(max_count=2)
        assert len(commits) == 2
        assert commits[0].message == "feat: add feature file"

        # Undo last commit (soft reset)
        res = git.undo_last_commit(mode="soft")
        assert res is not None

        # Commit log should now have only 1 commit
        commits_after = git.log(max_count=2)
        assert len(commits_after) == 1
        assert commits_after[0].message == "initial commit"

        # The feature.txt file MUST still exist! (work was not lost)
        assert (repo_path / "feature.txt").exists()

    def test_revert_commit(self, git_repo):
        git, repo_path = git_repo

        (repo_path / "test_revert.txt").write_text("v1")
        git.commit_all("add revert target")

        # Revert HEAD
        res = git.revert_commit()
        assert res is not None

        # Verify a new revert commit was created
        commits = git.log(max_count=2)
        assert "Revert" in commits[0].message
        assert not (repo_path / "test_revert.txt").exists()

    def test_reflog_history(self, git_repo):
        git, _ = git_repo
        reflog_entries = git.reflog(max_count=5)
        assert isinstance(reflog_entries, list)
        assert len(reflog_entries) > 0


class TestGitHubAccessManagerEnhancements:
    """Validates GitHub CLI repo delete, create, and fork operations."""

    def test_repo_delete_validation(self):
        mgr = GitHubAccessManager(workspace_root=Path.cwd())
        with pytest.raises(ValueError):
            mgr.repo_delete("")

    @patch("subprocess.run")
    def test_repo_delete_invocation(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Deleted")
        mgr = GitHubAccessManager(workspace_root=Path.cwd())

        with patch.object(mgr, "_gh_path", return_value="gh"):
            res = mgr.repo_delete("testowner/testrepo")
            assert "Successfully deleted" in res
            assert mock_run.called


class TestPlainEnglishTranslationSynthesis:
    """Validates natural language intent routing for programming and Git operations."""

    @pytest.fixture
    def translator(self):
        ctx = MagicMock()
        ctx.get_context_summary.return_value = "os=Windows"
        hist = MagicMock()
        hist.search_commands.return_value = []
        hist.get_recent.return_value = []
        return Translator(MagicMock(), ctx, hist)

    def test_translate_git_intents(self, translator):
        res1 = translator.translate("undo last commit")
        assert res1.command == "git reset --soft HEAD~1"

        res2 = translator.translate("reverse last commit")
        assert res2.command == "git reset --soft HEAD~1"

        res3 = translator.translate("revert last commit")
        assert res3.command == "git revert --no-edit HEAD"

        res4 = translator.translate("discard all changes")
        assert "git restore" in res4.command

        res5 = translator.translate("delete repo myuser/myrepo")
        assert "gh repo delete myuser/myrepo --yes" in res5.command

    def test_translate_polyglot_run_intents(self, translator):
        res1 = translator.translate("run main.cpp")
        assert res1.command == "run main.cpp"

        res2 = translator.translate("compile and run solution.cpp")
        assert res2.command == "run solution.cpp"

        res3 = translator.translate("run App.java")
        assert res3.command == "run App.java"

        res4 = translator.translate("execute main.rs")
        assert res4.command == "run main.rs"
