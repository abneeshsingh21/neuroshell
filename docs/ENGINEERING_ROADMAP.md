# NeuroShell Engineering Roadmap — v5.8 → v6.0

**Status:** Living document · **Owner:** Core maintainers · **Last updated:** 2026-08-29

This roadmap converts the v5.8.0 production-hardening audit into a sequenced
delivery plan. Every phase lists design, deliverables, acceptance criteria,
and risks. Phases are ordered by (security impact × user impact ÷ effort).

---

## Guiding principles

1. **Fail closed.** Security features must refuse operation when their
   preconditions are missing (unprovisioned keys, unverifiable payloads) —
   never silently degrade.
2. **AI is a fallback, not a dependency.** Every intelligence feature keeps an
   offline path.
3. **No shell string concatenation, ever.** All subprocess use goes through
   `safe_exec.hpp` (argv-vector) with allowlist validation.
4. **Cross-language contracts are ABI-locked.** Any C++↔Python shared format
   gets `static_assert`s on one side, struct-offset tests on the other, and a
   live interop test in CI (precedent: SHM ring ABI v2).
5. **Correctness is proven, not assumed.** Crypto and parsers ship with
   generated test vectors cross-validated against an independent
   implementation.

---

## Phase 1 — Cryptographically Signed Self-Updates  ✅ **SHIPPED in v5.9.0**

**Problem.** `/update` executes `curl | bash` (POSIX) or replaces the binary
with an unverified download (Windows). Anyone who can MITM the connection or
compromise the release CDN gains code execution on every install. This is the
single largest remaining hole after v5.8.0.

**Design (TUF-inspired, minimal-trust):**

```
Release pipeline                          Client (/update)
────────────────                          ────────────────
1. Build artifacts                        1. Download manifest.json + .sig
2. sign_release.py:                       2. Verify Ed25519 signature over the
   • sha256 every artifact                   RAW manifest bytes with the pinned
   • emit manifest.json                      release public key   → fail closed
     {schema, version, created_at,        3. Policy checks:
      expires_at, min_version,               • schema known
      artifacts[{platform,name,              • version > current (numeric semver
      sha256,size,url}]}                       — anti-downgrade / rollback)
   • Ed25519-sign manifest bytes             • now < expires_at (anti-freeze /
   • emit manifest.json.sig (base64)           stale-mirror attack)
3. Upload artifacts + manifest + sig         • artifact exists for this platform
   to the GitHub release                     • url host ∈ {github.com,
                                               objects.githubusercontent.com},
                                               https only
                                          4. Download artifact → temp file
                                          5. SHA-256(file) == manifest hash
                                          6. Atomic install:
                                             POSIX: write .new → chmod 755 →
                                               rename(exe→.old) → rename(.new→exe)
                                             Win32: MoveFileEx(exe→.old) →
                                               move .new into place
```

**Key management.**
- Verify-only Ed25519 implementation embedded in the host (no OpenSSL/libsodium
  dependency — the host stays a single static binary). Algorithm follows the
  public-domain TweetNaCl construction; correctness is proven by test vectors
  generated with the independent Python `cryptography` (OpenSSL) implementation.
- Release public key pinned at build time (`update_public_key.hpp`, overridable
  via `-DNEUROSHELL_UPDATE_PUBKEY=<hex64>`). The private key never enters the
  repository; `scripts/sign_release.py generate-key` provisions it locally /
  in CI secrets.
- **Fail closed:** a build with the unprovisioned placeholder key refuses
  signed updates and says exactly why, instead of falling back to the insecure
  path.
- Signature malleability rejected (S < L check); low-order/invalid points
  rejected by decompression failure.

**Deliverables**
- `cpp_engine/launcher/crypto/sha256.hpp`, `sha512.hpp` — constants generated
  programmatically (integer nth-root, no hand-typed tables), validated against
  `hashlib` vectors.
- `cpp_engine/launcher/crypto/ed25519.hpp` — verify-only, constant-time field
  ops, validated against `cryptography`-generated vectors incl. RFC 8032.
- `cpp_engine/launcher/update_verifier.hpp` — manifest parsing + policy engine
  (signature, semver anti-rollback, expiry, platform match, URL allowlist).
- `cpp_engine/launcher/update_public_key.hpp` — pinned key + provisioning doc.
- Rewritten `HandleSlashUpdate` — verified download + atomic swap, no shell.
- `scripts/sign_release.py` — keygen / sign / verify CLI (Python cryptography).
- `docs/UPDATE_SECURITY.md` — threat model, provisioning runbook, rotation.
- Native tests: hash vectors, signature vectors (valid/tampered/malleable/
  wrong-key), full manifest policy matrix. Python tests for the signer.
- Proposed release-workflow signing step (`.github/proposed-workflows/`).

**Acceptance criteria**
- Tampering with 1 bit of manifest, signature, or artifact ⇒ update refused.
- Replaying an old (signed) manifest ⇒ refused (downgrade + expiry).
- Unprovisioned key ⇒ `/update` fails closed with actionable message.
- All crypto vectors pass on Linux/macOS/Windows, GCC/Clang/MSVC.

**Risks / mitigations**
- *Hand-rolled crypto risk* → verify-only scope (no key generation / signing /
  secret handling in C++), well-studied construction, cross-implementation
  vectors, constant-time comparisons.
- *Key loss* → documented rotation via `successor` field + re-pin release.

---

## Phase 2 — Streaming LLM Tokens over SHM  ✅ **SHIPPED in v5.10.0**

**Problem.** `ai_pipe`/translate block up to 15 s, then dump the full answer.
**Design.** Second SHM ring (daemon→host, ABI v3 adds a `channel` byte);
daemon writes `{"stream_id", "seq", "delta"}` frames per token; host renders
incrementally with a spinner→stream transition; `Esc` cancels via a control
frame on the existing host→daemon ring. Backpressure = ring-full ⇒ daemon
coalesces deltas.
**Acceptance.** First token visible < 300 ms after provider first-byte; cancel
tears down the provider request; interop test streams 10k tokens both ways.

## Phase 3 — SQLite + FTS5 History Engine  ✅ **SHIPPED in v5.11.0**

Replace `history.txt` with `~/.neuroshell/history.db` (WAL): schema
`(id, cmd, cwd, exit_code, duration_ms, ts, session)` + FTS5 index; ranking =
`0.6·frecency + 0.3·cwd-affinity + 0.1·prefix-match` feeding ghost text and
Ctrl+R; transparent one-time migration; 100k-row search < 5 ms.

## Phase 4 — Blast-Radius Preview (dry-run engine) — ✅ SHIPPED in v5.12.0

Extend the AST extractor: for destructive verbs (`rm`, `del`, `rmdir`, `git
clean`, `docker system prune`, `kubectl delete`, …) resolve globs/paths and
render `→ 1,204 files · 340 MB · outside git: 3` in the confirmation card,
with a hard cap walk (50k inodes) and timeout (500 ms) so preview never hangs.

## Phase 5 — Universal Undo (CoW snapshots) — ✅ SHIPPED in v5.13.0

Pre-exec snapshot of write-targets via reflink (`FICLONE`/APFS `clonefile`,
copy fallback ≤ 512 MB) into `~/.neuroshell/undo/<txn>`; `undo` restores the
last transaction; GC by age+size budget. Works outside git repos.

## Phase 6 — MCP Server Mode (strategic) — ✅ SHIPPED in v5.14.0

Expose the daemon as an MCP tool provider (`neuroshell.execute`,
`neuroshell.translate`, `neuroshell.explain`) so Claude Desktop / Cursor /
agent frameworks execute **through** the 4-layer safety shield, policy RBAC,
DLP and audit chain instead of raw shell. Reuses the JSON-RPC dispatcher; adds
stdio transport + tool schemas + per-client policy scopes.

## Phase 7 — Remote Execution with Local Safety — ✅ SHIPPED in v5.15.0

`nsh user@host` — commands run over SSH (ControlMaster), but translation,
safety checks and DLP masking execute locally before bytes leave the machine.

## Phase 8 — Kernel-Level Sandboxing for AI-Generated Commands — ✅ SHIPPED in v5.16.0

Landlock + seccomp-bpf (Linux) / AppContainer (Windows) profile limiting
AI-proposed commands to the project directory + read-only system paths unless
the user escalates. Policy engine gains `sandbox: strict|project|off`.

## Phase 9 — WASM Plugin Runtime — ✅ SHIPPED in v5.17.0

Wasmtime-embedded plugin host with capability-scoped WASI (no ambient fs/net);
plugins declare permissions in a manifest surfaced at install time.

## Phase 10 — Distribution & Supply Chain — ✅ **SHIPPED in v5.18.0**

SBOM (CycloneDX) per release, SLSA provenance attestation, Authenticode +
notarization, winget/scoop/AUR/apt packaging; retire `curl | bash` from README
front-page (kept only as documented fallback).

Shipped in v5.18.0: `scripts/generate_sbom.py`, `scripts/provenance.py` +
`scripts/verify_provenance.py` (wired into `sign_release.py attest`),
`packaging/` (winget/scoop/AUR/deb) with the
`scripts/check_packaging_consistency.py` gate, the proposed
`.github/proposed-workflows/release.yml` pipeline, README verified-install
rewrite, and `docs/SUPPLY_CHAIN.md`. Authenticode/notarization for the
Windows .msi remains open (tracked below for v5.19+).

### Continuous (all phases)
- Fuzzing: libFuzzer harnesses for DLP regex input, manifest/JSON parsing,
  phrase matching — wired to the nightly-soak workflow.
- Windows UTF-8 correctness: replace all `std::wstring(s.begin(), s.end())`
  widening with `MultiByteToWideChar` (tracked as tech debt from v5.8 audit).
- Replace `ExtractStringField` sites with the hardened mini-JSON reader
  introduced in Phase 1 as call sites are touched.

---

## Sequencing & dependency graph

```
P1 Signed Updates ──────────► P10 Distribution (needs signing)
P2 SHM Streaming ─┬─────────► P6 MCP Server (streams tool output)
P3 History Engine ┘
P4 Blast Radius ──► P5 Undo (shares write-target resolution)
P8 Sandboxing ────► P6 (sandbox becomes an MCP-exposed guarantee)
```
