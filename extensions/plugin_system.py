# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Plugin System
Hot-reloadable plugin architecture for extending NeuroShell.
"""

import os
import sys
import re
import json
import hashlib
import importlib
import importlib.util
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable

from config import NEUROSHELL_DIR
from observability.logger import StructuredLogger


PLUGINS_DIR = NEUROSHELL_DIR / "plugins"
TRUSTED_PLUGINS_FILE = NEUROSHELL_DIR / "trusted_plugins.json"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class PluginMeta:
    """Plugin metadata."""
    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    commands: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)


@dataclass
class LoadedPlugin:
    """A loaded plugin instance."""
    meta: PluginMeta
    module: object
    file_path: str
    file_hash: str = ""
    load_time: float = 0
    last_modified: float = 0
    enabled: bool = True
    trusted: bool = False

    @property
    def stale(self) -> bool:
        """Check if plugin file has been modified since load."""
        try:
            mtime = os.path.getmtime(self.file_path)
            return mtime > self.last_modified
        except OSError:
            return False


class PluginSystem:
    """Hot-reloadable plugin manager."""

    def __init__(self):
        self._plugins: dict[str, LoadedPlugin] = {}
        self._hooks: dict[str, list[Callable]] = {}
        self._logger = StructuredLogger("plugins")
        self._allow_untrusted = _env_bool("NEUROSHELL_ALLOW_UNTRUSTED_PLUGINS", default=False)
        self._trusted_plugins: set[str] = self._load_trusted_plugins()
        self._loading_plugin: Optional[str] = None

        # Ensure plugins directory exists
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

    def _load_trusted_plugins(self) -> set[str]:
        """Load trusted plugin identifiers (name or sha256:<hash>) from disk."""
        if not TRUSTED_PLUGINS_FILE.exists():
            return set()
        try:
            data = json.loads(TRUSTED_PLUGINS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return {str(item).strip() for item in data if str(item).strip()}
        except Exception:
            pass
        return set()

    def _save_trusted_plugins(self):
        """Persist trusted plugin identifiers to disk."""
        try:
            TRUSTED_PLUGINS_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = sorted(self._trusted_plugins)
            TRUSTED_PLUGINS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            self._logger.error("trusted_plugins_save_failed", error=str(e))

    def _plugin_sha256(self, file_path: str) -> str:
        """Return sha256 digest for a plugin file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _is_trusted_plugin(self, name: str, file_hash: str) -> bool:
        """Plugin is trusted when name or explicit hash is trusted."""
        return name in self._trusted_plugins or f"sha256:{file_hash}" in self._trusted_plugins

    def trust_plugin(self, plugin_id: str):
        """Trust a plugin by name or by sha256:<hash> identifier."""
        if plugin_id:
            self._trusted_plugins.add(plugin_id.strip())
            self._save_trusted_plugins()

    def untrust_plugin(self, plugin_id: str):
        """Remove a trusted plugin identifier."""
        if plugin_id:
            self._trusted_plugins.discard(plugin_id.strip())
            self._save_trusted_plugins()

    def list_trusted_plugins(self) -> list[str]:
        """Return trusted plugin identifiers."""
        return sorted(self._trusted_plugins)

    def discover(self) -> list[str]:
        """Discover available plugins in the plugins directory."""
        found = []
        if not PLUGINS_DIR.is_dir():
            return found

        for entry in PLUGINS_DIR.iterdir():
            if entry.suffix == ".py" and not entry.name.startswith("_"):
                found.append(entry.stem)
            elif entry.is_dir() and (entry / "__init__.py").exists():
                found.append(entry.name)

        return found

    def load(self, name: str) -> bool:
        """Load a plugin by name."""
        if not re.match(r"^[a-zA-Z0-9_-]+$", name):
            self._logger.error("invalid_plugin_name", name=name)
            return False

        plugin_file = (PLUGINS_DIR / f"{name}.py").resolve()
        plugin_dir = (PLUGINS_DIR / name / "__init__.py").resolve()

        if not (str(plugin_file).startswith(str(PLUGINS_DIR.resolve())) or str(plugin_dir).startswith(str(PLUGINS_DIR.resolve()))):
            self._logger.error("path_traversal_blocked", name=name)
            return False

        if plugin_file.is_file():
            file_path = str(plugin_file)
        elif plugin_dir.is_file():
            file_path = str(plugin_dir)
        else:
            self._logger.error("plugin_not_found", name=name)
            return False

        try:
            file_hash = self._plugin_sha256(file_path)
        except Exception as e:
            self._logger.error("plugin_hash_failed", name=name, error=str(e))
            return False

        trusted = self._is_trusted_plugin(name, file_hash)
        if not trusted and not self._allow_untrusted:
            self._logger.warn(
                "plugin_blocked_untrusted",
                name=name,
                hint="Run trust_plugin('<name>') or set NEUROSHELL_ALLOW_UNTRUSTED_PLUGINS=true",
            )
            return False

        try:
            spec = importlib.util.spec_from_file_location(f"neuroshell_plugin_{name}", file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Extract metadata
            meta = PluginMeta(name=name)
            if hasattr(module, "PLUGIN_META"):
                pm = module.PLUGIN_META
                meta.version = pm.get("version", "1.0.0")
                meta.author = pm.get("author", "")
                meta.description = pm.get("description", "")
                meta.commands = pm.get("commands", [])
                meta.capabilities = pm.get("capabilities", ["execute"])
                meta.hooks = pm.get("hooks", [])
            else:
                meta.capabilities = ["execute"]

            loaded = LoadedPlugin(
                meta=meta,
                module=module,
                file_path=file_path,
                file_hash=file_hash,
                load_time=time.time(),
                last_modified=os.path.getmtime(file_path),
                trusted=trusted,
            )

            self._plugins[name] = loaded

            # Register hooks
            if hasattr(module, "register_hooks"):
                self._loading_plugin = name
                try:
                    module.register_hooks(self)
                finally:
                    self._loading_plugin = None

            # Call init
            if hasattr(module, "on_load"):
                module.on_load()

            self._logger.info("plugin_loaded", name=name, version=meta.version)
            return True

        except Exception as e:
            self._logger.error("plugin_load_failed", name=name, error=str(e))
            return False

    def unload(self, name: str) -> bool:
        """Unload a plugin."""
        plugin = self._plugins.get(name)
        if not plugin:
            return False

        # Call cleanup
        if hasattr(plugin.module, "on_unload"):
            try:
                plugin.module.on_unload()
            except Exception:
                pass

        # Remove hooks
        for hook_name, callbacks in self._hooks.items():
            self._hooks[hook_name] = [cb for cb in callbacks if not self._belongs_to(cb, name)]

        del self._plugins[name]
        self._logger.info("plugin_unloaded", name=name)
        return True

    def reload(self, name: str) -> bool:
        """Hot-reload a plugin."""
        self.unload(name)
        return self.load(name)

    def reload_stale(self) -> list[str]:
        """Reload all plugins whose files have changed."""
        reloaded = []
        for name, plugin in list(self._plugins.items()):
            if plugin.stale:
                if self.reload(name):
                    reloaded.append(name)
        return reloaded

    def load_all(self) -> int:
        """Load all discovered plugins. Returns count loaded."""
        count = 0
        for name in self.discover():
            if self.load(name):
                count += 1
        return count

    def register_hook(self, hook_name: str, callback: Callable):
        """Register a hook callback."""
        plugin_name = self._loading_plugin or self._plugin_name_from_callback(callback)
        if plugin_name:
            plugin = self._plugins.get(plugin_name)
            if plugin and not self._can_register_hook(plugin, hook_name):
                self._logger.warn(
                    "plugin_hook_blocked",
                    plugin=plugin_name,
                    hook=hook_name,
                    reason="missing hooks capability or hook not allowed",
                )
                return

        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append(callback)

    def trigger_hook(self, hook_name: str, **kwargs) -> list:
        """Trigger all callbacks for a hook. Returns list of results."""
        results = []
        for callback in self._hooks.get(hook_name, []):
            try:
                result = callback(**kwargs)
                if result is not None:
                    results.append(result)
            except Exception as e:
                self._logger.error("hook_error", hook=hook_name, error=str(e))
        return results

    def execute_command(self, name: str, command: str, args: list[str] = None) -> Optional[str]:
        """Execute a plugin command."""
        plugin = self._plugins.get(name)
        if not plugin or not plugin.enabled:
            return None

        if "execute" not in set(plugin.meta.capabilities):
            return "Plugin error: execute capability not granted"

        if plugin.meta.commands and command not in set(plugin.meta.commands):
            return f"Plugin error: command '{command}' not allowed"

        if hasattr(plugin.module, "execute"):
            try:
                return plugin.module.execute(command, args or [])
            except Exception as e:
                return f"Plugin error: {e}"
        return None

    def get_all_commands(self) -> dict[str, list[str]]:
        """Get all registered plugin commands."""
        commands = {}
        for name, plugin in self._plugins.items():
            if plugin.enabled and plugin.meta.commands:
                commands[name] = plugin.meta.commands
        return commands

    def list_plugins(self) -> list[dict]:
        """List all loaded plugins with status."""
        result = []
        for name, plugin in self._plugins.items():
            result.append({
                "name": name,
                "version": plugin.meta.version,
                "description": plugin.meta.description,
                "enabled": plugin.enabled,
                "commands": plugin.meta.commands,
                "capabilities": plugin.meta.capabilities,
                "hooks": plugin.meta.hooks,
                "stale": plugin.stale,
                "trusted": plugin.trusted,
            })
        return result

    def _plugin_name_from_callback(self, callback: Callable) -> str:
        """Resolve plugin name from callback module path."""
        callback_module = getattr(callback, "__module__", "")
        for name, plugin in self._plugins.items():
            if callback_module == getattr(plugin.module, "__name__", ""):
                return name
        return ""

    def _can_register_hook(self, plugin: LoadedPlugin, hook_name: str) -> bool:
        """Check if plugin is authorized to register a hook."""
        capabilities = set(plugin.meta.capabilities)
        if "hooks" not in capabilities:
            return False
        if plugin.meta.hooks and hook_name not in set(plugin.meta.hooks):
            return False
        return True

    def _belongs_to(self, callback: Callable, plugin_name: str) -> bool:
        """Check if a callback belongs to a plugin module."""
        module = getattr(callback, "__module__", "")
        return plugin_name in module
