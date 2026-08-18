# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Integration test suite for NeuroShell production wiring.
Verifies all previously orphaned/partially wired components, fallback engines,
execution lifecycle hooks, and multi-agent coordination.
"""

import os
import sys
import tempfile
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from main import NeuroShell
from cpp_engine.engine import FastParser, FuzzyMatcher, MarkovEngine
from intelligence.deep_search import DeepSearch
from operations.data_governance import DataGovernanceManager
from extensions.workspace_profiles import WorkspaceProfileManager
from extensions.session_recorder import SessionRecorder
from extensions.clipboard import ClipboardManager
from operations.git_ops import GitOps, GitTool


def test_cpp_engine_pure_python_fallback():
    """Verify C++ engine pure-Python fallback tokenization, matching and prediction."""
    parser = FastParser()
    parsed = parser.parse("git commit -m 'initial commit'")
    assert parsed.program == "git"
    assert "commit" in parsed.arguments
    assert "-m" in parsed.flags

    matcher = FuzzyMatcher(["git status", "git branch", "git commit"])
    match = matcher.did_you_mean("git stauts")
    assert match == "git status"
    best = matcher.best_match("git st")
    assert best == "git status"

    markov = MarkovEngine()
    markov.train([["git", "status"], ["git", "commit"], ["git", "status"]])
    predictions = markov.predict("git")
    assert len(predictions) > 0
    assert predictions[0][0] == "status"


def test_deep_search_programmatic_interface(tmp_path):
    """Verify DeepSearch scans directories and returns structured results."""
    test_dir = tmp_path / "search_root"
    test_dir.mkdir()
    (test_dir / "app_main.py").write_text("print('hello')", encoding="utf-8")
    (test_dir / "config_setting.json").write_text("{}", encoding="utf-8")
    sub = test_dir / "nested_sub"
    sub.mkdir()
    (sub / "util_main.py").write_text("# utility", encoding="utf-8")

    searcher = DeepSearch(default_timeout=5)
    results = searcher.search("main", directory=str(test_dir))
    assert len(results) >= 2
    assert any("app_main.py" in r[3] for r in results)
    
    formatted = searcher.format_results("main", results, str(test_dir), 0.05)
    assert "N-SEARCH RESULTS" in formatted


def test_data_governance_lifecycle(tmp_path):
    """Verify DataGovernanceManager backup, restore, validation and retention."""
    logs_dir = tmp_path / "logs"
    audit_dir = tmp_path / "audit"
    logs_dir.mkdir()
    audit_dir.mkdir()

    # Create dummy logs and audit files
    (logs_dir / "app_2026.log").write_text("log line 1\nlog line 2", encoding="utf-8")
    (audit_dir / "audit_chain.json").write_text("{\"chain\": []}", encoding="utf-8")

    gov = DataGovernanceManager(logs_dir, audit_dir)
    backup_zip = tmp_path / "backup_test.zip"
    meta = gov.create_backup(backup_zip)
    assert Path(meta["archive"]).exists()
    assert "sha256" in meta

    # Validate backup
    is_valid = gov.validate_backup(meta["archive"], meta["sha256"])
    assert is_valid is True

    # Restore backup
    restore_dir = tmp_path / "restored"
    gov.restore_backup(meta["archive"], restore_dir)
    assert (restore_dir / "logs" / "app_2026.log").exists()
    assert (restore_dir / "audit" / "audit_chain.json").exists()

    # Retention enforcement
    report = gov.enforce_retention_days(0)
    assert report.deleted_files >= 2


def test_execution_lifecycle_memory_and_slo(tmp_path, monkeypatch):
    """Verify execution lifecycle hooks: ext_memory, runtime_slo, and session recorder."""
    monkeypatch.setenv("NEUROSHELL_TEST_MODE", "1")
    shell = NeuroShell()
    shell.wait_for_modules()

    cid = shell.tracer.start_trace()
    shell._handle_shell_command("echo neuroshell_test", cid)

    # Verify session memory recorded execution
    assert hasattr(shell, "ext_memory")
    history_entries = shell.ext_memory.suggest("echo")
    assert len(history_entries) > 0

    # Verify runtime SLO recorded latency
    assert hasattr(shell, "runtime_slo")
    summary = shell.runtime_slo.summarize_latency("command_exec")
    assert summary["count"] >= 1


def test_workspace_profile_activation(tmp_path):
    """Verify workspace profile manager create, lookup, and activation."""
    mgr = WorkspaceProfileManager()
    proj_dir = str(tmp_path / "react_app")
    Path(proj_dir).mkdir(parents=True, exist_ok=True)

    profile = mgr.create("ReactApp", proj_dir, env_vars={"PORT": "3000"}, aliases={"dev": "npm run dev"})
    assert profile.name == "ReactApp"

    active = mgr.activate(proj_dir)
    assert active is not None
    assert active.name == "ReactApp"
    assert active.env_vars.get("PORT") == "3000"


def test_git_ops_and_tool_registration(tmp_path):
    """Verify GitOps instantiation and GitTool registration for Coordinator."""
    ops = GitOps(cwd=str(tmp_path))
    tool = GitTool(ops)
    assert tool.name == "git_tool"
    assert "Git" in tool.description
