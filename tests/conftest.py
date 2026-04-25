"""
conftest.py — Shared pytest fixtures for NeuroShell test suite.
"""
import sys
import os
import pytest

# Ensure the neuroshell package root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def tmp_secrets_file(tmp_path, monkeypatch):
    """Redirect the secrets file to a temp directory for each test."""
    import config as cfg_module
    fake_secrets = tmp_path / ".neuroshell_secrets.json"
    monkeypatch.setattr(cfg_module, "SECRETS_FILE", fake_secrets)
    yield fake_secrets


@pytest.fixture()
def mock_config(tmp_path):
    """Return a minimal Config-like object for tests that need config."""
    from unittest.mock import MagicMock
    cfg = MagicMock()
    cfg.default_shell = "powershell"
    cfg.max_tokens = 512
    cfg.temperature = 0.7
    cfg.model = "llama3"
    cfg.undo_snapshots = 5
    return cfg
