# ⌬ NeuroShell for Visual Studio Code & Cursor
### **Enterprise Autonomous AI Terminal Integration**

[![Version](https://img.shields.io/badge/Version-v5.1.5-blue.svg)](package.json)
[![Publisher](https://img.shields.io/badge/Publisher-epl--lang-purple.svg)](https://marketplace.visualstudio.com/items?itemName=epl-lang.neuroshell-vscode)
[![Open VSX](https://img.shields.io/badge/Open%20VSX-v5.1.5-green.svg)](https://open-vsx.org/extension/epl-lang/neuroshell-vscode)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE.txt)
[![Package Size](https://img.shields.io/badge/Size-27%20KB-brightgreen.svg)](neuroshell-vscode-5.1.5.vsix)

Seamlessly integrates **NeuroShell** as your default integrated AI terminal in Visual Studio Code, Antigravity IDE, Cursor, and VSCodium with zero latency.

---

## ✨ Features

- **⚡ 1-Click Engine Downloader with Live Progress**: Automatically discovers or downloads the native C++20 engine from GitHub CDN with real-time download progress (`XX MB / YY MB %`).
- **🖥️ Native Terminal Profile Provider**: Injects **`⌬ NeuroShell`** directly into VS Code's integrated terminal dropdown (`+`).
- **🧠 Direct TypeScript IPC Client (`net.Socket`)**: Connects to Windows Named Pipes (`\\.\pipe\neuroshell_ipc`) and Unix Domain Sockets (`~/.neuroshell/ipc.sock`) for sub-millisecond translation without spawning sub-shells.
- **⌨️ AI Command QuickPick (`Ctrl+Alt+N` / `Cmd+Alt+N`)**: Translate any plain English prompt and execute or copy the generated command in seconds.
- **🔍 CodeLens & Context Menus**:
  - Right-click editor selection $\rightarrow$ *"NeuroShell: Explain Code / Command Selection"*.
  - Right-click terminal $\rightarrow$ *"NeuroShell: Explain & Fix Last Error"*.
- **📊 Status Bar Indicator**: Displays `$(terminal) ⌬ NeuroShell` in the bottom status bar with one-click access.

---

## 🚀 Getting Started

### 1. Installation
Install from the **VS Code Marketplace** or **Open VSX Registry**:
```bash
code --install-extension epl-lang.neuroshell-vscode
```

### 2. Launching NeuroShell Terminal
1. Open the Integrated Terminal panel (`Ctrl+\`` or ``Ctrl+Shift+` ``).
2. Click the **`+` dropdown** and select **`NeuroShell`**.
3. Type plain English (e.g. `open explorer`, `find all ts files`, `kill port 8080`) or pipe output directly (`cargo build 2>&1 | @fix`).

---

## ⌨️ Shortcuts & Commands

| Command | Keybinding | Action |
| :--- | :--- | :--- |
| `neuroshell.askAI` | `Ctrl+Alt+N` (`Cmd+Alt+N`) | Opens interactive AI prompt to translate natural language into shell commands |
| `neuroshell.explainSelection` | Right-Click Selection | Sends selected code/command to NeuroShell AI for instant explanation |
| `neuroshell.fixTerminalError` | Right-Click Terminal | Analyzes clipboard error output and provides 1-click auto-fix |
| `neuroshell.injectDefaultTerminal` | Command Palette | Sets NeuroShell as the default integrated terminal profile |
| `neuroshell.downloadEngine` | Command Palette | Downloads or updates the native NeuroShell engine |

---

## ⚙️ Extension Settings

| Setting | Default | Description |
| :--- | :--- | :--- |
| `neuroshell.executablePath` | `""` | Custom path to the `NeuroShell.exe` / `neuroshell` binary. If empty, auto-discovers. |
| `neuroshell.enableIPC` | `true` | Enables high-speed direct IPC communication with the NeuroShell daemon. |

---

## 📄 License & Terms

- **Founder & Lead Developer**: Abneesh Singh ([@abneeshsingh21](https://github.com/abneeshsingh21))
- **Publisher**: `epl-lang`
- **Copyright**: © 2024-2026 Abneesh Singh. All rights reserved.
- **License**: Licensed under the **Apache License, Version 2.0**. See [LICENSE.txt](LICENSE.txt) for details.
