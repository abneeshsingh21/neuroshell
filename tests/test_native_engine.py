# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Unit tests for NeuroShell Native Autonomous AI Engine."""

from intelligence.native_engine import NativeEngine


def test_native_engine_compound_docker_prune():
    """Verify compound intent: 'clean up all stopped docker containers and unused images'."""
    engine = NativeEngine()
    match = engine.translate("clean up all stopped docker containers and unused images")
    assert match is not None
    assert match.action_id == "docker_cleanup_stopped_and_unused_images"
    assert "docker container prune -f" in match.command
    assert "docker image prune -a -f" in match.command
    assert match.confidence >= 0.90
    assert match.is_destructive is True


def test_native_engine_proc_kill_port():
    """Verify dynamic slot filling: port extraction and termination."""
    engine = NativeEngine()
    match = engine.translate("find what process is using port 8080 and kill it")
    assert match is not None
    assert match.action_id == "proc_kill_port"
    assert "8080" in match.command
    assert match.is_destructive is True


def test_native_engine_git_undo_soft():
    """Verify git undo soft commit."""
    engine = NativeEngine()
    match = engine.translate("undo last commit and keep my changes staged")
    assert match is not None
    assert match.action_id == "git_undo_last_commit_keep_staged"
    assert "git reset --soft HEAD~1" in match.command
    assert match.is_destructive is False


def test_native_engine_find_delete_logs():
    """Verify finding and deleting stale log files."""
    engine = NativeEngine()
    match = engine.translate("find all log files older than 30 days and delete them")
    assert match is not None
    assert match.action_id == "fs_find_delete_logs_older_30d"
    assert match.is_destructive is True


def test_native_engine_public_ip():
    """Verify public IP lookup."""
    engine = NativeEngine()
    match = engine.translate("show my public ip address")
    assert match is not None
    assert match.action_id == "net_get_public_ip"
