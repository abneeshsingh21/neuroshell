# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
"""
NeuroShell High-Performance Shared Memory (SHM) IPC Bridge
Connects to C++20 SHMRingBuffer for sub-50μs zero-copy IPC streaming.
"""

import os
import struct
import sys
import time
from typing import Optional

SHM_RING_CAPACITY = 8 * 1024 * 1024  # 8 MB
SHM_MAGIC = 0x4E455552  # "NEUR"
SHM_WIN_NAME = "Local\\NeuroShell_SHM_Ring"
SHM_POSIX_NAME = "/neuroshell_shm_ring"


class SHMClientBridge:
    def __init__(self):
        self._buf = None
        self._is_connected = False
        self._connect()

    def _connect(self):
        try:
            if sys.platform == "win32":
                import mmap

                # Windows Named Shared Memory
                self._buf = mmap.mmap(0, SHM_RING_CAPACITY + 128, tagname=SHM_WIN_NAME)
                self._is_connected = True
            else:
                import mmap

                # POSIX Shared Memory
                if os.path.exists("/dev/shm" + SHM_POSIX_NAME):
                    fd = os.open("/dev/shm" + SHM_POSIX_NAME, os.O_RDWR)
                    self._buf = mmap.mmap(fd, SHM_RING_CAPACITY + 128)
                    os.close(fd)
                    self._is_connected = True
        except Exception:
            self._is_connected = False

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def write_message(self, message: str) -> bool:
        if not self._is_connected or not self._buf:
            return False

        try:
            data = message.encode("utf-8")
            data_len = len(data)
            if data_len + 4 > SHM_RING_CAPACITY // 2:
                return False

            self._buf.seek(0)
            magic, version, capacity, flags = struct.unpack("<IIII", self._buf.read(16))
            if magic != SHM_MAGIC:
                return False

            # Read cursors at alignment offset 64
            self._buf.seek(64)
            (write_cursor,) = struct.unpack("<Q", self._buf.read(8))
            (read_cursor,) = struct.unpack("<Q", self._buf.read(8))

            # Check capacity
            if (write_cursor - read_cursor) + data_len + 4 > SHM_RING_CAPACITY:
                return False  # Buffer full

            # Write length + payload into circular buffer
            data_offset = 128
            len_bytes = struct.pack("<I", data_len)

            for i in range(4):
                idx = data_offset + ((write_cursor + i) % SHM_RING_CAPACITY)
                self._buf[idx] = len_bytes[i]

            for i in range(data_len):
                idx = data_offset + ((write_cursor + 4 + i) % SHM_RING_CAPACITY)
                self._buf[idx] = data[i]

            # Update write cursor
            self._buf.seek(64)
            self._buf.write(struct.pack("<Q", write_cursor + 4 + data_len))
            return True
        except Exception:
            return False

    def read_message(self) -> Optional[str]:
        if not self._is_connected or not self._buf:
            return None

        try:
            self._buf.seek(64)
            (write_cursor,) = struct.unpack("<Q", self._buf.read(8))
            (read_cursor,) = struct.unpack("<Q", self._buf.read(8))

            if read_cursor >= write_cursor:
                return None

            data_offset = 128
            len_bytes = bytearray(4)
            for i in range(4):
                idx = data_offset + ((read_cursor + i) % SHM_RING_CAPACITY)
                len_bytes[i] = self._buf[idx]

            (data_len,) = struct.unpack("<I", len_bytes)
            if data_len > SHM_RING_CAPACITY // 2:
                # Desync recovery
                self._buf.seek(72)
                self._buf.write(struct.pack("<Q", write_cursor))
                return None

            payload_bytes = bytearray(data_len)
            for i in range(data_len):
                idx = data_offset + ((read_cursor + 4 + i) % SHM_RING_CAPACITY)
                payload_bytes[i] = self._buf[idx]

            # Update read cursor
            self._buf.seek(72)
            self._buf.write(struct.pack("<Q", read_cursor + 4 + data_len))

            return payload_bytes.decode("utf-8", errors="replace")
        except Exception:
            return None

    def close(self):
        if self._buf:
            try:
                self._buf.close()
            except Exception:
                pass
            self._buf = None
        self._is_connected = False
