# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
"""Tests for SLSA v1 provenance (scripts/provenance.py, verify_provenance.py)
and its wiring into the Phase 1 signing flow (sign_release.py attest).

Covers the four policy scenarios the supply chain depends on — valid
provenance passes, tampered subject digest fails, wrong signature fails,
downgraded builder fails — plus DSSE envelopes, shape validation, and the
fail-closed paths.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("cryptography")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import provenance  # noqa: E402
import sign_release  # noqa: E402
import verify_provenance  # noqa: E402

BUILDER = ("https://github.com/abneeshsingh21/neuroshell/.github/workflows/"
           "release.yml@refs/heads/main")
OTHER_BUILDER = "https://example.com/legacy-builder@v0"
COMMIT = "a" * 40


@pytest.fixture(scope="module")
def keypair(tmp_path_factory):
    d = tmp_path_factory.mktemp("keys")
    assert sign_release.main(["keygen", "--out-dir", str(d)]) == 0
    return d / "update_signing.key", d / "update_signing.pub"


@pytest.fixture()
def artifact(tmp_path):
    p = tmp_path / "NeuroShell-linux-x86_64.tar.gz"
    p.write_bytes(b"\x1f\x8b" + b"release-payload" * 64)
    return p


@pytest.fixture()
def signed(tmp_path, keypair, artifact):
    """A complete generate→sign→verify chain over one artifact."""
    key, pub = keypair
    statement = tmp_path / "provenance.intoto.json"
    sig = tmp_path / "provenance.intoto.json.sig"
    assert provenance.main([
        "generate", "--subject", f"{artifact.name}:{artifact}",
        "--builder-id", BUILDER, "--source-uri",
        "git+https://github.com/abneeshsingh21/neuroshell",
        "--commit", COMMIT, "--invocation-id", "run-1",
        "--started-on", "2026-08-30T10:00:00Z",
        "--finished-on", "2026-08-30T10:05:00Z",
        "--out", str(statement)]) == 0
    assert provenance.main(["sign", "--key", str(key),
                            "--statement", str(statement), "--out", str(sig)]) == 0
    return statement, sig, pub, artifact


def _verify(*, pub, statement, sig=None, dsse=None, builders=(), artifacts=()):
    return verify_provenance.verify(
        pubkey=str(pub), statement=statement, sig=sig, dsse=dsse,
        expect_builders=list(builders), expect_buildtype=None,
        artifacts=list(artifacts))


class TestStatementShape:
    def test_statement_is_slsa_v1(self, signed):
        doc = json.loads(signed[0].read_text())
        assert doc["_type"] == "https://in-toto.io/Statement/v1"
        assert doc["predicateType"] == "https://slsa.dev/provenance/v1"
        bd = doc["predicate"]["buildDefinition"]
        assert bd["externalParameters"]["source"].endswith("@" + COMMIT)
        assert bd["resolvedDependencies"][0]["digest"]["gitCommit"] == COMMIT
        assert doc["predicate"]["runDetails"]["builder"]["id"] == BUILDER
        assert doc["predicate"]["runDetails"]["metadata"]["invocationId"] == "run-1"

    def test_subjects_sorted_by_name(self, tmp_path):
        arts = []
        for name in ("c.tar.gz", "a.tar.gz", "b.tar.gz"):
            p = tmp_path / name
            p.write_bytes(name.encode())
            arts.append(p)
        doc = provenance.build_statement(
            [{"name": p.name, "sha256": provenance._file_sha256(p)} for p in arts],
            BUILDER, "git+https://x", COMMIT)
        assert [s["name"] for s in doc["subject"]] == ["a.tar.gz", "b.tar.gz", "c.tar.gz"]

    def test_rejects_bad_digest(self):
        with pytest.raises(provenance.ProvenanceError):
            provenance.build_statement(
                [{"name": "x", "sha256": "zz"}], BUILDER, "git+https://x", COMMIT)

    def test_rejects_missing_builder(self):
        with pytest.raises(provenance.ProvenanceError):
            provenance.build_statement(
                [{"name": "x", "sha256": "a" * 64}], "", "git+https://x", COMMIT)

    def test_no_commit_omits_resolved_deps(self):
        doc = provenance.build_statement(
            [{"name": "x", "sha256": "a" * 64}], BUILDER, "git+https://x", "")
        assert doc["predicate"]["buildDefinition"]["resolvedDependencies"] == []


class TestTheFourScenarios:
    def test_valid_provenance_passes(self, signed):
        statement, sig, pub, artifact = signed
        doc = _verify(pub=pub, statement=statement, sig=sig,
                      builders=[BUILDER], artifacts=[(artifact.name, artifact)])
        assert doc["predicate"]["runDetails"]["builder"]["id"] == BUILDER

    def test_tampered_subject_digest_fails(self, signed, tmp_path):
        statement, sig, pub, artifact = signed
        doc = json.loads(statement.read_text())
        doc["subject"][0]["digest"]["sha256"] = "b" * 64
        tampered = tmp_path / "tampered.json"
        tampered.write_text(json.dumps(doc))
        with pytest.raises(verify_provenance.VerificationError):
            _verify(pub=pub, statement=tampered, sig=sig)

    def test_wrong_signature_fails(self, signed, tmp_path):
        statement, _, pub, _ = signed
        bad = tmp_path / "bad.sig"
        bad.write_text("00" * 64)
        with pytest.raises(verify_provenance.VerificationError, match="signature"):
            _verify(pub=pub, statement=statement, sig=bad)

    def test_downgraded_builder_fails(self, signed):
        statement, sig, pub, _ = signed
        with pytest.raises(verify_provenance.VerificationError, match="builder"):
            _verify(pub=pub, statement=statement, sig=sig,
                    builders=[OTHER_BUILDER])

    def test_builder_any_of_semantics(self, signed):
        statement, sig, pub, _ = signed
        _verify(pub=pub, statement=statement, sig=sig,
                builders=[OTHER_BUILDER, BUILDER])  # passes: BUILDER allowed

    def test_rebuilt_artifact_digest_mismatch_fails(self, signed, tmp_path):
        """Statement intact + locally modified artifact → digest gate trips."""
        statement, sig, pub, artifact = signed
        rebuilt = tmp_path / "rebuilt.tar.gz"
        rebuilt.write_bytes(b"attacker-rebuild")
        with pytest.raises(verify_provenance.VerificationError, match="digest"):
            _verify(pub=pub, statement=statement, sig=sig,
                    artifacts=[(artifact.name, rebuilt)])

    def test_unknown_artifact_name_fails(self, signed, tmp_path):
        statement, sig, pub, artifact = signed
        other = tmp_path / "other.bin"
        other.write_bytes(b"x")
        with pytest.raises(verify_provenance.VerificationError, match="not a subject"):
            _verify(pub=pub, statement=statement, sig=sig,
                    artifacts=[("other.bin", other)])


class TestShapeValidation:
    def test_wrong_statement_type_rejected(self, signed):
        statement, _, _, _ = signed
        doc = json.loads(statement.read_text())
        doc["_type"] = "https://example.com/other"
        with pytest.raises(verify_provenance.VerificationError, match="_type"):
            verify_provenance.validate_statement_shape(doc)

    def test_missing_predicate_rejected(self, signed):
        statement, _, _, _ = signed
        doc = json.loads(statement.read_text())
        del doc["predicate"]
        with pytest.raises(verify_provenance.VerificationError, match="predicate"):
            verify_provenance.validate_statement_shape(doc)

    def test_non_hex_digest_rejected(self, tmp_path):
        doc = {"_type": "https://in-toto.io/Statement/v1",
               "predicateType": "https://slsa.dev/provenance/v1",
               "subject": [{"name": "x", "digest": {"sha256": "NOTHEX"}}],
               "predicate": {"buildDefinition": {"buildType": "t"},
                             "runDetails": {"builder": {"id": "b"}}}}
        with pytest.raises(verify_provenance.VerificationError, match="hex"):
            verify_provenance.validate_statement_shape(doc)


class TestDSSE:
    def test_dsse_roundtrip(self, signed, tmp_path, keypair):
        key, pub = keypair
        statement, _, _, _ = signed
        env_path = tmp_path / "provenance.dsse.json"
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "provenance.py"), "sign",
             "--key", str(key), "--statement", str(statement),
             "--out", str(tmp_path / "x.sig"), "--dsse", str(env_path)],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        doc = _verify(pub=pub, statement=statement, dsse=env_path)
        assert doc["_type"] == "https://in-toto.io/Statement/v1"

    def test_dsse_tampered_payload_fails(self, signed, tmp_path, keypair):
        key, pub = keypair
        statement, _, _, _ = signed
        env_path = tmp_path / "env.json"
        provenance.main(["sign", "--key", str(key), "--statement", str(statement),
                         "--out", str(tmp_path / "x.sig"), "--dsse", str(env_path)])
        env = json.loads(env_path.read_text())
        env["payload"] = env["payload"][:-2] + "AA=="  # flip decoded bytes
        bad = tmp_path / "bad-env.json"
        bad.write_text(json.dumps(env))
        with pytest.raises(verify_provenance.VerificationError, match="DSSE"):
            _verify(pub=pub, statement=statement, dsse=bad)

    def test_pae_matches_dsse_spec(self):
        ptype = "application/vnd.in-toto+json"
        pae = provenance.pae(ptype, b'{"a":1}')
        assert pae == (f"DSSEv1 {len(ptype)} ".encode() + ptype.encode()
                       + b' 7 {"a":1}')


class TestSignReleaseWiring:
    def test_attest_end_to_end(self, tmp_path, keypair, artifact):
        key, pub = keypair
        statement = tmp_path / "prov.json"
        rc = sign_release.main([
            "attest", "--subject", f"{artifact.name}:{artifact}",
            "--builder-id", BUILDER, "--commit", COMMIT,
            "--key", str(key), "--out", str(statement)])
        assert rc == 0
        # self-verification gate inside attest already ran; verify externally too
        assert verify_provenance.main([
            "verify", "--pubkey", str(pub), "--statement", str(statement),
            "--sig", str(statement) + ".sig", "--expect-builder", BUILDER]) == 0

    def test_verify_attestation_subcommand(self, tmp_path, keypair, artifact):
        key, pub = keypair
        statement = tmp_path / "prov.json"
        assert sign_release.main([
            "attest", "--subject", f"{artifact.name}:{artifact}",
            "--builder-id", BUILDER, "--commit", COMMIT,
            "--key", str(key), "--out", str(statement)]) == 0
        assert sign_release.main([
            "verify-attestation", "--pubkey", str(pub),
            "--statement", str(statement), "--sig", str(statement) + ".sig",
            "--expect-builder", BUILDER,
            "--artifact", f"{artifact.name}:{artifact}"]) == 0

    def test_attest_refuses_missing_subject_file(self, tmp_path, keypair):
        key, _ = keypair
        rc = sign_release.main([
            "attest", "--subject", "ghost:/nonexistent/file",
            "--builder-id", BUILDER, "--key", str(key),
            "--out", str(tmp_path / "p.json")])
        assert rc == 1

    def test_detached_sig_covers_exact_bytes(self, signed):
        """Any byte change — even whitespace — breaks the signature."""
        statement, sig, pub, _ = signed
        raw = statement.read_bytes()
        statement.write_bytes(raw.replace(b"},\n", b"}, \n", 1))
        with pytest.raises(verify_provenance.VerificationError, match="signature"):
            _verify(pub=pub, statement=statement, sig=sig)
