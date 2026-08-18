# NeuroShell PII Scrubbing Filter
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
"""
Zero-Trust privacy filter that automatically redacts sensitive data
(passwords, API keys, tokens, secrets) from text BEFORE it is sent
to any cloud LLM provider. Runs entirely locally.
"""

import re
from typing import Optional

# Patterns that match common secret formats
_PII_PATTERNS = [
    # AWS Keys
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_ACCESS_KEY]"),
    (re.compile(r"(?:aws_secret_access_key|AWS_SECRET)\s*[=:]\s*\S+", re.I), "[REDACTED_AWS_SECRET]"),
    # Generic API Keys (long hex/base64 strings after key= or token=)
    (re.compile(r"(?:api[_-]?key|apikey|api[_-]?token)\s*[=:]\s*['\"]?\S{20,}['\"]?", re.I), "[REDACTED_API_KEY]"),
    # Bearer tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I), "Bearer [REDACTED_TOKEN]"),
    # GitHub tokens
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"), "[REDACTED_GITHUB_TOKEN]"),
    # OpenAI keys
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED_OPENAI_KEY]"),
    # Anthropic keys
    (re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}"), "[REDACTED_ANTHROPIC_KEY]"),
    # Private keys (PEM)
    (re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC )?PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    # Passwords in connection strings
    (re.compile(r"(?:password|passwd|pwd)\s*[=:]\s*['\"]?\S+['\"]?", re.I), "[REDACTED_PASSWORD]"),
    # Database connection strings
    (re.compile(r"(?:mongodb|postgres|mysql|redis)://\S+:\S+@", re.I), "[REDACTED_DB_CONN]://***@"),
    # Generic secrets in env vars
    (re.compile(r"(?:SECRET|TOKEN|CREDENTIALS?|AUTH)\s*[=:]\s*['\"]?\S{8,}['\"]?", re.I), "[REDACTED_SECRET]"),
    # IP addresses (optional — can be noisy)
    # (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[REDACTED_IP]"),
]


def scrub(text: str) -> str:
    """Redact all detected PII/secrets from text."""
    result = text
    for pattern, replacement in _PII_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def contains_secrets(text: str) -> bool:
    """Check if text contains any detectable secrets."""
    for pattern, _ in _PII_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _scrub_value(value):
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return scrub_dict(value)
    if isinstance(value, list):
        return [_scrub_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(v) for v in value)
    return value


def scrub_dict(data: dict) -> dict:
    """Recursively scrub all string values in a dictionary (including nested lists of dicts)."""
    return {key: _scrub_value(value) for key, value in data.items()}
