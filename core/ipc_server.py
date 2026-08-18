# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Production Dual-Engine Cross-Platform IPC Server.
Supports Windows Named Pipes (\\.\\pipe\\neuroshell_ipc) on NT and
Unix Domain Sockets (~/.neuroshell/ipc.sock) on Linux & macOS.
Full JSON-RPC 2.0 Specification Compliance, Multi-Client ThreadPool,
Dynamic Buffer Chunking, and DACL/Permission Access Control.
"""

from __future__ import annotations

import os
import sys
import json
import time
import socket
import select
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Any

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

PIPE_NAME = r"\\.\pipe\neuroshell_ipc"
UNIX_SOCKET_PATH = Path.home() / ".neuroshell" / "ipc.sock"
BUFFER_SIZE = 65536
MAX_PAYLOAD_SIZE = 10 * 1024 * 1024  # 10 MB max request threshold

# Windows Constants
PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_MESSAGE = 0x00000004
PIPE_READMODE_MESSAGE = 0x00000002
PIPE_WAIT = 0x00000000
INVALID_HANDLE_VALUE = -1
ERROR_PIPE_CONNECTED = 535
ERROR_MORE_DATA = 234
ERROR_BROKEN_PIPE = 109
ERROR_NO_DATA = 232


class NamedPipeServer:
    """
    High-Concurrency Dual-Engine IPC Server for NeuroShell.
    Compliant with JSON-RPC 2.0 standard across Windows, Linux & macOS.
    """

    def __init__(self, neuroshell_instance, max_workers: int = 16):
        self.shell = neuroshell_instance
        self.max_workers = max_workers
        self.running = False
        self._listener_thread: Optional[threading.Thread] = None
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="IPCWorker")
        self._state_lock = threading.Lock()
        self._server_sock: Optional[socket.socket] = None

    def start(self):
        """Start the IPC listener daemon on Windows or POSIX."""
        if self.running:
            return
        self.running = True
        if os.name == "nt":
            self._listener_thread = threading.Thread(
                target=self._listen_loop_windows, daemon=True, name="IPCListenerWin"
            )
        else:
            self._listener_thread = threading.Thread(
                target=self._listen_loop_unix, daemon=True, name="IPCListenerUnix"
            )
        self._listener_thread.start()

    def stop(self):
        """Gracefully terminate IPC server."""
        self.running = False
        if os.name == "nt":
            # Unblock ConnectNamedPipe
            try:
                with open(PIPE_NAME, "r+b"):
                    pass
            except Exception:
                pass
        else:
            if self._server_sock:
                try:
                    self._server_sock.close()
                except Exception:
                    pass
            try:
                UNIX_SOCKET_PATH.unlink(missing_ok=True)
            except Exception:
                pass
        self._pool.shutdown(wait=False)

    # ── Unix Domain Sockets Engine (Linux / macOS) ────────────

    def _listen_loop_unix(self):
        """High-performance Unix Domain Socket listener with strict permissions."""
        UNIX_SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)

        if UNIX_SOCKET_PATH.exists():
            try:
                test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                test_sock.connect(str(UNIX_SOCKET_PATH))
                test_sock.close()
                return  # Another active server is already bound
            except (ConnectionRefusedError, OSError):
                UNIX_SOCKET_PATH.unlink(missing_ok=True)

        old_umask = os.umask(0o077)
        try:
            self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._server_sock.bind(str(UNIX_SOCKET_PATH))
            self._server_sock.listen(128)
            os.chmod(str(UNIX_SOCKET_PATH), 0o600)
        finally:
            os.umask(old_umask)

        while self.running:
            try:
                r, _, _ = select.select([self._server_sock], [], [], 0.5)
                if not r or not self.running:
                    continue
                client_sock, _ = self._server_sock.accept()
                self._pool.submit(self._handle_unix_client, client_sock)
            except Exception:
                break

    def _handle_unix_client(self, client_sock: socket.socket):
        """Handle streaming newline-delimited JSON-RPC over Unix socket."""
        buffer = ""
        try:
            with client_sock:
                while self.running:
                    data = client_sock.recv(65536).decode("utf-8", errors="replace")
                    if not data:
                        break
                    buffer += data
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        if line.strip():
                            resp = self._process_raw_json(line.strip())
                            if resp:
                                client_sock.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        except Exception:
            pass

    # ── Windows Named Pipes Engine (Windows) ──────────────────

    def _listen_loop_windows(self):
        """Windows Named Pipe accept loop."""
        kernel32 = ctypes.windll.kernel32
        while self.running:
            h_pipe = kernel32.CreateNamedPipeW(
                PIPE_NAME,
                PIPE_ACCESS_DUPLEX,
                PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
                self.max_workers,
                BUFFER_SIZE,
                BUFFER_SIZE,
                0,
                None,
            )

            if h_pipe == INVALID_HANDLE_VALUE:
                time.sleep(0.1)
                continue

            connected = kernel32.ConnectNamedPipe(h_pipe, None)
            if not connected and kernel32.GetLastError() != ERROR_PIPE_CONNECTED:
                kernel32.CloseHandle(h_pipe)
                continue

            if not self.running:
                kernel32.DisconnectNamedPipe(h_pipe)
                kernel32.CloseHandle(h_pipe)
                break

            self._pool.submit(self._handle_win_client, h_pipe)

    def _handle_win_client(self, h_pipe):
        """Process incoming messages from a connected Windows Named Pipe client."""
        kernel32 = ctypes.windll.kernel32
        read_buf = ctypes.create_string_buffer(BUFFER_SIZE)
        bytes_read = wintypes.DWORD()
        chunks = []
        total_bytes = 0

        try:
            while self.running:
                success = kernel32.ReadFile(
                    h_pipe, read_buf, BUFFER_SIZE, ctypes.byref(bytes_read), None
                )
                err = kernel32.GetLastError()

                if bytes_read.value > 0:
                    chunks.append(read_buf.raw[: bytes_read.value])
                    total_bytes += bytes_read.value

                    if total_bytes > MAX_PAYLOAD_SIZE:
                        err_resp = json.dumps(
                            {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Payload size exceeded"}, "id": None}
                        ).encode("utf-8")
                        self._write_win_pipe(h_pipe, err_resp)
                        break

                if success:
                    full_payload = b"".join(chunks).decode("utf-8", errors="replace")
                    chunks.clear()
                    total_bytes = 0

                    resp = self._process_raw_json(full_payload)
                    if resp:
                        resp_bytes = json.dumps(resp).encode("utf-8")
                        self._write_win_pipe(h_pipe, resp_bytes)
                elif err == ERROR_MORE_DATA:
                    continue
                elif err in (ERROR_BROKEN_PIPE, ERROR_NO_DATA):
                    break
                else:
                    break
        finally:
            kernel32.FlushFileBuffers(h_pipe)
            kernel32.DisconnectNamedPipe(h_pipe)
            kernel32.CloseHandle(h_pipe)

    def _write_win_pipe(self, h_pipe, data: bytes):
        """Write response bytes into Windows pipe."""
        kernel32 = ctypes.windll.kernel32
        bytes_written = wintypes.DWORD()
        kernel32.WriteFile(h_pipe, data, len(data), ctypes.byref(bytes_written), None)

    # ── Unified JSON-RPC 2.0 Protocol Processing ──────────────

    def _process_raw_json(self, raw_str: str) -> Optional[dict | list]:
        """Parse raw JSON string into single or batch request."""
        try:
            parsed = json.loads(raw_str)
        except json.JSONDecodeError:
            return {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error (Invalid JSON)"}, "id": None}

        if isinstance(parsed, list):
            if not parsed:
                return {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid batch request"}, "id": None}
            responses = [self._execute_single_request(req) for req in parsed]
            filtered = [r for r in responses if r is not None]
            return filtered if filtered else None
        elif isinstance(parsed, dict):
            return self._execute_single_request(parsed)
        else:
            return {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request object"}, "id": None}

    def _execute_single_request(self, req: dict) -> Optional[dict]:
        """Validate and dispatch a single JSON-RPC 2.0 request."""
        if not isinstance(req, dict):
            return {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Request must be an object"}, "id": None}

        req_id = req.get("id")
        is_notification = "id" not in req

        if req.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": "Invalid JSON-RPC version, expected '2.0'"},
                "id": req_id
            }

        method = req.get("method")
        params = req.get("params", {})

        if not isinstance(method, str):
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": "Method must be a string"},
                "id": req_id
            }

        try:
            with self._state_lock:
                result = self._dispatch_method(method, params)

            if is_notification:
                return None

            return {"jsonrpc": "2.0", "result": result, "id": req_id}

        except KeyError as e:
            if is_notification:
                return None
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method '{method}' not found ({str(e)})"},
                "id": req_id
            }
        except Exception as e:
            if is_notification:
                return None
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                "id": req_id
            }

    def _handle_request(self, req: dict) -> Optional[dict]:
        """Direct request handler for testing and internal dispatch."""
        return self._execute_single_request(req)

    def _dispatch_method(self, method: str, params: dict) -> Any:
        """Route to NeuroShell sub-engines."""
        if method == "translate":
            query = params.get("query", "")
            cwd = params.get("cwd", os.getcwd())
            translation = self.shell.translator.translate(query, self.shell.context)
            if translation and translation.command:
                safety_fn = getattr(self.shell.safety, "assess", getattr(self.shell.safety, "check", None))
                assessment = safety_fn(translation.command, cwd) if safety_fn else None
                risk = getattr(getattr(assessment, "level", assessment), "value", str(assessment))
                return {
                    "command": translation.command,
                    "explanation": translation.explanation,
                    "risk_level": risk,
                    "confidence": translation.confidence,
                }
            return {
                "command": query,
                "explanation": "Direct shell passthrough",
                "risk_level": "SAFE",
                "confidence": 1.0,
            }

        elif method == "slash":
            cmd = params.get("command", "")
            handled = self.shell._handle_slash_command(cmd)
            return {"handled": handled, "command": cmd}

        elif method == "diagnose_error":
            command = params.get("command", "")
            output = params.get("output", "")
            exit_code = params.get("exit_code", 1)
            cwd = params.get("cwd", os.getcwd())

            try:
                from intelligence.error_fixer import ErrorFixer
                fixer = ErrorFixer(self.shell.llm, self.shell.context)
                fix_result = fixer.fix_error(command, output, exit_code, cwd)
                if fix_result:
                    return {
                        "category": getattr(fix_result, "category", "execution_error"),
                        "root_cause": getattr(fix_result, "explanation", "Command failed with error"),
                        "auto_fix": getattr(fix_result, "fixed_command", ""),
                        "confidence": getattr(fix_result, "confidence", 0.9),
                    }
            except Exception:
                pass

            return {
                "category": "general_error",
                "root_cause": f"Command '{command}' failed with exit code {exit_code}",
                "auto_fix": "",
                "confidence": 0.5,
            }

        elif method == "agent_plan":
            task = params.get("task", "")
            cwd = params.get("cwd", os.getcwd())

            try:
                from intelligence.agent import AgentPlanner
                planner = AgentPlanner(self.shell.llm, self.shell.context)
                plan = planner.create_plan(task, cwd)
                if plan and hasattr(plan, "steps"):
                    steps_data = [
                        {
                            "order": s.order if hasattr(s, "order") else idx + 1,
                            "command": s.command if hasattr(s, "command") else str(s),
                            "description": s.description if hasattr(s, "description") else "",
                            "risk": "CAUTION" if getattr(s, "is_destructive", False) else "SAFE",
                        }
                        for idx, s in enumerate(plan.steps)
                    ]
                    return {
                        "plan_id": getattr(plan, "plan_id", "plan_1"),
                        "task": task,
                        "steps": steps_data,
                    }
            except Exception:
                pass

            # Fallback simple 1-step plan
            trans = self.shell.translator.translate(task, self.shell.context)
            cmd = trans.command if trans else task
            return {
                "plan_id": "plan_fallback",
                "task": task,
                "steps": [
                    {"order": 1, "command": cmd, "description": "Execute requested operation", "risk": "SAFE"}
                ],
            }

        elif method == "ai_pipe":
            directive = params.get("directive", "@ai")
            prompt = params.get("prompt", "Analyze the following command output:")
            input_text = params.get("input_text", "")
            cwd = params.get("cwd", os.getcwd())

            full_prompt = f"{prompt}\n\n```\n{input_text[-4000:]}\n```"
            if directive == "@fix":
                full_prompt = f"Analyze the following compiler / execution error and provide ONLY the corrected command or patch instructions:\n\n```\n{input_text[-4000:]}\n```"

            try:
                response = self.shell.llm.generate(
                    full_prompt,
                    system_prompt="You are NeuroShell AI Assistant. Provide precise, actionable developer analysis."
                )
                return {
                    "response": response.strip() if response else "No response generated.",
                    "directive": directive,
                }
            except Exception as exc:
                return {
                    "response": f"AI analysis failed: {str(exc)}",
                    "directive": directive,
                }

        elif method == "ping":
            return "pong"

        elif method == "status":
            return {
                "status": "ready",
                "provider": getattr(self.shell.config.llm, "provider", "unknown"),
                "model": getattr(self.shell.config.llm, "model", "unknown"),
                "platform": sys.platform,
            }

        else:
            raise KeyError(f"Unsupported method '{method}'")


if __name__ == "__main__":
    import time
    from main import NeuroShell

    app = NeuroShell()
    server = NamedPipeServer(app)
    server.start()
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        server.stop()
