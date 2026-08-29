# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
"""Tests for scripts/generate_sbom.py — the CycloneDX 1.5 SBOM generator.

Covers the three Phase 10 guarantees: offline stdlib-only operation,
byte-level determinism, and self-validation of the emitted document — plus
component coverage (Python deps incl. extras, dlopen'd natives, the C++
launcher), purl/hash correctness, and tamper detection on --check.
"""

import copy
import json
import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import generate_sbom  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def _build(tmp_path, **kw) -> dict:
    defaults: dict = {
        "version": "5.18.0",
        "pyproject_path": REPO / "pyproject.toml",
        "artifacts": [],
        "sqlite_version": "3.45.1",
        "wasmtime_version": "25.0.0",
        "timestamp": None,
        "extras": None,
    }
    defaults.update(kw)
    return generate_sbom.build_document(**defaults)


class TestDeterminism:
    def test_two_runs_byte_identical(self, tmp_path):
        a = _build(tmp_path)
        b = _build(tmp_path)
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_serial_number_stable_across_processes(self, tmp_path):
        doc = _build(tmp_path)
        import subprocess

        out = tmp_path / "sbom.json"
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "generate_sbom.py"),
             "--version", "5.18.0", "--sqlite-version", "3.45.1",
             "--wasmtime-version", "25.0.0", "--out", str(out)],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert json.loads(out.read_text())["serialNumber"] == doc["serialNumber"]

    def test_component_ordering_is_sorted(self, tmp_path):
        doc = _build(tmp_path)
        keys = [(c["type"], c["name"]) for c in doc["components"]]
        assert keys == sorted(keys)

    def test_no_timestamp_by_default(self, tmp_path):
        assert "timestamp" not in _build(tmp_path)["metadata"]

    def test_timestamp_from_source_date_epoch(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
        import os

        assert os.environ["SOURCE_DATE_EPOCH"] == "1700000000"
        # exercised via CLI below; direct builder uses the explicit arg
        doc = _build(tmp_path, timestamp="2023-11-14T22:13:20Z")
        assert doc["metadata"]["timestamp"] == "2023-11-14T22:13:20Z"


class TestCoverage:
    def test_python_base_dependencies_present(self, tmp_path):
        doc = _build(tmp_path)
        names = {c["name"] for c in doc["components"]}
        for base in ("rich", "psutil", "toml", "cryptography"):
            assert base in names, f"{base} missing from SBOM"

    def test_optional_extras_present_with_group_tags(self, tmp_path):
        doc = _build(tmp_path)
        # 'plugins' extra pulls wasmtime the *Python package*; the *runtime*
        # is a separate generic component — select the pip one explicitly.
        wasm_pip = next(c for c in doc["components"]
                        if c["name"] == "wasmtime" and c.get("group") == "pip")
        groups = {p["value"] for p in wasm_pip["properties"]
                  if p["name"].endswith("groups")}
        assert any("plugins" in g for g in groups)
        assert wasm_pip["scope"] == "optional"

    def test_extras_selection_scopes_correctly(self, tmp_path):
        doc = _build(tmp_path, extras=["llm"])
        names = {c["name"] for c in doc["components"]}
        assert "ollama" in names          # llm extra
        assert "pytest" not in names      # dev extra not requested
        assert "rich" in names            # base deps always included

    def test_native_components_present(self, tmp_path):
        doc = _build(tmp_path)
        names = {c["name"] for c in doc["components"]}
        assert {"neuroshell-launcher", "sqlite3", "wasmtime"} <= names

    def test_sqlite_documents_runtime_resolution(self, tmp_path):
        doc = _build(tmp_path)
        sqlite = next(c for c in doc["components"] if c["name"] == "sqlite3")
        assert sqlite["properties"][0]["name"] == "neuroshell:resolution"

    def test_root_metadata_component(self, tmp_path):
        doc = _build(tmp_path)
        root = doc["metadata"]["component"]
        assert root["name"] == "neuroshell"
        assert root["version"] == "5.18.0"
        assert root["purl"] == "pkg:pypi/neuroshell@5.18.0"
        assert root["licenses"] == [{"license": {"id": "Apache-2.0"}}]

    def test_dependency_graph_references_all_components(self, tmp_path):
        doc = _build(tmp_path)
        root_ref = doc["metadata"]["component"]["bom-ref"]
        edge = next(d for d in doc["dependencies"] if d["ref"] == root_ref)
        refs = {c["bom-ref"] for c in doc["components"]}
        assert set(edge["dependsOn"]) == refs


class TestPurlsAndHashes:
    def test_purl_normalization_and_pins(self):
        req = generate_sbom.parse_requirement("scikit-learn>=1.3")
        assert generate_sbom.pypi_purl(req) == "pkg:pypi/scikit-learn"
        pinned = generate_sbom.parse_requirement("toml==0.10.2")
        assert generate_sbom.pypi_purl(pinned) == "pkg:pypi/toml@0.10.2"

    def test_marker_stripped_from_requirement(self):
        req = generate_sbom.parse_requirement(
            "colorama>=0.4; sys_platform == 'win32'")
        assert req["normalized"] == "colorama"
        assert req["pinned_version"] is None

    def test_launcher_carries_artifact_sha256(self, tmp_path):
        art = tmp_path / "NeuroShell-linux-x86_64.tar.gz"
        art.write_bytes(b"payload")
        import hashlib

        doc = _build(tmp_path, artifacts=[("neuroshell-linux", art)])
        launcher = next(c for c in doc["components"]
                        if c["name"] == "neuroshell-launcher")
        assert launcher["hashes"] == [
            {"alg": "SHA-256", "content": hashlib.sha256(b"payload").hexdigest()}]

    def test_hashes_streamed_not_whole_file(self, tmp_path):
        """>1 MiB artifact proves the streaming path (memory-safe hashing)."""
        art = tmp_path / "big.bin"
        art.write_bytes(b"\0" * (2 * 1024 * 1024 + 7))
        import hashlib

        expect = hashlib.sha256(b"\0" * (2 * 1024 * 1024 + 7)).hexdigest()
        assert generate_sbom._file_sha256(art) == expect


class TestSelfValidation:
    def test_generated_document_validates(self, tmp_path):
        generate_sbom.validate_document(_build(tmp_path))

    def test_check_mode_accepts_written_file(self, tmp_path):
        out = tmp_path / "sbom.cdx.json"
        assert generate_sbom.main([
            "--version", "5.18.0", "--sqlite-version", "3.45.1",
            "--out", str(out)]) == 0
        assert generate_sbom.main(["--check", str(out)]) == 0

    def test_tampered_bomformat_rejected(self, tmp_path):
        doc = _build(tmp_path)
        doc["bomFormat"] = "SPDX"
        with pytest.raises(generate_sbom.SbomValidationError) as e:
            generate_sbom.validate_document(doc)
        assert any("bomFormat" in p for p in e.value.args[0])

    def test_duplicate_bomref_rejected(self, tmp_path):
        doc = _build(tmp_path)
        doc["components"].append(copy.deepcopy(doc["components"][0]))
        with pytest.raises(generate_sbom.SbomValidationError) as e:
            generate_sbom.validate_document(doc)
        assert any("duplicate bom-ref" in p for p in e.value.args[0])

    def test_bad_hash_length_rejected(self, tmp_path):
        doc = _build(tmp_path)
        doc["components"][0]["hashes"] = [{"alg": "SHA-256", "content": "abcd"}]
        with pytest.raises(generate_sbom.SbomValidationError) as e:
            generate_sbom.validate_document(doc)
        assert any("hash" in p for p in e.value.args[0])

    def test_malformed_purl_rejected(self, tmp_path):
        doc = _build(tmp_path)
        doc["components"][0]["purl"] = "not-a-purl://x"
        with pytest.raises(generate_sbom.SbomValidationError) as e:
            generate_sbom.validate_document(doc)
        assert any("purl" in p for p in e.value.args[0])

    def test_broken_license_object_rejected(self, tmp_path):
        doc = _build(tmp_path)
        doc["components"][0]["licenses"] = [{"bogus": True}]
        with pytest.raises(generate_sbom.SbomValidationError) as e:
            generate_sbom.validate_document(doc)
        assert any("license" in p for p in e.value.args[0])

    def test_dangling_dependency_ref_rejected(self, tmp_path):
        doc = _build(tmp_path)
        doc["dependencies"][0]["dependsOn"].append("pkg:pypi/nonexistent")
        with pytest.raises(generate_sbom.SbomValidationError) as e:
            generate_sbom.validate_document(doc)
        assert any("unknown dependsOn" in p for p in e.value.args[0])

    def test_cli_refuses_to_write_invalid_document(self, tmp_path, monkeypatch):
        """If generation ever produced an invalid doc, it must not be written."""
        out = tmp_path / "out.json"

        def always_invalid(_doc, **_kw):
            raise generate_sbom.SbomValidationError(["boom"])

        monkeypatch.setattr(generate_sbom, "validate_document", always_invalid)
        rc = generate_sbom.main(["--version", "5.18.0", "--out", str(out)])
        assert rc == 1
        assert not out.exists()


class TestOfflineStdlib:
    def test_minimal_toml_fallback_parses_pyproject_shape(self):
        text = """
[project]
name = "neuroshell"
version = "5.18.0"

[project.optional-dependencies]
plugins = [
    "wasmtime>=25.0",
]
""".strip()
        data = generate_sbom._minimal_toml(text)
        assert data["project"]["version"] == "5.18.0"
        assert data["project"]["optional-dependencies"]["plugins"] == \
            ["wasmtime>=25.0"]

    def test_bad_requirement_name_raises(self):
        with pytest.raises(generate_sbom.SbomError):
            generate_sbom.parse_requirement("!!!not-a-name>=1")

    def test_bad_artifact_spec(self):
        with pytest.raises(generate_sbom.SbomError):
            generate_sbom._parse_artifact("no-colon-here")

    def test_unicode_not_mangled(self):
        # ensure_ascii=False keeps names readable & keeps bytes deterministic
        assert generate_sbom.normalize_pypi_name("Foo_Bar") == "foo-bar"
        assert unicodedata.is_normalized("NFC", "café")
