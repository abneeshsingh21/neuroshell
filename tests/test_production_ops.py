"""Production-ops test coverage for release, runtime, security, reliability, and deployment."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestReleasePipeline(unittest.TestCase):
    def test_manifest_and_checksums(self):
        from operations.release_pipeline import ReleasePipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            dist = Path(tmpdir) / "dist"
            dist.mkdir(parents=True, exist_ok=True)
            wheel = dist / "neuroshell-4.0.0-py3-none-any.whl"
            wheel.write_bytes(b"wheel-bytes")

            rp = ReleasePipeline(dist)
            rp.set_reproducible_env(epoch=1704067200)
            manifest_path = rp.write_manifest("4.0.0", "staging", dist / "release-manifest.json")
            checksums_path = rp.write_checksums(dist / "SHA256SUMS")

            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], "4.0.0")
            self.assertEqual(payload["stage"], "staging")
            self.assertEqual(payload["artifact_count"], 1)

            checksums = checksums_path.read_text(encoding="utf-8")
            self.assertIn("neuroshell-4.0.0-py3-none-any.whl", checksums)
            self.assertEqual(os.environ.get("SOURCE_DATE_EPOCH"), "1704067200")

    def test_read_checksums_parser(self):
        from operations.release_pipeline import ReleasePipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "SHA256SUMS"
            p.write_text("abc123  pkg.whl\ndef456  app.zip\n", encoding="utf-8")
            data = ReleasePipeline.read_checksums(p)
            self.assertEqual(data["pkg.whl"], "abc123")
            self.assertEqual(data["app.zip"], "def456")

    def test_public_key_fingerprint(self):
        from operations.release_pipeline import ReleasePipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            key = Path(tmpdir) / "release-public.pem"
            key.write_text("public-key-material", encoding="utf-8")
            fp1 = ReleasePipeline.public_key_fingerprint(key)
            fp2 = ReleasePipeline.public_key_fingerprint(key)
            self.assertEqual(fp1, fp2)
            self.assertEqual(len(fp1), 64)


class TestRuntimeOps(unittest.TestCase):
    def test_slo_alerting(self):
        from operations.runtime_ops import RuntimeSLOMonitor

        m = RuntimeSLOMonitor()
        for _ in range(30):
            m.record_latency_ms("translate", 1800)
            m.record_latency_ms("execute", 3500)
            m.record_error()

        alerts = m.evaluate_alerts()
        codes = {a["code"] for a in alerts}
        self.assertIn("SLO_LATENCY_TRANSLATE", codes)
        self.assertIn("SLO_LATENCY_EXECUTE", codes)


class TestChaos(unittest.TestCase):
    def test_fault_injector_failure_mode(self):
        from resilience.chaos import ChaosPolicy, FaultInjector

        fi = FaultInjector(ChaosPolicy(failure_rate=1.0))

        with self.assertRaises(RuntimeError):
            fi.run(lambda: "ok")


class TestDataGovernance(unittest.TestCase):
    def test_backup_and_restore(self):
        from operations.data_governance import DataGovernanceManager

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            logs = root / "logs"
            audits = root / "audits"
            logs.mkdir()
            audits.mkdir()
            (logs / "neuroshell.log").write_text("entry", encoding="utf-8")
            (audits / "audit.json").write_text("{}", encoding="utf-8")

            mgr = DataGovernanceManager(logs, audits)
            meta = mgr.create_backup(root / "backup.zip")
            self.assertTrue(Path(meta["archive"]).exists())
            self.assertTrue(mgr.validate_backup(Path(meta["archive"]), meta["sha256"]))

            restored = mgr.restore_backup(Path(meta["archive"]), root / "restored")
            self.assertTrue(restored.exists())


class TestDeployManager(unittest.TestCase):
    def test_stage_deploy_rollback_and_drift(self):
        from operations.deploy_manager import DeployManager

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state = root / "deploy_state.json"
            c1 = root / "dev.toml"
            c2 = root / "prod.toml"
            c1.write_text("[safety]\nenabled=true\n", encoding="utf-8")
            c2.write_text("[safety]\nenabled=true\nconfirm_destructive=true\n", encoding="utf-8")

            dm = DeployManager(state)
            dm.deploy("dev", "4.1.0-rc1", c1)
            dm.deploy("production", "4.1.0", c2)

            drift = dm.detect_drift(c2)
            self.assertFalse(drift["drift"])

            c2.write_text("[safety]\nenabled=false\n", encoding="utf-8")
            drift2 = dm.detect_drift(c2)
            self.assertTrue(drift2["drift"])

            event = dm.rollback()
            self.assertEqual(event["action"], "rollback")
            self.assertEqual(dm.current()["version"], "4.1.0-rc1")

    def test_promote_verified_requires_signatures(self):
        from operations.deploy_manager import DeployManager

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state = root / "deploy_state.json"
            cfg = root / "prod.toml"
            cfg.write_text("[safety]\nenabled=true\n", encoding="utf-8")

            artifact = root / "neuroshell-4.1.0.whl"
            artifact.write_bytes(b"artifact-bytes")
            checksum = __import__("hashlib").sha256(artifact.read_bytes()).hexdigest()

            manifest = root / "release-manifest.json"
            manifest.write_text(json.dumps({
                "version": "4.1.0",
                "stage": "production",
                "artifacts": [{
                    "path": str(artifact),
                    "size_bytes": artifact.stat().st_size,
                    "sha256": checksum,
                    "signature_path": str(artifact.with_suffix(artifact.suffix + ".sig")),
                }],
            }), encoding="utf-8")

            sums = root / "SHA256SUMS"
            sums.write_text(f"{checksum}  {artifact.name}\n", encoding="utf-8")

            pub = root / "release-public.pem"
            pub.write_text("public-key", encoding="utf-8")

            dm = DeployManager(state)
            dm.add_allowed_key(pub)
            with patch("operations.release_pipeline.ReleasePipeline.verify_artifact_signature", return_value=True):
                event = dm.promote_verified(
                    stage="production",
                    version="4.1.0",
                    config_path=cfg,
                    manifest_path=manifest,
                    checksums_path=sums,
                    public_key_path=pub,
                    require_signatures=True,
                )

            self.assertEqual(event["stage"], "production")
            self.assertEqual(event["version"], "4.1.0")
            self.assertEqual(event["verified_release"]["artifacts_checked"], 1)

    def test_promote_verified_fails_when_signature_missing(self):
        from operations.deploy_manager import DeployManager

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state = root / "deploy_state.json"
            cfg = root / "prod.toml"
            cfg.write_text("[safety]\nenabled=true\n", encoding="utf-8")

            artifact = root / "neuroshell-4.1.0.whl"
            artifact.write_bytes(b"artifact-bytes")
            checksum = __import__("hashlib").sha256(artifact.read_bytes()).hexdigest()

            manifest = root / "release-manifest.json"
            manifest.write_text(json.dumps({
                "version": "4.1.0",
                "stage": "production",
                "artifacts": [{
                    "path": str(artifact),
                    "size_bytes": artifact.stat().st_size,
                    "sha256": checksum,
                    "signature_path": "",
                }],
            }), encoding="utf-8")

            sums = root / "SHA256SUMS"
            sums.write_text(f"{checksum}  {artifact.name}\n", encoding="utf-8")

            pub = root / "release-public.pem"
            pub.write_text("public-key", encoding="utf-8")

            dm = DeployManager(state)
            with self.assertRaises(RuntimeError):
                dm.promote_verified(
                    stage="production",
                    version="4.1.0",
                    config_path=cfg,
                    manifest_path=manifest,
                    checksums_path=sums,
                    public_key_path=pub,
                    require_signatures=True,
                )

    def test_promote_verified_fails_when_key_not_trusted(self):
        from operations.deploy_manager import DeployManager

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state = root / "deploy_state.json"
            cfg = root / "prod.toml"
            cfg.write_text("[safety]\nenabled=true\n", encoding="utf-8")

            artifact = root / "neuroshell-4.1.1.whl"
            artifact.write_bytes(b"artifact-bytes")
            checksum = __import__("hashlib").sha256(artifact.read_bytes()).hexdigest()

            sig = artifact.with_suffix(artifact.suffix + ".sig")
            sig.write_bytes(b"sig")

            manifest = root / "release-manifest.json"
            manifest.write_text(json.dumps({
                "version": "4.1.1",
                "stage": "production",
                "artifacts": [{
                    "path": str(artifact),
                    "size_bytes": artifact.stat().st_size,
                    "sha256": checksum,
                    "signature_path": str(sig),
                }],
            }), encoding="utf-8")

            sums = root / "SHA256SUMS"
            sums.write_text(f"{checksum}  {artifact.name}\n", encoding="utf-8")

            pub = root / "release-public.pem"
            pub.write_text("public-key", encoding="utf-8")

            dm = DeployManager(state)
            with patch("operations.release_pipeline.ReleasePipeline.verify_artifact_signature", return_value=True):
                with self.assertRaises(RuntimeError):
                    dm.promote_verified(
                        stage="production",
                        version="4.1.1",
                        config_path=cfg,
                        manifest_path=manifest,
                        checksums_path=sums,
                        public_key_path=pub,
                        require_signatures=True,
                    )

    def test_deploy_audit_export_and_verify(self):
        from operations.deploy_manager import DeployManager

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state = root / "deploy_state.json"
            c1 = root / "dev.toml"
            c2 = root / "prod.toml"
            c1.write_text("[safety]\nenabled=true\n", encoding="utf-8")
            c2.write_text("[safety]\nenabled=true\nconfirm_destructive=true\n", encoding="utf-8")

            dm = DeployManager(state)
            dm.deploy("dev", "4.1.0-rc1", c1)
            dm.deploy("production", "4.1.0", c2)
            dm.detect_drift(c2)

            out = dm.export_audit_json(root / "deploy_audit.json")
            result = dm.verify_audit_export(out)
            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["entries_checked"], 1)

    def test_canary_auto_rollback_on_breach(self):
        from operations.deploy_manager import DeployManager

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state = root / "deploy_state.json"
            cfg = root / "prod.toml"
            cfg.write_text("[safety]\nenabled=true\n", encoding="utf-8")

            artifact = root / "neuroshell-4.2.0.whl"
            artifact.write_bytes(b"artifact-bytes")
            checksum = __import__("hashlib").sha256(artifact.read_bytes()).hexdigest()
            sig = artifact.with_suffix(artifact.suffix + ".sig")
            sig.write_bytes(b"sig")

            manifest = root / "release-manifest.json"
            manifest.write_text(json.dumps({
                "version": "4.2.0",
                "stage": "production",
                "artifacts": [{
                    "path": str(artifact),
                    "size_bytes": artifact.stat().st_size,
                    "sha256": checksum,
                    "signature_path": str(sig),
                }],
            }), encoding="utf-8")
            sums = root / "SHA256SUMS"
            sums.write_text(f"{checksum}  {artifact.name}\n", encoding="utf-8")
            pub = root / "release-public.pem"
            pub.write_text("public-key", encoding="utf-8")

            dm = DeployManager(state)
            dm.deploy("staging", "4.1.9", cfg)
            dm.add_allowed_key(pub)

            with patch("operations.release_pipeline.ReleasePipeline.verify_artifact_signature", return_value=True):
                result = dm.canary_promote(
                    stage="production",
                    version="4.2.0",
                    config_path=cfg,
                    manifest_path=manifest,
                    checksums_path=sums,
                    public_key_path=pub,
                    slo_snapshot={"budget_consumed_ratio": 1.5, "alerts": [{"severity": "critical"}]},
                    max_budget_consumed_ratio=1.0,
                )

            self.assertFalse(result["promoted"])
            self.assertTrue(result["rolled_back"])
