#!/usr/bin/env python3
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Verify NeuroShell SLSA v1 provenance attestations (Phase 10 supply chain).

A provenance statement is only a claim until it is *verified*. This tool is
the consumer-side gate: it checks, in order,

1. **Signature** — the detached Ed25519 signature (or DSSE envelope) must
   verify against the pinned NeuroShell release public key over the *raw*
   statement bytes. Any post-signing edit breaks this.
2. **Statement shape** — in-toto Statement v1 envelope, SLSA provenance v1
   predicate, non-empty subjects with well-formed sha256 digests.
3. **Builder identity** — the statement's ``runDetails.builder.id`` must
   exactly match the expected builder (``--expect-builder``, repeatable).
   A statement signed by the right key but produced by a *different*
   (e.g. downgraded/unknown) builder fails.
4. **Subject digests** — when local artifacts are supplied
   (``--artifact NAME:PATH``), their recomputed SHA-256 must match the
   signed subject digest for that name. A tampered/rebuilt binary fails.
5. **Build type** — optional exact match on ``--expect-buildtype``.

Exit code 0 only when every requested check passes.

Example
-------
  python3 scripts/verify_provenance.py \\
      --pubkey update_signing.pub \\
      --statement provenance.intoto.json --sig provenance.intoto.json.sig \\
      --expect-builder https://github.com/abneeshsingh21/neuroshell/.github/workflows/release.yml@refs/heads/main \\
      --artifact NeuroShell-linux-x86_64.tar.gz:./NeuroShell-linux-x86_64.tar.gz
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://slsa.dev/provenance/v1"


class VerificationError(Exception):
    """One or more verification checks failed (message is user-facing)."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_pubkey(pubkey: str) -> Any:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    path = Path(pubkey)
    hex_key = path.read_text().strip() if path.exists() else pubkey
    return Ed25519PublicKey.from_public_bytes(bytes.fromhex(hex_key))


def verify_signature(pub: Any, statement_bytes: bytes, sig_hex: str) -> None:
    from cryptography.exceptions import InvalidSignature

    try:
        sig = bytes.fromhex(sig_hex.strip())
    except ValueError as e:
        raise VerificationError(f"signature file is not valid hex: {e}") from e
    try:
        pub.verify(sig, statement_bytes)
    except InvalidSignature as e:
        raise VerificationError(
            "signature does not verify — the statement was modified after "
            "signing, or was signed by a different key") from e


def verify_dsse_envelope(pub: Any, envelope: dict[str, Any]) -> bytes:
    """Verify a DSSE envelope; return the decoded payload bytes."""
    from cryptography.exceptions import InvalidSignature

    try:
        payload_type = envelope["payloadType"]
        payload = base64.b64decode(envelope["payload"])
        signatures = envelope.get("signatures", [])
        if not signatures:
            raise VerificationError("DSSE envelope contains no signatures")
    except (KeyError, ValueError) as e:
        raise VerificationError(f"malformed DSSE envelope: {e}") from e
    pae = b"DSSEv1 %d %b %d %b" % (len(payload_type), payload_type.encode(),
                                   len(payload), payload)

    verified = False
    for s_entry in signatures:
        try:
            sig_bytes = base64.b64decode(s_entry["sig"])
            pub.verify(sig_bytes, pae)
            verified = True
            break
        except (InvalidSignature, KeyError, ValueError):
            continue

    if not verified:
        raise VerificationError(
            "DSSE signature does not verify over the PAE-encoded payload")
    return payload


def validate_statement_shape(doc: Any) -> None:
    problems: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            problems.append(msg)

    check(isinstance(doc, dict), "statement is not a JSON object")
    if not isinstance(doc, dict):
        raise VerificationError("statement is not a JSON object")
    check(doc.get("_type") == STATEMENT_TYPE,
          f"_type must be {STATEMENT_TYPE!r}, got {doc.get('_type')!r}")
    check(doc.get("predicateType") == PREDICATE_TYPE,
          f"predicateType must be {PREDICATE_TYPE!r}, got {doc.get('predicateType')!r}")
    subjects = doc.get("subject")
    check(isinstance(subjects, list) and bool(subjects), "subject list is empty")
    if isinstance(subjects, list):
        for s in subjects:
            name = s.get("name") if isinstance(s, dict) else None
            digest = (s.get("digest") or {}).get("sha256") if isinstance(s, dict) else None
            check(bool(name), f"subject without name: {s!r}")
            check(isinstance(digest, str) and len(digest) == 64
                  and all(c in "0123456789abcdef" for c in digest),
                  f"subject {name!r}: digest.sha256 must be 64 lowercase hex chars")
    predicate = doc.get("predicate")
    check(isinstance(predicate, dict), "predicate missing")
    if isinstance(predicate, dict):
        bd = predicate.get("buildDefinition")
        check(isinstance(bd, dict), "predicate.buildDefinition missing")
        if isinstance(bd, dict):
            check(bool(bd.get("buildType")), "buildDefinition.buildType missing")
            check(isinstance(bd.get("externalParameters"), dict),
                  "buildDefinition.externalParameters must be an object")
        rd = predicate.get("runDetails")
        check(isinstance(rd, dict), "predicate.runDetails missing")
        if isinstance(rd, dict):
            builder = rd.get("builder")
            check(isinstance(builder, dict) and bool(builder.get("id")),
                  "runDetails.builder.id missing")
    if problems:
        raise VerificationError("statement shape invalid: " + "; ".join(problems))


def verify(
    *,
    pubkey: str,
    statement: Path,
    sig: Path | None,
    dsse: Path | None,
    expect_builders: list[str],
    expect_buildtype: str | None,
    artifacts: list[tuple[str, Path]],
) -> dict[str, Any]:
    """Run all checks; raise VerificationError on the first failure category.
    Returns the parsed statement on success."""
    pub = _load_pubkey(pubkey)

    if dsse is not None:
        envelope = json.loads(dsse.read_text(encoding="utf-8"))
        statement_bytes = verify_dsse_envelope(pub, envelope)
        doc = json.loads(statement_bytes)
    else:
        statement_bytes = statement.read_bytes()
        doc = json.loads(statement_bytes)
        if sig is None:
            raise VerificationError("--sig (or --dsse) is required")
        verify_signature(pub, statement_bytes, sig.read_text(encoding="utf-8"))

    validate_statement_shape(doc)

    builder_id = doc["predicate"]["runDetails"]["builder"]["id"]
    if expect_builders and builder_id not in expect_builders:
        raise VerificationError(
            f"builder mismatch: statement says {builder_id!r}, "
            f"expected one of {expect_builders!r} (downgraded or unknown builder)")

    if expect_buildtype is not None:
        actual = doc["predicate"]["buildDefinition"]["buildType"]
        if actual != expect_buildtype:
            raise VerificationError(
                f"buildType mismatch: statement says {actual!r}, "
                f"expected {expect_buildtype!r}")

    if artifacts:
        by_name = {s["name"]: s["digest"]["sha256"] for s in doc["subject"]}
        for name, path in artifacts:
            if name not in by_name:
                raise VerificationError(
                    f"artifact {name!r} is not a subject of this statement "
                    f"(subjects: {sorted(by_name)})")
            actual = _file_sha256(path)
            if actual != by_name[name]:
                raise VerificationError(
                    f"subject digest mismatch for {name!r}: statement pins "
                    f"{by_name[name]}, local file hashes {actual} — the artifact "
                    f"was modified or rebuilt")

    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="verify_provenance.py",
        description="Verify SLSA v1 provenance: signature, shape, builder "
                    "identity, and (optionally) local artifact digests.")
    sub = ap.add_subparsers(dest="cmd")

    v = sub.add_parser("verify", help="verify a signed provenance statement")
    v.add_argument("--pubkey", required=True,
                   help="path to .pub file or 64-char hex key")
    v.add_argument("--statement", default=None,
                   help="path to raw provenance statement file (required if not using --dsse)")
    v.add_argument("--sig", default=None, help="detached hex signature file")
    v.add_argument("--dsse", default=None,
                   help="DSSE envelope file (alternative to --statement/--sig; "
                        "payload is verified via PAE)")
    v.add_argument("--expect-builder", action="append", default=[], metavar="ID",
                   help="required builder id (repeatable: any-of)")
    v.add_argument("--expect-buildtype", default=None)
    v.add_argument("--artifact", action="append", default=[], metavar="NAME:PATH",
                   help="local artifact to check against the signed subject digest")
    v.set_defaults(which="verify")

    args, rest = ap.parse_known_args(argv)
    if getattr(args, "which", None) != "verify" and not rest:
        # bare form without the 'verify' subcommand
        args = ap.parse_args(["verify", *(argv or [])])

    if not args.dsse and not args.statement:
        print("error: either --statement (with --sig) or --dsse is required",
              file=sys.stderr)
        return 2

    artifacts: list[tuple[str, Path]] = []
    for spec in args.artifact:
        name, sep, path = spec.partition(":")
        if not sep or not name or not path:
            print(f"error: bad --artifact spec {spec!r} (expected NAME:PATH)",
                  file=sys.stderr)
            return 2
        artifacts.append((name, Path(path)))

    try:
        doc = verify(
            pubkey=args.pubkey,
            statement=Path(args.statement) if args.statement else Path(),
            sig=Path(args.sig) if args.sig else None,
            dsse=Path(args.dsse) if args.dsse else None,
            expect_builders=list(args.expect_builder),
            expect_buildtype=args.expect_buildtype,
            artifacts=artifacts,
        )
    except VerificationError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    subjects = ", ".join(s["name"] for s in doc["subject"])
    builder = doc["predicate"]["runDetails"]["builder"]["id"]
    print(f"OK: provenance verified — {len(doc['subject'])} subject(s) [{subjects}]")
    print(f"    builder: {builder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
