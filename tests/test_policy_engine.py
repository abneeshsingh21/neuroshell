# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
import pytest
from core.policy_engine import PolicyEngine, UserRole, PolicyDecision


def test_admin_role_allows_standard_commands():
    engine = PolicyEngine(role=UserRole.ADMIN)
    decision = engine.evaluate("git status")
    assert decision.allowed is True
    assert decision.requires_confirmation is False


def test_developer_role_blocks_destructive_verbs():
    engine = PolicyEngine(role=UserRole.DEVELOPER)
    decision = engine.evaluate("terraform destroy -auto-approve")
    assert decision.allowed is False
    assert "BLOCKED" in decision.reason

    decision2 = engine.evaluate("kubectl delete namespace production")
    assert decision2.allowed is False


def test_developer_role_requires_confirmation_on_force_push():
    engine = PolicyEngine(role=UserRole.DEVELOPER)
    decision = engine.evaluate("git push origin main --force")
    assert decision.allowed is True
    assert decision.requires_confirmation is True


def test_contractor_role_restricts_cloud_destructive_ops():
    engine = PolicyEngine(role=UserRole.CONTRACTOR)
    decision = engine.evaluate("aws s3 rm s3://bucket/data --recursive")
    assert decision.allowed is False
    assert "BLOCKED" in decision.reason


def test_contractor_role_requires_confirmation_on_push():
    engine = PolicyEngine(role=UserRole.CONTRACTOR)
    decision = engine.evaluate("git push origin feature-branch")
    assert decision.allowed is True
    assert decision.requires_confirmation is True
