# 📖 NeuroShell — Exhaustive Feature & Module Catalog (The Complete Architecture Bible)

This document is the **definitive, exhaustive catalog** of every architectural domain, module, class, feature, command, prompt, extension, configuration parameter, and security mechanism in **NeuroShell v5.6.0**.

---

## 📑 Table of Contents
1. [Architectural Domain Overview](#1-architectural-domain-overview)
2. [Core Execution & System Layer (`core/`)](#2-core-execution--system-layer-core)
3. [Intelligence, NLP & AI Translation (`intelligence/` & `nlp/`)](#3-intelligence-nlp--ai-translation-intelligence--nlp)
4. [Learning & Autonomous Memory (`learning/`)](#4-learning--autonomous-memory-learning)
5. [LLM Routing, Multi-Provider & Resilience (`llm/` & `resilience/`)](#5-llm-routing-multi-provider--resilience-llm--resilience)
6. [Native C++20 High-Speed Engine (`cpp_engine/`)](#6-native-c20-high-speed-engine-cpp_engine)
7. [Operations, Web & DevOps Automation (`operations/`)](#7-operations-web--devops-automation-operations)
8. [Enterprise Extensions & Security (`extensions/`)](#8-enterprise-extensions--security-extensions)
9. [Desktop GUI Cockpit & REST API Server](#9-desktop-gui-cockpit--rest-api-server)
10. [VS Code Extension (`vscode-extension/`)](#10-vs-code-extension-vscode-extension)
11. [Master Configuration Dictionary (`config.toml`)](#11-master-configuration-dictionary-configtoml)
12. [Complete Command, Prompt & Directive Dictionary](#12-complete-command-prompt--directive-dictionary)

---

## 1. Architectural Domain Overview

NeuroShell is composed of **7 core operational domains**, **70+ Python modules**, **1 native C++20 terminal engine**, **1 TypeScript VS Code extension**, and **8 CustomTkinter desktop extension panels**:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                  NEUROSHELL ECOSYSTEM                                  │
├────────────────────────────────┬────────────────────────────────┬──────────────────────┤
│ 1. Native C++20 Engine         │ 2. Intelligence & NLP Layer    │ 3. Core & Sandbox    │
│  • Win32 ConPTY & POSIX PTY    │  • 4-Layer Zero-Trust Safety   │  • ShellExecutor     │
│  • Task Supervisor (0-zombie)  │  • Multi-LLM Router (6 backends│  • GitSandbox        │
│  • Polyglot Test Orchestrator  │  • 2,550+ Offline Phrases      │  • SQLite+FTS5 Store │
│  • Viewport Secret DLP Masker  │  • Autonomous Swarm Planner    │  • Process Monitor   │
├────────────────────────────────┼────────────────────────────────┼──────────────────────┤
│ 4. Enterprise Extensions       │ 5. Learning & Memory           │ 6. User Interfaces   │
│  • SHA-256 Audit Trail         │  • AutoDream Memory            │  • C++ Terminal Host │
│  • Vulnerability Scanner       │  • Markov Pattern Learner      │  • Desktop Cockpit   │
│  • Session Notebook & Snippets │  • Adaptive Autocomplete       │  • VS Code Extension │
│  • Plugin System (Sandboxed)   │  • Feedback Weight Optimizer   │  • REST API Server   │
└────────────────────────────────┴────────────────────────────────┴──────────────────────┘
```

---

## 2. Core Execution & System Layer (`core/`)

| Module | Key Class / Component | Purpose & Capabilities |
| :--- | :--- | :--- |
| **`core/executor.py`** | `ShellExecutor` | Cross-platform command execution, max 10 concurrent background workers, stdout/stderr non-blocking buffer management, process snapshotting, memory/CPU telemetry. |
| **`core/context.py`** | `ContextManager` | OS environment detection (Windows/macOS/Linux), current working directory tracking, virtual environment inspection, Git repository state analysis. |
| **`core/history.py`** | `HistoryStore` | SQLite-backed persistent history with FTS5 full-text indexing, 90-day retention pruning, CSV/JSON session exports. |
| **`core/output_parser.py`** | `OutputParser` | Detects and structures command outputs: CSV, JSON, XML, key-value tables, log formats, stack traces, and exit codes. |
| **`core/sandbox.py`** | `GitSandbox` | Git-backed isolated worktree sandbox allowing risky commands to be previewed and tested with 1-click rollback on failure. |
| **`core/dependency_resolver.py`**| `DependencyResolver`| Verifies required system CLI tools (`git`, `docker`, `cargo`, `mvn`, `npm`, `python`), offering 1-click install suggestions. |
| **`core/env_manager.py`** | `EnvironmentManager` | Auto-detects and activates `.venv`, `conda`, `poetry`, `pipenv`, `virtualenv` environments without manual sourcing. |
| **`core/timer.py`** | `CommandTimer` | Sub-millisecond execution profiling, timing benchmarks, and CPU execution telemetry. |
| **`core/events.py`** | `EventBus` | Asynchronous decoupled event bus connecting IPC, execution, safety, and telemetry layers. |
| **`core/ipc_server.py`** | `NamedPipeServer` | Dual-engine JSON-RPC 2.0 server supporting Windows Named Pipes (`\\.\pipe\neuroshell_ipc`) and Unix Sockets (`~/.neuroshell/ipc.sock`). |

---

## 3. Intelligence, NLP & AI Translation (`intelligence/` & `nlp/`)

| Module | Key Class / Component | Purpose & Capabilities |
| :--- | :--- | :--- |
| **`intelligence/translator.py`** | `CommandTranslator` | Multi-step Natural Language to Shell translation pipeline with context awareness, prompt optimization, and provider failover. |
| **`intelligence/safety.py`** | `SecurityGuard` | **4-Layer Zero-Trust Safety Shield**: Layer 1 Pattern AST $\rightarrow$ Layer 2 Chain Analyzer $\rightarrow$ Layer 3 Filesystem Scope $\rightarrow$ Layer 4 LLM Semantic Audit. |
| **`intelligence/sanitizer.py`** | `InputSanitizer` | Prevents null-byte injections, command chain poisoning, and path traversal attacks (`../..`). |
| **`intelligence/autocomplete.py`** | `SmartAutocomplete` | Ghost-text prediction engine, prefix trees, Levenshtein fuzzy matching, and context-aware suggestions. |
| **`intelligence/pii_scrubber.py`** | `PIIScrubber` | Redacts emails, IP addresses, API keys, passwords, SSNs, and credit card numbers before queries reach cloud LLMs. |
| **`intelligence/error_fixer.py`** | `ErrorAutoFixer` | Pattern engine recognizing 25+ compiler and runtime errors, providing instant 1-click `@fix` auto-repair commands. |
| **`intelligence/explainer.py`** | `CommandExplainer` | Deconstructs complex shell commands into plain English with flag-by-flag breakdowns. |
| **`intelligence/smart_suggestions.py`**| `ContextAdvisor` | Analyzes project files and suggests relevant developer workflows (e.g. `npm run dev`, `docker compose up`). |
| **`intelligence/pipeline_builder.py`**| `PipelineBuilder` | Assembles multi-step Unix/PowerShell pipelines (`curl | jq | grep | sort`). |
| **`intelligence/script_generator.py`**| `ScriptGenerator` | Generates full Bash (`.sh`), PowerShell (`.ps1`), or Batch (`.bat`) scripts from high-level user descriptions. |
| **`intelligence/smart_open.py`** | `SmartOpener` | Deep file, URL, and application launcher with OS-native application associations. |
| **`intelligence/project_detector.py`**| `ProjectDetector` | Detects Node.js, Python, Rust, Go, Java, C/C++, Docker, and Kubernetes environments. |
| **`intelligence/fuzzy_corrector.py`** | `FuzzyCorrector` | Typo tolerance and auto-correction for mistyped commands (`gti push` $\rightarrow$ `git push`). |
| **`intelligence/deep_search.py`** | `DeepSearcher` | Fast content and file search across deeply nested directories. |
| **`intelligence/bookmarks.py`** | `BookmarkStore` | Saved command bookmarks with tags and parameter placeholders. |
| **`intelligence/agent.py` & `swarm.py`**| `AgentCoordinator` | Multi-step autonomous task planner with step verification and human-in-the-loop approval. |
| **`intelligence/_phrase_data.py`** | `OfflinePhrases` | 2,550+ pre-trained, high-speed offline phrase mappings for sub-0.5ms instant offline translation. |
| **`nlp/intent_classifier.py`** | `IntentClassifier` | TF-IDF + LinearSVC with CalibratedClassifierCV for sub-5ms offline intent classification across 30+ categories. |

---

## 4. Learning & Autonomous Memory (`learning/`)

| Module | Key Class | Purpose & Capabilities |
| :--- | :--- | :--- |
| **`learning/predictor.py`** | `MarkovPredictor` | Second-order Markov chain predictor that learns individual developer command transition frequencies. |
| **`learning/pattern_learner.py`** | `PatternLearner` | Discovers repetitive command sequences and proposes custom automated 1-word aliases. |
| **`learning/feedback_loop.py`** | `FeedbackOptimizer`| Adjusts suggestion ranking weights based on user acceptance and execution success rates. |
| **`learning/memory/auto_dream.py`**| `AutoDream` | Background memory consolidation system that prunes stale sessions and optimizes frequently referenced context. |

---

## 5. LLM Routing, Multi-Provider & Resilience (`llm/` & `resilience/`)

### Supported AI Providers:
1. **Groq (Default / High-Speed)**: `llama-3.3-70b-versatile` ($<200\text{ms}$ time-to-first-token).
2. **OpenAI**: `gpt-4o`, `gpt-4o-mini`, `o1`.
3. **Anthropic**: `claude-3-5-sonnet-20241022`.
4. **Google Gemini**: `gemini-1.5-pro`, `gemini-2.0-flash`.
5. **Ollama (100% Offline / Private)**: `llama3.2`, `deepseek-r1`, `qwen2.5-coder`.
6. **OpenRouter**: Access to 100+ open-source models.

### Resilience Layer:
- **`resilience/circuit_breaker.py`**: Intercepts failing network requests to prevent UI lag.
- **`resilience/rate_limiter.py`**: Enforces configurable request rate limits (default: 60 req/min).
- **`resilience/degraded_mode.py`**: Seamlessly falls back to local offline phrases if cloud LLMs are unreachable.
- **`resilience/offline_cache.py`**: LRU caching of translated shell commands.

---

## 6. Native C++20 High-Speed Engine (`cpp_engine/`)

The native C++20 engine powers the user-facing terminal with **sub-millisecond latency**:

| Header / File | Component | Capabilities |
| :--- | :--- | :--- |
| **`main.cpp`** | `EnterpriseTerminalHost` | Win32 ConPTY & POSIX VT100 console host, line editor, ghost-text rendering, ANSI escape sequences, hotkey dispatch. |
| **`task_supervisor.hpp`** | `TaskSupervisor` | Multi-service concurrent runner (`start X and Y`), PID lifecycle tracker, Win32 Job Object & POSIX PGID **0-zombie teardown**. |
| **`test_orchestrator.hpp`** | `TestOrchestrator` | Parallel test runner across CPU cores with smart Git impact analysis (`test changed`) and polyglot repo filters. |
| **`dlp_masker.hpp`** | `DLPMasker` | Real-time Viewport Data Loss Prevention. Auto-redacts OpenAI keys (`sk-proj-***`), AWS keys, GitHub tokens, and JWTs. Toggle unmask with `Ctrl+U`. |
| **`smart_jumper.hpp`** | `SmartDirectoryJumper` | Deep fuzzy directory jumper (`z <dir>`) with path frequency weighting. |
| **`daemon_spawner.hpp`** | `DaemonManager` | Asynchronous, non-blocking background daemon launcher with Win32 Named Mutex singleton guard. |
| **`engine.cpp` / `engine.py`** | `NativeExtension` | pybind11 C++17 extension providing FastParser, FuzzyMatcher, and MarkovEngine. |

---

## 7. Operations, Web & DevOps Automation (`operations/`)

| Module | Component | Capabilities |
| :--- | :--- | :--- |
| **`operations/git_ops.py`** | `GitOpsManager` | Visual branch graphing, smart stashing, soft commit undos, automated merge conflict resolution helpers. |
| **`operations/github_access.py`** | `GitHubCLIBridge` | PR creation, issue inspection, GitHub Actions workflow run monitoring. |
| **`operations/browser_access.py`**| `BrowserAutomator` | Playwright-powered headless web testing, scraping, and verification. |
| **`operations/task_manager.py`** | `BackgroundJobManager`| Concurrent background job scheduler with resource thresholds. |

---

## 8. Enterprise Extensions & Security (`extensions/`)

| Extension Module | Feature Name | Description |
| :--- | :--- | :--- |
| **`extensions/enterprise.py`** | `AuditTrail` | Cryptographically sealed **SHA-256 hash-chained audit log** guaranteeing tamper-evident SOC2 / ISO 27001 compliance. |
| **`extensions/enterprise.py`** | `VulnerabilityScanner`| Scans dependencies (`pip-audit`, `npm audit`, `cargo audit`) for CVEs before builds. |
| **`extensions/desktop_features.py`**| `ThemeEngine` | 10 high-contrast themes: Cyberpunk, Tokyo Night, Dracula, Matrix, Nord, Monokai, Solarized, Gruvbox, Synthwave, Clean White. |
| **`extensions/desktop_features.py`**| `SnippetManager` | Parameterized reusable shell snippet templates (`<param>`). |
| **`extensions/desktop_features.py`**| `SessionNotebook` | Interactive execution scratchpad and markdown runbook logger. |
| **`extensions/plugin_system.py`** | `PluginManager` | Dynamic sandboxed plugin loader with manifest validation. |
| **`extensions/config_editor.py`** | `ConfigEditor` | Interactive TOML configuration wizard. |
| **`extensions/auto_docs.py`** | `MagicDocs` | Generates project architecture docs and context files on the fly. |
| **`extensions/session_recorder.py`**| `SessionRecorder` | Full terminal session recording and deterministic replay (`.cast`). |
| **`extensions/workspace_profiles.py`**| `WorkspaceManager` | Per-project environment variables, aliases, and safety rules. |

---

## 9. Desktop GUI Cockpit & REST API Server

### Desktop GUI Cockpit (`desktop_app.py`):
- **Framework**: CustomTkinter + Pillow with asynchronous thread dispatch.
- **Cockpit Dashboard**: Real-time CPU, RAM, GPU, active listening ports, and task monitor.
- **8 Extension Panels**: Security Scanner, Theme Picker, Snippet Manager, Session Notebook, Timeline, Audit Trail, API Control, Sync Hub.
- **Command Palette**: 28 interactive desktop actions.

### REST API Server (`server.py`):
- High-concurrency **FastAPI / Uvicorn** HTTP & WebSocket server.
- Endpoints:
  - `POST /api/v1/translate`: Translate natural language to shell command.
  - `POST /api/v1/execute`: Run command with safety shield and structured JSON output.
  - `GET /api/v1/health`: System health and memory telemetry.
  - `GET /api/v1/tasks`: Live task supervisor JSON status.

---

## 10. VS Code Extension (`vscode-extension/`)

- **1-Click Native Engine Downloader**: Live byte progress (`XX MB / YY MB %`) with stream-finish synchronization.
- **Automated Profile Injection**: Sets `NeuroShell` as default terminal in `terminal.integrated.profiles.windows/osx/linux`.
- **CodeLens & Context Menu**: "Ask AI", "Explain Selection", and "Fix Terminal Error".
- **Status Bar**: Interactive model switcher and IPC connection indicator.
- **Smart 6-Second Setup Loop**: Reminds uninstalled users every 6 seconds and stops permanently upon download.

---

## 11. Master Configuration Dictionary (`config.toml`)

```toml
# ==============================================================================
# NeuroShell Enterprise Configuration Specification v5.6.0
# ==============================================================================

[llm]
primary_provider = "groq"                  # groq, openai, anthropic, gemini, ollama, openrouter
primary_model = "llama-3.3-70b-versatile"
fallback_provider = "openai"
fallback_model = "gpt-4o-mini"
temperature = 0.1
request_timeout_seconds = 8.0
max_retries = 3

[safety]
enabled = true
block_destructive_patterns = true          # Intercepts fork bombs, rm -rf /, format
require_confirmation_for_caution = true    # Prompts on caution-level commands
max_file_impact_threshold = 100            # Alert if command touches >100 files
enable_semantic_audit = true               # AI-driven intent verification
enable_pii_scrubbing = true                # Redact keys/emails before sending to LLM

[ui]
theme = "cyberpunk"                        # cyberpunk, tokyo_night, dracula, matrix, nord...
show_banner = true
enable_ghost_text = true                   # Grey inline autocomplete predictions
enable_dlp_masking = true                  # Real-time Viewport Secret Redaction

[task_supervisor]
max_concurrent_workers = 16
enable_job_objects = true                  # Windows Job Object 0-zombie limit
default_restart_delay_ms = 500

[history]
retention_days = 90
enable_fts5_fulltext = true
database_path = "~/.neuroshell/history.db"

[resilience]
circuit_breaker_threshold = 5
circuit_breaker_cooldown_seconds = 30
rate_limit_requests_per_minute = 60
```

---

## 12. Complete Command, Prompt & Directive Dictionary

### A. 1-Word Productivity Shortcuts:
- **`ports`**: Scans and renders all active listening TCP ports, PIDs, and process names.
- **`specs`**: Telemetry for CPU cores, RAM usage, OS version, GPU model, and disk space.
- **`wifi`**: Lists all saved Wi-Fi SSID profiles and reveals passwords safely.
- **`tasks`**: Opens real-time background service dashboard.
- **`test`**: Auto-detects project ecosystem and runs parallel tests across all CPU cores.
- **`test changed`**: Runs unit tests only for files modified in git working directory.
- **`clean`**: Purges temporary caches (`node_modules/.cache`, `__pycache__`, `.pytest_cache`).
- **`stop all`**: Terminates all background processes and child workers with 0 zombies.

### B. Task Supervisor Directives:
- `start <svc1> and <svc2>`: Launches multiple services concurrently.
- `stop <name|id>`: Terminates a specific background worker.
- `restart <name|id>`: Restarts a specific background worker.

### C. AI Directives & Pipes:
- `<cmd> | @ai <query>`: Pipes command output to AI assistant.
- `<cmd> | @fix`: Auto-diagnoses compiler/runtime failure and suggests 1-click fix.
- `@agent <goal>`: Launches autonomous multi-step agent planner.
- `@explain <cmd>`: Deconstructs shell syntax into plain English.
- `@cluster <cmd>`: Broadcasts command across all open split panes.

### D. Navigation Shortcuts:
- `z <folder>`: Smart deep fuzzy directory jump.
- `..` / `...` / `....`: Jump 1, 2, or 3 folder levels up.
- `cd -`: Return to previous working directory.

### E. Slash Commands:
- `/help`: Opens Enterprise Command Reference directory.
- `/api-key`: Interactive AI provider configuration wizard.
- `/model`: Switches active language model or local Ollama.
- `/theme`: Selects terminal color theme.
- `/dlp`: Shows Viewport Secret Masking status.
- `/clear`: Clears screen and re-renders clean logo.
- `/exit`: Exits terminal and cleans up all background tasks.

### F. Hotkeys:
- `[F1]` / `[Ctrl+P]`: Command Palette.
- `[Ctrl+R]`: History Reverse Search.
- `[Ctrl+T]`: New Tab.
- `[Ctrl+W]`: Close Tab.
- `[Ctrl+U]`: Toggle DLP Secret Unmasking.
- `[Tab]`: Accept Autocomplete Prediction.
- `[Ctrl+C]`: Cancel foreground execution.
