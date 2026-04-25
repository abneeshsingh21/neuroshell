# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Staged rollout manager with rollback and config drift checks."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from operations.release_pipeline import ReleasePipeline


class DeployManager:
    """Manage staged deployments and rollback metadata."""

    def __init__(self, state_file: Path | str):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.state_file.exists():
            self._write_state({"history": [], "current": None, "audit": [], "key_allowlist": []})

    def deploy(self, stage: str, version: str, config_path: Path | str) -> dict:
        cfg = Path(config_path)
        cfg_hash = self.config_hash(cfg)

        state = self._read_state()
        previous = state.get("current")
        event = {
            "time": time.time(),
            "action": "deploy",
            "stage": stage,
            "version": version,
            "config_path": str(cfg),
            "config_hash": cfg_hash,
            "previous": previous,
        }
        state["history"].append(event)
        state["current"] = {
            "stage": stage,
            "version": version,
            "config_path": str(cfg),
            "config_hash": cfg_hash,
        }
        self._write_state(state)
        return event

    def promote_verified(
        self,
        stage: str,
        version: str,
        config_path: Path | str,
        manifest_path: Path | str,
        checksums_path: Path | str,
        public_key_path: Path | str,
        require_signatures: bool = True,
        require_trusted_key: bool = True,
    ) -> dict:
        """Promote a deployment only after artifact integrity checks pass."""
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        checksum_map = ReleasePipeline.read_checksums(checksums_path)
        artifacts = manifest.get("artifacts", [])
        if not artifacts:
            raise RuntimeError("manifest contains no artifacts")

        if version and manifest.get("version") and manifest.get("version") != version:
            raise RuntimeError("version does not match release manifest")

        key_fingerprint = ReleasePipeline.public_key_fingerprint(public_key_path)
        allowlist = set(self.get_allowed_key_fingerprints())
        if require_trusted_key and (not allowlist or key_fingerprint not in allowlist):
            raise RuntimeError("public key is not in trusted allowlist")

        verifier = ReleasePipeline(Path(manifest_path).parent)
        for art in artifacts:
            art_path = Path(art.get("path", ""))
            expected_sha = art.get("sha256", "")
            if not art_path.exists():
                raise RuntimeError(f"artifact missing: {art_path}")

            observed = verifier.sha256_file(art_path)
            if observed != expected_sha:
                raise RuntimeError(f"artifact hash mismatch: {art_path.name}")

            checksum_sha = checksum_map.get(art_path.name)
            if checksum_sha != expected_sha:
                raise RuntimeError(f"checksum mismatch: {art_path.name}")

            signature = art.get("signature_path")
            if require_signatures:
                if not signature:
                    raise RuntimeError(f"signature required but missing: {art_path.name}")
                if not verifier.verify_artifact_signature(art_path, signature, public_key_path):
                    raise RuntimeError(f"signature verification failed: {art_path.name}")

        event = self.deploy(stage=stage, version=version, config_path=config_path)
        event["verified_release"] = {
            "manifest": str(manifest_path),
            "checksums": str(checksums_path),
            "public_key": str(public_key_path),
            "public_key_fingerprint": key_fingerprint,
            "signatures_required": require_signatures,
            "artifacts_checked": len(artifacts),
        }

        state = self._read_state()
        if state.get("history"):
            state["history"][-1] = event
            self._write_state(state)

        self._append_audit(
            action="promote_verified",
            payload={
                "stage": stage,
                "version": version,
                "artifacts_checked": len(artifacts),
                "public_key_fingerprint": key_fingerprint,
            },
        )

        return event

    def canary_promote(
        self,
        stage: str,
        version: str,
        config_path: Path | str,
        manifest_path: Path | str,
        checksums_path: Path | str,
        public_key_path: Path | str,
        slo_snapshot: dict,
        max_budget_consumed_ratio: float = 1.0,
    ) -> dict:
        """Promote and auto-rollback if SLO breach signal is detected."""
        event = self.promote_verified(
            stage=stage,
            version=version,
            config_path=config_path,
            manifest_path=manifest_path,
            checksums_path=checksums_path,
            public_key_path=public_key_path,
            require_signatures=True,
            require_trusted_key=True,
        )

        burn = float(slo_snapshot.get("budget_consumed_ratio", 0.0))
        critical = any(a.get("severity") == "critical" for a in slo_snapshot.get("alerts", []))
        if burn > max_budget_consumed_ratio or critical:
            rollback_event = self.rollback()
            out = {
                "promoted": False,
                "rolled_back": True,
                "reason": "slo_breach",
                "burn_ratio": burn,
                "rollback": rollback_event,
            }
            self._append_audit(
                action="canary_auto_rollback",
                payload={"stage": stage, "version": version, "burn_ratio": burn},
            )
            return out

        out = {"promoted": True, "rolled_back": False, "reason": "ok", "event": event, "burn_ratio": burn}
        self._append_audit(
            action="canary_promoted",
            payload={"stage": stage, "version": version, "burn_ratio": burn},
        )
        return out

    def rollback(self) -> dict:
        state = self._read_state()
        current = state.get("current")
        if not current:
            raise RuntimeError("no active deployment")

        history = state.get("history", [])
        previous = None
        for item in reversed(history):
            if item.get("action") == "deploy" and item.get("version") != current.get("version"):
                previous = {
                    "stage": item.get("stage"),
                    "version": item.get("version"),
                    "config_path": item.get("config_path"),
                    "config_hash": item.get("config_hash"),
                }
                break

        if not previous:
            raise RuntimeError("no previous deployment to rollback to")

        event = {
            "time": time.time(),
            "action": "rollback",
            "from": current,
            "to": previous,
        }
        state["history"].append(event)
        state["current"] = previous
        self._write_state(state)
        self._append_audit(
            action="rollback",
            payload={
                "from_version": current.get("version"),
                "to_version": previous.get("version"),
                "to_stage": previous.get("stage"),
            },
        )
        return event

    def detect_drift(self, expected_config_path: Path | str) -> dict:
        state = self._read_state()
        current = state.get("current")
        if not current:
            return {"drift": False, "reason": "no_active_deployment"}

        expected_hash = self.config_hash(Path(expected_config_path))
        actual_hash = current.get("config_hash")
        result = {
            "drift": expected_hash != actual_hash,
            "expected_hash": expected_hash,
            "actual_hash": actual_hash,
            "stage": current.get("stage"),
            "version": current.get("version"),
        }
        self._append_audit(
            action="drift_check",
            payload={
                "drift": result["drift"],
                "stage": result["stage"],
                "version": result["version"],
            },
        )
        return result

    def current(self) -> dict | None:
        return self._read_state().get("current")

    def add_allowed_key(self, public_key_path: Path | str) -> str:
        """Add public key fingerprint to trusted allowlist."""
        fingerprint = ReleasePipeline.public_key_fingerprint(public_key_path)
        state = self._read_state()
        allow = set(state.get("key_allowlist", []))
        allow.add(fingerprint)
        state["key_allowlist"] = sorted(allow)
        self._write_state(state)
        self._append_audit(action="key_allowlist_add", payload={"fingerprint": fingerprint})
        return fingerprint

    def get_allowed_key_fingerprints(self) -> list[str]:
        state = self._read_state()
        return list(state.get("key_allowlist", []))

    def export_audit_json(self, output_path: Path | str, limit: int = 500) -> Path:
        state = self._read_state()
        rows = state.get("audit", [])[-limit:]
        payload = {
            "exported_at": time.time(),
            "entries": rows,
            "count": len(rows),
        }
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return out

    def get_audit_log(self, limit: int = 50) -> list[dict]:
        state = self._read_state()
        return list(state.get("audit", [])[-limit:])

    def verify_audit_export(self, export_path: Path | str) -> dict:
        path = Path(export_path)
        if not path.exists():
            return {"ok": False, "reason": "file_not_found", "entries_checked": 0}

        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        prev_hash = ""
        checked = 0
        for row in entries:
            if row.get("prev_hash", "") != prev_hash:
                return {"ok": False, "reason": "broken_prev_hash_chain", "entries_checked": checked}
            expected = self._compute_audit_hash(
                timestamp=float(row.get("timestamp", 0.0)),
                action=row.get("action", ""),
                payload=row.get("payload", {}),
                prev_hash=row.get("prev_hash", ""),
            )
            if row.get("entry_hash", "") != expected:
                return {"ok": False, "reason": "entry_hash_mismatch", "entries_checked": checked}
            prev_hash = row.get("entry_hash", "")
            checked += 1
        return {"ok": True, "reason": "ok", "entries_checked": checked}

    @staticmethod
    def config_hash(path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(f"config file not found: {path}")
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    def _read_state(self) -> dict:
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        state.setdefault("history", [])
        state.setdefault("audit", [])
        state.setdefault("key_allowlist", [])
        state.setdefault("current", None)
        return state

    def _write_state(self, state: dict):
        self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _append_audit(self, action: str, payload: dict):
        state = self._read_state()
        audit = state.get("audit", [])
        prev_hash = audit[-1].get("entry_hash", "") if audit else ""
        ts = time.time()
        entry_hash = self._compute_audit_hash(ts, action, payload, prev_hash)
        audit.append(
            {
                "timestamp": ts,
                "action": action,
                "payload": payload,
                "prev_hash": prev_hash,
                "entry_hash": entry_hash,
            }
        )
        state["audit"] = audit[-2000:]
        self._write_state(state)

    @staticmethod
    def _compute_audit_hash(timestamp: float, action: str, payload: dict, prev_hash: str) -> str:
        encoded = json.dumps(
            {
                "timestamp": f"{float(timestamp):.6f}",
                "action": action,
                "payload": payload,
                "prev_hash": prev_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
