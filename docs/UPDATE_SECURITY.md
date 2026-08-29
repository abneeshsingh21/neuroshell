# NeuroShell Signed Self-Update — Security Design & Operations Runbook

Status: **implemented in v5.9** (`cpp_engine/launcher/update_*.hpp`, `crypto/`, `scripts/sign_release.py`)

## 1. Why

The pre-5.9 self-updater executed `curl … | bash` (POSIX) or blind-replaced
the executable (Windows). Anyone who could influence the network path — a
hostile Wi-Fi AP, a compromised CDN edge, a DNS hijack — could achieve
arbitrary code execution on every machine that ran `/update`.

The v5.9 pipeline makes the network **fully untrusted**: a release is only
installed if it is provably signed by the offline NeuroShell release key,
strictly newer than the running build, unexpired, and byte-for-byte identical
to what was signed.

## 2. Threat model

| Adversary capability | Defense |
|---|---|
| MITM on any network hop, hostile CDN/mirror | Ed25519 signature over raw manifest bytes; artifact SHA-256 pinned inside the signed manifest |
| Replays an old signed release (downgrade to a vulnerable version) | Numeric-semver anti-downgrade (`version` must be **strictly** newer) + `expires_at` freshness window |
| Serves a manifest for the wrong platform / a hostile URL | Platform tag exact match; `https` only; exact-match host allowlist (`github.com`, `objects.githubusercontent.com`, `release-assets.githubusercontent.com`); no userinfo/port/whitespace tricks |
| Bit-flips the artifact in transit | Streaming SHA-256 of the download, constant-time compare against signed digest, exact size match |
| Signature malleability (S ⟶ S+L) | RFC 8032 canonical-S check: `S ≥ L` refused outright |
| Ships a build without a provisioned key | **Fail closed**: the placeholder (all-zero) key disables self-update entirely; all-zero is not a valid curve point, so no signature can ever verify against it even under logic bugs |
| Malformed / adversarial JSON (depth bombs, surrogates, dup keys) | Hardened strict parser (`json_mini.hpp`): 32-level depth cap, 256 KiB manifest cap, RFC 8259 grammar, last-wins duplicates, no exceptions |
| Interrupted install bricks the binary | Atomic same-directory rename dance with rollback (POSIX `rename`, Windows `MoveFileExW`); the previous binary is kept as `.old_<ts>` |

Out of scope (by design, documented): a compromise of the **offline signing
key** itself, or of the developer machine that pins the public key into the
build. Mitigations for those are procedural (Section 5).

## 3. Verification pipeline (client)

Order matters — every step fails closed:

```
0. key policy      pinned pubkey provisioned? placeholder ⇒ refuse everything
1. signature       Ed25519 over the RAW manifest bytes (no canonicalization step)
2. schema          strict JSON parse; schema == 1; required fields present & typed
3. anti-downgrade  manifest.version > running version (numeric semver)
                   running version >= manifest.min_version
4. freshness       now <= expires_at;  created_at <= now + 24h skew slack
5. artifact policy platform match, https + host allowlist, sane size, hex digest
6. payload         download → streaming SHA-256 == signed digest (constant time)
                   AND exact byte size match
7. install         chmod +x → atomic swap with rollback
```

The signature is checked **before** the JSON is trusted for anything, and it
covers the exact raw bytes — there is no re-serialization/canonicalization
step to exploit.

## 4. Manifest format (schema 1)

```json
{
  "schema": 1,
  "version": "5.9.0",
  "created_at": 1756400000,
  "expires_at": 1764176000,
  "min_version": "5.0.0",
  "artifacts": [
    {
      "platform": "linux-x86_64",
      "name": "neuroshell",
      "sha256": "…64 lowercase hex…",
      "size": 4823040,
      "url": "https://github.com/abneeshsingh21/neuroshell/releases/download/v5.9.0/neuroshell"
    }
  ]
}
```

Platform tags: `{linux,macos,windows}-{x86_64,arm64}`.
Release assets: `manifest.json` + `manifest.json.sig` (detached hex Ed25519
signature) uploaded alongside the binaries.

## 5. Key management runbook

### Provisioning (one-time)

1. On an **offline** machine (or an isolated CI secret scope):
   ```bash
   python3 scripts/sign_release.py keygen --out-dir /secure/keys
   # → update_signing.key (0600, PRIVATE — never leaves this machine)
   # → update_signing.pub (64 hex chars)
   ```
2. Pin the public key into release builds:
   ```bash
   cmake -DNEUROSHELL_UPDATE_PUBKEY=<contents of update_signing.pub> …
   ```
   (or set it as the default in `cpp_engine/launcher/update_public_key.hpp`
   before tagging).
3. Until this is done, every shipped binary refuses self-update with
   *"self-update disabled: no release signing key is provisioned in this
   build"* — that is intentional.

### Signing a release

```bash
python3 scripts/sign_release.py manifest \
    --version 5.9.0 --expires-days 90 --min-version 5.0.0 \
    --artifact linux-x86_64:dist/neuroshell:https://github.com/abneeshsingh21/neuroshell/releases/download/v5.9.0/neuroshell \
    --artifact windows-x86_64:dist/NeuroShell.exe:https://github.com/abneeshsingh21/neuroshell/releases/download/v5.9.0/NeuroShell.exe \
    --out manifest.json

python3 scripts/sign_release.py sign \
    --key /secure/keys/update_signing.key \
    --manifest manifest.json --out manifest.json.sig

python3 scripts/sign_release.py verify \
    --pubkey /secure/keys/update_signing.pub \
    --manifest manifest.json --sig manifest.json.sig   # sanity gate

# upload manifest.json, manifest.json.sig and all artifacts as release assets
```

**Never reformat `manifest.json` after signing** — the client verifies the
exact bytes.

A CI wiring example lives in `.github/proposed-workflows/release-signing.yml`
(kept outside `.github/workflows/` — see the note in that directory).

### Rotation / compromise

* Routine rotation: generate a new keypair, pin the new public key, ship it
  in release N via the *old* update channel, then start signing with the new
  key from release N+1. Keep `expires_days` short (≤90) so old manifests
  age out.
* Suspected compromise: pull all release assets immediately (expiry bounds
  the replay window to `expires_at`), rotate as above, and force
  `min_version` to the first clean release so compromised-era builds are
  directed to reinstall from source.

## 6. Implementation notes

* **Crypto is verify-only and embedded** (`crypto/sha2.hpp`,
  `crypto/ed25519.hpp`): no OpenSSL dependency, no signing capability in the
  shipped binary. The Ed25519 arithmetic is a port of the public-domain
  TweetNaCl construction with an added RFC 8032 canonical-S check.
* **Constants are derived, not typed**: SHA-2 round constants/IVs are
  computed at startup from square/cube roots of primes via exact integer
  arithmetic; Ed25519 curve constants (d, √-1, basepoint) are derived from
  their definitions in the field arithmetic itself. The single hardcoded
  value (group order L) is covered by cross-implementation vectors.
* **Cross-validated**: the native test suite verifies against RFC 8032
  vector 1 and vectors generated with Python `cryptography` (OpenSSL); the
  Python test suite (`tests/test_sign_release.py`) exercises the signer;
  and the two ends were proven interoperable end-to-end (Python-signed
  manifest accepted by the C++ verifier, tampered variants refused).
* **No shell anywhere**: downloads run through `safe_exec` argv execution
  (`curl --proto =https --tlsv1.2 --max-filesize …` / PowerShell
  `Invoke-WebRequest` with a typed `[uri]`), against URLs that already
  passed the allowlist policy.
