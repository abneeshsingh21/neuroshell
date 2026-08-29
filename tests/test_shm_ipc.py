# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
"""Tests for the shared-memory IPC bridge (ABI v2)."""

import struct
import sys

import pytest

from core.shm_bridge import (
    SHM_ABI_VERSION,
    SHM_HEADER_SIZE,
    SHM_MAGIC,
    SHM_RING_CAPACITY,
    SHMClientBridge,
)


def test_shm_bridge_constants():
    assert SHM_MAGIC == 0x4E455552
    assert SHM_RING_CAPACITY == 8 * 1024 * 1024
    assert SHM_ABI_VERSION == 3
    assert SHM_HEADER_SIZE == 128


def test_shm_bridge_graceful_unconnected():
    bridge = SHMClientBridge()
    # In test environment without active C++ host, should safely report status
    assert isinstance(bridge.is_connected, bool)
    if not bridge.is_connected:
        assert bridge.write_message("test") is False
        assert bridge.read_message() is None
    bridge.close()


@pytest.fixture
def fake_ring(tmp_path, monkeypatch):
    """Create an in-memory ring with a valid ABI v2 header and attach a bridge."""
    if sys.platform == "win32":
        pytest.skip("POSIX shm fixture")

    import mmap

    total = SHM_HEADER_SIZE + SHM_RING_CAPACITY
    buf = mmap.mmap(-1, total)
    struct.pack_into("<IIII", buf, 0, SHM_MAGIC, SHM_ABI_VERSION, SHM_RING_CAPACITY, 0)
    struct.pack_into("<Q", buf, 64, 0)
    struct.pack_into("<Q", buf, 72, 0)
    struct.pack_into("<I", buf, 80, 0)

    bridge = SHMClientBridge.__new__(SHMClientBridge)
    bridge._buf = buf
    bridge._is_connected = True
    import threading

    bridge._lock = threading.Lock()
    yield bridge
    bridge.close()


def test_shm_roundtrip(fake_ring):
    assert fake_ring.write_message('{"event":"x"}') is True
    assert fake_ring.write_message("second") is True
    assert fake_ring.read_message() == '{"event":"x"}'
    assert fake_ring.read_message() == "second"
    assert fake_ring.read_message() is None


def test_shm_wraparound(fake_ring):
    """Messages must survive crossing the ring boundary."""
    payload = "y" * 300_000
    for _ in range(60):  # 60 * ~300KB cycles the 8MB ring twice
        assert fake_ring.write_message(payload) is True
        assert fake_ring.read_message() == payload


def test_shm_oversize_rejected(fake_ring):
    too_big = "z" * (SHM_RING_CAPACITY // 2)
    assert fake_ring.write_message(too_big) is False


def test_shm_utf8_payload(fake_ring):
    msg = '{"cmd":"echo ⌬ NeuroShell — тест 日本語"}'
    assert fake_ring.write_message(msg) is True
    assert fake_ring.read_message() == msg


def test_shm_header_validation_rejects_bad_magic():
    if sys.platform == "win32":
        pytest.skip("POSIX shm fixture")

    import mmap

    total = SHM_HEADER_SIZE + SHM_RING_CAPACITY
    buf = mmap.mmap(-1, total)
    struct.pack_into("<IIII", buf, 0, 0xDEADBEEF, SHM_ABI_VERSION, SHM_RING_CAPACITY, 0)

    bridge = SHMClientBridge.__new__(SHMClientBridge)
    bridge._buf = buf
    assert bridge._validate_header() is False
    buf.close()


# ═══════════════════════════════════════════════════════════
# ABI v3 (Phase 2): token-stream frames + cooperative cancel
# ═══════════════════════════════════════════════════════════

from core.shm_bridge import FRAME_END, FRAME_ERROR, FRAME_TOKEN  # noqa: E402


def test_stream_frame_roundtrip(fake_ring):
    assert fake_ring.write_frame(FRAME_TOKEN, 42, "Hello ") is True
    assert fake_ring.write_frame(FRAME_TOKEN, 42, "world") is True
    assert fake_ring.write_frame(FRAME_END, 42, '{"cancelled": false}') is True

    assert fake_ring.read_frame() == (FRAME_TOKEN, 42, "Hello ")
    assert fake_ring.read_frame() == (FRAME_TOKEN, 42, "world")
    assert fake_ring.read_frame() == (FRAME_END, 42, '{"cancelled": false}')
    assert fake_ring.read_frame() is None


def test_stream_frame_utf8_and_large_ids(fake_ring):
    sid = 0xFFFF_FFF0
    assert fake_ring.write_frame(FRAME_TOKEN, sid, "⌬ café 日本語 😀") is True
    assert fake_ring.read_frame() == (FRAME_TOKEN, sid, "⌬ café 日本語 😀")


def test_stream_frame_error_type(fake_ring):
    assert fake_ring.write_frame(FRAME_ERROR, 7, "provider exploded") is True
    assert fake_ring.read_frame() == (FRAME_ERROR, 7, "provider exploded")


def test_stream_frame_garbage_rejected(fake_ring):
    # Too-short message is not a frame
    assert fake_ring.write_message("abc") is True
    assert fake_ring.read_frame() is None
    # Unknown frame type is refused
    fake_ring.write_frame(99, 1, "bogus")
    assert fake_ring.read_frame() is None


def test_cancel_flag_roundtrip(fake_ring):
    assert fake_ring.cancel_requested() == 0
    fake_ring.request_cancel(1234)
    assert fake_ring.cancel_requested() == 1234
    fake_ring.clear_cancel()
    assert fake_ring.cancel_requested() == 0


def test_cancel_offset_is_84(fake_ring):
    """The cancel flag must live at header offset 84 (C++ ABI contract)."""
    fake_ring.request_cancel(0xABCD1234)
    (raw,) = struct.unpack_from("<I", fake_ring._buf, 84)
    assert raw == 0xABCD1234
    fake_ring.clear_cancel()


def test_frame_binary_layout(fake_ring):
    """Frame bytes must be [u8 type][u32 id LE][payload] — C++ reads them raw."""
    fake_ring.write_frame(FRAME_TOKEN, 0x01020304, "AB")
    raw = fake_ring._read_message_bytes()
    assert raw is not None
    assert raw[0] == FRAME_TOKEN
    assert raw[1:5] == (0x01020304).to_bytes(4, "little")
    assert raw[5:] == b"AB"
