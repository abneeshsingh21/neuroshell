# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell First-Run Wizard & Settings GUI
Streamlined onboarding for new users to configure LLM providers and API keys.
Also provides a Settings panel accessible from the desktop app.
"""

import os
import sys
import webbrowser
import logging
from pathlib import Path

import customtkinter as ctk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config, NEUROSHELL_DIR, CONFIG_FILE

_log = logging.getLogger("neuroshell.wizard")

# ═══════════════════════════════════════════════════════════
# LLM Provider Registry
# ═══════════════════════════════════════════════════════════

PROVIDERS = [
    {
        "id": "ollama",
        "name": "Ollama (Local, Free)",
        "desc": "Run LLMs locally on your machine. No API key needed.",
        "url": "https://ollama.ai",
        "needs_key": False,
        "default_model": "phi3:mini",
        "default_url": "http://localhost:11434",
        "env_key": None,
    },
    {
        "id": "groq",
        "name": "Groq Cloud",
        "desc": "Ultra-fast cloud inference. Free tier available.",
        "url": "https://console.groq.com/keys",
        "needs_key": True,
        "default_model": "llama-3.3-70b-versatile",
        "default_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "desc": "GPT-4o and GPT-4o-mini models.",
        "url": "https://platform.openai.com/api-keys",
        "needs_key": True,
        "default_model": "gpt-4o-mini",
        "default_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "desc": "Claude 4 Sonnet and Opus models.",
        "url": "https://console.anthropic.com/settings/keys",
        "needs_key": True,
        "default_model": "claude-sonnet-4-20250514",
        "default_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "desc": "Gemini 2.5 Pro and Flash models.",
        "url": "https://aistudio.google.com/apikey",
        "needs_key": True,
        "default_model": "gemini-2.5-flash",
        "default_url": "https://generativelanguage.googleapis.com/v1beta",
        "env_key": "GEMINI_API_KEY",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "desc": "Access 100+ models through one API.",
        "url": "https://openrouter.ai/keys",
        "needs_key": True,
        "default_model": "meta-llama/llama-3.3-70b-instruct",
        "default_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
    },
]

# ═══════════════════════════════════════════════════════════
# Design Tokens
# ═══════════════════════════════════════════════════════════

WIZ_COLORS = {
    "bg": "#0a0f1a",
    "bg_card": "#111d2e",
    "bg_input": "#0d1a2a",
    "border": "#1c2f48",
    "accent": "#00d4ff",
    "accent_hover": "#00b8e6",
    "text": "#e8edf5",
    "text_dim": "#6b7a8d",
    "success": "#00ff88",
    "warning": "#ffaa00",
    "selected": "#162d50",
}


def needs_first_run() -> bool:
    """Check if the wizard should be shown."""
    return not CONFIG_FILE.exists()


# ═══════════════════════════════════════════════════════════
# First-Run Wizard Window
# ═══════════════════════════════════════════════════════════

class FirstRunWizard(ctk.CTkToplevel):
    """Multi-step onboarding wizard for new users."""

    def __init__(self, master=None, on_complete=None):
        super().__init__(master)
        self.title("🧠 NeuroShell — Setup Wizard")
        self.geometry("700x560")
        self.resizable(False, False)
        self.configure(fg_color=WIZ_COLORS["bg"])
        self._on_complete = on_complete
        self._selected_provider = None
        self._api_key_var = ctk.StringVar()
        self._raw_mode_var = ctk.BooleanVar(value=False)
        self._step = 0

        # Main container
        self._container = ctk.CTkFrame(self, fg_color="transparent")
        self._container.pack(fill="both", expand=True, padx=30, pady=20)

        self._show_step_welcome()

    def _clear(self):
        for w in self._container.winfo_children():
            w.destroy()

    # ── Step 1: Welcome ──
    def _show_step_welcome(self):
        self._clear()
        self._step = 0

        ctk.CTkLabel(
            self._container, text="🧠 Welcome to NeuroShell",
            font=("Segoe UI", 28, "bold"), text_color=WIZ_COLORS["accent"],
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            self._container,
            text="The Ultimate AI-Powered Terminal\nLet's get you set up in 60 seconds.",
            font=("Segoe UI", 14), text_color=WIZ_COLORS["text_dim"],
            justify="center",
        ).pack(pady=(0, 25))

        # Raw Shell Mode option
        raw_frame = ctk.CTkFrame(self._container, fg_color=WIZ_COLORS["bg_card"],
                                  corner_radius=10, border_width=1,
                                  border_color=WIZ_COLORS["border"])
        raw_frame.pack(fill="x", pady=10)

        ctk.CTkCheckBox(
            raw_frame, text="  Raw Shell Mode (No LLM — maximum privacy)",
            variable=self._raw_mode_var,
            font=("Segoe UI", 13), text_color=WIZ_COLORS["text"],
            fg_color=WIZ_COLORS["accent"], hover_color=WIZ_COLORS["accent_hover"],
        ).pack(padx=15, pady=12)

        ctk.CTkLabel(
            raw_frame,
            text="Uses the offline 2,500+ phrase dictionary. Zero internet required.",
            font=("Segoe UI", 11), text_color=WIZ_COLORS["text_dim"],
        ).pack(padx=15, pady=(0, 10))

        ctk.CTkButton(
            self._container, text="Continue →", font=("Segoe UI", 15, "bold"),
            fg_color=WIZ_COLORS["accent"], hover_color=WIZ_COLORS["accent_hover"],
            text_color="#000", height=42, corner_radius=8,
            command=self._on_welcome_next,
        ).pack(pady=(25, 0))

    def _on_welcome_next(self):
        if self._raw_mode_var.get():
            self._finish(raw_mode=True)
        else:
            self._show_step_provider()

    # ── Step 2: Choose Provider ──
    def _show_step_provider(self):
        self._clear()
        self._step = 1

        ctk.CTkLabel(
            self._container, text="Choose Your LLM Provider",
            font=("Segoe UI", 22, "bold"), text_color=WIZ_COLORS["text"],
        ).pack(pady=(10, 15))

        scroll = ctk.CTkScrollableFrame(
            self._container, fg_color="transparent", height=360,
        )
        scroll.pack(fill="both", expand=True)

        self._provider_buttons = []
        for prov in PROVIDERS:
            btn = ctk.CTkButton(
                scroll,
                text=f"  {prov['name']}\n  {prov['desc']}",
                font=("Segoe UI", 12), anchor="w", height=58,
                fg_color=WIZ_COLORS["bg_card"],
                hover_color=WIZ_COLORS["selected"],
                text_color=WIZ_COLORS["text"],
                border_width=1, border_color=WIZ_COLORS["border"],
                corner_radius=8,
                command=lambda p=prov: self._select_provider(p),
            )
            btn.pack(fill="x", pady=3)
            self._provider_buttons.append((btn, prov))

    def _select_provider(self, prov):
        self._selected_provider = prov
        if prov["needs_key"]:
            self._show_step_api_key()
        else:
            self._finish(provider=prov)

    # ── Step 3: API Key ──
    def _show_step_api_key(self):
        self._clear()
        self._step = 2
        prov = self._selected_provider

        ctk.CTkLabel(
            self._container, text=f"Configure {prov['name']}",
            font=("Segoe UI", 22, "bold"), text_color=WIZ_COLORS["text"],
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            self._container, text="Enter your API Key:",
            font=("Segoe UI", 13), text_color=WIZ_COLORS["text_dim"],
        ).pack(anchor="w", pady=(10, 3))

        ctk.CTkEntry(
            self._container, textvariable=self._api_key_var,
            font=("Consolas", 13), height=40, show="•",
            fg_color=WIZ_COLORS["bg_input"],
            border_color=WIZ_COLORS["border"],
            text_color=WIZ_COLORS["text"],
        ).pack(fill="x", pady=(0, 10))

        link_btn = ctk.CTkButton(
            self._container,
            text=f"🔗 Get API Key from {prov['name']}",
            font=("Segoe UI", 12),
            fg_color="transparent", hover_color=WIZ_COLORS["bg_card"],
            text_color=WIZ_COLORS["accent"],
            command=lambda: webbrowser.open(prov["url"]),
        )
        link_btn.pack(anchor="w", pady=5)

        btn_frame = ctk.CTkFrame(self._container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(20, 0))

        ctk.CTkButton(
            btn_frame, text="← Back", width=100,
            fg_color=WIZ_COLORS["bg_card"], hover_color=WIZ_COLORS["selected"],
            text_color=WIZ_COLORS["text"], corner_radius=8,
            command=self._show_step_provider,
        ).pack(side="left")

        ctk.CTkButton(
            btn_frame, text="Finish Setup ✓", width=160,
            font=("Segoe UI", 14, "bold"),
            fg_color=WIZ_COLORS["success"], hover_color="#00cc66",
            text_color="#000", corner_radius=8,
            command=lambda: self._finish(provider=prov, api_key=self._api_key_var.get()),
        ).pack(side="right")

    # ── Finish ──
    def _finish(self, raw_mode=False, provider=None, api_key=None):
        config = Config()
        config.raw_shell_mode = raw_mode

        if provider:
            config.llm.provider = provider["id"]
            config.llm.model = provider["default_model"]
            config.llm.base_url = provider["default_url"]

        if api_key and provider and provider.get("env_key"):
            config.set_secret(provider["env_key"], api_key)

        config.save()
        _log.info("First-run wizard completed: provider=%s raw=%s",
                   provider["id"] if provider else "none", raw_mode)

        if self._on_complete:
            self._on_complete(config)
        self.destroy()


# ═══════════════════════════════════════════════════════════
# Settings Panel (embeddable in desktop_app)
# ═══════════════════════════════════════════════════════════

class SettingsPanel(ctk.CTkToplevel):
    """In-app settings panel for runtime configuration."""

    def __init__(self, master, config: Config, on_save=None):
        super().__init__(master)
        self.title("⚙ NeuroShell Settings")
        self.geometry("600x500")
        self.configure(fg_color=WIZ_COLORS["bg"])
        self._config = config
        self._on_save = on_save

        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)

        # ── Provider ──
        self._add_section(container, "LLM Provider")
        self._provider_var = ctk.StringVar(value=config.llm.provider)
        ctk.CTkOptionMenu(
            container, variable=self._provider_var,
            values=[p["id"] for p in PROVIDERS],
            fg_color=WIZ_COLORS["bg_input"],
            button_color=WIZ_COLORS["accent"],
            text_color=WIZ_COLORS["text"],
        ).pack(fill="x", pady=5)

        # ── Model ──
        self._add_section(container, "Model Name")
        self._model_var = ctk.StringVar(value=config.llm.model)
        ctk.CTkEntry(
            container, textvariable=self._model_var,
            fg_color=WIZ_COLORS["bg_input"], text_color=WIZ_COLORS["text"],
        ).pack(fill="x", pady=5)

        # ── Theme ──
        self._add_section(container, "Theme")
        self._theme_var = ctk.StringVar(value=config.ui.theme)
        ctk.CTkOptionMenu(
            container, variable=self._theme_var,
            values=["cyberpunk", "dracula", "nord", "gruvbox", "catppuccin",
                    "monokai", "solarized", "github_dark", "tokyo_night", "one_dark"],
            fg_color=WIZ_COLORS["bg_input"],
            button_color=WIZ_COLORS["accent"],
            text_color=WIZ_COLORS["text"],
        ).pack(fill="x", pady=5)

        # ── Raw Shell Mode ──
        self._raw_var = ctk.BooleanVar(value=config.raw_shell_mode)
        ctk.CTkCheckBox(
            container, text="Raw Shell Mode (No LLM)",
            variable=self._raw_var,
            fg_color=WIZ_COLORS["accent"],
            text_color=WIZ_COLORS["text"],
        ).pack(anchor="w", pady=10)

        # ── Temperature ──
        self._add_section(container, f"Temperature: {config.llm.temperature}")
        self._temp_slider = ctk.CTkSlider(
            container, from_=0, to=2, number_of_steps=20,
            fg_color=WIZ_COLORS["bg_input"],
            progress_color=WIZ_COLORS["accent"],
        )
        self._temp_slider.set(config.llm.temperature)
        self._temp_slider.pack(fill="x", pady=5)

        # ── Save Button ──
        ctk.CTkButton(
            container, text="💾 Save Settings", height=40,
            font=("Segoe UI", 14, "bold"),
            fg_color=WIZ_COLORS["success"], hover_color="#00cc66",
            text_color="#000", corner_radius=8,
            command=self._save,
        ).pack(fill="x", pady=(20, 0))

    def _add_section(self, parent, title):
        ctk.CTkLabel(
            parent, text=title,
            font=("Segoe UI", 13, "bold"), text_color=WIZ_COLORS["text_dim"],
        ).pack(anchor="w", pady=(12, 2))

    def _save(self):
        self._config.llm.provider = self._provider_var.get()
        self._config.llm.model = self._model_var.get()
        self._config.ui.theme = self._theme_var.get()
        self._config.raw_shell_mode = self._raw_var.get()
        self._config.llm.temperature = round(self._temp_slider.get(), 2)
        self._config.save()
        if self._on_save:
            self._on_save(self._config)
        self.destroy()
