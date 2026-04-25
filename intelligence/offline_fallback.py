# NeuroShell Smart Offline Fallback
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
"""
Detects network connectivity loss and seamlessly pivots from cloud
LLM providers to local Ollama. Ensures the AI terminal never stops.
"""

import socket
import logging
import time
from typing import Optional

_log = logging.getLogger("neuroshell.offline_fallback")

# Cloud provider health-check endpoints
_CLOUD_HOSTS = {
    "openai": ("api.openai.com", 443),
    "anthropic": ("api.anthropic.com", 443),
    "gemini": ("generativelanguage.googleapis.com", 443),
    "groq": ("api.groq.com", 443),
    "openrouter": ("openrouter.ai", 443),
}

_OLLAMA_DEFAULT = ("127.0.0.1", 11434)


def check_internet(timeout: float = 2.0) -> bool:
    """Quick TCP probe to detect internet connectivity."""
    for host, port in [("8.8.8.8", 53), ("1.1.1.1", 53)]:
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            return True
        except (socket.timeout, OSError):
            continue
    return False


def check_ollama(host: str = "127.0.0.1", port: int = 11434,
                 timeout: float = 1.0) -> bool:
    """Check if local Ollama is reachable."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (socket.timeout, OSError):
        return False


def check_provider(provider: str, timeout: float = 2.0) -> bool:
    """Check if a specific cloud provider is reachable."""
    endpoint = _CLOUD_HOSTS.get(provider)
    if not endpoint:
        return False
    try:
        sock = socket.create_connection(endpoint, timeout=timeout)
        sock.close()
        return True
    except (socket.timeout, OSError):
        return False


class OfflineFallbackManager:
    """
    Monitors connectivity and manages automatic provider switching.
    
    Usage:
        mgr = OfflineFallbackManager(config)
        provider, reason = mgr.get_active_provider()
    """

    def __init__(self, config):
        self._config = config
        self._last_check = 0.0
        self._check_interval = 30.0  # seconds between checks
        self._is_online = True
        self._ollama_available = False

    def get_active_provider(self) -> tuple[str, str]:
        """
        Returns (provider_name, reason).
        Automatically falls back to 'ollama' if cloud is unreachable.
        """
        current = self._config.llm.provider

        # If already using ollama, no fallback needed
        if current == "ollama":
            return "ollama", "configured"

        # Rate-limit connectivity checks
        now = time.monotonic()
        if now - self._last_check > self._check_interval:
            self._is_online = check_internet()
            self._ollama_available = check_ollama()
            self._last_check = now

        if self._is_online and check_provider(current):
            return current, "online"

        # Cloud is down — try local fallback
        if self._ollama_available:
            _log.warning(
                "Cloud provider '%s' unreachable — falling back to local Ollama",
                current,
            )
            return "ollama", "offline-fallback"

        # Nothing available
        _log.error("No LLM provider available (cloud down + Ollama not running)")
        return "none", "no-provider"

    @property
    def status(self) -> dict:
        return {
            "internet": self._is_online,
            "ollama_local": self._ollama_available,
            "configured_provider": self._config.llm.provider,
        }
