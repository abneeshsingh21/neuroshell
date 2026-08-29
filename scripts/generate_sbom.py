#!/usr/bin/env python3
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# you may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""NeuroShell CycloneDX SBOM generator (Phase 10 — Distribution & Supply Chain).

Emits a CycloneDX 1.5 JSON SBOM covering, per release:

* the Python runtime dependencies declared in ``pyproject.toml``
  (base dependencies plus every optional extra group — ``llm``, ``plugins``,
  ``full``, ``nlp``, ``dev`` — each tagged with the group it came from);
* the vendored / runtime-``dlopen``'d native dependencies that never appear
  in any Python metadata (SQLite3 via ``cpp_engine/launcher/sqlite_dyn.hpp``,
  the Wasmtime runtime behind the optional ``plugins`` extra);
* the native C++20 launcher itself, as a first-class component with the
  SHA-256 of the built binary when ``--artifact`` is supplied.

Design constraints (enforced by tests):

* **Offline, stdlib-only.** No network resolution, no new hard dependencies.
  ``tomllib`` (Python >= 3.11) is preferred; the already-declared ``toml``
  package and a minimal built-in parser are fallbacks so Python 3.10 still
  works with stdlib alone.
* **Deterministic.** Identical inputs produce byte-identical output:
  components are emitted in sorted order, ``bom-ref`` values are derived
  from UUIDv5 (stable across runs and machines), the ``serialNumber`` is a
  UUIDv5 over the canonical component set, and the document contains no
  wall-clock timestamps unless ``--timestamp``/``SOURCE_DATE_EPOCH`` is given.
* **Self-validating.** Every document is checked against the CycloneDX 1.5
  schema *shape* (required fields, enums, purl syntax, hash algorithm/length,
  unique bom-refs, license object form) before it is written, and ``--check``
  re-validates an existing file. A document that fails validation is never
  written to disk.

Example
-------
  python3 scripts/generate_sbom.py \
      --artifact neuroshell-linux-x86_64:dist/NeuroShell-linux-x86_64.tar.gz \
      --out dist/sbom.cdx.json
  python3 scripts/generate_sbom.py --check dist/sbom.cdx.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

SPEC_VERSION = "1.5"
BOM_FORMAT = "CycloneDX"
TOOL_NAME = "generate_sbom.py"
TOOL_VERSION = "1.0.0"
# Deterministic namespace (RFC 4122 v5, SHA-1 based). Chosen once, never changed:
# changing it would silently renumber every bom-ref in subsequent SBOMs.
BOM_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/abneeshsingh21/neuroshell/sbom/v1")

# SPDX license ids for the dependencies NeuroShell declares. Anything not
# listed is emitted without a license object (never guessed).
KNOWN_LICENSES: dict[str, str] = {
    "rich": "MIT",
    "psutil": "BSD-3-Clause",
    "toml": "MIT",
    "tomli": "MIT",
    "cryptography": "Apache-2.0 OR BSD-3-Clause",
    "colorama": "BSD-3-Clause",
    "scikit-learn": "BSD-3-Clause",
    "nltk": "Apache-2.0",
    "pyperclip": "BSD-3-Clause",
    "ollama": "MIT",
    "groq": "Apache-2.0",
    "spacy": "MIT",
    "sentence-transformers": "Apache-2.0",
    "wasmtime": "Apache-2.0 WITH LLVM-exception",
    "pytest": "MIT",
    "pytest-cov": "MIT",
    "pytest-mock": "MIT",
    "mypy": "MIT",
    "ruff": "MIT",
    "pybind11": "BSD-3-Clause",
    "setuptools": "MIT",
    "wheel": "MIT",
    "numpy": "BSD-3-Clause",
}

SUPPORTED_HASH_ALGOS = {"SHA-256", "SHA-384", "SHA-512", "SHA-1", "MD5"}
_HASH_HEX_LEN = {"SHA-256": 64, "SHA-384": 96, "SHA-512": 128, "SHA-1": 40, "MD5": 32}
_PURL_RE = re.compile(
    r"^pkg:(?P<type>[a-z0-9._-]+)/(?P<name>[^@?\s]+)"
    r"(?:@(?P<version>[^?\s]+))?(?:\?(?P<qualifiers>.*))?$"
)
SPDX_IDS = {
    "MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "GPL-2.0-only",
    "GPL-3.0-only", "LGPL-2.1-only", "LGPL-3.0-only", "ISC", "MPL-2.0",
    "Python-2.0", "Zlib", "Blessing", "CC0-1.0", "Unlicense",
}


class SbomError(Exception):
    """Fatal generator error (bad input, unreadable file)."""


class SbomValidationError(SbomError):
    """The document does not conform to the CycloneDX 1.5 shape."""


# ─────────────────────────────────────────────────────────────────────────────
# pyproject.toml parsing (tomllib → toml → minimal built-in fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _load_toml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib  # Python >= 3.11

        return tomllib.loads(text)
    except ModuleNotFoundError:
        pass
    try:
        import toml  # already a NeuroShell runtime dependency (optional here)

        return toml.loads(text)
    except ModuleNotFoundError:
        return _minimal_toml(text)


def _minimal_toml(text: str) -> dict[str, Any]:
    """Parse the subset of TOML used by pyproject.toml (tables, string lists).

    Only exists so the SBOM generator stays functional on Python 3.10 with
    a pure stdlib environment; ``tomllib``/``toml`` are preferred whenever
    available. Handles multi-line arrays and comments inside values.
    """
    root: dict[str, Any] = {}
    current: dict[str, Any] = root
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = root
            for part in line[1:-1].split("."):
                current = current.setdefault(part.strip().strip('"'), {})
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value.startswith("[") and not _brackets_closed(value):
            buf = [value]
            while i < len(lines) and not _brackets_closed(" ".join(buf)):
                nxt = lines[i].strip()
                i += 1
                if nxt and not nxt.startswith("#"):
                    buf.append(nxt)
            value = " ".join(buf)
        current[key.strip().strip('"')] = _minimal_toml_value(value)
    return root


def _brackets_closed(s: str) -> bool:
    depth = 0
    in_str = False
    for ch in s:
        if ch == '"':
            in_str = not in_str
        elif not in_str:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
    return depth <= 0


def _minimal_toml_value(value: str) -> Any:
    if value.startswith("[") and value.endswith("]"):
        items: list[Any] = []
        buf: list[str] = []
        in_str = False
        for ch in value[1:-1]:
            if ch == '"':
                in_str = not in_str
                buf.append(ch)
            elif ch == "," and not in_str:
                if buf:
                    items.append(_minimal_toml_value("".join(buf).strip()))
                buf = []
            else:
                buf.append(ch)
        tail = "".join(buf).strip()
        if tail:
            items.append(_minimal_toml_value(tail))
        return items
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value in {"true", "false"}:
        return value == "true"
    try:
        return int(value)
    except ValueError:
        return value


# ─────────────────────────────────────────────────────────────────────────────
# PEP 508 requirement-string handling
# ─────────────────────────────────────────────────────────────────────────────

_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize_pypi_name(name: str) -> str:
    """PEP 503 / purl normalization: lowercase, ``_`` → ``-``."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirement(spec: str) -> dict[str, str | None]:
    """Split a PEP 508 requirement into name / pinned version / raw spec."""
    spec = spec.strip()
    base, _, _marker = spec.partition(";")  # drop environment markers
    match = _NAME_RE.match(base.strip())
    if not match:
        raise SbomError(f"cannot parse requirement name from {spec!r}")
    name = match.group(1)
    rest = base.strip()[len(name):].strip()
    version = None
    if rest.startswith("=="):
        version = rest[2:].strip().split(";")[0].strip()
    return {"name": name, "normalized": normalize_pypi_name(name),
            "pinned_version": version or None, "raw": spec}


def pypi_purl(req: dict[str, str | None]) -> str:
    version = req["pinned_version"]
    if version:
        return f"pkg:pypi/{req['normalized']}@{version}"
    return f"pkg:pypi/{req['normalized']}"


# ─────────────────────────────────────────────────────────────────────────────
# Component construction (all deterministic)
# ─────────────────────────────────────────────────────────────────────────────

def _bom_ref(purl: str | None, ctype: str, name: str, version: str | None) -> str:
    if purl:
        return purl
    seed = f"{ctype}:{name}:{version or 'noversion'}"
    return f"urn:uuid:{uuid.uuid5(BOM_NAMESPACE, seed)}"


def _spdx_license(entry: str) -> list[dict[str, Any]]:
    """Emit a valid CycloneDX licenses array.

    Composite expressions (``A OR B``, ``A WITH B``) must use the
    ``expression`` form; single known ids use the ``id`` form.
    """
    entry = entry.strip()
    if entry in SPDX_IDS:
        return [{"license": {"id": entry}}]
    if re.fullmatch(r"[A-Za-z0-9.+-]+( [A-Za-z0-9.+-]+)*", entry) and " " not in entry:
        return [{"license": {"name": entry}}]
    return [{"expression": entry}]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def component_python_dependency(req: dict[str, str | None], groups: list[str]) -> dict[str, Any]:
    purl = pypi_purl(req)
    base = "dependencies" in groups
    comp: dict[str, Any] = {
        "type": "library",
        "bom-ref": purl,
        "group": "pip",
        "name": req["normalized"],
        "purl": purl,
        "scope": "required" if base else "optional",
        "properties": [
            {"name": "neuroshell:requirement", "value": str(req["raw"])},
            {"name": "neuroshell:dependency-groups", "value": ",".join(sorted(groups))},
        ],
    }
    if req["pinned_version"]:
        comp["version"] = str(req["pinned_version"])
    license_expr = KNOWN_LICENSES.get(str(req["normalized"]))
    if license_expr:
        comp["licenses"] = _spdx_license(license_expr)
    return comp


def component_native_launcher(version: str, artifact_hashes: dict[str, str]) -> dict[str, Any]:
    purl = f"pkg:generic/neuroshell-launcher@{version}"
    comp: dict[str, Any] = {
        "type": "application",
        "bom-ref": purl,
        "group": "generic",
        "name": "neuroshell-launcher",
        "version": version,
        "purl": purl,
        "scope": "required",
        "licenses": [{"license": {"id": "Apache-2.0"}}],
        "description": "NeuroShell native C++20 terminal host (ConPTY/PTY, SHM IPC, "
                       "sandboxing, verified self-updater)",
        "properties": [
            {"name": "neuroshell:role", "value": "native-host"},
            {"name": "neuroshell:source", "value": "cpp_engine/launcher/"},
        ],
    }
    if artifact_hashes:
        comp["hashes"] = [{"alg": "SHA-256", "content": h}
                        for h in artifact_hashes.values()]
    return comp


def component_runtime_dependency(name: str, version: str | None, purl_base: str,
                                 license_id: str, description: str,
                                 resolved: str) -> dict[str, Any]:
    purl = f"{purl_base}@{version}" if version else purl_base
    comp: dict[str, Any] = {
        "type": "library",
        "bom-ref": purl,
        "group": "generic",
        "name": name,
        "purl": purl,
        "scope": "required",
        "licenses": [{"license": {"id": license_id}}],
        "description": description,
        "properties": [{"name": "neuroshell:resolution", "value": resolved}],
    }
    if version:
        comp["version"] = version
    return comp


# ─────────────────────────────────────────────────────────────────────────────
# Document assembly
# ─────────────────────────────────────────────────────────────────────────────

def collect_python_dependencies(pyproject: dict[str, Any],
                                extras: list[str] | None) -> list[tuple[dict[str, str | None], list[str]]]:
    """Return (requirement, groups) pairs — one entry per package, with the
    full list of pyproject groups that pull it in. Deterministic order."""
    project = pyproject.get("project", {})
    optional = project.get("optional-dependencies", {}) or {}
    wanted_groups = ["dependencies"] + [
        g for g in (extras if extras is not None else sorted(optional.keys()))
        if g in optional
    ]
    by_name: dict[str, dict[str, Any]] = {}
    for group in wanted_groups:
        specs = list(project.get("dependencies", [])) if group == "dependencies" \
            else list(optional.get(group, []))
        for spec in specs:
            req = parse_requirement(spec)
            entry = by_name.setdefault(str(req["normalized"]), {"req": req, "groups": []})
            if group not in entry["groups"]:
                entry["groups"].append(group)
    pairs = [(e["req"], e["groups"]) for e in by_name.values()]
    return sorted(pairs, key=lambda p: str(p[0]["normalized"]))


def build_document(version: str, pyproject_path: Path,
                   artifacts: list[tuple[str, Path]],
                   sqlite_version: str | None,
                   wasmtime_version: str | None,
                   timestamp: str | None,
                   extras: list[str] | None) -> dict[str, Any]:
    pyproject = _load_toml(pyproject_path)

    # artifact hashes keyed by "name" and matched to the launcher when the
    # name starts with "neuroshell"
    launcher_hashes: dict[str, str] = {}
    artifact_subjects: list[dict[str, Any]] = []
    for name, path in artifacts:
        digest = _file_sha256(path)
        if name.startswith("neuroshell"):
            launcher_hashes[name] = digest
        artifact_subjects.append({"name": name, "sha256": digest})

    components: list[dict[str, Any]] = [
        component_native_launcher(version, launcher_hashes),
        component_runtime_dependency(
            "sqlite3", sqlite_version, "pkg:generic/sqlite3", "Blessing",
            "SQLite database engine, runtime-loaded (dlopen/LoadLibrary) by "
            "cpp_engine/launcher/sqlite_dyn.hpp for the history engine",
            "runtime-dlopen"),
        component_runtime_dependency(
            "wasmtime", wasmtime_version, "pkg:generic/bytecodealliance/wasmtime",
            "Apache-2.0 WITH LLVM-exception",
            "Wasmtime WebAssembly runtime behind the optional Python "
            "'wasmtime' binding used by core/plugin_runtime.py",
            "runtime-binding"),
    ]
    components += [
        component_python_dependency(req, groups)
        for req, groups in collect_python_dependencies(pyproject, extras)
    ]
    components.sort(key=lambda c: (c["type"], c["name"], str(c.get("version", ""))))

    root_purl = f"pkg:pypi/neuroshell@{version}"
    root_ref = f"pkg:pypi/neuroshell@{version}"
    root: dict[str, Any] = {
        "type": "application",
        "bom-ref": root_ref,
        "group": "pip",
        "name": "neuroshell",
        "version": version,
        "purl": root_purl,
        "scope": "required",
        "licenses": [{"license": {"id": "Apache-2.0"}}],
        "description": "NeuroShell — AI-powered intelligent terminal "
                       "(Python daemon + native C++20 host)",
        "externalReferences": [
            {"type": "vcs",
             "url": "https://github.com/abneeshsingh21/neuroshell"},
            {"type": "website",
             "url": "https://github.com/abneeshsingh21/neuroshell#readme"},
            {"type": "bom",
             "url": "https://github.com/abneeshsingh21/neuroshell/blob/main/docs/SUPPLY_CHAIN.md"},
        ],
    }

    # Deterministic serial number: UUIDv5 over the canonical component set.
    ref_seed = "|".join(sorted(str(c["bom-ref"]) for c in components))
    serial = uuid.uuid5(BOM_NAMESPACE, f"neuroshell:{version}:{ref_seed}")

    metadata: dict[str, Any] = {
        "component": root,
        "tools": [{"vendor": "neuroshell", "name": TOOL_NAME, "version": TOOL_VERSION}],
        "authors": [{"name": "Abneesh Singh"}],
        "properties": [
            {"name": "neuroshell:pyproject", "value": str(pyproject_path)},
        ],
    }
    if timestamp:
        metadata["timestamp"] = timestamp
    if artifact_subjects:
        metadata["properties"].append({
            "name": "neuroshell:hashed-artifacts",
            "value": ",".join(
                f"{s['name']}={s['sha256']}" for s in sorted(artifact_subjects,
                                                             key=lambda s: str(s["name"]))),
        })

    doc = {
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": BOM_FORMAT,
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": metadata,
        "components": components,
        "dependencies": [
            {"ref": root_ref, "dependsOn": [str(c["bom-ref"]) for c in components]},
        ],
    }
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# Self-validation (CycloneDX 1.5 shape)
# ─────────────────────────────────────────────────────────────────────────────

def validate_document(doc: Any, where: str = "document") -> None:
    """Validate the CycloneDX 1.5 shape; raise SbomValidationError listing all
    problems (not just the first)."""
    problems: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            problems.append(f"{where}: {msg}")

    if not isinstance(doc, dict):
        raise SbomValidationError([f"{where}: not a JSON object"])
    check(doc.get("bomFormat") == "CycloneDX", "bomFormat must be 'CycloneDX'")
    check(doc.get("specVersion") == "1.5", "specVersion must be '1.5'")
    check(isinstance(doc.get("version"), int) and doc.get("version", 0) >= 1,
          "version must be an integer >= 1")
    serial = doc.get("serialNumber", "")
    check(isinstance(serial, str) and re.fullmatch(
        r"urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        serial) is not None, f"serialNumber is not a lowercase urn:uuid: {serial!r}")

    metadata = doc.get("metadata")
    check(isinstance(metadata, dict), "metadata must be an object")
    if isinstance(metadata, dict):
        root = metadata.get("component")
        check(isinstance(root, dict), "metadata.component must be an object")
        if isinstance(root, dict):
            check(root.get("type") in {"application", "library", "container", "framework",
                                       "operating-system", "device", "firmware", "file"},
                  f"metadata.component.type invalid: {root.get('type')!r}")
            check(bool(root.get("name")), "metadata.component.name missing")
            check(bool(root.get("version")), "metadata.component.version missing")
        ts = metadata.get("timestamp")
        if ts is not None:
            check(isinstance(ts, str) and re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z", str(ts)) is not None,
                f"metadata.timestamp not ISO-8601 UTC: {ts!r}")

    components = doc.get("components")
    check(isinstance(components, list) and bool(components),
          "components must be a non-empty array")
    refs: set[str] = set()
    if isinstance(components, list):
        for i, comp in enumerate(components, 1):
            check(isinstance(comp, dict), f"components[{i}] not an object")
            if not isinstance(comp, dict):
                continue
            name = comp.get("name")
            check(bool(name), f"components[{i}].name missing")
            check(comp.get("type") in {"application", "library", "framework", "container",
                                       "operating-system", "device", "firmware", "file"},
                  f"components[{i}] ({name}): invalid type {comp.get('type')!r}")
            ref = comp.get("bom-ref")
            check(isinstance(ref, str) and bool(ref), f"components[{i}] ({name}): bom-ref missing")
            if isinstance(ref, str):
                check(ref not in refs, f"components[{i}] ({name}): duplicate bom-ref {ref}")
                refs.add(ref)
            purl = comp.get("purl")
            if purl is not None:
                check(isinstance(purl, str) and _PURL_RE.match(purl) is not None,
                      f"components[{i}] ({name}): malformed purl {purl!r}")
            hashes = comp.get("hashes")
            if hashes is not None:
                check(isinstance(hashes, list), f"components[{i}] ({name}): hashes not a list")
                if isinstance(hashes, list):
                    for h in hashes:
                        alg = h.get("alg") if isinstance(h, dict) else None
                        content = h.get("content") if isinstance(h, dict) else None
                        check(alg in SUPPORTED_HASH_ALGOS,
                              f"components[{i}] ({name}): unsupported hash alg {alg!r}")
                        check(isinstance(content, str) and re.fullmatch(
                            r"[0-9a-fA-F]+", str(content)) is not None and
                            len(str(content)) == _HASH_HEX_LEN.get(str(alg), -1),
                            f"components[{i}] ({name}): hash content wrong length/hex for {alg}")
            licenses = comp.get("licenses")
            if licenses is not None:
                check(isinstance(licenses, list) and bool(licenses),
                      f"components[{i}] ({name}): licenses must be a non-empty array")
                if isinstance(licenses, list):
                    for lic in licenses:
                        ok = (
                            isinstance(lic, dict)
                            and (
                                ("expression" in lic and isinstance(lic["expression"], str))
                                or ("license" in lic and isinstance(lic["license"], dict)
                                    and bool(lic["license"].get("id")
                                            or lic["license"].get("name")))
                            )
                        )
                        check(ok, f"components[{i}] ({name}): malformed license entry {lic!r}")
            for prop in comp.get("properties", []) or []:
                ok = isinstance(prop, dict) and bool(prop.get("name")) and "value" in prop
                check(ok, f"components[{i}] ({name}): malformed property {prop!r}")

    dependencies = doc.get("dependencies")
    if dependencies is not None:
        check(isinstance(dependencies, list), "dependencies must be an array")
        if isinstance(dependencies, list):
            for dep in dependencies:
                ok = isinstance(dep, dict) and bool(dep.get("ref"))
                check(ok, f"malformed dependency entry {dep!r}")
                if ok and "dependsOn" in dep:
                    check(isinstance(dep["dependsOn"], list),
                          f"dependency {dep['ref']}: dependsOn must be an array")
                    for target in dep.get("dependsOn", []):
                        check(target in refs,
                              f"dependency {dep['ref']}: unknown dependsOn ref {target!r}")

    if problems:
        raise SbomValidationError(problems)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _default_version(repo_root: Path) -> str:
    text = (repo_root / "__version__.py").read_text(encoding="utf-8")
    match = re.search(r"__version__\s*=\s*\"([^\"]+)\"", text)
    if not match:
        raise SbomError("cannot read __version__.py")
    return match.group(1)


def _parse_artifact(spec: str) -> tuple[str, Path]:
    name, sep, path = spec.partition(":")
    if not sep or not name or not path:
        raise SbomError(f"bad --artifact spec {spec!r} (expected NAME:PATH)")
    return name, Path(path)


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(
        prog="generate_sbom.py",
        description="Generate a deterministic CycloneDX 1.5 SBOM for a NeuroShell release "
                    "(offline, stdlib-only, self-validating).")
    ap.add_argument("--version", default=None,
                    help="release version (default: read from __version__.py)")
    ap.add_argument("--pyproject", default=str(repo_root / "pyproject.toml"))
    ap.add_argument("--artifact", action="append", default=[], metavar="NAME:PATH",
                    help="release artifact to hash into the SBOM (repeatable); "
                         "names starting with 'neuroshell' attach to the launcher component")
    ap.add_argument("--sqlite-version", default=None,
                    help="SQLite version bundled/loaded at runtime (from the release "
                         "environment; omitted from the component when unknown)")
    ap.add_argument("--wasmtime-version", default=None,
                    help="wasmtime runtime version behind the Python binding")
    ap.add_argument("--extras", default=None,
                    help="comma-separated optional groups to include "
                         "(default: ALL groups in pyproject.toml)")
    ap.add_argument("--timestamp", default=None, metavar="ISO8601",
                    help="build timestamp (default: $SOURCE_DATE_EPOCH, else omitted "
                         "for reproducibility)")
    ap.add_argument("--out", default="sbom.cdx.json")
    ap.add_argument("--check", metavar="PATH", default=None,
                    help="validate an existing SBOM file instead of generating")
    ap.add_argument("--indent", type=int, default=2)
    args = ap.parse_args(argv)

    try:
        if args.check:
            doc = json.loads(Path(args.check).read_text(encoding="utf-8"))
            validate_document(doc, where=args.check)
            n = len(doc.get("components", []))
            print(f"OK: {args.check} is a valid CycloneDX {SPEC_VERSION} document "
                  f"({n} components)")
            return 0

        version = args.version or _default_version(repo_root)
        timestamp = args.timestamp
        if timestamp is None and os.environ.get("SOURCE_DATE_EPOCH"):
            import datetime as _dt

            timestamp = _dt.datetime.fromtimestamp(
                int(os.environ["SOURCE_DATE_EPOCH"]), tz=_dt.timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        extras = args.extras.split(",") if args.extras is not None else None

        doc = build_document(
            version=version,
            pyproject_path=Path(args.pyproject),
            artifacts=[_parse_artifact(s) for s in args.artifact],
            sqlite_version=args.sqlite_version,
            wasmtime_version=args.wasmtime_version,
            timestamp=timestamp,
            extras=extras,
        )
        validate_document(doc, where="generated document")

        payload = json.dumps(doc, indent=args.indent, sort_keys=True,
                             ensure_ascii=False) + "\n"
        out = Path(args.out)
        if out.parent and str(out.parent):
            out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        print(f"wrote {out} — CycloneDX {SPEC_VERSION}, "
              f"{len(doc['components'])} components, "
              f"serial {doc['serialNumber']}")
        return 0
    except SbomValidationError as e:
        print("FAIL: SBOM validation errors:", file=sys.stderr)
        for p in e.args[0] if isinstance(e.args[0], list) else [str(e)]:
            print(f"  - {p}", file=sys.stderr)
        return 1
    except (SbomError, OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
