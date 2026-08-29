# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
"""Tests for the Phase 2 (v5.10) daemon-side token streaming:

  * ai_pipe_stream publishes TOKEN frames + one terminal END frame,
  * cooperative cancellation stops generation between tokens,
  * graceful degradation when the SHM stream ring is unavailable,
  * stream_id validation,
  * provider errors surface as ERROR frames.
"""

from __future__ import annotations

import json
import struct
import sys
import threading
from unittest.mock import MagicMock

import pytest

from core.ipc_server import NamedPipeServer
from core.shm_bridge import (
    FRAME_END,
    FRAME_ERROR,
    FRAME_TOKEN,
    SHM_ABI_VERSION,
    SHM_HEADER_SIZE,
    SHM_MAGIC,
    SHM_RING_CAPACITY,
    SHMClientBridge,
)


@pytest.fixture
def fake_ring():
    """In-memory ring with a valid ABI v3 header (no C++ host required)."""
    if sys.platform == "win32":
        pytest.skip("POSIX shm fixture")
    import mmap

    total = SHM_HEADER_SIZE + SHM_RING_CAPACITY
    buf = mmap.mmap(-1, total)
    struct.pack_into("<IIII", buf, 0, SHM_MAGIC, SHM_ABI_VERSION, SHM_RING_CAPACITY, 0)

    bridge = SHMClientBridge.__new__(SHMClientBridge)
    bridge._buf = buf
    bridge._is_connected = True
    bridge._lock = threading.Lock()
    yield bridge
    bridge.close()


def _make_server(ring=None):
    shell = MagicMock()
    server = NamedPipeServer(shell)
    if ring is not None:
        server._stream_ring = ring
        # Short-circuit the lazy attach so tests never touch /dev/shm
        server._get_stream_ring = lambda: ring
    else:
        server._get_stream_ring = lambda: None
    return server, shell


def _drain_frames(ring):
    frames = []
    while True:
        f = ring.read_frame()
        if f is None:
            return frames
        frames.append(f)


class TestAiPipeStream:
    def test_tokens_published_then_end_frame(self, fake_ring):
        server, shell = _make_server(fake_ring)

        def fake_streaming(prompt, system_prompt="", callback=None, **kw):
            for tok in ["Hello", " ", "world"]:
                callback(tok)
            r = MagicMock()
            r.text = "Hello world"
            return r

        shell.llm.generate_streaming.side_effect = fake_streaming

        resp = server._handle_request({
            "jsonrpc": "2.0", "method": "ai_pipe_stream",
            "params": {"directive": "@ai", "prompt": "p", "input_text": "x",
                       "stream_id": 77},
            "id": 1,
        })

        result = resp["result"]
        assert result["streamed"] is True
        assert result["cancelled"] is False
        assert result["tokens"] == 3
        assert result["response"] == "Hello world"

        frames = _drain_frames(fake_ring)
        assert [f for f in frames if f[0] == FRAME_TOKEN] == [
            (FRAME_TOKEN, 77, "Hello"),
            (FRAME_TOKEN, 77, " "),
            (FRAME_TOKEN, 77, "world"),
        ]
        terminal = frames[-1]
        assert terminal[0] == FRAME_END and terminal[1] == 77
        end_doc = json.loads(terminal[2])
        assert end_doc["cancelled"] is False
        assert end_doc["tokens"] == 3

    def test_cancellation_between_tokens(self, fake_ring):
        server, shell = _make_server(fake_ring)

        def fake_streaming(prompt, system_prompt="", callback=None, **kw):
            callback("tok1")
            fake_ring.request_cancel(88)  # host presses Esc mid-stream
            callback("tok2")  # must raise InterruptedError inside on_token
            callback("tok3")  # never reached
            return MagicMock(text="full")

        shell.llm.generate_streaming.side_effect = fake_streaming

        resp = server._handle_request({
            "jsonrpc": "2.0", "method": "ai_pipe_stream",
            "params": {"stream_id": 88}, "id": 2,
        })

        result = resp["result"]
        assert result["streamed"] is True
        assert result["cancelled"] is True
        assert result["tokens"] == 1  # only tok1 made it out

        frames = _drain_frames(fake_ring)
        token_frames = [f for f in frames if f[0] == FRAME_TOKEN]
        assert token_frames == [(FRAME_TOKEN, 88, "tok1")]
        assert frames[-1][0] == FRAME_END
        assert json.loads(frames[-1][2])["cancelled"] is True
        fake_ring.clear_cancel()

    def test_no_ring_degrades_to_blocking(self):
        server, shell = _make_server(ring=None)
        shell.llm.generate.return_value = "blocking answer"

        resp = server._handle_request({
            "jsonrpc": "2.0", "method": "ai_pipe_stream",
            "params": {"stream_id": 5}, "id": 3,
        })

        result = resp["result"]
        assert result["streamed"] is False
        assert result["response"] == "blocking answer"
        shell.llm.generate_streaming.assert_not_called()

    @pytest.mark.parametrize("bad_id", [0, -1, "abc", None, 2**32])
    def test_invalid_stream_id_rejected(self, fake_ring, bad_id):
        server, _ = _make_server(fake_ring)
        resp = server._handle_request({
            "jsonrpc": "2.0", "method": "ai_pipe_stream",
            "params": {"stream_id": bad_id}, "id": 4,
        })
        assert "error" in resp

    def test_provider_exception_emits_error_frame(self, fake_ring):
        server, shell = _make_server(fake_ring)
        shell.llm.generate_streaming.side_effect = RuntimeError("provider exploded")

        resp = server._handle_request({
            "jsonrpc": "2.0", "method": "ai_pipe_stream",
            "params": {"stream_id": 9}, "id": 5,
        })

        result = resp["result"]
        assert result["streamed"] is True
        assert result.get("error") is True
        assert "provider exploded" in result["response"]

        frames = _drain_frames(fake_ring)
        assert frames[-1][0] == FRAME_ERROR
        assert frames[-1][1] == 9
        assert "provider exploded" in frames[-1][2]

    def test_stale_cancel_from_other_stream_ignored(self, fake_ring):
        """A cancel id belonging to a DIFFERENT stream must not abort ours."""
        server, shell = _make_server(fake_ring)
        fake_ring.request_cancel(999)  # stale flag from a previous stream

        def fake_streaming(prompt, system_prompt="", callback=None, **kw):
            callback("a")
            callback("b")
            return MagicMock(text="ab")

        shell.llm.generate_streaming.side_effect = fake_streaming

        resp = server._handle_request({
            "jsonrpc": "2.0", "method": "ai_pipe_stream",
            "params": {"stream_id": 10}, "id": 6,
        })
        assert resp["result"]["cancelled"] is False
        assert resp["result"]["tokens"] == 2
        fake_ring.clear_cancel()

    def test_legacy_ai_pipe_unchanged(self, fake_ring):
        """The blocking ai_pipe path must not be affected by streaming."""
        server, shell = _make_server(fake_ring)
        shell.llm.generate.return_value = "legacy result"

        resp = server._handle_request({
            "jsonrpc": "2.0", "method": "ai_pipe",
            "params": {"directive": "@ai", "input_text": "x"}, "id": 7,
        })
        assert resp["result"]["response"] == "legacy result"
        assert _drain_frames(fake_ring) == []  # nothing leaked onto the ring
