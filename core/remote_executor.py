# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Remote Execution with Local Safety (Phase 7, v5.15).

`nsh user@host` runs commands on a remote machine over SSH — but every
intelligence and safety layer executes LOCALLY, before a single byte
leaves this machine:

    input → [local NL translation]* → [local PolicyEngine RBAC]
          → [local 4-layer SafetyChecker] → [local outbound DLP scan]
          → SSH (ControlMaster multiplexed) → remote command
          → [local inbound DLP scrubbing] → [hash-chained audit] → screen

    * translation only when the input doesn't look like a shell command

Why local-first matters:
  • The remote host never sees your natural-language prompts or your
    LLM API keys — only the final vetted command.
  • A compromised remote host cannot weaken safety: BLOCKED commands
    are refused before the SSH process is even spawned.
  • Secrets accidentally echoed by the remote (keys in configs, tokens
    in logs) are scrubbed locally before they reach your terminal or
    scrollback.

Transport: the system `ssh` binary with ControlMaster auto-multiplexing —
the first command pays the handshake, subsequent commands reuse the
connection (~10ms). No paramiko, no new dependencies, and your existing
~/.ssh/config, agents, ProxyJumps, and hardware keys all keep working.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "RemoteTarget",
    "RemoteResult",
    "RemoteExecutor",
    "GateDecision",
]

CONTROL_DIR = Path.home() / ".neuroshell" / "ssh"
CONTROL_PERSIST = "120"          # keep the master connection open (seconds)
CONNECT_TIMEOUT = "10"
DEFAULT_COMMAND_TIMEOUT = 120    # seconds a remote command may run
MAX_OUTPUT_CHARS = 200_000


# ═══════════════════════════════════════════════════════════
# Target parsing
# ═══════════════════════════════════════════════════════════

_TARGET_RE = re.compile(
    r"^(?:(?P<user>[A-Za-z0-9._][A-Za-z0-9._-]*)@)?"
    r"(?P<host>\[[0-9A-Fa-f:]+\]|[A-Za-z0-9._-]+)"
    r"(?::(?P<port>\d{1,5}))?$"
)


@dataclass(frozen=True)
class RemoteTarget:
    """A parsed `user@host:port` remote destination."""
    host: str
    user: str = ""
    port: int = 0

    @classmethod
    def parse(cls, spec: str) -> "RemoteTarget":
        spec = (spec or "").strip()
        m = _TARGET_RE.match(spec)
        if not m:
            raise ValueError(
                f"Invalid remote target '{spec}' — expected [user@]host[:port]")
        port = int(m.group("port") or 0)
        if port > 65535:
            raise ValueError(f"Invalid port {port}")
        host = m.group("host")
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]  # bracketed IPv6
        return cls(host=host, user=m.group("user") or "", port=port)

    @property
    def label(self) -> str:
        base = f"{self.user}@{self.host}" if self.user else self.host
        return f"{base}:{self.port}" if self.port else base

    def ssh_destination(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host


# ═══════════════════════════════════════════════════════════
# Results
# ═══════════════════════════════════════════════════════════

@dataclass
class GateDecision:
    """Outcome of the local pre-flight gate."""
    allowed: bool
    needs_confirmation: bool = False
    risk_level: str = "SAFE"
    reason: str = ""
    outbound_secret: bool = False   # command itself contains a secret


@dataclass
class RemoteResult:
    command: str
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    executed: bool = False
    gate: GateDecision = field(default_factory=lambda: GateDecision(allowed=True))
    error: str = ""


# ═══════════════════════════════════════════════════════════
# Remote executor
# ═══════════════════════════════════════════════════════════

class RemoteExecutor:
    """Runs commands on a RemoteTarget through the local safety stack.

    Dependency-injectable for tests and embedding:
      safety   — object with .check(command) → SafetyResult (4-layer shield)
      policy   — object with .evaluate(command) → PolicyDecision (RBAC)
      audit    — object with .record(dict) (hash-chained log); optional
      transport_argv — override the ssh argv prefix (tests inject a local
                       shim like ["bash", "-c"])
    """

    def __init__(self, target: RemoteTarget,
                 safety=None, policy=None, audit=None,
                 transport_argv: list[str] | None = None,
                 command_timeout: int = DEFAULT_COMMAND_TIMEOUT):
        self.target = target
        self._safety = safety
        self._policy = policy
        self._audit = audit
        self._transport_argv = transport_argv
        self.command_timeout = command_timeout

    # ── lazy engines (only built when actually used) ──────

    @property
    def safety(self):
        if self._safety is None:
            from config import load_config
            from intelligence.safety import SafetyChecker
            self._safety = SafetyChecker(load_config())
        return self._safety

    @property
    def policy(self):
        if self._policy is None:
            from core.policy_engine import PolicyEngine, UserRole
            role = os.environ.get("NEUROSHELL_REMOTE_ROLE", "developer").lower()
            valid = {r.value for r in UserRole}
            self._policy = PolicyEngine(
                UserRole(role) if role in valid else UserRole.GUEST)
        return self._policy

    @property
    def audit(self):
        if self._audit is None:
            from core.mcp_server import MCPAuditLog
            self._audit = MCPAuditLog(
                Path.home() / ".neuroshell" / "remote_audit.jsonl")
        return self._audit

    # ── local pre-flight gate ──────────────────────────────

    def gate(self, command: str) -> GateDecision:
        """All checks run locally; nothing has touched the network yet."""
        from intelligence.pii_scrubber import contains_secrets

        decision = self.policy.evaluate(command)
        if not decision.allowed:
            return GateDecision(allowed=False, risk_level="BLOCKED",
                                reason=f"Corporate policy: {decision.reason}")

        result = self.safety.check(command)
        risk = result.risk_level.value
        if result.should_block:
            return GateDecision(allowed=False, risk_level=risk,
                                reason=result.reason)

        needs_confirm = (result.needs_confirmation
                         or decision.requires_confirmation
                         or risk == "DANGER")
        return GateDecision(
            allowed=True,
            needs_confirmation=needs_confirm,
            risk_level=risk,
            reason=result.reason,
            outbound_secret=contains_secrets(command),
        )

    # ── execution ──────────────────────────────────────────

    def execute(self, command: str, confirmed: bool = False) -> RemoteResult:
        """Gate locally, then run over SSH. `confirmed=True` approves a
        command previously reported as needs_confirmation."""
        command = (command or "").strip()
        res = RemoteResult(command=command)
        if not command:
            res.error = "empty command"
            return res

        gate = self.gate(command)
        res.gate = gate

        if not gate.allowed:
            res.error = f"refused locally ({gate.risk_level}): {gate.reason}"
            self._record({"event": "remote_refused", "target": self.target.label,
                          "command": command, "risk": gate.risk_level,
                          "reason": gate.reason})
            return res

        if gate.needs_confirmation and not confirmed:
            res.error = "confirmation required"
            self._record({"event": "remote_confirmation_required",
                          "target": self.target.label, "command": command,
                          "risk": gate.risk_level})
            return res

        argv = self._build_argv(command)
        start = time.time()
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True,
                timeout=self.command_timeout,
            )
            res.exit_code = proc.returncode
            raw_out, raw_err = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            res.error = f"remote command timed out after {self.command_timeout}s"
            raw_out = (exc.stdout or b"")
            raw_err = (exc.stderr or b"")
            if isinstance(raw_out, bytes):
                raw_out = raw_out.decode("utf-8", "replace")
            if isinstance(raw_err, bytes):
                raw_err = raw_err.decode("utf-8", "replace")
        except FileNotFoundError:
            res.error = "ssh binary not found on PATH"
            self._record({"event": "remote_error", "target": self.target.label,
                          "command": command, "error": res.error})
            return res
        res.duration_ms = (time.time() - start) * 1000.0
        res.executed = res.error == ""

        # Inbound DLP: scrub secrets locally before they reach the terminal.
        from intelligence.pii_scrubber import scrub
        res.stdout = scrub(raw_out or "")[:MAX_OUTPUT_CHARS]
        res.stderr = scrub(raw_err or "")[:MAX_OUTPUT_CHARS]

        self._record({"event": "remote_executed" + ("_confirmed" if confirmed else ""),
                      "target": self.target.label, "command": command,
                      "risk": gate.risk_level, "exit_code": res.exit_code,
                      "duration_ms": round(res.duration_ms, 1)})
        return res

    # ── connection health ──────────────────────────────────

    def check_connection(self) -> tuple[bool, str]:
        """Cheap reachability probe (also warms the ControlMaster)."""
        r = self.execute("true", confirmed=True)
        if r.executed and r.exit_code == 0:
            return True, f"connected to {self.target.label}"
        return False, r.error or r.stderr.strip() or f"exit {r.exit_code}"

    def close(self) -> None:
        """Tear down the multiplexed master connection, if any."""
        if self._transport_argv is not None:
            return
        try:
            subprocess.run(
                ["ssh", "-O", "exit",
                 "-o", f"ControlPath={self._control_path()}",
                 self.target.ssh_destination()],
                capture_output=True, timeout=10,
            )
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            pass

    # ── internals ──────────────────────────────────────────

    def _control_path(self) -> str:
        CONTROL_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(CONTROL_DIR, 0o700)
        except OSError:
            pass
        return str(CONTROL_DIR / "%r@%h:%p")

    def _build_argv(self, command: str) -> list[str]:
        if self._transport_argv is not None:
            # Test/embedding shim: run locally, no network.
            return [*self._transport_argv, command]

        argv = [
            "ssh",
            "-o", "ControlMaster=auto",
            "-o", f"ControlPath={self._control_path()}",
            "-o", f"ControlPersist={CONTROL_PERSIST}",
            "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
            "-o", "BatchMode=yes",       # never hang on a password prompt
            "-o", "StrictHostKeyChecking=accept-new",
        ]
        if self.target.port:
            argv += ["-p", str(self.target.port)]
        argv.append(self.target.ssh_destination())
        # Remote side gets ONE argument: the exact vetted command string.
        argv.append(command)
        return argv

    def _record(self, event: dict) -> None:
        try:
            self.audit.record(event)
        except Exception:
            pass  # audit failure must never break execution


# ═══════════════════════════════════════════════════════════
# CLI — `nsh user@host [-- command…]`
# ═══════════════════════════════════════════════════════════

_ANSI = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
    "cyan": "\033[36m",
}


def _c(color: str, text: str) -> str:
    if not os.isatty(1):
        return text
    return f"{_ANSI.get(color, '')}{text}{_ANSI['reset']}"


_SHELL_STARTERS = {
    "ls", "cd", "cat", "grep", "find", "ps", "top", "df", "du", "free",
    "systemctl", "journalctl", "docker", "kubectl", "git", "tail", "head",
    "echo", "pwd", "whoami", "uname", "uptime", "curl", "wget", "rm", "mv",
    "cp", "mkdir", "touch", "chmod", "chown", "kill", "pkill", "service",
    "apt", "apt-get", "yum", "dnf", "pip", "pip3", "python", "python3",
    "npm", "node", "cargo", "make", "sudo", "tar", "ssh", "scp", "rsync",
}


def _looks_like_shell(text: str) -> bool:
    first = text.split(None, 1)[0] if text.split() else ""
    if first in _SHELL_STARTERS:
        return True
    return bool(re.search(r"[|;&><$/\\]|^\w+=[^ ]", text))


def _translate_local(text: str) -> str | None:
    """Local NL → command translation. Returns None when unavailable."""
    try:
        from config import load_config
        from core.context import ContextManager
        from core.history import HistoryStore
        from intelligence.translator import Translator
        from llm.client import LLMClient
        cfg = load_config()
        translator = Translator(LLMClient(cfg), ContextManager(cfg), HistoryStore())
        result = translator.translate(text)
        if result and result.command and result.command.strip() != text.strip():
            return result.command.strip()
    except Exception:
        pass
    return None


def cli_main(argv: list[str] | None = None) -> int:
    import argparse
    import sys as _sys

    parser = argparse.ArgumentParser(
        prog="nsh",
        description="NeuroShell remote execution — safety checks run "
                    "locally, commands run over SSH.",
    )
    parser.add_argument("target", help="[user@]host[:port]")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="One-shot command (omit for interactive REPL). "
                             "Everything after the target is passed through "
                             "verbatim — flags like -rf are never parsed by nsh.")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Auto-confirm CAUTION/DANGER commands (not BLOCKED)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_COMMAND_TIMEOUT,
                        help="Per-command timeout in seconds")
    args = parser.parse_args(argv)
    # argparse.REMAINDER keeps a leading "--" separator if present; drop it.
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]

    try:
        target = RemoteTarget.parse(args.target)
    except ValueError as exc:
        print(_c("red", f"✘ {exc}"), file=_sys.stderr)
        return 2

    ex = RemoteExecutor(target, command_timeout=args.timeout)

    def run_one(cmd: str, auto_yes: bool) -> int:
        r = ex.execute(cmd)
        if r.error == "confirmation required":
            print(_c("yellow", f"⚠ {r.gate.risk_level}: {r.gate.reason}"))
            if r.gate.outbound_secret:
                print(_c("red", "⚠ the command itself contains a secret "
                                "that would be sent to the remote host"))
            if auto_yes:
                ok = True
            else:
                try:
                    ok = input(f"Run on {target.label}? [y/N]: ").strip().lower() == "y"
                except (EOFError, KeyboardInterrupt):
                    ok = False
            if not ok:
                print(_c("dim", "aborted — nothing was sent"))
                return 130
            r = ex.execute(cmd, confirmed=True)
        if r.error and not r.executed:
            print(_c("red", f"✘ {r.error}"), file=_sys.stderr)
            return 1
        if r.stdout:
            _sys.stdout.write(r.stdout)
        if r.stderr:
            _sys.stderr.write(r.stderr)
        return r.exit_code if r.exit_code >= 0 else 1

    # One-shot mode
    if args.command:
        cmd = " ".join(args.command)
        return run_one(cmd, args.yes)

    # Interactive REPL
    ok, msg = ex.check_connection()
    if not ok:
        print(_c("red", f"✘ cannot reach {target.label}: {msg}"), file=_sys.stderr)
        return 1
    print(_c("green", f"⌬ NeuroShell remote → {target.label}"))
    print(_c("dim", "  safety, translation & DLP run locally · "
                    "'exit' to quit"))
    rc = 0
    while True:
        try:
            line = input(_c("cyan", f"{target.label} ❯ ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("exit", "quit", "q"):
            break
        if not _looks_like_shell(line):
            translated = _translate_local(line)
            if translated:
                print(_c("dim", f"  ⌬ {line!r} → {translated}"))
                line = translated
        rc = run_one(line, args.yes)
    ex.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(cli_main())
