# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
"""
Regression tests for the v5.8 IPC server hardening:
  * ping/status are no longer serialized behind slow LLM dispatches
  * payload-size DoS guard
  * malformed params rejected with -32602
"""

import json
import threading
import time
from unittest.mock import MagicMock

from core.ipc_server import MAX_PAYLOAD_SIZE, NamedPipeServer


def _make_server():
    shell = MagicMock()
    return NamedPipeServer(shell), shell


def test_ping_not_blocked_by_slow_translate():
    """A slow `translate` (LLM call) must not serialize `ping` behind it."""
    server, shell = _make_server()

    release = threading.Event()

    def slow_translate(query, ctx):
        release.wait(timeout=5)
        result = MagicMock()
        result.command = "ls"
        result.explanation = "x"
        result.confidence = 0.9
        return result

    shell.translator.translate.side_effect = slow_translate

    slow_done = []

    def run_slow():
        server._handle_request(
            {"jsonrpc": "2.0", "method": "translate", "params": {"query": "list"}, "id": 1}
        )
        slow_done.append(True)

    t = threading.Thread(target=run_slow, daemon=True)
    t.start()
    time.sleep(0.1)  # slow request is now in-flight

    start = time.monotonic()
    resp = server._handle_request({"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 2})
    elapsed = time.monotonic() - start

    assert resp["result"] == "pong"
    # Before the fix this waited for the full translate; now it's immediate.
    assert elapsed < 0.5, f"ping serialized behind translate ({elapsed:.2f}s)"

    release.set()
    t.join(timeout=5)
    assert slow_done


def test_stateful_slash_still_serialized():
    """slash commands mutate shell state and must still take the lock."""
    server, shell = _make_server()
    assert "slash" in server._STATEFUL_METHODS

    shell._handle_slash_command.return_value = True
    resp = server._handle_request(
        {"jsonrpc": "2.0", "method": "slash", "params": {"command": "/help"}, "id": 3}
    )
    assert resp["result"]["handled"] is True


def test_invalid_params_type_rejected():
    server, _ = _make_server()
    resp = server._handle_request(
        {"jsonrpc": "2.0", "method": "ping", "params": "not-a-dict", "id": 4}
    )
    assert resp["error"]["code"] == -32602


def test_payload_cap_constant_sane():
    assert MAX_PAYLOAD_SIZE == 10 * 1024 * 1024


def test_batch_request_and_parse_error():
    server, shell = _make_server()

    batch = json.dumps([
        {"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 10},
        {"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 11},
    ])
    resp = server._process_raw_json(batch)
    assert isinstance(resp, list)
    assert [r["id"] for r in resp] == [10, 11]

    bad = server._process_raw_json("{not json")
    assert bad["error"]["code"] == -32700


def test_notification_returns_none():
    server, _ = _make_server()
    resp = server._handle_request({"jsonrpc": "2.0", "method": "ping", "params": {}})
    assert resp is None
