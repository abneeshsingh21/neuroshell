# 🧠 NeuroShell v5

> **Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.**
> **Proprietary Software — see LICENSE.txt for terms.**

**The Ultimate AI-Powered Intelligent Terminal** — Type English, get shell commands. Auto-fix errors. Works offline. Works with any LLM.

NeuroShell replaces your terminal with an AI brain that understands natural language, catches dangerous commands, auto-fixes errors, and learns from your patterns. Powered by a **C++ hybrid engine** for sub-microsecond performance with a **2,500+ phrase offline dictionary** for instant translation — even without any LLM.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🗣️ **Natural Language → Shell** | Type "show big files" → `find . -size +100M` |
| 🧠 **2,500+ Offline Phrases** | Instant English→Shell translation without any LLM or internet |
| ⚡ **C++ Hybrid Engine** | Native FastParser, FuzzyMatcher, MarkovEngine via pybind11 |
| 🔒 **Raw Shell Mode** | Full privacy — disables all LLM, telemetry, and cloud communication |
| 🛡️ **4-Layer Safety System** | Blocks `rm -rf /`, warns on destructive ops, LLM verification |
| 🔧 **Auto Error Fix** | 25+ offline patterns + cached fixes + LLM for complex errors |
| 🔐 **PII Scrubbing** | Auto-redacts API keys, passwords, tokens before cloud LLM calls |
| 📡 **Smart Offline Fallback** | Auto-pivots from cloud LLMs to local Ollama on network loss |
| 🌐 **Multi-LLM Support** | Ollama, Groq, OpenAI, Claude, Gemini, OpenRouter |
| 📖 **Command Explainer** | Offline database for 40+ commands with flags, risks, examples |
| 🎯 **Smart NLP** | TF-IDF intent classification, entity extraction |
| 🎨 **10 Built-in Themes** | Cyberpunk, Nord, Gruvbox, Catppuccin, Dracula, and more |
| ⚡ **Circuit Breaker** | Rate limiting, crash recovery, graceful degradation |
| 🔌 **Plugin System** | Extend with custom commands and integrations |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Ollama** (free, local LLM) — [Install Ollama](https://ollama.ai) *(optional with Raw Shell Mode)*

### Install

```bash
# Install dependencies
pip install -r requirements.txt

# (Optional) Pull a free local LLM model
ollama pull phi3:mini

# Launch NeuroShell
python main.py

# Or launch the Desktop GUI
python desktop_app.py
```

### Raw Shell Mode (No LLM Required)

```bash
# Set in config or environment
NEUROSHELL_RAW_SHELL=true python main.py
```

In this mode, NeuroShell operates with **zero API calls** and **zero internet** while still providing:
- 2,500+ English→Shell phrase translations (offline TF-IDF)
- C++ powered Ghost Text auto-suggestions
- Full syntax highlighting and theming
- Command safety system

---

## 🎮 Usage

```
🧠 NeuroShell v5.0 ❯ show me all python files modified today
  ⟶ find . -name "*.py" -mtime 0
  Confidence: 0.92 [LLM]
  Execute? [Y/n] y

🧠 NeuroShell v5.0 ❯ kill port 3000
  ⟶ lsof -ti:3000 | xargs kill -9
  Confidence: 0.98 [OFFLINE-DICTIONARY]
  Execute? [Y/n] y

🧠 NeuroShell v5.0 ❯ rm -rf /
  ⛔ BLOCKED — Catastrophic: recursive deletion of root filesystem
```

---

## 🏗️ Architecture

```
neuroshell/
├── main.py                   # Orchestrator — REPL, routing, signal handling
├── config.py                 # TOML config, env overrides, encrypted secrets
├── desktop_app.py            # CustomTkinter GUI with Mission Control HUD
├── setup.py                  # C++ extension build (pybind11)
├── cpp_engine/
│   ├── engine.cpp            # Native C++ — FastParser, FuzzyMatcher, MarkovEngine
│   ├── engine.py             # Python fallback implementation
│   ├── CMakeLists.txt        # CMake build configuration
│   └── __init__.py           # Graceful C++/Python fallback loader
├── intelligence/
│   ├── phrase_dictionary.py  # Offline NLP Fast-Dictionary engine (TF-IDF)
│   ├── _phrase_data.py       # 2,500+ English→Shell phrase mappings
│   ├── pii_scrubber.py       # Zero-Trust PII redaction filter
│   ├── offline_fallback.py   # Smart cloud→local LLM pivot
│   ├── update_checker.py     # GitHub release auto-update checker
│   ├── translator.py         # Multi-step NL → shell
│   ├── safety.py             # 4-layer safety analysis
│   ├── error_fixer.py        # 25+ offline patterns + LLM
│   └── autocomplete.py       # Fuzzy, weighted, git-aware
├── llm/
│   ├── client.py             # Streaming, retry, caching, multi-provider
│   └── prompts.py            # Few-shot, chain-of-thought prompts
├── nlp/
│   ├── intent_classifier.py  # TF-IDF + SVM, multi-intent
│   ├── entity_extractor.py   # Git, Docker, IP, ports, env vars
│   ├── embeddings.py         # Sentence-transformers + TF-IDF fallback
│   └── sentiment.py          # 7 states, adaptive suggestions
├── core/
│   ├── executor.py           # Process lifecycle, resource monitoring
│   ├── context.py            # Environment detection
│   └── history.py            # FTS5 search, analytics
├── ui/
│   ├── app.py                # Rich terminal UI
│   └── themes.py             # 10 themes
├── resilience/
│   └── resilience.py         # Circuit breaker, rate limiter
├── observability/
│   ├── logger.py             # Structured logging
│   └── tracer.py             # Correlation ID tracing
└── tests/                    # 85+ unit and integration tests
```

---

## ⚙️ Configuration

NeuroShell stores config in `~/.neuroshell/config.toml`:

```toml
[llm]
provider = "ollama"        # ollama, groq, openai, anthropic, gemini, openrouter
model = "phi3:mini"
temperature = 0.3
streaming = true

[safety]
enabled = true
confirm_destructive = true

[ui]
theme = "cyberpunk"

# Privacy mode — disables all LLM and cloud features
raw_shell_mode = false
```

### Supported LLM Providers

| Provider | Get API Key |
|----------|-------------|
| Ollama (local, free) | [ollama.ai](https://ollama.ai) |
| Groq | [console.groq.com/keys](https://console.groq.com/keys) |
| OpenAI | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| Anthropic Claude | [console.anthropic.com](https://console.anthropic.com) |
| Google Gemini | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| OpenRouter | [openrouter.ai/keys](https://openrouter.ai/keys) |

---

## 🧪 Testing

```bash
python -m pytest tests/ -v
```

---

## 🖥️ Desktop App

```bash
python desktop_app.py
```

Features: Mission Control HUD, multi-pane workspace, theme switcher, sparkline charts, command graph view.

---

## 📋 Commands

| Command | Action |
|---------|--------|
| Any English sentence | Translates to shell command |
| `fix` | Auto-fix last error |
| `explain: <command>` | Explain any command |
| `undo` | Rollback last destructive operation |
| `help [topic]` | Show help |
| `exit` / `quit` / `q` | Exit NeuroShell |

---

## 📬 Contact

- **Author:** Abneesh Singh
- **Email:** singhabneesh250@gmail.com
- **GitHub:** [github.com/abneeshsingh21](https://github.com/abneeshsingh21)

---

## 📘 Terms of Use

By using NeuroShell, you agree to the following:

1. You may use the application only as explicitly permitted by the copyright holder.
2. You may not copy, modify, decompile, reverse engineer, or create derivative works.
3. You may not redistribute, sublicense, resell, or republish the application or source code.
4. You may not remove or alter copyright, ownership, or attribution notices.
5. Commercial use, team-wide deployment, and redistribution require prior written permission.

For full legal terms, see LICENSE.txt.

---

## 📜 License

**Proprietary License** — All rights reserved. No permission is granted to use, copy, modify, distribute, sublicense, or create derivative works without explicit written consent from the copyright holder.

See [LICENSE.txt](LICENSE.txt) for full EULA terms.

## © Copyright

Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
