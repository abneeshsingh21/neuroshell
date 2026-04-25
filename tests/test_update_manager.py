"""Tests for signed update manifest and channel helpers."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestUpdateManager(unittest.TestCase):
    def test_build_and_validate_manifest(self):
        from operations.update_manager import UpdateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            art = root / "NeuroShell-windows-x64.zip"
            art.write_bytes(b"payload")

            um = UpdateManager(root)
            manifest = um.build_manifest("4.2.0", "stable", [art], notes="release")
            self.assertEqual(manifest["version"], "4.2.0")
            self.assertEqual(manifest["channel"], "stable")
            self.assertEqual(len(manifest["artifacts"]), 1)

            check = um.validate_manifest_integrity(manifest)
            self.assertTrue(check["ok"])

    def test_select_channel_fallback(self):
        from operations.update_manager import UpdateManager

        self.assertEqual(UpdateManager.select_channel("beta"), "beta")
        self.assertEqual(UpdateManager.select_channel("unknown"), "stable")

    def test_verify_manifest_signature_uses_openssl_exit_status(self):
        from operations.update_manager import UpdateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = root / "update-manifest.json"
            sig = root / "update-manifest.json.sig"
            pub = root / "release-public.pem"
            manifest.write_text(json.dumps({"version": "1"}), encoding="utf-8")
            sig.write_bytes(b"sig")
            pub.write_text("pub", encoding="utf-8")

            um = UpdateManager(root)
            with patch("operations.update_manager.subprocess.run") as mocked:
                mocked.return_value.returncode = 0
                ok = um.verify_manifest_signature(manifest, sig, pub)
            self.assertTrue(ok)
