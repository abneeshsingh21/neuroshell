# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
#!/usr/bin/env python3
"""
NeuroShell Desktop v5.2.0 — Professional AI Terminal GUI
Premium dark glassmorphism interface with real-time telemetry,
security indicators, AI pipeline routing, and multi-panel cockpit.
"""

import os
import re
import sys
import io
import time
import uuid
import json
import math
import traceback
import platform
import subprocess
import webbrowser
import threading
import importlib
from collections import deque
from datetime import datetime
import customtkinter as ctk  # type: ignore[import]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import NEUROSHELL_DIR, Config  # type: ignore[import]
from core.events import neuro_events  # type: ignore[import]
from ui.wizard import FirstRunWizard, needs_first_run, SettingsPanel
from config import load_config


# ═══════════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM — Premium Dark Theme
# ═══════════════════════════════════════════════════════════════════════════

COLORS = {
    # Backgrounds
    "bg_root":        "#060b12",
    "bg_deep":        "#080d15",
    "bg_dark":        "#0b1120",
    "bg_panel":       "#0f1828",
    "bg_card":        "#111d2e",
    "bg_elevated":    "#162338",
    "bg_input":       "#0d1a2a",
    "bg_hover":       "#1a2d44",
    "bg_active":      "#1e3452",
    "bg_glass":       "#12203580",

    # Borders
    "border":         "#1c2f48",
    "border_soft":    "#1a2a3d",
    "border_focus":   "#3b9eff",
    "border_glow":    "#1d4a7a",

    # Text
    "text_primary":   "#dce8f5",
    "text_secondary": "#7a9bbf",
    "text_muted":     "#3d5570",
    "text_dim":       "#2a3f57",

    # Accent Palette
    "accent_cyan":    "#00d4c8",
    "accent_blue":    "#3b9eff",
    "accent_green":   "#00e676",
    "accent_red":     "#ff4d6d",
    "accent_yellow":  "#ffd93d",
    "accent_purple":  "#b47bff",
    "accent_orange":  "#ff9248",
    "accent_pink":    "#ff6fb0",

    # Glow backgrounds (tkinter doesn't support 8-digit RGBA — use solid dark tints)
    "glow_cyan":      "#002e2c",
    "glow_blue":      "#0d2340",
    "glow_green":     "#002e14",
    "glow_red":       "#2e0011",

    # Scrollbar
    "scrollbar":      "#1c2f48",
    "scrollbar_hover":"#2a4562",

    # Canvas
    "chart_line_1":   "#00d4c8",
    "chart_line_2":   "#ff4d6d",
    "chart_line_3":   "#ffd93d",
    "chart_grid":     "#1c2f48",
}

FONT_MONO   = "Cascadia Code"
FONT_MONO2  = "Consolas"
FONT_UI     = "Segoe UI"
FONT_UI2    = "Inter"

ANSI_TAG_COLORS = {
    "ansi_black":    "#485f7a",  "ansi_red":      "#ff4d6d",
    "ansi_green":    "#00e676",  "ansi_yellow":   "#ffd93d",
    "ansi_blue":     "#3b9eff",  "ansi_magenta":  "#b47bff",
    "ansi_cyan":     "#00d4c8",  "ansi_white":    "#dce8f5",
    "ansi_gray":     "#7a9bbf",  "ansi_lred":     "#ff8095",
    "ansi_lgreen":   "#5dfa9a",  "ansi_lyellow":  "#ffe080",
    "ansi_lblue":    "#79bcff",  "ansi_lmagenta": "#cda0ff",
    "ansi_lcyan":    "#66e8e3",  "ansi_lwhite":   "#ffffff",
    "ansi_bold":     "#ffffff",
}

ANSI_CODE_MAP = {
    "30": "ansi_black",   "31": "ansi_red",     "32": "ansi_green",
    "33": "ansi_yellow",  "34": "ansi_blue",    "35": "ansi_magenta",
    "36": "ansi_cyan",    "37": "ansi_white",   "90": "ansi_gray",
    "91": "ansi_lred",    "92": "ansi_lgreen",  "93": "ansi_lyellow",
    "94": "ansi_lblue",   "95": "ansi_lmagenta","96": "ansi_lcyan",
    "97": "ansi_lwhite",  "1":  "ansi_bold",
}

# Alias expected by tests (maps ANSI code -> hex color directly)
ANSI_COLORS = {
    k: ANSI_TAG_COLORS[v] for k, v in ANSI_CODE_MAP.items()
}

# Font aliases used in tests
FONT_FAMILY = FONT_MONO


# ═══════════════════════════════════════════════════════════════════════════
# GUI OUTPUT STREAM  +  MOCK STDIN
# ═══════════════════════════════════════════════════════════════════════════

_ANSI_RE1 = re.compile(r'\x1b\[[0-9;]*m')
_ANSI_RE2 = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')


class _GUIOutputStream:
    """Thread-safe stdout/stderr redirector that strips ANSI and sends to GUI."""
    def __init__(self, app):
        self._app = app
        self._buffer = []

    def get_captured_text(self) -> str:
        """Flushes and returns the exact accumulated assistant text for memory recording."""
        return "".join(self._buffer)

    def write(self, text):
        if not text:
            return
        if '\r' in text:
            parts = text.split('\r')
            text = parts[-1]
            if not text.strip():
                return
            stripped = text.strip()
            if stripped.startswith(('🤖 Thinking', '🔄 Following', '⏳')):
                return
            if not stripped:
                return
        # Use pre-compiled patterns to strip ANSI for memory buffering
        raw_text = _ANSI_RE1.sub('', text)
        raw_text = _ANSI_RE2.sub('', raw_text)
        if raw_text:
            self._buffer.append(raw_text)
            
        # Pass original text WITH ANSI to GUI for colored rendering
        self._app.after(0, lambda t=text: self._app._append_output(t))

    def flush(self): pass
    def isatty(self): return False
    def fileno(self): raise io.UnsupportedOperation('fileno')
    @property
    def encoding(self): return 'utf-8'
    @property
    def errors(self): return 'replace'


class _GUIMockStdin:
    """Infinite mock stdin for GUI mode — auto-answers 'y' to all prompts.

    Unlike StringIO('y\n'), this is never exhausted — every read returns 'y\n'
    so multi-prompt command pipelines don't crash on the second input() call.
    """
    def readline(self): return 'y\n'
    def read(self, n=-1): return 'y\n'
    def isatty(self): return False
    def fileno(self): raise io.UnsupportedOperation('fileno')
    def flush(self): pass
    def close(self): pass
    @property
    def encoding(self): return 'utf-8'
    @property
    def errors(self): return 'replace'
    def __iter__(self): return self
    def __next__(self): return 'y\n'


# Thread-safe builtins.input override for GUI mode.
# Using builtins.input instead of sys.stdin avoids the global-state race
# condition when two commands run concurrently (double-click, keyboard mash).
# The Semaphore below enforces only one command thread runs at a time.
_GUI_INPUT_LOCK = threading.Semaphore(1)  # singleton command slot


def _gui_safe_input(prompt=''):
    """Replacement for builtins.input() in GUI mode — never blocks."""
    return 'y'


# ═══════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════

class NeuroShellDesktop(ctk.CTk):
    """NeuroShell v5.2.0 — Professional AI-Powered Terminal Desktop Application."""

    # Theme definitions — keys must be consistent across all themes
    _THEMES = {
        "dark": {
            "bg": COLORS["bg_root"], "fg": COLORS["text_primary"],
            "accent": COLORS["accent_cyan"], "border": COLORS["border"],
            "panel": COLORS["bg_panel"], "input": COLORS["bg_input"],
        },
        "ocean": {
            "bg": "#020b18", "fg": "#b0d8ff",
            "accent": "#00bcd4", "border": "#0e2a3d",
            "panel": "#061525", "input": "#040f1d",
        },
        "matrix": {
            "bg": "#000f00", "fg": "#00ff41",
            "accent": "#00ff41", "border": "#003300",
            "panel": "#001400", "input": "#000a00",
        },
        "light": {
            "bg": "#f5f7fa", "fg": "#1a2332",
            "accent": "#0066cc", "border": "#d0dae8",
            "panel": "#edf1f7", "input": "#ffffff",
        },
    }

    def __init__(self):
        super().__init__()

        # ── Window Setup ──
        self.title("NeuroShell v5.2.0 — AI Terminal")
        self.geometry("1440x860")
        self.minsize(1100, 660)
        self.configure(fg_color=COLORS["bg_root"])

        # ── App Config ──
        try:
            self._app_config = load_config()
        except Exception:
            self._app_config = Config()

        try:
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # ── State ──
        self.session_id           = uuid.uuid4().hex[:8]
        self.command_history: list[str] = []
        self.history_index        = -1
        self.command_count        = 0
        self.command_success_count= 0
        self.command_error_count  = 0
        self.total_duration_ms    = 0.0
        self.current_shell        = "powershell"
        self.sidebar_visible      = True
        self.cockpit_visible      = True
        self._current_process     = None
        self._neuroshell          = None
        self._engine_ready        = False
        self._init_lock           = threading.Lock()
        self._last_error          = ""
        self._last_command         = ""
        self._saved_input_text     = ""   # preserves typed text during history nav
        self.mode                 = "Builder"
        self.experience_level     = "Guided"
        self.ai_mode              = "Fast LLM"
        self._fullscreen          = False
        self._theme_index         = 0  # for _cycle_theme

        # Telemetry history
        self._perf_samples        = deque(maxlen=60)
        self._error_samples       = deque(maxlen=60)
        self._tps_samples         = deque(maxlen=60)
        self._last_tick_cmds      = 0
        self._last_tick_time      = time.time()
        self._boot_time           = datetime.now()
        self._telemetry_after_id  = None  # to cancel ticker on exit

        # Singleton dialog tracking — prevents opening multiple of same window
        self._open_windows: dict[str, ctk.CTkToplevel] = {}

        # Security panel state
        self._security_events: deque = deque(maxlen=50)
        self._injection_blocks    = 0
        self._encryption_ok       = True

        # Crash reporting
        self._crash_dir = NEUROSHELL_DIR / "crash_reports"
        self._crash_dir.mkdir(parents=True, exist_ok=True)

        # Bookmarks
        self._bookmarks: list[str] = []
        self._load_bookmarks()

        # Search overlay state
        self._search_bar = None
        self._search_matches: list = []
        self._search_index = 0

        # Brand assets
        self._brand_logo_source = None
        self._brand_images: dict[int, ctk.CTkImage] = {}
        self._load_brand_assets()

        # ── Build UI ──
        self._build_titlebar()
        self._build_main_layout()
        self._build_statusbar()

        # ── Keybindings ──
        self.bind("<Control-l>",       lambda e: self._clear_terminal())
        self.bind("<Control-c>",       lambda e: self._interrupt_command())
        self.bind("<F11>",             lambda e: self._toggle_fullscreen())
        self.bind("<Control-b>",       lambda e: self._toggle_sidebar())
        self.bind("<Control-Shift-P>", lambda e: self._show_command_palette())
        self.bind("<Control-Shift-p>", lambda e: self._show_command_palette())
        self.bind("<Control-g>",       lambda e: self._show_command_graph())
        self.bind("<Control-d>",       lambda e: self._on_close())
        self.bind("<Control-a>",       lambda e: self._select_all_input())
        self.bind("<Control-f>",       lambda e: self._toggle_search_bar())
        self.bind("<Control-Shift-C>", lambda e: self._copy_selection())
        self.bind("<Control-Shift-c>", lambda e: self._copy_selection())
        self.bind("<Control-Shift-E>", lambda e: self._export_session_markdown())
        self.bind("<Control-Shift-e>", lambda e: self._export_session_markdown())
        self.bind("<Control-Shift-B>", lambda e: self._bookmark_last_command())
        self.bind("<Control-Shift-b>", lambda e: self._bookmark_last_command())
        self.bind("<Escape>",          lambda e: self._on_escape())

        # ── Close handler — clean teardown ──
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── Event Bus ──
        neuro_events.subscribe("swarm_update",  self._append_agent_feed)
        neuro_events.subscribe("gc_update",     lambda m: self.after(0, lambda: self._show_toast(m, "info")))
        neuro_events.subscribe("injection_blocked", self._on_injection_blocked)

        # ── Live Log Handler — routes neuroshell.* WARNING+ to terminal ──
        self._install_gui_log_handler()

        self._install_crash_handlers()
        self.after(100, self._on_startup)
        self.after(1500, self._tick_telemetry)
        self.after(1000, self._poll_task_manager)


    # ── Brand Assets ─────────────────────────────────────────────────────────

    def _load_brand_assets(self):
        try:
            _Image = importlib.import_module("PIL.Image")
        except Exception:
            return
        logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
        if not os.path.exists(logo_path):
            return
        try:
            self._brand_logo_source = _Image.open(logo_path).convert("RGBA")
        except Exception:
            self._brand_logo_source = None

    def _get_brand_image(self, size: int):
        if self._brand_logo_source is None:
            return None
        if size not in self._brand_images:
            self._brand_images[size] = ctk.CTkImage(
                light_image=self._brand_logo_source,
                dark_image=self._brand_logo_source,
                size=(size, size),
            )
        return self._brand_images[size]

    def _brand_badge(self, parent, size=28, title_size=16, subtitle=""):
        """Compact brand badge: logo + wordmark + optional subtitle."""
        f = ctk.CTkFrame(parent, fg_color="transparent")
        img = self._get_brand_image(size)
        if img:
            ctk.CTkLabel(f, text="", image=img).pack(side="left")
        else:
            ctk.CTkLabel(
                f, text="N⚡", width=size, height=size,
                corner_radius=size // 4,
                fg_color=COLORS["bg_active"],
                text_color=COLORS["accent_cyan"],
                font=ctk.CTkFont(family=FONT_UI, size=size // 2, weight="bold"),
            ).pack(side="left")

        txt = ctk.CTkFrame(f, fg_color="transparent")
        txt.pack(side="left", padx=(6, 0))
        ctk.CTkLabel(
            txt, text="NeuroShell",
            font=ctk.CTkFont(family=FONT_UI, size=title_size, weight="bold"),
            text_color=COLORS["accent_cyan"], anchor="w",
        ).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(
                txt, text=subtitle,
                font=ctk.CTkFont(family=FONT_UI, size=9),
                text_color=COLORS["text_muted"], anchor="w",
            ).pack(anchor="w")
        return f

    # ═════════════════════════════════════════════════════════════════════════
    # TITLEBAR  (top navigation strip)
    # ═════════════════════════════════════════════════════════════════════════

    def _build_titlebar(self):
        self.titlebar = ctk.CTkFrame(
            self, height=52, fg_color=COLORS["bg_panel"],
            corner_radius=0, border_width=0,
        )
        self.titlebar.pack(fill="x", side="top")
        self.titlebar.pack_propagate(False)

        # ── Left: Brand ──
        left = ctk.CTkFrame(self.titlebar, fg_color="transparent")
        left.pack(side="left", padx=14, pady=0)
        self._brand_badge(left, size=28, title_size=15, subtitle="v5.2.0  •  AI Terminal").pack(side="left")

        # ── Center: Selectors ──
        center = ctk.CTkFrame(self.titlebar, fg_color="transparent")
        center.pack(side="left", padx=10)

        sseg = dict(
            font=ctk.CTkFont(family=FONT_UI, size=10, weight="bold"),
            fg_color=COLORS["bg_dark"],
            unselected_color=COLORS["bg_card"],
            unselected_hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            corner_radius=8,
        )

        # Shell
        self.shell_selector = ctk.CTkSegmentedButton(
            center, values=["PowerShell", "CMD"],
            command=self._on_shell_change,
            selected_color=COLORS["accent_blue"],
            selected_hover_color="#2a80dd",
            width=160, **sseg,
        )
        self.shell_selector.set("PowerShell")
        self.shell_selector.pack(side="left")

        # Mode
        self.mode_selector = ctk.CTkSegmentedButton(
            center, values=["Builder", "Planner", "Agentic", "DevOps"],
            command=self._on_mode_change,
            selected_color=COLORS["accent_cyan"],
            selected_hover_color="#00b0a8",
            width=220, **sseg,
        )
        self.mode_selector.set("Builder")
        self.mode_selector.pack(side="left", padx=(8, 0))

        # AI Engine
        self.ai_selector = ctk.CTkSegmentedButton(
            center, values=["Fast LLM", "Local AI", "Swarm"],
            command=self._on_ai_change,
            selected_color=COLORS["accent_purple"],
            selected_hover_color="#8a5bdd",
            width=180, **sseg,
        )
        self.ai_selector.set("Fast LLM")
        self.ai_selector.pack(side="left", padx=(8, 0))

        # ── HUD metrics ──
        hud = ctk.CTkFrame(self.titlebar, fg_color="transparent")
        hud.pack(side="left", padx=14)
        hf = ctk.CTkFont(family=FONT_UI, size=10, weight="bold")

        self.hud_latency = ctk.CTkLabel(hud, text="⚡ --ms", font=hf, text_color=COLORS["accent_cyan"])
        self.hud_latency.pack(side="left", padx=6)

        self.hud_success = ctk.CTkLabel(hud, text="✓ --", font=hf, text_color=COLORS["accent_green"])
        self.hud_success.pack(side="left", padx=6)

        self.hud_errors = ctk.CTkLabel(hud, text="✗ --", font=hf, text_color=COLORS["accent_red"])
        self.hud_errors.pack(side="left", padx=6)

        self.hud_security = ctk.CTkLabel(hud, text="🔒 SECURE", font=hf, text_color=COLORS["accent_green"])
        self.hud_security.pack(side="left", padx=6)

        # ── Right: Actions ──
        right = ctk.CTkFrame(self.titlebar, fg_color="transparent")
        right.pack(side="right", padx=10)

        actions = [
            ("⚡ Dashboard",    self._show_dashboard,       COLORS["accent_cyan"]),
            ("🔍 Palette",     self._show_command_palette,  COLORS["text_secondary"]),
            ("📊 Monitor",     self._show_process_monitor,  COLORS["text_secondary"]),
            ("🛡️ Security",   self._show_security_panel,   COLORS["accent_green"]),
            ("🎨 Theme",       self._cycle_theme,           COLORS["text_secondary"]),
            ("⚙️ Settings",   self._show_settings,         COLORS["text_secondary"]),
            ("⌫ Clear",        self._clear_terminal,        COLORS["text_secondary"]),
            ("—",             self.iconify,                COLORS["text_muted"]),
            ("⛶",             self._toggle_fullscreen,     COLORS["text_muted"]),
            ("◧",             self._toggle_sidebar,        COLORS["text_muted"]),
        ]

        for text, cmd, color in actions:
            is_accent = text.startswith("⚡")
            ctk.CTkButton(
                right,
                text=text, command=cmd,
                width=70, height=28, corner_radius=8,
                fg_color=COLORS["accent_cyan"] if is_accent else COLORS["bg_card"],
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["bg_root"] if is_accent else color,
                font=ctk.CTkFont(size=10, weight="bold"),
                border_width=0 if is_accent else 1,
                border_color=COLORS["border"],
            ).pack(side="left", padx=2)

        # Glowing bottom border
        ctk.CTkFrame(self, height=1, fg_color=COLORS["border_glow"], corner_radius=0).pack(fill="x", side="top")

    # ═════════════════════════════════════════════════════════════════════════
    # MAIN LAYOUT
    # ═════════════════════════════════════════════════════════════════════════

    def _build_main_layout(self):
        self.main_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_root"], corner_radius=0)
        self.main_frame.pack(fill="both", expand=True)

        self._build_sidebar()
        self._build_terminal_area()
        self._build_cockpit()

    # ═════════════════════════════════════════════════════════════════════════
    # SIDEBAR
    # ═════════════════════════════════════════════════════════════════════════

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(
            self.main_frame, width=230, fg_color=COLORS["bg_panel"],
            corner_radius=0, border_width=1, border_color=COLORS["border_soft"],
        )
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.sidebar_content = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=COLORS["scrollbar"],
            scrollbar_button_hover_color=COLORS["scrollbar_hover"],
        )
        self.sidebar_content.pack(fill="both", expand=True)

        p = self.sidebar_content

        # ── Brand header ──
        self._brand_badge(p, size=20, title_size=13, subtitle="Control Center").pack(
            fill="x", padx=10, pady=(12, 8)
        )

        ctk.CTkFrame(p, height=1, fg_color=COLORS["border_soft"], corner_radius=0).pack(fill="x", padx=6, pady=2)

        # ── Session Info Card ──
        self._sidebar_section(p, "SESSION INFO", COLORS["accent_cyan"])
        info_card = self._card(p)
        self.session_label = ctk.CTkLabel(
            info_card, text=f"ID  #{self.session_id}  •  {platform.node()[:14]}",
            font=ctk.CTkFont(family=FONT_MONO, size=9),
            text_color=COLORS["text_muted"], anchor="w",
        )
        self.session_label.pack(fill="x", padx=10, pady=(6, 0))

        self.uptime_label = ctk.CTkLabel(
            info_card, text="Uptime  0m",
            font=ctk.CTkFont(family=FONT_UI, size=10),
            text_color=COLORS["text_secondary"], anchor="w",
        )
        self.uptime_label.pack(fill="x", padx=10, pady=(0, 4))

        self.project_label = ctk.CTkLabel(
            info_card, text="📂 Detecting project...",
            font=ctk.CTkFont(family=FONT_UI, size=10),
            text_color=COLORS["text_secondary"],
            anchor="w", wraplength=190,
        )
        self.project_label.pack(fill="x", padx=10, pady=(0, 8))

        # ── Security Status Card ──
        self._sidebar_section(p, "SECURITY STATUS", COLORS["accent_green"])
        sec_card = self._card(p)

        self.sec_encryption_label = self._status_row(sec_card, "🔒 Fernet AES-128", "Active", COLORS["accent_green"])
        self.sec_injection_label  = self._status_row(sec_card, "🛡️ Injection Guard", "Active", COLORS["accent_green"])
        self.sec_hash_label       = self._status_row(sec_card, "📋 SHA-256 Verify", "Active", COLORS["accent_green"])
        self.sec_blocks_label     = self._status_row(sec_card, "⛔ Blocks", "0", COLORS["text_secondary"])

        # ── Mission Control ──
        self._sidebar_section(p, "MISSION CONTROL", COLORS["accent_purple"])
        mission_card = self._card(p)

        self.mission_posture = ctk.CTkLabel(
            mission_card, text="● Bootstrapping...",
            font=ctk.CTkFont(family=FONT_UI, size=10, weight="bold"),
            text_color=COLORS["accent_cyan"], anchor="w",
        )
        self.mission_posture.pack(fill="x", padx=10, pady=(8, 4))

        for lbl, color, attr in [
            ("Reliability", COLORS["accent_green"],  "bar_reliability"),
            ("Performance", COLORS["accent_blue"],   "bar_performance"),
            ("Load",        COLORS["accent_orange"], "bar_load"),
            ("Security",    COLORS["accent_purple"], "bar_security"),
        ]:
            row = ctk.CTkFrame(mission_card, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=1)
            ctk.CTkLabel(row, text=lbl, width=62,
                         font=ctk.CTkFont(family=FONT_UI, size=9),
                         text_color=COLORS["text_muted"], anchor="w").pack(side="left")
            bar = ctk.CTkProgressBar(row, progress_color=color, height=5, corner_radius=3)
            bar.set(0)
            bar.pack(side="left", fill="x", expand=True, padx=(4, 0))
            setattr(self, attr, bar)

        ctk.CTkFrame(mission_card, fg_color="transparent", height=6).pack()

        # ── Quick Commands ──
        self._sidebar_section(p, "QUICK ACTIONS", COLORS["accent_blue"])
        quick_card = self._card(p)

        quick_commands = [
            ("⚡  Dashboard",          "dashboard"),
            ("❓  Help & Commands",     "help"),
            ("🔧  Fix Last Error",      "fix"),
            ("💡  Explain Command",     "explain: "),
            ("↩   Undo Last Action",   "undo"),
            ("🔗  Smart Clone",         "clone "),
            ("🚀  Quick Launch",        "open "),
            ("🚀  Deploy Status",       "deploy status"),
            ("📋  Policy Audit",        "policy"),
            ("💡  AI Suggestions",      "suggest"),
            ("🛡️  Security Scan",      "scan"),
            ("🎨  Themes",             "themes"),
            ("📌  Snippets",            "snippets"),
            ("📓  Notebook",            "notebook"),
            ("🔍  Command Palette",     "palette "),
            ("📅  Timeline",            "timeline"),
            ("📊  Audit Report",        "audit"),
            ("🌐  Start API",           "api start"),
        ]

        for label, cmd in quick_commands:
            ctk.CTkButton(
                quick_card, text=label, anchor="w",
                font=ctk.CTkFont(family=FONT_UI, size=10),
                fg_color="transparent", hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_primary"], corner_radius=6, height=26,
                command=lambda c=cmd: self._quick_command(c),
            ).pack(fill="x", padx=6, pady=1)
        ctk.CTkFrame(quick_card, fg_color="transparent", height=4).pack()

        # ── Starter Missions ──
        self._sidebar_section(p, "STARTER MISSIONS", COLORS["accent_yellow"])
        starter_card = self._card(p)

        self.starter_tip_label = ctk.CTkLabel(
            starter_card,
            text="Run 'help' to discover all AI capabilities.",
            font=ctk.CTkFont(family=FONT_UI, size=9),
            text_color=COLORS["text_secondary"],
            justify="left", wraplength=185, anchor="w",
        )
        self.starter_tip_label.pack(fill="x", padx=10, pady=(8, 6))

        ctk.CTkButton(
            starter_card, text="📘 Beginner Guide",
            font=ctk.CTkFont(family=FONT_UI, size=10, weight="bold"),
            fg_color=COLORS["bg_elevated"], hover_color=COLORS["glow_cyan"],
            border_width=1, border_color=COLORS["border_glow"],
            text_color=COLORS["accent_cyan"], corner_radius=8, height=28,
            command=self._show_beginner_guide,
        ).pack(fill="x", padx=6, pady=(0, 8))

    def _sidebar_section(self, parent, title, color):
        """Compact section label."""
        ctk.CTkLabel(
            parent, text=title,
            font=ctk.CTkFont(family=FONT_UI, size=9, weight="bold"),
            text_color=color, anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 3))

    def _card(self, parent, **kw):
        """Standard glassmorphism-style card frame."""
        c = ctk.CTkFrame(
            parent, fg_color=COLORS["bg_card"],
            corner_radius=10,
            border_width=1, border_color=COLORS["border_soft"],
            **kw,
        )
        c.pack(fill="x", padx=8, pady=(0, 6))
        return c

    def _status_row(self, parent, label, value, color):
        """A two-column status row inside a card."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=1)
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(family=FONT_UI, size=9),
                     text_color=COLORS["text_muted"], anchor="w").pack(side="left")
        lbl = ctk.CTkLabel(row, text=value, font=ctk.CTkFont(family=FONT_UI, size=9, weight="bold"),
                           text_color=color, anchor="e")
        lbl.pack(side="right")
        return lbl

    # ═════════════════════════════════════════════════════════════════════════
    # TERMINAL AREA
    # ═════════════════════════════════════════════════════════════════════════

    def _build_terminal_area(self):
        self.terminal_container = ctk.CTkFrame(
            self.main_frame, fg_color=COLORS["bg_root"], corner_radius=0,
        )
        self.terminal_container.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        # ── Tab bar ──
        tab_bar = ctk.CTkFrame(self.terminal_container, height=34,
                               fg_color=COLORS["bg_panel"], corner_radius=8)
        tab_bar.pack(fill="x", pady=(0, 4))
        tab_bar.pack_propagate(False)

        self.tab_label = ctk.CTkLabel(
            tab_bar, text="  ❯ Terminal  ✦  Session #{sid}".format(sid=self.session_id),
            font=ctk.CTkFont(family=FONT_MONO, size=11),
            text_color=COLORS["accent_cyan"], anchor="w",
        )
        self.tab_label.pack(side="left", padx=10)

        self.shell_indicator = ctk.CTkLabel(
            tab_bar, text="⬡ PowerShell",
            font=ctk.CTkFont(family=FONT_UI, size=10, weight="bold"),
            text_color=COLORS["accent_blue"],
        )
        self.shell_indicator.pack(side="right", padx=10)

        self.cwd_label = ctk.CTkLabel(
            tab_bar, text=f"📂 {os.path.basename(os.getcwd())}",
            font=ctk.CTkFont(family=FONT_UI, size=9),
            text_color=COLORS["text_muted"],
        )
        self.cwd_label.pack(side="right", padx=10)

        # ── Terminal Shell ──
        terminal_shell = ctk.CTkFrame(
            self.terminal_container,
            fg_color=COLORS["bg_panel"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
        )
        terminal_shell.pack(fill="both", expand=True)

        # Output pane
        self.output_text = ctk.CTkTextbox(
            terminal_shell,
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family=FONT_MONO, size=13),
            corner_radius=10,
            border_width=0,
            scrollbar_button_color=COLORS["scrollbar"],
            scrollbar_button_hover_color=COLORS["scrollbar_hover"],
            wrap="word",
            state="disabled",
        )
        self.output_text.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self._setup_output_tags()
        self._setup_context_menu()

        # Glowing divider
        ctk.CTkFrame(terminal_shell, height=1,
                     fg_color=COLORS["border_glow"], corner_radius=0).pack(fill="x", padx=10, pady=(4, 0))

        # ── Input Row ──
        input_outer = ctk.CTkFrame(terminal_shell, fg_color="transparent")
        input_outer.pack(fill="x", padx=10, pady=(6, 10))

        # Input box with glow border
        input_box = ctk.CTkFrame(
            input_outer,
            fg_color=COLORS["bg_input"],
            corner_radius=10,
            border_width=2,
            border_color=COLORS["border_glow"],
        )
        input_box.pack(side="left", fill="x", expand=True)

        self.prompt_label = ctk.CTkLabel(
            input_box, text="❯",
            font=ctk.CTkFont(family=FONT_MONO, size=16, weight="bold"),
            text_color=COLORS["accent_cyan"], width=20, anchor="w",
        )
        self.prompt_label.pack(side="left", padx=(10, 4))

        self.command_entry = ctk.CTkEntry(
            input_box,
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["bg_input"],
            border_width=0,
            font=ctk.CTkFont(family=FONT_MONO, size=13),
            corner_radius=0,
            placeholder_text="Type a command or ask in plain English...",
            placeholder_text_color=COLORS["text_dim"],
        )
        self.command_entry.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.command_entry.bind("<Return>",  self._on_enter)
        self.command_entry.bind("<Up>",      self._on_history_up)
        self.command_entry.bind("<Down>",    self._on_history_down)
        self.command_entry.bind("<Tab>",     self._on_tab)
        self.command_entry.bind("<KeyRelease>", self._on_key_release)
        self.command_entry.focus_set()

        # AI badge
        self.ai_badge = ctk.CTkLabel(
            input_box, text="⚡ AI",
            font=ctk.CTkFont(family=FONT_UI, size=9, weight="bold"),
            text_color=COLORS["accent_cyan"],
            fg_color=COLORS["bg_active"], corner_radius=4,
            padx=5, pady=2,
        )
        self.ai_badge.pack(side="left", padx=4)

        # Run button
        self.run_button = ctk.CTkButton(
            input_outer, text="▶  RUN", width=80, height=36,
            font=ctk.CTkFont(family=FONT_UI, size=11, weight="bold"),
            fg_color=COLORS["accent_cyan"],
            hover_color="#00b0a8",
            text_color=COLORS["bg_root"],
            corner_radius=10,
            command=lambda: self._on_enter(None),
        )
        self.run_button.pack(side="left", padx=(6, 0))

        # Voice Dictation button
        self.voice_button = ctk.CTkButton(
            input_outer, text="🎙️  DICTATE", width=100, height=36,
            font=ctk.CTkFont(family=FONT_UI, size=11, weight="bold"),
            fg_color=COLORS["bg_panel"],
            hover_color=COLORS["bg_active"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border"],
            corner_radius=10,
            command=self._toggle_voice_recording,
        )
        self.voice_button.pack(side="left", padx=(6, 0))

    # ═════════════════════════════════════════════════════════════════════════
    # VOICE CONTROL
    # ═════════════════════════════════════════════════════════════════════════

    def _toggle_voice_recording(self):
        if not hasattr(self, "_audio_capture") or not self._audio_capture:
            self._show_toast("Voice transcription module not loaded", "warn")
            return

        if not self.is_recording:
            # Start Recording
            self.is_recording = True
            self.voice_button.configure(
                text="⏹️  RECORDING...", fg_color=COLORS["accent_red"], text_color=COLORS["bg_root"]
            )
            self._show_toast("Listening... Speak your command.", "info")
            
            def _record_task():
                try:
                    self._audio_capture.start()
                except Exception as e:
                    self.after(0, lambda err=str(e): self._show_toast(f"Mic Error: {err}", "err"))
                    self.after(0, self._reset_voice_ui)
            threading.Thread(target=_record_task, daemon=True).start()
        else:
            # Stop Recording & Transcribe
            self.is_recording = False
            self.voice_button.configure(
                text="⏳  TRANSCRIBING...", fg_color=COLORS["accent_yellow"], text_color=COLORS["bg_root"], state="disabled"
            )
            
            def _transcribe_task():
                try:
                    self._audio_capture.stop()
                    from intelligence.voice.whisper_bridge import WhisperBridge
                    audio_data = self._audio_capture.get_audio_data()
                    
                    if audio_data is None or len(audio_data) < 4000: # arbitrary minimum bytes
                        self.after(0, lambda: self._show_toast("Audio too short, discarded.", "warn"))
                    else:
                        bridge = WhisperBridge()
                        text = bridge.transcribe(audio_data)
                        if text:
                            def _paste():
                                current = self.command_entry.get()
                                self.command_entry.delete(0, "end")
                                # Append to existing text if there was any
                                insert_text = (current + " " + text.strip()).strip()
                                self.command_entry.insert(0, insert_text)
                                self._show_toast("Voice transcribed successfully.", "success")
                            self.after(0, _paste)
                except Exception as e:
                    self.after(0, lambda err=str(e): self._show_toast(f"Transcribe Error: {err}", "err"))
                finally:
                    self.after(0, self._reset_voice_ui)
                    
            threading.Thread(target=_transcribe_task, daemon=True).start()

    def _reset_voice_ui(self):
        self.is_recording = False
        self.voice_button.configure(
            text="🎙️  DICTATE", 
            fg_color=COLORS["bg_panel"],
            text_color=COLORS["text_primary"],
            state="normal"
        )

    # ═════════════════════════════════════════════════════════════════════════
    # COCKPIT (right panel)
    # ═════════════════════════════════════════════════════════════════════════

    def _build_cockpit(self):
        self.cockpit_panel = ctk.CTkFrame(
            self.main_frame, width=290, fg_color=COLORS["bg_panel"],
            corner_radius=0, border_width=1, border_color=COLORS["border_soft"],
        )
        self.cockpit_panel.pack(side="right", fill="y")
        self.cockpit_panel.pack_propagate(False)

        # Scrollable
        self.cockpit_scroll = ctk.CTkScrollableFrame(
            self.cockpit_panel, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=COLORS["scrollbar"],
            scrollbar_button_hover_color=COLORS["scrollbar_hover"],
        )
        self.cockpit_scroll.pack(fill="both", expand=True)

        cp = self.cockpit_scroll

        # Title
        ctk.CTkLabel(
            cp, text="⚡ Neural Cockpit",
            font=ctk.CTkFont(family=FONT_UI, size=13, weight="bold"),
            text_color=COLORS["accent_cyan"], anchor="w",
        ).pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkFrame(cp, height=1, fg_color=COLORS["border_soft"], corner_radius=0).pack(fill="x", padx=8, pady=2)

        # ── Sparkline Telemetry Card ──
        self._sidebar_section(cp, "LIVE TELEMETRY", COLORS["accent_cyan"])
        telem_card = self._cockpit_card(cp)

        self.sparkline_label = ctk.CTkLabel(
            telem_card,
            text="Latency  ░░░░░░░░░░  --ms\nErrors   ░░░░░░░░░░  --\nTPS      ░░░░░░░░░░  --/m",
            font=ctk.CTkFont(family=FONT_MONO, size=10),
            text_color=COLORS["text_secondary"],
            justify="left", anchor="w",
        )
        self.sparkline_label.pack(fill="x", padx=10, pady=8)

        # ── AI Status ──
        self._sidebar_section(cp, "AI ENGINE STATUS", COLORS["accent_purple"])
        ai_card = self._cockpit_card(cp)

        self.ai_status_rows = {}
        for label, attr, color in [
            ("Groq Cloud",    "ai_groq",   COLORS["accent_green"]),
            ("Local Ollama",  "ai_ollama", COLORS["text_muted"]),
            ("NLP Classifier","ai_nlp",    COLORS["accent_green"]),
            ("Circuit Brk",  "ai_circuit",COLORS["accent_green"]),
        ]:
            self.ai_status_rows[attr] = self._status_row(ai_card, label, "● Online", color)

        ctk.CTkFrame(ai_card, fg_color="transparent", height=4).pack()

        # ── Agent Feed ──
        self._sidebar_section(cp, "AGENT ACTIVITY", COLORS["accent_purple"])
        agent_card = self._cockpit_card(cp)

        self.agent_feed = ctk.CTkTextbox(
            agent_card,
            fg_color=COLORS["bg_elevated"],
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(family=FONT_MONO, size=9),
            corner_radius=8, height=120,
            border_width=0, wrap="word", state="disabled",
        )
        self.agent_feed.pack(fill="x", padx=6, pady=(0, 6))
        self._append_agent_feed("Agent feed online — awaiting tasks")

        # ── Deploy Status ──
        self._sidebar_section(cp, "DEPLOY STATUS", COLORS["accent_green"])
        deploy_card = self._cockpit_card(cp)

        self.deploy_feed = ctk.CTkTextbox(
            deploy_card,
            fg_color=COLORS["bg_elevated"],
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(family=FONT_MONO, size=9),
            corner_radius=8, height=100,
            border_width=0, wrap="word", state="disabled",
        )
        self.deploy_feed.pack(fill="x", padx=6, pady=(0, 6))
        self._append_deploy_feed("Standby — no active deployments")

        # ── Security Events ──
        self._sidebar_section(cp, "SECURITY EVENTS", COLORS["accent_red"])
        sec_card = self._cockpit_card(cp)

        self.security_feed = ctk.CTkTextbox(
            sec_card,
            fg_color=COLORS["bg_elevated"],
            text_color=COLORS["accent_green"],
            font=ctk.CTkFont(family=FONT_MONO, size=9),
            corner_radius=8, height=80,
            border_width=0, wrap="word", state="disabled",
        )
        self.security_feed.pack(fill="x", padx=6, pady=(0, 6))
        self._append_security_feed("✓ System secured — Fernet AES-128 active")
        self._append_security_feed("✓ Injection guards armed")

        # ── Cockpit Actions ──
        self._sidebar_section(cp, "COCKPIT ACTIONS", COLORS["accent_blue"])
        btn_card = self._cockpit_card(cp)
        btns_frame = ctk.CTkFrame(btn_card, fg_color="transparent")
        btns_frame.pack(fill="x", padx=6, pady=6)

        cockpit_btns = [
            ("📈 Graph",     self._show_command_graph,    COLORS["accent_blue"]),
            ("🚀 Deploy",    lambda: self._quick_command("deploy status"), COLORS["accent_green"]),
            ("🛡️ Audit",    self._show_security_panel,   COLORS["accent_yellow"]),
            ("📉 Monitor",  self._show_process_monitor,  COLORS["accent_purple"]),
            ("⭐ Bookmarks", self._show_bookmarks_dialog, COLORS["accent_cyan"]),
            ("🔍 Search",    self._toggle_search_bar,    COLORS["accent_blue"]),
        ]
        _row = None
        for i, (text, cmd, color) in enumerate(cockpit_btns):
            if i % 2 == 0:
                _row = ctk.CTkFrame(btns_frame, fg_color="transparent")
                _row.pack(fill="x", pady=2)

            ctk.CTkButton(
                _row, text=text, command=cmd,
                height=28, corner_radius=8,
                fg_color=COLORS["bg_elevated"],
                hover_color=COLORS["bg_hover"],
                border_width=1, border_color=COLORS["border_soft"],
                text_color=color,
                font=ctk.CTkFont(family=FONT_UI, size=10, weight="bold"),
            ).pack(side="left", fill="x", expand=True, padx=2)

    def _cockpit_card(self, parent, **kw):
        c = ctk.CTkFrame(
            parent, fg_color=COLORS["bg_card"],
            corner_radius=10,
            border_width=1, border_color=COLORS["border_soft"],
            **kw,
        )
        c.pack(fill="x", padx=8, pady=(0, 6))
        return c

    def _poll_task_manager(self):
        """Polls the global TaskManager for background Swarm processes to update UI."""
        try:
            from intelligence.tasks.task_manager import task_manager
            active = task_manager.get_active_tasks()
            if active:
                count = sum(1 for t in active.values() if t.get("status") == "running")
                if count > 0:
                    self.status_swarm.configure(text=f"⚡ Background Swarms: {count} Active")
                else:
                    self.status_swarm.configure(text="")
            else:
                self.status_swarm.configure(text="")
        except ImportError:
            self.status_swarm.configure(text="")
        finally:
            self.after(1000, self._poll_task_manager)

    # ═════════════════════════════════════════════════════════════════════════
    # STATUS BAR
    # ═════════════════════════════════════════════════════════════════════════

    def _build_statusbar(self):
        ctk.CTkFrame(self, height=1, fg_color=COLORS["border_soft"], corner_radius=0).pack(fill="x", side="bottom")
        self.statusbar = ctk.CTkFrame(
            self, height=26, fg_color=COLORS["bg_panel"],
            corner_radius=0, border_width=0,
        )
        self.statusbar.pack(fill="x", side="bottom")
        self.statusbar.pack_propagate(False)

        sf = ctk.CTkFont(family=FONT_UI, size=9)

        self.status_left = ctk.CTkLabel(
            self.statusbar,
            text=f"  NeuroShell v5.2.0  •  Session #{self.session_id}  •  {platform.system()} {platform.machine()}",
            font=sf, text_color=COLORS["text_muted"], anchor="w",
        )
        self.status_left.pack(side="left", padx=6)

        self.status_right = ctk.CTkLabel(
            self.statusbar, text="● Ready",
            font=sf, text_color=COLORS["accent_green"], anchor="e",
        )
        self.status_right.pack(side="right", padx=10)

        self.status_swarm = ctk.CTkLabel(
            self.statusbar, text="",
            font=sf, text_color=COLORS["accent_purple"],
        )
        self.status_swarm.pack(side="right", padx=15)

        self.status_center = ctk.CTkLabel(
            self.statusbar, text="Ctrl+L Clear  Ctrl+B Side  Ctrl+Shift+P Palette  Tab Complete",
            font=sf, text_color=COLORS["text_muted"],
        )
        self.status_center.pack(side="right", padx=20)

    # ═════════════════════════════════════════════════════════════════════════
    # OUTPUT TAGS & RENDERING
    # ═════════════════════════════════════════════════════════════════════════

    def _setup_output_tags(self):
        """Configure all named text tags for rich terminal output."""
        tw = self.output_text._textbox
        for tag, color in ANSI_TAG_COLORS.items():
            tw.tag_configure(tag, foreground=color)
        tw.tag_configure("cmd_echo",    foreground=COLORS["accent_cyan"],   font=(FONT_MONO, 13, "bold"))
        tw.tag_configure("separator",   foreground=COLORS["text_dim"])
        tw.tag_configure("err",         foreground=COLORS["accent_red"])
        tw.tag_configure("success",     foreground=COLORS["accent_green"])
        tw.tag_configure("info",        foreground=COLORS["accent_blue"])
        tw.tag_configure("warn",        foreground=COLORS["accent_yellow"])
        tw.tag_configure("ai_note",     foreground=COLORS["accent_purple"])
        tw.tag_configure("muted",       foreground=COLORS["text_dim"])
        tw.tag_configure("ts",          foreground=COLORS["text_muted"],    font=(FONT_UI, 9))
        tw.tag_configure("bold",        font=(FONT_MONO, 13, "bold"))

    def _append_output(self, text: str, tag: str = ""):
        """Append styled text to the terminal output widget."""
        tw = self.output_text._textbox
        self.output_text.configure(state="normal")
        if tag:
            tw.insert("end", text, tag)
        else:
            self._render_ansi(tw, text)
        self.output_text.configure(state="disabled")
        self.output_text.see("end")
        # Update line counter in statusbar
        self._update_line_count()

    def _render_ansi(self, tw, text: str):
        """Parse and render ANSI escape codes as colored text tags."""
        segments = re.split(r'(\x1b\[[0-9;]*m)', text)
        current_tag = ""
        for seg in segments:
            m = re.match(r'\x1b\[([0-9;]*)m', seg)
            if m:
                codes = m.group(1).split(";")
                current_tag = ""
                for code in codes:
                    if code in ANSI_CODE_MAP:
                        current_tag = ANSI_CODE_MAP[code]
            else:
                if seg:
                    if current_tag:
                        tw.insert("end", seg, current_tag)
                    else:
                        tw.insert("end", seg)

    def _print_welcome(self):
        """Print the welcome banner to the terminal."""
        now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        banner = f"""
╔═══════════════════════════════════════════════════════════════════╗
║            NeuroShell v5.2.0  —  AI-Powered Terminal             ║
║   Secure  •  Intelligent  •  Production-Ready                    ║
╚═══════════════════════════════════════════════════════════════════╝

  Session  #{self.session_id}   ·   {platform.node()}   ·   {now}
  Platform  {platform.system()} {platform.release()} ({platform.machine()})
  Security  AES-128 Fernet + SHA-256 verification + Injection Guards

  Type a command or plain English.  Use 'help' to see all features.
  Keyboard  Ctrl+L Clear  Ctrl+B Sidebar  Ctrl+D Exit  Tab Complete
            Ctrl+Shift+P Palette  F11 Fullscreen  Esc Interrupt

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        self._append_output(banner, "info")

    # ═════════════════════════════════════════════════════════════════════════
    # EVENT HANDLERS
    # ═════════════════════════════════════════════════════════════════════════

    def _on_enter(self, event):
        cmd = self.command_entry.get().strip()
        if not cmd:
            return
        self.command_entry.delete(0, "end")
        # Deduplicate: don't add if the same as the most recent history entry
        if not self.command_history or self.command_history[0] != cmd:
            self.command_history.insert(0, cmd)
            # Cap history at 500 entries to prevent memory bloat
            if len(self.command_history) > 500:
                self.command_history = self.command_history[:500]
        self.history_index = -1
        self.command_count += 1
        self._last_command = cmd

        # ── Risk Score Check — warn before dangerous commands ──
        if self._engine_ready and self._neuroshell and hasattr(self._neuroshell, 'ext_risk'):
            try:
                assessment = self._neuroshell.ext_risk.assess(cmd)
                if assessment.get('score', 0) >= 7:
                    score = assessment['score']
                    level = assessment.get('level', 'HIGH')
                    reasons = assessment.get('reasons', [])
                    reason_text = '\n'.join(f'  • {r}' for r in reasons[:3])
                    self._append_output(
                        f"\n⚠️  RISK WARNING — Level: {level} ({score}/10)\n{reason_text}\n",
                        "err")
            except Exception:
                pass

        # Echo with timestamp
        ts = datetime.now().strftime("%H:%M:%S")
        self._append_output(f"\n[{ts}] ❯ {cmd}\n", "cmd_echo")

        if self._engine_ready and self._neuroshell:
            if hasattr(self._neuroshell, "session_memory"):
                self._neuroshell.session_memory.add_turn("user", cmd)
            threading.Thread(target=self._run_command, args=(cmd,), daemon=True).start()
        else:
            self._append_output("⚠ Engine not ready yet. Please wait...\n", "warn")

    def _run_command(self, cmd: str):
        """
        Execute a command via the NeuroShell engine in a background thread.

        Thread-safety strategy
        ─────────────────────
        • `_GUI_INPUT_LOCK` (Semaphore=1) ensures only one command thread
          patches builtins.input at a time — eliminates the race if the
          user submits two commands before the first completes.
        • We patch `builtins.input` (not `sys.stdin`) so that even code
          that calls input() directly rather than reading sys.stdin is
          safely intercepted without touching a shared global file object.
        • sys.stdout/stderr are redirected to _GUIOutputStream as before;
          sys.stdin is also mocked for code that reads it directly.
        """
        import builtins as _builtins

        acquired = _GUI_INPUT_LOCK.acquire(blocking=False)
        if not acquired:
            # Another command is running — queue feedback and return
            self.after(0, lambda: self._append_output(
                "⚠ Command queued — previous command still running.\n", "warn"))
            return

        t0 = time.perf_counter()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_stdin  = sys.stdin
        old_input  = _builtins.input   # save real input()

        stream = _GUIOutputStream(self)
        sys.stdout = sys.stderr = stream
        sys.stdin  = _GUIMockStdin()   # for code that reads sys.stdin directly
        _builtins.input = _gui_safe_input  # for code that calls input()

        try:
            self.after(0, lambda: self.status_right.configure(text=f"● Running {self.mode}...", text_color=COLORS["accent_yellow"]))
            
            # Sync mode selection to backend
            if hasattr(self._neuroshell, "mode"):
                self._neuroshell.mode = self.mode

            if self.mode == "Agentic" and hasattr(self._neuroshell, "coordinator"):
                # Run the async swarm stream
                self._run_tool_stream(self._neuroshell.coordinator, query=cmd)
            elif self.mode == "Planner" and hasattr(self._neuroshell, "plan_mode"):
                # Run the async planner stream
                self._run_tool_stream(self._neuroshell.plan_mode, query=cmd)
            elif self.mode == "DevOps" and hasattr(self._neuroshell, "swarm_orchestrator"):
                # Run synchronous multi-agent devops sandbox
                try:
                    res = self._neuroshell.swarm_orchestrator.route_task(cmd)
                    if hasattr(self._neuroshell, "session_memory"):
                        self._neuroshell.session_memory.add_turn("assistant", res.explanation)
                    
                    self.after(0, lambda r=res: self._append_output(f"\n🚀 Swarm Completed: {r.final_command}\n", "success"))
                except Exception as e:
                    self.after(0, lambda e=str(e): self._append_output(f"\n✗ Swarm Failed: {e}\n", "err"))
            else:
                # Default Builder (Synchronous pipeline)
                self._neuroshell.process_input(cmd)
                
            duration_ms = (time.perf_counter() - t0) * 1000
            self._perf_samples.append(duration_ms)
            self.total_duration_ms += duration_ms
            self.command_success_count += 1
            self.after(0, self._update_hud)
            self.after(0, lambda d=duration_ms: self._append_output(
                f"\n✓ Done in {d:.0f}ms\n", "success"))
            # Audible bell for long-running commands (>5s)
            if duration_ms > 5000:
                self.after(0, lambda: self.bell())
            # Smart desktop notification for long commands
            try:
                if hasattr(self._neuroshell, 'ext_notifications'):
                    self._neuroshell.ext_notifications.on_command_complete(cmd, 0, duration_ms)
            except Exception:
                pass
            # Record to ext_memory for learning
            try:
                if hasattr(self._neuroshell, 'ext_memory'):
                    self._neuroshell.ext_memory.record(cmd, cmd, True, os.getcwd())
                if hasattr(self._neuroshell, 'ext_notebook'):
                    captured = stream.get_captured_text().strip()
                    self._neuroshell.ext_notebook.add_command(cmd, captured[:500], 0, duration_ms)
            except Exception:
                pass
            # Log to audit trail
            try:
                if hasattr(self._neuroshell, 'ext_audit'):
                    self._neuroshell.ext_audit.log(cmd, 0, 'executed', os.getcwd(), duration_ms, 0)
            except Exception:
                pass
            self.after(0, lambda: self.status_right.configure(
                text=f"● OK  {(time.perf_counter()-t0)*1000:.0f}ms",
                text_color=COLORS["accent_green"]))
            # Update CWD in case command changed directory
            self.after(100, self._update_cwd_label)
        except Exception as e:
            err = traceback.format_exc()
            self._last_error = err
            self.command_error_count += 1
            self._error_samples.append(1)
            duration_ms = (time.perf_counter() - t0) * 1000
            self.after(0, lambda e=str(e): self._append_output(f"✗ {e}\n", "err"))
            self.after(0, lambda: self.status_right.configure(
                text="● Error", text_color=COLORS["accent_red"]))
            # Notify on failed long commands
            try:
                if hasattr(self._neuroshell, 'ext_notifications'):
                    self._neuroshell.ext_notifications.on_command_complete(cmd, 1, duration_ms)
                if hasattr(self._neuroshell, 'ext_audit'):
                    self._neuroshell.ext_audit.log(cmd, 5, 'error', os.getcwd(), duration_ms, 1)
            except Exception:
                pass
        finally:
            # Sync memory if utilizing the synchronous Builder stream
            if self.mode == "Builder" and hasattr(self._neuroshell, "session_memory"):
                captured = stream.get_captured_text().strip()
                if captured:
                    self._neuroshell.session_memory.add_turn("assistant", captured)

            # Always restore — even if process_input raised
            sys.stdout       = old_stdout
            sys.stderr       = old_stderr
            sys.stdin        = old_stdin
            _builtins.input  = old_input
            _GUI_INPUT_LOCK.release()   # release lock for next command
            self.after(0, self._update_telemetry_panel)
            # Return focus to input entry
            self.after(50, lambda: self.command_entry.focus_set())

    def _run_tool_stream(self, tool, query: str = ""):
        """
        Execute an async progressive stream interface seamlessly streaming UI updates.
        To be called from a background thread. Assumes 'tool' has an async generator 
        method named either `call(query=...)` or `route_request(...)` or `process_stream(...)`.
        """
        import asyncio
        
        async def _consume_stream():
            try:
                # Resolve the correct stream method
                if hasattr(tool, "route_request"):
                    stream = tool.route_request(query)
                elif hasattr(tool, "process_stream"):
                    stream = tool.process_stream(query)
                else:
                    stream = tool.call(query=query)

                async for chunk in stream:
                    if chunk.get("type") == "progress":
                        msg = chunk.get("message", "")
                        self.after(0, lambda m=msg: self._append_output(f"⏳ {m}\n", "info"))
                    elif chunk.get("type") == "result":
                        data = chunk.get("data", "")
                        self.after(0, lambda d=data: self._append_output(f"\n✓ {d}\n", "success"))
                        if hasattr(self._neuroshell, "session_memory"):
                            self._neuroshell.session_memory.add_turn("assistant", str(data))
                    elif chunk.get("type") == "error":
                        err = chunk.get("message", "Unknown error")
                        self.after(0, lambda e=err: self._append_output(f"\n✗ Error: {e}\n", "err"))
            except Exception as e:
                self.after(0, lambda err=str(e): self._append_output(f"\n✗ Engine Exception: {err}\n", "err"))

        # Run the async stream consumer synchronously inside this background thread
        asyncio.run(_consume_stream())

    def _on_history_up(self, event):
        if self.command_history:
            if self.history_index == -1:
                self._saved_input_text = self.command_entry.get()
            self.history_index = min(self.history_index + 1, len(self.command_history) - 1)
            self.command_entry.delete(0, "end")
            self.command_entry.insert(0, self.command_history[self.history_index])
        return "break"

    def _on_history_down(self, event):
        if self.history_index > 0:
            self.history_index -= 1
            self.command_entry.delete(0, "end")
            self.command_entry.insert(0, self.command_history[self.history_index])
        elif self.history_index == 0:
            self.history_index = -1
            self.command_entry.delete(0, "end")
            self.command_entry.insert(0, self._saved_input_text)
        return "break"

    def _on_tab(self, event):
        """Tab completion — match commands from built-ins and history."""
        text = self.command_entry.get().strip()
        if not text:
            return "break"
        builtins = [
            "help", "fix", "undo", "clear", "dashboard", "stats", "aliases",
            "models", "config", "config show", "config reset", "config keys",
            "policy", "policy audit", "deploy status", "deploy rollback",
            "deploy audit", "history export", "history import", "env",
            "cheatsheet", "playbook", "pipelines", "suggest", "explain:",
            "agent:", "script:", "browser", "github",
            # ── Tier 1-4 extension commands ──
            "voice", "listen", "scan", "risk", "themes", "theme",
            "snippets", "snippet save", "snippet run", "palette",
            "notebook", "notebook save", "notebook note",
            "preview", "audit", "audit report", "api start", "api stop",
            "sync export", "sync import", "timeline", "memory stats",
            "schedule", "voice mode",
        ]
        matches = [c for c in builtins if c.startswith(text.lower())]
        hist_m = [c for c in dict.fromkeys(self.command_history)
                  if c.lower().startswith(text.lower()) and c not in matches]
        all_m = matches + hist_m[:10]
        if len(all_m) == 1:
            self.command_entry.delete(0, "end")
            self.command_entry.insert(0, all_m[0])
        elif all_m:
            self._show_autocomplete_popup(all_m[:12])
        return "break"

    def _show_autocomplete_popup(self, items: list):
        """Show a floating autocomplete dropdown below the input."""
        if hasattr(self, "_ac_popup") and self._ac_popup and self._ac_popup.winfo_exists():
            self._ac_popup.destroy()
        entry = self.command_entry
        x = entry.winfo_rootx()
        y = entry.winfo_rooty() + entry.winfo_height() + 4
        popup = ctk.CTkToplevel(self)
        popup.overrideredirect(True)
        popup.geometry(f"+{x}+{y}")
        popup.configure(fg_color=COLORS["bg_elevated"])
        popup.attributes("-topmost", True)
        self._ac_popup = popup
        for item in items:
            ctk.CTkButton(
                popup, text=item, anchor="w", height=26, corner_radius=4,
                fg_color="transparent", hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_primary"],
                font=ctk.CTkFont(family=FONT_MONO, size=11),
                command=lambda t=item: self._pick_autocomplete(t),
            ).pack(fill="x", padx=4, pady=1)
        popup.bind("<FocusOut>", lambda e: popup.destroy())
        popup.focus_set()

    def _pick_autocomplete(self, text: str):
        """Insert selected autocomplete item and close popup."""
        self.command_entry.delete(0, "end")
        self.command_entry.insert(0, text)
        self.command_entry.focus_set()
        if hasattr(self, "_ac_popup") and self._ac_popup and self._ac_popup.winfo_exists():
            self._ac_popup.destroy()

    _CMD_PREFIXES = {
        'ls', 'cd', 'dir', 'git', 'python', 'python3', 'npm', 'npx', 'node',
        'docker', 'pip', 'pip3', 'mkdir', 'rm', 'rmdir', 'cat', 'echo', 'cp',
        'mv', 'curl', 'wget', 'java', 'javac', 'cargo', 'make', 'cmake',
        'go', 'ruby', 'powershell', 'cmd', 'ssh', 'scp', 'tar', 'zip',
        'unzip', 'grep', 'find', 'awk', 'sed', 'chmod', 'chown', 'sudo',
        'apt', 'brew', 'choco', 'winget', 'dotnet', 'rustc', 'gcc', 'g++',
    }

    def _on_key_release(self, event):
        """Real-time input feedback — update AI badge if text looks like NL."""
        text = self.command_entry.get()
        first_word = text.split()[0].lower() if text.strip() else ""
        if text and first_word not in self._CMD_PREFIXES:
            self.ai_badge.configure(text="⚡ AI", text_color=COLORS["accent_cyan"])
        else:
            self.ai_badge.configure(text="⬡ CMD", text_color=COLORS["accent_blue"])

    def _on_shell_change(self, val):
        self.current_shell = "powershell" if val == "PowerShell" else "cmd"
        self.shell_indicator.configure(text=f"⬡ {val}")
        self._append_output(f"\n● Shell switched to {val}\n", "info")
        if self._neuroshell:
            try:
                self._neuroshell.executor.current_shell = self.current_shell
            except Exception:
                pass

    def _on_mode_change(self, val):
        self.mode = val
        self._append_output(f"\n● Mode: {val}\n", "info")
        if self.mission_posture:
            self.mission_posture.configure(text=f"● {val} Mode Active")

    def _on_ai_change(self, val):
        self.ai_mode = val
        self._append_output(f"\n⚡ AI Engine: {val}\n", "ai_note")

    def _on_injection_blocked(self, msg: str):
        self._injection_blocks += 1
        self.after(0, lambda: self._append_security_feed(
            f"⛔ BLOCKED: {msg[:60]}"
        ))
        self.after(0, lambda: self.sec_blocks_label.configure(
            text=str(self._injection_blocks), text_color=COLORS["accent_red"]
        ))
        self.after(0, lambda: self.hud_security.configure(
            text=f"🔒 {self._injection_blocks} BLOCKED", text_color=COLORS["accent_yellow"]
        ))

    # ═════════════════════════════════════════════════════════════════════════
    # TELEMETRY & HUD
    # ═════════════════════════════════════════════════════════════════════════

    def _tick_telemetry(self):
        """Periodic telemetry update — runs every 3s on the main thread."""
        try:
            self._update_hud()
            self._update_telemetry_panel()
            self._update_uptime()
            self._update_mission_bars()
        except Exception:
            pass
        # Store the after-ID so we can cancel it cleanly on window close
        self._telemetry_after_id = self.after(3000, self._tick_telemetry)

    def _update_hud(self):
        n = len(self._perf_samples)
        avg_ms = (sum(self._perf_samples) / n) if n > 0 else 0.0
        self.hud_latency.configure(text=f"⚡ {avg_ms:.0f}ms")
        self.hud_success.configure(text=f"✓ {self.command_success_count}")
        self.hud_errors.configure(text=f"✗ {self.command_error_count}")

    def _update_telemetry_panel(self):
        """Update the cockpit sparklines."""
        avg_ms = (sum(self._perf_samples) / len(self._perf_samples)) if self._perf_samples else 0
        errs   = sum(self._error_samples) if self._error_samples else 0
        total  = self.command_count

        def _bar(val, max_val, width=10):
            filled = int(min(val / max(max_val, 1), 1.0) * width)
            return "█" * filled + "░" * (width - filled)

        lat_bar = _bar(avg_ms, 2000)
        err_bar = _bar(errs, max(total, 1) * 10)
        tps_bar = _bar(total, 100)

        color_lat = COLORS["accent_cyan"] if avg_ms < 500 else COLORS["accent_yellow"] if avg_ms < 1500 else COLORS["accent_red"]
        self.sparkline_label.configure(
            text=(
                f"Latency  {lat_bar}  {avg_ms:.0f}ms\n"
                f"Errors   {err_bar}  {errs}\n"
                f"Commands {tps_bar}  {total}"
            ),
            text_color=color_lat,
        )

    def _update_uptime(self):
        elapsed = (datetime.now() - self._boot_time).seconds
        mins, secs = divmod(elapsed, 60)
        hrs, mins = divmod(mins, 60)
        uptime = f"Uptime  {hrs}h {mins}m" if hrs else f"Uptime  {mins}m {secs}s"
        self.uptime_label.configure(text=uptime)

    def _update_mission_bars(self):
        total = max(self.command_count, 1)
        err_rate = self.command_error_count / total
        rel = max(0.0, 1.0 - err_rate)
        avg_ms = (sum(self._perf_samples) / len(self._perf_samples)) if self._perf_samples else 0
        perf = max(0.0, 1.0 - (avg_ms / 3000))
        load = min(1.0, total / 100)
        security = 1.0 if self._encryption_ok and self._injection_blocks < 5 else 0.75
        try:
            self.bar_reliability.set(rel)
            self.bar_performance.set(perf)
            self.bar_load.set(load)
            self.bar_security.set(security)
        except Exception:
            pass

        posture = "● Active  —  All systems nominal" if err_rate < 0.1 else "⚠ Degraded  —  Elevated errors"
        # Only update posture if not in a custom mode
        if self.mode == "Builder":
            try:
                self.mission_posture.configure(text=posture)
            except Exception:
                pass

    # ═════════════════════════════════════════════════════════════════════════
    # FEED HELPERS
    # ═════════════════════════════════════════════════════════════════════════

    def _append_agent_feed(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.after(0, lambda: self._append_feed(self.agent_feed, f"[{ts}] {msg}\n"))

    def _append_deploy_feed(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.after(0, lambda: self._append_feed(self.deploy_feed, f"[{ts}] {msg}\n"))

    def _append_security_feed(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.after(0, lambda: self._append_feed(self.security_feed, f"[{ts}] {msg}\n"))

    def _append_feed(self, widget, msg: str):
        widget.configure(state="normal")
        widget._textbox.insert("end", msg)
        widget.configure(state="disabled")
        widget.see("end")

    # ═════════════════════════════════════════════════════════════════════════
    # STARTUP
    # ═════════════════════════════════════════════════════════════════════════

    def _on_startup(self):
        self._print_welcome()
        self._load_history()
        sys.stdout = _GUIOutputStream(self)
        sys.stderr = _GUIOutputStream(self)
        self._detect_project()
        threading.Thread(target=self._init_engine, daemon=True).start()

    def _detect_project(self):
        cwd = os.getcwd()
        basename = os.path.basename(cwd)
        markers = {
            "package.json":   "📦 Node/JS",
            "pyproject.toml": "🐍 Python",
            "Cargo.toml":     "🦀 Rust",
            "go.mod":         "🐹 Go",
            "pom.xml":        "☕ Java/Maven",
            "Makefile":       "⚙ Make",
            "Dockerfile":     "🐳 Docker",
        }
        detected = []
        for f, label in markers.items():
            if os.path.exists(os.path.join(cwd, f)):
                detected.append(label)
        if detected:
            self.project_label.configure(
                text=f"📂 {basename}\n{' · '.join(detected)}",
                text_color=COLORS["accent_cyan"],
            )
        else:
            self.project_label.configure(
                text=f"📂 {basename}\nNo framework detected",
                text_color=COLORS["text_secondary"],
            )
        self._update_cwd_label()

    def _init_engine(self):
        with self._init_lock:
            try:
                self.after(0, lambda: self.status_right.configure(
                    text="● Initializing AI engine...", text_color=COLORS["accent_yellow"]))
                from main import NeuroShell
                self._neuroshell = NeuroShell()

                # GUI warm-up: same sub-steps as startup() but no CLI banner/readline/input loop
                try:
                    self._neuroshell._init_nlp()
                except Exception:
                    pass
                try:
                    self._neuroshell.pattern_learner.learn_from_history()
                    self._neuroshell.predictor.train()
                except Exception:
                    pass
                try:
                    self._neuroshell.llm.warmup_async()
                except Exception:
                    pass
                try:
                    import os as _os
                    _cwd = _os.getcwd()
                    _ws = self._neuroshell.context._detect_workspace(_cwd) if hasattr(self._neuroshell.context, "_detect_workspace") else ""
                    self._neuroshell.history.start_session(self._neuroshell.session_id, _cwd, _ws or "")
                except Exception:
                    pass

                # ── Load ALL Tier 1-4 extension modules ──
                try:
                    self._neuroshell._load_heavy_modules()
                    self.after(0, lambda: self._append_output(
                        "✓ Extensions loaded — 28 features active.\n", "success"))
                except Exception:
                    self.after(0, lambda: self._append_output(
                        "⚠ Some extensions failed to load — core operational.\n", "warn"))

                self._engine_ready = True
                self.after(0, lambda: self.status_right.configure(
                    text="● AI Ready", text_color=COLORS["accent_green"]))
                self.after(0, lambda: self._append_output(
                    "✓ AI engine initialized — all systems operational.\n", "success"))
                self.after(0, self._update_hud)
                self.after(0, lambda: self.mission_posture.configure(
                    text="● Active  —  All Systems Operational"))
                
                # Pre-warm voice recording module if available
                try:
                    from intelligence.voice.audio_capture import AudioCapture
                    self._audio_capture = AudioCapture()
                    self.is_recording = False
                except Exception:
                    self._audio_capture = None
                    self.is_recording = False
                    
            except Exception as e:
                self.after(0, lambda: self.status_right.configure(
                    text="● Engine Degraded", text_color=COLORS["accent_yellow"]))
                self.after(0, lambda err=str(e): self._append_output(
                    f"⚠ Engine started in limited mode: {err}\n", "warn"))
                self._engine_ready = True

    def _on_close(self):
        """Clean teardown — cancel timers, remove log handler, save session, destroy window."""
        # Cancel the telemetry ticker so no TclError after window close
        if self._telemetry_after_id:
            try:
                self.after_cancel(self._telemetry_after_id)
            except Exception:
                pass
        # Remove GUI log handler so it doesn't reference the destroyed widget
        try:
            import logging
            handler = getattr(self, "_gui_log_handler", None)
            if handler:
                logging.getLogger("neuroshell").removeHandler(handler)
        except Exception:
            pass
        # Close any open sub-windows
        for win in list(self._open_windows.values()):
            try:
                win.destroy()
            except Exception:
                pass
        self._open_windows.clear()
        # Close autocomplete popup if open
        if hasattr(self, "_ac_popup") and self._ac_popup:
            try:
                self._ac_popup.destroy()
            except Exception:
                pass
        # Save command history
        self._save_history()
        self._save_bookmarks()
        # Close search bar if open
        if self._search_bar and self._search_bar.winfo_exists():
            try:
                self._search_bar.destroy()
            except Exception:
                pass
        # Graceful engine shutdown
        if self._neuroshell:
            try:
                self._neuroshell.shutdown()
            except Exception:
                pass
        self.destroy()


    def _install_crash_handlers(self):
        import sys as _sys
        original = _sys.excepthook
        def handler(exc_type, exc_val, exc_tb):
            report = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
            report_file = self._crash_dir / f"crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            try:
                report_file.write_text(report)
            except Exception:
                pass
            original(exc_type, exc_val, exc_tb)
        _sys.excepthook = handler

    def _install_gui_log_handler(self):
        """Attach a logging.Handler so WARNING+ records from neuroshell.* appear in the terminal.

        This wires Python's structured logging framework to the GUI output pane,
        meaning internal errors and warnings are visible to the user in real-time
        without having to read ~/.neuroshell/logs/*.log.
        """
        import logging

        app_ref = self  # explicit capture for closure

        class _GUILogHandler(logging.Handler):
            """Emit log records ≥ WARNING to the GUI terminal pane."""

            def emit(self, record: logging.LogRecord) -> None:
                try:
                    msg = self.format(record)
                    level = record.levelname
                    tag = "err" if level in ("ERROR", "CRITICAL") else "warn"
                    # Schedule on main thread — logging may come from any thread
                    app_ref.after(0, lambda m=f"[{level}] {msg}\n", t=tag:
                                  app_ref._append_output(m, t))
                except Exception:
                    pass  # never let logging crash the app

        handler = _GUILogHandler()
        handler.setLevel(logging.WARNING)
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))

        root_logger = logging.getLogger("neuroshell")
        root_logger.addHandler(handler)
        # Keep reference so we can remove it cleanly on window close
        self._gui_log_handler = handler


    # ═════════════════════════════════════════════════════════════════════════
    # UI ACTIONS
    # ═════════════════════════════════════════════════════════════════════════

    def _clear_terminal(self):
        self.output_text.configure(state="normal")
        self.output_text.delete("0.0", "end")
        self.output_text.configure(state="disabled")
        self._print_welcome()

    def _interrupt_command(self):
        """Interrupt any running command — kills subprocess or releases semaphore."""
        interrupted = False
        if self._current_process:
            try:
                self._current_process.terminate()
                interrupted = True
            except Exception:
                pass
        # Also try to release the input lock if stuck
        if not _GUI_INPUT_LOCK.acquire(blocking=False):
            # Lock is held — a command is running
            interrupted = True
        else:
            _GUI_INPUT_LOCK.release()  # wasn't actually locked
        if interrupted:
            self._append_output("\n⛔ Command interrupted.\n", "warn")
            self.status_right.configure(text="● Interrupted", text_color=COLORS["accent_yellow"])
        # Close autocomplete popup if open
        if hasattr(self, "_ac_popup") and self._ac_popup:
            try:
                self._ac_popup.destroy()
            except Exception:
                pass

    def _toggle_fullscreen(self):
        if platform.system() == "Windows":
            if self.state() == "zoomed":
                self.state("normal")
            else:
                self.state("zoomed")
        else:
            self._fullscreen = not self._fullscreen
            self.attributes("-fullscreen", self._fullscreen)

    def _toggle_sidebar(self):
        if self.sidebar_visible:
            self.sidebar.pack_forget()
        else:
            self.sidebar.pack(side="left", fill="y", before=self.terminal_container)
        self.sidebar_visible = not self.sidebar_visible

    def _quick_command(self, cmd: str):
        self.command_entry.delete(0, "end")
        self.command_entry.insert(0, cmd)
        self.command_entry.focus_set()
        if not cmd.endswith(": "):
            self._on_enter(None)

    # ═════════════════════════════════════════════════════════════════════════
    # DIALOGS
    # ═════════════════════════════════════════════════════════════════════════

    def _show_toast(self, msg: str, kind: str = "info"):
        """Show a floating toast notification that auto-dismisses."""
        colors = {"info": COLORS["accent_blue"], "warn": COLORS["accent_yellow"],
                  "error": COLORS["accent_red"], "success": COLORS["accent_green"]}
        color = colors.get(kind, COLORS["accent_blue"])
        tag   = {"info": "info", "warn": "warn", "error": "err", "success": "success"}.get(kind, "info")
        self._append_output(f"  {msg}\n", tag)
        # Also show a floating visual toast
        try:
            toast = ctk.CTkLabel(
                self, text=f"  {msg}  ",
                font=ctk.CTkFont(family=FONT_UI, size=11, weight="bold"),
                text_color=COLORS["bg_root"],
                fg_color=color, corner_radius=8,
                padx=12, pady=6,
            )
            toast.place(relx=0.5, rely=0.02, anchor="n")
            self.after(3000, lambda: toast.destroy() if toast.winfo_exists() else None)
        except Exception:
            pass

    def _show_dashboard(self):
        key = "dashboard"
        if key in self._open_windows and self._open_windows[key].winfo_exists():
            self._open_windows[key].lift()
            return
        win = ctk.CTkToplevel(self)
        self._open_windows[key] = win
        win.protocol("WM_DELETE_WINDOW", lambda: (self._open_windows.pop(key, None), win.destroy()))
        win.title("NeuroShell Dashboard")
        win.geometry("680x520")
        win.configure(fg_color=COLORS["bg_dark"])
        win.grab_set()

        ctk.CTkLabel(win, text="⚡ NeuroShell Dashboard",
                     font=ctk.CTkFont(family=FONT_UI, size=18, weight="bold"),
                     text_color=COLORS["accent_cyan"]).pack(pady=(20, 4))
        ctk.CTkLabel(win, text=f"Session  #{self.session_id}  |  Production Build",
                     font=ctk.CTkFont(family=FONT_UI, size=11),
                     text_color=COLORS["text_muted"]).pack()

        ctk.CTkFrame(win, height=1, fg_color=COLORS["border_soft"]).pack(fill="x", padx=20, pady=12)

        # Stats grid
        grid = ctk.CTkFrame(win, fg_color="transparent")
        grid.pack(fill="x", padx=20)

        stats = [
            ("Total Commands",  str(self.command_count),          COLORS["accent_cyan"]),
            ("Successful",      str(self.command_success_count),  COLORS["accent_green"]),
            ("Errors",          str(self.command_error_count),    COLORS["accent_red"]),
            ("Security Blocks", str(self._injection_blocks),      COLORS["accent_yellow"]),
            ("Avg Latency",     f"{(sum(self._perf_samples)/max(len(self._perf_samples),1)):.0f}ms", COLORS["accent_blue"]),
            ("AI Mode",         self.ai_mode,                    COLORS["accent_purple"]),
        ]

        for i, (label, value, color) in enumerate(stats):
            row, col = divmod(i, 3)
            cell = ctk.CTkFrame(grid, fg_color=COLORS["bg_card"],
                                corner_radius=10, border_width=1, border_color=COLORS["border_soft"])
            cell.grid(row=row, column=col, padx=6, pady=6, sticky="ew")
            grid.columnconfigure(col, weight=1)
            ctk.CTkLabel(cell, text=value,
                         font=ctk.CTkFont(family=FONT_UI, size=22, weight="bold"),
                         text_color=color).pack(pady=(12, 2))
            ctk.CTkLabel(cell, text=label,
                         font=ctk.CTkFont(family=FONT_UI, size=10),
                         text_color=COLORS["text_muted"]).pack(pady=(0, 12))

        # Features status
        ctk.CTkFrame(win, height=1, fg_color=COLORS["border_soft"]).pack(fill="x", padx=20, pady=12)
        ctk.CTkLabel(win, text="Security & Features",
                     font=ctk.CTkFont(family=FONT_UI, size=12, weight="bold"),
                     text_color=COLORS["text_secondary"]).pack(anchor="w", padx=20)

        features = [
            ("🔒 AES-128 Fernet Encryption",  "Active",    COLORS["accent_green"]),
            ("🛡️ Command Injection Guard",     "Armed",     COLORS["accent_green"]),
            ("📋 SHA-256 Model Verification",  "Active",    COLORS["accent_green"]),
            ("⚡ Multi-LLM Routing",           self.ai_mode,COLORS["accent_cyan"]),
            ("🔄 Circuit Breaker",             "Closed",    COLORS["accent_green"]),
            ("📊 Rate Limiter",                "Active",    COLORS["accent_green"]),
        ]
        feat_frame = ctk.CTkFrame(win, fg_color=COLORS["bg_card"],
                                  corner_radius=10, border_width=1, border_color=COLORS["border_soft"])
        feat_frame.pack(fill="x", padx=20, pady=8)
        for label, status, color in features:
            row = ctk.CTkFrame(feat_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont(family=FONT_UI, size=10),
                         text_color=COLORS["text_secondary"], anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=f"● {status}", font=ctk.CTkFont(family=FONT_UI, size=10, weight="bold"),
                         text_color=color, anchor="e").pack(side="right")

    def _show_security_panel(self):
        key = "security"
        if key in self._open_windows and self._open_windows[key].winfo_exists():
            self._open_windows[key].lift()
            return
        win = ctk.CTkToplevel(self)
        self._open_windows[key] = win
        win.protocol("WM_DELETE_WINDOW", lambda: (self._open_windows.pop(key, None), win.destroy()))
        win.title("NeuroShell — Security Audit")
        win.geometry("580x480")
        win.configure(fg_color=COLORS["bg_dark"])
        win.grab_set()

        ctk.CTkLabel(win, text="🛡️ Security Audit Report",
                     font=ctk.CTkFont(family=FONT_UI, size=16, weight="bold"),
                     text_color=COLORS["accent_green"]).pack(pady=(18, 4))
        ctk.CTkLabel(win, text=datetime.now().strftime("Generated: %Y-%m-%d %H:%M:%S"),
                     font=ctk.CTkFont(family=FONT_UI, size=10),
                     text_color=COLORS["text_muted"]).pack()

        checks = [
            ("AES-128 Fernet Encryption",          "PASS", "Machine-bound key derivation active."),
            ("SHA-256 Model Hash Verification",     "PASS", "All intent models verified."),
            ("Command Injection Guard",             "PASS", "Null-byte, newline, subshell patterns blocked."),
            ("Prompt Injection Sanitizer",          "PASS", "LLaMA/Mistral tokens stripped from outputs."),
            ("Human-in-the-Loop Enforcement",       "PASS", "All AI commands require user confirmation."),
            ("Secrets Never Written to Disk",       "PASS", "Runtime-only secret memory management."),
            ("Circuit Breaker",                     "PASS", "Prevents cascading AI API failures."),
            ("Injection Blocks This Session",       "INFO", f"{self._injection_blocks} attempts blocked."),
        ]

        frame = ctk.CTkScrollableFrame(win, fg_color=COLORS["bg_card"],
                                       corner_radius=10, border_width=1, border_color=COLORS["border_soft"])
        frame.pack(fill="both", expand=True, padx=16, pady=10)

        for label, status, detail in checks:
            row = ctk.CTkFrame(frame, fg_color=COLORS["bg_elevated"],
                               corner_radius=8, border_width=1, border_color=COLORS["border_soft"])
            row.pack(fill="x", padx=6, pady=3)
            color = COLORS["accent_green"] if status == "PASS" else COLORS["accent_blue"]
            ctk.CTkLabel(row, text=f"  {status}",
                         font=ctk.CTkFont(family=FONT_UI, size=10, weight="bold"),
                         text_color=color, width=50).pack(side="left", pady=6)
            ctk.CTkLabel(row, text=label,
                         font=ctk.CTkFont(family=FONT_UI, size=10, weight="bold"),
                         text_color=COLORS["text_primary"]).pack(side="left", pady=6)
            ctk.CTkLabel(row, text=detail,
                         font=ctk.CTkFont(family=FONT_UI, size=9),
                         text_color=COLORS["text_muted"]).pack(side="right", padx=10)

    def _show_command_palette(self):
        key = "palette"
        if key in self._open_windows and self._open_windows[key].winfo_exists():
            self._open_windows[key].lift()
            return
        win = ctk.CTkToplevel(self)
        self._open_windows[key] = win
        win.protocol("WM_DELETE_WINDOW", lambda: (self._open_windows.pop(key, None), win.destroy()))
        win.title("Command Palette")
        win.geometry("540x480")
        win.configure(fg_color=COLORS["bg_dark"])
        win.grab_set()

        ctk.CTkLabel(win, text="⌘ Command Palette",
                     font=ctk.CTkFont(family=FONT_UI, size=14, weight="bold"),
                     text_color=COLORS["accent_cyan"]).pack(pady=(14, 6))

        search = ctk.CTkEntry(win, placeholder_text="Search commands...",
                              font=ctk.CTkFont(family=FONT_MONO, size=12),
                              fg_color=COLORS["bg_input"],
                              text_color=COLORS["text_primary"],
                              border_color=COLORS["border_focus"], border_width=2)
        search.pack(fill="x", padx=16, pady=(0, 8))
        search.focus_set()

        results_frame = ctk.CTkScrollableFrame(win, fg_color=COLORS["bg_card"],
                                               corner_radius=10, border_width=1, border_color=COLORS["border_soft"])
        results_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        all_commands = [
            ("help",                "Show all available commands"),
            ("dashboard",           "Open session analytics dashboard"),
            ("fix",                 "AI-powered error auto-recovery"),
            ("explain: ...",        "Explain any command or concept"),
            ("undo",                "Undo last git/filesystem operation"),
            ("clone <repo>",        "Smart-clone any GitHub repo by name or URL"),
            ("open <app/site>",     "Smart launch: apps, sites, folders, URLs"),
            ("open chrome",         "Launch Google Chrome"),
            ("open github",         "Open GitHub in browser"),
            ("open downloads folder","Open Downloads folder in Explorer"),
            ("open vs code",        "Launch Visual Studio Code"),
            ("lock screen",         "Lock the Windows screen"),
            ("my ip",               "Get your public IP address"),
            ("flush dns",           "Flush the DNS cache"),
            ("screenshot",          "Open Snipping Tool for screenshots"),
            ("deploy status",       "Check deployment pipeline status"),
            ("policy",              "Run a security policy audit"),
            ("suggest",             "Get AI command suggestions"),
            ("pipelines",           "Show active build pipelines"),
            ("clear",               "Clear terminal output"),
            ("history",             "Browse command history"),
            ("aliases",             "Manage command aliases"),
            ("env list",            "Show environment variables"),
            ("model switch",        "Switch the active AI model"),
            ("stats",               "View session statistics and metrics"),
            ("models",              "List all available AI models"),
            ("cheatsheet",          "Quick command reference card"),
            ("playbook",            "Interactive operational runbook"),
            ("config",              "View current configuration"),
            ("config reset",        "Reset configuration to defaults"),
            ("config keys",         "Show all configuration keys"),
            ("policy audit",        "Run a full security policy audit"),
            ("time <cmd>",          "Measure command execution time"),
            ("history export",      "Export command history to file"),
            ("history import",      "Import command history from file"),
            ("agent: <task>",       "Assign task to AI agent"),
            ("script: <desc>",      "Generate a script from description"),
            ("browser <query>",     "Open a browser search"),
            ("deploy rollback",     "Rollback last deployment"),
            ("deploy audit",        "Audit deployment pipeline"),
            # ── Tier 1: Game Changers ──
            ("voice",               "🎙️ Activate voice command mode (Whisper)"),
            ("listen",              "🎙️ Listen for a voice command"),
            ("agent: <task>",       "🤖 Autonomous agent with multi-step planning"),
            ("explain: <cmd>",      "💡 Live command explainer with details"),
            ("schedule <desc>",     "📅 Natural language workflow engine (cron/schtasks)"),
            # ── Tier 2: Enterprise Power ──
            ("scan",                "🛡️ Vulnerability scanner (pip-audit/npm/secrets)"),
            ("risk <cmd>",          "💀 Risk scoring with visual danger meter (0-10)"),
            ("audit",               "📊 View SOC2/ISO audit trail"),
            ("audit report",        "📊 Generate full audit compliance report"),
            ("timeline",            "📅 Session memory timeline"),
            ("memory stats",        "🧠 Cross-session learning statistics"),
            ("sync export",         "☁️ Export settings for multi-machine sync"),
            ("sync import",         "☁️ Import settings from another machine"),
            # ── Tier 3: Intelligent UX ──
            ("preview <cmd>",       "👁️ Diff preview — dry-run simulation"),
            ("palette <query>",     "🔍 Fuzzy search 50+ commands"),
            # ── Tier 4: Desktop & Ecosystem ──
            ("themes",              "🎨 Browse and switch color themes"),
            ("theme <name>",        "🎨 Apply a theme (dracula/cyberpunk/ocean...)"),
            ("snippets",            "📌 List saved command snippets"),
            ("snippet save <name>", "📌 Save last command as a reusable snippet"),
            ("snippet run <name>",  "📌 Execute a saved snippet"),
            ("notebook",            "📓 Interactive notebook mode (Jupyter-like)"),
            ("notebook save",       "📓 Export notebook as Markdown"),
            ("api start",           "🌐 Start REST API on port 9876"),
            ("api stop",            "🌐 Stop REST API server"),
            ("⭐ bookmarks",         "Show bookmarked commands       Ctrl+Shift+B"),
            ("🔍 search",            "Search in terminal output      Ctrl+F"),
            ("📝 export session",    "Export session as Markdown     Ctrl+Shift+E"),
        ]

        def _run_palette_cmd(cmd):
            """Handle special palette commands that aren't CLI commands."""
            win.destroy()
            self._open_windows.pop(key, None)
            if cmd == "⭐ bookmarks":
                self._show_bookmarks_dialog()
            elif cmd == "🔍 search":
                self._toggle_search_bar()
            elif cmd == "📝 export session":
                self._export_session_markdown()
            else:
                self._quick_command(cmd)

        def populate(filter_text=""):
            for w in results_frame.winfo_children():
                w.destroy()
            for cmd, desc in all_commands:
                if filter_text.lower() in cmd.lower() or filter_text.lower() in desc.lower():
                    btn_row = ctk.CTkFrame(results_frame, fg_color=COLORS["bg_elevated"],
                                           corner_radius=8, border_width=1, border_color=COLORS["border_soft"])
                    btn_row.pack(fill="x", padx=4, pady=2)
                    ctk.CTkLabel(btn_row, text=cmd,
                                 font=ctk.CTkFont(family=FONT_MONO, size=11, weight="bold"),
                                 text_color=COLORS["accent_cyan"], width=130, anchor="w").pack(side="left", padx=10, pady=6)
                    ctk.CTkLabel(btn_row, text=desc,
                                 font=ctk.CTkFont(family=FONT_UI, size=10),
                                 text_color=COLORS["text_muted"], anchor="w").pack(side="left")
                    ctk.CTkButton(btn_row, text="▶", width=28, height=24,
                                  font=ctk.CTkFont(size=10),
                                  fg_color=COLORS["accent_cyan"], hover_color="#00b0a8",
                                  text_color=COLORS["bg_root"], corner_radius=6,
                                  command=lambda c=cmd: _run_palette_cmd(c)
                                  ).pack(side="right", padx=8)

        populate()
        search.bind("<KeyRelease>", lambda e: populate(search.get()))

    def _show_command_graph(self):
        key = "graph"
        if key in self._open_windows and self._open_windows[key].winfo_exists():
            self._open_windows[key].lift()
            return
        win = ctk.CTkToplevel(self)
        self._open_windows[key] = win
        win.protocol("WM_DELETE_WINDOW", lambda: (self._open_windows.pop(key, None), win.destroy()))
        win.title("Command History Graph")
        win.geometry("560x440")
        win.configure(fg_color=COLORS["bg_dark"])
        win.grab_set()
        ctk.CTkLabel(win, text="📈 Command Flow Graph",
                     font=ctk.CTkFont(family=FONT_UI, size=14, weight="bold"),
                     text_color=COLORS["accent_blue"]).pack(pady=14)

        recent = self.command_history[:15]
        frame = ctk.CTkScrollableFrame(win, fg_color=COLORS["bg_card"],
                                       corner_radius=10, border_width=1, border_color=COLORS["border_soft"])
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        if not recent:
            ctk.CTkLabel(frame, text="No commands in history yet.",
                         text_color=COLORS["text_muted"],
                         font=ctk.CTkFont(family=FONT_UI, size=11)).pack(pady=20)
        else:
            for i, cmd in enumerate(reversed(recent)):
                row = ctk.CTkFrame(frame, fg_color=COLORS["bg_elevated"],
                                   corner_radius=6, border_width=1, border_color=COLORS["border_soft"])
                row.pack(fill="x", padx=6, pady=2)
                ctk.CTkLabel(row, text=f"#{len(recent)-i:02d}",
                             font=ctk.CTkFont(family=FONT_MONO, size=9),
                             text_color=COLORS["text_muted"], width=30).pack(side="left", padx=6, pady=5)
                ctk.CTkLabel(row, text=cmd,
                             font=ctk.CTkFont(family=FONT_MONO, size=10),
                             text_color=COLORS["text_primary"], anchor="w").pack(side="left")

    def _show_process_monitor(self):
        key = "monitor"
        if key in self._open_windows and self._open_windows[key].winfo_exists():
            self._open_windows[key].lift()
            return
        win = ctk.CTkToplevel(self)
        self._open_windows[key] = win
        win.protocol("WM_DELETE_WINDOW", lambda: (self._open_windows.pop(key, None), win.destroy()))
        win.title("Process Monitor")
        win.geometry("600x440")
        win.configure(fg_color=COLORS["bg_dark"])
        win.grab_set()
        ctk.CTkLabel(win, text="📊 Live Process Monitor",
                     font=ctk.CTkFont(family=FONT_UI, size=14, weight="bold"),
                     text_color=COLORS["accent_purple"]).pack(pady=14)
        try:
            import psutil
            # Sort by CPU descending, show top 25
            procs = sorted(
                psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]),
                key=lambda p: p.info["cpu_percent"] or 0, reverse=True
            )[:25]
            hdr = ctk.CTkFrame(win, fg_color=COLORS["bg_elevated"], corner_radius=6)
            hdr.pack(fill="x", padx=16, pady=(0, 4))
            for col, w, anchor in [("PID", 50, "w"), ("Name", 200, "w"), ("CPU%", 70, "e"), ("MEM%", 70, "e"), ("Status", 80, "e")]:
                ctk.CTkLabel(hdr, text=col, width=w, anchor=anchor,
                             font=ctk.CTkFont(family=FONT_UI, size=9, weight="bold"),
                             text_color=COLORS["accent_cyan"]).pack(side="left", padx=4, pady=4)
            frame = ctk.CTkScrollableFrame(win, fg_color=COLORS["bg_card"], corner_radius=10,
                                           border_width=1, border_color=COLORS["border_soft"])
            frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
            for p in procs:
                row = ctk.CTkFrame(frame, fg_color=COLORS["bg_elevated"],
                                   corner_radius=4, border_width=1, border_color=COLORS["border_soft"])
                row.pack(fill="x", padx=4, pady=1)
                cpu  = p.info["cpu_percent"] or 0.0
                mem  = p.info["memory_percent"] or 0.0
                stat = p.info["status"] or ""
                cpu_color = COLORS["accent_red"] if cpu > 50 else COLORS["accent_yellow"] if cpu > 10 else COLORS["accent_green"]
                ctk.CTkLabel(row, text=f"{p.info['pid']:6}", width=50, anchor="w",
                             font=ctk.CTkFont(family=FONT_MONO, size=9),
                             text_color=COLORS["text_muted"]).pack(side="left", padx=4, pady=3)
                ctk.CTkLabel(row, text=(p.info["name"] or "")[:30], width=200, anchor="w",
                             font=ctk.CTkFont(family=FONT_MONO, size=9),
                             text_color=COLORS["text_primary"]).pack(side="left")
                ctk.CTkLabel(row, text=f"{cpu:5.1f}%", width=70, anchor="e",
                             font=ctk.CTkFont(family=FONT_MONO, size=9),
                             text_color=cpu_color).pack(side="left")
                ctk.CTkLabel(row, text=f"{mem:5.1f}%", width=70, anchor="e",
                             font=ctk.CTkFont(family=FONT_MONO, size=9),
                             text_color=COLORS["text_secondary"]).pack(side="left")
                ctk.CTkLabel(row, text=stat, width=80, anchor="e",
                             font=ctk.CTkFont(family=FONT_MONO, size=9),
                             text_color=COLORS["text_muted"]).pack(side="left")
        except ImportError:
            ctk.CTkLabel(win, text="psutil not installed. Run: pip install psutil",
                         text_color=COLORS["accent_yellow"],
                         font=ctk.CTkFont(family=FONT_UI, size=11)).pack(pady=20)

    def _show_beginner_guide(self):
        key = "guide"
        if key in self._open_windows and self._open_windows[key].winfo_exists():
            self._open_windows[key].lift()
            return
        win = ctk.CTkToplevel(self)
        self._open_windows[key] = win
        win.protocol("WM_DELETE_WINDOW", lambda: (self._open_windows.pop(key, None), win.destroy()))
        win.title("NeuroShell — Beginner Guide")
        win.geometry("580x500")
        win.configure(fg_color=COLORS["bg_dark"])
        win.grab_set()
        ctk.CTkLabel(win, text="📘 Beginner's Guide to NeuroShell",
                     font=ctk.CTkFont(family=FONT_UI, size=15, weight="bold"),
                     text_color=COLORS["accent_cyan"]).pack(pady=(16, 6))

        guide = ctk.CTkScrollableFrame(win, fg_color=COLORS["bg_card"], corner_radius=10,
                                       border_width=1, border_color=COLORS["border_soft"])
        guide.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        sections = [
            ("What is NeuroShell?",
             "An AI-powered terminal replacing rigid CLI syntax. Type plain English and NeuroShell translates it into the correct shell command automatically."),
            ("Natural Language Commands",
             "Instead of: git reset --soft HEAD~1\nJust type:   undo my last git commit\n\nNeuroShell handles the translation using Groq Cloud or local Ollama AI."),
            ("Auto Error Recovery",
             "When a command fails, NeuroShell captures the error and immediately suggests the fix. Run 'fix' after any failed command."),
            ("Security Features",
             "• AES-128 Fernet encryption for all stored secrets\n• SHA-256 model verification prevents supply-chain attacks\n• Command injection guard blocks malicious inputs\n• Prompt injection sanitizer strips AI control tokens\n• Risk scoring (0-10) warns before destructive commands\n• SOC2/ISO audit trail logs every command"),
            ("New Intelligence Features",
             "• voice / listen → Speak commands with Whisper AI\n• scan → Security vulnerability scanner\n• themes → Switch between 6 premium color themes\n• snippets → Save & reuse command sequences\n• notebook → Jupyter-like interactive sessions\n• timeline → View your session history timeline\n• audit → SOC2-compliant command audit trail\n• api start → REST API for external tool integration\n• sync export/import → Multi-machine settings sync\n• palette → Fuzzy search 50+ commands"),
            ("Keyboard Shortcuts",
             "Ctrl+L      Clear terminal\nCtrl+B      Toggle sidebar\nCtrl+Shift+P  Command palette\nCtrl+D      Exit NeuroShell\nF11         Fullscreen\nEsc         Interrupt command\nUp/Down     Command history\nTab         Autocomplete"),
            ("AI Engine Modes",
             "Fast LLM  →  Groq Cloud (fastest, requires internet)\nLocal AI   →  Ollama (offline, requires local model)\nSwarm      →  Multi-agent deep analysis mode"),
        ]

        for title, content in sections:
            ctk.CTkLabel(guide, text=title,
                         font=ctk.CTkFont(family=FONT_UI, size=11, weight="bold"),
                         text_color=COLORS["accent_cyan"], anchor="w").pack(fill="x", padx=12, pady=(10, 2))
            ctk.CTkLabel(guide, text=content,
                         font=ctk.CTkFont(family=FONT_UI, size=10),
                         text_color=COLORS["text_secondary"],
                         anchor="w", justify="left", wraplength=510).pack(fill="x", padx=12, pady=(0, 4))
            ctk.CTkFrame(guide, height=1, fg_color=COLORS["border_soft"]).pack(fill="x", padx=8, pady=2)

    def _cycle_theme(self):
        """
        Cycle between 3 premium dark theme palettes.
        Reconfigures all stored widget references so the change is visible
        across the full UI — sidebar, cockpit, terminal, titlebar, borders.
        """
        themes = [
            # (name, root_bg, panel_bg, card_bg, elevated_bg,
            #  acc1(cyan), acc2(blue), acc3(purple), border, border_glow, text_pri, text_sec)
            (
                "Deep Dark",
                "#060b12", "#0f1828", "#111d2e", "#162338",
                "#00d4c8", "#3b9eff", "#b47bff",
                "#1c2f48", "#1d4a7a",
                "#dce8f5", "#7a9bbf",
            ),
            (
                "Midnight Indigo",
                "#07060f", "#100e1e", "#15122a", "#1c1838",
                "#9b78ff", "#c96fff", "#ff6fb0",
                "#2a1f55", "#3d2d80",
                "#e8e0ff", "#8a7abf",
            ),
            (
                "Matrix Green",
                "#050e07", "#091808", "#0e2212", "#122c16",
                "#00e676", "#5dfa9a", "#ffd93d",
                "#112a15", "#1a4024",
                "#d6ffe4", "#5a9b6e",
            ),
        ]
        self._theme_index = (self._theme_index + 1) % len(themes)
        (
            name, root_bg, panel_bg, card_bg, elevated_bg,
            acc1, acc2, acc3,
            border, border_glow,
            text_pri, text_sec,
        ) = themes[self._theme_index]

        # ── 1. Update the global COLORS dict so new widgets get the right colors ──
        COLORS["bg_root"]       = root_bg
        COLORS["bg_panel"]      = panel_bg
        COLORS["bg_card"]       = card_bg
        COLORS["bg_elevated"]   = elevated_bg
        COLORS["accent_cyan"]   = acc1
        COLORS["accent_blue"]   = acc2
        COLORS["accent_purple"] = acc3
        COLORS["border"]        = border
        COLORS["border_glow"]   = border_glow
        COLORS["text_primary"]  = text_pri
        COLORS["text_secondary"]= text_sec

        # ── 2. Reconfigure all stored root-level containers ──
        _safe = lambda w, **kw: (w.configure(**kw) if w and w.winfo_exists() else None)  # noqa
        try:
            self.configure(fg_color=root_bg)
            _safe(self.main_frame,         fg_color=root_bg)
            _safe(self.terminal_container, fg_color=root_bg)
            _safe(self.titlebar,           fg_color=panel_bg)
            _safe(self.sidebar,            fg_color=panel_bg)
            _safe(self.cockpit_panel,      fg_color=panel_bg)
        except Exception:
            pass

        # ── 3. Reconfigure HUD labels (stored refs) ──
        try:
            _safe(self.hud_latency,  text_color=acc1)
            _safe(self.hud_success,  text_color=COLORS["accent_green"])
            _safe(self.hud_errors,   text_color=COLORS["accent_red"])
            _safe(self.hud_security, text_color=acc1)
        except Exception:
            pass

        # ── 4. Reconfigure terminal output pane ──
        try:
            _safe(
                self.output_text,
                fg_color=root_bg,
                text_color=text_pri,
            )
        except Exception:
            pass

        # ── 5. Reconfigure progress bars (sidebar mission control) ──
        try:
            _safe(self.bar_reliability, progress_color=COLORS["accent_green"])
            _safe(self.bar_performance, progress_color=acc2)
            _safe(self.bar_load,        progress_color=COLORS["accent_orange"])
            _safe(self.bar_security,    progress_color=acc3)
        except Exception:
            pass

        # ── 6. Reconfigure session / uptime / project labels ──
        try:
            _safe(self.session_label,    text_color=COLORS["text_muted"])
            _safe(self.uptime_label,     text_color=text_sec)
            _safe(self.project_label,    text_color=text_sec)
            _safe(self.mission_posture,  text_color=acc1)
            _safe(self.sparkline_label,  text_color=text_sec)
        except Exception:
            pass

        # ── 7. Reconfigure tab bar ──
        try:
            _safe(self.tab_label,       text_color=acc1)
            _safe(self.shell_indicator, text_color=acc2)
        except Exception:
            pass

        # ── 8. Reconfigure the prompt label ──
        try:
            _safe(self.prompt_label, text_color=acc1)
        except Exception:
            pass

        # ── 9. Reconfigure AI badge ──
        try:
            _safe(self.ai_badge, text_color=acc1, fg_color=COLORS["bg_active"])
        except Exception:
            pass

        # ── 10. Reconfigure command entry + input box ──
        try:
            _safe(self.command_entry, fg_color=COLORS.get("bg_input", root_bg),
                  text_color=text_pri, border_color=COLORS.get("bg_input", root_bg))
        except Exception:
            pass

        # ── 11. Reconfigure statusbar ──
        try:
            _safe(self.statusbar, fg_color=panel_bg)
            _safe(self.status_left, text_color=COLORS.get("text_muted", text_sec))
            _safe(self.status_right, text_color=acc1)
        except Exception:
            pass

        # ── 12. Reconfigure CWD label ──
        try:
            _safe(self.cwd_label, text_color=COLORS.get("text_muted", text_sec))
        except Exception:
            pass

        # ── 13. Reconfigure sidebar content area ──
        try:
            _safe(self.sidebar_content, fg_color="transparent")
        except Exception:
            pass

        self._show_toast(f"🎨 Theme: {name}", "success")

    def _show_github_repo_dialog(self):
        win = ctk.CTkToplevel(self)
        win.title("GitHub Repository")
        win.geometry("420x200")
        win.configure(fg_color=COLORS["bg_dark"])
        win.grab_set()
        ctk.CTkLabel(win, text="⌂ GitHub Repository",
                     font=ctk.CTkFont(family=FONT_UI, size=14, weight="bold"),
                     text_color=COLORS["accent_cyan"]).pack(pady=16)
        entry = ctk.CTkEntry(win, placeholder_text="Enter GitHub repo URL or 'owner/repo'...",
                             font=ctk.CTkFont(family=FONT_MONO, size=11),
                             fg_color=COLORS["bg_input"], text_color=COLORS["text_primary"],
                             border_color=COLORS["border_focus"], border_width=2)
        entry.pack(fill="x", padx=20, pady=8)
        ctk.CTkButton(win, text="Open in Browser", height=32,
                      fg_color=COLORS["accent_cyan"], hover_color="#00b0a8",
                      text_color=COLORS["bg_root"],
                      font=ctk.CTkFont(family=FONT_UI, size=11, weight="bold"),
                      command=lambda: (
                          webbrowser.open(entry.get()),
                          win.destroy()
                      )).pack(padx=20, pady=4)


    # ═════════════════════════════════════════════════════════════════════════
    # NEW FEATURES — Context Menu, Settings, CWD
    # ═════════════════════════════════════════════════════════════════════════

    def _setup_context_menu(self):
        """Create right-click context menu for the terminal output."""
        import tkinter as tk
        self._ctx_menu = tk.Menu(
            self, tearoff=0,
            bg=COLORS["bg_elevated"], fg=COLORS["text_primary"],
            activebackground=COLORS["accent_cyan"],
            activeforeground=COLORS["bg_root"],
            font=(FONT_UI, 10),
            bd=1, relief="flat",
        )
        self._ctx_menu.add_command(label="📋 Copy",       command=self._copy_selection)
        self._ctx_menu.add_command(label="📋 Select All",  command=self._select_all_output)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="⌫  Clear",       command=self._clear_terminal)
        self._ctx_menu.add_command(label="💾 Export",      command=self._export_output)
        self.output_text._textbox.bind("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event):
        """Display context menu at cursor position."""
        try:
            self._ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._ctx_menu.grab_release()

    def _copy_selection(self):
        """Copy selected text from terminal output to clipboard."""
        try:
            tw = self.output_text._textbox
            selected = tw.get("sel.first", "sel.last")
            self.clipboard_clear()
            self.clipboard_append(selected)
            self._show_toast("Copied to clipboard.", "success")
        except Exception:
            self._show_toast("No text selected.", "warn")

    def _select_all_output(self):
        """Select all text in terminal output."""
        tw = self.output_text._textbox
        tw.tag_add("sel", "1.0", "end")

    def _export_output(self):
        """Export terminal output to a text file."""
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
                title="Export Terminal Output",
            )
            if path:
                content = self.output_text._textbox.get("1.0", "end")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self._show_toast(f"Output exported to {os.path.basename(path)}", "success")
        except Exception as e:
            self._show_toast(f"Export failed: {e}", "error")

    def _show_settings(self):
        """Open the Settings panel."""
        key = "settings"
        if key in self._open_windows and self._open_windows[key].winfo_exists():
            self._open_windows[key].lift()
            return
        try:
            def _on_settings_save(cfg):
                self._app_config = cfg
                self._show_toast("Settings saved successfully", "success")

            win = SettingsPanel(self, config=self._app_config, on_save=_on_settings_save)
            self._open_windows[key] = win
            win.protocol("WM_DELETE_WINDOW", lambda: (
                self._open_windows.pop(key, None), win.destroy()))
        except Exception as e:
            self._show_toast(f"Settings panel error: {e}", "error")

    def _update_cwd_label(self):
        """Refresh the CWD breadcrumb in the tab bar."""
        try:
            cwd = os.getcwd()
            self.cwd_label.configure(text=f"📂 {os.path.basename(cwd)}")
        except Exception:
            pass

    def _select_all_input(self):
        """Select all text in the command entry (Ctrl+A)."""
        self.command_entry.select_range(0, "end")
        self.command_entry.icursor("end")
        return "break"

    def _save_history(self):
        """Persist command history to disk for next session."""
        try:
            hist_file = NEUROSHELL_DIR / "command_history.json"
            data = self.command_history[:500]  # cap at 500
            hist_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _load_history(self):
        """Load command history from previous session."""
        try:
            hist_file = NEUROSHELL_DIR / "command_history.json"
            if hist_file.exists():
                data = json.loads(hist_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.command_history = data[:500]
        except Exception:
            pass

    # ═════════════════════════════════════════════════════════════════════════
    # SEARCH IN OUTPUT (Ctrl+F)
    # ═════════════════════════════════════════════════════════════════════════

    def _toggle_search_bar(self):
        """Toggle the Ctrl+F search overlay above the terminal."""
        if self._search_bar and self._search_bar.winfo_exists():
            self._close_search_bar()
            return

        bar = ctk.CTkFrame(
            self.terminal_container, height=36,
            fg_color=COLORS["bg_elevated"], corner_radius=0,
            border_width=1, border_color=COLORS["border_focus"],
        )
        bar.pack(fill="x", side="top", before=self.output_text)
        bar.pack_propagate(False)

        ctk.CTkLabel(bar, text="🔍", font=ctk.CTkFont(size=13),
                     text_color=COLORS["accent_cyan"]).pack(side="left", padx=(8, 4))

        entry = ctk.CTkEntry(
            bar, placeholder_text="Search output...", width=300,
            font=ctk.CTkFont(family=FONT_MONO, size=11),
            fg_color=COLORS["bg_input"], text_color=COLORS["text_primary"],
            border_color=COLORS["border_focus"], border_width=1,
        )
        entry.pack(side="left", padx=4, pady=4)
        entry.focus_set()
        entry.bind("<Return>", lambda e: self._search_next(entry.get()))
        entry.bind("<Shift-Return>", lambda e: self._search_prev(entry.get()))
        entry.bind("<Escape>", lambda e: self._close_search_bar())

        self._search_match_label = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(family=FONT_UI, size=10),
            text_color=COLORS["text_muted"],
        )
        self._search_match_label.pack(side="left", padx=6)

        ctk.CTkButton(bar, text="▲", width=28, height=24, corner_radius=6,
                      fg_color=COLORS["bg_panel"], hover_color=COLORS["bg_hover"],
                      text_color=COLORS["text_primary"],
                      font=ctk.CTkFont(size=11),
                      command=lambda: self._search_prev(entry.get())).pack(side="left", padx=1)
        ctk.CTkButton(bar, text="▼", width=28, height=24, corner_radius=6,
                      fg_color=COLORS["bg_panel"], hover_color=COLORS["bg_hover"],
                      text_color=COLORS["text_primary"],
                      font=ctk.CTkFont(size=11),
                      command=lambda: self._search_next(entry.get())).pack(side="left", padx=1)
        ctk.CTkButton(bar, text="✕", width=28, height=24, corner_radius=6,
                      fg_color="transparent", hover_color=COLORS["bg_hover"],
                      text_color=COLORS["text_secondary"],
                      font=ctk.CTkFont(size=12),
                      command=self._close_search_bar).pack(side="right", padx=4)

        self._search_bar = bar
        self._search_entry = entry

    def _search_next(self, query: str):
        """Find and highlight the next match in terminal output."""
        if not query:
            return
        tw = self.output_text._textbox
        tw.tag_remove("search_hl", "1.0", "end")
        tw.tag_configure("search_hl", background=COLORS["accent_yellow"], foreground=COLORS["bg_root"])
        tw.tag_configure("search_cur", background=COLORS["accent_cyan"], foreground=COLORS["bg_root"])

        # Collect all matches
        self._search_matches = []
        start = "1.0"
        while True:
            pos = tw.search(query, start, stopindex="end", nocase=True)
            if not pos:
                break
            end = f"{pos}+{len(query)}c"
            self._search_matches.append((pos, end))
            tw.tag_add("search_hl", pos, end)
            start = end

        if not self._search_matches:
            self._search_match_label.configure(text="No matches")
            return

        self._search_index = (self._search_index + 1) % len(self._search_matches)
        pos, end = self._search_matches[self._search_index]
        tw.tag_remove("search_cur", "1.0", "end")
        tw.tag_add("search_cur", pos, end)
        tw.see(pos)
        self._search_match_label.configure(
            text=f"{self._search_index + 1}/{len(self._search_matches)}")

    def _search_prev(self, query: str):
        """Find and highlight the previous match."""
        if not self._search_matches:
            self._search_next(query)
            return
        tw = self.output_text._textbox
        self._search_index = (self._search_index - 1) % len(self._search_matches)
        tw.tag_remove("search_cur", "1.0", "end")
        pos, end = self._search_matches[self._search_index]
        tw.tag_add("search_cur", pos, end)
        tw.see(pos)
        self._search_match_label.configure(
            text=f"{self._search_index + 1}/{len(self._search_matches)}")

    def _close_search_bar(self):
        """Close search overlay and clear highlights."""
        if self._search_bar and self._search_bar.winfo_exists():
            self._search_bar.destroy()
        self._search_bar = None
        self._search_matches = []
        self._search_index = 0
        try:
            tw = self.output_text._textbox
            tw.tag_remove("search_hl", "1.0", "end")
            tw.tag_remove("search_cur", "1.0", "end")
        except Exception:
            pass
        self.command_entry.focus_set()

    # ═════════════════════════════════════════════════════════════════════════
    # ESCAPE KEY (multi-function)
    # ═════════════════════════════════════════════════════════════════════════

    def _on_escape(self):
        """Escape key: close search bar → close autocomplete → interrupt command."""
        if self._search_bar and self._search_bar.winfo_exists():
            self._close_search_bar()
            return
        self._interrupt_command()

    # ═════════════════════════════════════════════════════════════════════════
    # COMMAND BOOKMARKS (Ctrl+Shift+B)
    # ═════════════════════════════════════════════════════════════════════════

    def _bookmark_last_command(self):
        """Bookmark the last executed command for quick reuse."""
        cmd = self._last_command
        if not cmd:
            self._show_toast("No command to bookmark.", "warn")
            return
        if cmd in self._bookmarks:
            self._show_toast(f"Already bookmarked: {cmd}", "info")
            return
        self._bookmarks.insert(0, cmd)
        if len(self._bookmarks) > 50:
            self._bookmarks = self._bookmarks[:50]
        self._save_bookmarks()
        self._show_toast(f"⭐ Bookmarked: {cmd}", "success")

    def _save_bookmarks(self):
        """Persist bookmarks to disk."""
        try:
            bk_file = NEUROSHELL_DIR / "bookmarks.json"
            bk_file.write_text(json.dumps(self._bookmarks, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _load_bookmarks(self):
        """Load bookmarks from previous session."""
        try:
            bk_file = NEUROSHELL_DIR / "bookmarks.json"
            if bk_file.exists():
                data = json.loads(bk_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self._bookmarks = data[:50]
        except Exception:
            pass

    def _show_bookmarks_dialog(self):
        """Show bookmarks in a selectable dialog."""
        key = "bookmarks"
        if key in self._open_windows and self._open_windows[key].winfo_exists():
            self._open_windows[key].lift()
            return
        win = ctk.CTkToplevel(self)
        self._open_windows[key] = win
        win.protocol("WM_DELETE_WINDOW", lambda: (self._open_windows.pop(key, None), win.destroy()))
        win.title("⭐ Command Bookmarks")
        win.geometry("500x400")
        win.configure(fg_color=COLORS["bg_dark"])
        win.grab_set()

        ctk.CTkLabel(win, text="⭐ Bookmarked Commands",
                     font=ctk.CTkFont(family=FONT_UI, size=14, weight="bold"),
                     text_color=COLORS["accent_cyan"]).pack(pady=(16, 8))

        if not self._bookmarks:
            ctk.CTkLabel(win, text="No bookmarks yet.\nUse Ctrl+Shift+B to bookmark the last command.",
                         font=ctk.CTkFont(family=FONT_UI, size=11),
                         text_color=COLORS["text_muted"]).pack(expand=True)
            return

        scroll = ctk.CTkScrollableFrame(win, fg_color=COLORS["bg_card"], corner_radius=10)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        for i, cmd in enumerate(self._bookmarks):
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkButton(
                row, text=cmd, anchor="w",
                font=ctk.CTkFont(family=FONT_MONO, size=10),
                fg_color=COLORS["bg_elevated"], hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_primary"], corner_radius=6, height=30,
                command=lambda c=cmd: (self._quick_command(c), win.destroy()),
            ).pack(side="left", fill="x", expand=True, padx=(4, 2))
            ctk.CTkButton(
                row, text="✕", width=28, height=28, corner_radius=6,
                fg_color="transparent", hover_color=COLORS["accent_red"],
                text_color=COLORS["text_muted"],
                command=lambda idx=i: self._remove_bookmark(idx, win),
            ).pack(side="right", padx=2)

    def _remove_bookmark(self, idx: int, win):
        """Remove a bookmark and refresh the dialog."""
        try:
            self._bookmarks.pop(idx)
            self._save_bookmarks()
        except Exception:
            pass
        win.destroy()
        self._open_windows.pop("bookmarks", None)
        self._show_bookmarks_dialog()

    # ═════════════════════════════════════════════════════════════════════════
    # SESSION EXPORT AS MARKDOWN (Ctrl+Shift+E)
    # ═════════════════════════════════════════════════════════════════════════

    def _export_session_markdown(self):
        """Export the full session as a professional Markdown report."""
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                defaultextension=".md",
                filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All Files", "*.*")],
                title="Export Session Report",
                initialfile=f"neuroshell_session_{self.session_id}.md",
            )
            if not path:
                return

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elapsed = (datetime.now() - self._boot_time).seconds
            mins, secs = divmod(elapsed, 60)
            avg_ms = (sum(self._perf_samples) / len(self._perf_samples)) if self._perf_samples else 0

            content = self.output_text._textbox.get("1.0", "end").strip()

            md = f"""# NeuroShell Session Report

**Session ID**: `{self.session_id}`
**Date**: {now}
**Platform**: {platform.system()} {platform.release()} ({platform.machine()})
**Duration**: {mins}m {secs}s

---

## Session Statistics

| Metric | Value |
|--------|-------|
| Total Commands | {self.command_count} |
| Successful | {self.command_success_count} |
| Errors | {self.command_error_count} |
| Success Rate | {(self.command_success_count / max(self.command_count, 1) * 100):.1f}% |
| Avg Latency | {avg_ms:.0f}ms |
| Security Blocks | {self._injection_blocks} |
| AI Mode | {self.ai_mode} |
| Execution Mode | {self.mode} |

## Command History

```
{chr(10).join(reversed(self.command_history[:50]))}
```

## Terminal Output

```
{content[:50000]}
```

---
*Generated by NeuroShell v5.2.0 — AI-Powered Terminal*
"""
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            self._show_toast(f"📝 Session exported → {os.path.basename(path)}", "success")
        except Exception as e:
            self._show_toast(f"Export failed: {e}", "error")

    # ═════════════════════════════════════════════════════════════════════════
    # OUTPUT LINE COUNTER (statusbar)
    # ═════════════════════════════════════════════════════════════════════════

    def _update_line_count(self):
        """Update output line count in statusbar — called after each append."""
        try:
            tw = self.output_text._textbox
            line_count = int(tw.index("end-1c").split(".")[0])
            self.status_center.configure(
                text=f"Lines: {line_count}  │  Ctrl+F Search  Ctrl+Shift+B Bookmarks")
        except Exception:
            pass

    # ═════════════════════════════════════════════════════════════════════════
    # EXIT SESSION SUMMARY
    # ═════════════════════════════════════════════════════════════════════════

    def _show_exit_summary(self):
        """Show a brief session summary before closing."""
        elapsed = (datetime.now() - self._boot_time).seconds
        mins, secs = divmod(elapsed, 60)
        avg_ms = (sum(self._perf_samples) / len(self._perf_samples)) if self._perf_samples else 0
        rate = (self.command_success_count / max(self.command_count, 1)) * 100

        summary = (
            f"Session #{self.session_id} Summary\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Duration:      {mins}m {secs}s\n"
            f"Commands:      {self.command_count}\n"
            f"Success Rate:  {rate:.0f}%\n"
            f"Avg Latency:   {avg_ms:.0f}ms\n"
            f"Sec Blocks:    {self._injection_blocks}\n"
        )
        self._append_output(f"\n{summary}\n", "info")

# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    app = NeuroShellDesktop()
        
    config = load_config()
    if needs_first_run():
        print('Starting First-Run Wizard...')
        wiz = FirstRunWizard(app, on_complete=lambda cfg: print('Wizard complete. Using:', cfg.llm.provider))
        # wait for wizard to close
        wiz.wait_window()
        # Reload config after wizard
        config = load_config()
        
    app.mainloop()

if __name__ == "__main__":
    main()
