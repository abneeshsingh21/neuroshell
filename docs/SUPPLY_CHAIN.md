# NeuroShell Supply Chain — Threat Model, Verification & Release Runbook

Status: **implemented in v5.18** (Phase 10 of `docs/ENGINEERING_ROADMAP.md`;
tools: `scripts/generate_sbom.py`, `scripts/provenance.py`,
`scripts/verify_provenance.py`, `scripts/check_packaging_consistency.py`,
`.github/proposed-workflows/release.yml`)

Every NeuroShell release publishes **evidence**, not just binaries:

| Asset | Format | Tool that produces it |
|---|---|---|
| `checksums.txt` | `sha256sum` | release workflow |
| `sbom.cdx.json` (+ `.sig`) | CycloneDX 1.5 JSON | `scripts/generate_sbom.py` |
| `manifest.json` (+ `.sig`) | v5.9 update manifest | `scripts/sign_release.py` |
| `provenance.intoto.json` (+ `.sig`, `provenance.dsse.json`) | in-toto Statement / SLSA provenance **v1** | `scripts/provenance.py` |

All signatures are detached Ed25519 over the **raw bytes** of the signed
document, made by the same offline release key as the v5.9 update manifests
(see `docs/UPDATE_SECURITY.md`). The DSSE envelope is the SLSA-native
packaging of the same statement (PAE-encoded payload).

---

## 1. Threat model — what each layer defends against

No single control stops every attack; the layers overlap deliberately.

| Adversary capability | Defense | Where it breaks for the attacker |
|---|---|---|
| MITM / hostile CDN / mirror swaps bytes in transit | TLS + `checksums.txt` + SHA-256 pinned **inside** the signed manifest and provenance | A swapped artifact no longer matches any signed digest |
| Attacker replaces *both* artifact and its digest file | Ed25519 signatures (manifest, provenance, SBOM) by the offline key | They cannot forge a signature without the key, which never touches a build machine with network access |
| A compromised dependency is silently bundled | CycloneDX SBOM enumerates every Python dep (incl. `llm`/`plugins` extras), the dlopen'd natives (SQLite3, Wasmtime), and the C++ launcher, with hashes/PURLs/licenses | Consumers & scanners can diff releases and audit the full component set |
| Malicious artifact substituted after CI built it | SLSA v1 provenance: subject SHA-256 per artifact, builder identity, source repo + exact `gitCommit` | `verify_provenance.py` fails on any digest/builder mismatch |
| Release built from *modified* sources (not the tag) | `resolvedDependencies` pins the commit; `externalParameters.source` records `git+…@<sha>` | The statement is signed, so lying about provenance requires the key |
| Unknown/downgraded builder produces a validly-signed artifact | `--expect-builder` allowlist on verification | Right key, wrong builder → rejected |
| Version/digest drift across package managers (brew, winget, scoop, AUR, deb) | `scripts/check_packaging_consistency.py` gate + `REPLACE_AT_RELEASE` sentinel resolved at release time | A manifest that drifts or floats on `latest` fails CI |
| Replay of an old release | Anti-downgrade + expiry in the v5.9 manifest (see UPDATE_SECURITY §2) | Old signed releases refuse to install |
| `curl | bash` as the primary install path | Retired from the README front page; checksum-verified fallback only | Piping unverified network content to a shell is no longer the default |

What this does **not** defend against (explicit non-goals): a fully
compromised release key (mitigate: offline key storage, rotation procedure),
compromised GitHub runners before signing (the key is injected only into the
signing steps and shredded after), and malicious *source* that maintainer
review misses — code review and CI remain the controls there.

---

## 2. End-user verification walkthrough

Prerequisites: `python3`, `sha256sum` (or `shasum -a 256`), the `cryptography`
package, and the NeuroShell public key. **Pin the key out-of-band** — take it
from the repo variable `UPDATE_PUBLIC_KEY`, the release notes of a release you
already trust, or the `NEUROSHELL_UPDATE_PUBKEY` value baked into a launcher
binary you already trust:

```
export NS_PUB=<64-hex Ed25519 public key from a trusted source>
TAG=v5.18.0
BASE=https://github.com/abneeshsingh21/neuroshell/releases/download/$TAG
```

1. **Download** the artifact you want plus the evidence files
   (`checksums.txt`, `manifest.json{,.sig}`, `provenance.intoto.json{,.sig}`,
   `sbom.cdx.json{,.sig}`).

2. **Integrity** — every byte arrived intact:
   ```bash
   sha256sum -c checksums.txt --ignore-missing
   ```

3. **Update manifest** (what the launcher's self-updater enforces natively):
   ```bash
   python3 scripts/sign_release.py verify \
       --pubkey "$NS_PUB" --manifest manifest.json --sig manifest.json.sig
   ```

4. **Provenance** — this exact binary was built by the official builder from
   the tagged commit:
   ```bash
   python3 scripts/verify_provenance.py verify \
       --pubkey "$NS_PUB" \
       --statement provenance.intoto.json --sig provenance.intoto.json.sig \
       --expect-builder https://github.com/abneeshsingh21/neuroshell/.github/workflows/release.yml@refs/heads/main \
       --artifact NeuroShell-linux-x86_64.tar.gz:./NeuroShell-linux-x86_64.tar.gz
   ```
   (`--artifact` recomputes the local file's SHA-256 and compares it against
   the *signed* subject digest — fails on any tamper or rebuild.)

5. **SBOM** — inspect what you are about to run:
   ```bash
   python3 scripts/generate_sbom.py --check sbom.cdx.json
   jq '.components[] | {name, version, licenses}' sbom.cdx.json
   ```

6. Optionally verify the **DSSE envelope** (`provenance.dsse.json`) instead of
   the detached signature:
   ```bash
   python3 scripts/verify_provenance.py verify --pubkey "$NS_PUB" \
       --statement provenance.intoto.json --dsse provenance.dsse.json
   ```

Package managers do step 2 for you (brew/winget/scoop/AUR all pin SHA-256s),
and `pip` verifies PyPI's own signatures — steps 3–5 remain meaningful
whenever you run a standalone binary.

---

## 3. Release-engineer runbook

One-time setup

1. Generate the offline keypair on an air-gapped machine:
   `python3 scripts/sign_release.py keygen --out-dir keys/`.
2. Store the private key in the repo secret `UPDATE_SIGNING_KEY` and the
   public key in the variable `UPDATE_PUBLIC_KEY`; pin it into builds with
   `-DNEUROSHELL_UPDATE_PUBKEY=<hex>`.

Per release

1. **Bump versions** — `__version__.py`, `pyproject.toml`,
   `cpp_engine/launcher/version.hpp` (string **and** MAJOR/MINOR/PATCH
   macros), `Formula/neuroshell.rb`, `packaging/*` manifests, Debian
   `changelog`, and the top `CHANGELOG.md` entry. The gate fails otherwise:
   ```bash
   python3 scripts/check_packaging_consistency.py check
   ```
2. **Tag** `vX.Y.Z` and push. The release workflow (proposed file:
   `.github/proposed-workflows/release.yml`) then:
   builds per-platform launchers → emits `checksums.txt` → generates the
   deterministic CycloneDX SBOM → builds + signs the update manifest →
   builds + signs SLSA v1 provenance for **all** artifacts (+DSSE) → renders
   the packaging manifests with real digests → **runs every verification gate
   locally** (SBOM check, manifest verify, provenance verify with builder +
   digest checks, sentinel-absence check) → publishes via first-party `gh`
   (no third-party release action) → shreds the signing key.
3. **Submit the package-manager updates** from `dist/packaging/` in the
   workflow artifacts: winget PR to `microsoft/winget-pkgs`, scoop bucket PR,
   AUR `updpkgsums && mksrcinfo`, `brew bump-formula-pr`, and upload the
   `.deb`s. All digests are already pinned — never use `latest` URLs.
4. **Rotate** the signing key at any hint of exposure; clients fail closed on
   unverifiable manifests (a placeholder-pinned build disables self-update
   entirely — see `docs/UPDATE_SECURITY.md`).

Incident: if any gate fails after a tag exists, delete the tag/release before
users see partial evidence; never upload artifacts whose provenance does not
verify.

---

## 4. Related documents

* `docs/UPDATE_SECURITY.md` — the v5.9 signed self-update design (key
  handling, anti-downgrade, client verification).
* `docs/ENGINEERING_ROADMAP.md` — Phase 10 scope.
* `scripts/README` headers — every tool documents its own threat assumptions.
