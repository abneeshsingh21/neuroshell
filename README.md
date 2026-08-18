<div align="center">

# ⌬ NeuroShell v5.6.0
### **The Tier-1 Enterprise Flagship AI Terminal**
*High-Performance Native C++20 Host • Sub-Millisecond JSON-RPC IPC • True ConPTY Fidelity • 4-Layer Zero-Trust Safety Shield • Multi-LLM Routing • Autonomous Agent Swarms*

[![Release](https://img.shields.io/badge/GitHub%20Release-v5.6.0-blue.svg?logo=github)](https://github.com/abneeshsingh21/neuroshell/releases/latest)
[![VS Code Marketplace](https://img.shields.io/badge/VS%20Code%20Extension-v5.6.0-blue.svg?logo=visual-studio-code)](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/neuroshell-vscode-5.6.0.vsix)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Tests Passing](https://img.shields.io/badge/Tests-481%20Passed%20(100%25)-brightgreen.svg)](tests/)

---

### 📦 1-Click Graphical Installers (Commercial Desktop Experience)

| Platform | 1-Click Graphical Installer | Portable / Command Line |
| :--- | :--- | :--- |
| 🪟 **Windows** | [**📥 Download Windows Setup Wizard (.msi)**](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/NeuroShell-windows-x64-5.6.0.msi) | [**`NeuroShell.exe` (Standalone)**](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/NeuroShell.exe) • `irm https://raw.githubusercontent.com/abneeshsingh21/neuroshell/main/scripts/install.ps1 \| iex` |
| 🍎 **macOS** | [**📥 Download macOS Universal Archive (.tar.gz)**](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/NeuroShell-macos-universal.tar.gz) | `curl -fsSL https://raw.githubusercontent.com/abneeshsingh21/neuroshell/main/scripts/install.sh \| bash` • `brew install neuroshell` |
| 🐧 **Linux** | [**📥 Download Linux x86_64 Archive (.tar.gz)**](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/NeuroShell-linux-x86_64.tar.gz) | `curl -fsSL https://raw.githubusercontent.com/abneeshsingh21/neuroshell/main/scripts/install.sh \| bash` • `pip install neuroshell` |
| 💻 **VS Code** | [**📥 Download VS Code Extension (.vsix)**](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/neuroshell-vscode-5.6.0.vsix) | 1-Click `⚡ Download & Setup NeuroShell` prompt |

---

</div>

## 🌟 Overview

**NeuroShell** is an industry-defining, enterprise-grade AI terminal uniting a high-performance **Native C++20 Terminal Host** with an intelligent **Python AI Daemon** over zero-latency IPC (Windows Named Pipes & POSIX Domain Sockets).

Whether you type in plain English, pipe live compiler errors into AI, orchestrate autonomous multi-step agent swarms, or run full-screen curses applications (`vim`, `htop`, `tmux`, `ssh`), NeuroShell delivers sub-millisecond responsiveness with 4-layer cryptographic safety validation.

---

## 🏛️ System Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        NEUROSHELL NATIVE C++20 TERMINAL HOST                           │
│  • True Windows ConPTY API (`CreatePseudoConsole`) & POSIX `openpty`/`forkpty`         │
│  • Raw Console VT100 Engine • Ghost-Text Predictions • Reverse History (Ctrl+R)        │
│  • Interactive Arrow-Key Menu GUI • Deep Jumper (`z <dir>`) • Multi-Tabs (Ctrl+T)      │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            │ High-Speed JSON-RPC 2.0 IPC
                                            │ Windows: \\.\pipe\neuroshell_ipc
                                            │ Unix:    ~/.neuroshell/ipc.sock
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        PYTHON INTELLIGENCE & SAFETY DAEMON                             │
├───────────────────────────┬────────────────────────────┬───────────────────────────────┤
│  🧠 Multi-LLM Router      │  🛡️ 4-Layer Safety Shield  │  🤖 Autonomous Swarm Planner  │
│  • Groq (LLaMA 3.3 70B)   │  1. AST & Pattern Regex    │  • Multi-step decomposition   │
│  • OpenAI (GPT-4o)        │  2. Pipeline Chain Guard   │  • Interactive step approval  │
│  • Anthropic (Claude 3.5) │  3. Filesystem Scope Audit │  • GitSandbox safe worktrees  │
│  • Google Gemini 1.5 Pro  │  4. Semantic LLM Audit     │  • Auto-rollback on failure   │
│  • Ollama (Local/Air-Gap) │  • SHA-256 SOC2 Hash Chain │                               │
├───────────────────────────┴────────────────────────────┴───────────────────────────────┤
│  ⚡ 2,554+ Enhanced Modern Offline Phrases (<0.5ms Instant Translation)                │
│  • Docker, K8s, Git, Systemd, Ollama, UV, Bun, PNPM, GitHub CLI (gh), Homebrew, Winget │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ Key Capabilities

| Capability | Description | Example / Shortcut |
| :--- | :--- | :--- |
| **🗣️ Plain English Translation** | Translates natural language into platform-specific commands. | `find all large mp4 files and sort by size` |
| **🌊 First-Class AI Pipings** | Pipe stdout/stderr directly into streaming LLM reasoning. | `pytest 2>&1 \| @fix` or `git diff \| @ai "write commit"` |
| **🤖 Autonomous Agent Swarms** | Multi-step task execution with step-by-step TUI approval cards. | `@agent "Setup PostgreSQL 16 docker-compose & run migrations"` |
| **🛡️ 4-Layer Zero-Trust Safety** | Blocks dangerous commands before execution with cryptographic logs. | Catches `rm -rf /`, fork bombs, unauthorized drops |
| **💻 ConPTY Console Fidelity** | 100% interactive terminal fidelity for full-screen applications. | `vim`, `nano`, `htop`, `fzf`, `tmux`, `ssh`, `docker exec -it` |
| **⌨️ Ghost-Text Autocomplete** | Real-time predictive inline suggestions from Markov learning. | Press `Right Arrow` or `Tab` to accept |
| **⚙️ Interactive Slash Menus** | TrueColor arrow-key configuration for models, keys, and themes. | `/model`, `/api-key`, `/theme`, `/health`, `/audit`, `?` |
| **🔌 Universal Extensions** | First-class integration in VS Code, Cursor, and native shells. | VS Code Extension (`26 KB`) + Zsh/Bash/Fish/PWSH hooks |

---

## 🚀 Installation & Setup

### 🪟 1. Windows Installation

#### Option A: Direct Executable (Easiest)
1. Download **[`NeuroShell.exe`](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/NeuroShell.exe)** from the latest release.
2. Double-click or run from any terminal:
   ```cmd
   NeuroShell.exe
   ```

#### Option B: Portable Zip
Download **[`NeuroShell-windows-x64.zip`](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/NeuroShell-windows-x64.zip)**, extract to any directory, and add to your system `PATH`.

---

### 🍎 2. macOS Installation (Apple Silicon & Intel)

#### Option A: Homebrew (Recommended)
```bash
brew tap abneeshsingh21/neuroshell https://github.com/abneeshsingh21/neuroshell
brew install neuroshell
```

#### Option B: 1-Line Universal Binary
```bash
curl -fsSL -O https://github.com/abneeshsingh21/neuroshell/releases/latest/download/NeuroShell-macos-universal.tar.gz
tar -xzf NeuroShell-macos-universal.tar.gz
sudo mv neuroshell /usr/local/bin/
```

---

### 🐧 3. Linux Installation (x86_64)

```bash
curl -fsSL -O https://github.com/abneeshsingh21/neuroshell/releases/latest/download/NeuroShell-linux-x86_64.tar.gz
tar -xzf NeuroShell-linux-x86_64.tar.gz
sudo mv neuroshell /usr/local/bin/
```

---

### 🧩 4. Visual Studio Code & Cursor Extension

1. Open VS Code or Cursor $\rightarrow$ Extensions tab (`Ctrl+Shift+X`).
2. Search for **`NeuroShell`** (Publisher: `epl-lang`) and click **Install**.
3. *Alternatively*, install via command line:
   ```bash
   code --install-extension epl-lang.neuroshell-vscode
   ```
4. **Auto-Installer**: If the native engine is not found, the extension will display a 1-click installer with a **live progress bar** (`XX MB / YY MB %`) that automatically configures NeuroShell as your default integrated terminal!

---

### 🐚 5. Native Shell Integration Hooks

If you prefer using your existing default shell (`zsh`, `bash`, `fish`, `powershell`) with inline NeuroShell AI translation:

- **macOS Zsh (`~/.zshrc`)**:
  ```bash
  source /path/to/neuroshell/integrations/neuroshell.zsh
  ```
  *(Press `Ctrl+Space` or `Alt+E` on any line to translate English to shell commands inline!)*
- **Linux Bash (`~/.bashrc`)**:
  ```bash
  source /path/to/neuroshell/integrations/neuroshell.bash
  ```
- **Fish Shell (`~/.config/fish/config.fish`)**:
  ```fish
  source /path/to/neuroshell/integrations/neuroshell.fish
  ```
- **PowerShell 7 / Windows Terminal (`$PROFILE`)**:
  ```powershell
  . "C:\path\to\neuroshell\integrations\neuroshell.ps1"
  ```
  *(Press `Alt+Space` to trigger instant AI translation)*

---

## 🎮 Interactive Usage Guide

### 1. Plain English Translation
Simply type what you want to achieve. Offline phrases execute in $<0.5\text{ms}$; complex tasks route to your active LLM:
```text
⌬ C:\workspace\app (main) ❯ convert all png files to webp with 85 quality
  ✔ Transformed → for %f in (*.png) do magick "%f" -quality 85 "%~nf.webp"
```

### 2. First-Class AI Command Pipings
Pipe real-time terminal output into AI directives:
```bash
# Analyze runtime log files
cat /var/log/nginx/error.log | @ai "explain the cause of 502 bad gateway"

# Automatically fix compiler or test failures
cargo build 2>&1 | @fix

# Generate commit messages from live diffs
git diff | @ai "write a conventional commit message"
```

### 3. Autonomous Multi-Agent Swarms
Let NeuroShell orchestrate complex, multi-step engineering tasks:
```text
⌬ C:\workspace (main) ❯ @agent "Setup PostgreSQL 16 docker-compose, configure .env, and run migrations"

  ╭── ⌬ Swarm Orchestration Plan (3 Steps) ─────────────────────────╮
  │ 1. [⬜ PENDING] Generate docker-compose.yml with postgres:16     │
  │    ❯ cat << 'EOF' > docker-compose.yml ...                      │
  │ 2. [⬜ PENDING] Start database container in detached mode       │
  │    ❯ docker compose up -d                                       │
  │ 3. [⬜ PENDING] Run database migrations                         │
  │    ❯ python manage.py migrate                                   │
  ╰──────────────────────────────────────────────────────────────────╯

  [y] Approve & Run   [n] Skip   [a] Auto-Approve All   [q] Abort:
```

### 4. Interactive Configuration & Help
- **`?` or `/help`**: Interactive TrueColor documentation directory.
- **`/model`**: Switch LLM providers with arrow keys (Groq, OpenAI, Anthropic, Gemini, OpenRouter, Ollama).
- **`/api-key`**: Encrypted credential manager using PBKDF2 + Fernet AES-128.
- **`/theme`**: Live theme picker (Cyberpunk Neon, Nord Frost, Dracula, Monokai, Synthwave, Solarized).

---

## 🛡️ Enterprise Security & SOC2 Compliance

- **Zero-Trust 4-Layer Safety Shield**:
  1. *Layer 1 (Regex AST)*: Blocks catastrophic operations (`rm -rf /`, fork bombs, volume format).
  2. *Layer 2 (Pipeline Chain Guard)*: Inspects dangerous piping and redirection targets.
  3. *Layer 3 (Scope Estimator)*: Evaluates file impact counts and disk space consequences.
  4. *Layer 4 (Semantic LLM Audit)*: Performs semantic intent verification for elevated actions.
- **Tamper-Evident Cryptographic Audit Logging**:
  All executions are chained via SHA-256 hashes in `~/.neuroshell/audit/audit_YYYY-MM-DD.jsonl`:
  $$\text{entry\_hash} = \text{SHA256}(\text{prev\_hash} : \text{timestamp} : \text{user} : \text{role} : \text{command} : \text{risk} : \text{action} : \text{cwd} : \text{exit\_code})$$
- **Automatic PII Scrubbing**: Strips passwords, authorization bearer tokens, API keys, and IP addresses before cloud LLM transmission.
- **Air-Gapped Privacy**: Works 100% offline with local Ollama or pure offline phrase dictionary ($2,554+$ patterns).

---

## 🧪 Test Suite & Verification

NeuroShell includes an extensive, multi-tier automated test suite covering core execution, intelligence routing, resilience circuit breakers, IPC protocols, and enterprise security:

```bash
pytest tests/ -v
```

```text
======================= 481 passed, 2 skipped in 32.89s (100% Pass Rate) =======================
```

---

## 📄 License & Terms

- **Founder & Lead Developer**: Abneesh Singh ([@abneeshsingh21](https://github.com/abneeshsingh21))
- **Copyright**: © 2024-2026 Abneesh Singh. All rights reserved.
- **License**: Licensed under the **Apache License, Version 2.0** (the "License"). You may obtain a copy of the License at [LICENSE](LICENSE) or [http://www.apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0).
