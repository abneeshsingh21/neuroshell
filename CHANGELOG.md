# Changelog

All notable changes to NeuroShell are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [5.10.0 → 5.16.0] — Engineering roadmap Phases 2–8

### Added
- Streaming LLM tokens over SHM with cancellation and backpressure (Phase 2).
- SQLite/WAL + FTS5 command history and transparent migration (Phase 3).
- Bounded blast-radius previews for destructive commands (Phase 4).
- Universal undo with CoW/reflink snapshots and copy fallback (Phase 5).
- MCP server mode exposing the safety-shielded execution tools (Phase 6).
- Remote SSH execution with local translation, safety checks, and DLP masking (Phase 7).
- Landlock/seccomp-bpf and AppContainer sandbox profiles for AI commands (Phase 8).

This roadmap release train also carries forward the v5.8 production hardening
and v5.9 cryptographically signed, fail-closed self-update work.

---

## [5.9.0] — 2026-08-29

### Security (Critical) — Cryptographically Signed Self-Updates

The `/update` command no longer trusts the network. The previous updater
executed `curl … | bash` (POSIX) or blind-replaced the executable (Windows),
giving any on-path attacker remote code execution. It is replaced by a fully
verified pipeline (design + runbook: `docs/UPDATE_SECURITY.md`):

- **Ed25519-signed release manifests** — the client verifies a detached
  signature over the *raw* manifest bytes with a build-time pinned public key
  (`-DNEUROSHELL_UPDATE_PUBKEY=<hex>`). Unprovisioned builds **fail closed**:
  the placeholder key disables self-update entirely.
- **Anti-downgrade + freshness** — manifests must offer a strictly newer
  version (numeric semver), satisfy `min_version`, and be within their
  `created_at`/`expires_at` window, bounding replay of old signed releases.
- **Artifact binding** — each artifact's SHA-256 and exact byte size are
  pinned inside the signed manifest; downloads are hashed in a stream and
  compared in constant time. URLs must be `https` on an exact-match GitHub
  host allowlist (no userinfo/port/suffix tricks).
- **Atomic install with rollback** — verified binaries are staged next to
  the destination and swapped via atomic rename (`rename`/`MoveFileExW`),
  keeping the previous binary as a rollback copy; a failed swap rolls back.
- **Embedded verify-only crypto** (`cpp_engine/launcher/crypto/`) — SHA-256/
  SHA-512 with round constants *derived* from square/cube roots of primes at
  startup (no typo-able tables), and a TweetNaCl-construction Ed25519
  verifier with the RFC 8032 canonical-S malleability check (S ≥ L refused).
  No OpenSSL dependency; no signing capability in the shipped binary.
- **Hardened JSON reader** (`json_mini.hpp`) — strict RFC 8259 parser for
  untrusted input: 32-level depth cap, size caps, full `\uXXXX`/surrogate
  handling, deterministic duplicate-key semantics, no exceptions.

### Added
- `scripts/sign_release.py` — offline release-signing CLI
  (`keygen`/`manifest`/`sign`/`verify`), private keys created 0600.
- `.github/proposed-workflows/release-signing.yml` — CI wiring for signed
  releases (manifest generation, signing, pinned-key sanity gate).
- `docs/UPDATE_SECURITY.md` — threat model, verification pipeline,
  key-provisioning and rotation runbook.
- `docs/ENGINEERING_ROADMAP.md` — 10-phase production-engineering roadmap.

### Testing
- Native suite grown 307 → 393 checks: SHA-2 vectors (NIST + Python
  `hashlib` cross-vectors, streaming/block-boundary sweeps), Ed25519
  (RFC 8032 vector 1, OpenSSL cross-vectors, 1-bit tamper of R/S/message,
  wrong key, malleable S+L, invalid points), strict-JSON negative matrix
  (depth bombs, lone surrogates, trailing garbage), and a full
  update-manifest policy matrix (tamper/replay/downgrade/expiry/platform/
  URL-allowlist/fail-closed).
- Python suite grown 509 → 526: `tests/test_sign_release.py` covers the
  signing tool end to end, including tamper and expired-manifest paths.
- Cross-language proof: a manifest signed by the Python tool verifies in
  the C++ client, and every tampered variant is refused.

---

## [5.8.0] — 2026-08-29

### Security (Critical)
- **Command-injection elimination (C++ host)** — All `system()`/`popen()` string-concatenation call sites that mixed in user-controlled input (repo slugs, GitHub URLs, vault key names, browser URLs) replaced with the new `safe_exec.hpp` argv-vector executor (no shell involved) plus strict allowlist validators (`IsValidRepoSlug`, `IsValidGitHubUser`, `IsValidHost`, `IsValidVaultKey`). Payloads like `owner/repo; rm -rf /` and `$(whoami)` are now rejected or passed as inert literals.
- **`os_vault.hpp` rewritten** — Secrets were previously interpolated into shell command lines (single-quote escape → arbitrary code execution) and the Windows DPAPI path encrypted a secret then *discarded the ciphertext* (`RetrieveSecret` always returned `""`). Secrets now travel via stdin/argv-vector, and the Windows vault persists DPAPI ciphertext to `%USERPROFILE%\.neuroshell\vault\<key>.bin` with real decryption on read.
- **API keys no longer written in plaintext** — `SaveConfig` now stores keys in the OS credential vault (Keychain / DPAPI / Secret Service) and writes only an `os-vault:` reference into `config.toml`; the plaintext fallback (headless Linux) is chmod `0600` with a visible warning.
- **DLP masking moved ahead of the viewport** — Secrets were displayed raw on screen and only masked in the recorded copy. The process runner now applies the DLP filter line-by-line *before* any byte reaches stdout.
- **IPC DoS guards** — Unix-socket receive path now enforces the 10 MB payload cap (previously unbounded memory growth); C++ IPC client caps responses at 16 MB.
- **Real local security audit** — `audit` previously printed a hardcoded "0 Exposed Secrets / 98 / 100" without scanning a single byte. It now regex-scans source/config files for AWS/GitHub/Groq/OpenAI/Slack keys and private-key blocks, reports findings with file paths, and computes an honest score.
- **Hardened builds** — CMake now applies `-fstack-protector-strong`, `_FORTIFY_SOURCE=2`, full RELRO + `BIND_NOW`, PIE, `noexecstack` (GCC/Clang) and `/guard:cf /sdl /DYNAMICBASE /NXCOMPAT /HIGHENTROPYVA` (MSVC), with optional ASan/UBSan config and LTO.
- **WebSocket auth hardening**: All WebSocket endpoints (`/ws/terminal`, `/ws/telemetry`, `/ws/sysmon`) now pass through a constant-time `secrets.compare_digest` auth gate; unauthenticated frames demoted from logs.
- **Container security**: Docker image now runs as a dedicated non-root `neuroshell` user; added `.dockerignore` to exclude secrets and build artifacts from image layers.

### Fixed (Critical runtime bugs & engine hardening)
- **Startup crash**: `threading` was only imported inside `__init__`, so `startup()` raised `NameError` on the critical path — the LLM warmup thread, pattern learner, and predictor training silently never started. `threading` is now a module-level import.
- **Shutdown never stopped background services**: `NeuroShell.shutdown()` was defined twice; the second definition silently shadowed the first, so the IPC server and AutoDream daemon were never stopped on exit. Consolidated into a single idempotent `shutdown()` that stops background services before printing the session summary.
- **`deploy promote` crash**: a function-local `from pathlib import Path` shadowed the module-level import, causing `UnboundLocalError` before the re-import line. All redundant local `Path` imports removed.
- **`voice` / `api start` crash**: `VoiceCommandEngine` and `NeuroShellAPI` were referenced from handlers but only imported inside the background loader's scope, raising `NameError`. Handlers now import them explicitly.
- **Server safety shield broken**: `server.py` read `safety_res.risk`, an attribute that does not exist on `SafetyResult` (it is `risk_level`) — every command sent through `/ws/terminal` died with `[CRITICAL ERROR]` *after* passing translation. Now uses the correct attribute; blocked commands are actually blocked again.
- **AutoDream crash-in-cleanup**: the `finally` block referenced an out-of-scope exception variable and invoked a possibly-`None` UI callback.
- **SHM ring buffer ABI mismatch** — The C++ `SHMHeader` (pack(1)+alignas trick) compiled to cursors at offsets 16/24 while the Python bridge read offsets 64/72 with data at 128: the two sides could never interoperate. Layout is now explicit (`static_assert`-locked ABI v2: cursors at 64/72, seq at 80, data at 128) and validated end-to-end with a live C++↔Python interop test. Python ring copies are now wrap-aware bulk slices instead of byte-by-byte loops, and both sides validate magic/version/capacity on attach.
- **Interactive TUI passthrough was input-dead** — `vim`/`htop`/`ssh` spawned on a PTY and streamed output, but keystrokes were never forwarded. Added `PumpStdinLoop()` (POSIX `poll` + Win32 console-event drain) wired into the runner; PTY rows now use real window height instead of hardcoded 30.
- **`exit` left the terminal broken** — `exit(0)` skipped all destructors, leaving POSIX terminals in raw mode with bracketed paste stuck on. Replaced with a clean shutdown flag; `Run()` drains, stops supervised tasks, and lets RAII restore the terminal.
- **Ctrl+C never interrupted running commands** — raw mode disables `ISIG` and children were placed in their own process group with no relay. A SIGINT handler now forwards to the active foreground child's process group; `SIGPIPE` ignored.
- **Update checker compared versions lexicographically** — `"10.0.0" < "5.7.0"` meant future major releases would never be detected (same bug in the VS Code extension). Added `version.hpp` with numeric `CompareSemver`/`IsNewerRelease`; extension now parses numerically and reads its own version from `package.json`.
- **IPC client truncated large responses** — a single 16 KB `recv`/`ReadFile` silently cut off big agent plans and `ai_pipe` results; now accumulates to the newline frame delimiter with deadline-based timeout and full-write send loops.
- **Invalid JSON escaping in `EscapeJSON`** — control characters were emitted as malformed `\u1`-style sequences (invalid JSON, corrupted every subsequent number formatting via sticky `std::hex`); now fixed-width `\u00XX`.
- **IPC server global-lock serialization** — every JSON-RPC method (including `ping`) queued behind a single mutex, so one 8-second LLM call froze all clients. Only genuinely stateful methods (`slash`) are serialized now; `params` type is validated (`-32602`).
- **Daemon spawner zombie leak** — the forked Python daemon was never reaped; now proper double-fork daemonization with immediate `waitpid` of the intermediate.
- **`SelectMenu` frame corruption** — `std::string(n, '─')` with a multi-byte glyph is a multi-character-constant overflow producing garbage bytes; added `RepeatGlyph()`.
- **UTF-8 input rejected** — the POSIX key reader dropped all bytes ≥ 0x7F, making accented/CJK/emoji input impossible; continuation bytes are now accepted.
- **`/clip copy` corrupted quoting** — `shlex.split` + re-join stripped quotes ("echo 'Hello World'" → "echo Hello World"); the verbatim argument text is now preserved.
- **Smart-open folder resolution**: well-known profile folders (Downloads, Documents…) failed to resolve when the directory didn't exist on the executing machine. Well-known mappings now resolve deterministically.
- **LLM retry loop**: late-binding lambda captured the loop's `messages` variable (ruff B023) — bound explicitly to prevent stale-payload retries.
- **Version drift** — Single sources of truth now: `version.hpp` (native) and `__version__.py` (Python, read by `setup.py`/build scripts).

### Added
- `cpp_engine/launcher/safe_exec.hpp` — injection-proof subprocess primitives (argv exec, stdout capture, stdin plumbing, strict POSIX/Win32 quoting, input validators).
- `cpp_engine/launcher/version.hpp` — native version constants + numeric semver comparison.
- `cpp_engine/tests/native_tests.cpp` — first native C++ test suite (307 checks) wired into CTest.
- `tests/test_production_hardening.py` — 18 regression tests for Python lifecycle, safety, and quoting.
- `tests/test_ipc_hardening.py` + expanded `tests/test_shm_ipc.py` — concurrency, DoS-guard, ABI-layout, wraparound and UTF-8 regression coverage.
- `docs/PRODUCTION_AUDIT_2026-08.md` — full audit report with methodology & findings.
- CI: new `native` job building the hardened host on Linux/macOS/Windows, running CTest, plus an ASan/UBSan pass on Linux.

---

## [5.0.0] — 2026-04-25

### Added
- **C++ Hybrid Engine** — Native `engine.cpp` with pybind11 bindings for `FastParser`, `FuzzyMatcher`, and `MarkovEngine` (sub-microsecond performance)
- **NLP Fast-Dictionary** — 1,000+ pre-loaded English→Shell phrase mappings for offline translation without any LLM
- **Raw Shell Mode** — Full privacy mode that disables all LLM engines, telemetry, and RAG scanners while retaining C++-powered Ghost Text, syntax highlighting, and local NLP translation
- **Multi-LLM First-Run Wizard** — Guided onboarding UI supporting Ollama, Groq, Google Gemini, Anthropic Claude, OpenAI, and OpenRouter with direct "Get API Key" hyperlinks
- **Ghost Text Auto-Suggestions** — Zsh-style faded text predictions ahead of the cursor, powered by the C++ Markov Engine
- **Workspace Context Awareness (RAG)** — Silent directory scanning (`package.json`, `requirements.txt`, `.git`) to automatically inject project context into LLM prompts
- **PII Scrubbing Filter** — Automatic redaction of passwords, API keys, and sensitive environment variables before cloud LLM transmission
- **Smart Offline Fallback** — Automatic detection of network loss and seamless pivot from cloud LLMs to local Ollama
- **Auto-Update Version Checker** — Lightweight GitHub release checker with user notification
- **Settings GUI Panel** — In-app configuration for shells, themes, LLM models, and engine parameters
- **IDE Default Terminal Injection** — VS Code / Antigravity IDE extension that automatically sets NeuroShell as the default integrated terminal

### Changed
- **`LICENSE.txt`** — Upgraded from basic copyright to comprehensive Proprietary EULA with reverse-engineering prohibition, confidentiality clauses, and termination terms
- **`README.md`** — Complete rewrite reflecting v5.0 architecture, multi-LLM support, and proprietary status
- **`SECURITY.md`** — Updated with PII scrubbing documentation and Zero-Trust privacy architecture
- **`pyproject.toml`** — Bumped to v5.0.0, added C++ build system requirements and new LLM provider dependencies
- **`cpp_engine/__init__.py`** — Graceful C++/Python fallback: tries compiled C++ module first, falls back to pure Python automatically

### Security
- Proprietary copyright headers injected into all core source files
- PII scrubbing prevents accidental credential leakage to cloud providers
- Raw Shell Mode provides air-gapped terminal operation with zero network activity

---

## [4.2.0] — 2026-04-12

### Added
- **`nlp/embeddings.py`** — Production embedding module with `EmbeddingModel` (sentence-transformers primary + TF-IDF zero-dependency fallback, thread-safe)
- **`operations/git_ops.py`** — Full git CLI wrapper: `status`, `log`, `commit`, `push`, `pull`, `undo_last_commit`, `stash`, `branches`, `diff`, `tags`
- **`tests/test_core_pipeline.py`** — 58-test suite covering Config, SecurityGuard, IntentClassifier, ShellExecutor, EmbeddingModel, GitOps
- **`NeuroShell_Installer.iss`** — Inno Setup 6.x Windows installer script (per-user, LZMA2, Start Menu + desktop shortcuts)
- **`SECURITY.md`** — Responsible disclosure policy and security architecture documentation
- **`requirements-dev.txt`** — Separated dev/test dependencies (pytest, ruff, mypy, bandit, pip-audit)
- **`CHANGELOG.md`** — This file

### Changed
- **`pyproject.toml`** — Bumped version 4.0→4.2, status Beta→Production/Stable, added ruff/mypy/coverage tool config, `neuroshell-gui` entry point
- **`requirements.txt`** — Added upper-bound version constraints for all packages, added numpy, Pillow
- **`pytest.ini`** — Added strict-markers, custom markers (slow, integration, gui, llm)
- **`.github/workflows/ci.yml`** — Full pipeline: lint (ruff) → typecheck (mypy) → test (3×OS, 3×Python) → security (pip-audit + bandit) → build on tag
- **`desktop_app.py`** — Production hardening: `_GUIMockStdin`, singleton windows, telemetry teardown, ANSI pre-compilation, history dedup

### Fixed
- `SafetyResult.safe` attribute → corrected to `SafetyResult.should_block` across tests
- `IntentClassifier` constructor → takes no config argument (fixed test)
- `ShellExecutor.run()` → corrected to `ShellExecutor.execute()` (fixed test)
- `sys.stdin` command wrapping on Windows (`cmd /c` prefix) — test assertion uses `in` not `==`

### Security
- All 56 tests pass; 0 secrets/keys in source; `bandit` SAST integrated in CI

---

## [4.1.0] — 2026-03-15

### Added
- Circuit breaker with configurable failure threshold and recovery timeout
- Groq cloud LLM fallback when Ollama is unreachable
- Safety audit log with hash-chain integrity verification
- Deploy manager: promote, rollback, canary, drift-check
- Browser access module (fetch + Playwright screenshot)
- GitHub API operations via `gh` CLI
- Policy profiles (dev / staging / production)
- Plugin trust-gate and capability system

### Changed
- Secrets upgraded from XOR (v1) to Fernet AES-128 (v2) with automatic migration
- LLM client: added TTL-based LRU cache (3600s, 200 entries)
- Config system: added hot-reload, profile support, TOML persistence

### Fixed
- `os.getlogin()` crash in Docker/WSL/CI — safe fallback chain
- Division-by-zero in HUD telemetry when sample count is zero

---

## [4.0.0] — 2026-01-30

### Added
- Initial production release
- NLP intent classifier (scikit-learn + rule fusion)
- LLM translation (Ollama + local models)
- Command history with FTS (full-text search via SQLite)
- Undo/rollback with filesystem snapshot
- Error auto-fix pipeline
- Semantic search (MiniLM embeddings)
- Desktop GUI (customtkinter, dark theme, dashboard HUD)
- Observability: structured logger, event tracer, provenance tracker
- Resilience: rate limiter, retry with backoff

---

[4.2.0]: https://github.com/abneeshsingh21/neuroshell/compare/v4.1.0...v4.2.0
[4.1.0]: https://github.com/abneeshsingh21/neuroshell/compare/v4.0.0...v4.1.0
[4.0.0]: https://github.com/abneeshsingh21/neuroshell/releases/tag/v4.0.0
