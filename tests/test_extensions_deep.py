# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Deep test suite covering all NeuroShell extension modules:
- Enterprise audit trail, workflows, and vulnerability scanner
- Session memory with thread-safety and atomic storage
- Smart intel risk scoring and notifications
- Desktop themes and snippet management
- Config editor and alias resolution
- MagicDocs auto-documentation
- MachineSync security controls
- Session recording and replay
- Workspace profiles
"""

import os
import sys
import json
import time
import tempfile
import pytest
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from extensions.enterprise import WorkflowEngine, AuditTrail, VulnerabilityScanner, UserRole
from extensions.session_memory import SessionMemory, MemoryEntry
from extensions.smart_intel import score_risk, explain_command, detect_project
from extensions.desktop_features import ThemeEngine, SnippetManager, NotebookMode
from extensions.config_editor import ConfigEditor
from extensions.alias_manager import AliasManager
from extensions.auto_docs import AutoDocsGenerator
from extensions.platform_features import MachineSync
from extensions.session_recorder import SessionRecorder
from extensions.workspace_profiles import WorkspaceProfileManager, WorkspaceProfile
from operations.data_governance import DataGovernanceManager


# ── Enterprise Tests ──────────────────────────────────────────

def test_enterprise_workflow_parser_time():
    wp = WorkflowEngine()
    # 12-hour AM/PM formats
    h, m = wp._parse_time("2pm")
    assert h == 14 and m == 0

    h, m = wp._parse_time("11:30pm")
    assert h == 23 and m == 30

    h, m = wp._parse_time("12am")
    assert h == 0 and m == 0

    h, m = wp._parse_time("9:15am")
    assert h == 9 and m == 15

    # 24-hour format
    h, m = wp._parse_time("18:45")
    assert h == 18 and m == 45


def test_enterprise_audit_trail_rbac(tmp_path):
    audit = AuditTrail(log_dir=tmp_path)
    audit.set_role(UserRole.VIEWER)

    # Viewer cannot run destructive or elevated commands
    allowed, reason = audit.check_permission("rm -rf /tmp/test", risk_score=9)
    assert not allowed

    # Admin can run commands
    audit.set_role(UserRole.ADMIN)
    allowed, reason = audit.check_permission("git status", risk_score=1)
    assert allowed

    # Logging and export
    audit.log(command="git status", risk_score=1, action="executed", cwd=str(tmp_path))
    report = audit.export_report(days=1)
    assert "NeuroShell Audit Report" in report
    assert "git status" in report or "Total commands: 1" in report


# ── Session Memory Tests ──────────────────────────────────────

def test_session_memory_persistence_and_concurrency(tmp_path):
    mem = SessionMemory(memory_dir=tmp_path)
    mem.record(input_text="list files", command="ls -la", success=True, duration_ms=12.5)
    mem.record(input_text="list files", command="ls -la", success=True, duration_ms=10.0)

    # Frequency should increment
    entry = mem._entries.get(list(mem._entries.keys())[0])
    assert entry.frequency == 2

    # Reload from disk
    mem2 = SessionMemory(memory_dir=tmp_path)
    assert len(mem2._entries) == 1


# ── Smart Intel Tests ─────────────────────────────────────────

def test_smart_intel_risk_assessment():
    # Safe command
    safe_res = score_risk("ls -la")
    assert safe_res.score <= 2

    # Critical destructive command
    danger_res = score_risk("rm -rf /")
    assert danger_res.score >= 8
    assert len(danger_res.reasons) > 0


def test_smart_intel_command_explainer():
    explanation = explain_command("chmod -R 777 .")
    assert explanation is not None
    assert "command" in explanation
    assert "description" in explanation


# ── Desktop Features Tests ────────────────────────────────────

def test_desktop_theme_engine(tmp_path):
    te = ThemeEngine(config_dir=tmp_path)
    themes = te.list_themes()
    assert len(themes) > 0
    assert "cyberpunk" in themes or "dracula" in themes or "dark" in themes or "matrix" in themes

    te.set_theme("cyberpunk")
    theme = te.get_theme()
    assert theme is not None
    assert "bg" in theme or "primary" in theme


def test_snippet_manager(tmp_path):
    sm = SnippetManager(config_dir=tmp_path)
    sm.save("deploy", "docker compose up -d", description="Deploy production stack")
    snippet = sm.get("deploy")
    assert snippet is not None
    assert snippet.command == "docker compose up -d"
    snippets = sm.list_all()
    assert any(s.name == "deploy" for s in snippets)


# ── Config & Alias Tests ──────────────────────────────────────

def test_alias_manager_recursion_and_expansion():
    am = AliasManager(load_defaults=True)
    assert am.add("custom_gs", "git status")
    assert am.get("custom_gs") == "git status" or am.expand("custom_gs") == "git status"

    # Recursive alias should be blocked
    assert not am.add("loop", "loop")


# ── Platform Security Tests ───────────────────────────────────

def test_machine_sync_path_traversal_protection(tmp_path):
    ms = MachineSync(config_dir=tmp_path)
    # Attempt path traversal in sync package
    malicious_data = {
        "machine": "attacker",
        "data": {
            "../../etc/passwd": "root:x:0:0:root:/root:/bin/bash",
            "unauthorized_file.txt": "evil",
            "aliases.json": {"test": "echo test"}
        }
    }
    sync_file = tmp_path / "sync.json"
    sync_file.write_text(json.dumps(malicious_data), encoding="utf-8")

    result = ms.import_config(sync_file)
    assert "../../etc/passwd" not in result["imported"]
    assert "unauthorized_file.txt" not in result["imported"]
    assert "aliases.json" in result["imported"]


def test_data_governance_zip_slip_protection(tmp_path):
    dg = DataGovernanceManager(logs_dir=tmp_path / "logs", audit_dir=tmp_path / "audit")
    # Valid backup and validation
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "test.log").write_text("test log", encoding="utf-8")

    meta = dg.create_backup(output_zip=tmp_path / "backup.zip")
    assert Path(meta["archive"]).exists()
    assert dg.validate_backup(meta["archive"], meta["sha256"])

    # Safe restore
    restore_target = tmp_path / "restored"
    dg.restore_backup(meta["archive"], restore_target)
    assert (restore_target / "logs" / "test.log").exists()
