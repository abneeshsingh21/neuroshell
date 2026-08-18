# 🤖 NeuroShell — AI Agent Integration Guide

This guide explains how **Autonomous AI Coding Agents** (**Antigravity / Gemini, Claude Code, Cursor, Windsurf, Devin, OpenAI Operator, Cline, Roo Code**) configure and execute commands through **NeuroShell** as their default execution shell on Windows, macOS, and Linux.

---

## 📑 Table of Contents
1. [Why AI Agents Need NeuroShell](#1-why-ai-agents-need-neuroshell)
2. [Configuring NeuroShell as Default Shell for Agents](#2-configuring-neuroshell-as-default-shell-for-agents)
3. [Model Context Protocol (MCP) Integration](#3-model-context-protocol-mcp-integration)
4. [Non-Interactive CLI Flags & Structured JSON Output](#4-non-interactive-cli-flags--structured-json-output)
5. [Semantic Shell ANSI OSC 133 Protocol](#5-semantic-shell-ansi-osc-133-protocol)
6. [Standard Agent Rule Templates (AGENTS.md & CLAUDE.md)](#6-standard-agent-rule-templates-agentsmd--claudemd)

---

## 1. Why AI Agents Need NeuroShell

When AI agents execute shell commands in standard PowerShell or Bash, they suffer from 4 major failure modes:
1. **Orphaned Zombie Processes**: When an agent cancels a background dev server, child processes stay alive and lock ports (e.g. port 3000 stays blocked).
2. **Cryptic Unparsed Output**: Raw ANSI escape codes, terminal clear sequences, and carriage returns clutter context windows and waste LLM tokens.
3. **Cross-Platform Syntax Divergence**: Agents frequently hallucinate Unix commands on Windows (`rm -rf` instead of `rmdir /s /q`) or PowerShell cmdlets on Linux.
4. **Destructive Command Risks**: Hallucinated file deletions execute without warning.

**NeuroShell solves all 4 problems natively**:
- **Guaranteed 0 Zombies**: Win32 Job Objects & POSIX PGIDs terminate all child subprocesses cleanly.
- **Cross-Platform Unified Syntax**: Standard commands work identically across Windows, macOS, and Linux.
- **4-Layer Zero-Trust Safety Shield**: Intercepts dangerous operations before they touch the disk.
- **Semantic OSC 133 Protocol**: Emits deterministic exit codes and structured output.

---

## 2. Configuring NeuroShell as Default Shell for Agents

### A. VS Code, Cursor & Windsurf Agents
Add to your global or workspace `.vscode/settings.json`:

```json
{
  "terminal.integrated.defaultProfile.windows": "NeuroShell",
  "terminal.integrated.defaultProfile.osx": "NeuroShell",
  "terminal.integrated.defaultProfile.linux": "NeuroShell",
  "terminal.integrated.profiles.windows": {
    "NeuroShell": {
      "path": "${env:LOCALAPPDATA}\\Programs\\NeuroShell\\NeuroShell.exe",
      "args": [],
      "icon": "terminal"
    }
  },
  "terminal.integrated.profiles.osx": {
    "NeuroShell": {
      "path": "/usr/local/bin/neuroshell",
      "args": [],
      "icon": "terminal"
    }
  },
  "terminal.integrated.profiles.linux": {
    "NeuroShell": {
      "path": "/usr/local/bin/neuroshell",
      "args": [],
      "icon": "terminal"
    }
  }
}
```

---

### B. CLI Autonomous Agents (Claude Code, Antigravity, Devin, Aider)
Configure the agent's runner environment:

```bash
# Unix (macOS / Linux)
export SHELL=/usr/local/bin/neuroshell

# Windows
$env:SHELL = "$env:LOCALAPPDATA\Programs\NeuroShell\NeuroShell.exe"
$env:COMSPEC = "$env:LOCALAPPDATA\Programs\NeuroShell\NeuroShell.exe"
```

---

## 3. Model Context Protocol (MCP) Integration

NeuroShell exposes a high-concurrency **Model Context Protocol (MCP)** server. Connect your Claude Desktop, Cursor, or OpenHands agent to `neuroshell --mcp-server`:

### `mcp.json` / `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "neuroshell": {
      "command": "neuroshell",
      "args": ["--mcp-server"]
    }
  }
}
```

### Available MCP Tools:
- **`neuroshell_execute`**: Run commands with real-time safety validation and 0-zombie supervision.
- **`neuroshell_tasks`**: Query running background workers, CPU/RAM stats, and terminate services.
- **`neuroshell_test`**: Run parallel tests across all CPU cores or run tests only for git modified files.
- **`neuroshell_diagnose`**: Pass terminal errors to receive auto-fix commands.

---

## 4. Non-Interactive CLI Flags & Structured JSON Output

AI agents can execute commands non-interactively using `-c` or `--json`:

### Non-Interactive Command Execution:
```bash
neuroshell -c "start frontend and backend"
neuroshell -c "test changed"
neuroshell -c "ports"
```

### Deterministic JSON Output (`--json`):
```bash
neuroshell --json "ports"
```

**Returns:**
```json
{
  "status": "success",
  "exit_code": 0,
  "execution_time_ms": 12,
  "data": [
    { "pid": 14208, "port": 3000, "service": "node.exe", "state": "LISTENING" },
    { "pid": 28412, "port": 8000, "service": "python.exe", "state": "LISTENING" }
  ]
}
```

---

## 5. Semantic Shell ANSI OSC 133 Protocol

NeuroShell emits standard **OSC 133 Semantic Escape Sequences**:
- `\033]133;A\007` $\rightarrow$ Start of Prompt
- `\033]133;B\007` $\rightarrow$ Command Execution Triggered
- `\033]133;C\007` $\rightarrow$ Command Output Begins
- `\033]133;D;<exit_code>\007` $\rightarrow$ Command Terminated with exact Exit Code

This enables AI agents to **split stdout from prompts with 100% mathematical precision** without relying on brittle regex matching.

---

## 6. Standard Agent Rule Templates (AGENTS.md & CLAUDE.md)

Place an `AGENTS.md` or `CLAUDE.md` in the root of your project to instruct all AI models to use NeuroShell shortcuts:

```markdown
# AGENTS.md — Terminal Execution Policy

## Primary Shell Runtime: NeuroShell
Always run terminal commands through `neuroshell` instead of raw PowerShell/Bash.

### Conversational Syntax & Shortcuts:
- Start services in parallel: `start frontend and backend` (or `run dev and api`)
- View background workers: `tasks`
- Stop specific worker: `stop frontend` or `stop backend`
- Run parallel test suite: `test`
- Run tests only for modified files: `test changed`
- Inspect listening ports: `ports`
- Safe command execution: `neuroshell -c "<cmd>"`
```
