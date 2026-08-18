# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Data governance utilities for retention, rotation, and backup/restore drills."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CleanupReport:
    deleted_files: int
    reclaimed_bytes: int


class DataGovernanceManager:
    """Enforce retention and perform backup/restore drills for ops artifacts."""

    def __init__(self, logs_dir: Path | str, audit_dir: Path | str):
        self.logs_dir = Path(logs_dir)
        self.audit_dir = Path(audit_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    def enforce_retention_days(self, days: int) -> CleanupReport:
        cutoff = time.time() - (days * 24 * 3600)
        deleted = 0
        reclaimed = 0

        for root in (self.logs_dir, self.audit_dir):
            for path in root.glob("**/*"):
                if not path.is_file():
                    continue
                stat = path.stat()
                if stat.st_mtime < cutoff:
                    reclaimed += stat.st_size
                    path.unlink(missing_ok=True)
                    deleted += 1

        return CleanupReport(deleted_files=deleted, reclaimed_bytes=reclaimed)

    def create_backup(self, output_zip: Path | str) -> dict:
        target = Path(output_zip)
        target.parent.mkdir(parents=True, exist_ok=True)
        base = target.with_suffix("")

        archive_path = shutil.make_archive(str(base), "zip", root_dir=self.logs_dir.parent)
        archive = Path(archive_path)
        digest = self._sha256_file(archive)

        meta = {
            "created_at": time.time(),
            "archive": str(archive),
            "sha256": digest,
            "logs_dir": str(self.logs_dir),
            "audit_dir": str(self.audit_dir),
        }
        meta_path = archive.with_suffix(".zip.meta.json")
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta

    def restore_backup(self, archive_zip: Path | str, restore_dir: Path | str) -> Path:
        import zipfile
        archive = Path(archive_zip)
        restore = Path(restore_dir).resolve()
        restore.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "r") as zf:
            for member in zf.infolist():
                target_path = (restore / member.filename).resolve()
                if not str(target_path).startswith(str(restore)):
                    raise PermissionError(f"Zip slip path traversal detected: {member.filename}")
            zf.extractall(path=restore)
        return restore

    def validate_backup(self, archive_zip: Path | str, expected_sha256: str) -> bool:
        return self._sha256_file(Path(archive_zip)) == expected_sha256

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
