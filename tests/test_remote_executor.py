# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
"""Phase 7 (v5.15): Remote Execution with Local Safety tests.

The transport is injectable, so the full pipeline — local policy gate,
local safety shield, two-phase confirmation, outbound secret detection,
inbound DLP scrubbing, hash-chained audit — is exercised without any
network. SSH argv construction is verified structurally.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.mcp_server import MCPAuditLog  # noqa: E402
from core.remote_executor import (  # noqa: E402
    RemoteExecutor,
    RemoteTarget,
    _looks_like_shell,
)


# ─────────────────────────────────────────────────────────────
# Target parsing
# ─────────────────────────────────────────────────────────────

class TestRemoteTarget:
    def test_full_spec(self):
        t = RemoteTarget.parse("deploy@web-01.prod.example.com:2222")
        assert t.user == "deploy"
        assert t.host == "web-01.prod.example.com"
        assert t.port == 2222
        assert t.label == "deploy@web-01.prod.example.com:2222"
        assert t.ssh_destination() == "deploy@web-01.prod.example.com"

    def test_host_only(self):
        t = RemoteTarget.parse("build-box")
        assert t.user == "" and t.port == 0
        assert t.ssh_destination() == "build-box"

    def test_user_host(self):
        t = RemoteTarget.parse("root@10.0.0.5")
        assert t.user == "root" and t.host == "10.0.0.5"

    def test_bracketed_ipv6(self):
        t = RemoteTarget.parse("admin@[2001:db8::1]:22")
        assert t.host == "2001:db8::1" and t.port == 22

    @pytest.mark.parametrize("bad", [
        "", "   ", "user@", "@host", "host:99999", "host:port",
        "user@host:22:33", "user name@host", "host; rm -rf /",
        "$(evil)@host", "user@host`id`",
    ])
    def test_rejects_malformed_and_injection(self, bad):
        with pytest.raises(ValueError):
            RemoteTarget.parse(bad)


# ─────────────────────────────────────────────────────────────
# Fixtures: executor with a local transport shim (no network)
# ─────────────────────────────────────────────────────────────

@pytest.fixture()
def executor(tmp_path):
    if sys.platform == "win32":
        transport_argv = [
            sys.executable,
            "-c",
            "import sys, subprocess; sys.exit(subprocess.run(sys.argv[1], shell=True).returncode)",
        ]
    else:
        transport_argv = ["bash", "-c"]
    return RemoteExecutor(
        RemoteTarget.parse("tester@fake-host"),
        transport_argv=transport_argv,
        audit=MCPAuditLog(tmp_path / "audit.jsonl"),
    )


# ─────────────────────────────────────────────────────────────
# Local pre-flight gate
# ─────────────────────────────────────────────────────────────

class TestLocalGate:
    def test_safe_command_passes(self, executor):
        g = executor.gate("ls -la")
        assert g.allowed and not g.needs_confirmation
        assert g.risk_level == "SAFE"

    def test_blocked_never_reaches_transport(self, executor, monkeypatch):
        spawned = []
        import subprocess as sp
        real_run = sp.run
        monkeypatch.setattr(sp, "run",
                            lambda *a, **k: spawned.append(a) or real_run(*a, **k))
        r = executor.execute("rm -rf /", confirmed=True)  # confirm must not help
        assert not r.executed
        assert "refused locally" in r.error
        assert spawned == []  # no process was ever spawned

    def test_danger_requires_confirmation(self, executor):
        r = executor.execute("rm -rf /tmp/some_dir")
        assert not r.executed
        assert r.error == "confirmation required"
        assert r.gate.risk_level in ("CAUTION", "DANGER")

    def test_confirmed_danger_executes(self, executor, tmp_path):
        victim = tmp_path / "victim"
        victim.mkdir()
        (victim / "x").write_text("1")
        cmd = f'rmdir /s /q "{victim}"' if sys.platform == "win32" else f"rm -rf {victim}"
        r = executor.execute(cmd, confirmed=True)
        assert r.executed and r.exit_code == 0
        assert not victim.exists()

    def test_outbound_secret_is_flagged(self, executor):
        g = executor.gate("curl -H 'Authorization: Bearer abc123def456ghi789' api")
        assert g.outbound_secret is True

    def test_no_false_secret_flag(self, executor):
        assert executor.gate("ls -la /var/log").outbound_secret is False

    def test_empty_command(self, executor):
        r = executor.execute("   ")
        assert not r.executed and r.error == "empty command"


# ─────────────────────────────────────────────────────────────
# Execution + inbound DLP
# ─────────────────────────────────────────────────────────────

class TestExecution:
    def test_stdout_stderr_and_exit_code(self, executor):
        if sys.platform == "win32":
            cmd = "python -c \"import sys; print('out-line'); sys.stderr.write('err-line\\n'); sys.exit(3)\""
        else:
            cmd = "echo out-line && echo err-line >&2 && exit 3"
        r = executor.execute(cmd)
        assert r.executed
        assert r.exit_code == 3
        assert "out-line" in r.stdout
        assert "err-line" in r.stderr

    def test_inbound_secrets_scrubbed(self, executor):
        r = executor.execute("echo AKIA" + "ABCDEFGHIJKLMNOP")
        assert r.executed
        assert "AKIA" + "ABCDEFGHIJKLMNOP" not in r.stdout
        assert "REDACTED_AWS_ACCESS_KEY" in r.stdout

    def test_github_token_scrubbed_from_stderr(self, executor):
        token = "ghp_" + "a" * 40
        r = executor.execute(f"echo {token} >&2")
        assert token not in r.stderr
        assert "REDACTED_GITHUB_TOKEN" in r.stderr

    def test_timeout_kills_remote_command(self, tmp_path):
        ex = RemoteExecutor(
            RemoteTarget.parse("t@h"),
            transport_argv=["bash", "-c"],
            audit=MCPAuditLog(tmp_path / "a.jsonl"),
            command_timeout=1,
        )
        r = ex.execute("sleep 5")
        assert not r.executed
        assert "timed out" in r.error

    def test_duration_is_measured(self, executor):
        r = executor.execute("sleep 0.1")
        assert r.executed
        assert r.duration_ms >= 90


# ─────────────────────────────────────────────────────────────
# Audit chain
# ─────────────────────────────────────────────────────────────

class TestRemoteAudit:
    def test_full_flow_is_audited_and_chained(self, executor, tmp_path):
        executor.execute("echo hello")                       # executed
        executor.execute("rm -rf /")                         # refused
        executor.execute("rm -rf /tmp/zzz")                  # confirmation_required
        executor.execute("rm -rf /tmp/zzz", confirmed=True)  # executed_confirmed
        ok, n = executor.audit.verify()
        assert ok and n == 4
        events = [json.loads(l)["event"] for l in
                  executor.audit.path.read_text().strip().splitlines()]
        assert events == ["remote_executed", "remote_refused",
                          "remote_confirmation_required",
                          "remote_executed_confirmed"]

    def test_audit_records_target(self, executor):
        executor.execute("echo x")
        entry = json.loads(executor.audit.path.read_text().strip().splitlines()[-1])
        assert entry["target"] == "tester@fake-host"


# ─────────────────────────────────────────────────────────────
# SSH argv construction (structural, no network)
# ─────────────────────────────────────────────────────────────

class TestSSHArgv:
    def test_argv_shape(self, tmp_path):
        ex = RemoteExecutor(RemoteTarget.parse("deploy@host1:2200"))
        argv = ex._build_argv("uptime")
        assert argv[0] == "ssh"
        assert argv[-1] == "uptime"           # command is ONE argv element
        assert argv[-2] == "deploy@host1"
        assert "-p" in argv and argv[argv.index("-p") + 1] == "2200"
        joined = " ".join(argv)
        assert "ControlMaster=auto" in joined
        assert "BatchMode=yes" in joined
        assert "ConnectTimeout=" in joined

    def test_no_port_flag_when_default(self):
        ex = RemoteExecutor(RemoteTarget.parse("host2"))
        argv = ex._build_argv("ls")
        assert "-p" not in argv

    def test_command_not_shell_interpolated_locally(self, tmp_path):
        # A hostile command stays a single argv element — the local shell
        # never interprets it (the remote shell is the execution boundary,
        # and the safety gate has already vetted the string).
        ex = RemoteExecutor(RemoteTarget.parse("u@h"))
        argv = ex._build_argv("echo $(hostname); rm -rf ~")
        assert argv[-1] == "echo $(hostname); rm -rf ~"

    def test_control_dir_permissions(self, tmp_path):
        ex = RemoteExecutor(RemoteTarget.parse("u@h"))
        path = ex._control_path()
        from core.remote_executor import CONTROL_DIR
        assert str(CONTROL_DIR) in path
        if sys.platform == "win32":
            pytest.skip("POSIX directory permissions not enforced on Windows")
        import os
        import stat
        mode = stat.S_IMODE(os.stat(CONTROL_DIR).st_mode)
        assert mode == 0o700


# ─────────────────────────────────────────────────────────────
# CLI heuristics
# ─────────────────────────────────────────────────────────────

class TestShellHeuristic:
    @pytest.mark.parametrize("cmd", [
        "ls -la", "docker ps", "cat /etc/hosts", "systemctl status nginx",
        "df -h | sort", "FOO=bar make", "echo hi > /tmp/x",
    ])
    def test_shell_like(self, cmd):
        assert _looks_like_shell(cmd)

    @pytest.mark.parametrize("text", [
        "show me the largest log files",
        "how much memory is free",
        "restart the web service please",
    ])
    def test_natural_language(self, text):
        assert not _looks_like_shell(text)


# ─────────────────────────────────────────────────────────────
# CLI one-shot mode (through the shim-free parser only)
# ─────────────────────────────────────────────────────────────

class TestCLI:
    def test_invalid_target_exits_2(self, capsys):
        from core.remote_executor import cli_main
        rc = cli_main(["bad target!", "ls"])
        assert rc == 2

    def test_remainder_keeps_command_flags(self):
        # Regression: `nsh host rm -rf dir` must NOT have argparse eat -rf.
        import argparse
        parser = argparse.ArgumentParser(prog="nsh")
        parser.add_argument("target")
        parser.add_argument("command", nargs=argparse.REMAINDER)
        parser.add_argument("--yes", "-y", action="store_true")
        args = parser.parse_args(["--yes", "host1", "rm", "-rf", "/tmp/x"])
        assert args.command == ["rm", "-rf", "/tmp/x"]
        assert args.yes is True

    def test_readonly_role_env_degrades_unknown(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEUROSHELL_REMOTE_ROLE", "galactic_emperor")
        ex = RemoteExecutor(RemoteTarget.parse("u@h"),
                            transport_argv=["bash", "-c"],
                            audit=MCPAuditLog(tmp_path / "a.jsonl"))
        from core.policy_engine import UserRole
        assert ex.policy.role == UserRole.GUEST
