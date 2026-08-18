# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
import re
import pytest

# Python parity implementation of DLPMasker for CI / Backend validation
class PyDLPMasker:
    PATTERNS = [
        ("AWS Access Key", re.compile(r"\b(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b")),
        ("GitHub Token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,255}\b")),
        ("GitHub PAT", re.compile(r"\bgithub_pat_[a-zA-Z0-9_]{82}\b")),
        ("OpenAI Key", re.compile(r"\bsk-(?:proj-|svcacct-)?[a-zA-Z0-9_\-]{32,128}\b")),
        ("Groq Key", re.compile(r"\bgsk_[a-zA-Z0-9]{48,64}\b")),
        ("Anthropic Key", re.compile(r"\bsk-ant-[a-zA-Z0-9_\-]{40,128}\b")),
        ("JWT Bearer", re.compile(r"Bearer\s+(eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+)")),
        ("DB URI", re.compile(r"(postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp)://([^:]+):([^@]+)@")),
        ("Private Key", re.compile(r"-----BEGIN\s+(?:RSA|EC|DSA|OPENSSH|PGP)?\s*PRIVATE KEY[^\r\n]*")),
    ]

    def __init__(self):
        self.enabled = True
        self.unmasked = False
        self.total_masked = 0

    def filter_stream(self, text: str) -> str:
        if not self.enabled or self.unmasked:
            return text

        result = text
        for name, pat in self.PATTERNS:
            def repl(m):
                self.total_masked += 1
                val = m.group(0)
                if "AKIA" in val or "ghp_" in val or "sk-" in val or "gsk_" in val:
                    if len(val) > 8:
                        return val[:4] + "••••••••••••" + val[-4:]
                return f"[🔒 {name} REDACTED]"

            result = pat.sub(repl, result)
        return result


def test_dlp_masker_aws_key():
    masker = PyDLPMasker()
    output = "Configuring profile with AKIAIOSFODNN7EXAMPLE key."
    filtered = masker.filter_stream(output)
    assert "AKIAIOSFODNN7EXAMPLE" not in filtered
    assert "AKIA••••••••••••MPLE" in filtered
    assert masker.total_masked == 1


def test_dlp_masker_github_tokens():
    masker = PyDLPMasker()
    output = "export GITHUB_TOKEN=ghp_123456789012345678901234567890123456"
    filtered = masker.filter_stream(output)
    assert "ghp_123456789012345678901234567890123456" not in filtered
    assert "ghp_••••••••••••3456" in filtered


def test_dlp_masker_openai_key():
    masker = PyDLPMasker()
    key = "sk-proj-" + "a" * 48
    output = f"OPENAI_API_KEY={key}"
    filtered = masker.filter_stream(output)
    assert key not in filtered
    assert "sk-p••••••••••••aaaa" in filtered


def test_dlp_masker_database_url():
    masker = PyDLPMasker()
    output = "DATABASE_URL=postgres://app_user:super_secret_password_123@prod-db.corp.internal:5432/main"
    filtered = masker.filter_stream(output)
    assert "super_secret_password_123" not in filtered
    assert "[🔒 DB URI REDACTED]" in filtered


def test_dlp_masker_private_key():
    masker = PyDLPMasker()
    output = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA..."
    filtered = masker.filter_stream(output)
    assert "-----BEGIN RSA PRIVATE KEY-----" not in filtered
    assert "[🔒 Private Key REDACTED]" in filtered


def test_dlp_masker_unmask_toggle():
    masker = PyDLPMasker()
    output = "AWS Key: AKIAIOSFODNN7EXAMPLE"
    
    # Masked
    assert "AKIAIOSFODNN7EXAMPLE" not in masker.filter_stream(output)
    
    # Unmasked
    masker.unmasked = True
    assert "AKIAIOSFODNN7EXAMPLE" in masker.filter_stream(output)
    
    # Re-masked
    masker.unmasked = False
    assert "AKIAIOSFODNN7EXAMPLE" not in masker.filter_stream(output)
