# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
"""
NeuroShell High-Performance Shared Memory (SHM) IPC Bridge.

Connects to the C++20 SHMRingBuffer (cpp_engine/launcher/shm_ipc.hpp) for
zero-copy IPC streaming. The binary ABI (v3) is:

    offset   0  u32  magic            "NEUR" (0x4E455552)
    offset   4  u32  version          == 3
    offset   8  u32  capacity
    offset  12  u32  flags
    offset  64  u64  write_cursor
    offset  72  u64  read_cursor
    offset  80  u32  message_sequence
    offset  84  u32  cancel_stream_id (consumer → producer)
    offset 128  u8[] ring data (capacity bytes)

v5.8 improvements:
  * ABI version + capacity validation on connect (rejects mismatched peers).
  * Wrap-aware bulk slice copies replace byte-by-byte Python loops
    (orders of magnitude faster for large payloads).
  * message_sequence is bumped on write to mirror the C++ host behaviour.

v5.10 (ABI v3, Phase 2 — token streaming):
  * Named rings: the legacy EVENT ring (host → daemon) plus a new STREAM
    ring (daemon → host) that carries AI tokens with sub-frame latency.
  * Binary stream frames [u8 type][u32 stream_id LE][utf-8 text] with
    TOKEN/END/ERROR types; stale-stream frames are discarded by readers.
  * Cooperative cancellation via the cancel_stream_id header field: the
    host publishes the stream id to abort (user pressed Esc) and the
    daemon checks it between tokens, stopping LLM generation mid-flight.
"""

from __future__ import annotations

import os
import struct
import sys
import threading

SHM_RING_CAPACITY = 8 * 1024 * 1024  # 8 MB — must match C++ host
SHM_MAGIC = 0x4E455552  # "NEUR"
SHM_ABI_VERSION = 3
SHM_HEADER_SIZE = 128
SHM_WIN_NAME = "Local\\NeuroShell_SHM_Ring"
SHM_POSIX_NAME = "/neuroshell_shm_ring"
SHM_STREAM_WIN_NAME = "Local\\NeuroShell_SHM_Stream"
SHM_STREAM_POSIX_NAME = "/neuroshell_shm_stream"

_OFF_MAGIC = 0
_OFF_WRITE = 64
_OFF_READ = 72
_OFF_SEQ = 80
_OFF_CANCEL = 84

# Stream-frame types (ABI v3): [u8 type][u32 stream_id LE][utf-8 payload]
FRAME_TOKEN = 1
FRAME_END = 2
FRAME_ERROR = 3


class SHMClientBridge:
    """Peer-side attachment to a host-owned shared-memory ring.

    ABI v3 (Phase 2): rings are named. The default attaches to the legacy
    event ring; pass ``stream=True`` to attach to the daemon→host token
    stream ring instead.
    """

    def __init__(self, stream: bool = False):
        self._buf = None
        self._is_connected = False
        self._lock = threading.Lock()
        self._win_name = SHM_STREAM_WIN_NAME if stream else SHM_WIN_NAME
        self._posix_name = SHM_STREAM_POSIX_NAME if stream else SHM_POSIX_NAME
        self._connect()

    # ── Connection ────────────────────────────────────────────

    def _connect(self) -> None:
        total = SHM_HEADER_SIZE + SHM_RING_CAPACITY
        try:
            import mmap

            if sys.platform == "win32":
                self._buf = mmap.mmap(-1, total, tagname=self._win_name)
            else:
                path = "/dev/shm" + self._posix_name
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

    def _read_message_bytes(self) -> bytes | None:
        """Like read_message but returns raw bytes (frame parsing needs them)."""
        if not self._is_connected or self._buf is None:
            return None
        try:
            with self._lock:
                write_cursor, read_cursor = self._get_cursors()
                if read_cursor >= write_cursor:
                    return None
                (data_len,) = struct.unpack("<I", self._ring_read(read_cursor, 4))
                if data_len > SHM_RING_CAPACITY // 2 or read_cursor + 4 + data_len > write_cursor:
                    struct.pack_into("<Q", self._buf, _OFF_READ, write_cursor)
                    return None
                payload = self._ring_read(read_cursor + 4, data_len)
                struct.pack_into("<Q", self._buf, _OFF_READ, read_cursor + 4 + data_len)
            return payload
        except Exception:
            return None

    # ── ABI v3: token-stream frames (Phase 2) ─────────────────
    # Frame layout inside a normal length-prefixed ring message:
    #   [u8 type][u32 stream_id LE][utf-8 payload]
    # Mirrors SHMRingBuffer::write_frame/read_frame in shm_ipc.hpp.

    def write_frame(self, frame_type: int, stream_id: int, payload: str) -> bool:
        """Producer side (daemon): publish one stream frame."""
        if not self._is_connected or self._buf is None:
            return False
        try:
            data = struct.pack("<BI", frame_type, stream_id) + payload.encode("utf-8")
            data_len = len(data)
            if data_len + 4 > SHM_RING_CAPACITY // 2:
                return False
            with self._lock:
                write_cursor, read_cursor = self._get_cursors()
                if (write_cursor - read_cursor) + data_len + 4 > SHM_RING_CAPACITY:
                    return False  # Ring full — backpressure
                self._ring_write(write_cursor, struct.pack("<I", data_len))
                self._ring_write(write_cursor + 4, data)
                struct.pack_into("<Q", self._buf, _OFF_WRITE, write_cursor + 4 + data_len)
                (seq,) = struct.unpack_from("<I", self._buf, _OFF_SEQ)
                struct.pack_into("<I", self._buf, _OFF_SEQ, (seq + 1) & 0xFFFFFFFF)
            return True
        except Exception:
            return False

    def read_frame(self) -> tuple[int, int, str] | None:
        """Consumer side: returns (type, stream_id, payload) or None."""
        raw = self._read_message_bytes()
        if raw is None or len(raw) < 5:
            return None
        frame_type, stream_id = struct.unpack_from("<BI", raw, 0)
        if frame_type not in (FRAME_TOKEN, FRAME_END, FRAME_ERROR):
            return None
        return frame_type, stream_id, raw[5:].decode("utf-8", errors="replace")

    # ── Cooperative cancellation ──────────────────────────────

    def request_cancel(self, stream_id: int) -> None:
        """Consumer publishes the id of the stream it wants aborted."""
        if self._buf is not None:
            struct.pack_into("<I", self._buf, _OFF_CANCEL, stream_id & 0xFFFFFFFF)

    def cancel_requested(self) -> int:
        """Producer polls this between tokens; non-zero means abort that id."""
        if self._buf is None:
            return 0
        (v,) = struct.unpack_from("<I", self._buf, _OFF_CANCEL)
        return v

    def clear_cancel(self) -> None:
        if self._buf is not None:
            struct.pack_into("<I", self._buf, _OFF_CANCEL, 0)

    def close(self) -> None:
        if self._buf is not None:
            try:
                self._buf.close()
            except Exception:
                pass
            self._buf = None
        self._is_connected = False
