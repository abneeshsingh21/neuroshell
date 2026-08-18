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

try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False
    class _MockCTK:
        CTk = object
        CTkToplevel = object
        CTkFont = object
        CTkFrame = object
        CTkButton = object
        CTkLabel = object
        CTkEntry = object
        CTkTextbox = object
        CTkScrollableFrame = object
        CTkTabview = object
        CTkOptionMenu = object
        CTkCheckBox = object
        CTkProgressBar = object
        CTkSlider = object
        CTkSwitch = object
        StringVar = object
        BooleanVar = object
        IntVar = object
        DoubleVar = object
        @staticmethod
        def set_appearance_mode(*args, **kwargs): pass
        @staticmethod
        def set_default_color_theme(*args, **kwargs): pass
    ctk = _MockCTK()

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
        "default_model": "qwen3.6:30b",
        "default_url": "http://localhost:11434",
        "env_key": None,
    },
    {
        "id": "groq",
        "name": "Groq Cloud",
        "desc": "Ultra-fast cloud inference. Free tier available.",
        "url": "https://console.groq.com/keys",
        "needs_key": True,
        "default_model": "qwen/qwen3-32b",
        "default_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "desc": "GPT-5.5 and GPT-5.4 flagship models.",
        "url": "https://platform.openai.com/api-keys",
        "needs_key": True,
        "default_model": "gpt-5.5",
        "default_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "desc": "Claude Opus 4.7, Sonnet 4.6 & Haiku 4.5 models.",
        "url": "https://console.anthropic.com/settings/keys",
        "needs_key": True,
        "default_model": "claude-opus-4.7-20260416",
        "default_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "desc": "Gemini 3.1 Pro and Flash-Lite models.",
        "url": "https://aistudio.google.com/apikey",
        "needs_key": True,
        "default_model": "gemini-3.1-pro",
        "default_url": "https://generativelanguage.googleapis.com/v1beta",
        "env_key": "GEMINI_API_KEY",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "desc": "Access 300+ models through one API.",
        "url": "https://openrouter.ai/keys",
        "needs_key": True,
        "default_model": "openai/gpt-5.5",
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
    """Comprehensive in-app settings panel for runtime configuration."""

    # Model suggestions per provider
    _MODEL_SUGGESTIONS = {
        "ollama":     ["qwen3.6:30b", "llama4-scout:17b", "deepseek-r1:14b", "phi-4:14b", "gemma4:26b", "devstral-small:24b", "qwen3:4b", "mistral:7b"],
        "groq":       ["qwen/qwen3-32b", "meta-llama/llama-4-scout-17b-16e-instruct", "deepseek-r1-distill-llama-70b", "llama-3.3-70b-versatile", "gemma2-9b-it"],
        "openai":     ["gpt-5.5", "gpt-5.5-instant", "gpt-5.4", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o3", "o3-pro"],
        "anthropic":  ["claude-opus-4.7-20260416", "claude-sonnet-4.6-20260217", "claude-haiku-4.5-20251015", "claude-sonnet-4-20250514"],
        "gemini":     ["gemini-3.1-pro", "gemini-3.1-flash-lite", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
        "openrouter": ["openai/gpt-5.5", "anthropic/claude-opus-4.7", "google/gemini-3.1-pro", "meta-llama/llama-4-behemoth",
                        "deepseek/deepseek-r1", "qwen/qwen3.6-coder", "anthropic/claude-sonnet-4.6", "openai/gpt-4.1",
                        "meta-llama/llama-3.3-70b-instruct", "qwen/qwen3-235b", "google/gemma-4-27b", "nvidia/nemotron-3-super-120b"],
    }

    _BASE_URLS = {
        "ollama":     "http://localhost:11434",
        "groq":       "https://api.groq.com/openai/v1",
        "openai":     "https://api.openai.com/v1",
        "anthropic":  "https://api.anthropic.com/v1",
        "gemini":     "https://generativelanguage.googleapis.com/v1beta",
        "openrouter": "https://openrouter.ai/api/v1",
    }

    _ENV_KEYS = {
        "ollama": None, "groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY", "openrouter": "OPENROUTER_API_KEY",
    }

    def __init__(self, master, config: Config, on_save=None):
        super().__init__(master)
        self.title("⚙ NeuroShell Settings")
        self.geometry("680x720")
        self.resizable(True, True)
        self.configure(fg_color=WIZ_COLORS["bg"])
        self._config = config
        self._on_save = on_save
        self._status_label = None

        # Main scrollable container
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=10)

        # ═══════════ Section 1: LLM Configuration ═══════════
        self._section_header(container, "🤖  LLM Configuration")

        # Provider
        self._label(container, "Provider")
        self._provider_var = ctk.StringVar(value=config.llm.provider)
        prov_menu = ctk.CTkOptionMenu(
            container, variable=self._provider_var,
            values=[p["id"] for p in PROVIDERS],
            fg_color=WIZ_COLORS["bg_input"], button_color=WIZ_COLORS["accent"],
            text_color=WIZ_COLORS["text"], command=self._on_provider_change,
        )
        prov_menu.pack(fill="x", pady=4)

        # Model (dropdown with suggestions)
        self._label(container, "Model")
        self._model_var = ctk.StringVar(value=config.llm.model)
        models = self._MODEL_SUGGESTIONS.get(config.llm.provider, ["custom"])
        self._model_menu = ctk.CTkOptionMenu(
            container, variable=self._model_var, values=models,
            fg_color=WIZ_COLORS["bg_input"], button_color=WIZ_COLORS["accent"],
            text_color=WIZ_COLORS["text"],
        )
        self._model_menu.pack(fill="x", pady=4)

        # Custom model entry
        self._label(container, "Custom Model (override)")
        self._model_entry = ctk.CTkEntry(
            container, textvariable=self._model_var, placeholder_text="Enter custom model name",
            fg_color=WIZ_COLORS["bg_input"], text_color=WIZ_COLORS["text"],
            border_color=WIZ_COLORS["border"],
        )
        self._model_entry.pack(fill="x", pady=4)

        # API Key
        self._label(container, "API Key")
        env_key = self._ENV_KEYS.get(config.llm.provider)
        existing_key = config.get_secret(env_key) if env_key else ""
        self._api_key_var = ctk.StringVar(value=existing_key)
        key_frame = ctk.CTkFrame(container, fg_color="transparent")
        key_frame.pack(fill="x", pady=4)
        self._key_entry = ctk.CTkEntry(
            key_frame, textvariable=self._api_key_var, show="•",
            placeholder_text="sk-... or gsk_... (leave blank to keep current)",
            fg_color=WIZ_COLORS["bg_input"], text_color=WIZ_COLORS["text"],
            border_color=WIZ_COLORS["border"],
        )
        self._key_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._show_key = False
        ctk.CTkButton(
            key_frame, text="👁", width=32, height=28,
            fg_color=WIZ_COLORS["bg_card"], hover_color=WIZ_COLORS["selected"],
            text_color=WIZ_COLORS["text"], corner_radius=6,
            command=self._toggle_key_visibility,
        ).pack(side="right")

        # Base URL
        self._label(container, "Base URL")
        self._url_var = ctk.StringVar(value=config.llm.base_url)
        ctk.CTkEntry(
            container, textvariable=self._url_var,
            fg_color=WIZ_COLORS["bg_input"], text_color=WIZ_COLORS["text"],
            border_color=WIZ_COLORS["border"],
        ).pack(fill="x", pady=4)

        # Max Tokens + Temperature row
        row1 = ctk.CTkFrame(container, fg_color="transparent")
        row1.pack(fill="x", pady=4)

        lf = ctk.CTkFrame(row1, fg_color="transparent")
        lf.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._label(lf, "Max Tokens")
        self._tokens_var = ctk.StringVar(value=str(config.llm.max_tokens))
        ctk.CTkEntry(
            lf, textvariable=self._tokens_var, width=120,
            fg_color=WIZ_COLORS["bg_input"], text_color=WIZ_COLORS["text"],
            border_color=WIZ_COLORS["border"],
        ).pack(fill="x")

        rf = ctk.CTkFrame(row1, fg_color="transparent")
        rf.pack(side="right", fill="x", expand=True, padx=(6, 0))
        self._label(rf, "Timeout (sec)")
        self._timeout_var = ctk.StringVar(value=str(config.llm.timeout))
        ctk.CTkEntry(
            rf, textvariable=self._timeout_var, width=120,
            fg_color=WIZ_COLORS["bg_input"], text_color=WIZ_COLORS["text"],
            border_color=WIZ_COLORS["border"],
        ).pack(fill="x")

        # Temperature slider
        self._temp_label_var = ctk.StringVar(value=f"Temperature: {config.llm.temperature}")
        ctk.CTkLabel(container, textvariable=self._temp_label_var,
                     font=("Segoe UI", 11, "bold"), text_color=WIZ_COLORS["text_dim"],
                     ).pack(anchor="w", pady=(8, 0))
        self._temp_slider = ctk.CTkSlider(
            container, from_=0, to=2, number_of_steps=20,
            fg_color=WIZ_COLORS["bg_input"], progress_color=WIZ_COLORS["accent"],
            command=lambda v: self._temp_label_var.set(f"Temperature: {v:.2f}"),
        )
        self._temp_slider.set(config.llm.temperature)
        self._temp_slider.pack(fill="x", pady=4)

        # Toggles row
        tog_row = ctk.CTkFrame(container, fg_color="transparent")
        tog_row.pack(fill="x", pady=6)
        self._streaming_var = ctk.BooleanVar(value=config.llm.streaming)
        ctk.CTkCheckBox(tog_row, text="Streaming", variable=self._streaming_var,
                        fg_color=WIZ_COLORS["accent"], text_color=WIZ_COLORS["text"],
                        ).pack(side="left", padx=(0, 16))
        self._cache_var = ctk.BooleanVar(value=config.llm.cache_enabled)
        ctk.CTkCheckBox(tog_row, text="Response Cache", variable=self._cache_var,
                        fg_color=WIZ_COLORS["accent"], text_color=WIZ_COLORS["text"],
                        ).pack(side="left")

        # ═══════════ Section 2: UI Settings ═══════════
        self._section_header(container, "🎨  UI Settings")

        self._label(container, "Theme")
        self._theme_var = ctk.StringVar(value=config.ui.theme)
        ctk.CTkOptionMenu(
            container, variable=self._theme_var,
            values=["cyberpunk", "dracula", "nord", "gruvbox", "catppuccin",
                    "monokai", "solarized", "github_dark", "tokyo_night", "one_dark"],
            fg_color=WIZ_COLORS["bg_input"], button_color=WIZ_COLORS["accent"],
            text_color=WIZ_COLORS["text"],
        ).pack(fill="x", pady=4)

        ui_tog = ctk.CTkFrame(container, fg_color="transparent")
        ui_tog.pack(fill="x", pady=4)
        self._ghost_var = ctk.BooleanVar(value=config.ui.ghost_text)
        ctk.CTkCheckBox(ui_tog, text="Ghost Text", variable=self._ghost_var,
                        fg_color=WIZ_COLORS["accent"], text_color=WIZ_COLORS["text"],
                        ).pack(side="left", padx=(0, 12))
        self._syntax_var = ctk.BooleanVar(value=config.ui.syntax_highlighting)
        ctk.CTkCheckBox(ui_tog, text="Syntax Highlighting", variable=self._syntax_var,
                        fg_color=WIZ_COLORS["accent"], text_color=WIZ_COLORS["text"],
                        ).pack(side="left", padx=(0, 12))
        self._confidence_var = ctk.BooleanVar(value=config.ui.show_confidence)
        ctk.CTkCheckBox(ui_tog, text="Show Confidence", variable=self._confidence_var,
                        fg_color=WIZ_COLORS["accent"], text_color=WIZ_COLORS["text"],
                        ).pack(side="left")

        # ═══════════ Section 3: Safety ═══════════
        self._section_header(container, "🛡️  Safety & Security")
        safety_row = ctk.CTkFrame(container, fg_color="transparent")
        safety_row.pack(fill="x", pady=4)
        self._safety_var = ctk.BooleanVar(value=config.safety.enabled)
        ctk.CTkCheckBox(safety_row, text="Safety Guard", variable=self._safety_var,
                        fg_color=WIZ_COLORS["accent"], text_color=WIZ_COLORS["text"],
                        ).pack(side="left", padx=(0, 12))
        self._confirm_var = ctk.BooleanVar(value=config.safety.confirm_destructive)
        ctk.CTkCheckBox(safety_row, text="Confirm Destructive", variable=self._confirm_var,
                        fg_color=WIZ_COLORS["accent"], text_color=WIZ_COLORS["text"],
                        ).pack(side="left", padx=(0, 12))
        self._audit_var = ctk.BooleanVar(value=config.safety.audit_log_enabled)
        ctk.CTkCheckBox(safety_row, text="Audit Logging", variable=self._audit_var,
                        fg_color=WIZ_COLORS["accent"], text_color=WIZ_COLORS["text"],
                        ).pack(side="left")

        # ═══════════ Section 4: General ═══════════
        self._section_header(container, "⚙️  General")
        self._raw_var = ctk.BooleanVar(value=config.raw_shell_mode)
        ctk.CTkCheckBox(container, text="Raw Shell Mode (No LLM — maximum privacy)",
                        variable=self._raw_var, fg_color=WIZ_COLORS["accent"],
                        text_color=WIZ_COLORS["text"]).pack(anchor="w", pady=4)

        gen_row = ctk.CTkFrame(container, fg_color="transparent")
        gen_row.pack(fill="x", pady=4)
        self._hints_var = ctk.BooleanVar(value=config.hints_enabled)
        ctk.CTkCheckBox(gen_row, text="Show Hints", variable=self._hints_var,
                        fg_color=WIZ_COLORS["accent"], text_color=WIZ_COLORS["text"],
                        ).pack(side="left", padx=(0, 12))
        self._recording_var = ctk.BooleanVar(value=config.session_recording)
        ctk.CTkCheckBox(gen_row, text="Session Recording", variable=self._recording_var,
                        fg_color=WIZ_COLORS["accent"], text_color=WIZ_COLORS["text"],
                        ).pack(side="left")

        self._label(container, "Log Level")
        self._log_var = ctk.StringVar(value=config.log_level)
        ctk.CTkOptionMenu(
            container, variable=self._log_var,
            values=["DEBUG", "INFO", "WARNING", "ERROR"],
            fg_color=WIZ_COLORS["bg_input"], button_color=WIZ_COLORS["accent"],
            text_color=WIZ_COLORS["text"],
        ).pack(fill="x", pady=4)

        # ═══════════ Action Buttons ═══════════
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(16, 4))

        ctk.CTkButton(
            btn_frame, text="💾 Save Settings", height=40,
            font=("Segoe UI", 14, "bold"),
            fg_color=WIZ_COLORS["success"], hover_color="#00cc66",
            text_color="#000", corner_radius=8, command=self._save,
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="↺ Reset Defaults", width=150, height=40,
            font=("Segoe UI", 13),
            fg_color=WIZ_COLORS["bg_card"], hover_color=WIZ_COLORS["selected"],
            text_color=WIZ_COLORS["warning"], corner_radius=8,
            command=self._reset_defaults,
        ).pack(side="right")

        # Status label
        self._status_label = ctk.CTkLabel(
            container, text="", font=("Segoe UI", 11),
            text_color=WIZ_COLORS["success"],
        )
        self._status_label.pack(pady=(4, 0))

    # ── Helpers ──
    def _section_header(self, parent, title):
        sep = ctk.CTkFrame(parent, height=1, fg_color=WIZ_COLORS["border"])
        sep.pack(fill="x", pady=(14, 6))
        ctk.CTkLabel(parent, text=title, font=("Segoe UI", 15, "bold"),
                     text_color=WIZ_COLORS["accent"]).pack(anchor="w", pady=(0, 4))

    def _label(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=("Segoe UI", 11, "bold"),
                     text_color=WIZ_COLORS["text_dim"]).pack(anchor="w", pady=(6, 0))

    def _on_provider_change(self, provider):
        models = self._MODEL_SUGGESTIONS.get(provider, ["custom"])
        self._model_menu.configure(values=models)
        self._model_var.set(models[0])
        url = self._BASE_URLS.get(provider, "")
        self._url_var.set(url)
        env_key = self._ENV_KEYS.get(provider)
        if env_key:
            existing = self._config.get_secret(env_key, "")
            self._api_key_var.set(existing)
        else:
            self._api_key_var.set("")

    def _toggle_key_visibility(self):
        self._show_key = not self._show_key
        self._key_entry.configure(show="" if self._show_key else "•")

    def _reset_defaults(self):
        self._provider_var.set("ollama")
        self._on_provider_change("ollama")
        self._tokens_var.set("512")
        self._timeout_var.set("30")
        self._temp_slider.set(0.3)
        self._temp_label_var.set("Temperature: 0.30")
        self._streaming_var.set(True)
        self._cache_var.set(True)
        self._theme_var.set("cyberpunk")
        self._ghost_var.set(True)
        self._syntax_var.set(True)
        self._confidence_var.set(True)
        self._safety_var.set(True)
        self._confirm_var.set(True)
        self._audit_var.set(True)
        self._raw_var.set(False)
        self._hints_var.set(True)
        self._recording_var.set(True)
        self._log_var.set("INFO")
        if self._status_label:
            self._status_label.configure(text="✓ Reset to defaults (click Save to apply)",
                                         text_color=WIZ_COLORS["warning"])

    def _save(self):
        # LLM
        self._config.llm.provider = self._provider_var.get()
        self._config.llm.model = self._model_var.get()
        self._config.llm.base_url = self._url_var.get()
        try:
            self._config.llm.max_tokens = int(self._tokens_var.get())
        except ValueError:
            pass
        try:
            self._config.llm.timeout = int(self._timeout_var.get())
        except ValueError:
            pass
        self._config.llm.temperature = round(self._temp_slider.get(), 2)
        self._config.llm.streaming = self._streaming_var.get()
        self._config.llm.cache_enabled = self._cache_var.get()

        # API Key
        provider = self._provider_var.get()
        env_key = self._ENV_KEYS.get(provider)
        api_key = self._api_key_var.get().strip()
        if env_key and api_key:
            self._config.set_secret(env_key, api_key)

        # UI
        self._config.ui.theme = self._theme_var.get()
        self._config.ui.ghost_text = self._ghost_var.get()
        self._config.ui.syntax_highlighting = self._syntax_var.get()
        self._config.ui.show_confidence = self._confidence_var.get()

        # Safety
        self._config.safety.enabled = self._safety_var.get()
        self._config.safety.confirm_destructive = self._confirm_var.get()
        self._config.safety.audit_log_enabled = self._audit_var.get()

        # General
        self._config.raw_shell_mode = self._raw_var.get()
        self._config.hints_enabled = self._hints_var.get()
        self._config.session_recording = self._recording_var.get()
        self._config.log_level = self._log_var.get()

        self._config.save()
        if self._on_save:
            self._on_save(self._config)
        self.destroy()

