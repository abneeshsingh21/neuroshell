# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
"""Contract tests for the shared history database (Phase 3, v5.11).

The C++ native host (cpp_engine/launcher/history_engine.hpp) and the Python
daemon (core/history.py) now write to the SAME ~/.neuroshell/history.db.
These tests pin the parts of the schema and semantics the C++ side relies
on, so a Python-side refactor cannot silently break the native host:

  * `commands` table columns used by the host INSERT,
  * `commands_fts` FTS5 index shape (content= linkage on rowid),
  * WAL journal mode (concurrent host+daemon access),
  * rows written by an external connection (simulating the host) are
    visible through HistoryStore search,
  * REAL timestamps with fractional seconds are accepted.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from core.history import CommandRecord, HistoryStore


@pytest.fixture()
def store(tmp_path):
    return HistoryStore(db_path=tmp_path / "history.db")


def _host_insert(db_path: Path, command: str, cwd: str, ts: float | None = None) -> None:
    """Replicates the exact INSERT the C++ HistoryEngine performs."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO commands (command, exit_code, cwd, timestamp, source) "
            "VALUES (?, 0, ?, ?, 'native_host')",
            (command, cwd, ts if ts is not None else time.time()),
        )
        conn.execute(
            "INSERT INTO commands_fts(rowid, command, original_nl, cwd, tags) "
            "VALUES (?, ?, '', ?, '')",
            (cur.lastrowid, command, cwd),
        )
        conn.commit()
    finally:
        conn.close()


class TestSchemaContract:
    def test_commands_columns_used_by_host_exist(self, store):
        conn = sqlite3.connect(store.db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(commands)")}
        conn.close()
        # Exactly the columns the native INSERT references
        assert {"command", "exit_code", "cwd", "timestamp", "source"} <= cols

    def test_fts_table_exists_with_expected_shape(self, store):
        conn = sqlite3.connect(store.db_path)
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'commands_fts'"
        ).fetchone()
        conn.close()
        assert row is not None, "commands_fts missing — host FTS inserts would fail"
        sql = row[0]
        assert "fts5" in sql.lower()
        assert "content='commands'" in sql
        assert "content_rowid='id'" in sql

    def test_wal_mode_enabled(self, store):
        store.add_command(CommandRecord(command="x", timestamp=time.time()))
        conn = sqlite3.connect(store.db_path)
        (mode,) = conn.execute("PRAGMA journal_mode").fetchone()
        conn.close()
        assert mode.lower() == "wal"


class TestCrossProcessVisibility:
    def test_python_sees_host_written_rows(self, store):
        store.add_command(CommandRecord(command="warmup", timestamp=time.time()))
        _host_insert(store.db_path, "cmake --build build", "/repo/cpp")

        results = store.search_commands("cmake")
        assert any(r.command == "cmake --build build" for r in results)

    def test_host_rows_carry_native_source_tag(self, store):
        store.add_command(CommandRecord(command="warmup", timestamp=time.time()))
        _host_insert(store.db_path, "ninja -C out", "/repo/cpp")

        conn = sqlite3.connect(store.db_path)
        (src,) = conn.execute(
            "SELECT source FROM commands WHERE command = 'ninja -C out'"
        ).fetchone()
        conn.close()
        assert src == "native_host"

    def test_fractional_timestamps_roundtrip(self, store):
        ts = 1700000000.123456
        store.add_command(CommandRecord(command="frac", timestamp=ts))
        conn = sqlite3.connect(store.db_path)
        (got,) = conn.execute(
            "SELECT timestamp FROM commands WHERE command = 'frac'"
        ).fetchone()
        conn.close()
        assert abs(got - ts) < 1e-6

    def test_concurrent_connections_do_not_lock_out(self, store):
        """WAL + busy timeout: a second writer must not raise 'locked'."""
        store.add_command(CommandRecord(command="a", timestamp=time.time()))
        # Second connection writes while the store's thread-local conn is open
        _host_insert(store.db_path, "b-from-host", "/x")
        store.add_command(CommandRecord(command="c", timestamp=time.time()))
        conn = sqlite3.connect(store.db_path)
        (n,) = conn.execute("SELECT COUNT(*) FROM commands").fetchone()
        conn.close()
        assert n == 3


class TestRankedRecallSemantics:
    """Python-side mirror of the C++ ranking maths (kept in lockstep)."""

    HALF_LIFE_HOURS = 72.0

    @staticmethod
    def _frecency(uses: int, age_hours: float) -> float:
        import math

        if uses <= 0:
            return 0.0
        return math.log(1 + uses) * math.exp(
            -age_hours * math.log(2) / TestRankedRecallSemantics.HALF_LIFE_HOURS
        )

    def test_half_life_is_72_hours(self):
        fresh = self._frecency(5, 0)
        halved = self._frecency(5, 72)
        assert abs(halved / fresh - 0.5) < 0.01

    def test_more_uses_beats_fewer_at_equal_age(self):
        assert self._frecency(10, 24) > self._frecency(2, 24)

    def test_recency_beats_staleness_at_equal_uses(self):
        assert self._frecency(5, 1) > self._frecency(5, 24 * 30)
