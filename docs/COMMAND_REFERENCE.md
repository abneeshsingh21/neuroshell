# 📚 NeuroShell — Complete Command & Syntax Reference Manual

This document is the exhaustive reference manual for all built-in commands, natural language queries, 1-word shortcuts, task supervisor controls, AI directives, and keyboard shortcuts in **NeuroShell v5.6.0**.

---

## 📑 Table of Contents
1. [Natural Language Translation Prompts](#1-natural-language-translation-prompts)
2. [1-Word Productivity Shortcuts](#2-1-word-productivity-shortcuts)
3. [Multi-Process Task Supervisor Syntax](#3-multi-process-task-supervisor-syntax)
4. [Polyglot Parallel Test Orchestrator](#4-polyglot-parallel-test-orchestrator)
5. [AI Directives & Output Pipes](#5-ai-directives--output-pipes)
6. [Intelligent Navigation & Jumper](#6-intelligent-navigation--jumper)
7. [Slash Commands & Configuration](#7-slash-commands--configuration)
8. [Hotkeys & Keybindings](#8-hotkeys--keybindings)

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

---

## 3. Remote Repository & Document Intelligence

NeuroShell provides zero-clone exploration, reading, auditing, and management of any local document or remote GitHub repository worldwide (your own or anyone else's public repositories):

```
  ╭────┬──────────────────────────────────────┬────────────┬────────────┬──────────────────────────────────────────╮
  │  # │ REPOSITORY                           │ VISIBILITY │ UPDATED    │ DESCRIPTION                              │
  ├────┼──────────────────────────────────────┼────────────┼────────────┼──────────────────────────────────────────┤
  │  1 │ abneeshsingh21/neuroshell            │ public     │ 2026-08-18 │ AI-Powered Intelligent Terminal Host     │
  │  2 │ abneeshsingh21/ira-voice-assistant   │ private    │ 2026-08-16 │ Voice assistant daemon                   │
  │  3 │ abneeshsingh21/epl-website           │ public     │ 2026-07-20 │ Official website for EPL                 │
  ╰────┴──────────────────────────────────────┴────────────┴────────────┴──────────────────────────────────────────╯
```

### Numbered Interactive Commands
After running `repos` or `repos <user|org>`, all repositories are indexed in memory:

| Command | Syntax | What It Does |
| :--- | :--- | :--- |
| **`repos`** | `repos` or `my repos` | Lists your own GitHub repositories with index numbers |
| **`repos <user\|org>`** | `repos vercel` / `repos google` | Lists public repositories from another developer or company |
| **`read <#\|target>`** | `read 1` / `read facebook/react` / `read README.md` | Reads local file or remote README in formatted markdown |
| **`audit <#\|target>`** | `audit 1` / `audit openai/whisper` / `audit .` | Scans for secret leaks, dependency CVEs, and security posture |
| **`tree <#\|target>`** | `tree 1` / `tree vercel/next.js` | Displays remote file and directory tree without cloning |
| **`clone <#\|target>`** | `clone 1` / `clone torvalds/linux` | Clones target repository to current directory |
| **`open <#\|target>`** | `open 1` / `open microsoft/vscode` | Opens repository in default web browser |

---
| **`tasks`** | Task Supervisor Dashboard | Opens real-time dashboard of background workers with CPU/RAM metrics |
| **`test`** | Parallel Test Suite | Auto-detects project language and runs all unit tests across all CPU cores |
| **`test changed`**| Git Impact Test Runner | Runs tests only for files modified in git working directory |
| **`clean`** | Cache Cleaner | Purges temporary artifacts (`node_modules/.cache`, `__pycache__`, `.pytest_cache`) |
| **`stop all`** | Global Teardown | Terminates all running background tasks and child processes with 0 zombies |

---

## 3. Multi-Process Task Supervisor Syntax

Start, manage, and supervise multiple services concurrently within a single terminal:

```bash
# Start 2 or more services concurrently in parallel:
start frontend and backend
run dev and api
start web, worker and redis

# Inspect live status and PID tree:
tasks

# Stop a single service by name or ID:
stop frontend
stop backend
kill 1

# Restart a single service:
restart backend
restart frontend

# Teardown everything cleanly:
stop all
```

---

## 4. Polyglot Parallel Test Orchestrator

NeuroShell detects project manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`) and runs parallel test runners:

```bash
# Auto-detect ecosystem and run test suite:
test

# Smart Git Impact Analysis (runs tests only for files touched in git):
test changed

# Polyglot repo filters (if project contains both Python backend & Node frontend):
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

## 6. Intelligent Navigation & Jumper

| Navigation Command | Description | Example |
| :--- | :--- | :--- |
| **`z <folder>`** | Smart Deep Jumper (Fuzzy Directory Jump) | `z neuro` $\rightarrow$ Jumps directly to `C:\Users\dev\projects\neuroshell` |
| **`..`** | Move 1 folder up | `cd ..` |
| **`...`** | Move 2 folders up | `cd ../..` |
| **`....`** | Move 3 folders up | `cd ../../..` |
| **`cd -`** | Return to previous directory | Jumps back to last working directory |

---

## 7. Slash Commands & Configuration

| Slash Command | Description | Action |
| :--- | :--- | :--- |
| **`/help`** or **`help`** | Enterprise Reference Directory | Displays categorized command reference box |
| **`/update`** or **`update`** | In-Place Self-Updater | Downloads and applies the latest release in 1-click |
| **`/api-key`** | Configure AI Providers | Interactive wizard to set Groq, OpenAI, Claude, Gemini API keys |
| **`/model`** | Model Switcher | Switch active language model (e.g. `llama-3.3-70b-versatile`, `gpt-4o`) |
| **`/theme`** | Theme Picker | Switch between 10 terminal color themes (Cyberpunk, Tokyo Night, Dracula, Matrix...) |
| **`/dlp`** | Secret Masking Status | View real-time Viewport DLP statistics and unmasked state |
| **`cls`** / **`clear`** | Clear Screen | Clears console viewport and reprints clean logo |
| **`exit`** / **`quit`** | Exit Terminal | Shuts down shell and all background workers cleanly |

---

## 8. Hotkeys & Keybindings

| Key Combo | Function | Description |
| :--- | :--- | :--- |
| **`[F1]`** / **`[Ctrl+P]`** | **Command Palette** | Interactive searchable overlay containing all features |
| **`[Ctrl+R]`** | **History Reverse Search** | Search past command history with fuzzy matching |
| **`[Ctrl+T]`** | **New Tab** | Create a new isolated terminal tab |
| **`[Ctrl+W]`** | **Close Tab** | Close currently active terminal tab |
| **`[Ctrl+U]`** | **Toggle DLP Mask** | Reveal / unmask sensitive tokens temporarily |
| **`[Tab]`** | **Autocomplete** | Accept grey ghost-text inline prediction |
| **`[Up]` / `[Down]`** | **History Traversal** | Cycle through previous executed commands |
| **`[Ctrl+C]`** | **Cancel Process** | Interrupt current foreground running task |
