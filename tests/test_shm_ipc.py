# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
import pytest
from core.shm_bridge import SHMClientBridge, SHM_MAGIC, SHM_RING_CAPACITY


def test_shm_bridge_constants():
    assert SHM_MAGIC == 0x4E455552
    assert SHM_RING_CAPACITY == 8 * 1024 * 1024


def test_shm_bridge_graceful_unconnected():
    bridge = SHMClientBridge()
    # In test environment without active C++ server, should safely report status
    assert isinstance(bridge.is_connected, bool)
    if not bridge.is_connected:
        assert bridge.write_message("test") is False
        assert bridge.read_message() is None
    bridge.close()
