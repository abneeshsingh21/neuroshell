# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
import pytest
import shutil
from pathlib import Path
from extensions.enterprise import AuditTrail


def test_hmac_audit_logging_and_verification(tmp_path):
    log_dir = tmp_path / "audit_logs"
    audit = AuditTrail(log_dir=log_dir)
    secret_key = b"enterprise_corp_secret_key_2026"

    # Log 3 commands with HMAC signing
    e1 = audit.log("git status", risk_score=1, action="executed", cwd=".", duration_ms=12.5, exit_code=0, hmac_key=secret_key)
    e2 = audit.log("npm test", risk_score=2, action="executed", cwd=".", duration_ms=45.0, exit_code=0, hmac_key=secret_key)
    e3 = audit.log("docker build -t app .", risk_score=3, action="executed", cwd=".", duration_ms=1200.0, exit_code=0, hmac_key=secret_key)

    assert e1.entry_hash != ""
    assert e2.prev_hash == e1.entry_hash
    assert e3.prev_hash == e2.entry_hash

    # Verify blockchain integrity
    valid, count, msg = audit.verify_chain(hmac_key=secret_key)
    assert valid is True
    assert count == 3
    assert "verified" in msg


def test_tampered_audit_log_fails_verification(tmp_path):
    log_dir = tmp_path / "audit_tampered"
    audit = AuditTrail(log_dir=log_dir)
    secret_key = b"enterprise_corp_secret_key_2026"

    audit.log("git status", risk_score=1, action="executed", cwd=".", hmac_key=secret_key)
    audit.log("cargo check", risk_score=1, action="executed", cwd=".", hmac_key=secret_key)

    # Tamper with the log file
    log_files = list(log_dir.glob("audit_*.jsonl"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    tampered = content.replace("cargo check", "cargo malicious_cmd")
    log_files[0].write_text(tampered, encoding="utf-8")

    # Verification must catch the tampering
    valid, count, msg = audit.verify_chain(hmac_key=secret_key)
    assert valid is False
    assert "mismatch" in msg or "Signature" in msg
