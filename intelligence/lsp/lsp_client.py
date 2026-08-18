# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
LSP Client — Language Server Protocol Integration
Orchestrates connections to local language servers (e.g., pylsp, tsserver)
using json-rpc over stdin/stdout.
"""

import json
import subprocess
import threading
from typing import Any, Dict


class LSPClient:
    def __init__(self, server_command: list):
        self.server_command = server_command
        self.process: subprocess.Popen | None = None
        self._request_id = 1
        self._callbacks = {}
        self._lock = threading.Lock()

    def start(self):
        import sys
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        self.process = subprocess.Popen(
            self.server_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            **kwargs,
        )
        # Background thread to read responses
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process = None

    def _read_loop(self):
        while self.process and self.process.poll() is None:
            # Simple JSON-RPC reader
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                if line.startswith("Content-Length:"):
                    length = int(line.split(":")[1].strip())
                    # Skip empty line
                    self.process.stdout.readline()
                    content = self.process.stdout.read(length)
                    data = json.loads(content)

                    if "id" in data and data["id"] in self._callbacks:
                        with self._lock:
                            cb = self._callbacks.pop(data["id"])
                        cb(data)
            except Exception:
                pass

    def send_request(self, method: str, params: dict, timeout=5) -> Dict[str, Any]:
        """Send JSON-RPC request and block for response."""
        if not self.process:
            return {"error": "LSP Server not running"}

        import queue
        q = queue.Queue()

        with self._lock:
            req_id = self._request_id
            self._request_id += 1
            self._callbacks[req_id] = q.put

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params
        }
        body = json.dumps(payload)
        headers = f"Content-Length: {len(body)}\r\n\r\n"

        self.process.stdin.write(headers + body)
        self.process.stdin.flush()

        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            with self._lock:
                self._callbacks.pop(req_id, None)
            return {"error": "Timeout"}

    def initialize(self, root_uri: str):
        return self.send_request("initialize", {
            "processId": None,
            "rootUri": root_uri,
            "capabilities": {}
        })

    def get_definition(self, file_uri: str, line: int, character: int):
        return self.send_request("textDocument/definition", {
            "textDocument": {"uri": file_uri},
            "position": {"line": line, "character": character}
        })
