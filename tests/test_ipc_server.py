# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Unit tests for NeuroShell Named Pipe IPC Server and JSON-RPC Protocol.
"""

import os
import json
import pytest
from unittest.mock import MagicMock
from core.ipc_server import NamedPipeServer


class DummyAssessment:
    class DummyLevel:
        value = "SAFE"
    level = DummyLevel()


class DummyTranslation:
    command = "dir /s /b *.py"
    explanation = "Find all Python files"
    confidence = 0.95


def test_ipc_server_ping():
    mock_shell = MagicMock()
    server = NamedPipeServer(mock_shell)
    req = {"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 42}
    resp = server._handle_request(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["result"] == "pong"
    assert resp["id"] == 42


def test_ipc_server_translate():
    mock_shell = MagicMock()
    mock_shell.tracer.start_trace.return_value = "trace-123"
    mock_shell.translator.translate.return_value = DummyTranslation()
    mock_shell.safety.assess.return_value = DummyAssessment()

    server = NamedPipeServer(mock_shell)
    req = {
        "jsonrpc": "2.0",
        "method": "translate",
        "params": {"query": "find all python files", "cwd": "C:\\test"},
        "id": 100
    }
    resp = server._handle_request(req)
    assert resp["result"]["command"] == "dir /s /b *.py"
    assert resp["result"]["risk_level"] == "SAFE"
    assert resp["result"]["confidence"] == 0.95


def test_ipc_server_slash_command():
    mock_shell = MagicMock()
    mock_shell.tracer.start_trace.return_value = "trace-456"
    mock_shell._handle_slash_command.return_value = True

    server = NamedPipeServer(mock_shell)
    req = {
        "jsonrpc": "2.0",
        "method": "slash",
        "params": {"command": "/model"},
        "id": 101
    }
    resp = server._handle_request(req)
    assert resp["result"]["handled"] is True


def test_ipc_server_unknown_method():
    mock_shell = MagicMock()
    server = NamedPipeServer(mock_shell)
    req = {"jsonrpc": "2.0", "method": "invalid_method", "params": {}, "id": 999}
    resp = server._handle_request(req)
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_ipc_server_diagnose_error():
    mock_shell = MagicMock()
    server = NamedPipeServer(mock_shell)
    req = {
        "jsonrpc": "2.0",
        "method": "diagnose_error",
        "params": {
            "command": "python app.py",
            "output": "ModuleNotFoundError: No module named 'fastapi'",
            "exit_code": 1,
            "cwd": "C:\\test"
        },
        "id": 102
    }
    resp = server._handle_request(req)
    assert resp["jsonrpc"] == "2.0"
    assert "root_cause" in resp["result"]
    assert "auto_fix" in resp["result"]


def test_ipc_server_agent_plan():
    mock_shell = MagicMock()
    mock_shell.translator.translate.return_value = DummyTranslation()
    server = NamedPipeServer(mock_shell)
    req = {
        "jsonrpc": "2.0",
        "method": "agent_plan",
        "params": {
            "task": "Create a docker container",
            "cwd": "C:\\test"
        },
        "id": 103
    }
    resp = server._handle_request(req)
    assert resp["jsonrpc"] == "2.0"
    assert "steps" in resp["result"]
    assert len(resp["result"]["steps"]) > 0


def test_ipc_server_ai_pipe():
    mock_shell = MagicMock()
    mock_shell.llm.generate.return_value = "Here is the error analysis."
    server = NamedPipeServer(mock_shell)
    req = {
        "jsonrpc": "2.0",
        "method": "ai_pipe",
        "params": {
            "directive": "@ai",
            "prompt": "explain error",
            "input_text": "Error: Port 8080 already in use",
            "cwd": "C:\\test"
        },
        "id": 104
    }
    resp = server._handle_request(req)
    assert resp["jsonrpc"] == "2.0"
    assert "response" in resp["result"]
    assert resp["result"]["directive"] == "@ai"

