# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
import asyncio
import json
import logging
import threading
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

import sys
import os
import psutil

# Ensure project root in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_config
from llm.client import LLMClient
from intelligence.translator import Translator
from core.executor import ShellExecutor
from core.context import ContextManager
from core.history import HistoryStore
from core.events import neuro_events
from pathlib import Path

app = FastAPI(title="NeuroShell Terminal Server")

# Allow CORS for dev environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core Telemetry state
_last_telemetry = {
    "total_commands": 0,
    "success_commands": 0,
    "error_commands": 0,
    "latency_samples": [],
}

# Serve built Vite frontend
app.mount("/assets", StaticFiles(directory="neuroshell-web/dist/assets"), name="assets")

@app.get("/")
async def serve_frontend():
    return FileResponse("neuroshell-web/dist/index.html", headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    })

# Initialize Core Services
try:
    config = load_config()
    llm_client = LLMClient(config)
    executor = ShellExecutor(config)
    context = ContextManager(config)
    history = HistoryStore(Path('history.db'))
    translator = Translator(llm_client, context, history)
    logging.info("NeuroShell core engines loaded and ready.")
except Exception as e:
    logging.error(f"Failed to initialize core engines: {e}")
    sys.exit(1)


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

manager = ConnectionManager()

@app.websocket("/ws/telemetry")
async def telemetry_endpoint(websocket: WebSocket):
    await websocket.accept()
    output_queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _on_swarm(msg: str):
        try:
            asyncio.run_coroutine_threadsafe(
                output_queue.put({"type": "swarm_update", "payload": msg}), loop
            )
        except Exception:
            pass
            
    def _on_gc(msg: str):
        try:
            asyncio.run_coroutine_threadsafe(
                output_queue.put({"type": "gc_update", "payload": msg}), loop
            )
        except Exception:
            pass

    neuro_events.subscribe("swarm_update", _on_swarm)
    neuro_events.subscribe("gc_update", _on_gc)

    try:
        while True:
            msg = await output_queue.get()
            await websocket.send_json(msg)
    except Exception as e:
        logging.error(f"Telemetry socket error: {e}")
    finally:
        neuro_events.unsubscribe("swarm_update", _on_swarm)
        neuro_events.unsubscribe("gc_update", _on_gc)
        try:
            await websocket.close()
        except:
            pass

@app.websocket("/ws/sysmon")
async def sysmon_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Gather top processes
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'memory_percent', 'cpu_percent']):
                try:
                    info = p.info
                    # For safety, avoid sending everything, just memory heavy ones
                    if info['memory_percent'] is not None and info['memory_percent'] > 0.05:
                        procs.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            procs.sort(key=lambda x: x.get('memory_percent', 0), reverse=True)
            top_procs = []
            for p in procs[:10]:
                top_procs.append({
                    "pid": p['pid'],
                    "name": p['name'],
                    "cpu": round(p.get('cpu_percent', 0) or 0, 1),
                    "mem": round(p.get('memory_percent', 0) or 0, 1)
                })

            payload = {
                "cpu": psutil.cpu_percent(),
                "mem": psutil.virtual_memory().percent,
                "disk": psutil.disk_usage('/').percent,
                "procs": top_procs
            }
            await websocket.send_json(payload)
            await asyncio.sleep(2)
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except:
            pass
            
@app.get("/api/dashboard")
async def dashboard_api():
    """Return static dashboard state."""
    cwd = os.getcwd()
    return {
        "session_id": "WS-Active",
        "commands": _last_telemetry["total_commands"],
        "shell": config.get('shell', 'powershell').title(),
        "cwd": cwd,
        "uptime": "Active",
        "history": len(history._history) if hasattr(history, '_history') else 0
    }

@app.websocket("/ws/terminal")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    # Send a custom welcome line to the terminal
    await websocket.send_text("\x1b[1;35mNeuroShell Core Server [Online]\x1b[0m\r\n\r\n")

    # Sync-to-Async bridging queue for real-time terminal stream
    output_queue = asyncio.Queue()

    # Capture the main event loop
    loop = asyncio.get_running_loop()

    def sync_stream_callback(text: str):
        # The executor calls this from its monitoring thread (or main thread)
        # We put it in the async queue to be pushed to the websocket
        if text is not None:
            # Reformat text to ensure carriage return + newline for xterm.js
            # Normalize all newlines to CRLF, and append CRLF if missing
            formatted = text.replace('\r\n', '\n').replace('\n', '\r\n')
            if not formatted.endswith('\r\n'):
                formatted += '\r\n'
            asyncio.run_coroutine_threadsafe(output_queue.put(formatted), loop)

    async def emit_loop():
        """Continuously drain the queue to the client."""
        while True:
            try:
                msg = await output_queue.get()
                await websocket.send_text(msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"emit_loop error: {e}")

    emit_task = asyncio.create_task(emit_loop())

    try:
        while True:
            # Await user input JSON
            data = await websocket.receive_text()
            logging.info(f"Terminal Command Received: {data}")
            try:
                frame = json.loads(data)
                with open('received.txt', 'a') as f:
                    f.write(f"RECV: {frame}\n")
            except Exception as e:
                logging.error(f"JSON Decode Error: {e}")
                continue

            if frame.get("type") == "config":
                if "force_swarm" in frame:
                    translator.force_swarm = bool(frame["force_swarm"])
                    sync_stream_callback(f"\x1b[1;35m[System] Swarm Mode {'Enabled' if translator.force_swarm else 'Disabled'}\x1b[0m\n")
                continue

            if frame.get("type") == "input":
                user_cmd = frame.get("payload", "").strip()
                if not user_cmd:
                    continue
                
                # Echo what the user typed so it instantly locks into the terminal history
                await websocket.send_text(f"\r\n\x1b[1;38;5;250mneuroshell\x1b[0m \x1b[1;32m>\x1b[0m \x1b[38;5;15m{user_cmd}\x1b[0m\r\n")
                _last_telemetry["total_commands"] += 1

                def execute_pipeline(raw_input: str):
                    try:
                        # 1. AI NLP Translation
                        translation_result = translator.translate(raw_input)
                        if not translation_result or not translation_result.has_command:
                            sync_stream_callback(f"\x1b[1;31m[!] Could not understand command: {raw_input}\x1b[0m\n")
                            return

                        command_to_run = translation_result.command
                        
                        # 2. Add some telemetry
                        sync_stream_callback(f"\x1b[38;5;240m[AI Translator] {translation_result.explanation}\x1b[0m\n")
                        sync_stream_callback(f"\x1b[1;36m$ {command_to_run}\x1b[0m\n")

                        # 3. Execution
                        res = executor.execute(
                            command=command_to_run,
                            stream_callback=sync_stream_callback,
                            timeout=60
                        )
                        
                        if res.exit_code != 0:
                            sync_stream_callback(f"\n\x1b[1;31m[Pipeline exited with code {res.exit_code}]\x1b[0m\n")
                        else:
                            sync_stream_callback(f"\n\x1b[1;32m[Success in {res.duration_ms:.0f}ms]\x1b[0m\n")

                    except Exception as e:
                        sync_stream_callback(f"\n\x1b[1;31m[CRITICAL ERROR] {str(e)}\x1b[0m\n")

                # Run the pipeline in another thread to avoid blocking the websocket event loop
                threading.Thread(target=execute_pipeline, args=(user_cmd,), daemon=True).start()

    except Exception as e:
        logging.error(f"WS Disconnect or error: {e}")
    finally:
        manager.disconnect(websocket)
        emit_task.cancel()

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
