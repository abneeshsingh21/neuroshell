#!/usr/bin/env python3
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
"""NeuroShell release-signing tool.

Produces the Ed25519-signed update manifest consumed by the native host's
verified self-updater (cpp_engine/launcher/update_verifier.hpp).

Subcommands
-----------
keygen    Generate a new Ed25519 keypair (run on an OFFLINE machine).
manifest  Build a manifest.json from release artifacts (computes SHA-256s).
sign      Sign a manifest, producing manifest.json.sig (hex detached sig).
verify    Verify a manifest + signature against a public key (sanity check
          that mirrors the client's core signature verification).

Security notes
--------------
* The private key file is created with mode 0600 and should live only on an
  offline signing machine or in a CI secret store (never in the repo).
* The signature covers the RAW manifest bytes. Do not reformat/pretty-print
  manifest.json after signing — the client verifies the exact bytes.
* The client additionally enforces: schema==1, anti-downgrade, expiry,
  platform match, https + GitHub host allowlist, artifact size bounds.

Example release flow
--------------------
  python3 scripts/sign_release.py manifest \
      --version 5.9.0 --expires-days 90 \
      --artifact linux-x86_64:dist/neuroshell:https://github.com/abneeshsingh21/neuroshell/releases/download/v5.9.0/neuroshell \
      --out manifest.json
  python3 scripts/sign_release.py sign --key /secure/keys/update_signing.key \
      --manifest manifest.json --out manifest.json.sig
  # upload manifest.json + manifest.json.sig + artifacts as release assets
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
except ImportError:  # pragma: no cover
    print("error: the 'cryptography' package is required: pip install cryptography",
          file=sys.stderr)
    sys.exit(2)

# Phase 10: sibling tooling (works both as a script and as an imported module).
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from verify_provenance import main as verify_provenance_main
except ImportError:  # pragma: no cover
    try:
        from scripts.verify_provenance import main as verify_provenance_main
    except ImportError:
        verify_provenance_main = None  # only needed for attest/verify-attestation

SCHEMA_VERSION = 1
VALID_PLATFORMS = {
    "linux-x86_64", "linux-arm64",
    "macos-x86_64", "macos-arm64",
    "windows-x86_64", "windows-arm64",
}
ALLOWED_URL_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}


def _write_private(path: Path, key: Ed25519PrivateKey) -> None:
    raw = key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, raw.hex().encode() + b"\n")
    finally:
        os.close(fd)


def _read_private(path: Path) -> Ed25519PrivateKey:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        print(f"warning: {path} is group/world accessible (mode {oct(mode)}); "
              "run: chmod 600 " + str(path), file=sys.stderr)
    raw = bytes.fromhex(path.read_text().strip())
    if len(raw) != 32:
        raise ValueError("private key file must contain 64 hex chars (32 bytes)")
    return Ed25519PrivateKey.from_private_bytes(raw)


def _pub_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def cmd_keygen(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    priv_path = out_dir / "update_signing.key"
    pub_path = out_dir / "update_signing.pub"
    if priv_path.exists():
        print(f"error: {priv_path} already exists — refusing to overwrite a signing key",
              file=sys.stderr)
        return 1
    key = Ed25519PrivateKey.generate()
    _write_private(priv_path, key)
    pub_hex = _pub_hex(key)
    pub_path.write_text(pub_hex + "\n")
    print(f"private key : {priv_path}  (mode 0600 — keep OFFLINE)")
    print(f"public key  : {pub_path}")
    print("\npin this key into release builds with:")
    print(f"  cmake -DNEUROSHELL_UPDATE_PUBKEY={pub_hex} ...")
    return 0


def _validate_url(url: str) -> None:
    if not url.startswith("https://"):
        raise ValueError(f"artifact URL must be https: {url}")
    rest = url[len("https://"):]
    host = rest.split("/", 1)[0].lower()
    if "@" in host or ":" in host:
        raise ValueError(f"artifact URL must not carry userinfo/port: {url}")
    if host not in ALLOWED_URL_HOSTS:
        raise ValueError(
            f"artifact host '{host}' is not in the client allowlist {sorted(ALLOWED_URL_HOSTS)}"
        )
    if "/" not in rest:
        raise ValueError(f"artifact URL must include a path: {url}")


def cmd_manifest(args: argparse.Namespace) -> int:
    artifacts = []
    for spec in args.artifact:
        # platform:local_path:url  (url contains ':' so split from the left, handle Windows drive letters)
        try:
            platform, rest = spec.split(":", 1)
            if ":https://" in rest:
                local_path, url = rest.split(":https://", 1)
                url = "https://" + url
            elif ":http://" in rest:
                local_path, url = rest.split(":http://", 1)
                url = "http://" + url
            else:
                local_path, url = rest.rsplit(":", 1)
        except ValueError:
            print(f"error: bad --artifact spec '{spec}' "
                  "(expected platform:path:url)", file=sys.stderr)
            return 1
        if platform not in VALID_PLATFORMS:
            print(f"error: unknown platform '{platform}' "
                  f"(valid: {sorted(VALID_PLATFORMS)})", file=sys.stderr)
            return 1
        _validate_url(url)
        p = Path(local_path)
        data = p.read_bytes()
        artifacts.append({
            "platform": platform,
            "name": p.name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
            "url": url,
        })

    now = int(time.time())
    manifest = {
        "schema": SCHEMA_VERSION,
        "version": args.version,
        "created_at": now,
        "expires_at": now + args.expires_days * 86400,
        "min_version": args.min_version,
        "artifacts": artifacts,
    }
    out = Path(args.out)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n")
    print(f"wrote {out} ({len(artifacts)} artifact(s), "
          f"expires in {args.expires_days} days)")
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    key = _read_private(Path(args.key))
    manifest_bytes = Path(args.manifest).read_bytes()
    # sanity: must be valid JSON with the expected schema before we bless it
    doc = json.loads(manifest_bytes)
    if doc.get("schema") != SCHEMA_VERSION:
        print(f"error: manifest schema must be {SCHEMA_VERSION}", file=sys.stderr)
        return 1
    sig = key.sign(manifest_bytes)
    Path(args.out).write_text(sig.hex() + "\n")
    print(f"signed {args.manifest} -> {args.out}")
    print(f"public key: {_pub_hex(key)}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    pub_hex = Path(args.pubkey).read_text().strip() if Path(args.pubkey).exists() \
        else args.pubkey
    pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
    manifest_bytes = Path(args.manifest).read_bytes()
    sig = bytes.fromhex(Path(args.sig).read_text().strip())
    try:
        pub.verify(sig, manifest_bytes)
    except InvalidSignature:
        print("FAIL: signature does not verify", file=sys.stderr)
        return 1
    doc = json.loads(manifest_bytes)
    now = int(time.time())
    problems = []
    if doc.get("schema") != SCHEMA_VERSION:
        problems.append(f"schema != {SCHEMA_VERSION}")
    if now > int(doc.get("expires_at", 0)):
        problems.append("manifest is expired")
    for art in doc.get("artifacts", []):
        try:
            _validate_url(art["url"])
        except (ValueError, KeyError) as e:
            problems.append(str(e))
    if problems:
        print("signature OK, but policy problems:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"OK: signature valid, schema {doc['schema']}, version {doc['version']}, "
          f"{len(doc.get('artifacts', []))} artifact(s)")
    return 0


def cmd_attest(args: argparse.Namespace) -> int:
    """Phase 10: generate + sign a SLSA v1 provenance statement in one step."""
    import provenance

    rc = provenance.main([
        "generate",
        *sum([["--subject", s] for s in args.subject], []),
        "--builder-id", args.builder_id,
        "--source-uri", args.source_uri,
        "--commit", args.commit,
        "--build-type", args.build_type,
        "--out", args.out,
    ])
    if rc != 0:
        return rc
    sig_out = args.sig_out or (args.out + ".sig")
    rc = provenance.main(["sign", "--key", args.key,
                          "--statement", args.out, "--out", sig_out])
    if rc != 0:
        return rc
    # Sanity gate mirroring the manifest flow: verify what we just produced.
    pub = provenance.sign_statement(Path(args.key), Path(args.out))[1]
    rc = verify_provenance_main([
        "verify", "--pubkey", pub, "--statement", args.out, "--sig", sig_out,
        "--expect-builder", args.builder_id,
    ])
    if rc != 0:
        print("error: freshly signed provenance failed self-verification "
              "(this is a bug — refusing to ship it)", file=sys.stderr)
        return 1
    return 0


def cmd_verify_attestation(args: argparse.Namespace) -> int:
    """Phase 10: consumer-side verification gate."""
    argv = ["verify", "--pubkey", args.pubkey,
            "--statement", args.statement, "--sig", args.sig]
    for builder in args.expect_builder:
        argv += ["--expect-builder", builder]
    for artifact in args.artifact:
        argv += ["--artifact", artifact]
    return verify_provenance_main(argv)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sign_release.py",
                                 description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    kg = sub.add_parser("keygen", help="generate a new Ed25519 signing keypair")
    kg.add_argument("--out-dir", required=True)
    kg.set_defaults(func=cmd_keygen)

    mf = sub.add_parser("manifest", help="build manifest.json from artifacts")
    mf.add_argument("--version", required=True)
    mf.add_argument("--min-version", default="0.0.0")
    mf.add_argument("--expires-days", type=int, default=90)
    mf.add_argument("--artifact", action="append", required=True,
                    metavar="PLATFORM:PATH:URL")
    mf.add_argument("--out", default="manifest.json")
    mf.set_defaults(func=cmd_manifest)

    sg = sub.add_parser("sign", help="sign a manifest")
    sg.add_argument("--key", required=True)
    sg.add_argument("--manifest", required=True)
    sg.add_argument("--out", default="manifest.json.sig")
    sg.set_defaults(func=cmd_sign)

    vf = sub.add_parser("verify", help="verify a manifest signature + policy")
    vf.add_argument("--pubkey", required=True,
                    help="path to .pub file or 64-char hex key")
    vf.add_argument("--manifest", required=True)
    vf.add_argument("--sig", required=True)
    vf.set_defaults(func=cmd_verify)

    # ── Phase 10: SLSA provenance, wired into the same signing flow ──────────
    at = sub.add_parser(
        "attest",
        help="generate + sign a SLSA v1 provenance statement for release "
             "artifacts (same Ed25519 key as manifests)")
    at.add_argument("--subject", action="append", required=True, metavar="NAME:PATH")
    at.add_argument("--builder-id", required=True)
    at.add_argument("--source-uri",
                    default="git+https://github.com/abneeshsingh21/neuroshell")
    at.add_argument("--commit", default="")
    at.add_argument("--build-type",
                    default="https://github.com/abneeshsingh21/neuroshell/buildtypes/cmake-native-v1")
    at.add_argument("--invocation-id", default=None)
    at.add_argument("--started-on", default=None)
    at.add_argument("--finished-on", default=None)
    at.add_argument("--key", required=True)
    at.add_argument("--out", default="provenance.intoto.json")
    at.add_argument("--sig-out", default=None)
    at.set_defaults(func=cmd_attest)

    va = sub.add_parser(
        "verify-attestation",
        help="verify a signed provenance statement (signature, shape, builder, "
             "optional local artifact digests)")
    va.add_argument("--pubkey", required=True)
    va.add_argument("--statement", required=True)
    va.add_argument("--sig", required=True)
    va.add_argument("--expect-builder", action="append", default=[], metavar="ID")
    va.add_argument("--artifact", action="append", default=[], metavar="NAME:PATH")
    va.set_defaults(func=cmd_verify_attestation)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
