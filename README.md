<div align="center">

# ⌬ NeuroShell v5.18.0
### **The Tier-1 Enterprise Flagship AI Terminal**
*High-Performance Native C++20 Host • Sub-Millisecond JSON-RPC IPC • True ConPTY Fidelity • 4-Layer Zero-Trust Safety Shield • Multi-LLM Routing • Autonomous Agent Swarms*

[![Release](https://img.shields.io/badge/GitHub%20Release-v5.18.0-blue.svg?logo=github)](https://github.com/abneeshsingh21/neuroshell/releases/latest)
[![VS Code Marketplace](https://img.shields.io/badge/VS%20Code%20Extension-v5.18.0-blue.svg?logo=visual-studio-code)](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/neuroshell-vscode-5.18.0.vsix)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Tests Passing](https://img.shields.io/badge/Tests-481%20Passed%20(100%25)-brightgreen.svg)](tests/)

---

### 📦 Install with your package manager (sha256-pinned, verified channels)

| Platform | Package manager | One-liner |
| :--- | :--- | :--- |
| 🪟 **Windows** | **winget** | `winget install epl-lang.NeuroShell` |
| 🪟 **Windows** | **scoop** | `scoop bucket add neuroshell https://github.com/abneeshsingh21/neuroshell` → `scoop install neuroshell` |
| 🍎 **macOS** | **Homebrew** | `brew install https://raw.githubusercontent.com/abneeshsingh21/neuroshell/main/Formula/neuroshell.rb` |
| 🐧 **Arch** | **AUR** | `yay -S neuroshell` |
| 🐧 **Debian/Ubuntu** | **apt (.deb)** | download the pinned `.deb` from the [release assets](https://github.com/abneeshsingh21/neuroshell/releases) → `sudo apt install ./neuroshell_*.deb` |
| 🌍 **Any (Python)** | **pip** | `pip install neuroshell` |
| 💻 **VS Code / Cursor** | Marketplace | Search **`NeuroShell`** (publisher `epl-lang`) or `code --install-extension epl-lang.neuroshell-vscode` |

Every manifest above pins an **exact version + SHA-256** — no floating
`latest` downloads. See
**[docs/SUPPLY_CHAIN.md](docs/SUPPLY_CHAIN.md)** to verify a release before
running it: checksums, Ed25519-signed update manifest, SLSA v1 provenance,
and a CycloneDX SBOM ship with every release.

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
| **🐙 Remote Repo Intelligence** | Explore, read, and audit any GitHub repo worldwide without cloning. | `repos vercel`, `read 1`, `audit 1`, `tree 1` |
| **🤖 Autonomous Agent Swarms** | Multi-step task execution with step-by-step TUI approval cards. | `@agent "Setup PostgreSQL 16 docker-compose & run migrations"` |
| **🛡️ 4-Layer Zero-Trust Safety** | Blocks dangerous commands before execution with cryptographic logs. | Catches `rm -rf /`, fork bombs, unauthorized drops |
| **💻 ConPTY Console Fidelity** | 100% interactive terminal fidelity for full-screen applications. | `vim`, `nano`, `htop`, `fzf`, `tmux`, `ssh`, `docker exec -it` |
| **⌨️ Ghost-Text Autocomplete** | Real-time predictive inline suggestions from Markov learning. | Press `Right Arrow` or `Tab` to accept |
| **⚙️ Interactive Slash Menus** | TrueColor arrow-key configuration for models, keys, and themes. | `/model`, `/api-key`, `/theme`, `/update`, `/repos` |
| **🔌 Universal Extensions** | First-class integration in VS Code, Cursor, and native shells. | VS Code Extension (`28 KB`) + Zsh/Bash/Fish/PWSH hooks |

---

## 🚀 Installation & Setup

### ✅ Recommended — package managers (sha256-pinned)

Package-manager installs verify the artifact digest for you and track a
pinned release version — no piping network content into a shell.

#### 🪟 1. Windows
```powershell
winget install epl-lang.NeuroShell
# or with scoop:
scoop bucket add neuroshell https://github.com/abneeshsingh21/neuroshell
scoop install neuroshell
```

#### 🍎 2. macOS
```bash
brew install https://raw.githubusercontent.com/abneeshsingh21/neuroshell/main/Formula/neuroshell.rb
```

#### 🐧 3. Linux
```bash
# Arch (AUR):
yay -S neuroshell
# Debian/Ubuntu (pinned .deb from the release assets):
sudo apt install ./neuroshell_5.18.0_amd64.deb
# Any distro (Python package):
pip install neuroshell
```

#### 🧩 4. Visual Studio Code & Cursor Extension

1. Open VS Code or Cursor $\rightarrow$ Extensions tab (`Ctrl+Shift+X`).
2. Search for **`NeuroShell`** (Publisher: `epl-lang`) and click **Install**.
3. *Alternatively*, install via command line:
   ```bash
   code --install-extension epl-lang.neuroshell-vscode
   ```
4. **Auto-Installer**: If the native engine is not found, the extension will display a 1-click installer with a **live progress bar** (`XX MB / YY MB %`) that automatically configures NeuroShell as your default integrated terminal!

---

### 🔐 Verified install (standalone binaries)

If you install a standalone binary, verify it first — every release ships
with `checksums.txt`, an Ed25519-signed `manifest.json`, SLSA v1
`provenance.intoto.json`, and a CycloneDX SBOM. Full walkthrough:
**[docs/SUPPLY_CHAIN.md](docs/SUPPLY_CHAIN.md)**. The short version:

```bash
TAG=v5.18.0
BASE=https://github.com/abneeshsingh21/neuroshell/releases/download/$TAG
curl -fsSL -O "$BASE/checksums.txt" -O "$BASE/NeuroShell-linux-x86_64.tar.gz"
sha256sum -c checksums.txt --ignore-missing        # digest gate
tar -xzf NeuroShell-linux-x86_64.tar.gz && sudo ./install.sh
```

---

### ⚠️ Fallback — 1-line install scripts (not recommended)

> **These pipe remote content straight into a shell.** They predate the
> verified-install tooling above and are kept only as a documented fallback
> for automated environments. If you use them, use the checksum-verified
> variant shown here — never the blind `curl … | bash` form.

```bash
# POSIX — download, verify against the published checksums, THEN run:
curl -fsSL -O https://raw.githubusercontent.com/abneeshsingh21/neuroshell/main/scripts/install.sh
curl -fsSL -O https://github.com/abneeshsingh21/neuroshell/releases/latest/download/checksums.txt
# verify the installer itself is the published one before executing:
grep " install.sh" checksums.txt || echo "checksum entry missing — stop here"
shasum -a 256 -c --ignore-missing <(grep " install.sh" checksums.txt)
bash install.sh
```

```powershell
# Windows PowerShell fallback — download, verify, then run:
irm https://raw.githubusercontent.com/abneeshsingh21/neuroshell/main/scripts/install.ps1 `
  -OutFile install.ps1
# compare the hash against the published checksums before executing:
Get-FileHash install.ps1 -Algorithm SHA256
powershell -ExecutionPolicy Bypass -File install.ps1
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
