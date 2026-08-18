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

import os
import sys

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


def cli_first_run_wizard(force: bool = False):
    """Console-based first-run wizard for terminal/VS Code users.
    
    Triggers when:
    - config.toml doesn't exist (true first run)
    - --setup flag is passed (force reconfigure)
    - Config exists but no API key is set for a cloud provider
    """

    from config import CONFIG_FILE, SECRETS_FILE, Config

    if not force and CONFIG_FILE.exists():
        # Smart check: if using a cloud provider, verify API key exists
        try:
            import toml
            data = toml.load(CONFIG_FILE)
            provider = data.get("llm", {}).get("provider", "ollama")

            if provider == "ollama":
                return  # Ollama doesn't need API keys

            if data.get("raw_shell_mode", False):
                return  # Raw shell mode doesn't need keys

            # Check if API key exists in secrets or environment
            env_keys = {
                "groq": "GROQ_API_KEY",
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "gemini": "GEMINI_API_KEY",
                "openrouter": "OPENROUTER_API_KEY",
            }

            env_key = env_keys.get(provider)
            if env_key:
                # Check environment variable
                if os.environ.get(env_key):
                    return  # Key set in environment

                # Check secrets file
                if SECRETS_FILE.exists():
                    return  # Secrets exist (encrypted, can't check contents easily)

            return  # Default: trust the config

        except Exception:
            return  # If anything fails, don't block startup

    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║     🧠 NeuroShell — Setup Wizard             ║")
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
        print("  ─────────────────────────────────────────────")
        print(f"  Enter your {selected['name']} API key:")
        print(f"  (Leave blank to set later with: setenv {selected['env_key']} <key>)")
        print()

        try:
            api_key = input("  API Key: ").strip()
        except (EOFError, KeyboardInterrupt):
            api_key = ""

        if api_key and selected.get("env_key"):
            config.set_secret(selected["env_key"], api_key)
            print("  ✅ API key saved securely (encrypted)")
        elif not api_key:
            print(f"  ⚠️  No key provided. Set it later with: setenv {selected['env_key']} <your-key>")

    config.save()

    print()
    print("  ✅ Setup complete!")
    print(f"     Provider: {selected['name']}")
    print(f"     Model: {selected['default_model']}")
    print("     Config: ~/.neuroshell/config.toml")
    print()
    print("  You can reconfigure anytime with: neuroshell --setup")
    print()


def main():
    """Launch the NeuroShell REPL."""
    import argparse

    parser = argparse.ArgumentParser(description="NeuroShell CLI", add_help=False)
    parser.add_argument("--setup", action="store_true", help="Force run the setup wizard")
    parser.add_argument("--fast", action="store_true", help="Skip health checks for instant startup")
    parser.add_argument("--help", "-h", action="store_true", help="Show help")
    args, remaining = parser.parse_known_args()

    if args.help:
        print("NeuroShell CLI — AI-powered terminal")
        print()
        print("Usage:")
        print("  neuroshell_cli.py           Start NeuroShell REPL")
        print("  neuroshell_cli.py --setup   Run setup wizard")
        print("  neuroshell_cli.py --fast    Skip health checks (instant start)")
        print()
        return

    try:
        # Run setup wizard if requested or needed
        cli_first_run_wizard(force=args.setup)

        if args.setup:
            return  # Exit after setup

        # Set fast mode environment variable so main.py can skip health checks
        if args.fast:
            os.environ["NEUROSHELL_FAST_START"] = "1"

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

