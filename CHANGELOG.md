# Changelog

All notable changes to NeuroShell are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [5.17.0] — 2026-08-30

### Added — Phase 9: WASM Plugin Runtime (capability-scoped WASI sandbox)

- **`core/plugin_runtime.py` (new)** — third-party plugins run as
  WebAssembly/WASI modules inside a wasmtime embedding with **zero
  ambient authority**:
  - **Filesystem**: none by default — only manifest-declared dirs are
    preopened (`fs_read` mounted read-only, `fs_write` read-write; max 8;
    a granted path that doesn't exist is an error, not a silent hole).
  - **Environment**: allowlist of variable names only (max 16).
  - **Network**: never available — nothing is linked.
  - **CPU**: fuel metering (default 50M, host cap 500M) — an infinite
    loop traps with "exceeded its CPU budget", it cannot hang the host.
  - **Memory**: wasmtime store limits (default 64 MiB, cap 256 MiB).
  - **stdout/stderr/stdin** wired through temp files, capture capped at
    1 MB.
- **Manifest schema v1** (`plugin.json`): strict name/semver/entry
  validation, NUL-byte path rejection, limits clamped to host ceilings
  (a manifest may ask for less, never more).
- **Informed consent**: `install()` without `approved=True` raises with
  the full human-readable permission surface; the CLI shows it and
  requires `--yes`. Modules must compile in wasmtime **before** consent
  is requested.
- **SHA-256 supply-chain pinning**: module hash recorded at install,
  re-verified before every run — a swapped `plugin.wasm` refuses to run
  until reinstalled/re-approved. Installs are tmp-write + rename
  (crash-safe: a half-install is never runnable); corrupt store entries
  are invisible, never runnable.
- **Hash-chained audit** (`~/.neuroshell/plugin_audit.jsonl`, same
  tamper-evident scheme as MCP/remote): plugin_installed, plugin_run,
  plugin_hash_mismatch, plugin_uninstalled.
- **`neuroshell-plugin` console script**: install / list / info / run
  (args after `--` pass through verbatim, `--stdin`) / uninstall.
  `docs/PLUGINS.md` covers the security model and authoring in
  Rust/C/Go/WAT. `wasmtime` is an optional dependency
  (`pip install "neuroshell[plugins]"`) — absent, plugin commands fail
  cleanly and nothing else is affected.
- **42 new tests** (676 total pass): manifest validation matrix (names,
  semver, env, preopen caps, NUL bytes, ceiling clamps), consent gate,
  hash pinning + tamper refusal, fuel-bomb trap, missing export,
  stdin wiring, missing-grant error, corrupt-store invisibility, audit
  event sequence, full CLI lifecycle. Live E2E: WAT plugin installed,
  run (stdout captured), tampered (refused), uninstalled — audit chain
  intact.

## [5.16.0] — 2026-08-30

### Added — Phase 8: Kernel-Level Sandboxing for AI-Generated Commands

- **`cpp_engine/launcher/sandbox_engine.hpp` (new)** — the Phase 4
  blast-radius preview is a heuristic; obfuscated commands can evade string
  analysis. This phase adds **kernel enforcement**: the child process is
  confined between `fork` and `exec` no matter what the command string
  turns out to mean:
  - **`PR_SET_NO_NEW_PRIVS`** — setuid/setgid/caps can never elevate.
  - **Landlock LSM (ABI 1–3 adaptive)** — whole tree read+execute only;
    project dir, `/tmp` (when granted), `~/.neuroshell`, and device files
    (`/dev/null`, `/dev/tty`, …, via reduced file-only masks — Landlock
    rejects directory rights on non-directory fds) read-write. An
    AI-translated `rm` outside the project gets **EACCES from the kernel,
    not from a regex**.
  - **seccomp-BPF denylist** — mount family, `pivot_root`/`chroot`, module
    load/unload, reboot/kexec, swap, `bpf()`, `open_by_handle_at` (a
    classic Landlock bypass primitive), `perf_event_open`. Denied calls
    fail with **EPERM (readable errors), not SIGKILL**; non-native-arch
    syscalls are killed outright so the 32-bit compat table can't bypass
    the filter.
- **Modes** (`/sandbox off|project|strict`, env `NEUROSHELL_SANDBOX`):
  `project` (default) confines **AI-translated commands only** — the
  untrusted input path — while user-typed commands run unconfined;
  `strict` confines every non-TUI command. **`!command` escalation** runs
  one command unsandboxed (explicit user intent, sudo ergonomics).
- **Fail-closed**: if confinement was requested but cannot be established,
  the child refuses to exec (distinct exit codes 90+step, surfaced with the
  failing step name) — a sandbox that silently isn't there is worse than an
  error. Fork-safety contract: all allocation happens in the parent
  (`PreparedSandbox::Prepare`); the child performs only raw syscalls.
- **`/sandbox` status panel** (mode, Landlock ABI, seccomp availability)
  and help-panel entries; non-Linux platforms compile to stubs.
- **49 new native checks** (687 total, 0 failures) including **live kernel
  enforcement**: write/rm outside project denied by the kernel while the
  file survives, reads and system binaries allowed, `/dev/null` writable,
  `/tmp` not writable unless granted, `chroot` → EPERM (not signal), extra
  `rw_paths` honored, unconfined control, `ShouldSandbox` policy matrix,
  escalation override, rw-path dedup, mode parsing.

### Notes

- Requires Linux ≥ 5.13 for Landlock (probe: `/sandbox`). On kernels
  without it, NeuroShell warns and falls back to the heuristic layers
  (blast-radius + safety patterns) rather than pretending to confine.

## [5.15.0] — 2026-08-30

### Added — Phase 7: Remote Execution with Local Safety (`nsh user@host`)

- **`core/remote_executor.py` (new)** — run commands on remote machines over
  SSH while **every intelligence and safety layer executes locally**, before
  a single byte leaves the machine:
  `input → local NL translation → local PolicyEngine RBAC → local 4-layer
  SafetyChecker → local outbound DLP scan → SSH → remote → local inbound DLP
  scrubbing → hash-chained audit → screen`.
  - **BLOCKED commands never spawn an SSH process** (verified by test:
    `subprocess.run` is never invoked) — a compromised remote host cannot
    weaken safety, and `confirm` offers no override.
  - **Two-phase confirmation** for DANGER/CAUTION commands, same semantics
    as the MCP server.
  - **Outbound secret detection**: if the command string itself contains a
    credential (Bearer token, AWS key, …) the user is warned it would be
    sent to the remote host.
  - **Inbound DLP**: remote stdout/stderr is scrubbed locally before it
    reaches the terminal or scrollback (passwords in remote configs, tokens
    in remote logs).
  - **Hash-chained audit** (`~/.neuroshell/remote_audit.jsonl`, reuses the
    tamper-evident `MCPAuditLog`) records target + decision + risk for
    every refused/confirmed/executed command.
- **Transport: system `ssh` with ControlMaster auto-multiplexing** — first
  command pays the handshake, subsequent ones reuse the master (**measured
  9 ms** per command against a live sshd). `BatchMode=yes` (never hangs on
  password prompts), `StrictHostKeyChecking=accept-new` (refuses changed
  host keys), control sockets under `~/.neuroshell/ssh` (chmod 700). No
  paramiko, zero new dependencies; `~/.ssh/config`, agents, ProxyJump and
  hardware keys keep working. The vetted command travels as **one argv
  element** — the local shell never interprets it.
- **`nsh` console script** — one-shot (`nsh host uptime`, flags after the
  target pass through verbatim via `argparse.REMAINDER` — `rm -rf` is never
  eaten), `--yes` auto-confirm, `--timeout`, and an interactive REPL with
  local NL→command translation for non-shell-looking input.
- **`RemoteTarget` parser** — `[user@]host[:port]` incl. bracketed IPv6;
  rejects injection attempts (`host; rm -rf /`, `$(evil)@host`, backticks).
- **46 new tests** (634 total pass): target parsing/injection matrix,
  BLOCKED-never-spawns-transport, two-phase confirm, outbound secret flag,
  inbound stdout/stderr scrubbing, timeout kill, audit event sequence,
  SSH argv shape, control-dir permissions, NL heuristic, REMAINDER
  regression. Live E2E against a real local sshd: connect, exec,
  multiplexed latency, BLOCKED refusal, DLP scrub, CLI one-shot + `--yes`.

## [5.14.0] — 2026-08-30

### Added — Phase 6: MCP Server Mode (safety-shielded agent execution)

- **`core/mcp_server.py` (new)** — NeuroShell is now a **Model Context
  Protocol tool provider** over stdio, so Claude Desktop, Cursor, and agent
  frameworks execute shell commands *through* the safety stack instead of a
  raw shell. Zero new dependencies: the transport is newline-delimited
  JSON-RPC 2.0, implemented natively (handshake, `tools/list`, `tools/call`,
  notifications, `ping`, graceful unknown-method handling).
- **Four tools**: `neuroshell_execute` (gated execution),
  `neuroshell_translate` (NL → command + risk grade, nothing runs),
  `neuroshell_explain` (offline DB → man page → LLM), and
  `neuroshell_safety_check` (grade without executing).
- **Execution pipeline** for `neuroshell_execute`:
  PolicyEngine RBAC → 4-layer SafetyChecker → **two-phase confirmation**
  (DANGER commands are refused with structured risk details until re-called
  with `confirm=true`; **BLOCKED commands have no override parameter at
  all**) → ShellExecutor (injection guard, clamped timeout ≤ 300 s) →
  **PII/DLP scrubbing** of stdout/stderr before bytes return to the client →
  shared SQLite history (`source='mcp'`).
- **Hash-chained audit log** (`~/.neuroshell/mcp_audit.jsonl`) — every
  decision (executed, refused_policy, refused_blocked,
  confirmation_required, executed_confirmed) embeds the SHA-256 of the
  previous entry; `MCPAuditLog.verify()` detects any tampering from the
  altered line forward. Chain state survives server restarts.
- **Per-client policy scope** via the MCP client's `env` block:
  `NEUROSHELL_MCP_ROLE` (unknown roles degrade to `guest` — least
  privilege) and `NEUROSHELL_MCP_READONLY=1` (execute disabled;
  advisory tools stay available).
- **Protocol hygiene** — stdout is reserved for JSON-RPC framing; engine
  banner prints are redirected to stderr for the server's lifetime, so a
  chatty subsystem can never corrupt the stream (verified byte-exact in the
  stdio E2E test).
- **`neuroshell-mcp` console script** + `docs/MCP_SERVER.md` (Claude
  Desktop / Cursor setup, gating semantics, audit verification).
- **34 new tests** (`tests/test_mcp_server.py`, 588 total pass): handshake,
  schemas, two-phase confirm actually deleting only in phase 2, BLOCKED
  refusal even with `confirm=true`, DLP redaction of AWS keys in output,
  read-only scope, role degradation, audit chain tamper detection, and a
  full subprocess stdio session.

## [5.13.0] — 2026-08-30

### Added — Phase 5: Universal Undo (CoW snapshots of write-targets)

- **`cpp_engine/launcher/undo_engine.hpp` (new)** — `UndoEngine`: when the
  user confirms a destructive command in the Phase 4 blast-radius gate, the
  launcher snapshots every existing write-target into
  `~/.neuroshell/undo/<txn>/` **before** execution:
  - **Copy-on-write first** — Linux `FICLONE` reflinks (btrfs/XFS/bcachefs)
    and macOS `clonefile(2)` (APFS) share extents with the original, so
    snapshotting large trees is near-instant and near-free. Filesystems
    without reflink (ext4, tmpfs) fall back to a real copy bounded by a
    **512 MiB budget** — over budget, the snapshot is skipped cleanly
    (partial txn removed) and the confirmed command still runs: undo is
    best-effort, never a blocker.
  - **Durable manifests** — line-oriented, tab-escaped format (no JSON
    parser needed to restore), committed via tmp-write + rename with a
    `complete` sentinel; a transaction missing the sentinel is never
    restored and is swept by GC (crash-safe by construction).
  - **GC budgets** on every snapshot: max 20 transactions, 2 GiB total,
    7-day age — oldest evicted first; corrupt/incomplete dirs swept.
  - Symlinks preserved as symlinks; permission bits restored; directory
    trees restored recursively; snapshot walk capped at 50k inodes.
- **`undo` / `undo list` builtins** — `undo` shows what would be restored
  (command, files, bytes) and asks y/N; on success the transaction is
  consumed (LIFO — newest first). `undo list` shows the stack. Works
  outside git repos — this is filesystem-level, not VCS-level.
- **Confirmation flow integration** — after `y` (or typed `yes` for
  CRITICAL), the gate prints `⎌ Undo point saved (N files, X MiB) — type
  'undo' to revert.` Opt-out: `NEUROSHELL_NO_UNDO=1`.
- **52 new native checks** (638 total, 0 failures): manifest escaping
  round-trips, dir/file/symlink snapshot+restore cycles, copy-budget and
  inode-budget skips with clean partial-dir removal, incomplete-manifest
  rejection, GC eviction, LIFO ordering, permission-bit restoration,
  empty-store failure path.

### Notes

- Deliberately out of scope for v1: block-device writes (`dd of=/dev/sdX`),
  VCS-destructive verbs (`git reset --hard` has the reflog), and
  permission-only changes (`chmod -R` metadata journaling).

## [5.12.0] — 2026-08-30

### Added — Phase 4: Blast-Radius Preview (dry-run destructive-command gate)

- **`cpp_engine/launcher/blast_radius.hpp` (new)** — `BlastRadiusAnalyzer`: a
  quote-aware shell parser (segments across `| ; && ||`, tokenizer handling
  quotes, backslash escapes, and `>`/`>>`/`2>` redirection operators) plus a
  real-filesystem impact engine. Before a destructive command runs, NeuroShell
  resolves its targets (tilde expansion + trailing-component globs), walks them
  with hard caps (**50,000 inodes / 500 ms**, so the preview can never hang),
  and grades severity:
  - **CRITICAL** — system-critical paths (`/`, `/etc`, `/usr`, `$HOME`, …) or
    raw block-device writes (`dd of=/dev/sdX`, `mkfs`, `fdisk`, `parted`,
    `wipefs`). Requires typing `yes` to proceed.
  - **HIGH** — recursive deletes of >1,000 files or >1 GiB, capped scans
    ("assume the worst"), and VCS-destructive verbs: `git clean -f`,
    `git reset --hard`, `git push --force`, `git branch -D`, `find … -delete`.
  - **MEDIUM** — bounded deletions of existing files, `mv`/`cp` overwriting an
    existing file, `>` truncation of a non-empty file, `truncate`,
    `chmod/chown -R`. Confirmed with a single `y`.
  - **NONE** — everything else, including `rm` of nonexistent paths: zero
    friction, no prompt, no scan overhead for non-destructive commands.
- **Preview panel in the launcher** — severity-colored card showing each
  operation's verb, resolved targets, and measured `files / bytes` totals
  (prefixed with `≥` when the scan hit its cap), rendered just before
  execution; declining aborts with nothing executed. Destructive stages hidden
  mid-pipeline (`ls && rm -rf x | echo`) are still caught. Benign wrappers
  (`sudo`, `env`, `nohup`, `time`, `VAR=…`) are unwrapped before analysis.
- **Opt-out for CI / scripted use** — `NEUROSHELL_NO_BLAST_GUARD=1` disables
  the gate entirely.
- **84 new native checks** (586 total, 0 failures): tokenizer/segment matrix,
  glob resolution against a live fixture tree, symlinks counted-not-followed,
  severity policy (incl. `rm -rf /`, `dd` device vs file, git verbs, `>` vs
  `>>`), inode-cap behavior, and quoted-paths-with-spaces resolution.

### Notes

- This is a **heuristic safety net**, not a sandbox: obfuscated commands can
  evade it. Kernel-level enforcement is Phase 8 on the roadmap.

## [5.11.0] — 2026-08-30

### Added — SQLite+FTS5 Ranked History (Phase 3 of the engineering roadmap)

The native host's history moves from an append-only `history.txt` flat file
to the **same SQLite database the Python daemon already maintains**
(`~/.neuroshell/history.db`) — one unified, searchable history across both
processes.

- **`sqlite_dyn.hpp`** — runtime-loaded SQLite binding (dlopen/LoadLibrary
  of the system library: `libsqlite3.so.0` / `libsqlite3.dylib` /
  `winsqlite3.dll`). Zero build-time dependency, all-or-nothing symbol
  resolution, and full fail-open degradation: no system SQLite ⇒ the legacy
  flat file keeps working, the shell never refuses to start.
- **`history_engine.hpp`** — WAL journal + 5 s busy timeout for safe
  concurrent host/daemon access; schema-compatible inserts into the
  existing `commands` table (`source='native_host'`) with `commands_fts`
  FTS5 indexing; microsecond REAL timestamps matching Python `time.time()`.
- **Ranked recall** — Ctrl+R results are scored
  `0.6·frecency + 0.3·cwd-affinity + 0.1·prefix-match`, where frecency is
  `ln(1+uses) · 2^(−age/72h)`: what you run often *and* recently *and* in
  this directory surfaces first. The Ctrl+R modal now shows the top-5
  ranked matches with ↑/↓ navigation instead of a single most-recent
  substring hit.
- **One-time legacy migration** — `history.txt` lines are imported (with
  FTS indexing and order-preserving timestamps) on first open; a marker
  row makes re-runs no-ops and the file is left untouched for rollback.
- **Injection-proof by construction** — every user string is bound via
  prepared-statement parameters; FTS queries are rewritten as quoted
  prefix tokens (`git pu` → `"git" "pu"*`) so FTS5 operators (`OR`,
  `NEAR`, column filters) in user input are inert.

### Testing
- Native suite 439 → 502 checks: frecency maths (monotonicity, exact 72 h
  half-life), FTS sanitization matrix, and a live-DB battery — cwd-affinity
  ranking flips winners per directory, prefix beats substring, hostile
  queries (`'; DROP TABLE commands;--`, `a OR b`, unbalanced quotes) are
  inert, migration idempotence, concurrent second-connection visibility,
  and unopened-engine no-op degradation.
- Python suite 544 → 554: `tests/test_shared_history_db.py` pins the
  schema contract the C++ side relies on (columns, FTS shape, WAL mode,
  cross-process visibility, fractional timestamps, ranking maths mirror).
- Cross-language E2E: C++-written rows found by Python `HistoryStore`
  search; Python-written rows found by C++ ranked recall; cwd-affinity
  winner verified over the shared file.

---

## [5.10.0] — 2026-08-29

### Added — SHM Token Streaming (Phase 2 of the engineering roadmap)

AI responses (`cmd | @ai`, `@fix`, `@explain`) now render **token by token**
as the LLM produces them, instead of blocking for the full response. The
tokens travel over a dedicated shared-memory ring — no sockets, no JSON
per token, sub-frame latency.

- **SHM ABI v3** (`shm_ipc.hpp` + `core/shm_bridge.py`, byte-identical on
  both sides) — rings are now *named*: the legacy event ring (host → daemon)
  plus a new **stream ring** (daemon → host). New header field
  `cancel_stream_id` @ offset 84 for consumer → producer cancellation.
  Compile-time `static_assert`s pin every offset.
- **Binary stream frames** `[u8 type][u32 stream_id LE][utf-8 payload]` with
  `TOKEN`/`END`/`ERROR` types. Frames from stale stream ids are silently
  dropped — a cancelled stream's in-flight tokens can never bleed into the
  next answer. Malformed frames are rejected, never surfaced.
- **Esc cancels generation mid-flight** — the host publishes the stream id
  in `cancel_stream_id`; the daemon polls it between tokens and aborts the
  LLM iteration (cooperative cancel, acked with `END{"cancelled": true}`).
- **`TokenStreamReader`** (`stream_reader.hpp`) — host-side consumer with
  first-token (30 s) and inter-token stall (15 s) deadlines so a dead daemon
  can never hang the host; 2 ms poll granularity; DLP masking applied per
  completed line via a carry buffer so a secret split across token frames is
  still masked before a single byte reaches the screen.
- **`ai_pipe_stream` RPC** (`core/ipc_server.py`) — streams via
  `llm.generate_streaming` with bounded backpressure retries (gives up if
  the host stops draining), publishes exactly one terminal frame, and
  returns the full text as a fallback/verification copy. Degrades gracefully
  to blocking `ai_pipe` when the ring or a v3 daemon is unavailable.

### Testing
- Native suite 393 → 439 checks: frame roundtrips (UTF-8 multibyte splits
  reassembled byte-exact), garbage-frame rejection, cancel-flag semantics,
  `drain()`, and a threaded `TokenStreamReader` battery (happy path, stale-id
  filtering, ERROR frames, cooperative cancel with producer ack, END-carried
  cancel).
- Python suite 526 → 544: stream-frame binary-layout contract tests (offset
  84, little-endian id) + 11 `ai_pipe_stream` dispatcher tests (cancel
  between tokens, stale-cancel ignored, no-ring degradation, invalid
  stream_id rejection, provider-error frames, legacy path untouched).
- Cross-language E2E proofs: Python-produced token stream rendered live by
  the C++ reader (UTF-8 intact, line-carry correct), and C++-initiated
  cancel observed by the Python producer which stopped and acked.

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

### Fixed (Critical)
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
- **Version drift** — `__version__.py` said 5.0.6 while `pyproject.toml` said 5.7.0 and `setup.py` said 5.0.0, with the version also hardcoded in 8 places in `main.cpp`, install scripts and build tooling. Single sources of truth now: `version.hpp` (native) and `__version__.py` (Python, read by `setup.py`/build scripts).

### Added
- `cpp_engine/launcher/safe_exec.hpp` — injection-proof subprocess primitives (argv exec, stdout capture, stdin plumbing, strict POSIX/Win32 quoting, input validators).
- `cpp_engine/launcher/version.hpp` — native version constants + numeric semver comparison.
- `cpp_engine/tests/native_tests.cpp` — first native C++ test suite (307 checks: semver, validators, quoting, SHM ABI/roundtrip/wrap/oversize, DLP masking, argv-exec injection resistance) wired into CTest.
- `tests/test_ipc_hardening.py` + expanded `tests/test_shm_ipc.py` — concurrency, DoS-guard, ABI-layout, wraparound and UTF-8 regression coverage.
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
