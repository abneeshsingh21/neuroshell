# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Theme System — Production Grade
Custom themes via config, auto dark/light, icon sets, 10 built-in themes.
"""

import os
import json
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path
from config import NEUROSHELL_DIR


THEMES_DIR = NEUROSHELL_DIR / "themes"


@dataclass
class Theme:
    """A color theme definition."""
    name: str
    description: str = ""
    is_dark: bool = True
    colors: dict = field(default_factory=dict)
    icons: dict = field(default_factory=dict)

    DEFAULT_COLORS = {
        "primary": "#00d4ff", "secondary": "#ff6ec7",
        "success": "#00ff88", "warning": "#ffaa00",
        "danger": "#ff3333", "muted": "#666666",
        "bg": "#0a0a0f", "text": "#e0e0e0",
        "prompt": "#00d4ff", "git_branch": "#ff6ec7",
        "safe_badge": "#00ff88", "caution_badge": "#ffaa00", "danger_badge": "#ff3333",
        "provenance_llm": "#00d4ff", "provenance_cached": "#00ff88",
        "provenance_pattern": "#ff6ec7", "provenance_history": "#ffaa00",
        "provenance_nlp": "#b388ff",
        "accent": "#b388ff", "border": "#333333",
        "highlight": "#1a1a2e",
    }

    # Unicode icons with fallback
    DEFAULT_ICONS = {
        "success": "✔", "error": "✖", "warning": "⚠",
        "info": "ℹ", "arrow": "→", "bullet": "•",
        "branch": "⎇", "folder": "📁", "file": "📄",
        "lock": "🔒", "key": "🔑", "clock": "⏱",
        "lightning": "⚡", "star": "★", "check": "✓",
        "cross": "✗", "dot": "·", "pipe": "│",
        "corner": "└", "tee": "├",
    }

    ASCII_ICONS = {
        "success": "+", "error": "x", "warning": "!",
        "info": "i", "arrow": "->", "bullet": "*",
        "branch": "#", "folder": "[D]", "file": "[F]",
        "lock": "[L]", "key": "[K]", "clock": "[T]",
        "lightning": "!", "star": "*", "check": "v",
        "cross": "x", "dot": ".", "pipe": "|",
        "corner": "\\", "tee": "+",
    }

    def __post_init__(self):
        for key, default in self.DEFAULT_COLORS.items():
            if key not in self.colors:
                self.colors[key] = default
        if not self.icons:
            self.icons = dict(self.DEFAULT_ICONS)

    def get(self, key: str) -> str:
        return self.colors.get(key, self.DEFAULT_COLORS.get(key, "#ffffff"))

    def icon(self, key: str) -> str:
        return self.icons.get(key, self.DEFAULT_ICONS.get(key, ""))

    def use_ascii_icons(self):
        """Switch to ASCII-safe icons for terminals without Unicode."""
        self.icons = dict(self.ASCII_ICONS)


# ═══════════════════════════════════════════════════════════
# Built-in Themes
# ═══════════════════════════════════════════════════════════

CYBERPUNK = Theme("cyberpunk", "Neon cyberpunk (default)", True, {
    "primary": "#00d4ff", "secondary": "#ff6ec7", "success": "#00ff88",
    "warning": "#ffaa00", "danger": "#ff3333", "muted": "#666666",
    "bg": "#0a0a0f", "text": "#e0e0e0", "prompt": "#00d4ff", "git_branch": "#ff6ec7",
    "accent": "#b388ff", "border": "#1a1a2e",
})

DRACULA = Theme("dracula", "Dracula-inspired dark theme", True, {
    "primary": "#bd93f9", "secondary": "#ff79c6", "success": "#50fa7b",
    "warning": "#f1fa8c", "danger": "#ff5555", "muted": "#6272a4",
    "bg": "#282a36", "text": "#f8f8f2", "prompt": "#bd93f9", "git_branch": "#ff79c6",
    "accent": "#8be9fd", "border": "#44475a",
})

SOLARIZED_DARK = Theme("solarized", "Solarized dark theme", True, {
    "primary": "#268bd2", "secondary": "#2aa198", "success": "#859900",
    "warning": "#b58900", "danger": "#dc322f", "muted": "#586e75",
    "bg": "#002b36", "text": "#839496", "prompt": "#268bd2", "git_branch": "#2aa198",
    "accent": "#6c71c4", "border": "#073642",
})

SOLARIZED_LIGHT = Theme("solarized_light", "Solarized light theme", False, {
    "primary": "#268bd2", "secondary": "#2aa198", "success": "#859900",
    "warning": "#b58900", "danger": "#dc322f", "muted": "#93a1a1",
    "bg": "#fdf6e3", "text": "#657b83", "prompt": "#268bd2", "git_branch": "#2aa198",
    "accent": "#6c71c4", "border": "#eee8d5",
})

MONOKAI = Theme("monokai", "Monokai Pro inspired", True, {
    "primary": "#66d9ef", "secondary": "#f92672", "success": "#a6e22e",
    "warning": "#fd971f", "danger": "#f92672", "muted": "#75715e",
    "bg": "#272822", "text": "#f8f8f2", "prompt": "#66d9ef", "git_branch": "#a6e22e",
    "accent": "#ae81ff", "border": "#3e3d32",
})

MATRIX = Theme("matrix", "Matrix green-on-black", True, {
    "primary": "#00ff41", "secondary": "#008f11", "success": "#00ff41",
    "warning": "#b3ff00", "danger": "#ff0000", "muted": "#003b00",
    "bg": "#000000", "text": "#00ff41", "prompt": "#00ff41", "git_branch": "#008f11",
    "accent": "#33ff77", "border": "#003300",
})

NORD = Theme("nord", "Nord arctic theme", True, {
    "primary": "#88c0d0", "secondary": "#81a1c1", "success": "#a3be8c",
    "warning": "#ebcb8b", "danger": "#bf616a", "muted": "#4c566a",
    "bg": "#2e3440", "text": "#d8dee9", "prompt": "#88c0d0", "git_branch": "#b48ead",
    "accent": "#b48ead", "border": "#3b4252",
})

GRUVBOX = Theme("gruvbox", "Gruvbox warm retro", True, {
    "primary": "#83a598", "secondary": "#d3869b", "success": "#b8bb26",
    "warning": "#fabd2f", "danger": "#fb4934", "muted": "#928374",
    "bg": "#282828", "text": "#ebdbb2", "prompt": "#83a598", "git_branch": "#d3869b",
    "accent": "#fe8019", "border": "#3c3836",
})

CATPPUCCIN = Theme("catppuccin", "Catppuccin Mocha pastel", True, {
    "primary": "#89b4fa", "secondary": "#f38ba8", "success": "#a6e3a1",
    "warning": "#f9e2af", "danger": "#f38ba8", "muted": "#6c7086",
    "bg": "#1e1e2e", "text": "#cdd6f4", "prompt": "#89b4fa", "git_branch": "#cba6f7",
    "accent": "#cba6f7", "border": "#313244",
})

MINIMAL_LIGHT = Theme("minimal", "Minimal light theme", False, {
    "primary": "#0969da", "secondary": "#8250df", "success": "#1a7f37",
    "warning": "#9a6700", "danger": "#cf222e", "muted": "#656d76",
    "bg": "#ffffff", "text": "#1f2328", "prompt": "#0969da", "git_branch": "#8250df",
    "accent": "#8250df", "border": "#d0d7de",
})


class ThemeManager:
    """Manages theme selection, custom themes, and auto dark/light."""

    BUILT_IN = {
        "cyberpunk": CYBERPUNK, "dracula": DRACULA,
        "solarized": SOLARIZED_DARK, "solarized_light": SOLARIZED_LIGHT,
        "monokai": MONOKAI, "matrix": MATRIX,
        "nord": NORD, "gruvbox": GRUVBOX,
        "catppuccin": CATPPUCCIN, "minimal": MINIMAL_LIGHT,
    }

    def __init__(self):
        self._active: Theme = CYBERPUNK
        self._custom_themes: dict[str, Theme] = {}
        THEMES_DIR.mkdir(parents=True, exist_ok=True)
        self._load_custom()

    def get_active(self) -> Theme:
        return self._active

    def set_theme(self, name: str) -> bool:
        if name in self.BUILT_IN:
            self._active = self.BUILT_IN[name]
            return True
        if name in self._custom_themes:
            self._active = self._custom_themes[name]
            return True
        return False

    def auto_detect(self) -> str:
        """Auto-select dark or light based on terminal environment."""
        colorfgbg = os.environ.get("COLORFGBG", "")
        if colorfgbg:
            try:
                bg = int(colorfgbg.split(";")[-1])
                if bg > 8:
                    self.set_theme("minimal")
                    return "minimal"
            except (ValueError, IndexError):
                pass

        term_program = os.environ.get("TERM_PROGRAM", "").lower()
        if "iterm" in term_program or "alacritty" in term_program:
            return self._active.name  # keep dark default

        return self._active.name

    def create_custom(self, name: str, colors: dict, description: str = "", is_dark: bool = True) -> Theme:
        theme = Theme(name=name, description=description, is_dark=is_dark, colors=colors)
        self._custom_themes[name] = theme
        self._save_custom(theme)
        return theme

    def delete_custom(self, name: str) -> bool:
        if name in self._custom_themes:
            del self._custom_themes[name]
            path = THEMES_DIR / f"{name}.json"
            if path.exists():
                path.unlink()
            return True
        return False

    def list_themes(self) -> list[dict]:
        themes = []
        for name, theme in self.BUILT_IN.items():
            themes.append({
                "name": name, "description": theme.description,
                "active": theme.name == self._active.name,
                "type": "built-in", "is_dark": theme.is_dark,
            })
        for name, theme in self._custom_themes.items():
            themes.append({
                "name": name, "description": theme.description,
                "active": theme.name == self._active.name,
                "type": "custom", "is_dark": theme.is_dark,
            })
        return themes

    def export_theme(self, name: str) -> Optional[str]:
        """Export theme as JSON string."""
        theme = self.BUILT_IN.get(name) or self._custom_themes.get(name)
        if theme:
            return json.dumps({
                "name": theme.name, "description": theme.description,
                "is_dark": theme.is_dark, "colors": theme.colors,
            }, indent=2)
        return None

    def import_theme(self, json_str: str) -> Optional[Theme]:
        """Import theme from JSON string."""
        try:
            data = json.loads(json_str)
            return self.create_custom(
                data["name"], data.get("colors", {}),
                data.get("description", ""), data.get("is_dark", True),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def _load_custom(self):
        for file in THEMES_DIR.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                theme = Theme(
                    name=data.get("name", file.stem),
                    description=data.get("description", ""),
                    is_dark=data.get("is_dark", True),
                    colors=data.get("colors", {}),
                )
                self._custom_themes[theme.name] = theme
            except Exception:
                pass

    def _save_custom(self, theme: Theme):
        file = THEMES_DIR / f"{theme.name}.json"
        data = {"name": theme.name, "description": theme.description,
                "is_dark": theme.is_dark, "colors": theme.colors}
        file.write_text(json.dumps(data, indent=2), encoding="utf-8")
