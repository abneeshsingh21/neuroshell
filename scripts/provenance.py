#!/usr/bin/env python3
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""NeuroShell SLSA v1 provenance attestation (Phase 10 — Distribution & Supply Chain).

Builds in-toto / SLSA **v1.0** provenance statements for release artifacts and
signs them with the same offline Ed25519 key used for update manifests
(Phase 1, ``scripts/sign_release.py``) — the provenance is itself signed
content, so consumers can prove *who built it, from what source, and which
bytes came out* before trusting a binary.

Statement layout (SLSA provenance v1)::

    {
      "_type": "https://in-toto.io/Statement/v1",
      "subject": [{"name": "...", "digest": {"sha256": "..."}}],
      "predicateType": "https://slsa.dev/provenance/v1",
      "predicate": {
        "buildDefinition": {
          "buildType": "...",
          "externalParameters": {...},     # user-supplied inputs
          "internalParameters": {...},     # build system recorded state
          "resolvedDependencies": [{"uri": "git+...", "digest": {"gitCommit": "..."}}]
        },
        "runDetails": {
          "builder": {"id": "..."},        # exact builder identity (verifiable)
          "metadata": {"invocationId": "...", "startedOn": "...", "finishedOn": "..."}
        }
      }
    }

Two signature formats are produced:

* **detached** — hex Ed25519 signature over the *raw* statement bytes
  (``provenance.intoto.json`` + ``provenance.intoto.json.sig``), consistent
  with the Phase 1 manifest signing convention;
* **DSSE envelope** (optional, ``--dsse``) — the
  ``https://github.com/secure-systems-lab/dsse`` canonicalized envelope
  (PAE over ``application/vnd.in-toto+json``), the format native SLSA
  attestations (``gh attestation verify``) use.

Determinism: identical inputs produce identical statements apart from the
explicitly-supplied run metadata (invocation id / timestamps), which the
caller controls — CI passes the real GitHub run id; local runs may omit them.

Example
-------
  python3 scripts/provenance.py generate \\
      --subject NeuroShell-linux-x86_64.tar.gz:dist/NeuroShell-linux-x86_64.tar.gz \\
      --builder-id https://github.com/abneeshsingh21/neuroshell/.github/workflows/release.yml@refs/heads/main \\
      --source-uri git+https://github.com/abneeshsingh21/neuroshell \\
      --commit "$GITHUB_SHA" --out provenance.intoto.json
  python3 scripts/provenance.py sign --key /secure/keys/update_signing.key \\
      --statement provenance.intoto.json --out provenance.intoto.json.sig
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# Make sign_release importable both as a script sibling and as a module.
try:
    import sign_release  # type: ignore[import-not-found]  # noqa: S404
except ImportError:  # pragma: no cover - direct `python3 scripts/provenance.py` use
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import sign_release  # type: ignore[import-not-found]  # noqa: S404

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://slsa.dev/provenance/v1"
DEFAULT_BUILD_TYPE = "https://github.com/abneeshsingh21/neuroshell/buildtypes/cmake-native-v1"
DSSE_PAYLOAD_TYPE = "application/vnd.in-toto+json"


class ProvenanceError(Exception):
    """Fatal provenance error (bad input, malformed statement)."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Statement construction
# ─────────────────────────────────────────────────────────────────────────────

def build_statement(
    subjects: list[dict[str, str]],
    builder_id: str,
    source_uri: str,
    commit: str,
    *,
    build_type: str = DEFAULT_BUILD_TYPE,
    external_parameters: dict[str, Any] | None = None,
    internal_parameters: dict[str, Any] | None = None,
    invocation_id: str | None = None,
    started_on: str | None = None,
    finished_on: str | None = None,
) -> dict[str, Any]:
    """Assemble a SLSA v1 provenance statement.

    ``subjects`` is a list of ``{"name": ..., "sha256": ...}`` dicts.
    ``commit`` may be empty (local build), in which case the resolved
    dependency entry is omitted — the statement then describes a build whose
    source must be authenticated by other means (it stays valid, just weaker).
    """
    if not subjects:
        raise ProvenanceError("at least one --subject is required")
    for s in subjects:
        if not s.get("name"):
            raise ProvenanceError("subject without a name")
        digest = s.get("sha256", "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ProvenanceError(f"subject {s.get('name')!r}: sha256 must be 64 hex chars")
    if not builder_id:
        raise ProvenanceError("--builder-id is required (SLSA builder identity)")

    external: dict[str, Any] = {"source": f"{source_uri}@{commit}" if commit else source_uri}
    if external_parameters:
        external.update(external_parameters)
    internal: dict[str, Any] = internal_parameters or {}

    resolved: list[dict[str, Any]] = []
    if commit:
        resolved.append({
            "uri": source_uri,
            "digest": {"gitCommit": commit},
        })

    metadata: dict[str, Any] = {}
    if invocation_id:
        metadata["invocationId"] = invocation_id
    if started_on:
        metadata["startedOn"] = started_on
    if finished_on:
        metadata["finishedOn"] = finished_on

    return {
        "_type": STATEMENT_TYPE,
        "subject": [
            {"name": s["name"], "digest": {"sha256": s["sha256"]}}
            for s in sorted(subjects, key=lambda s: s["name"])
        ],
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "buildDefinition": {
                "buildType": build_type,
                "externalParameters": external,
                "internalParameters": internal,
                "resolvedDependencies": resolved,
            },
            "runDetails": {
                "builder": {"id": builder_id},
                "metadata": metadata,
            },
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Signing (reuses the Phase 1 Ed25519 key handling)
# ─────────────────────────────────────────────────────────────────────────────

def sign_statement(key_path: Path, statement_path: Path) -> tuple[str, str]:
    """Sign the RAW statement bytes; return (hex_signature, public_key_hex)."""
    key = sign_release._read_private(key_path)  # noqa: SLF001 — same tool family
    statement_bytes = statement_path.read_bytes()
    signature = key.sign(statement_bytes)
    public = sign_release._pub_hex(key)  # noqa: SLF001
    return signature.hex(), public


# ─────────────────────────────────────────────────────────────────────────────
# DSSE envelope (secure-systems-lab/dsse PAE)
# ─────────────────────────────────────────────────────────────────────────────

def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE Pre-Authentication Encoding."""
    return b"DSSEv1 %d %b %d %b" % (len(payload_type), payload_type.encode(),
                                    len(payload), payload)


def build_dsse_envelope(payload_type: str, payload: bytes,
                        signature: bytes, key_id: str) -> dict[str, Any]:
    return {
        "payloadType": payload_type,
        "payload": base64.b64encode(payload).decode(),
        "signatures": [{"keyid": key_id, "sig": base64.b64encode(signature).decode()}],
    }


def key_id_for_public_key(public_key_hex: str) -> str:
    """DSSE key id: first 16 hex chars of the SHA-256 of the raw public key."""
    return hashlib.sha256(bytes.fromhex(public_key_hex)).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_subject(spec: str) -> dict[str, str]:
    name, sep, path = spec.partition(":")
    if not sep or not name or not path:
        raise ProvenanceError(f"bad --subject spec {spec!r} (expected NAME:PATH)")
    p = Path(path)
    if not p.is_file():
        raise ProvenanceError(f"subject file not found: {path}")
    return {"name": name, "sha256": _file_sha256(p)}


def cmd_generate(args: argparse.Namespace) -> int:
    subjects = [_parse_subject(s) for s in args.subject]
    params: dict[str, Any] = {}
    for kv in args.param:
        key, sep, value = kv.partition("=")
        if not sep:
            raise ProvenanceError(f"bad --param {kv!r} (expected key=value)")
        params[key] = value
    internal: dict[str, Any] = {}
    for kv in args.internal_param:
        key, sep, value = kv.partition("=")
        if not sep:
            raise ProvenanceError(f"bad --internal-param {kv!r} (expected key=value)")
        internal[key] = value
    statement = build_statement(
        subjects, args.builder_id, args.source_uri, args.commit,
        build_type=args.build_type, external_parameters=params,
        internal_parameters=internal, invocation_id=args.invocation_id,
        started_on=args.started_on, finished_on=args.finished_on,
    )
    out = Path(args.out)
    out.write_text(json.dumps(statement, indent=2, sort_keys=False) + "\n",
                   encoding="utf-8")
    print(f"wrote {out} — SLSA v1 provenance for {len(subjects)} subject(s), "
          f"builder {args.builder_id}")
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    statement_path = Path(args.statement)
    key = sign_release._read_private(Path(args.key))  # noqa: SLF001
    statement_bytes = statement_path.read_bytes()
    signature = key.sign(statement_bytes)
    Path(args.out).write_text(signature.hex() + "\n", encoding="utf-8")
    print(f"signed {args.statement} -> {args.out}")
    public = sign_release._pub_hex(key)  # noqa: SLF001
    print(f"public key: {public}")
    if args.dsse:
        # The DSSE signature is over the PAE-encoded payload (not the raw
        # bytes) — a separate, intentionally non-interchangeable signature.
        pae_signature = key.sign(pae(DSSE_PAYLOAD_TYPE, statement_bytes))
        envelope = build_dsse_envelope(
            DSSE_PAYLOAD_TYPE, statement_bytes,
            pae_signature, key_id_for_public_key(public))
        Path(args.dsse).write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        print(f"DSSE envelope -> {args.dsse} (keyid {envelope['signatures'][0]['keyid']})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="provenance.py",
        description="Generate and Ed25519-sign SLSA v1 provenance statements "
                    "for NeuroShell release artifacts.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="build a provenance statement")
    g.add_argument("--subject", action="append", required=True, metavar="NAME:PATH")
    g.add_argument("--builder-id", required=True)
    g.add_argument("--source-uri",
                   default="git+https://github.com/abneeshsingh21/neuroshell")
    g.add_argument("--commit", default="")
    g.add_argument("--build-type", default=DEFAULT_BUILD_TYPE)
    g.add_argument("--param", action="append", default=[], metavar="KEY=VALUE",
                   help="extra external parameter (repeatable)")
    g.add_argument("--internal-param", action="append", default=[], metavar="KEY=VALUE",
                   help="extra internal parameter (repeatable)")
    g.add_argument("--invocation-id", default=None)
    g.add_argument("--started-on", default=None)
    g.add_argument("--finished-on", default=None)
    g.add_argument("--out", default="provenance.intoto.json")
    g.set_defaults(func=cmd_generate)

    s = sub.add_parser("sign", help="sign a statement with the release key")
    s.add_argument("--key", required=True)
    s.add_argument("--statement", required=True)
    s.add_argument("--out", default="provenance.intoto.json.sig")
    s.add_argument("--dsse", default=None, metavar="PATH",
                   help="also write a DSSE envelope to PATH")
    s.set_defaults(func=cmd_sign)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (ProvenanceError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
