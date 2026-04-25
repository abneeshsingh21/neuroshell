# NeuroShell Integration

This is the official VS Code and Antigravity IDE integration for **NeuroShell**. 

NeuroShell is an advanced, AI-powered hybrid terminal that utilizes local Ollama intelligence (or Groq cloud models) alongside a C++ native fuzzy-matching engine to translate natural language into powerful terminal commands instantly.

## Features
- **Seamless Injection**: Automatically configures the `terminal.integrated.defaultProfile` to launch NeuroShell when you open a terminal in VS Code or Antigravity IDE.
- **Privacy First**: NeuroShell scrubs all PII and secrets (like AWS keys and passwords) before any cloud transaction.
- **Offline Capable**: Functions autonomously using a local 2,500+ phrase TF-IDF dictionary and Ollama if the internet drops.

## Installation
1. Ensure the NeuroShell executable (or `python main.py` setup) is available on your system.
2. Install this extension.
3. Reload your IDE. NeuroShell will now be your default terminal.

## Configuration
You can configure the path to the executable in your VS Code `settings.json`:
```json
"neuroshell.executablePath": "NeuroShell"
```
*(If running from source, change this to the absolute path of your Python interpreter and `main.py`)*

## License
Proprietary - See [LICENSE](LICENSE) for details.
