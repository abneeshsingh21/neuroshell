# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Release pipeline helpers for deterministic artifacts, checksums, and optional signing."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ReleaseArtifact:
    path: str
    size_bytes: int
    sha256: str
    signature_path: Optional[str] = None


class ReleasePipeline:
    """Create reproducible release manifests and optional detached signatures."""

    def __init__(self, dist_dir: Path | str):
        self.dist_dir = Path(dist_dir)
        self.dist_dir.mkdir(parents=True, exist_ok=True)

    def collect_artifacts(self) -> list[Path]:
        patterns = ("*.whl", "*.tar.gz", "*.zip", "*.exe", "*.vsix")
        artifacts: list[Path] = []
        for pattern in patterns:
            artifacts.extend(sorted(self.dist_dir.glob(pattern)))
        return artifacts

    def set_reproducible_env(self, epoch: Optional[int] = None) -> int:
        """Set SOURCE_DATE_EPOCH for deterministic build tooling."""
        if epoch is None:
            epoch = int(time.time())
        os.environ["SOURCE_DATE_EPOCH"] = str(epoch)
        os.environ.setdefault("PYTHONHASHSEED", "0")
        return epoch

    def build_manifest(self, version: str, stage: str, include_signatures: bool = True) -> dict:
        artifacts = []
        for path in self.collect_artifacts():
            digest = self.sha256_file(path)
            signature_path = None
            if include_signatures:
                sig = path.with_suffix(path.suffix + ".sig")
                if sig.exists():
                    signature_path = str(sig)

            artifacts.append(
                ReleaseArtifact(
                    path=str(path),
                    size_bytes=path.stat().st_size,
                    sha256=digest,
                    signature_path=signature_path,
                )
            )

        return {
            "created_at": time.time(),
            "version": version,
            "stage": stage,
            "artifact_count": len(artifacts),
            "artifacts": [a.__dict__ for a in artifacts],
        }

    def write_manifest(self, version: str, stage: str, output_path: Path | str) -> Path:
        manifest = self.build_manifest(version=version, stage=stage)
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return target

    def write_checksums(self, output_path: Path | str) -> Path:
        lines = []
        for path in self.collect_artifacts():
            lines.append(f"{self.sha256_file(path)}  {path.name}")

        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return target

    def sign_artifact(self, artifact: Path | str, private_key_path: Path | str) -> Path:
        """Create detached signature via openssl. Raises if openssl/key unavailable."""
        artifact_path = Path(artifact)
        key_path = Path(private_key_path)
        if not artifact_path.exists():
            raise FileNotFoundError(f"artifact not found: {artifact_path}")
        if not key_path.exists():
            raise FileNotFoundError(f"private key not found: {key_path}")

        signature_path = artifact_path.with_suffix(artifact_path.suffix + ".sig")
        cmd = [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(key_path),
            "-out",
            str(signature_path),
            str(artifact_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return signature_path

    def verify_artifact_signature(
        self,
        artifact: Path | str,
        signature_path: Path | str,
        public_key_path: Path | str,
    ) -> bool:
        """Verify detached artifact signature via openssl."""
        artifact_path = Path(artifact)
        sig_path = Path(signature_path)
        pub_path = Path(public_key_path)
        if not artifact_path.exists() or not sig_path.exists() or not pub_path.exists():
            return False

        cmd = [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(pub_path),
            "-signature",
            str(sig_path),
            str(artifact_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0

    @staticmethod
    def read_checksums(path: Path | str) -> dict[str, str]:
        """Read checksum file into mapping of artifact name -> sha256."""
        target = Path(path)
        out: dict[str, str] = {}
        for raw in target.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            digest = parts[0]
            filename = parts[-1]
            out[filename] = digest
        return out

    @staticmethod
    def public_key_fingerprint(public_key_path: Path | str) -> str:
        """Return SHA256 fingerprint of a public key file."""
        p = Path(public_key_path)
        return hashlib.sha256(p.read_bytes()).hexdigest()

    @staticmethod
    def sha256_file(path: Path | str) -> str:
        p = Path(path)
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
