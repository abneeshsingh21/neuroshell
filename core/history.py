# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell History Store — Production Grade
SQLite-backed storage with FTS5 full-text search, analytics, auto-cleanup,
export/import, and comprehensive session management.
"""

import sqlite3
import time
import json
import csv
import io
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
from config import DB_FILE


# ═══════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════

@dataclass
class CommandRecord:
    """A stored command in history."""
    id: int = 0
    command: str = ""
    exit_code: int = 0
    stdout_preview: str = ""
    stderr_preview: str = ""
    cwd: str = ""
    shell: str = ""
    duration_ms: float = 0
    timestamp: float = 0
    session_id: str = ""
    intent: str = ""
    source: str = ""
    context_hash: str = ""
    was_ai_translated: bool = False
    original_nl: str = ""
    tags: str = ""             # comma-separated user tags
    resources_json: str = ""   # ResourceUsage serialized
    pid: int = 0

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def age_hours(self) -> float:
        return (time.time() - self.timestamp) / 3600 if self.timestamp else 0

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════
# History Store — Production Engine
# ═══════════════════════════════════════════════════════════

class HistoryStore:
    """
    Production-grade SQLite storage for NeuroShell.

    Features:
    - FTS5 full-text search for instant history queries
    - Analytics: failure patterns, productivity metrics, usage trends
    - Auto-cleanup with configurable retention
    - JSON/CSV export and import
    - Session lifecycle management
    - Error fix caching with confidence scoring
    - Feedback loop storage and statistics
    - Thread-safe with WAL mode
    """

    DEFAULT_RETENTION_DAYS = 90
    MAX_PREVIEW_LENGTH = 1000
    MAX_EXPORT_RECORDS = 100_000

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA cache_size=-8000")    # 8MB cache
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
        return self._conn

    def _init_db(self):
        """Create tables, indexes, and FTS5 virtual table."""
        conn = self._get_conn()
        conn.executescript("""
            -- Main commands table
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT NOT NULL,
                exit_code INTEGER DEFAULT 0,
                stdout_preview TEXT DEFAULT '',
                stderr_preview TEXT DEFAULT '',
                cwd TEXT DEFAULT '',
                shell TEXT DEFAULT '',
                duration_ms REAL DEFAULT 0,
                timestamp REAL NOT NULL,
                session_id TEXT DEFAULT '',
                intent TEXT DEFAULT '',
                source TEXT DEFAULT '',
                context_hash TEXT DEFAULT '',
                was_ai_translated INTEGER DEFAULT 0,
                original_nl TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                resources_json TEXT DEFAULT '',
                pid INTEGER DEFAULT 0
            );

            -- Error fixes with confidence
            CREATE TABLE IF NOT EXISTS error_fixes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_pattern TEXT NOT NULL,
                error_message TEXT NOT NULL,
                fix_command TEXT NOT NULL,
                success_count INTEGER DEFAULT 1,
                failure_count INTEGER DEFAULT 0,
                last_used REAL,
                source TEXT DEFAULT 'llm',
                context_hash TEXT DEFAULT '',
                confidence REAL DEFAULT 0.5
            );

            -- Learned patterns
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                pattern_data TEXT NOT NULL,
                frequency INTEGER DEFAULT 1,
                last_seen REAL,
                confidence REAL DEFAULT 0.5
            );

            -- Sessions
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                start_time REAL NOT NULL,
                end_time REAL,
                command_count INTEGER DEFAULT 0,
                cwd TEXT DEFAULT '',
                workspace_type TEXT DEFAULT '',
                error_count INTEGER DEFAULT 0,
                avg_duration_ms REAL DEFAULT 0
            );

            -- Feedback loop
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                suggestion_type TEXT NOT NULL,
                original_input TEXT NOT NULL,
                suggested_output TEXT NOT NULL,
                user_correction TEXT,
                signal TEXT NOT NULL,
                context_hash TEXT DEFAULT '',
                source TEXT DEFAULT '',
                confidence REAL DEFAULT 0
            );

            -- Undo snapshots
            CREATE TABLE IF NOT EXISTS undo_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT NOT NULL,
                command TEXT NOT NULL,
                timestamp REAL NOT NULL,
                file_path TEXT NOT NULL,
                file_content BLOB,
                cwd TEXT DEFAULT ''
            );

            -- Command aliases (user-defined)
            CREATE TABLE IF NOT EXISTS aliases (
                name TEXT PRIMARY KEY,
                expansion TEXT NOT NULL,
                created REAL NOT NULL,
                use_count INTEGER DEFAULT 0
            );

            -- Performance indexes
            CREATE INDEX IF NOT EXISTS idx_commands_timestamp ON commands(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_commands_command ON commands(command);
            CREATE INDEX IF NOT EXISTS idx_commands_session ON commands(session_id);
            CREATE INDEX IF NOT EXISTS idx_commands_exit ON commands(exit_code);
            CREATE INDEX IF NOT EXISTS idx_commands_cwd ON commands(cwd);
            CREATE INDEX IF NOT EXISTS idx_error_fixes_pattern ON error_fixes(error_pattern);
            CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback(suggestion_type);
            CREATE INDEX IF NOT EXISTS idx_feedback_signal ON feedback(signal);
        """)

        # ── Schema migration: add columns that may be missing in older DBs ──
        _migrations = [
            ("commands", "tags", "TEXT DEFAULT ''"),
            ("commands", "resources_json", "TEXT DEFAULT ''"),
            ("commands", "pid", "INTEGER DEFAULT 0"),
            ("commands", "context_hash", "TEXT DEFAULT ''"),
            ("commands", "was_ai_translated", "INTEGER DEFAULT 0"),
            ("commands", "original_nl", "TEXT DEFAULT ''"),
            ("commands", "intent", "TEXT DEFAULT ''"),
            ("commands", "source", "TEXT DEFAULT ''"),
        ]
        for table, col, col_type in _migrations:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Create FTS5 table for full-text search (if not exists)
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS commands_fts USING fts5(
                    command, original_nl, cwd, tags,
                    content='commands',
                    content_rowid='id'
                )
            """)
        except sqlite3.OperationalError:
            pass  # FTS5 not available, degrade gracefully

        conn.commit()

    # ═══════════════════════════════════════════════════════
    # Commands
    # ═══════════════════════════════════════════════════════

    def add_command(self, record: CommandRecord) -> int:
        """Store a command execution record with FTS indexing."""
        conn = self._get_conn()
        cursor = conn.execute("""
            INSERT INTO commands (
                command, exit_code, stdout_preview, stderr_preview,
                cwd, shell, duration_ms, timestamp, session_id,
                intent, source, context_hash, was_ai_translated,
                original_nl, tags, resources_json, pid
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.command, record.exit_code,
            record.stdout_preview[:self.MAX_PREVIEW_LENGTH],
            record.stderr_preview[:self.MAX_PREVIEW_LENGTH],
            record.cwd, record.shell, record.duration_ms,
            record.timestamp or time.time(), record.session_id,
            record.intent, record.source, record.context_hash,
            int(record.was_ai_translated), record.original_nl,
            record.tags, record.resources_json, record.pid,
        ))

        # Index in FTS5
        row_id = cursor.lastrowid
        try:
            conn.execute("""
                INSERT INTO commands_fts(rowid, command, original_nl, cwd, tags)
                VALUES (?, ?, ?, ?, ?)
            """, (row_id, record.command, record.original_nl, record.cwd, record.tags))
        except sqlite3.OperationalError:
            pass  # FTS5 not available

        conn.commit()
        return row_id

    def search_commands(self, query: str, limit: int = 20) -> list[CommandRecord]:
        """Full-text search with FTS5, falling back to LIKE."""
        conn = self._get_conn()

        # Try FTS5 first
        try:
            rows = conn.execute("""
                SELECT c.* FROM commands c
                JOIN commands_fts f ON c.id = f.rowid
                WHERE commands_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (query, limit)).fetchall()
            if rows:
                return [self._row_to_record(r) for r in rows]
        except sqlite3.OperationalError:
            pass

        # Fallback to LIKE search
        rows = conn.execute("""
            SELECT * FROM commands
            WHERE command LIKE ? OR original_nl LIKE ? OR tags LIKE ?
            ORDER BY timestamp DESC LIMIT ?
        """, (f"%{query}%", f"%{query}%", f"%{query}%", limit)).fetchall()

        return [self._row_to_record(r) for r in rows]

    def get_recent(self, limit: int = 20) -> list[CommandRecord]:
        """Get most recent commands."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM commands ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_frequent(self, limit: int = 10) -> list[tuple[str, int]]:
        """Get most frequently used commands."""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT command, COUNT(*) as cnt
            FROM commands GROUP BY command
            ORDER BY cnt DESC LIMIT ?
        """, (limit,)).fetchall()
        return [(r["command"], r["cnt"]) for r in rows]

    def get_by_directory(self, cwd: str, limit: int = 20) -> list[CommandRecord]:
        """Get commands executed in a specific directory."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM commands WHERE cwd = ? ORDER BY timestamp DESC LIMIT ?",
            (cwd, limit)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def tag_command(self, command_id: int, tag: str):
        """Add a tag to a command."""
        conn = self._get_conn()
        row = conn.execute("SELECT tags FROM commands WHERE id = ?", (command_id,)).fetchone()
        if row:
            existing = row["tags"]
            tags = set(existing.split(",")) if existing else set()
            tags.add(tag)
            conn.execute("UPDATE commands SET tags = ? WHERE id = ?", (",".join(tags), command_id))
            conn.commit()

    # ═══════════════════════════════════════════════════════
    # Analytics
    # ═══════════════════════════════════════════════════════

    def get_analytics(self) -> dict:
        """Comprehensive analytics dashboard data."""
        conn = self._get_conn()

        total = conn.execute("SELECT COUNT(*) as c FROM commands").fetchone()["c"]
        errors = conn.execute("SELECT COUNT(*) as c FROM commands WHERE exit_code != 0").fetchone()["c"]

        # Time-based analytics
        last_24h = conn.execute(
            "SELECT COUNT(*) as c FROM commands WHERE timestamp > ?",
            (time.time() - 86400,)
        ).fetchone()["c"]

        last_7d = conn.execute(
            "SELECT COUNT(*) as c FROM commands WHERE timestamp > ?",
            (time.time() - 604800,)
        ).fetchone()["c"]

        # Duration stats
        duration_stats = conn.execute("""
            SELECT
                AVG(duration_ms) as avg_ms,
                MAX(duration_ms) as max_ms,
                MIN(duration_ms) as min_ms,
                SUM(duration_ms) as total_ms
            FROM commands WHERE duration_ms > 0
        """).fetchone()

        # Top error commands
        top_errors = conn.execute("""
            SELECT command, COUNT(*) as cnt, stderr_preview
            FROM commands WHERE exit_code != 0
            GROUP BY command ORDER BY cnt DESC LIMIT 5
        """).fetchall()

        # Most used directories
        top_dirs = conn.execute("""
            SELECT cwd, COUNT(*) as cnt
            FROM commands WHERE cwd != ''
            GROUP BY cwd ORDER BY cnt DESC LIMIT 5
        """).fetchall()

        # AI translation accuracy
        ai_translated = conn.execute(
            "SELECT COUNT(*) as c FROM commands WHERE was_ai_translated = 1"
        ).fetchone()["c"]
        ai_success = conn.execute(
            "SELECT COUNT(*) as c FROM commands WHERE was_ai_translated = 1 AND exit_code = 0"
        ).fetchone()["c"]

        # Hourly distribution
        hourly = conn.execute("""
            SELECT CAST(strftime('%H', timestamp, 'unixepoch', 'localtime') AS INTEGER) as hour,
                   COUNT(*) as cnt
            FROM commands GROUP BY hour ORDER BY hour
        """).fetchall()

        return {
            "total_commands": total,
            "error_count": errors,
            "success_rate": round((total - errors) / max(total, 1) * 100, 1),
            "last_24h": last_24h,
            "last_7d": last_7d,
            "duration": {
                "avg_ms": round(duration_stats["avg_ms"] or 0, 1),
                "max_ms": round(duration_stats["max_ms"] or 0, 1),
                "min_ms": round(duration_stats["min_ms"] or 0, 1),
                "total_s": round((duration_stats["total_ms"] or 0) / 1000, 1),
            },
            "top_errors": [
                {"command": r["command"], "count": r["cnt"], "error": r["stderr_preview"][:100]}
                for r in top_errors
            ],
            "top_directories": [
                {"cwd": r["cwd"], "count": r["cnt"]}
                for r in top_dirs
            ],
            "ai_translation": {
                "total": ai_translated,
                "success": ai_success,
                "accuracy": round(ai_success / max(ai_translated, 1) * 100, 1),
            },
            "hourly_distribution": {r["hour"]: r["cnt"] for r in hourly},
        }

    def get_failure_patterns(self, limit: int = 10) -> list[dict]:
        """Analyze common failure patterns."""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT
                SUBSTR(stderr_preview, 1, 100) as error_fragment,
                COUNT(*) as occurrence,
                GROUP_CONCAT(DISTINCT command) as commands,
                MAX(timestamp) as last_seen
            FROM commands
            WHERE exit_code != 0 AND stderr_preview != ''
            GROUP BY error_fragment
            ORDER BY occurrence DESC LIMIT ?
        """, (limit,)).fetchall()

        return [
            {
                "error": r["error_fragment"],
                "occurrences": r["occurrence"],
                "commands": r["commands"][:200],
                "last_seen": r["last_seen"],
            }
            for r in rows
        ]

    def get_productivity_metrics(self, days: int = 7) -> dict:
        """Productivity metrics over a time period."""
        conn = self._get_conn()
        cutoff = time.time() - (days * 86400)

        daily = conn.execute("""
            SELECT
                date(timestamp, 'unixepoch', 'localtime') as day,
                COUNT(*) as commands,
                SUM(CASE WHEN exit_code = 0 THEN 1 ELSE 0 END) as successes,
                AVG(duration_ms) as avg_ms
            FROM commands WHERE timestamp > ?
            GROUP BY day ORDER BY day
        """, (cutoff,)).fetchall()

        return {
            "days": [
                {
                    "date": r["day"],
                    "commands": r["commands"],
                    "successes": r["successes"],
                    "avg_duration_ms": round(r["avg_ms"] or 0, 1),
                }
                for r in daily
            ],
            "period_days": days,
        }

    # ═══════════════════════════════════════════════════════
    # Error Fixes
    # ═══════════════════════════════════════════════════════

    def find_fix(self, error_pattern: str) -> Optional[dict]:
        """Find a cached fix with confidence scoring."""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT *, 
                   CAST(success_count AS REAL) / (success_count + failure_count) as computed_confidence
            FROM error_fixes
            WHERE error_pattern = ? AND success_count > failure_count
            ORDER BY computed_confidence DESC, success_count DESC LIMIT 1
        """, (error_pattern,)).fetchone()

        return dict(row) if row else None

    def find_fix_fuzzy(self, error_message: str, limit: int = 3) -> list[dict]:
        """Find similar error fixes using substring matching."""
        conn = self._get_conn()
        words = error_message.split()[:5]  # Use first 5 words for matching
        conditions = " AND ".join(f"error_message LIKE '%{w}%'" for w in words if len(w) > 3)
        if not conditions:
            return []

        rows = conn.execute(f"""
            SELECT *,
                   CAST(success_count AS REAL) / (success_count + failure_count) as computed_confidence
            FROM error_fixes
            WHERE {conditions} AND success_count > failure_count
            ORDER BY success_count DESC LIMIT ?
        """, (limit,)).fetchall()

        return [dict(r) for r in rows]

    def store_fix(self, error_pattern: str, error_message: str,
                  fix_command: str, source: str = "llm"):
        """Store a successful error fix."""
        conn = self._get_conn()
        existing = conn.execute(
            "SELECT id FROM error_fixes WHERE error_pattern = ? AND fix_command = ?",
            (error_pattern, fix_command)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE error_fixes SET success_count = success_count + 1, last_used = ? WHERE id = ?",
                (time.time(), existing["id"])
            )
        else:
            conn.execute("""
                INSERT INTO error_fixes (error_pattern, error_message, fix_command, last_used, source)
                VALUES (?, ?, ?, ?, ?)
            """, (error_pattern, error_message, fix_command, time.time(), source))
        conn.commit()

    def mark_fix_failed(self, error_pattern: str, fix_command: str):
        """Mark a fix as failed."""
        conn = self._get_conn()
        conn.execute("""
            UPDATE error_fixes SET failure_count = failure_count + 1
            WHERE error_pattern = ? AND fix_command = ?
        """, (error_pattern, fix_command))
        conn.commit()

    # ═══════════════════════════════════════════════════════
    # Aliases
    # ═══════════════════════════════════════════════════════

    def set_alias(self, name: str, expansion: str):
        """Set a command alias."""
        conn = self._get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO aliases (name, expansion, created, use_count)
            VALUES (?, ?, ?, COALESCE((SELECT use_count FROM aliases WHERE name = ?), 0))
        """, (name, expansion, time.time(), name))
        conn.commit()

    def get_alias(self, name: str) -> Optional[str]:
        """Get alias expansion."""
        conn = self._get_conn()
        row = conn.execute("SELECT expansion FROM aliases WHERE name = ?", (name,)).fetchone()
        if row:
            conn.execute("UPDATE aliases SET use_count = use_count + 1 WHERE name = ?", (name,))
            conn.commit()
            return row["expansion"]
        return None

    def list_aliases(self) -> list[dict]:
        """List all aliases."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM aliases ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def remove_alias(self, name: str) -> bool:
        """Remove an alias."""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM aliases WHERE name = ?", (name,))
        conn.commit()
        return cursor.rowcount > 0

    # ═══════════════════════════════════════════════════════
    # Feedback
    # ═══════════════════════════════════════════════════════

    def store_feedback(self, suggestion_type: str, original_input: str,
                       suggested_output: str, signal: str,
                       user_correction: Optional[str] = None,
                       source: str = "", confidence: float = 0):
        """Store user feedback on a suggestion."""
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO feedback (
                timestamp, suggestion_type, original_input,
                suggested_output, user_correction, signal, source, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (time.time(), suggestion_type, original_input,
              suggested_output, user_correction, signal, source, confidence))
        conn.commit()

    def get_feedback_stats(self) -> dict:
        """Get comprehensive feedback statistics."""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as c FROM feedback").fetchone()["c"]
        if total == 0:
            return {"total": 0, "accept_rate": 0, "edit_rate": 0, "reject_rate": 0}

        accepts = conn.execute("SELECT COUNT(*) as c FROM feedback WHERE signal = 'accept'").fetchone()["c"]
        edits = conn.execute("SELECT COUNT(*) as c FROM feedback WHERE signal = 'edit'").fetchone()["c"]
        rejects = conn.execute("SELECT COUNT(*) as c FROM feedback WHERE signal = 'reject'").fetchone()["c"]

        # By source breakdown
        by_source = conn.execute("""
            SELECT source, signal, COUNT(*) as cnt
            FROM feedback GROUP BY source, signal
        """).fetchall()

        source_stats = {}
        for r in by_source:
            src = r["source"] or "unknown"
            if src not in source_stats:
                source_stats[src] = {}
            source_stats[src][r["signal"]] = r["cnt"]

        return {
            "total": total,
            "accept_rate": round(accepts / total * 100, 1),
            "edit_rate": round(edits / total * 100, 1),
            "reject_rate": round(rejects / total * 100, 1),
            "by_source": source_stats,
        }

    # ═══════════════════════════════════════════════════════
    # Sessions
    # ═══════════════════════════════════════════════════════

    def start_session(self, session_id: str, cwd: str, workspace_type: str = ""):
        """Start a new session."""
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO sessions (id, start_time, cwd, workspace_type)
            VALUES (?, ?, ?, ?)
        """, (session_id, time.time(), cwd, workspace_type))
        conn.commit()

    def end_session(self, session_id: str):
        """End a session with computed statistics."""
        conn = self._get_conn()
        stats = conn.execute("""
            SELECT
                COUNT(*) as cnt,
                SUM(CASE WHEN exit_code != 0 THEN 1 ELSE 0 END) as errors,
                AVG(duration_ms) as avg_ms
            FROM commands WHERE session_id = ?
        """, (session_id,)).fetchone()

        conn.execute("""
            UPDATE sessions SET end_time = ?, command_count = ?,
                   error_count = ?, avg_duration_ms = ?
            WHERE id = ?
        """, (time.time(), stats["cnt"], stats["errors"], stats["avg_ms"] or 0, session_id))
        conn.commit()

    def get_session_history(self, limit: int = 10) -> list[dict]:
        """Get recent session summaries."""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT * FROM sessions ORDER BY start_time DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ═══════════════════════════════════════════════════════
    # Export / Import
    # ═══════════════════════════════════════════════════════

    def export_json(self, filepath: Optional[Path] = None, limit: int = None) -> str:
        """Export command history as JSON."""
        conn = self._get_conn()
        effective_limit = min(limit or self.MAX_EXPORT_RECORDS, self.MAX_EXPORT_RECORDS)
        rows = conn.execute(
            "SELECT * FROM commands ORDER BY timestamp DESC LIMIT ?",
            (effective_limit,)
        ).fetchall()

        records = [dict(r) for r in rows]
        json_str = json.dumps(records, indent=2, default=str)

        if filepath:
            Path(filepath).write_text(json_str, encoding="utf-8")

        return json_str

    def export_csv(self, filepath: Path) -> int:
        """Export command history as CSV. Returns number of records exported."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM commands ORDER BY timestamp DESC LIMIT ?",
            (self.MAX_EXPORT_RECORDS,)
        ).fetchall()

        if not rows:
            return 0

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow(tuple(row))

        Path(filepath).write_text(output.getvalue(), encoding="utf-8")
        return len(rows)

    def import_json(self, filepath: Path) -> int:
        """Import commands from JSON. Returns number of records imported."""
        data = json.loads(Path(filepath).read_text(encoding="utf-8"))
        count = 0
        for item in data:
            record = CommandRecord(
                command=item.get("command", ""),
                exit_code=item.get("exit_code", 0),
                stdout_preview=item.get("stdout_preview", ""),
                stderr_preview=item.get("stderr_preview", ""),
                cwd=item.get("cwd", ""),
                shell=item.get("shell", ""),
                duration_ms=item.get("duration_ms", 0),
                timestamp=item.get("timestamp", time.time()),
                session_id=item.get("session_id", ""),
                intent=item.get("intent", ""),
                source=item.get("source", "imported"),
                was_ai_translated=item.get("was_ai_translated", False),
                original_nl=item.get("original_nl", ""),
            )
            self.add_command(record)
            count += 1
        return count

    def export_text(self, filepath: Path, limit: int = None) -> int:
        """Export command history as plain text (one command per line). Returns count."""
        conn = self._get_conn()
        effective_limit = min(limit or self.MAX_EXPORT_RECORDS, self.MAX_EXPORT_RECORDS)
        rows = conn.execute(
            "SELECT command, timestamp, exit_code, cwd FROM commands ORDER BY timestamp DESC LIMIT ?",
            (effective_limit,)
        ).fetchall()

        lines = []
        for r in rows:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["timestamp"]))
            status = "✓" if r["exit_code"] == 0 else "✗"
            lines.append(f"[{ts}] {status} {r['command']}")

        Path(filepath).write_text("\n".join(lines), encoding="utf-8")
        return len(rows)

    def get_all_fixes(self, limit: int = 30) -> list[dict]:
        """Get all cached error fixes for playbook generation."""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT error_pattern, error_message, fix_command, source,
                   success_count, failure_count, last_used
            FROM error_fixes
            ORDER BY success_count DESC LIMIT ?
        """, (limit,)).fetchall()

        return [
            {
                "error_preview": r["error_message"][:200],
                "fix_command": r["fix_command"],
                "source": r["source"],
                "success_count": r["success_count"],
                "failure_count": r["failure_count"],
            }
            for r in rows
        ]

    # ═══════════════════════════════════════════════════════
    # Maintenance
    # ═══════════════════════════════════════════════════════

    def cleanup(self, retention_days: int = None) -> int:
        """Auto-cleanup old records. Returns number of records removed."""
        days = retention_days or self.DEFAULT_RETENTION_DAYS
        cutoff = time.time() - (days * 86400)
        conn = self._get_conn()

        # Delete old commands
        cursor = conn.execute("DELETE FROM commands WHERE timestamp < ?", (cutoff,))
        deleted = cursor.rowcount

        # Delete old feedback
        conn.execute("DELETE FROM feedback WHERE timestamp < ?", (cutoff,))

        # Delete old snapshots (shorter retention)
        snap_cutoff = time.time() - (7 * 86400)  # 7 days for snapshots
        conn.execute("DELETE FROM undo_snapshots WHERE timestamp < ?", (snap_cutoff,))

        # Rebuild FTS index
        try:
            conn.execute("INSERT INTO commands_fts(commands_fts) VALUES('rebuild')")
        except sqlite3.OperationalError:
            pass

        # Vacuum to reclaim space
        conn.execute("VACUUM")
        conn.commit()
        return deleted

    def get_db_stats(self) -> dict:
        """Get database size and table statistics."""
        conn = self._get_conn()
        tables = ["commands", "error_fixes", "patterns", "sessions", "feedback", "aliases"]
        stats = {}
        for table in tables:
            try:
                row = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
                stats[table] = row["c"]
            except sqlite3.OperationalError:
                stats[table] = 0

        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {
            "tables": stats,
            "db_size_mb": round(db_size / (1024 * 1024), 2),
            "db_path": str(self.db_path),
        }

    # ═══════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════

    def _row_to_record(self, row) -> CommandRecord:
        return CommandRecord(
            id=row["id"],
            command=row["command"],
            exit_code=row["exit_code"],
            stdout_preview=row["stdout_preview"],
            stderr_preview=row["stderr_preview"],
            cwd=row["cwd"],
            shell=row["shell"],
            duration_ms=row["duration_ms"],
            timestamp=row["timestamp"],
            session_id=row["session_id"],
            intent=row["intent"],
            source=row["source"],
            context_hash=row["context_hash"],
            was_ai_translated=bool(row["was_ai_translated"]),
            original_nl=row["original_nl"],
            tags=row["tags"] if "tags" in row.keys() else "",
            resources_json=row["resources_json"] if "resources_json" in row.keys() else "",
            pid=row["pid"] if "pid" in row.keys() else 0,
        )

    def get_stats(self) -> dict:
        """Get overall history statistics."""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as c FROM commands").fetchone()["c"]
        errors = conn.execute("SELECT COUNT(*) as c FROM commands WHERE exit_code != 0").fetchone()["c"]
        fixes = conn.execute("SELECT COUNT(*) as c FROM error_fixes").fetchone()["c"]

        return {
            "total_commands": total,
            "error_count": errors,
            "success_rate": round((total - errors) / max(total, 1) * 100, 1),
            "cached_fixes": fixes,
        }

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
