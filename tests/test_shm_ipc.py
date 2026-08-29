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
    assert SHM_ABI_VERSION == 2
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
