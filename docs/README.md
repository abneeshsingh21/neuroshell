# 📚 NeuroShell Documentation Portal

Welcome to the **NeuroShell Official Documentation Hub**. Whether you are a beginner exploring natural language commands, a full-stack developer managing concurrent microservices, or an AI engineer connecting autonomous coding agents, this documentation suite covers every detail.

---

## 🧭 Documentation Map

```
                                  NEUROSHELL DOCUMENTATION
                                             │
      ┌──────────────────┬───────────────────┼───────────────────┬──────────────────┐
      ▼                  ▼                   ▼                   ▼                  ▼
📖 User Guide      📚 Command Ref      🏛️ Architecture     🤖 AI Agents       ⚙️ Config & FAQ
 (Getting Started)  (50+ Commands)      (Safety & IPC)      (MCP & Coding)     (TOML & Fixes)
```

| Document | Description | Target Audience |
| :--- | :--- | :--- |
| [**📖 User Guide**](USER_GUIDE.md) | Getting started, first 5 minutes, core concepts, installation, and developer workflows | Beginners, New Users, Developers |
| [**📚 Command & Syntax Reference**](COMMAND_REFERENCE.md) | Exhaustive directory of all 50+ commands, 1-word shortcuts, task supervisor, and AI pipes | All Users, Power Users |
| [**🏛️ Architecture & Safety Deep Dive**](ARCHITECTURE_AND_SAFETY.md) | C++20 ConPTY engine, 4-layer Zero-Trust Safety Shield, JSON-RPC IPC, and Viewport DLP | Architects, Security Teams |
| [**🤖 AI Agent Integration Guide**](AI_AGENT_INTEGRATION.md) | How Claude Code, Antigravity, ChatGPT, Cursor, and Windsurf use NeuroShell via MCP & OSC 133 | AI Developers, Agent Builders |
| [**⚙️ Configuration & Troubleshooting**](CONFIGURATION_AND_TROUBLESHOOTING.md) | `config.toml` reference, AI provider API keys, DLP rules, error diagnostics, and FAQ | SysAdmins, DevOps, Developers |

---

## ⚡ Quick Cheat Sheet

### Top 1-Word Shortcuts:
- **`ports`** — View active listening TCP ports and process owners.
- **`specs`** — Inspect CPU, RAM, OS, GPU, and disk hardware stats.
- **`wifi`** — Show saved Wi-Fi networks and passwords.
- **`test`** — Run parallel tests across all CPU cores.
- **`test changed`** — Run tests only for files touched in git.
- **`tasks`** — Open real-time background service dashboard.
- **`clean`** — Purge build caches and temporary files.

### Top Multi-Service Task Controls:
- `start frontend and backend` — Run both services concurrently in parallel.
- `stop frontend` — Terminate a specific worker.
- `restart backend` — Restart a specific worker.
- `stop all` — Terminate all background processes (0 zombies).

### Top Slash Commands:
- **`/help`** — Open enterprise command reference directory.
- **`/api-key`** — Configure Groq, OpenAI, Claude, Gemini API keys.
- **`/model`** — Switch active language model or connect to local Ollama.
- **`/theme`** — Switch between 10 terminal color themes.
- **`/dlp`** — Check Viewport DLP secret masking status.

---

## 📦 Commercial Graphical Installers:
- **Windows Setup Wizard**: [**`NeuroShell-windows-x64-5.6.0.msi`**](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/NeuroShell-windows-x64-5.6.0.msi)
- **macOS Universal**: [**`NeuroShell-macos-universal.tar.gz`**](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/NeuroShell-macos-universal.tar.gz)
- **Linux x86_64**: [**`NeuroShell-linux-x86_64.tar.gz`**](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/NeuroShell-linux-x86_64.tar.gz)
- **VS Code Extension**: [**`neuroshell-vscode-5.6.0.vsix`**](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/neuroshell-vscode-5.6.0.vsix)
