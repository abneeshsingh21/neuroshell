# 📖 NeuroShell — Complete User Guide

Welcome to **NeuroShell**, the world's most advanced AI-powered intelligent terminal. NeuroShell bridges the gap between human language and low-level system commands, giving developers, system administrators, DevOps engineers, and students a blazing-fast, safe, and conversational command-line experience.

---

## 📑 Table of Contents
1. [What is NeuroShell?](#-what-is-neuroshell)
2. [Why NeuroShell? (The Problems It Solves)](#-why-neuroshell-the-problems-it-solves)
3. [How to Install & Launch](#-how-to-install--launch)
4. [Your First 5 Minutes with NeuroShell](#-your-first-5-minutes-with-neuroshell)
5. [Core Concepts in Simple Words](#-core-concepts-in-simple-words)
6. [Everyday Developer Workflows](#-everyday-developer-workflows)
7. [Visual Keyboard Shortcuts & Hotkeys](#-visual-keyboard-shortcuts--hotkeys)

---

## 🌟 What is NeuroShell?

In traditional terminals (**Command Prompt, PowerShell, Bash, Zsh**), you must memorize hundreds of obscure flags and commands (e.g. `tar -xvf`, `netstat -ano | findstr :8080`, `lsof -i :8080`, `git log --graph --oneline`). If you make a typo or get the syntax wrong, the terminal gives you a cryptic error message or worse—accidentally deletes files.

**NeuroShell replaces that complexity with natural intelligence**:
- **You talk in plain English**: Type `"kill whatever is running on port 3000"` or `"create a postgres container with password secret"`, and NeuroShell instantly understands and runs the exact command.
- **It is natively fast**: Built in **C++20**, NeuroShell boots in under **5 milliseconds** with 0ms keystroke latency.
- **It guards your computer**: Every command passes through a **4-Layer Zero-Trust Safety Shield** that intercepts destructive operations before they touch your disk.
- **It runs full-stack workflows**: Run frontend and backend concurrently in 1 command (`start frontend and backend`) with 0 orphaned zombie processes.

```
  ⌬ NeuroShell
  Type plain English or press [F1] for Command Palette • /help for commands

⌬ C:\Users\dev\my-project ❯ find all large mp4 files and sort by size
  [AI:Groq] ❯ Get-ChildItem -Path . -Filter *.mp4 -Recurse | Sort-Object Length -Descending
  Running command...
```

---

## 🎯 Why NeuroShell? (The Problems It Solves)

| Traditional Shells (PowerShell / Bash) | NeuroShell v5.6.0 |
| :--- | :--- |
| ❌ You must memorize hundreds of flags and syntax rules | ✅ Translates any natural English sentence to exact shell commands |
| ❌ Cryptic stack traces when commands fail | ✅ Automatic root-cause diagnostics with 1-click `@fix` auto-repair |
| ❌ Accidental destructive commands (`rm -rf`, `del *`) execute instantly | ✅ 4-Layer Safety Shield warns you of danger and file blast-radius |
| ❌ Multi-service processes hang and leave ports locked (zombies) | ✅ Multi-process Task Supervisor with guaranteed 0-zombie cleanup |
| ❌ Different commands on Windows, Mac, and Linux (`dir` vs `ls`, `type` vs `cat`) | ✅ Universal cross-platform syntax across Windows, macOS, and Linux |
| ❌ API keys and passwords accidentally leaked on terminal screen | ✅ Real-time Viewport DLP automatically masks passwords and tokens |

---

## 🚀 How to Install & Launch

### 🪟 Windows Users
- **1-Click Installer**: Download and run [**`NeuroShell-Setup-x64.msi`**](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/NeuroShell-windows-x64-5.6.0.msi).
- **1-Line PowerShell**:
  ```powershell
  irm https://raw.githubusercontent.com/abneeshsingh21/neuroshell/main/scripts/install.ps1 | iex
  ```
- **Standalone `.exe`**: Download [**`NeuroShell.exe`**](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/NeuroShell.exe) and double-click to run!

---

### 🍎 macOS Users (Apple Silicon M1/M2/M3/M4 & Intel)
- **1-Line Terminal**:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/abneeshsingh21/neuroshell/main/scripts/install.sh | bash
  ```
- **Homebrew**:
  ```bash
  brew tap abneeshsingh21/neuroshell && brew install neuroshell
  ```

---

### 🐧 Linux Users (Ubuntu, Debian, Fedora, Arch, WSL2)
- **1-Line Shell**:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/abneeshsingh21/neuroshell/main/scripts/install.sh | bash
  ```
- **Python / Pip**:
  ```bash
  pip install neuroshell && neuroshell
  ```

---

### 💻 Inside VS Code / Cursor / Windsurf
1. Install [`neuroshell-vscode-5.6.0.vsix`](https://github.com/abneeshsingh21/neuroshell/releases/latest/download/neuroshell-vscode-5.6.0.vsix).
2. Click **`⚡ Download & Setup NeuroShell`** in the notification popup.
3. NeuroShell automatically becomes your default integrated terminal!

---

## ⏱️ Your First 5 Minutes with NeuroShell

### 1. Launch the App
Open NeuroShell. You will be greeted by the minimalist header:
```
  ⌬ NeuroShell
  Type plain English or press [F1] for Command Palette • /help for commands

⌬ C:\Users\dev\projects ❯
```

### 2. Try Natural Language
Type plain English just like talking to a teammate:
```bash
show me all git commits from yesterday
```
NeuroShell will translate it to `git log --since="yesterday"` and execute it immediately.

### 3. Try 1-Word Shortcuts
```bash
ports      # Instantly lists all active listening TCP ports & PID owners
specs      # Shows your CPU, RAM, OS, and GPU hardware stats
wifi       # Lists all saved Wi-Fi networks and passwords
test       # Auto-detects project language and runs tests across all CPU cores
```

### 4. Configure Your AI Provider
Type:
```bash
/api-key
```
Select your preferred provider (**Groq [Free/Fast]**, **OpenAI**, **Claude**, **Gemini**, or **Local Ollama**) and paste your API key. (Keys are encrypted locally with Fernet AES-128).

---

## 🧠 Core Concepts in Simple Words

### 1. Dual-Engine Intelligence (C++ + Python)
NeuroShell combines **two engines working together**:
1. **The Native C++20 Host**: Handles the keyboard, terminal rendering, ANSI colors, process pipes, and hotkeys in sub-millisecond C++ speed.
2. **The Background AI Daemon**: Connects to LLMs (Groq, OpenAI, Ollama) and analyzes queries without freezing the user interface.

### 2. The 4-Layer Zero-Trust Safety Shield
Before any generated command runs on your machine, it is inspected by 4 security layers:
- **Layer 1: Regex & Pattern Matcher** — Blocks dangerous commands (`rm -rf /`, `format c:`, fork bombs).
- **Layer 2: Pipe Chain Analyzer** — Checks redirected output and sub-shells.
- **Layer 3: Filesystem Scope Auditor** — Calculates how many files will be modified or deleted.
- **Layer 4: AI Semantic Audit** — Evaluates intent and alerts you if a command carries high risk.

### 3. Multi-Process Task Supervisor
When building modern apps (React + FastAPI, Next.js + Go, Vue + Django), you usually need multiple terminal windows.
In NeuroShell, you simply write:
```bash
start frontend and backend
```
Both services boot concurrently in the background. Type `tasks` to view CPU/RAM usage, `stop frontend` to stop one service, or `stop all` to shut everything down cleanly.

---

## 💼 Everyday Developer Workflows

### 1. The Full-Stack Web Developer
```bash
# Jump straight into project folder
z my-app

# Run frontend and backend concurrently
start npm run dev and python -m uvicorn main:app --reload

# Check task dashboard
tasks

# Run tests across modified files only
test changed

# Stop backend only to restart it
restart backend
```

### 2. The DevOps & Cloud Engineer
```bash
# Natural language Docker & Kubernetes
build docker image tagged my-service:v2
run docker container mapping port 80 to 8080 in background
show logs for pod auth-service with follow

# Network & Server diagnostics
ports
show top 5 memory consuming processes
```

### 3. The Git Power User
```bash
undo my last commit but keep the files
stash everything including untracked files
create and checkout branch feature/user-auth
show visual branch history graph
```

---

## ⌨️ Visual Keyboard Shortcuts & Hotkeys

| Hotkey | Action | Description |
| :--- | :--- | :--- |
| **`[F1]`** / **`[Ctrl+P]`** | **Command Palette** | Interactive searchable menu of all 50+ actions |
| **`[Ctrl+R]`** | **History Fuzzy Search** | Search past executed commands interactively |
| **`[Ctrl+T]`** | **New Tab** | Open a new terminal tab in current folder |
| **`[Ctrl+W]`** | **Close Tab** | Close active terminal tab |
| **`[Ctrl+U]`** | **Toggle DLP Masking** | Temporarily unmask/reveal sensitive tokens |
| **`[Tab]`** | **Accept Autocomplete** | Accept grey ghost-text prediction |
| **`[Ctrl+C]`** | **Cancel / Interrupt** | Cancel current running command or prompt |
