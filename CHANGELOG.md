# Changelog

All notable changes to NeuroShell are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

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
