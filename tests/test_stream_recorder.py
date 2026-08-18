# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
import json
import os
import tempfile
import pytest


class PyStreamRecorder:
    def __init__(self, max_chunks=50000):
        self.chunks = []
        self.max_chunks = max_chunks

    def record_input(self, data: str):
        if len(self.chunks) >= self.max_chunks:
            self.chunks.pop(0)
        self.chunks.append((0.1, "i", data))

    def record_output(self, data: str):
        if len(self.chunks) >= self.max_chunks:
            self.chunks.pop(0)
        self.chunks.append((0.2, "o", data))

    def export_asciinema(self, filepath: str) -> bool:
        with open(filepath, "w", encoding="utf-8") as f:
            header = {"version": 2, "width": 120, "height": 35, "title": "NeuroShell Session"}
            f.write(json.dumps(header) + "\n")
            for ts, mode, data in self.chunks:
                f.write(json.dumps([ts, mode, data]) + "\n")
        return True


def test_stream_recorder_lifecycle():
    rec = PyStreamRecorder(max_chunks=5)
    rec.record_input("ls -la")
    rec.record_output("total 48\n-rw-r--r-- 1 user 1024 app.py")
    assert len(rec.chunks) == 2

    with tempfile.NamedTemporaryFile(suffix=".cast", delete=False) as tf:
        temp_path = tf.name

    try:
        assert rec.export_asciinema(temp_path) is True
        assert os.path.exists(temp_path)
        with open(temp_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 3
        header = json.loads(lines[0])
        assert header["version"] == 2
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
