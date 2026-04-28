# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Startup Banner
Styled ASCII art banner with system info, health summary, and tips.
"""

import os
import sys
import time
import platform


# ═══════════════════════════════════════════════════════════
# ASCII Art Banners (theme-aware)
# ═══════════════════════════════════════════════════════════

BANNER_DEFAULT = r"""
  _   _                      ____  _          _ _
 | \ | | ___ _   _ _ __ ___ / ___|| |__   ___| | |
 |  \| |/ _ \ | | | '__/ _ \\___ \| '_ \ / _ \ | |
 | |\  |  __/ |_| | | | (_) |___) | | | |  __/ | |
 |_| \_|\___|\__,_|_|  \___/|____/|_| |_|\___|_|_|
"""

BANNER_MINIMAL = r"""
  ╔═══════════════════════════╗
  ║    🧠 NeuroShell v5       ║
  ╚═══════════════════════════╝
"""

BANNER_CYBER = r"""
  ┌─────────────────────────────────────────┐
  │  ███╗   ██╗███████╗██╗   ██╗██████╗  ██████╗  │
  │  ████╗  ██║██╔════╝██║   ██║██╔══██╗██╔═══██╗ │
  │  ██╔██╗ ██║█████╗  ██║   ██║██████╔╝██║   ██║ │
  │  ██║╚██╗██║██╔══╝  ██║   ██║██╔══██╗██║   ██║ │
  │  ██║ ╚████║███████╗╚██████╔╝██║  ██║╚██████╔╝ │
  │  ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝  │
  │              SHELL   v5.0                       │
  └─────────────────────────────────────────┘
"""


def get_banner(theme: str = "default") -> str:
    """Get the ASCII banner for the given theme."""
    banners = {
        "cyberpunk": BANNER_CYBER,
        "matrix": BANNER_CYBER,
        "minimal": BANNER_MINIMAL,
    }
    return banners.get(theme, BANNER_DEFAULT)


def get_system_info(config) -> str:
    """Get formatted system info line."""
    model = config.llm.model
    shell = config.default_shell
    theme = config.ui.theme
    py_ver = platform.python_version()
    os_name = platform.system()

    parts = [
        f"🐍 Python {py_ver}",
        f"🖥️  {os_name}",
        f"🤖 {model}",
        f"💻 {shell}",
        f"🎨 {theme}",
    ]
    return "  " + "  │  ".join(parts)


def get_health_summary(config) -> str:
    """Get a quick health check summary."""
    lines = []

    # Check Ollama
    try:
        import ollama
        models = ollama.list()
        model_names = [m.get("name", "") for m in models.get("models", [])]
        has_model = any(config.llm.model in n for n in model_names)
        if has_model:
            lines.append("  ✅ Ollama: ready")
        else:
            lines.append(f"  ⚠️  Ollama: running but '{config.llm.model}' not found")
    except ImportError:
        lines.append("  ❌ Ollama: package not installed")
    except Exception:
        lines.append("  ❌ Ollama: not running")

    # Check safety
    safety = "on" if config.safety.enabled else "off"
    lines.append(f"  🛡️  Safety: {safety}")

    # Check NLP
    try:
        import sklearn
        lines.append("  🧠 NLP: available")
    except ImportError:
        lines.append("  ⚠️  NLP: sklearn not installed (basic mode)")

    return "\n".join(lines)


def get_tips() -> str:
    """Get random helpful tips."""
    tips = [
        '💡 Type natural language and I\'ll translate to shell commands',
        '💡 Type "fix" after an error to auto-fix it',
        '💡 Type "explain: <command>" to understand any command',
        '💡 Type "help" to see all features',
        '💡 Type "models" to switch LLM models',
        '💡 Type "stats" to see session statistics',
        '💡 Type "aliases" to see command shortcuts',
        '💡 Press F2 for the dashboard',
    ]
    index = int(time.time()) % len(tips)
    return f"\n  {tips[index]}"


def render_startup_banner(config, show_health: bool = True) -> str:
    """
    Render the full startup banner with system info and health.
    
    Returns a formatted string ready for display.
    """
    parts = []

    # Banner art
    parts.append(get_banner(config.ui.theme))

    # System info
    parts.append(get_system_info(config))

    # Health summary
    if show_health:
        parts.append("\n" + get_health_summary(config))

    # Tip
    parts.append(get_tips())

    # Separator
    parts.append("\n  " + "─" * 55)

    return "\n".join(parts)
