# ⚙️ NeuroShell — Configuration & Troubleshooting Guide

This guide covers **configuration options (`config.toml`)**, **AI provider setups**, **DLP secret masking rules**, **troubleshooting common errors**, and **frequently asked questions (FAQ)** for **NeuroShell v5.6.0**.

---

## 📑 Table of Contents
1. [Configuration File (`config.toml`)](#1-configuration-file-configtoml)
2. [Setting Up AI Providers](#2-setting-up-ai-providers)
3. [DLP Secret Masking Rules](#3-dlp-secret-masking-rules)
4. [Troubleshooting & Diagnostics](#4-troubleshooting--diagnostics)
5. [Frequently Asked Questions (FAQ)](#5-frequently-asked-questions-faq)

---

## 1. Configuration File (`config.toml`)

NeuroShell stores its settings in `~/.neuroshell/config.toml` (or `%USERPROFILE%\.neuroshell\config.toml` on Windows).

```toml
# NeuroShell v5.6.0 Configuration

[llm]
primary_provider = "groq"
primary_model = "llama-3.3-70b-versatile"
fallback_provider = "openai"
fallback_model = "gpt-4o-mini"
temperature = 0.1
request_timeout_seconds = 8.0

[safety]
enabled = true
block_destructive_patterns = true
require_confirmation_for_caution = true
max_file_impact_threshold = 100
enable_semantic_audit = true

[ui]
theme = "cyberpunk"           # Options: cyberpunk, tokyo_night, dracula, matrix, nord, monokai
show_banner = true
enable_ghost_text = true
enable_dlp_masking = true

[task_supervisor]
max_concurrent_workers = 16
enable_job_objects = true      # Windows Job Object 0-zombie guarantee
default_restart_delay_ms = 500

[history]
retention_days = 90
enable_fts5_fulltext = true
```

---

## 2. Setting Up AI Providers

You can configure your API keys interactively using `/api-key` in NeuroShell, or by setting standard environment variables:

### 1. Groq (Default / Ultra-Fast / Free Tier)
- **Get Key**: [console.groq.com](https://console.groq.com)
- **Terminal Command**: `/api-key` $\rightarrow$ Select `Groq` $\rightarrow$ Paste Key
- **Environment Variable**: `GROQ_API_KEY=gsk_...`

### 2. OpenAI
- **Get Key**: [platform.openai.com](https://platform.openai.com)
- **Terminal Command**: `/api-key` $\rightarrow$ Select `OpenAI` $\rightarrow$ Paste Key
- **Environment Variable**: `OPENAI_API_KEY=sk-proj-...`

### 3. Anthropic (Claude)
- **Get Key**: [console.anthropic.com](https://console.anthropic.com)
- **Terminal Command**: `/api-key` $\rightarrow$ Select `Anthropic` $\rightarrow$ Paste Key
- **Environment Variable**: `ANTHROPIC_API_KEY=sk-ant-...`

### 4. Google Gemini
- **Get Key**: [aistudio.google.com](https://aistudio.google.com)
- **Environment Variable**: `GEMINI_API_KEY=AIza...`

### 5. Local Ollama (100% Offline / Private)
1. Install Ollama: [ollama.com](https://ollama.com)
2. Pull a coding model:
   ```bash
   ollama pull qwen2.5-coder:7b
   ```
3. Switch NeuroShell to Ollama:
   ```bash
   /model
   ```
   Select `ollama:qwen2.5-coder:7b`. NeuroShell will now run completely offline with 0 internet traffic!

---

## 3. DLP Secret Masking Rules

NeuroShell's **Viewport Data Loss Prevention (DLP)** engine scans incoming stdout streams and masks sensitive patterns in real-time:

| Credential Type | Regex Pattern Sample | Masked Screen Rendering |
| :--- | :--- | :--- |
| **OpenAI Key** | `sk-proj-[A-Za-z0-9_-]{48,}` | `sk-proj-********************************` |
| **AWS Key** | `AKIA[0-9A-Z]{16}` | `AKIA****************` |
| **GitHub Token** | `ghp_[A-Za-z0-9]{36}` | `ghp_************************************` |
| **Generic Secret** | `password:\s*["'][^"']+["']` | `password: "********"` |

### Hotkey:
- Press **`[Ctrl+U]`** to toggle temporary reveal/unmasking.
- Check status anytime with **`/dlp`**.

---

## 4. Troubleshooting & Diagnostics

### Issue 1: "AI Translation Failed / Timeout"
- **Cause**: Network disconnection or invalid API key.
- **Solution**:
  1. Check your internet connection.
  2. Type `/api-key` to re-enter your key.
  3. Note: NeuroShell's **2,550+ offline phrases** will continue working even with no internet connection!

### Issue 2: "Port 8080 is already in use"
- **Quick Fix**: Simply type:
  ```bash
  ports
  kill 8080
  # OR
  kill whatever is on port 8080
  ```

### Issue 3: "Background tasks not stopping"
- **Quick Fix**: Run the global teardown shortcut:
  ```bash
  stop all
  ```
  NeuroShell's Win32 Job Object will terminate all child processes and free all locked ports immediately.

---

## 5. Frequently Asked Questions (FAQ)

### Q1: Does NeuroShell send my terminal commands to external servers?
**A**: No. NeuroShell only queries your configured AI provider when you type natural language or use `@ai`. Standard direct commands (`git`, `npm`, `cd`, `ls`) execute 100% locally on your machine with 0 telemetry. If you use **Ollama**, even natural language translation runs 100% locally and offline.

### Q2: How is NeuroShell different from GitHub Copilot CLI or Warp?
**A**:
1. **Zero-Trust Safety Shield**: Intercepts destructive commands before they execute.
2. **True Cross-Platform Engine**: Runs on Windows, macOS, and Linux with full ConPTY fidelity.
3. **Multi-Service Supervisor**: Start frontend and backend in 1 command with 0 zombie leaks.
4. **Offline Capability**: Works with local Ollama models and 2,550+ pre-trained offline phrases.

### Q3: How do I change the color theme?
**A**: Type `/theme` and choose between Cyberpunk, Tokyo Night, Dracula, Matrix, Nord, Monokai, and more!
