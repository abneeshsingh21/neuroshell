# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
"""Phase 9 (v5.17): WASM Plugin Runtime tests.

Covers manifest validation, the informed-consent install gate, SHA-256
module pinning, capability-scoped WASI execution (preopens, env
allowlist, stdin/stdout wiring), fuel exhaustion, missing-export and
trap handling, uninstall, listing, and the hash-chained audit trail.

Plugins are authored inline as WAT text — wasmtime compiles it directly,
so no external toolchain is needed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.mcp_server import MCPAuditLog  # noqa: E402
from core.plugin_runtime import (  # noqa: E402
    MAX_FUEL,
    MAX_MEMORY_BYTES,
    PluginError,
    PluginManifest,
    PluginRuntime,
    wasmtime_available,
)

pytestmark = pytest.mark.skipif(
    not wasmtime_available(), reason="wasmtime not installed")


# ─────────────────────────────────────────────────────────────
# WAT fixtures
# ─────────────────────────────────────────────────────────────

HELLO_WAT = r"""
(module
  (import "wasi_snapshot_preview1" "fd_write"
    (func $fd_write (param i32 i32 i32 i32) (result i32)))
  (memory (export "memory") 1)
  (data (i32.const 8) "hello-plugin\n")
  (func (export "_start")
    (i32.store (i32.const 0) (i32.const 8))
    (i32.store (i32.const 4) (i32.const 13))
    (call $fd_write (i32.const 1) (i32.const 0) (i32.const 1) (i32.const 40))
    drop))
"""

INFINITE_LOOP_WAT = '(module (func (export "_start") (loop br 0)))'

NO_START_WAT = '(module (func (export "other") (nop)))'

# Reads one byte from stdin, echoes stdout "got" if it read anything.
STDIN_WAT = r"""
(module
  (import "wasi_snapshot_preview1" "fd_read"
    (func $fd_read (param i32 i32 i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "fd_write"
    (func $fd_write (param i32 i32 i32 i32) (result i32)))
  (memory (export "memory") 1)
  (data (i32.const 100) "got\n")
  (func (export "_start")
    ;; read up to 8 bytes from fd 0 into offset 16
    (i32.store (i32.const 0) (i32.const 16))
    (i32.store (i32.const 4) (i32.const 8))
    (call $fd_read (i32.const 0) (i32.const 0) (i32.const 1) (i32.const 40))
    drop
    ;; if nread > 0, write "got\n"
    (if (i32.gt_u (i32.load (i32.const 40)) (i32.const 0))
      (then
        (i32.store (i32.const 48) (i32.const 100))
        (i32.store (i32.const 52) (i32.const 4))
        (call $fd_write (i32.const 1) (i32.const 48) (i32.const 1) (i32.const 60))
        drop))))
"""


def make_manifest(**overrides) -> dict:
    m = {
        "schema": 1,
        "name": "testplug",
        "version": "1.0.0",
        "description": "a test plugin",
        "permissions": {},
        "limits": {},
    }
    m.update(overrides)
    return m


@pytest.fixture()
def rt(tmp_path):
    return PluginRuntime(root=tmp_path / "store",
                         audit=MCPAuditLog(tmp_path / "audit.jsonl"))


def write_plugin(tmp_path, wat=HELLO_WAT, manifest=None):
    wasm = tmp_path / "p.wat"
    wasm.write_text(wat)
    mf = tmp_path / "m.json"
    mf.write_text(json.dumps(manifest or make_manifest()))
    return wasm, mf


# ─────────────────────────────────────────────────────────────
# Manifest validation
# ─────────────────────────────────────────────────────────────

class TestManifest:
    def test_valid_manifest_parses(self):
        m = PluginManifest.parse(make_manifest(
            permissions={"fs_read": ["./data"], "fs_write": [], "env": ["LANG"]},
            limits={"fuel": 1000, "memory_bytes": 1 << 20}))
        assert m.name == "testplug"
        assert m.fs_read == ["./data"]
        assert m.env == ["LANG"]
        assert m.fuel == 1000

    def test_wrong_schema_rejected(self):
        with pytest.raises(PluginError, match="schema"):
            PluginManifest.parse(make_manifest(schema=99))

    @pytest.mark.parametrize("bad", [
        "", "UPPER", "1starts-with-digit", "has space", "a" * 70, "x",
        "../evil", "name;rm",
    ])
    def test_bad_names_rejected(self, bad):
        with pytest.raises(PluginError, match="name"):
            PluginManifest.parse(make_manifest(name=bad))

    @pytest.mark.parametrize("bad", ["1.0", "v1.0.0", "1.0.0-beta", "", "abc"])
    def test_bad_versions_rejected(self, bad):
        with pytest.raises(PluginError, match="semver"):
            PluginManifest.parse(make_manifest(version=bad))

    def test_limits_are_clamped_to_host_ceilings(self):
        m = PluginManifest.parse(make_manifest(
            limits={"fuel": MAX_FUEL * 100, "memory_bytes": MAX_MEMORY_BYTES * 100}))
        assert m.fuel == MAX_FUEL
        assert m.memory_bytes == MAX_MEMORY_BYTES

    def test_too_many_preopens_rejected(self):
        with pytest.raises(PluginError, match="at most"):
            PluginManifest.parse(make_manifest(
                permissions={"fs_read": [f"./d{i}" for i in range(20)]}))

    def test_bad_env_names_rejected(self):
        with pytest.raises(PluginError, match="env"):
            PluginManifest.parse(make_manifest(
                permissions={"env": ["OK_VAR", "bad-dash"]}))

    def test_nul_byte_path_rejected(self):
        with pytest.raises(PluginError, match="invalid path"):
            PluginManifest.parse(make_manifest(
                permissions={"fs_read": ["./ok", "bad\x00path"]}))

    def test_bad_entry_rejected(self):
        with pytest.raises(PluginError, match="entry"):
            PluginManifest.parse(make_manifest(entry="not valid!"))

    def test_permission_summary_mentions_capabilities(self):
        m = PluginManifest.parse(make_manifest(
            permissions={"fs_read": ["./data"], "fs_write": ["./out"],
                         "env": ["LANG"]}))
        s = m.permission_summary()
        assert "./data" in s and "./out" in s and "LANG" in s
        assert "network" in s.lower()

    def test_roundtrip_to_dict(self):
        m = PluginManifest.parse(make_manifest(
            permissions={"fs_read": ["./d"], "env": ["HOME"]}))
        m2 = PluginManifest.parse(m.to_dict())
        assert m2.name == m.name and m2.fs_read == m.fs_read


# ─────────────────────────────────────────────────────────────
# Install: consent gate, validation, pinning
# ─────────────────────────────────────────────────────────────

class TestInstall:
    def test_install_requires_approval(self, rt, tmp_path):
        wasm, mf = write_plugin(tmp_path)
        with pytest.raises(PluginError, match="approval"):
            rt.install(wasm, mf)
        assert rt.list_plugins() == []   # nothing landed on disk

    def test_approved_install_pins_sha256(self, rt, tmp_path):
        wasm, mf = write_plugin(tmp_path)
        m = rt.install(wasm, mf, approved=True)
        assert len(m.sha256) == 64
        stored = json.loads(
            (rt.root / "testplug" / "plugin.json").read_text())
        assert stored["sha256"] == m.sha256

    def test_invalid_wat_rejected(self, rt, tmp_path):
        wasm = tmp_path / "bad.wat"
        wasm.write_text("(module (this is not wat")
        mf = tmp_path / "m.json"
        mf.write_text(json.dumps(make_manifest()))
        with pytest.raises(PluginError, match="validation|neither"):
            rt.install(wasm, mf, approved=True)

    def test_garbage_binary_rejected(self, rt, tmp_path):
        wasm = tmp_path / "junk.wasm"
        wasm.write_bytes(b"\x7fELF not wasm at all")
        mf = tmp_path / "m.json"
        mf.write_text(json.dumps(make_manifest()))
        with pytest.raises(PluginError, match="neither"):
            rt.install(wasm, mf, approved=True)

    def test_bad_manifest_json_rejected(self, rt, tmp_path):
        wasm = tmp_path / "p.wat"
        wasm.write_text(HELLO_WAT)
        mf = tmp_path / "m.json"
        mf.write_text("{ not json")
        with pytest.raises(PluginError, match="JSON"):
            rt.install(wasm, mf, approved=True)

    def test_reinstall_updates_hash(self, rt, tmp_path):
        wasm, mf = write_plugin(tmp_path)
        m1 = rt.install(wasm, mf, approved=True)
        wasm.write_text(NO_START_WAT)  # different module bytes
        m2 = rt.install(wasm, mf, approved=True)
        assert m1.sha256 != m2.sha256
        assert "does not export" in rt.run("testplug").error


# ─────────────────────────────────────────────────────────────
# Run: sandbox semantics
# ─────────────────────────────────────────────────────────────

class TestRun:
    def test_hello_writes_stdout(self, rt, tmp_path):
        wasm, mf = write_plugin(tmp_path)
        rt.install(wasm, mf, approved=True)
        r = rt.run("testplug")
        assert r.success
        assert r.stdout == "hello-plugin\n"
        assert r.fuel_used > 0
        assert r.duration_ms >= 0

    def test_tampered_module_refuses_to_run(self, rt, tmp_path):
        wasm, mf = write_plugin(tmp_path)
        rt.install(wasm, mf, approved=True)
        (rt.root / "testplug" / "plugin.wasm").write_text("(module)")
        r = rt.run("testplug")
        assert not r.success
        assert "hash mismatch" in r.error

    def test_fuel_bomb_is_trapped(self, rt, tmp_path):
        wasm, mf = write_plugin(
            tmp_path, wat=INFINITE_LOOP_WAT,
            manifest=make_manifest(name="bomb", limits={"fuel": 100_000}))
        rt.install(wasm, mf, approved=True)
        r = rt.run("bomb")
        assert not r.success
        assert r.trap == "fuel_exhausted"
        assert "CPU budget" in r.error

    def test_missing_export_reported(self, rt, tmp_path):
        wasm, mf = write_plugin(tmp_path, wat=NO_START_WAT,
                                manifest=make_manifest(name="noentry"))
        rt.install(wasm, mf, approved=True)
        r = rt.run("noentry")
        assert not r.success
        assert "does not export" in r.error

    def test_stdin_is_wired(self, rt, tmp_path):
        wasm, mf = write_plugin(tmp_path, wat=STDIN_WAT,
                                manifest=make_manifest(name="reader"))
        rt.install(wasm, mf, approved=True)
        r = rt.run("reader", stdin_data="ping")
        assert r.success
        assert r.stdout == "got\n"

    def test_empty_stdin_reads_nothing(self, rt, tmp_path):
        wasm, mf = write_plugin(tmp_path, wat=STDIN_WAT,
                                manifest=make_manifest(name="reader2"))
        rt.install(wasm, mf, approved=True)
        r = rt.run("reader2", stdin_data="")
        assert r.success
        assert r.stdout == ""

    def test_missing_granted_dir_is_an_error(self, rt, tmp_path):
        wasm, mf = write_plugin(
            tmp_path,
            manifest=make_manifest(
                name="fsplug",
                permissions={"fs_read": [str(tmp_path / "does_not_exist")]}))
        rt.install(wasm, mf, approved=True)
        r = rt.run("fsplug")
        assert not r.success
        assert "does not exist" in r.error

    def test_not_installed(self, rt):
        r = rt.run("ghost")
        assert not r.success
        assert "not installed" in r.error

    def test_env_allowlist(self, rt, tmp_path, monkeypatch):
        monkeypatch.setenv("NS_PLUGIN_TEST_VAR", "visible")
        wasm, mf = write_plugin(
            tmp_path,
            manifest=make_manifest(name="envplug",
                                   permissions={"env": ["NS_PLUGIN_TEST_VAR"]}))
        m = rt.install(wasm, mf, approved=True)
        assert m.env == ["NS_PLUGIN_TEST_VAR"]
        r = rt.run("envplug")     # module ignores env; run must still succeed
        assert r.success


# ─────────────────────────────────────────────────────────────
# Lifecycle: list / uninstall / audit
# ─────────────────────────────────────────────────────────────

class TestLifecycle:
    def test_list_and_uninstall(self, rt, tmp_path):
        wasm, mf = write_plugin(tmp_path)
        rt.install(wasm, mf, approved=True)
        assert [m.name for m in rt.list_plugins()] == ["testplug"]
        assert rt.uninstall("testplug") is True
        assert rt.list_plugins() == []
        assert rt.uninstall("testplug") is False

    def test_uninstall_rejects_bad_names(self, rt):
        with pytest.raises(PluginError):
            rt.uninstall("../../etc")

    def test_corrupt_store_entry_is_invisible(self, rt):
        bad = rt.root / "broken"
        bad.mkdir(parents=True)
        (bad / "plugin.json").write_text("{ nope")
        assert rt.list_plugins() == []

    def test_audit_chain_records_lifecycle(self, rt, tmp_path):
        wasm, mf = write_plugin(tmp_path)
        rt.install(wasm, mf, approved=True)
        rt.run("testplug")
        (rt.root / "testplug" / "plugin.wasm").write_text("(module)")
        rt.run("testplug")            # hash mismatch
        rt.uninstall("testplug")
        ok, n = rt.audit.verify()
        assert ok and n == 4
        events = [json.loads(l)["event"] for l in
                  rt.audit.path.read_text().strip().splitlines()]
        assert events == ["plugin_installed", "plugin_run",
                          "plugin_hash_mismatch", "plugin_uninstalled"]


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

class TestCLI:
    def test_cli_install_list_run_uninstall(self, tmp_path, monkeypatch, capsys):
        import core.plugin_runtime as pr
        monkeypatch.setattr(pr, "PLUGIN_DIR", tmp_path / "store")
        wasm, mf = write_plugin(tmp_path)

        rc = pr.cli_main(["install", str(wasm), str(mf)])
        assert rc == 3                      # consent required
        out = capsys.readouterr()
        assert "approval" in out.err

        rc = pr.cli_main(["install", str(wasm), str(mf), "--yes"])
        assert rc == 0
        assert "installed" in capsys.readouterr().out

        rc = pr.cli_main(["list"])
        assert rc == 0
        assert "testplug" in capsys.readouterr().out

        rc = pr.cli_main(["run", "testplug"])
        assert rc == 0
        assert "hello-plugin" in capsys.readouterr().out

        rc = pr.cli_main(["info", "testplug"])
        assert rc == 0
        assert "network" in capsys.readouterr().out

        rc = pr.cli_main(["uninstall", "testplug"])
        assert rc == 0

        rc = pr.cli_main(["run", "testplug"])
        assert rc == 1