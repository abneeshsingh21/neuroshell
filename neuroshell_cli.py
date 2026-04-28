# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
#!/usr/bin/env python3
"""
NeuroShell CLI — Console Entry Point for VS Code Terminal Integration.

This is the console-mode launcher used by the VS Code extension to run
NeuroShell as an integrated terminal.  Unlike the GUI desktop_app.py
(which is built with console=False), this entry point keeps stdin/stdout
attached so VS Code can display the REPL output.

Usage:
    python neuroshell_cli.py          (development)
    NeuroShell-CLI.exe                (after PyInstaller build with console=True)
"""

import sys
import os

# ── Force UTF-8 on Windows BEFORE any other imports ──────────
# Without this, the default 'charmap' (cp1252) codec crashes on
# emoji and Unicode box-drawing characters used in the banner.
os.environ["PYTHONUTF8"] = "1"
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════
# Console-Based First-Run Wizard
# ═══════════════════════════════════════════════════════════

PROVIDERS = [
    {
        "id": "ollama",
        "name": "Ollama (Local, Free)",
        "desc": "Run LLMs locally. No API key needed.",
        "needs_key": False,
        "default_model": "phi3:mini",
        "default_url": "http://localhost:11434",
        "env_key": None,
    },
    {
        "id": "groq",
        "name": "Groq Cloud",
        "desc": "Ultra-fast cloud inference. Free tier available.",
        "needs_key": True,
        "default_model": "llama-3.3-70b-versatile",
        "default_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "desc": "GPT-4o and GPT-4o-mini models.",
        "needs_key": True,
        "default_model": "gpt-4o-mini",
        "default_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "desc": "Claude 4 Sonnet and Opus models.",
        "needs_key": True,
        "default_model": "claude-sonnet-4-20250514",
        "default_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "desc": "Gemini 2.5 Pro and Flash models.",
        "needs_key": True,
        "default_model": "gemini-2.5-flash",
        "default_url": "https://generativelanguage.googleapis.com/v1beta",
        "env_key": "GEMINI_API_KEY",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "desc": "Access 100+ models through one API.",
        "needs_key": True,
        "default_model": "meta-llama/llama-3.3-70b-instruct",
        "default_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
    },
]


def cli_first_run_wizard():
    """Console-based first-run wizard for terminal/VS Code users."""
    from config import CONFIG_FILE, Config

    if CONFIG_FILE.exists():
        return  # Already configured

    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║     🧠 Welcome to NeuroShell — First Setup   ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print("  Let's get you set up in 60 seconds.")
    print()
    print("  ─────────────────────────────────────────────")
    print("  Choose your mode:")
    print()
    print("  [1] 🤖 LLM Mode — AI-powered command translation")
    print("  [2] 🔒 Raw Shell Mode — No LLM, maximum privacy")
    print("       (Uses offline 2,500+ phrase dictionary)")
    print()

    while True:
        try:
            choice = input("  Enter choice (1 or 2): ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "2"
            break
        if choice in ("1", "2"):
            break
        print("  Please enter 1 or 2.")

    config = Config()

    if choice == "2":
        # Raw Shell Mode
        config.raw_shell_mode = True
        config.save()
        print()
        print("  ✅ Raw Shell Mode activated!")
        print("  You can change this later with: config set raw_shell_mode false")
        print()
        return

    # LLM Mode — choose provider
    print()
    print("  ─────────────────────────────────────────────")
    print("  Choose your LLM provider:")
    print()

    for i, prov in enumerate(PROVIDERS, 1):
        key_info = " (API key required)" if prov["needs_key"] else " (No key needed)"
        print(f"  [{i}] {prov['name']}{key_info}")
        print(f"      {prov['desc']}")
        print()

    while True:
        try:
            prov_choice = input(f"  Enter choice (1-{len(PROVIDERS)}): ").strip()
        except (EOFError, KeyboardInterrupt):
            prov_choice = "1"
            break
        if prov_choice.isdigit() and 1 <= int(prov_choice) <= len(PROVIDERS):
            break
        print(f"  Please enter a number between 1 and {len(PROVIDERS)}.")

    selected = PROVIDERS[int(prov_choice) - 1]
    config.llm.provider = selected["id"]
    config.llm.model = selected["default_model"]
    config.llm.base_url = selected["default_url"]

    # Ask for API key if needed
    if selected["needs_key"]:
        print()
        print(f"  ─────────────────────────────────────────────")
        print(f"  Enter your {selected['name']} API key:")
        print(f"  (Leave blank to set later with: setenv {selected['env_key']} <key>)")
        print()

        try:
            api_key = input("  API Key: ").strip()
        except (EOFError, KeyboardInterrupt):
            api_key = ""

        if api_key and selected.get("env_key"):
            config.set_secret(selected["env_key"], api_key)
            print(f"  ✅ API key saved securely (encrypted)")
        elif not api_key:
            print(f"  ⚠️  No key provided. Set it later with: setenv {selected['env_key']} <your-key>")

    config.save()

    print()
    print(f"  ✅ Setup complete!")
    print(f"     Provider: {selected['name']}")
    print(f"     Model: {selected['default_model']}")
    print(f"     Config: ~/.neuroshell/config.toml")
    print()
    print("  You can change settings anytime with the 'config' command.")
    print()


def main():
    """Launch the NeuroShell REPL."""
    try:
        # Run first-run wizard if needed (console version)
        cli_first_run_wizard()

        from main import NeuroShell
        shell = NeuroShell()
        shell.run()
    except KeyboardInterrupt:
        print("\n  NeuroShell session ended.")
        sys.exit(0)
    except Exception as e:
        print(f"\n  ❌ NeuroShell failed to start: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
