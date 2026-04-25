# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Live Config Editor
View and modify configuration from within the REPL.
"""

from typing import Optional
from dataclasses import fields, asdict


class ConfigEditor:
    """
    Live configuration editor for the REPL.

    Features:
    - Show current config as formatted tables
    - Set individual config values at runtime
    - Reset to defaults
    - Show specific sections (llm, safety, ui, etc.)
    """

    # Map of settable config keys with their types and descriptions
    EDITABLE_KEYS = {
        "llm.model": ("str", "Active LLM model name"),
        "llm.temperature": ("float", "LLM temperature (0.0-2.0)"),
        "llm.max_tokens": ("int", "Max response tokens (64-32768)"),
        "llm.timeout": ("int", "LLM timeout in seconds (5-300)"),
        "llm.streaming": ("bool", "Enable streaming output"),
        "llm.cache_enabled": ("bool", "Enable response caching"),
        "safety.enabled": ("bool", "Enable safety checks"),
        "safety.confirm_destructive": ("bool", "Confirm destructive commands"),
        "ui.theme": ("str", "UI theme name"),
        "ui.ghost_text": ("bool", "Show ghost text predictions"),
        "ui.show_confidence": ("bool", "Show confidence scores"),
        "ui.show_provenance": ("bool", "Show provenance tags"),
        "ui.syntax_highlighting": ("bool", "Enable syntax highlighting"),
        "ui.max_output_lines": ("int", "Max output lines to display"),
        "ui.spinner_style": ("str", "Spinner animation style"),
        "nlp.intent_confidence_threshold": ("float", "Intent classification threshold"),
        "hints_enabled": ("bool", "Show contextual hints"),
        "log_level": ("str", "Log level (DEBUG/INFO/WARNING/ERROR)"),
        "max_history": ("int", "Max history records stored"),
        "session_recording": ("bool", "Enable session recording"),
    }

    def __init__(self, config):
        self.config = config

    def show(self, section: str = "") -> str:
        """Show current configuration."""
        config_dict = self.config.to_dict()

        if section:
            # Show specific section
            section_data = config_dict.get(section)
            if section_data is None:
                return f"❌ Unknown section: '{section}'. Available: {', '.join(k for k in config_dict if not k.startswith('_'))}"
            if isinstance(section_data, dict):
                return self._format_section(section, section_data)
            return f"  {section} = {section_data}"

        # Show all sections
        lines = ["\n⚙️  NeuroShell Configuration:\n"]

        for key, value in config_dict.items():
            if key.startswith("_"):
                continue
            if isinstance(value, dict):
                lines.append(self._format_section(key, value))
            else:
                lines.append(f"  {key} = {value}")

        lines.append(f"\n  Profile: {self.config._active_profile or 'default'}")
        lines.append("  Edit: config set <key> <value>")
        return "\n".join(lines)

    def set_value(self, key: str, value_str: str) -> tuple[bool, str]:
        """
        Set a configuration value.
        Returns (success, message).
        """
        if key not in self.EDITABLE_KEYS:
            # Find close matches
            matches = [k for k in self.EDITABLE_KEYS if key in k]
            if matches:
                return False, f"Unknown key '{key}'. Did you mean: {', '.join(matches[:3])}?"
            return False, f"Unknown key '{key}'. Use 'config show' to see available keys."

        type_name, desc = self.EDITABLE_KEYS[key]

        # Convert value
        try:
            if type_name == "bool":
                converted = value_str.lower() in ("true", "1", "yes", "on")
            elif type_name == "int":
                converted = int(value_str)
            elif type_name == "float":
                converted = float(value_str)
            else:
                converted = value_str
        except (ValueError, TypeError):
            return False, f"Invalid value '{value_str}' for {key} (expected {type_name})"

        # Apply
        parts = key.split(".")
        obj = self.config
        for part in parts[:-1]:
            obj = getattr(obj, part, None)
            if obj is None:
                return False, f"Config section not found: {'.'.join(parts[:-1])}"

        old_value = getattr(obj, parts[-1], None)
        setattr(obj, parts[-1], converted)

        # Re-validate
        self.config._validate()

        new_value = getattr(obj, parts[-1])
        return True, f"✅ {key}: {old_value} → {new_value}"

    def reset_to_defaults(self) -> str:
        """Reset all config to defaults (does not save to disk)."""
        from config import Config
        default = Config()

        # Copy default values
        for f in fields(default):
            if f.name.startswith("_"):
                continue
            setattr(self.config, f.name, getattr(default, f.name))

        return "✅ Configuration reset to defaults (not saved to disk). Use 'config save' to persist."

    def save(self) -> str:
        """Save current config to disk."""
        try:
            self.config.save()
            return "💾 Configuration saved to disk."
        except Exception as e:
            return f"❌ Failed to save: {e}"

    def list_editable(self) -> str:
        """List all editable configuration keys."""
        lines = ["\n📝 Editable Configuration Keys:\n"]
        for key, (type_name, desc) in sorted(self.EDITABLE_KEYS.items()):
            # Get current value
            parts = key.split(".")
            obj = self.config
            for part in parts:
                obj = getattr(obj, part, "?")
            lines.append(f"  {key:<40} = {obj:<10}  ({type_name}) {desc}")
        return "\n".join(lines)

    # ── Formatting ──

    def _format_section(self, name: str, data: dict) -> str:
        """Format a config section as a table."""
        lines = [f"\n  [{name}]"]
        for k, v in data.items():
            if isinstance(v, list):
                v = f"[{len(v)} items]"
            lines.append(f"    {k:<30} = {v}")
        return "\n".join(lines)
