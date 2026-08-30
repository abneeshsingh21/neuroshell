# 📚 NeuroShell — Complete Command & Syntax Reference Manual

This document is the exhaustive reference manual for all built-in commands, natural language queries, 1-word shortcuts, task supervisor controls, AI directives, and keyboard shortcuts in **NeuroShell v5.18.0**.

---

## 📑 Table of Contents
1. [Natural Language Translation Prompts](#1-natural-language-translation-prompts)
2. [1-Word Productivity Shortcuts](#2-1-word-productivity-shortcuts)
3. [Multi-Process Task Supervisor Syntax](#3-multi-process-task-supervisor-syntax)
4. [Polyglot Parallel Test Orchestrator](#4-polyglot-parallel-test-orchestrator)
5. [AI Directives & Output Pipes](#5-ai-directives--output-pipes)
6. [Universal Undo & Snapshot Controls](#6-universal-undo--snapshot-controls)
7. [Kernel-Level Sandboxing Controls](#7-kernel-level-sandboxing-controls)
8. [Remote SSH Execution (`nsh`)](#8-remote-ssh-execution-nsh)
9. [WASM Plugin Manager (`neuroshell-plugin`)](#9-wasm-plugin-manager-neuroshell-plugin)
10. [Model Context Protocol (MCP) Mode (`neuroshell-mcp`)](#10-model-context-protocol-mcp-mode-neuroshell-mcp)
11. [Intelligent Navigation & Jumper](#11-intelligent-navigation--jumper)
12. [Complete Slash Command Directory](#12-complete-slash-command-directory)
13. [Hotkeys & Keybindings](#13-hotkeys--keybindings)

---

## 1. Natural Language Translation Prompts

You can type commands in plain conversational English. NeuroShell uses its sub-millisecond offline phrase dictionary (2,550+ phrases) or your configured LLM (Groq, OpenAI, Ollama) to translate them.

### 📁 File & Directory Operations
| Natural Language Prompt | Target Generated Command |
| :--- | :--- |
| `find all large mp4 files and sort by size` | `Get-ChildItem -Filter *.mp4 -Recurse \| Sort Length -Desc` / `find . -name "*.mp4" -exec ls -lh {} +` |
| `count lines of code in python files` | `Get-ChildItem -Filter *.py -Recurse \| Get-Content \| Measure-Object -Line` |
| `delete all node_modules folders recursively` | `Get-ChildItem -Include node_modules -Recurse \| Remove-Item -Recurse -Force` |
| `create a folder called test and enter it` | `mkdir test && cd test` |
| `show total disk space free on drive c` | `Get-PSDrive C` / `df -h /` |
| `compress all pdf files into documents.zip` | `Compress-Archive -Path *.pdf -DestinationPath documents.zip` |

### 🌿 Git Operations
| Natural Language Prompt | Target Generated Command |
| :--- | :--- |
| `undo my last commit but keep changes` | `git reset --soft HEAD~1` |
| `show commits from the last 3 days` | `git log --since="3 days ago" --oneline` |
| `discard all local uncommitted changes` | `git restore . && git clean -fd` |
| `create and switch to branch feature/login`| `git checkout -b feature/login` |
| `show visual graph of all git branches` | `git log --graph --oneline --all --decorate` |
| `stash untracked files with message backup`| `git stash push -u -m "backup"` |

### 🐳 Docker & Container Management
| Natural Language Prompt | Target Generated Command |
| :--- | :--- |
| `run a postgres container with password secret` | `docker run -d --name pg -e POSTGRES_PASSWORD=secret -p 5432:5432 postgres` |
| `stop and remove all running containers` | `docker stop $(docker ps -q) && docker rm $(docker ps -aq)` |
| `show real-time memory and cpu of containers` | `docker stats` |
| `build docker image tagged myapp:latest` | `docker build -t myapp:latest .` |
| `clean up all dangling images and volumes` | `docker system prune -af --volumes` |

### 🌐 Network & Port Diagnostics
| Natural Language Prompt | Target Generated Command |
| :--- | :--- |
| `kill whatever process is on port 8080` | `Stop-Process -Id (Get-NetTCPConnection -LocalPort 8080).OwningProcess -Force` |
| `find my public and private ip address` | `curl -s ifconfig.me && ipconfig` |
| `test if google.com responds on port 443` | `Test-NetConnection -ComputerName google.com -Port 443` |
| `show active network connections` | `netstat -ano` |

---

## 2. 1-Word Productivity Shortcuts

NeuroShell includes ultra-fast, 1-word aliases for common everyday tasks:

| Shortcut | Description | Target Action |
| :--- | :--- | :--- |
| **`ports`** | Port Inspector | Scans and displays all active listening TCP ports, PIDs, and process names in a clean table |
| **`specs`** | Hardware Telemetry | Displays CPU cores, RAM usage, OS version, GPU model, and disk space |
| **`wifi`** | Wi-Fi Password Viewer | Lists all saved Wi-Fi SSID profiles and reveals passwords safely |
| **`repos`** | GitHub Repo Catalog | Displays your repositories in an enterprise-aligned box table with index numbers `1..N` |
| **`audit`** | Security Scanner | Runs a Zero-Trust secret leak, dependency CVE, and safety scan on current folder |
| **`undo`** | Filesystem Rollback | Restores modified or deleted files using the most recent pre-execution snapshot |

---

## 3. Multi-Process Task Supervisor Syntax

Manage background processes, daemons, and microservices with zero zombie leakage:

```bash
# Start background jobs:
npm run dev &
python -m uvicorn server:app &

# Inspect active workers:
jobs

# Stop a background task:
kill %1
```

---

## 4. Polyglot Parallel Test Orchestrator

NeuroShell detects project manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`) and runs parallel test runners:

```bash
# Auto-detect ecosystem and run test suite:
test

# Smart Git Impact Analysis (runs tests only for files touched in git):
test changed

# Polyglot repo filters:
test python       # Runs pytest / unittest
test node         # Runs npm test / vitest / jest
test rust         # Runs cargo test
test go           # Runs go test ./...
test java         # Runs mvn test / gradle test
```

---

## 5. AI Directives & Output Pipes

Pipe output from any command directly into AI models or trigger autonomous workflows:

### A. Pipe Command Output to AI (`| @ai <query>`)
```bash
# Ask AI to summarize git commit logs:
git log -n 10 --oneline | @ai summarize the major architectural changes in 3 bullets

# Analyze build errors:
npm run build | @ai what is causing the TypeScript compilation failure?

# Inspect JSON payloads:
curl -s https://api.github.com/users/octocat | @ai extract public repo count and bio
```

### B. Automatic Error Auto-Fixer (`| @fix`)
```bash
# Auto-diagnose and generate a 1-click fix command:
cargo build | @fix
python manage.py migrate | @fix
```

### C. Autonomous Multi-Step Agent Mode (`@agent <goal>`)
```bash
# Autonomous planner breaks the goal into verified safe steps:
@agent create a full-stack Next.js and FastAPI app with SQLite database
```

### D. Deep Command Explanation (`@explain <cmd>`)
```bash
@explain tar -czvf archive.tar.gz /var/log/
@explain awk -F: '{ print $1 }' /etc/passwd
```

### E. Cluster Command Broadcast (`@cluster <cmd>`)
```bash
# Broadcasts a command across all open split panes simultaneously:
@cluster git pull origin main
@cluster clear
```

---

## 6. Universal Undo & Snapshot Controls

NeuroShell automatically captures pre-execution CoW/reflink snapshots before running destructive commands:

```bash
# Roll back the most recent operation:
undo
# or via slash command:
/snapshots undo

# List all available snapshots:
/snapshots list

# Create a manual named snapshot:
/snapshots create "pre-refactor"
```

---

## 7. Kernel-Level Sandboxing Controls

Confinement enforcement using Linux Landlock LSM + seccomp-BPF filters:

```bash
# Set sandboxing mode:
/sandbox project      # Confines AI-translated commands only (default)
/sandbox strict       # Confines all non-interactive commands
/sandbox off          # Disables kernel sandboxing

# Run a command unconfined explicitly:
!sudo systemctl restart nginx
```

---

## 8. Remote SSH Execution (`nsh`)

Execute commands on remote systems with local safety verification and local DLP data scrubbing:

```bash
# Interactive remote REPL:
nsh user@hostname

# One-shot command execution:
nsh user@hostname "cat /etc/nginx/nginx.conf"

# Auto-approve CAUTION/DANGER commands:
nsh --yes user@hostname "docker restart web"
```

---

## 9. WASM Plugin Manager (`neuroshell-plugin`)

Run third-party WebAssembly/WASI plugins inside an isolated sandbox with zero ambient authority:

```bash
# Install a plugin with interactive consent:
neuroshell-plugin install ./formatter.wasm --yes

# List installed plugins:
neuroshell-plugin list

# Inspect granted permissions:
neuroshell-plugin info formatter

# Execute plugin:
neuroshell-plugin run formatter -- file.py

# Uninstall plugin:
neuroshell-plugin uninstall formatter
```

---

## 10. Model Context Protocol (MCP) Mode (`neuroshell-mcp`)

Run NeuroShell as an MCP-compliant JSON-RPC 2.0 tool server for AI agents (e.g. Claude Desktop, Cursor):

```bash
# Launch stdio server:
neuroshell-mcp

# Supported MCP Tools:
# - neuroshell_translate: Translates NL to shell commands
# - neuroshell_safety_check: Pre-execution risk assessment
# - neuroshell_execute: Runs command through 4-layer safety shield
# - neuroshell_undo: Rolls back recent file modifications
```

---

## 11. Intelligent Navigation & Jumper

| Navigation Command | Description | Example |
| :--- | :--- | :--- |
| **`z <folder>`** | Smart Deep Jumper (Fuzzy Directory Jump) | `z neuro` $\rightarrow$ Jumps directly to project folder |
| **`..`** | Move 1 folder up | `cd ..` |
| **`...`** | Move 2 folders up | `cd ../..` |
| **`....`** | Move 3 folders up | `cd ../../..` |
| **`cd -`** | Return to previous directory | Jumps back to last working directory |

---

## 12. Complete Slash Command Directory

| Slash Command | Description |
| :--- | :--- |
| **`/help`**, **`/?`** | Displays interactive categorized documentation |
| **`/api-key`** | Configure AI API keys (Groq, OpenAI, Gemini, Claude) |
| **`/model`** | Interactive LLM model switcher menu |
| **`/swarm`** | Orchestrates complex multi-agent goals across tools |
| **`/agent`** | Autonomous agent mode with step-by-step approval |
| **`/plan`** | Interactive planning mode |
| **`/undo`**, **`/snapshots`** | File rollback & snapshot management |
| **`/sandbox`** | Inspect & toggle Linux kernel sandboxing modes |
| **`/scan`**, **`/security`** | Zero-trust security, CVE & secret scanner |
| **`/theme`** | Interactive TrueColor color theme picker |
| **`/config`** | Show, set, save, or reset configuration keys |
| **`/profile`** | Switch workspace environment profiles |
| **`/plugins`** | Manage WASM and Python extensions |
| **`/dream`** | Trigger AutoDream memory consolidation |
| **`/backup`** | Encrypted config & session backup export |
| **`/record`** | Record terminal session stream for playback |
| **`/clip`** | Manage clipboard intelligence |
| **`/voice`** | Voice-to-command Whisper bridge |
| **`/git`** | Git operations dashboard |
| **`/notebook`** | Interactive command notebook & markdown exporter |
| **`/stats`** | Execution performance & token usage metrics |
| **`/update`** | In-place cryptographic self-updater |
| **`/clear`** | Clear console viewport |
| **`/exit`** | Clean shutdown of shell and child processes |

---

## 13. Hotkeys & Keybindings

| Key Combo | Function | Description |
| :--- | :--- | :--- |
| **`[F1]`** / **`[Ctrl+Shift+P]`** | **Command Palette** | Searchable overlay containing all commands & features |
| **`[Ctrl+R]`** | **Ranked History Search** | SQLite FTS5 frecency + CWD ranked history search modal |
| **`[Ctrl+T]`** | **New Tab** | Create a new isolated terminal tab |
| **`[Ctrl+W]`** | **Close Tab** | Close currently active terminal tab |
| **`[Up]` / `[Down]`** | **History Traversal** | Cycle through previous executed commands |
| **`[Ctrl+C]`** | **Cancel Process** | Interrupt current foreground running task |
