# NeuroShell Production-Hardening Audit — August 2026

**Scope:** Full codebase (~41k LOC Python, C++ launcher headers, CI/CD, packaging)
**Method:** Static analysis (ruff full rule set, AST inspection), dynamic execution of the
startup/shutdown lifecycle, full test-suite execution on Linux/py3.11, and manual review of
every security-relevant module (`server.py`, `core/executor.py`, `core/policy_engine.py`,
`intelligence/safety.py`, `config.py` secret handling, `Dockerfile`, CI workflows).

---

## 1. Baseline (before)

| Metric | Value |
|---|---|
| Tests | 498 collected — **12 failing**, 1 skipped |
| Ruff (repo's own configured rules) | **433 violations** → CI lint job red |
| Undefined-name runtime bugs (F821/F823/F811/B023) | **8 confirmed** |
| Startup lifecycle | `startup()` crashes with `NameError: threading` (verified by execution) |
| Shutdown lifecycle | background services never stopped (shadowed method) |
| Server safety shield | broken — `SafetyResult.risk` attribute does not exist |
| Version | 3-way drift: 5.0.6 / 5.7.0 / 5.0.0 |
| Docker | runs as root, no `.dockerignore` |

## 2. Findings and resolutions

### P0 — Runtime correctness

| ID | Component | Defect | Resolution |
|----|-----------|--------|------------|
| P0-1 | `main.py` startup | `threading` imported only in `__init__` scope; `startup()` raised `NameError`, killing async warmup + downstream startup steps | module-level import |
| P0-2 | `main.py` lifecycle | duplicate `shutdown()`; the later definition shadowed the one that stopped `ipc_server`/`auto_dream` | single idempotent `shutdown()` + `_stop_background_services()` |
| P0-3 | `main.py` deploy | local `from pathlib import Path` created an unbound local before the import line → `UnboundLocalError` in `deploy promote` | removed all redundant local imports |
| P0-4 | `main.py` handlers | `VoiceCommandEngine` / `NeuroShellAPI` referenced but never in scope | scoped imports at call sites |
| P0-5 | `server.py` | `safety_res.risk` (nonexistent) crashed the pipeline **after** translation for every command; blocked commands were not blocked | `risk_level` |
| P0-6 | `auto_dream.py` | `finally` referenced out-of-scope `e`; unconditional `ui_callback` call | dead code removed |
| P0-7 | slash router | POSIX `shlex` stripped quotes from `/clip copy` payloads | raw arg string passed to clip handler |
| P0-8 | `smart_open.py` | well-known folders required local existence → nondeterministic resolution | trusted mapping resolves deterministically |
| P0-9 | `llm/client.py` | retry lambda late-bound loop variable (B023) | default-arg binding |

### P1 — Security

| ID | Component | Gap | Resolution |
|----|-----------|-----|------------|
| P1-1 | `server.py` | token compared with `!=` (timing oracle) | `secrets.compare_digest` |
| P1-2 | `server.py` | `/ws/telemetry`, `/ws/sysmon` unauthenticated | shared `_authorize_websocket` gate on all WS endpoints |
| P1-3 | `server.py` | silent open mode when key unset | explicit startup warning |
| P1-4 | `server.py` | raw command frames logged at INFO | demoted to DEBUG, byte-count only |
| P1-5 | `Dockerfile` | container ran as root | dedicated `neuroshell` system user; `HOME=/app` |
| P1-6 | build context | no `.dockerignore`; keys/artifacts could enter layers | added `.dockerignore` excluding `.git`, `.master.key`, `*.pem`, envs |
| P1-7 | `session_memory.py` | MD5 dedup hash | truncated SHA-256 |
| P1-8 | multiple | bare `except:`, missing exception chaining | `except Exception:` + `raise … from e` |
| P1-9 | `/ws/sysmon` | crashed when psutil absent | graceful close with error frame |

S608 SQL-injection hits were audited and found to be false positives (hard-coded
table lists / placeholder-only condition strings); they are annotated inline with
justification comments rather than globally suppressed.

### P2 — Engineering hygiene

- **Lint:** 433 → 0. Mechanical issues fixed (unused imports/variables, deprecated
  typing generics, `E701` one-liners expanded, ambiguous `l` renamed). Intentional
  patterns (S110/S112 graceful-degradation guards around optional subsystems, E402
  lazy imports for startup latency, S311 non-crypto randomness for jitter/chaos)
  are codified in `pyproject.toml` with dated justifications — CI lint is now a
  meaningful, enforceable gate.
- **Version:** unified to 5.7.1; `setup.py` now derives its version from
  `__version__.py`, and a regression test asserts `pyproject.toml` agreement.
- **Caught-in-review:** ruff's "safe-looking" SIM118 autofix would have broken
  `sqlite3.Row` handling (`Row` has `.keys()` but not `.get()`); reverted with an
  explanatory noqa — a reminder that autofixes require test verification.

## 3. Verification (after)

| Metric | Value |
|---|---|
| Tests | **519 passed** (501 existing/adjusted + 18 new regression tests), 0 failed |
| Ruff | `All checks passed!` |
| Startup lifecycle | executes cleanly end-to-end (verified by direct execution) |
| Shutdown | idempotent, stops IPC + AutoDream (regression-tested) |
| Server API tests | 3/3 pass with fastapi installed |

## 4. Recommended next steps (out of scope for this PR)

1. **Executor sandboxing depth** — consider seccomp/JobObject resource jails for
   AI-translated commands beyond pattern-based safety.
2. **mypy strict ratchet** — the CI mypy job is `|| true`; ratchet per-module.
3. **Property-based testing** — `hypothesis` for the safety normalizer
   (`_normalize_for_safety`) which is regex-heavy and adversary-facing.
4. **SBOM + provenance** — add `pip-audit --strict` gating and SLSA provenance to
   the release workflow.
5. **Consolidate duplicated shell integrations** — `integrations/` and
   `shell_integrations/` have diverged copies of the same scripts.
6. **Root-level ad-hoc test scripts** (`test_ws.py`, `test_phase5.py`, …) should be
   migrated into `tests/` or `examples/` so pytest discovery and packaging stay clean.
