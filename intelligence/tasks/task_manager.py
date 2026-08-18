# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Task Manager — Asynchronous Worker Swarms
Handles queuing, dispatching, and monitoring long-running sub-agents.
"""

import asyncio
import time
import uuid
from typing import Any, Dict


class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskManager:
    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create_task(self, goal: str, context: dict = None) -> str:
        """Create a new async task and return its ID."""
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        async with self._lock:
            self._tasks[task_id] = {
                "id": task_id,
                "goal": goal,
                "status": TaskStatus.PENDING,
                "context": context or {},
                "created_at": time.time(),
                "output": None,
                "error": None
            }

        # In a real environment, we'd add to an asyncio queue here
        # for a background worker pool to consume.
        # For simplicity, we dispatch immediate non-blocking future:
        asyncio.create_task(self._execute_worker(task_id))
        return task_id

    async def get_task(self, task_id: str) -> Dict[str, Any]:
        async with self._lock:
            return self._tasks.get(task_id, {})

    async def list_tasks(self) -> list:
        async with self._lock:
            return list(self._tasks.values())

    async def stop_task(self, task_id: str):
        async with self._lock:
            if task_id in self._tasks and self._tasks[task_id]["status"] == TaskStatus.RUNNING:
                self._tasks[task_id]["status"] = TaskStatus.FAILED
                self._tasks[task_id]["error"] = "Cancelled by user"

    async def _execute_worker(self, task_id: str):
        """Simulate a worker executing the exact goal asynchronously."""
        async with self._lock:
            if task_id not in self._tasks:
                return
            self._tasks[task_id]["status"] = TaskStatus.RUNNING

        print(f"[Worker] Started: {task_id}")

        # Simulate processing time depending on task complexity
        await asyncio.sleep(3)

        async with self._lock:
            if self._tasks[task_id]["status"] != TaskStatus.RUNNING:
                return # Was cancelled

            self._tasks[task_id]["status"] = TaskStatus.COMPLETED
            self._tasks[task_id]["output"] = f"Result of solving: {self._tasks[task_id]['goal']}"

        print(f"[Worker] Completed: {task_id}")
