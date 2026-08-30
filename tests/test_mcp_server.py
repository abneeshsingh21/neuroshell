# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
"""Phase 6 (v5.14): MCP Server Mode tests.

Covers the stdio JSON-RPC framing, MCP handshake, tool schemas, the
policy → safety → confirm → execute pipeline, DLP output scrubbing,
read-only scope, and the hash-chained audit log.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.mcp_server import (  # noqa: E402
    MCPAuditLog,
    MCPServer,
    TOOL_DEFINITIONS,
)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

@pytest.fixture()
def server(tmp_path):
    return MCPServer(audit_path=tmp_path / "audit.jsonl")


def rpc(server, method, params=None, mid=1):
    return server.handle_message(
        {"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}
    )


def tool(server, name, arguments, mid=1):
    resp = rpc(server, "tools/call", {"name": name, "arguments": arguments}, mid)
    assert "result" in resp, resp
    result = resp["result"]
    payload = json.loads(result["content"][0]["text"])
    return payload, result.get("isError", False)


# ─────────────────────────────────────────────────────────────
# Protocol / handshake
# ─────────────────────────────────────────────────────────────

class TestProtocol:
    def test_initialize_returns_server_info(self, server):
        resp = rpc(server, "initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1.0"},
        })
        result = resp["result"]
        assert result["serverInfo"]["name"] == "neuroshell"
        assert result["protocolVersion"] == "2025-06-18"
        assert "tools" in result["capabilities"]
        from __version__ import __version__
        assert result["serverInfo"]["version"] == __version__

    def test_initialized_notification_returns_nothing(self, server):
        out = server.handle_message(
            {"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert out is None

    def test_ping(self, server):
        assert rpc(server, "ping")["result"] == {}

    def test_tools_list_matches_definitions(self, server):
        resp = rpc(server, "tools/list")
        names = [t["name"] for t in resp["result"]["tools"]]
        assert names == [t["name"] for t in TOOL_DEFINITIONS]
        assert set(names) == {
            "neuroshell_execute", "neuroshell_translate",
            "neuroshell_explain", "neuroshell_safety_check",
        }
        for t in resp["result"]["tools"]:
            assert t["inputSchema"]["type"] == "object"
            assert t["description"]

    def test_unknown_method_is_error(self, server):
        resp = rpc(server, "bogus/method")
        assert resp["error"]["code"] == -32601

    def test_unknown_notification_is_swallowed(self, server):
        out = server.handle_message(
            {"jsonrpc": "2.0", "method": "notifications/whatever"})
        assert out is None

    def test_invalid_jsonrpc_version_rejected(self, server):
        resp = server.handle_message({"jsonrpc": "1.0", "id": 1, "method": "ping"})
        assert resp["error"]["code"] == -32600

    def test_empty_prompts_and_resources(self, server):
        assert rpc(server, "prompts/list")["result"] == {"prompts": []}
        assert rpc(server, "resources/list")["result"] == {"resources": []}

    def test_unknown_tool_name(self, server):
        payload, is_error = tool(server, "not_a_tool", {})
        assert is_error and "Unknown tool" in payload["error"]


# ─────────────────────────────────────────────────────────────
# neuroshell_safety_check
# ─────────────────────────────────────────────────────────────

class TestSafetyCheck:
    def test_safe_command(self, server):
        payload, is_error = tool(server, "neuroshell_safety_check",
                                 {"command": "ls -la"})
        assert not is_error
        assert payload["risk_level"] == "SAFE"
        assert payload["blocked"] is False

    def test_rm_rf_root_blocked(self, server):
        payload, _ = tool(server, "neuroshell_safety_check",
                          {"command": "rm -rf /"})
        assert payload["risk_level"] == "BLOCKED"
        assert payload["blocked"] is True

    def test_recursive_delete_flagged(self, server):
        payload, _ = tool(server, "neuroshell_safety_check",
                          {"command": "rm -rf build/"})
        assert payload["risk_level"] in ("CAUTION", "DANGER")
        assert payload["needs_confirmation"] is True

    def test_empty_command_rejected(self, server):
        payload, is_error = tool(server, "neuroshell_safety_check",
                                 {"command": "   "})
        assert is_error


# ─────────────────────────────────────────────────────────────
# neuroshell_execute: the safety pipeline
# ─────────────────────────────────────────────────────────────

class TestExecute:
    def test_safe_command_executes(self, server):
        payload, is_error = tool(server, "neuroshell_execute",
                                 {"command": "echo mcp-test-42"})
        assert not is_error
        assert payload["exit_code"] == 0
        assert "mcp-test-42" in payload["stdout"]
        assert payload["risk_level"] == "SAFE"

    def test_blocked_command_never_executes_even_confirmed(self, server):
        payload, is_error = tool(server, "neuroshell_execute",
                                 {"command": "rm -rf /", "confirm": True})
        assert is_error
        assert "BLOCKED" in payload["error"]
        assert payload["risk_level"] == "BLOCKED"

    def test_danger_requires_two_phase_confirm(self, server, tmp_path):
        victim = tmp_path / "victim_dir"
        victim.mkdir()
        (victim / "f.txt").write_text("data")
        cmd = f'rmdir /s /q "{victim}"' if sys.platform == "win32" else f"rm -rf {victim}"

        payload, is_error = tool(server, "neuroshell_execute", {"command": cmd})
        assert is_error
        assert "Confirmation required" in payload["error"]
        assert "risk_level" in payload
        assert victim.exists()  # phase 1 must not touch the filesystem

        payload, is_error = tool(server, "neuroshell_execute",
                                 {"command": cmd, "confirm": True})
        assert not is_error
        assert payload["exit_code"] == 0
        assert not victim.exists()  # phase 2 actually ran

    def test_cwd_is_respected(self, server, tmp_path):
        (tmp_path / "marker_xyz.txt").write_text("x")
        payload, is_error = tool(server, "neuroshell_execute",
                                 {"command": "ls", "cwd": str(tmp_path)})
        assert not is_error
        assert "marker_xyz.txt" in payload["stdout"]

    def test_nonexistent_cwd_rejected(self, server):
        payload, is_error = tool(server, "neuroshell_execute",
                                 {"command": "ls", "cwd": "/no/such/dir/xyz"})
        assert is_error and "cwd" in payload["error"]

    def test_output_is_dlp_scrubbed(self, server):
        secret = "AKIA" + "ABCDEFGHIJKLMNOP"
        payload, is_error = tool(server, "neuroshell_execute",
                                 {"command": f"echo {secret}"})
        assert not is_error
        assert secret not in payload["stdout"]
        assert "REDACTED" in payload["stdout"]

    def test_missing_command_rejected(self, server):
        payload, is_error = tool(server, "neuroshell_execute", {})
        assert is_error

    def test_timeout_is_clamped(self, server):
        # Absurd timeout must be clamped, not honored.
        payload, is_error = tool(server, "neuroshell_execute",
                                 {"command": "echo ok", "timeout": 99999})
        assert not is_error and payload["exit_code"] == 0


# ─────────────────────────────────────────────────────────────
# Read-only scope
# ─────────────────────────────────────────────────────────────

class TestReadOnly:
    def test_readonly_blocks_execute_but_not_checks(self, tmp_path):
        srv = MCPServer(audit_path=tmp_path / "a.jsonl", read_only=True)
        payload, is_error = tool(srv, "neuroshell_execute", {"command": "echo hi"})
        assert is_error and "read-only" in payload["error"]

        payload, is_error = tool(srv, "neuroshell_safety_check",
                                 {"command": "ls"})
        assert not is_error and payload["risk_level"] == "SAFE"

    def test_readonly_env_flag(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEUROSHELL_MCP_READONLY", "1")
        srv = MCPServer(audit_path=tmp_path / "a.jsonl")
        assert srv.read_only is True
        monkeypatch.setenv("NEUROSHELL_MCP_READONLY", "0")
        srv2 = MCPServer(audit_path=tmp_path / "b.jsonl")
        assert srv2.read_only is False


# ─────────────────────────────────────────────────────────────
# Role scoping
# ─────────────────────────────────────────────────────────────

class TestRoleScope:
    def test_unknown_role_degrades_to_guest(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEUROSHELL_MCP_ROLE", "supreme_leader")
        srv = MCPServer(audit_path=tmp_path / "a.jsonl")
        from core.policy_engine import UserRole
        assert srv.engine.policy.role == UserRole.GUEST

    def test_valid_role_is_used(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEUROSHELL_MCP_ROLE", "devops")
        srv = MCPServer(audit_path=tmp_path / "a.jsonl")
        from core.policy_engine import UserRole
        assert srv.engine.policy.role == UserRole.DEVOPS


# ─────────────────────────────────────────────────────────────
# Hash-chained audit log
# ─────────────────────────────────────────────────────────────

class TestAuditChain:
    def test_entries_are_chained_and_verify(self, tmp_path):
        log = MCPAuditLog(tmp_path / "audit.jsonl")
        h1 = log.record({"tool": "execute", "command": "ls", "decision": "executed"})
        h2 = log.record({"tool": "execute", "command": "pwd", "decision": "executed"})
        assert h1 != h2
        ok, n = log.verify()
        assert ok and n == 2
        lines = (tmp_path / "audit.jsonl").read_text().strip().splitlines()
        assert json.loads(lines[1])["prev_hash"] == h1

    def test_tampering_breaks_the_chain(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = MCPAuditLog(path)
        log.record({"tool": "execute", "command": "ls", "decision": "executed"})
        log.record({"tool": "execute", "command": "pwd", "decision": "executed"})
        # Tamper with the first entry's command
        lines = path.read_text().strip().splitlines()
        entry = json.loads(lines[0])
        entry["command"] = "rm -rf /"
        lines[0] = json.dumps(entry, sort_keys=True)
        path.write_text("\n".join(lines) + "\n")
        ok, _ = MCPAuditLog(path).verify()
        assert not ok

    def test_chain_survives_reopen(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        MCPAuditLog(path).record({"a": 1})
        log2 = MCPAuditLog(path)  # new instance picks up tail hash
        log2.record({"b": 2})
        ok, n = log2.verify()
        assert ok and n == 2

    def test_refusals_are_audited(self, server):
        tool(server, "neuroshell_execute", {"command": "rm -rf /"})
        ok, n = server.audit.verify()
        assert ok and n >= 1
        entries = [json.loads(l) for l in
                   server.audit.path.read_text().strip().splitlines()]
        assert entries[-1]["decision"] == "refused_blocked"

    def test_two_phase_flow_is_fully_audited(self, server, tmp_path):
        victim = tmp_path / "d"
        victim.mkdir()
        cmd = f"rm -rf {victim}"
        tool(server, "neuroshell_execute", {"command": cmd})
        tool(server, "neuroshell_execute", {"command": cmd, "confirm": True})
        entries = [json.loads(l) for l in
                   server.audit.path.read_text().strip().splitlines()]
        decisions = [e["decision"] for e in entries]
        assert "confirmation_required" in decisions
        assert "executed_confirmed" in decisions
        ok, _ = server.audit.verify()
        assert ok

    def test_empty_log_verifies(self, tmp_path):
        ok, n = MCPAuditLog(tmp_path / "missing.jsonl").verify()
        assert ok and n == 0


# ─────────────────────────────────────────────────────────────
# neuroshell_explain (offline path — no LLM required)
# ─────────────────────────────────────────────────────────────

class TestExplain:
    def test_explain_common_command(self, server):
        payload, is_error = tool(server, "neuroshell_explain",
                                 {"command": "ls -la"})
        assert not is_error
        assert payload["summary"]

    def test_explain_empty_rejected(self, server):
        payload, is_error = tool(server, "neuroshell_explain", {"command": ""})
        assert is_error


# ─────────────────────────────────────────────────────────────
# End-to-end over real stdio (subprocess)
# ─────────────────────────────────────────────────────────────

class TestStdioE2E:
    def test_full_session_over_stdio(self, tmp_path):
        repo = Path(__file__).resolve().parent.parent
        env = dict(os.environ)
        env["PYTHONPATH"] = str(repo)
        script = (
            "from pathlib import Path\n"
            "from core.mcp_server import MCPServer\n"
            f"MCPServer(audit_path=Path({str(tmp_path / 'audit.jsonl')!r})).serve_stdio()\n"
        )
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "e2e", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "neuroshell_execute",
                        "arguments": {"command": "echo stdio-e2e-ok"}}},
        ]
        stdin_data = "".join(json.dumps(m) + "\n" for m in messages)
        proc = subprocess.run(
            [sys.executable, "-c", script],
            input=stdin_data.encode(), capture_output=True,
            cwd=str(repo), env=env, timeout=90,
        )
        lines = [l for l in proc.stdout.decode().splitlines() if l.strip()]
        # Every stdout line must be valid JSON-RPC — no banner pollution.
        replies = [json.loads(l) for l in lines]
        by_id = {r.get("id"): r for r in replies}
        assert by_id[1]["result"]["serverInfo"]["name"] == "neuroshell"
        assert len(by_id[2]["result"]["tools"]) == 4
        exec_payload = json.loads(
            by_id[3]["result"]["content"][0]["text"])
        assert exec_payload["exit_code"] == 0
        assert "stdio-e2e-ok" in exec_payload["stdout"]
