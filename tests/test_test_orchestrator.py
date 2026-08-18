# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
import pytest
from pathlib import Path


def test_test_file_mapping():
    """Verify test file naming conventions."""
    src_file = "src/auth.py"
    expected_test = "tests/test_auth.py"
    
    stem = Path(src_file).stem
    candidate = f"tests/test_{stem}.py"
    assert candidate == expected_test


def test_parallel_test_command_formatting():
    """Verify pytest-xdist parallel test arguments."""
    files = ["tests/test_policy_engine.py", "tests/test_hmac_audit.py"]
    base_cmd = "pytest -n auto -v"
    full_cmd = f"{base_cmd} {' '.join(files)}"
    assert "-n auto" in full_cmd
    assert "tests/test_policy_engine.py" in full_cmd
    assert "tests/test_hmac_audit.py" in full_cmd
