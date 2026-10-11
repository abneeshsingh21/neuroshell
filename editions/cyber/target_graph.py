"""
NeuroShell Cyber — Persistent Engagement Target Graph.
Stores discovered hosts, open ports, web endpoints, captured credentials,
and security findings across the entire session using SQLite WAL.
Ensures deterministic connection closure for clean multi-process operation on Windows & Linux.
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator


@dataclass
class HostEntity:
    ip: str
    hostname: str = ""
    os_name: str = ""
    status: str = "up"
    notes: str = ""


@dataclass
class PortServiceEntity:
    ip: str
    port: int
    protocol: str = "tcp"
    service: str = ""
    version: str = ""
    banner: str = ""


@dataclass
class CredentialEntity:
    target_ip: str
    service: str
    username: str
    secret: str
    is_hash: bool = False


class TargetGraph:
    """
    SQLite-backed state graph for cybersecurity engagements.
    Enables NeuroShell to remember target environments across commands.
    """

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            home = Path.home() / ".neuroshell" / "cyber"
            home.mkdir(parents=True, exist_ok=True)
            self.db_path = home / "target_graph.db"
        else:
            self.db_path = Path(db_path)

        self._init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS hosts (
                    ip TEXT PRIMARY KEY,
                    hostname TEXT,
                    os_name TEXT,
                    status TEXT,
                    notes TEXT,
                    first_seen REAL,
                    last_seen REAL
                );

                CREATE TABLE IF NOT EXISTS ports (
                    ip TEXT,
                    port INTEGER,
                    protocol TEXT DEFAULT 'tcp',
                    service TEXT,
                    version TEXT,
                    banner TEXT,
                    last_seen REAL,
                    PRIMARY KEY (ip, port, protocol),
                    FOREIGN KEY (ip) REFERENCES hosts(ip)
                );

                CREATE TABLE IF NOT EXISTS web_paths (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip TEXT,
                    port INTEGER,
                    path TEXT,
                    status_code INTEGER,
                    title TEXT,
                    timestamp REAL
                );

                CREATE TABLE IF NOT EXISTS credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_ip TEXT,
                    service TEXT,
                    username TEXT,
                    secret TEXT,
                    is_hash INTEGER DEFAULT 0,
                    timestamp REAL
                );

                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT,
                    title TEXT,
                    severity TEXT,
                    description TEXT,
                    tool TEXT,
                    timestamp REAL
                );
            """)

    def add_host(self, ip: str, hostname: str = "", os_name: str = "", status: str = "up", notes: str = "") -> None:
        now = time.time()
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO hosts (ip, hostname, os_name, status, notes, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ip) DO UPDATE SET
                    hostname = CASE WHEN ? != '' THEN ? ELSE hostname END,
                    os_name = CASE WHEN ? != '' THEN ? ELSE os_name END,
                    status = ?,
                    notes = CASE WHEN ? != '' THEN ? ELSE notes END,
                    last_seen = ?;
            """, (ip, hostname, os_name, status, notes, now, now, hostname, hostname, os_name, os_name, status, notes, notes, now))

    def add_port(self, ip: str, port: int, protocol: str = "tcp", service: str = "", version: str = "", banner: str = "") -> None:
        self.add_host(ip)
        now = time.time()
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO ports (ip, port, protocol, service, version, banner, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ip, port, protocol) DO UPDATE SET
                    service = CASE WHEN ? != '' THEN ? ELSE service END,
                    version = CASE WHEN ? != '' THEN ? ELSE version END,
                    banner = CASE WHEN ? != '' THEN ? ELSE banner END,
                    last_seen = ?;
            """, (ip, port, protocol, service, version, banner, now, service, service, version, version, banner, banner, now))

    def add_web_path(self, ip: str, port: int, path: str, status_code: int = 200, title: str = "") -> None:
        now = time.time()
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO web_paths (ip, port, path, status_code, title, timestamp)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (ip, port, path, status_code, title, now))

    def add_credential(self, target_ip: str, service: str, username: str, secret: str, is_hash: bool = False) -> None:
        now = time.time()
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO credentials (target_ip, service, username, secret, is_hash, timestamp)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (target_ip, service, username, secret, 1 if is_hash else 0, now))

    def get_hosts(self) -> list[HostEntity]:
        with self._connection() as conn:
            cursor = conn.execute("SELECT ip, hostname, os_name, status, notes FROM hosts ORDER BY last_seen DESC;")
            return [HostEntity(ip=r[0], hostname=r[1], os_name=r[2], status=r[3], notes=r[4]) for r in cursor.fetchall()]

    def get_ports(self, ip: str | None = None, service: str | None = None) -> list[PortServiceEntity]:
        with self._connection() as conn:
            query = "SELECT ip, port, protocol, service, version, banner FROM ports WHERE 1=1"
            params: list[Any] = []
            if ip:
                query += " AND ip = ?"
                params.append(ip)
            if service:
                query += " AND service LIKE ?"
                params.append(f"%{service}%")
            query += " ORDER BY ip, port ASC;"
            cursor = conn.execute(query, params)
            return [PortServiceEntity(ip=r[0], port=r[1], protocol=r[2], service=r[3], version=r[4], banner=r[5]) for r in cursor.fetchall()]

    def get_credentials(self) -> list[CredentialEntity]:
        with self._connection() as conn:
            cursor = conn.execute("SELECT target_ip, service, username, secret, is_hash FROM credentials ORDER BY timestamp DESC;")
            return [CredentialEntity(target_ip=r[0], service=r[1], username=r[2], secret=r[3], is_hash=bool(r[4])) for r in cursor.fetchall()]

    def get_summary(self) -> dict[str, Any]:
        hosts = self.get_hosts()
        ports = self.get_ports()
        creds = self.get_credentials()
        return {
            "total_hosts": len(hosts),
            "total_open_ports": len(ports),
            "total_credentials": len(creds),
            "hosts": [h.ip for h in hosts],
        }
