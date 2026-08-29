# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
"""Tests for scripts/sign_release.py — the release-manifest signing tool.

These tests exercise the full offline signing flow (keygen → manifest →
sign → verify) plus the negative paths the C++ client relies on: URL
allowlist enforcement, schema validation, tamper detection.
"""

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest

pytest.importorskip("cryptography")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sign_release  # noqa: E402


@pytest.fixture()
def keydir(tmp_path):
    d = tmp_path / "keys"
    assert sign_release.main(["keygen", "--out-dir", str(d)]) == 0
    return d


@pytest.fixture()
def artifact(tmp_path):
    p = tmp_path / "neuroshell"
    p.write_bytes(b"\x7fELF" + os.urandom(4096))
    return p


GOOD_URL = ("https://github.com/abneeshsingh21/neuroshell/releases/"
            "download/v9.9.9/neuroshell")


class TestKeygen:
    def test_creates_keypair(self, keydir):
        priv = keydir / "update_signing.key"
        pub = keydir / "update_signing.pub"
        assert priv.exists() and pub.exists()
        assert len(bytes.fromhex(priv.read_text().strip())) == 32
        assert len(bytes.fromhex(pub.read_text().strip())) == 32

    def test_private_key_mode_0600(self, keydir):
        mode = stat.S_IMODE((keydir / "update_signing.key").stat().st_mode)
        assert mode == 0o600

    def test_refuses_overwrite(self, keydir):
        assert sign_release.main(["keygen", "--out-dir", str(keydir)]) == 1


class TestManifest:
    def test_builds_valid_manifest(self, tmp_path, artifact):
        out = tmp_path / "manifest.json"
        rc = sign_release.main([
            "manifest", "--version", "9.9.9", "--expires-days", "30",
            "--artifact", f"linux-x86_64:{artifact}:{GOOD_URL}",
            "--out", str(out),
        ])
        assert rc == 0
        doc = json.loads(out.read_text())
        assert doc["schema"] == 1
        assert doc["version"] == "9.9.9"
        assert doc["expires_at"] - doc["created_at"] == 30 * 86400
        art = doc["artifacts"][0]
        assert art["platform"] == "linux-x86_64"
        assert art["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert art["size"] == artifact.stat().st_size

    def test_rejects_unknown_platform(self, tmp_path, artifact):
        rc = sign_release.main([
            "manifest", "--version", "9.9.9",
            "--artifact", f"amiga-68k:{artifact}:{GOOD_URL}",
            "--out", str(tmp_path / "m.json"),
        ])
        assert rc == 1

    @pytest.mark.parametrize("bad_url", [
        "http://github.com/x/y",                    # not https
        "https://evil.com/neuroshell",              # host not allowlisted
        "https://github.com.evil.com/neuroshell",   # suffix confusion
        "https://github.com@evil.com/neuroshell",   # userinfo confusion
        "https://github.com:8443/neuroshell",       # explicit port
        "https://github.com",                       # no path
    ])
    def test_rejects_disallowed_urls(self, tmp_path, artifact, bad_url):
        rc = sign_release.main([
            "manifest", "--version", "9.9.9",
            "--artifact", f"linux-x86_64:{artifact}:{bad_url}",
            "--out", str(tmp_path / "m.json"),
        ])
        assert rc == 1


class TestSignVerify:
    def _make_signed(self, tmp_path, keydir, artifact):
        manifest = tmp_path / "manifest.json"
        sig = tmp_path / "manifest.json.sig"
        assert sign_release.main([
            "manifest", "--version", "9.9.9",
            "--artifact", f"linux-x86_64:{artifact}:{GOOD_URL}",
            "--out", str(manifest),
        ]) == 0
        assert sign_release.main([
            "sign", "--key", str(keydir / "update_signing.key"),
            "--manifest", str(manifest), "--out", str(sig),
        ]) == 0
        return manifest, sig

    def test_sign_then_verify_roundtrip(self, tmp_path, keydir, artifact):
        manifest, sig = self._make_signed(tmp_path, keydir, artifact)
        assert len(bytes.fromhex(sig.read_text().strip())) == 64
        assert sign_release.main([
            "verify", "--pubkey", str(keydir / "update_signing.pub"),
            "--manifest", str(manifest), "--sig", str(sig),
        ]) == 0

    def test_verify_detects_manifest_tamper(self, tmp_path, keydir, artifact):
        manifest, sig = self._make_signed(tmp_path, keydir, artifact)
        raw = manifest.read_bytes()
        manifest.write_bytes(raw.replace(b"9.9.9", b"9.9.8", 1))
        assert sign_release.main([
            "verify", "--pubkey", str(keydir / "update_signing.pub"),
            "--manifest", str(manifest), "--sig", str(sig),
        ]) == 1

    def test_verify_detects_sig_tamper(self, tmp_path, keydir, artifact):
        manifest, sig = self._make_signed(tmp_path, keydir, artifact)
        raw = bytearray(bytes.fromhex(sig.read_text().strip()))
        raw[5] ^= 0x01
        sig.write_text(raw.hex() + "\n")
        assert sign_release.main([
            "verify", "--pubkey", str(keydir / "update_signing.pub"),
            "--manifest", str(manifest), "--sig", str(sig),
        ]) == 1

    def test_verify_rejects_wrong_key(self, tmp_path, keydir, artifact):
        manifest, sig = self._make_signed(tmp_path, keydir, artifact)
        other = tmp_path / "otherkeys"
        assert sign_release.main(["keygen", "--out-dir", str(other)]) == 0
        assert sign_release.main([
            "verify", "--pubkey", str(other / "update_signing.pub"),
            "--manifest", str(manifest), "--sig", str(sig),
        ]) == 1

    def test_sign_rejects_wrong_schema(self, tmp_path, keydir):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"schema": 999, "version": "1.0.0"}))
        assert sign_release.main([
            "sign", "--key", str(keydir / "update_signing.key"),
            "--manifest", str(bad), "--out", str(tmp_path / "s.sig"),
        ]) == 1

    def test_verify_flags_expired_manifest(self, tmp_path, keydir, artifact):
        manifest = tmp_path / "manifest.json"
        sig = tmp_path / "manifest.json.sig"
        doc = {
            "schema": 1, "version": "9.9.9",
            "created_at": 1000, "expires_at": 2000,  # long past
            "min_version": "0.0.0",
            "artifacts": [{
                "platform": "linux-x86_64", "name": "neuroshell",
                "sha256": "a" * 64, "size": 4100, "url": GOOD_URL,
            }],
        }
        manifest.write_text(json.dumps(doc))
        assert sign_release.main([
            "sign", "--key", str(keydir / "update_signing.key"),
            "--manifest", str(manifest), "--out", str(sig),
        ]) == 0
        # signature is VALID but policy must still flag the expiry
        assert sign_release.main([
            "verify", "--pubkey", str(keydir / "update_signing.pub"),
            "--manifest", str(manifest), "--sig", str(sig),
        ]) == 1
