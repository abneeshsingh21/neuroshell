# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell MCP Server Mode (Phase 6, v5.14).

Exposes NeuroShell as a Model Context Protocol (MCP) tool provider over
stdio, so MCP clients — Claude Desktop, Cursor, agent frameworks — execute
shell commands THROUGH NeuroShell's safety stack instead of raw shell:

    client → MCP stdio → [PolicyEngine RBAC] → [4-layer SafetyChecker]
           → [two-phase confirmation] → ShellExecutor
           → [PII/DLP scrubbing] → [hash-chained audit log] → client

Tools exposed:
    neuroshell_execute       run a command through the full safety pipeline
    neuroshell_translate     natural language → shell command (+ risk grade)
    neuroshell_explain       explain what a command does before running it
    neuroshell_safety_check  grade a command without executing anything

Design notes:
  • Zero new dependencies: MCP's stdio transport is newline-delimited
    JSON-RPC 2.0, which this module implements directly (the repo already
    ships a JSON-RPC 2.0 dispatcher for the native host IPC).
  • Two-phase confirmation: DANGER-level commands are refused with a
    structured hint; the client must re-call with confirm=true. BLOCKED
    commands can never be confirmed — there is no override parameter.
  • Per-client policy scope via environment (set in the MCP client's
    server config): NEUROSHELL_MCP_ROLE=guest|contractor|developer|
    devops|admin and NEUROSHELL_MCP_READONLY=1 (disables execute).
  • Every decision — allowed, refused, confirmed — lands in a
    hash-chained JSONL audit log (~/.neuroshell/mcp_audit.jsonl), so a
    tampered entry breaks the chain from that point forward.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "neuroshell"
MAX_OUTPUT_CHARS = 100_000          # per-stream cap sent back to the client
DEFAULT_TIMEOUT_S = 60
MAX_TIMEOUT_S = 300

_VALID_ROLES = {"admin", "devops", "developer", "contractor", "guest"}


# ═══════════════════════════════════════════════════════════
# Lazy engine container — build only what a tool call needs
# ═══════════════════════════════════════════════════════════

class _Engine:
    """Lazily constructs NeuroShell subsystems on first use so `tools/list`
    responds in milliseconds and an LLM misconfiguration cannot prevent the
    safety-checked `execute` path from working."""

    def __init__(self):
        self._config = None
        self._executor = None
        self._safety = None
        self._context = None
        self._history = None
        self._llm = None
        self._translator = None
        self._explainer = None
        self._policy = None

    @property
    def config(self):
        if self._config is None:
            from config import load_config
            self._config = load_config()
        return self._config

    @property
    def executor(self):
        if self._executor is None:
            from core.executor import ShellExecutor
            self._executor = ShellExecutor(self.config)
        return self._executor

    @property
    def safety(self):
        if self._safety is None:
            from intelligence.safety import SafetyChecker
            self._safety = SafetyChecker(self.config)  # no LLM: layers 1-3 are local
        return self._safety

    @property
    def context(self):
        if self._context is None:
            from core.context import ContextManager
            self._context = ContextManager(self.config)
        return self._context

    @property
    def history(self):
        if self._history is None:
            from core.history import HistoryStore
            self._history = HistoryStore()
        return self._history

    @property
    def llm(self):
        if self._llm is None:
            from llm.client import LLMClient
            self._llm = LLMClient(self.config)
        return self._llm

    @property
    def translator(self):
        if self._translator is None:
            from intelligence.translator import Translator
            self._translator = Translator(self.llm, self.context, self.history)
        return self._translator

    @property
    def explainer(self):
        if self._explainer is None:
            from intelligence.explainer import Explainer
            try:
                self._explainer = Explainer(self.llm, self.context)
            except Exception:
                self._explainer = Explainer(None, None)  # offline DB + man pages
        return self._explainer

    @property
    def policy(self):
        if self._policy is None:
            from core.policy_engine import PolicyEngine, UserRole
            role_name = os.environ.get("NEUROSHELL_MCP_ROLE", "developer").lower()
            if role_name not in _VALID_ROLES:
                role_name = "guest"  # unknown role → least privilege
            self._policy = PolicyEngine(UserRole(role_name))
        return self._policy


# ═══════════════════════════════════════════════════════════
# Hash-chained audit log
# ═══════════════════════════════════════════════════════════

class MCPAuditLog:
    """Append-only JSONL log where each entry embeds the SHA-256 of the
    previous entry — editing any line breaks verification of every line
    after it."""

    def __init__(self, path: Path):
        self.path = path
        self._prev_hash = self._load_tail_hash()

    def _load_tail_hash(self) -> str:
        try:
            with open(self.path, "rb") as f:
                last = b""
                for line in f:
                    if line.strip():
                        last = line
                if last:
                    return json.loads(last).get("entry_hash", "")
        except (OSError, ValueError):
            pass
        return ""

    def record(self, event: dict) -> str:
        entry = dict(event)
        entry["ts"] = round(time.time(), 3)
        entry["prev_hash"] = self._prev_hash
        digest = hashlib.sha256(
            (self._prev_hash + json.dumps(entry, sort_keys=True)).encode("utf-8")
        ).hexdigest()
        entry["entry_hash"] = digest
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
        except OSError:
            pass  # audit failure must not break tool calls
        self._prev_hash = digest
        return digest

    def verify(self) -> tuple[bool, int]:
        """Return (chain_intact, entries_checked)."""
        prev = ""
        count = 0
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    claimed = entry.pop("entry_hash", "")
                    if entry.get("prev_hash", "") != prev:
                        return False, count
                    digest = hashlib.sha256(
                        (prev + json.dumps(entry, sort_keys=True)).encode("utf-8")
                    ).hexdigest()
                    if digest != claimed:
                        return False, count
                    prev = claimed
                    count += 1
        except FileNotFoundError:
            return True, 0
        except (OSError, ValueError):
            return False, count
        return True, count


# ═══════════════════════════════════════════════════════════
# Tool schemas (MCP tools/list payload)
# ═══════════════════════════════════════════════════════════

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "neuroshell_execute",
        "description": (
            "Execute a shell command through NeuroShell's full safety pipeline: "
            "role-based policy, 4-layer safety analysis, DLP secret scrubbing of "
            "output, and a tamper-evident audit log. Commands graded DANGER are "
            "refused until re-called with confirm=true; BLOCKED commands are "
            "never executed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."},
                "cwd": {"type": "string", "description": "Working directory (optional)."},
                "timeout": {
                    "type": "integer",
                    "description": f"Seconds before the command is killed (default {DEFAULT_TIMEOUT_S}, max {MAX_TIMEOUT_S}).",
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Set true to approve a command previously refused as DANGER.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "neuroshell_translate",
        "description": (
            "Translate a natural-language request into a shell command with a "
            "safety grade. Nothing is executed — pass the result to "
            "neuroshell_execute to run it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language request."},
                "cwd": {"type": "string", "description": "Working directory context (optional)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "neuroshell_explain",
        "description": (
            "Explain what a shell command does (summary, flag breakdown, risks) "
            "using offline knowledge, man pages, and the configured LLM. Nothing "
            "is executed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to explain."},
            },
            "required": ["command"],
        },
    },
    {
        "name": "neuroshell_safety_check",
        "description": (
            "Grade a command's risk (SAFE / CAUTION / DANGER / BLOCKED) with "
            "reasons and estimated blast scope, without executing anything."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to grade."},
            },
            "required": ["command"],
        },
    },
]


# ═══════════════════════════════════════════════════════════
# MCP server
# ═══════════════════════════════════════════════════════════

class MCPServer:
    """Model Context Protocol server over newline-delimited JSON-RPC 2.0."""

    def __init__(self, engine: _Engine | None = None,
                 audit_path: Path | None = None,
                 read_only: bool | None = None):
        self.engine = engine or _Engine()
        self.audit = MCPAuditLog(
            audit_path or Path.home() / ".neuroshell" / "mcp_audit.jsonl"
        )
        if read_only is None:
            read_only = os.environ.get("NEUROSHELL_MCP_READONLY", "") not in ("", "0")
        self.read_only = read_only
        self._initialized = False

    # ── transport ──────────────────────────────────────────

    def serve_stdio(self) -> None:
        """Blocking loop: one JSON-RPC message per line on stdin/stdout.

        stdout is the protocol channel. NeuroShell subsystems occasionally
        print banners/warnings on import, which would corrupt MCP framing —
        so we keep a private handle to the real stdout and point sys.stdout
        at stderr for the lifetime of the server.
        """
        self._proto_out = sys.stdout
        sys.stdout = sys.stderr
        stdin = sys.stdin.buffer
        try:
            while True:
                line = stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except ValueError:
                    self._send({"jsonrpc": "2.0", "id": None,
                                "error": {"code": -32700, "message": "Parse error"}})
                    continue
                reply = self.handle_message(msg)
                if reply is not None:
                    self._send(reply)
        finally:
            sys.stdout = self._proto_out

    _proto_out = None

    def _send(self, obj: dict) -> None:
        out = self._proto_out or sys.stdout
        out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        out.flush()

    # ── JSON-RPC dispatch ──────────────────────────────────

    def handle_message(self, msg: dict) -> dict | None:
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32600, "message": "Invalid Request"}}

        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params") or {}
        is_notification = "id" not in msg

        if not isinstance(method, str):
            if is_notification:
                return None
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32600, "message": "Missing method"}}

        try:
            if method == "initialize":
                result = self._on_initialize(params)
            elif method == "notifications/initialized":
                self._initialized = True
                return None
            elif method.startswith("notifications/"):
                return None
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOL_DEFINITIONS}
            elif method == "tools/call":
                result = self._on_tools_call(params)
            elif method == "prompts/list":
                result = {"prompts": []}
            elif method == "resources/list":
                result = {"resources": []}
            else:
                if is_notification:
                    return None
                return {"jsonrpc": "2.0", "id": msg_id,
                        "error": {"code": -32601, "message": f"Method not found: {method}"}}
        except Exception as exc:  # noqa: BLE001 — protocol boundary
            if is_notification:
                return None
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32603, "message": f"Internal error: {exc}"}}

        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _on_initialize(self, params: dict) -> dict:
        from __version__ import __version__
        return {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
            "instructions": (
                "NeuroShell executes commands through a 4-layer safety shield. "
                "Use neuroshell_translate for natural language, "
                "neuroshell_safety_check to pre-grade risk, and "
                "neuroshell_execute to run. DANGER commands need confirm=true; "
                "BLOCKED commands cannot be run at all."
            ),
        }

    # ── tools/call ─────────────────────────────────────────

    def _on_tools_call(self, params: dict) -> dict:
        name = params.get("name", "")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return self._tool_error("Tool arguments must be an object.")

        if name == "neuroshell_execute":
            return self._tool_execute(args)
        if name == "neuroshell_translate":
            return self._tool_translate(args)
        if name == "neuroshell_explain":
            return self._tool_explain(args)
        if name == "neuroshell_safety_check":
            return self._tool_safety_check(args)
        return self._tool_error(f"Unknown tool: {name}")

    @staticmethod
    def _tool_result(payload: dict, is_error: bool = False) -> dict:
        return {
            "content": [{"type": "text",
                         "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
            "isError": is_error,
        }

    @classmethod
    def _tool_error(cls, message: str, **extra) -> dict:
        payload = {"error": message}
        payload.update(extra)
        return cls._tool_result(payload, is_error=True)

    # ── neuroshell_execute ─────────────────────────────────

    def _tool_execute(self, args: dict) -> dict:
        command = args.get("command", "")
        if not isinstance(command, str) or not command.strip():
            return self._tool_error("'command' must be a non-empty string.")
        command = command.strip()
        confirm = bool(args.get("confirm", False))
        cwd = args.get("cwd")
        timeout = args.get("timeout", DEFAULT_TIMEOUT_S)
        if not isinstance(timeout, int) or timeout <= 0:
            timeout = DEFAULT_TIMEOUT_S
        timeout = min(timeout, MAX_TIMEOUT_S)

        if self.read_only:
            self.audit.record({"tool": "execute", "command": command,
                               "decision": "refused_readonly"})
            return self._tool_error(
                "This MCP server is running in read-only mode "
                "(NEUROSHELL_MCP_READONLY=1). Execution is disabled; "
                "translate/explain/safety_check remain available."
            )

        # Layer A: corporate policy (RBAC)
        decision = self.engine.policy.evaluate(command)
        if not decision.allowed:
            self.audit.record({"tool": "execute", "command": command,
                               "decision": "refused_policy",
                               "rule": decision.matched_rule})
            return self._tool_error(
                f"Refused by corporate policy: {decision.reason}",
                matched_rule=decision.matched_rule,
            )

        # Layer B: 4-layer safety shield
        safety = self.engine.safety.check(command)
        risk = safety.risk_level.value
        if safety.should_block:
            self.audit.record({"tool": "execute", "command": command,
                               "decision": "refused_blocked", "risk": risk,
                               "reason": safety.reason})
            return self._tool_error(
                f"BLOCKED by NeuroShell safety shield: {safety.reason} "
                "This command cannot be executed through this server and "
                "there is no override.",
                risk_level=risk,
            )

        needs_confirm = (safety.needs_confirmation
                         or risk in ("DANGER",)
                         or decision.requires_confirmation)
        if needs_confirm and not confirm:
            self.audit.record({"tool": "execute", "command": command,
                               "decision": "confirmation_required", "risk": risk,
                               "reason": safety.reason})
            return self._tool_error(
                "Confirmation required before executing this command. "
                "Review the risk details, then re-call neuroshell_execute "
                "with the same command and confirm=true if the user approves.",
                risk_level=risk,
                reason=safety.reason,
                affected_scope=safety.affected.summary,
                reversible=safety.is_reversible,
            )

        # Execute through the shared executor (injection guard, timeout,
        # background detection all live there).
        executor = self.engine.executor
        if isinstance(cwd, str) and cwd:
            if os.path.isdir(cwd):
                executor._cwd = os.path.abspath(cwd)
            else:
                return self._tool_error(f"cwd does not exist: {cwd}")

        result = executor.execute(command, timeout=timeout)

        # Layer C: DLP — scrub secrets before output leaves the machine.
        from intelligence.pii_scrubber import scrub
        stdout = scrub(result.stdout or "")[:MAX_OUTPUT_CHARS]
        stderr = scrub(result.stderr or "")[:MAX_OUTPUT_CHARS]

        # History (best-effort) + audit
        try:
            from core.history import CommandRecord
            self.engine.history.add_command(CommandRecord(
                command=command,
                exit_code=result.exit_code,
                stdout_preview=stdout[:500],
                stderr_preview=stderr[:500],
                cwd=result.cwd,
                shell=result.shell,
                duration_ms=result.duration_ms,
                timestamp=time.time(),
                source="mcp",
            ))
        except Exception:
            pass
        self.audit.record({"tool": "execute", "command": command,
                           "decision": "executed" + ("_confirmed" if confirm else ""),
                           "risk": risk, "exit_code": result.exit_code})

        return self._tool_result({
            "command": command,
            "exit_code": result.exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": round(result.duration_ms, 1),
            "cwd": result.cwd,
            "risk_level": risk,
        }, is_error=False)

    # ── neuroshell_translate ───────────────────────────────

    def _tool_translate(self, args: dict) -> dict:
        query = args.get("query", "")
        if not isinstance(query, str) or not query.strip():
            return self._tool_error("'query' must be a non-empty string.")
        try:
            translation = self.engine.translator.translate(query.strip())
        except Exception as exc:  # noqa: BLE001 — LLM/provider failures
            return self._tool_error(f"Translation failed: {exc}")
        if not translation or not translation.command:
            return self._tool_error(
                "Could not translate this request into a shell command.")

        safety = self.engine.safety.check(translation.command)
        self.audit.record({"tool": "translate", "query": query.strip(),
                           "command": translation.command,
                           "risk": safety.risk_level.value})
        return self._tool_result({
            "command": translation.command,
            "explanation": translation.explanation,
            "confidence": translation.confidence,
            "risk_level": safety.risk_level.value,
            "risk_reason": safety.reason,
            "next_step": "Pass 'command' to neuroshell_execute to run it.",
        })

    # ── neuroshell_explain ─────────────────────────────────

    def _tool_explain(self, args: dict) -> dict:
        command = args.get("command", "")
        if not isinstance(command, str) or not command.strip():
            return self._tool_error("'command' must be a non-empty string.")
        try:
            explained = self.engine.explainer.explain(command.strip())
        except Exception as exc:  # noqa: BLE001
            return self._tool_error(f"Explanation failed: {exc}")
        self.audit.record({"tool": "explain", "command": command.strip()})
        return self._tool_result({
            "command": command.strip(),
            "summary": getattr(explained, "summary", ""),
            "breakdown": getattr(explained, "breakdown", []),
            "risks": getattr(explained, "risks", []),
            "source": getattr(explained, "source", ""),
        })

    # ── neuroshell_safety_check ────────────────────────────

    def _tool_safety_check(self, args: dict) -> dict:
        command = args.get("command", "")
        if not isinstance(command, str) or not command.strip():
            return self._tool_error("'command' must be a non-empty string.")
        safety = self.engine.safety.check(command.strip())
        self.audit.record({"tool": "safety_check", "command": command.strip(),
                           "risk": safety.risk_level.value})
        return self._tool_result({
            "command": command.strip(),
            "risk_level": safety.risk_level.value,
            "reason": safety.reason,
            "needs_confirmation": safety.needs_confirmation,
            "blocked": safety.should_block,
            "reversible": safety.is_reversible,
            "affected_scope": safety.affected.summary,
            "suggestions": safety.suggestions,
        })


def main() -> None:
    """Entry point: `neuroshell-mcp` / `python -m core.mcp_server`."""
    # stdout is the protocol channel — anything the engine prints would
    # corrupt framing, so demote accidental prints to stderr.
    server = MCPServer()
    server.serve_stdio()


if __name__ == "__main__":
    main()
