# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Configuration System — Production Grade
TOML config with environment variable overrides, encrypted secrets,
hot-reload, validation, and profile support.
"""

__version__ = "5.0.0"

import os
import platform
import json
import base64
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import time

# Optional strong encryption via cryptography.fernet (AES-128-CBC + HMAC)
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    HAS_FERNET = True
except ImportError:
    HAS_FERNET = False

_config_log = logging.getLogger("neuroshell.config")

try:
    import toml
except ImportError:
    toml = None


# ═══════════════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════════════

NEUROSHELL_DIR = Path.home() / ".neuroshell"
CONFIG_FILE = NEUROSHELL_DIR / "config.toml"
DB_FILE = NEUROSHELL_DIR / "history.db"
LOG_DIR = NEUROSHELL_DIR / "logs"
PLUGINS_DIR = NEUROSHELL_DIR / "plugins"
NLP_MODELS_DIR = NEUROSHELL_DIR / "models"
SESSIONS_DIR = NEUROSHELL_DIR / "sessions"
SECRETS_FILE = NEUROSHELL_DIR / ".secrets.json"
PROFILES_DIR = NEUROSHELL_DIR / "profiles"


# ═══════════════════════════════════════════════════════════
# Environment Variable Mapping
# ═══════════════════════════════════════════════════════════

# Maps NEUROSHELL_* env vars to config paths
ENV_OVERRIDES = {
    "NEUROSHELL_MODEL": "llm.model",
    "NEUROSHELL_LLM_URL": "llm.base_url",
    "NEUROSHELL_LLM_TIMEOUT": ("llm.timeout", int),
    "NEUROSHELL_LLM_TOKENS": ("llm.max_tokens", int),
    "NEUROSHELL_LLM_TEMP": ("llm.temperature", float),
    "NEUROSHELL_SHELL": "default_shell",
    "NEUROSHELL_LOG_LEVEL": "log_level",
    "NEUROSHELL_THEME": "ui.theme",
    "NEUROSHELL_SAFETY": ("safety.enabled", lambda v: v.lower() in ("true", "1", "yes")),
    "NEUROSHELL_HISTORY_MAX": ("max_history", int),
    "NEUROSHELL_PROFILE": "_active_profile",
}


# ═══════════════════════════════════════════════════════════
# Config Dataclasses
# ═══════════════════════════════════════════════════════════

@dataclass
class LLMConfig:
    """LLM settings supporting multiple providers."""
    provider: str = "ollama"  # ollama, groq, openai, anthropic, gemini, openrouter
    model: str = "qwen3:4b"
    base_url: str = "http://localhost:11434"
    timeout: int = 30
    max_tokens: int = 512
    temperature: float = 0.3
    retry_count: int = 3
    cache_enabled: bool = True
    cache_ttl: int = 3600
    streaming: bool = True
    airgap_mode: bool = False


@dataclass
class SafetyConfig:
    """Safety checker settings."""
    enabled: bool = True
    confirm_destructive: bool = True
    blocked_patterns: list = field(default_factory=lambda: [
        r"rm\s+-rf\s+/\s*$",
        r"format\s+[a-zA-Z]:",
        r"del\s+/[sS]\s+/[qQ]\s+[cC]:\\",
        r"mkfs\.",
        r"dd\s+if=.+of=/dev/",
        r":\(\)\{.*:\|:.*\}",
    ])
    danger_keywords: list = field(default_factory=lambda: [
        "rm -rf", "format", "del /s", "rmdir /s",
        "drop database", "truncate", "shutdown",
    ])
    audit_log_enabled: bool = True
    whitelist: list = field(default_factory=list)


@dataclass
class NLPConfig:
    """NLP fast layer settings."""
    intent_classifier_enabled: bool = True
    entity_extractor_enabled: bool = True
    semantic_search_enabled: bool = True
    sentiment_enabled: bool = True
    spacy_model: str = "en_core_web_sm"
    embedding_model: str = "all-MiniLM-L6-v2"
    intent_confidence_threshold: float = 0.7


@dataclass
class UIConfig:
    """Terminal UI settings."""
    theme: str = "cyberpunk"
    ghost_text: bool = True
    show_confidence: bool = True
    show_provenance: bool = True
    dashboard_default: bool = False
    vi_mode: bool = False
    syntax_highlighting: bool = True
    show_resource_usage: bool = False
    spinner_style: str = "dots"
    max_output_lines: int = 500


@dataclass
class ExecutorConfig:
    """Command executor settings."""
    default_timeout: int = 300
    max_background_jobs: int = 10
    max_snapshot_size_mb: int = 50
    max_snapshot_count: int = 20
    max_output_buffer_mb: int = 10
    enable_resource_monitoring: bool = True


@dataclass
class HistoryConfig:
    """History store settings."""
    retention_days: int = 90
    fts_enabled: bool = True
    auto_cleanup: bool = True
    export_format: str = "json"


@dataclass
class ResilienceConfig:
    """Resilience and rate limiting settings."""
    llm_rate_limit: int = 60
    llm_rate_period: int = 60
    llm_hard_timeout: int = 60
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: int = 60
    cache_max_entries: int = 200
    audit_max_entries: int = 1000


# ═══════════════════════════════════════════════════════════
# Master Config
# ═══════════════════════════════════════════════════════════

@dataclass
class Config:
    """Master configuration with env overrides and hot-reload."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    nlp: NLPConfig = field(default_factory=NLPConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)

    # General
    default_shell: str = "powershell" if platform.system() == "Windows" else "bash"
    raw_shell_mode: bool = False  # Privacy first: Disables LLM, telemetry, and RAG
    log_level: str = "INFO"
    max_history: int = 10000
    undo_snapshots: int = 10
    session_recording: bool = True
    hints_enabled: bool = True

    # Internal
    _active_profile: str = ""
    _config_file_mtime: float = 0
    _secrets: dict = field(default_factory=dict)

    @classmethod
    def load(cls, profile: str = "") -> "Config":
        """Load config from TOML file, env vars, secrets, with profile support."""
        config = cls()

        # Ensure directories exist
        for d in [NEUROSHELL_DIR, LOG_DIR, PLUGINS_DIR, NLP_MODELS_DIR, SESSIONS_DIR, PROFILES_DIR]:
            d.mkdir(parents=True, exist_ok=True)

        # 1. Load base TOML config
        config._load_toml(CONFIG_FILE)

        # 2. Load profile override if specified
        active_profile = profile or os.environ.get("NEUROSHELL_PROFILE", "")
        if active_profile:
            profile_file = PROFILES_DIR / f"{active_profile}.toml"
            if profile_file.exists():
                config._load_toml(profile_file)
                config._active_profile = active_profile

        # 3. Apply environment variable overrides
        config._apply_env_overrides()

        # 4. Load secrets
        config._load_secrets()

        # 5. Validate
        config._validate()

        # Track file modification time for hot-reload
        if CONFIG_FILE.exists():
            config._config_file_mtime = CONFIG_FILE.stat().st_mtime

        return config

    def _load_toml(self, path: Path):
        """Load and apply a TOML config file."""
        if path.exists() and toml is not None:
            try:
                data = toml.load(path)
                _apply_dict(self, data)
            except Exception as exc:
                _config_log.warning("Failed to load TOML config %s: %s", path, exc)

    def _apply_env_overrides(self):
        """Apply NEUROSHELL_* environment variables."""
        for env_key, config_path in ENV_OVERRIDES.items():
            value = os.environ.get(env_key)
            if value is None:
                continue

            if isinstance(config_path, tuple):
                path_str, converter = config_path
            else:
                path_str = config_path
                converter = str

            try:
                converted = converter(value)
                _set_nested(self, path_str, converted)
            except (ValueError, TypeError) as exc:
                _config_log.warning("Invalid env override %s=%s: %s", env_key, value, exc)

    def _load_secrets(self):
        """Load secrets — supports Fernet (v2), XOR (v1 migration), and plaintext."""
        if not SECRETS_FILE.exists():
            return
        try:
            raw = SECRETS_FILE.read_text(encoding="utf-8")
            envelope = json.loads(raw)

            if not isinstance(envelope, dict):
                self._secrets = {}
                return

            enc_version = envelope.get("_enc_version", 0)

            if enc_version == 2 and HAS_FERNET:
                # Current format: Fernet AES-128
                token = base64.b64decode(envelope["data"])
                try:
                    self._secrets = json.loads(_fernet_decrypt(token).decode("utf-8"))
                except Exception:
                    # Fallback to legacy deterministic derivation if master key was rotated
                    try:
                        legacy_f = Fernet(base64.urlsafe_b64encode(hashlib.sha256(_get_machine_identity().encode("utf-8")).digest()))
                        self._secrets = json.loads(legacy_f.decrypt(token).decode("utf-8"))
                        self._persist_secrets()
                    except Exception:
                        self._secrets = {}

            elif envelope.get("_encrypted"):
                # Legacy v1 format: XOR — read and immediately re-encrypt with Fernet
                payload = base64.b64decode(envelope["data"])
                legacy_key = _derive_machine_key()
                self._secrets = json.loads(_xor_crypt(payload, legacy_key).decode("utf-8"))
                _config_log.info("Migrating secrets from XOR (v1) → Fernet (v2)")
                # Re-save with Fernet immediately
                self._persist_secrets()

            else:
                # Plaintext legacy — load and auto-upgrade
                self._secrets = envelope
                _config_log.info("Upgrading plaintext secrets → Fernet (v2)")
                self._persist_secrets()

        except Exception as exc:
            _config_log.error("Failed to load secrets: %s", exc)
            self._secrets = {}

    def _validate(self):
        """Validate config values."""
        # Clamp temperature
        self.llm.temperature = max(0.0, min(2.0, self.llm.temperature))
        # Clamp max_tokens
        self.llm.max_tokens = max(64, min(32768, self.llm.max_tokens))
        # Clamp timeout
        self.llm.timeout = max(5, min(300, self.llm.timeout))
        # Ensure log level is valid
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_levels:
            self.log_level = "INFO"

    def save(self):
        """Save current config to TOML file."""
        if toml is None:
            return
        NEUROSHELL_DIR.mkdir(parents=True, exist_ok=True)
        data = _to_dict(self)
        # Remove internal fields
        data.pop("_active_profile", None)
        data.pop("_config_file_mtime", None)
        data.pop("_secrets", None)
        with open(CONFIG_FILE, "w") as f:
            toml.dump(data, f)

    def save_profile(self, profile_name: str):
        """Save current config as a named profile."""
        if toml is None:
            return
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        data = _to_dict(self)
        data.pop("_active_profile", None)
        data.pop("_config_file_mtime", None)
        data.pop("_secrets", None)
        with open(PROFILES_DIR / f"{profile_name}.toml", "w") as f:
            toml.dump(data, f)

    def hot_reload(self) -> bool:
        """Reload config if file changed. Returns True if reloaded."""
        if not CONFIG_FILE.exists():
            return False
        current_mtime = CONFIG_FILE.stat().st_mtime
        if current_mtime > self._config_file_mtime:
            self._load_toml(CONFIG_FILE)
            self._apply_env_overrides()
            self._validate()
            self._config_file_mtime = current_mtime
            return True
        return False

    def get_secret(self, key: str, default: str = "") -> str:
        """Get a secret value."""
        return self._secrets.get(key, os.environ.get(key, default))

    def set_secret(self, key: str, value: str):
        """Set and persist a secret with Fernet encryption."""
        self._secrets[key] = value
        self._persist_secrets()

    def save_secret(self, key: str, value: str):
        """Set and persist a secret (alias for set_secret)."""
        return self.set_secret(key, value)

    def _persist_secrets(self):
        """Write secrets to disk using the strongest available encryption with atomic backup."""
        try:
            plaintext = json.dumps(self._secrets).encode("utf-8")
            if HAS_FERNET:
                encrypted = _fernet_encrypt(plaintext)
                envelope = {
                    "_enc_version": 2,
                    "data": base64.b64encode(encrypted).decode("ascii"),
                }
            else:
                # Fallback: XOR (weak but zero-dependency)
                _config_log.warning(
                    "cryptography package not installed — falling back to XOR encryption. "
                    "Run: pip install cryptography"
                )
                legacy_key = _derive_machine_key()
                encrypted = _xor_crypt(plaintext, legacy_key)
                envelope = {
                    "_encrypted": True,
                    "data": base64.b64encode(encrypted).decode("ascii"),
                }

            NEUROSHELL_DIR.mkdir(parents=True, exist_ok=True)
            if SECRETS_FILE.exists():
                try:
                    import shutil
                    shutil.copy2(SECRETS_FILE, SECRETS_FILE.with_suffix(".json.bak"))
                except Exception:
                    pass

            data_bytes = json.dumps(envelope, indent=2).encode("utf-8")
            if platform.system() != "Windows":
                fd = os.open(str(SECRETS_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with open(fd, "wb") as f:
                    f.write(data_bytes)
            else:
                SECRETS_FILE.write_bytes(data_bytes)
        except Exception as exc:
            _config_log.error("Failed to save secrets: %s", exc)

    def list_profiles(self) -> list[str]:
        """List available config profiles."""
        if not PROFILES_DIR.exists():
            return []
        return [p.stem for p in PROFILES_DIR.glob("*.toml")]

    def to_dict(self) -> dict:
        """Export config as dictionary."""
        d = _to_dict(self)
        d.pop("_active_profile", None)
        d.pop("_config_file_mtime", None)
        d.pop("_secrets", None)
        return d

    @property
    def summary(self) -> str:
        """One-line config summary."""
        parts = [
            f"model={self.llm.model}",
            f"shell={self.default_shell}",
            f"theme={self.ui.theme}",
            f"safety={'on' if self.safety.enabled else 'off'}",
        ]
        if self._active_profile:
            parts.insert(0, f"profile={self._active_profile}")
        return " | ".join(parts)


# ═══════════════════════════════════════════════════════════
# Encryption Helpers (zero-dependency)
# ═══════════════════════════════════════════════════════════

def _get_machine_identity() -> str:
    """Get a stable machine identity string. Safe in Docker/WSL/CI/macOS environments."""
    # Check for persistent OS machine UUID before node/hostname
    machine_id = ""
    sys_name = platform.system()
    if sys_name == "Linux":
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        machine_id = f.read().strip()
                        if machine_id:
                            break
                except Exception:
                    pass
    elif sys_name == "Darwin":
        try:
            import subprocess
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                text=True, timeout=2,
                stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    machine_id = line.split("=")[-1].strip().strip('"')
                    break
        except Exception:
            pass

    try:
        username = os.getlogin()
    except (OSError, AttributeError):
        username = (
            os.environ.get("USERNAME")
            or os.environ.get("USER")
            or os.environ.get("LOGNAME")
            or "user"
        )
    base_node = machine_id or platform.node()
    return f"{base_node}:{username}:{sys_name}"


def _derive_machine_key() -> bytes:
    """Derive a 32-byte machine-specific key from system identity (legacy XOR use)."""
    identity = _get_machine_identity()
    return hashlib.sha256(identity.encode("utf-8")).digest()


def _get_master_seed() -> bytes:
    """Retrieve or generate a cryptographically secure random master key seed."""
    key_file = NEUROSHELL_DIR / ".master.key"
    try:
        if key_file.exists():
            return key_file.read_bytes().strip()
    except Exception:
        pass
    
    # Generate 32 bytes of secure random material
    raw_seed = base64.urlsafe_b64encode(os.urandom(32))
    try:
        NEUROSHELL_DIR.mkdir(parents=True, exist_ok=True)
        if platform.system() != "Windows":
            fd = os.open(str(key_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with open(fd, "wb") as f:
                f.write(raw_seed)
        else:
            key_file.write_bytes(raw_seed)
            try:
                username = os.environ.get("USERNAME", "")
                if username:
                    import subprocess
                    subprocess.run(
                        ["icacls", str(key_file), "/inheritance:r", "/grant:r", f'"{username}":(R,W)'],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                    )
            except Exception:
                pass
    except Exception as exc:
        _config_log.warning("Could not persist .master.key with restricted permissions: %s", exc)
    return raw_seed


def _derive_fernet_key() -> bytes:
    """Derive a URL-safe base64 Fernet key using PBKDF2HMAC-SHA256.

    Binds the random master key to the local machine identity so secrets are
    both non-portable and cryptographically strong.
    """
    master_seed = _get_master_seed()
    identity = _get_machine_identity().encode("utf-8")
    salt = hashlib.sha256(b"neuroshell-salt-v2:" + identity + b":" + master_seed).digest()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390_000,
    )
    raw_key = kdf.derive(master_seed + identity)
    return base64.urlsafe_b64encode(raw_key)


def _fernet_encrypt(data: bytes) -> bytes:
    """Encrypt data with Fernet (AES-128-CBC + HMAC-SHA256)."""
    f = Fernet(_derive_fernet_key())
    return f.encrypt(data)


def _fernet_decrypt(token: bytes) -> bytes:
    """Decrypt a Fernet token."""
    f = Fernet(_derive_fernet_key())
    return f.decrypt(token)


def _xor_crypt(data: bytes, key: bytes) -> bytes:
    """XOR encrypt/decrypt — kept for legacy migration reads only."""
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def _apply_dict(obj, data: dict):
    """Recursively apply dict values to dataclass."""
    for key, value in data.items():
        if hasattr(obj, key):
            attr = getattr(obj, key)
            if hasattr(attr, "__dataclass_fields__") and isinstance(value, dict):
                _apply_dict(attr, value)
            else:
                setattr(obj, key, value)


def _set_nested(obj, path: str, value):
    """Set a nested attribute given a dot-separated path."""
    parts = path.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part, None)
        if obj is None:
            return
    setattr(obj, parts[-1], value)


def _to_dict(obj) -> dict:
    """Convert dataclass to dict recursively."""
    result = {}
    for key, val in obj.__dataclass_fields__.items():
        v = getattr(obj, key)
        if hasattr(v, "__dataclass_fields__"):
            result[key] = _to_dict(v)
        else:
            result[key] = v
    return result


def load_config(profile: str = "") -> Config:
    """Load configuration. Convenience alias for Config.load()."""
    return Config.load(profile)
