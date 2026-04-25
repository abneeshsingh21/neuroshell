# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Update channel and signed manifest utilities for desktop release delivery."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path


class UpdateManager:
    """Build and verify update manifests for stable/beta/canary channels."""

    CHANNELS = ("stable", "beta", "canary")

    def __init__(self, release_dir: Path | str):
        self.release_dir = Path(release_dir)
        self.release_dir.mkdir(parents=True, exist_ok=True)

    def build_manifest(
        self,
        version: str,
        channel: str,
        artifacts: list[Path | str],
        notes: str = "",
        min_supported_version: str = "",
    ) -> dict:
        channel_norm = channel.strip().lower()
        if channel_norm not in self.CHANNELS:
            raise ValueError(f"invalid channel: {channel}")

        rows = []
        for art in artifacts:
            path = Path(art)
            if not path.exists():
                raise FileNotFoundError(f"artifact not found: {path}")
            rows.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                    "sha256": self.sha256_file(path),
                }
            )

        return {
            "manifest_version": 1,
            "created_at": time.time(),
            "version": version,
            "channel": channel_norm,
            "min_supported_version": min_supported_version,
            "release_notes": notes,
            "artifacts": rows,
        }

    def write_manifest(self, manifest: dict, output_path: Path | str) -> Path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return out

    def validate_manifest_integrity(self, manifest: dict) -> dict:
        checked = 0
        for row in manifest.get("artifacts", []):
            path = Path(row.get("path", ""))
            expected = row.get("sha256", "")
            if not path.exists():
                return {"ok": False, "reason": "artifact_missing", "checked": checked}
            observed = self.sha256_file(path)
            if observed != expected:
                return {"ok": False, "reason": "artifact_hash_mismatch", "checked": checked}
            checked += 1
        return {"ok": True, "reason": "ok", "checked": checked}

    def sign_manifest(self, manifest_path: Path | str, private_key_path: Path | str) -> Path:
        target = Path(manifest_path)
        key = Path(private_key_path)
        if not target.exists():
            raise FileNotFoundError(f"manifest not found: {target}")
        if not key.exists():
            raise FileNotFoundError(f"private key not found: {key}")

        sig = target.with_suffix(target.suffix + ".sig")
        cmd = [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(key),
            "-out",
            str(sig),
            str(target),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return sig

    def verify_manifest_signature(
        self,
        manifest_path: Path | str,
        signature_path: Path | str,
        public_key_path: Path | str,
    ) -> bool:
        target = Path(manifest_path)
        sig = Path(signature_path)
        pub = Path(public_key_path)
        if not target.exists() or not sig.exists() or not pub.exists():
            return False

        cmd = [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(pub),
            "-signature",
            str(sig),
            str(target),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0

    @staticmethod
    def select_channel(preferred: str) -> str:
        p = (preferred or "stable").strip().lower()
        if p in UpdateManager.CHANNELS:
            return p
        return "stable"

    @staticmethod
    def sha256_file(path: Path | str) -> str:
        p = Path(path)
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
