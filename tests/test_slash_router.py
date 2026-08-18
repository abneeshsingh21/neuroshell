# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Unit tests for NeuroShell Unified Slash Command Router (/).
"""

import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from main import NeuroShell


@pytest.fixture
def shell_instance(tmp_path, monkeypatch):
    """Instantiate a NeuroShell test instance with mocked background services."""
    monkeypatch.setenv("NEUROSHELL_TEST_MODE", "1")
    shell = NeuroShell()
    shell.wait_for_modules()
    yield shell
    try:
        shell.shutdown()
    except Exception:
        pass


def test_slash_help(shell_instance, capsys):
    """Test /help command displays slash directory."""
    cid = shell_instance.tracer.start_trace()
    handled = shell_instance._handle_slash_command("/help", cid)
    assert handled is True
    out = capsys.readouterr().out
    assert "NEUROSHELL SLASH COMMAND DIRECTORY" in out
    assert "/api-key" in out
    assert "/swarm" in out
    assert "/plan" in out
    assert "/backup" in out


def test_slash_model_list_and_switch(shell_instance):
    """Test /model listing and switching."""
    cid = shell_instance.tracer.start_trace()
    handled = shell_instance._handle_slash_command("/model", cid)
    assert handled is True

    handled = shell_instance._handle_slash_command("/model llama3:8b", cid)
    assert handled is True


def test_slash_plan_mode_lifecycle(shell_instance):
    """Test /plan start, add, status, and finish."""
    cid = shell_instance.tracer.start_trace()
    assert hasattr(shell_instance, "plan_mode")
    
    shell_instance._handle_slash_command("/plan start Build Auth", cid)
    assert shell_instance.plan_mode.is_active is True

    shell_instance._handle_slash_command("/plan add Step 1: JWT tokens", cid)
    plan_text = shell_instance.plan_mode.get_current_plan()
    assert "Step 1: JWT tokens" in plan_text

    shell_instance._handle_slash_command("/plan status", cid)
    shell_instance._handle_slash_command("/plan finish", cid)
    assert shell_instance.plan_mode.is_active is False


def test_slash_clip_operations(shell_instance):
    """Test /clip copy, paste, history, and last."""
    cid = shell_instance.tracer.start_trace()
    assert hasattr(shell_instance, "ext_clipboard")

    shell_instance._handle_slash_command("/clip copy echo 'Hello World'", cid)
    pasted = shell_instance.ext_clipboard.paste()
    assert "echo 'Hello World'" in pasted

    shell_instance._last_command = "git status"
    shell_instance._handle_slash_command("/clip last", cid)
    assert shell_instance.ext_clipboard.paste() == "git status"

    shell_instance._handle_slash_command("/clip history", cid)


def test_slash_record_lifecycle(shell_instance, tmp_path, monkeypatch):
    """Test /record start, list, and stop."""
    cid = shell_instance.tracer.start_trace()
    assert hasattr(shell_instance, "ext_recorder")

    import extensions.session_recorder as rec_mod
    monkeypatch.setattr(rec_mod, "RECORDINGS_DIR", tmp_path / "recordings")
    (tmp_path / "recordings").mkdir(parents=True, exist_ok=True)

    shell_instance._handle_slash_command("/record start TestRecording", cid)
    assert shell_instance.ext_recorder.is_recording is True

    shell_instance.ext_recorder.record_input("ls -la")
    shell_instance.ext_recorder.record_output("file1.txt\nfile2.txt")

    shell_instance._handle_slash_command("/record list", cid)
    shell_instance._handle_slash_command("/record stop", cid)
    assert shell_instance.ext_recorder.is_recording is False


def test_slash_profile_management(shell_instance, tmp_path):
    """Test /profile list, create, switch, and delete."""
    cid = shell_instance.tracer.start_trace()
    assert hasattr(shell_instance, "workspace_profiles")

    target_dir = str(tmp_path / "my_project")
    Path(target_dir).mkdir(parents=True, exist_ok=True)

    shell_instance._handle_slash_command("/profile list", cid)
    shell_instance._handle_slash_command(f"/profile create WebProject {target_dir}", cid)

    p = shell_instance.workspace_profiles.get(target_dir)
    assert p is not None
    assert p.name == "WebProject"

    shell_instance._handle_slash_command(f"/profile switch {target_dir}", cid)
    assert shell_instance.workspace_profiles.get_active() is not None

    shell_instance._handle_slash_command(f"/profile delete {target_dir}", cid)


def test_slash_jobs_and_snapshots(shell_instance):
    """Test /jobs and /snapshots listing."""
    cid = shell_instance.tracer.start_trace()
    
    handled_jobs = shell_instance._handle_slash_command("/jobs list", cid)
    assert handled_jobs is True

    handled_snaps = shell_instance._handle_slash_command("/snapshots list", cid)
    assert handled_snaps is True


def test_slash_search(shell_instance):
    """Test /search query."""
    cid = shell_instance.tracer.start_trace()
    handled = shell_instance._handle_slash_command("/search main", cid)
    assert handled is True


def test_slash_git_status(shell_instance):
    """Test /git commands."""
    cid = shell_instance.tracer.start_trace()
    handled = shell_instance._handle_slash_command("/git status", cid)
    assert handled is True


def test_slash_plugins_list(shell_instance):
    """Test /plugins command."""
    cid = shell_instance.tracer.start_trace()
    handled = shell_instance._handle_slash_command("/plugins list", cid)
    assert handled is True


def test_slash_dream_status(shell_instance):
    """Test /dream command."""
    cid = shell_instance.tracer.start_trace()
    handled = shell_instance._handle_slash_command("/dream status", cid)
    assert handled is True


def test_slash_update_check(shell_instance):
    """Test /update command."""
    cid = shell_instance.tracer.start_trace()
    handled = shell_instance._handle_slash_command("/update check", cid)
    assert handled is True

    handled = shell_instance._handle_slash_command("/update channel beta", cid)
    assert handled is True


def test_slash_notebook_notes(shell_instance):
    """Test /notebook note and show."""
    cid = shell_instance.tracer.start_trace()
    shell_instance._handle_slash_command("/notebook note Deployment completed smoothly", cid)
    handled = shell_instance._handle_slash_command("/notebook show", cid)
    assert handled is True


def test_slash_security(shell_instance):
    """Test /security commands."""
    cid = shell_instance.tracer.start_trace()
    shell_instance._handle_slash_command("/security policy", cid)
    shell_instance._handle_slash_command("/security audit", cid)


def test_slash_theme(shell_instance):
    """Test /theme command."""
    cid = shell_instance.tracer.start_trace()
    handled = shell_instance._handle_slash_command("/theme list", cid)
    assert handled is True


def test_slash_config(shell_instance):
    """Test /config command."""
    cid = shell_instance.tracer.start_trace()
    handled = shell_instance._handle_slash_command("/config show", cid)
    assert handled is True


def test_slash_stats(shell_instance):
    """Test /stats command."""
    cid = shell_instance.tracer.start_trace()
    handled = shell_instance._handle_slash_command("/stats", cid)
    assert handled is True


def test_slash_api_key_direct(shell_instance, tmp_path, monkeypatch):
    """Test /api-key direct assignment with secret encryption."""
    cid = shell_instance.tracer.start_trace()
    handled = shell_instance._handle_slash_command("/api-key groq gsk_sample_test_key_12345", cid)
    assert handled is True
    assert shell_instance.config.llm.provider == "groq"


def test_slash_unknown_command(shell_instance):
    """Test unknown slash command returns True but prints hint."""
    cid = shell_instance.tracer.start_trace()
    handled = shell_instance._handle_slash_command("/nonexistent_cmd_123", cid)
    assert handled is True


def test_slash_process_input_routing(shell_instance):
    """Test process_input seamlessly routes commands starting with '/'."""
    shell_instance.process_input("/theme list")
    shell_instance.process_input("/stats")
