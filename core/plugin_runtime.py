# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell WASM Plugin Runtime (Phase 9, v5.17).

Runs third-party plugins as WebAssembly/WASI modules inside a
capability-scoped sandbox embedded in the daemon:

    • NO ambient authority — a plugin sees only the directories its
      manifest declares (WASI preopens), only the environment variables
      it lists, and has no network access at all (nothing is linked).
    • Deterministic resource ceilings — a fuel budget bounds CPU
      (runaway loops trap, they cannot hang the host), a memory limit
      bounds RAM, and stdout/stderr are size-capped.
    • Supply-chain pinning — the module's SHA-256 is recorded at install
      time and re-verified before every run; a swapped .wasm file
      refuses to load.
    • Informed consent — the permission surface (paths, env, limits) is
      shown at install time; install requires an explicit approval flag.

Manifest (plugin.json, shipped next to plugin.wasm):

    {
      "schema": 1,
      "name": "wordcount",
      "version": "1.0.0",
      "description": "Counts words on stdin",
      "entry": "_start",
      "permissions": {
        "fs_read":  ["./data"],
        "fs_write": [],
        "env":      ["LANG"]
      },
      "limits": {
        "fuel": 50000000,
        "memory_bytes": 67108864
      }
    }

The wasmtime embedding is an optional dependency: without it, install/
run fail with a clear message while the rest of NeuroShell is untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "PluginManifest",
    "PluginRunResult",
    "PluginError",
    "PluginRuntime",
    "wasmtime_available",
]

MANIFEST_SCHEMA = 1
PLUGIN_DIR = Path.home() / ".neuroshell" / "plugins"

# Host-enforced ceilings — a manifest may ask for less, never more.
MAX_FUEL = 500_000_000            # ~ a few CPU-seconds of wasm execution
DEFAULT_FUEL = 50_000_000
MAX_MEMORY_BYTES = 256 * 1024 * 1024
DEFAULT_MEMORY_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_BYTES = 1_000_000      # stdout/stderr capture cap
MAX_WASM_SIZE = 64 * 1024 * 1024  # refuse absurd module files
MAX_PREOPENS = 8
MAX_ENV_VARS = 16

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def wasmtime_available() -> bool:
    try:
        import wasmtime  # noqa: F401
        return True
    except ImportError:
        return False


class PluginError(Exception):
    """Raised for manifest, verification, and execution failures."""


# ═══════════════════════════════════════════════════════════
# Manifest
# ═══════════════════════════════════════════════════════════

@dataclass
class PluginManifest:
    name: str
    version: str
    description: str = ""
    entry: str = "_start"
    fs_read: list[str] = field(default_factory=list)
    fs_write: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    fuel: int = DEFAULT_FUEL
    memory_bytes: int = DEFAULT_MEMORY_BYTES
    sha256: str = ""          # filled at install time

    @classmethod
    def parse(cls, raw: dict) -> PluginManifest:
        if not isinstance(raw, dict):
            raise PluginError("manifest must be a JSON object")
        if raw.get("schema") != MANIFEST_SCHEMA:
            raise PluginError(
                f"unsupported manifest schema {raw.get('schema')!r} "
                f"(expected {MANIFEST_SCHEMA})")

        name = raw.get("name", "")
        if not isinstance(name, str) or not _NAME_RE.match(name):
            raise PluginError(
                "invalid plugin name (lowercase letters, digits, '-', '_'; "
                "2-64 chars; must start with a letter)")

        version = raw.get("version", "")
        if not isinstance(version, str) or not re.match(r"^\d+\.\d+\.\d+$", version):
            raise PluginError("version must be semver 'X.Y.Z'")

        entry = raw.get("entry", "_start")
        if not isinstance(entry, str) or not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$", entry):
            raise PluginError("invalid entry export name")

        perms = raw.get("permissions") or {}
        if not isinstance(perms, dict):
            raise PluginError("permissions must be an object")

        def _path_list(key: str) -> list[str]:
            vals = perms.get(key) or []
            if not isinstance(vals, list) or not all(isinstance(v, str) for v in vals):
                raise PluginError(f"permissions.{key} must be a list of strings")
            if len(vals) > MAX_PREOPENS:
                raise PluginError(f"permissions.{key}: at most {MAX_PREOPENS} paths")
            for v in vals:
                if "\x00" in v or v.strip() == "":
                    raise PluginError(f"permissions.{key}: invalid path {v!r}")
            return vals

        env_vars = perms.get("env") or []
        if not isinstance(env_vars, list) or not all(
                isinstance(v, str) and _ENV_RE.match(v) for v in env_vars):
            raise PluginError("permissions.env must be a list of env var names")
        if len(env_vars) > MAX_ENV_VARS:
            raise PluginError(f"permissions.env: at most {MAX_ENV_VARS} vars")

        limits = raw.get("limits") or {}
        if not isinstance(limits, dict):
            raise PluginError("limits must be an object")
        fuel = limits.get("fuel", DEFAULT_FUEL)
        memory = limits.get("memory_bytes", DEFAULT_MEMORY_BYTES)
        if not isinstance(fuel, int) or fuel <= 0:
            raise PluginError("limits.fuel must be a positive integer")
        if not isinstance(memory, int) or memory <= 0:
            raise PluginError("limits.memory_bytes must be a positive integer")
        # Host ceilings win — a manifest may ask for less, never more.
        fuel = min(fuel, MAX_FUEL)
        memory = min(memory, MAX_MEMORY_BYTES)

        return cls(
            name=name,
            version=version,
            description=str(raw.get("description", ""))[:500],
            entry=entry,
            fs_read=_path_list("fs_read"),
            fs_write=_path_list("fs_write"),
            env=list(env_vars),
            fuel=fuel,
            memory_bytes=memory,
            sha256=str(raw.get("sha256", "")),
        )

    def permission_summary(self) -> str:
        """Human-readable capability surface, shown at install time."""
        lines = [f"{self.name} v{self.version} — {self.description or 'no description'}"]
        if self.fs_read:
            lines.append(f"  read-only dirs:  {', '.join(self.fs_read)}")
        if self.fs_write:
            lines.append(f"  READ-WRITE dirs: {', '.join(self.fs_write)}")
        if not self.fs_read and not self.fs_write:
            lines.append("  filesystem:      none")
        lines.append(f"  env vars:        {', '.join(self.env) if self.env else 'none'}")
        lines.append("  network:         none (never available to plugins)")
        lines.append(f"  cpu budget:      {self.fuel:,} fuel")
        lines.append(f"  memory limit:    {self.memory_bytes // (1024*1024)} MiB")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "schema": MANIFEST_SCHEMA,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "entry": self.entry,
            "permissions": {
                "fs_read": self.fs_read,
                "fs_write": self.fs_write,
                "env": self.env,
            },
            "limits": {"fuel": self.fuel, "memory_bytes": self.memory_bytes},
            "sha256": self.sha256,
        }


# ═══════════════════════════════════════════════════════════
# Run result
# ═══════════════════════════════════════════════════════════

@dataclass
class PluginRunResult:
    name: str
    success: bool
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    fuel_used: int = 0
    duration_ms: float = 0.0
    trap: str = ""            # "fuel_exhausted", "trap", ""


# ═══════════════════════════════════════════════════════════
# Runtime
# ═══════════════════════════════════════════════════════════

class PluginRuntime:
    """Installs, verifies, lists, and runs WASM plugins.

    Layout on disk:
        <root>/<name>/plugin.wasm
        <root>/<name>/plugin.json     (normalized manifest + pinned sha256)
    """

    def __init__(self, root: Path | None = None, audit=None):
        self.root = root or PLUGIN_DIR
        self._audit = audit

    # ── audit (hash-chained, shared with MCP/remote) ───────

    @property
    def audit(self):
        if self._audit is None:
            from core.mcp_server import MCPAuditLog
            self._audit = MCPAuditLog(
                Path.home() / ".neuroshell" / "plugin_audit.jsonl")
        return self._audit

    def _record(self, event: dict) -> None:
        try:
            self.audit.record(event)
        except Exception:
            pass

    # ── install / uninstall / list ─────────────────────────

    def install(self, wasm_path: Path, manifest_path: Path,
                approved: bool = False) -> PluginManifest:
        """Validate, pin, and copy a plugin into the store.

        `approved=False` raises with the permission summary so the caller
        can show it and re-invoke with approved=True — informed consent
        is mandatory, there is no silent install path.
        """
        if not wasmtime_available():
            raise PluginError(
                "wasmtime is not installed — run: pip install wasmtime")

        wasm_path = Path(wasm_path)
        manifest_path = Path(manifest_path)
        if not wasm_path.is_file():
            raise PluginError(f"wasm module not found: {wasm_path}")
        if wasm_path.stat().st_size > MAX_WASM_SIZE:
            raise PluginError("wasm module exceeds 64 MiB limit")
        if not manifest_path.is_file():
            raise PluginError(f"manifest not found: {manifest_path}")

        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise PluginError(f"manifest is not valid JSON: {exc}") from exc
        manifest = PluginManifest.parse(raw)

        wasm_bytes = wasm_path.read_bytes()
        if not (wasm_bytes[:4] == b"\x00asm" or
                wasm_bytes[:8].lstrip().startswith(b"(module")):
            raise PluginError("file is neither a wasm binary nor a wat module")

        # Validate the module actually compiles before accepting it.
        try:
            from wasmtime import Engine, Module
            Module(Engine(), wasm_bytes)
        except Exception as exc:
            raise PluginError(f"module failed validation: {exc}") from exc

        if not approved:
            raise PluginError(
                "installation requires explicit approval of this "
                "permission surface:\n" + manifest.permission_summary())

        manifest.sha256 = hashlib.sha256(wasm_bytes).hexdigest()

        dest = self.root / manifest.name
        dest.mkdir(parents=True, exist_ok=True)
        # tmp-write + rename: a crashed install never leaves a runnable
        # half-plugin behind (run() requires both files + matching hash).
        tmp_wasm = dest / ".plugin.wasm.tmp"
        tmp_wasm.write_bytes(wasm_bytes)
        tmp_wasm.replace(dest / "plugin.wasm")
        tmp_json = dest / ".plugin.json.tmp"
        tmp_json.write_text(json.dumps(manifest.to_dict(), indent=2),
                            encoding="utf-8")
        tmp_json.replace(dest / "plugin.json")

        self._record({"event": "plugin_installed", "name": manifest.name,
                      "version": manifest.version, "sha256": manifest.sha256,
                      "fs_read": manifest.fs_read, "fs_write": manifest.fs_write})
        return manifest

    def uninstall(self, name: str) -> bool:
        if not _NAME_RE.match(name):
            raise PluginError(f"invalid plugin name {name!r}")
        dest = self.root / name
        if not dest.is_dir():
            return False
        shutil.rmtree(dest)
        self._record({"event": "plugin_uninstalled", "name": name})
        return True

    def list_plugins(self) -> list[PluginManifest]:
        out: list[PluginManifest] = []
        if not self.root.is_dir():
            return out
        for d in sorted(self.root.iterdir()):
            mf = d / "plugin.json"
            if not d.is_dir() or not mf.is_file():
                continue
            try:
                out.append(PluginManifest.parse(
                    json.loads(mf.read_text(encoding="utf-8"))))
            except (PluginError, ValueError):
                continue  # corrupt entries are invisible, never runnable
        return out

    def get_manifest(self, name: str) -> PluginManifest:
        if not _NAME_RE.match(name):
            raise PluginError(f"invalid plugin name {name!r}")
        mf = self.root / name / "plugin.json"
        if not mf.is_file():
            raise PluginError(f"plugin '{name}' is not installed")
        return PluginManifest.parse(json.loads(mf.read_text(encoding="utf-8")))

    # ── run ────────────────────────────────────────────────

    def run(self, name: str, argv: list[str] | None = None,
            stdin_data: str = "") -> PluginRunResult:
        """Execute an installed plugin inside the WASI sandbox."""
        start = time.time()
        result = PluginRunResult(name=name, success=False)

        if not wasmtime_available():
            result.error = "wasmtime is not installed — run: pip install wasmtime"
            return result

        try:
            manifest = self.get_manifest(name)
        except PluginError as exc:
            result.error = str(exc)
            return result

        wasm_file = self.root / name / "plugin.wasm"
        if not wasm_file.is_file():
            result.error = f"plugin '{name}' has no module file"
            return result

        wasm_bytes = wasm_file.read_bytes()
        actual = hashlib.sha256(wasm_bytes).hexdigest()
        if not manifest.sha256 or actual != manifest.sha256:
            result.error = (
                "module hash mismatch — plugin.wasm changed since install "
                f"(expected {manifest.sha256[:16]}…, got {actual[:16]}…). "
                "Reinstall to re-approve.")
            self._record({"event": "plugin_hash_mismatch", "name": name,
                          "expected": manifest.sha256, "actual": actual})
            return result

        from wasmtime import Config, Engine, Linker, Module, Store, WasiConfig

        cfg = Config()
        cfg.consume_fuel = True
        engine = Engine(cfg)
        try:
            module = Module(engine, wasm_bytes)
        except Exception as exc:
            result.error = f"module failed to compile: {exc}"
            return result

        store = Store(engine)
        store.set_fuel(manifest.fuel)
        store.set_limits(memory_size=manifest.memory_bytes)

        # WASI capability wiring — nothing is inherited by default.
        wasi = WasiConfig()
        wasi.argv = [name] + [str(a) for a in (argv or [])]

        allowed_env = [(k, os.environ.get(k, "")) for k in manifest.env
                       if k in os.environ]
        if allowed_env:
            wasi.env = allowed_env

        tmpdir = tempfile.mkdtemp(prefix="nsplugin_")
        stdout_path = Path(tmpdir) / "stdout"
        stderr_path = Path(tmpdir) / "stderr"
        stdin_path = Path(tmpdir) / "stdin"
        stdin_path.write_text(stdin_data or "", encoding="utf-8")
        wasi.stdout_file = str(stdout_path)
        wasi.stderr_file = str(stderr_path)
        wasi.stdin_file = str(stdin_path)

        # Preopens: the ONLY filesystem a plugin can see. Guest paths
        # mirror the manifest strings; host paths are resolved and must
        # exist — a missing grant is an error, not a silent hole.
        try:
            for spec_path, mutable in (
                    [(p, False) for p in manifest.fs_read] +
                    [(p, True) for p in manifest.fs_write]):
                host = Path(spec_path).expanduser().resolve()
                if not host.is_dir():
                    raise PluginError(
                        f"granted path does not exist or is not a directory: "
                        f"{spec_path}")
                wasi.preopen_dir(str(host), spec_path, fs_mutable=mutable)
        except PluginError as exc:
            result.error = str(exc)
            shutil.rmtree(tmpdir, ignore_errors=True)
            return result

        store.set_wasi(wasi)
        linker = Linker(engine)
        linker.define_wasi()

        try:
            instance = linker.instantiate(store, module)
            exports = instance.exports(store)
            entry = exports.get(manifest.entry)
            if entry is None:
                result.error = (f"module does not export "
                                f"'{manifest.entry}'")
                return result
            entry(store)
            result.success = True
        except Exception as exc:
            msg = str(exc)
            if "fuel" in msg.lower():
                result.trap = "fuel_exhausted"
                result.error = (
                    f"plugin exceeded its CPU budget "
                    f"({manifest.fuel:,} fuel) and was stopped")
            else:
                result.trap = "trap"
                result.error = f"plugin trapped: {msg.splitlines()[0][:200]}"
        finally:
            try:
                remaining = store.get_fuel()
                result.fuel_used = max(0, manifest.fuel - remaining)
            except Exception:
                result.fuel_used = manifest.fuel if result.trap == "fuel_exhausted" else 0
            result.duration_ms = (time.time() - start) * 1000.0
            try:
                result.stdout = stdout_path.read_text(
                    encoding="utf-8", errors="replace")[:MAX_OUTPUT_BYTES]
                result.stderr = stderr_path.read_text(
                    encoding="utf-8", errors="replace")[:MAX_OUTPUT_BYTES]
            except OSError:
                pass
            shutil.rmtree(tmpdir, ignore_errors=True)

        self._record({"event": "plugin_run", "name": name,
                      "success": result.success, "trap": result.trap,
                      "fuel_used": result.fuel_used,
                      "duration_ms": round(result.duration_ms, 1)})
        return result


# ═══════════════════════════════════════════════════════════
# CLI — `neuroshell-plugin install|list|info|run|uninstall`
# ═══════════════════════════════════════════════════════════

def cli_main(argv: list[str] | None = None) -> int:
    import argparse
    import sys as _sys

    parser = argparse.ArgumentParser(
        prog="neuroshell-plugin",
        description="NeuroShell WASM plugin manager — capability-scoped "
                    "WASI sandbox (no ambient filesystem, no network).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser("install", help="Install a plugin")
    p_install.add_argument("wasm", help="Path to plugin.wasm (or .wat)")
    p_install.add_argument("manifest", help="Path to plugin.json")
    p_install.add_argument("--yes", "-y", action="store_true",
                           help="Approve the permission surface")

    sub.add_parser("list", help="List installed plugins")

    p_info = sub.add_parser("info", help="Show a plugin's permissions")
    p_info.add_argument("name")

    p_run = sub.add_parser("run", help="Run a plugin")
    p_run.add_argument("name")
    p_run.add_argument("args", nargs=argparse.REMAINDER,
                       help="Arguments passed to the plugin")
    p_run.add_argument("--stdin", default="",
                       help="String piped to the plugin's stdin")

    p_rm = sub.add_parser("uninstall", help="Remove a plugin")
    p_rm.add_argument("name")

    args = parser.parse_args(argv)
    rt = PluginRuntime()

    try:
        if args.cmd == "install":
            if not args.yes:
                # Dry parse to show the surface, then ask.
                try:
                    rt.install(Path(args.wasm), Path(args.manifest))
                except PluginError as exc:
                    print(str(exc), file=_sys.stderr)
                    print("\nRe-run with --yes to approve.", file=_sys.stderr)
                    return 3
            m = rt.install(Path(args.wasm), Path(args.manifest), approved=True)
            print(f"✔ installed {m.name} v{m.version} "
                  f"(sha256 {m.sha256[:16]}…)")
            return 0

        if args.cmd == "list":
            plugins = rt.list_plugins()
            if not plugins:
                print("no plugins installed")
                return 0
            for m in plugins:
                caps = []
                if m.fs_read:
                    caps.append(f"ro:{len(m.fs_read)}")
                if m.fs_write:
                    caps.append(f"rw:{len(m.fs_write)}")
                if m.env:
                    caps.append(f"env:{len(m.env)}")
                print(f"{m.name:<20} v{m.version:<10} "
                      f"[{', '.join(caps) if caps else 'no capabilities'}]  "
                      f"{m.description[:50]}")
            return 0

        if args.cmd == "info":
            print(rt.get_manifest(args.name).permission_summary())
            return 0

        if args.cmd == "run":
            plugin_args = args.args
            if plugin_args and plugin_args[0] == "--":
                plugin_args = plugin_args[1:]
            r = rt.run(args.name, argv=plugin_args, stdin_data=args.stdin)
            if r.stdout:
                _sys.stdout.write(r.stdout)
            if r.stderr:
                _sys.stderr.write(r.stderr)
            if not r.success:
                print(f"✘ {r.error}", file=_sys.stderr)
                return 1
            return 0

        if args.cmd == "uninstall":
            if rt.uninstall(args.name):
                print(f"✔ removed {args.name}")
                return 0
            print(f"plugin '{args.name}' is not installed", file=_sys.stderr)
            return 1
    except PluginError as exc:
        print(f"✘ {exc}", file=_sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
