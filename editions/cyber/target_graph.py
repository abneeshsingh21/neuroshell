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

    def get_web_paths(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            cursor = conn.execute("SELECT ip, port, path, status_code, title, timestamp FROM web_paths ORDER BY ip, port, path ASC;")
            return [
                {"ip": r[0], "port": r[1], "path": r[2], "status_code": r[3], "title": r[4], "timestamp": r[5]}
                for r in cursor.fetchall()
            ]

    def get_findings(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            cursor = conn.execute("SELECT target, title, severity, description, tool, timestamp FROM findings ORDER BY timestamp DESC;")
            return [
                {"target": r[0], "title": r[1], "severity": r[2], "description": r[3], "tool": r[4], "timestamp": r[5]}
                for r in cursor.fetchall()
            ]

    def export_json(self, filepath: str | Path | None = None) -> str:
        """Export all discovered entities and security findings as JSON."""
        import json
        data = {
            "version": "1.0",
            "summary": self.get_summary(),
            "hosts": [
                {"ip": h.ip, "hostname": h.hostname, "os_name": h.os_name, "status": h.status, "notes": h.notes}
                for h in self.get_hosts()
            ],
            "ports": [
                {"ip": p.ip, "port": p.port, "protocol": p.protocol, "service": p.service, "version": p.version, "banner": p.banner}
                for p in self.get_ports()
            ],
            "web_paths": self.get_web_paths(),
            "credentials": [
                {"target_ip": c.target_ip, "service": c.service, "username": c.username, "secret": c.secret, "is_hash": c.is_hash}
                for c in self.get_credentials()
            ],
            "findings": self.get_findings(),
        }
        json_str = json.dumps(data, indent=2)
        if filepath:
            Path(filepath).write_text(json_str, encoding="utf-8")
        return json_str

    def export_markdown_report(self, output_path: str | Path | None = None) -> str:
        """Generate an executive security assessment report in Markdown."""
        hosts = self.get_hosts()
        ports = self.get_ports()
        creds = self.get_credentials()
        web_paths = self.get_web_paths()
        findings = self.get_findings()

        import datetime
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        report = [
            "# 🛡️ NeuroShell Cyber — Security Assessment & Engagement Report",
            "",
            f"**Generated:** {now_str}  ",
            "**Tool:** NeuroShell Cyber (AI-Native Terminal & Reconnaissance Orchestrator)  ",
            "",
            "---",
            "",
            "## 1. Executive Summary",
            "",
            f"- **Total Discovered Hosts:** {len(hosts)}",
            f"- **Total Open Services:** {len(ports)}",
            f"- **Total Web Endpoints Discovered:** {len(web_paths)}",
            f"- **Captured Credentials:** {len(creds)}",
            f"- **Documented Findings:** {len(findings)}",
            "",
            "---",
            "",
            "## 2. Discovered Target Topology",
            "",
            "| Host IP | Hostname | OS / Banner | Status | Open Ports & Services |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]

        if not hosts:
            report.append("| *None* | - | - | - | - |")
        else:
            for h in hosts:
                h_ports = [p for p in ports if p.ip == h.ip]
                ports_desc = ", ".join(f"{p.port}/{p.protocol} ({p.service})" for p in h_ports) or "None"
                report.append(f"| `{h.ip}` | {h.hostname or '-'} | {h.os_name or '-'} | {h.status} | {ports_desc} |")

        report.extend([
            "",
            "---",
            "",
            "## 3. Web Application Attack Surface",
            "",
            "| Host IP | Port | Path | Status Code | Title / Response |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])

        if not web_paths:
            report.append("| *None* | - | - | - | - |")
        else:
            for wp in web_paths:
                report.append(f"| `{wp['ip']}` | {wp['port']} | `{wp['path']}` | {wp['status_code']} | {wp['title'] or '-'} |")

        report.extend([
            "",
            "---",
            "",
            "## 4. Compromised & Captured Credentials",
            "",
            "| Target IP | Service | Username | Secret / Hash | Type |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])

        if not creds:
            report.append("| *None* | - | - | - | - |")
        else:
            for c in creds:
                ctype = "HASH" if c.is_hash else "PLAINTEXT"
                report.append(f"| `{c.target_ip}` | {c.service} | **{c.username}** | `{c.secret}` | {ctype} |")

        report.extend([
            "",
            "---",
            "",
            "## 5. Security Recommendations & Hardening",
            "",
            "1. **Surface Reduction:** Restrict externally accessible administrative ports and disable non-essential services.",
            "2. **Patch Management:** Immediately upgrade vulnerable server packages identified during reconnaissance.",
            "3. **Credential Hygiene:** Rotate all compromised accounts, enforce strong multifactor authentication (MFA), and deprecate legacy hash formats.",
            "4. **Continuous Monitoring:** Implement rate limiting and intrusion detection against automated fuzzing and injection attempts.",
            "",
            "*Report compiled automatically by NeuroShell Cyber.*",
        ])

        content = "\n".join(report)
        if output_path:
            Path(output_path).write_text(content, encoding="utf-8")
        return content

    def format_topology(self) -> str:
        """Render the complete engagement target topology into a rich ANSI table."""
        hosts = self.get_hosts()
        ports = self.get_ports()
        creds = self.get_credentials()

        if not hosts:
            return "\n  \033[90m[i] Target graph is currently empty. Run reconnaissance scans to automatically discover hosts.\033[0m\n"

        lines = [
            "\n  \033[1m\033[38;2;74;222;128m╭── 🎯 Persistent Engagement Target Graph ─────────────────────────────╮\033[0m",
            f"  \033[38;2;74;222;128m│\033[0m \033[1mHosts: {len(hosts)} | Open Services: {len(ports)} | Credentials: {len(creds)}\033[0m",
            "  \033[38;2;74;222;128m├──────────────────────────────────────────────────────────────────────┤\033[0m",
        ]

        for host in hosts:
            h_ports = [p for p in ports if p.ip == host.ip]
            host_label = f"{host.ip} ({host.hostname})" if host.hostname else host.ip
            lines.append(f"  \033[38;2;74;222;128m│\033[0m \033[1m\033[37m🖥️  {host_label:<32}\033[0m [Status: \033[32m{host.status}\033[0m]")
            for p in h_ports:
                svc_desc = f"{p.service} {p.version}".strip() or "unknown"
                lines.append(f"  \033[38;2;74;222;128m│\033[0m   \033[36m↳ {p.port}/{p.protocol:<4}\033[0m \033[32mopen\033[0m \033[90m{svc_desc:<35}\033[0m")

        if creds:
            lines.append("  \033[38;2;74;222;128m├──────────────────────────────────────────────────────────────────────┤\033[0m")
            lines.append("  \033[38;2;74;222;128m│\033[0m \033[1m\033[33m🔑 Captured Credentials:\033[0m")
            for c in creds:
                tag = "[HASH]" if c.is_hash else "[PASS]"
                lines.append(f"  \033[38;2;74;222;128m│\033[0m   \033[33m{c.target_ip}\033[0m (\033[36m{c.service}\033[0m) -> \033[1m{c.username}\033[0m : \033[90m{c.secret}\033[0m {tag}")

        lines.append("  \033[38;2;74;222;128m╰──────────────────────────────────────────────────────────────────────╯\033[0m\n")
        return "\n".join(lines)
