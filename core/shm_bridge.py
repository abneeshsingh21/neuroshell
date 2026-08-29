# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
"""
NeuroShell High-Performance Shared Memory (SHM) IPC Bridge.

Connects to the C++20 SHMRingBuffer (cpp_engine/launcher/shm_ipc.hpp) for
zero-copy IPC streaming. The binary ABI (v2) is:

    offset   0  u32  magic        "NEUR" (0x4E455552)
    offset   4  u32  version      == 2
    offset   8  u32  capacity
    offset  12  u32  flags
    offset  64  u64  write_cursor
    offset  72  u64  read_cursor
    offset  80  u32  message_sequence
    offset 128  u8[] ring data (capacity bytes)

v5.8 improvements:
  * ABI version + capacity validation on connect (rejects mismatched peers).
  * Wrap-aware bulk slice copies replace byte-by-byte Python loops
    (orders of magnitude faster for large payloads).
  * message_sequence is bumped on write to mirror the C++ host behaviour.
"""

from __future__ import annotations

import os
import struct
import sys
import threading

SHM_RING_CAPACITY = 8 * 1024 * 1024  # 8 MB — must match C++ host
SHM_MAGIC = 0x4E455552  # "NEUR"
SHM_ABI_VERSION = 2
SHM_HEADER_SIZE = 128
SHM_WIN_NAME = "Local\\NeuroShell_SHM_Ring"
SHM_POSIX_NAME = "/neuroshell_shm_ring"

_OFF_MAGIC = 0
_OFF_WRITE = 64
_OFF_READ = 72
_OFF_SEQ = 80


class SHMClientBridge:
    """Peer-side attachment to the host-owned shared-memory ring."""

    def __init__(self):
        self._buf = None
        self._is_connected = False
        self._lock = threading.Lock()
        self._connect()

    # ── Connection ────────────────────────────────────────────

    def _connect(self) -> None:
        total = SHM_HEADER_SIZE + SHM_RING_CAPACITY
        try:
            import mmap

            if sys.platform == "win32":
                self._buf = mmap.mmap(-1, total, tagname=SHM_WIN_NAME)
            else:
                path = "/dev/shm" + SHM_POSIX_NAME
                if not os.path.exists(path):
                    return
                fd = os.open(path, os.O_RDWR)
                try:
                    self._buf = mmap.mmap(fd, total)
                finally:
                    os.close(fd)

            if not self._validate_header():
                self.close()
                return
            self._is_connected = True
        except Exception:
            self._is_connected = False
            self._buf = None

    def _validate_header(self) -> bool:
        if self._buf is None:
            return False
        magic, version, capacity, _flags = struct.unpack_from("<IIII", self._buf, _OFF_MAGIC)
        return magic == SHM_MAGIC and version == SHM_ABI_VERSION and capacity == SHM_RING_CAPACITY

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    # ── Cursor helpers ────────────────────────────────────────

    def _get_cursors(self) -> tuple[int, int]:
        (w,) = struct.unpack_from("<Q", self._buf, _OFF_WRITE)
        (r,) = struct.unpack_from("<Q", self._buf, _OFF_READ)
        return w, r

    def _ring_write(self, pos: int, data: bytes) -> None:
        """Wrap-aware bulk copy into the ring."""
        start = pos % SHM_RING_CAPACITY
        first = min(len(data), SHM_RING_CAPACITY - start)
        base = SHM_HEADER_SIZE
        self._buf[base + start : base + start + first] = data[:first]
        if first < len(data):
            self._buf[base : base + len(data) - first] = data[first:]

    def _ring_read(self, pos: int, length: int) -> bytes:
        start = pos % SHM_RING_CAPACITY
        first = min(length, SHM_RING_CAPACITY - start)
        base = SHM_HEADER_SIZE
        out = bytes(self._buf[base + start : base + start + first])
        if first < length:
            out += bytes(self._buf[base : base + length - first])
        return out

    # ── Public API ────────────────────────────────────────────

    def write_message(self, message: str) -> bool:
        if not self._is_connected or self._buf is None:
            return False

        try:
            data = message.encode("utf-8")
            data_len = len(data)
            if data_len + 4 > SHM_RING_CAPACITY // 2:
                return False

            with self._lock:
                write_cursor, read_cursor = self._get_cursors()
                if (write_cursor - read_cursor) + data_len + 4 > SHM_RING_CAPACITY:
                    return False  # Ring full — backpressure

                self._ring_write(write_cursor, struct.pack("<I", data_len))
                self._ring_write(write_cursor + 4, data)

                # Publish: cursor last (matches release semantics on C++ side)
                struct.pack_into("<Q", self._buf, _OFF_WRITE, write_cursor + 4 + data_len)
                (seq,) = struct.unpack_from("<I", self._buf, _OFF_SEQ)
                struct.pack_into("<I", self._buf, _OFF_SEQ, (seq + 1) & 0xFFFFFFFF)
            return True
        except Exception:
            return False

    def read_message(self) -> str | None:
        if not self._is_connected or self._buf is None:
            return None

        try:
            with self._lock:
                write_cursor, read_cursor = self._get_cursors()
                if read_cursor >= write_cursor:
                    return None

                (data_len,) = struct.unpack("<I", self._ring_read(read_cursor, 4))
                if data_len > SHM_RING_CAPACITY // 2 or read_cursor + 4 + data_len > write_cursor:
                    # Desync recovery — fast-forward to writer position
                    struct.pack_into("<Q", self._buf, _OFF_READ, write_cursor)
                    return None

                payload = self._ring_read(read_cursor + 4, data_len)
                struct.pack_into("<Q", self._buf, _OFF_READ, read_cursor + 4 + data_len)

            return payload.decode("utf-8", errors="replace")
        except Exception:
            return None

    def close(self) -> None:
        if self._buf is not None:
            try:
                self._buf.close()
            except Exception:
                pass
            self._buf = None
        self._is_connected = False
