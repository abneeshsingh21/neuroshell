# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
import asyncio
from typing import Any, AsyncGenerator, Dict
from intelligence.tools.base_tool import BaseTool
from intelligence.tasks.task_manager import TaskManager

class TaskSystemTool(BaseTool):
    """
    Sub-agent tool to interact with the background async task manager queue.
    Supports dispatching, listing, and halting worker agents.
    """
    def __init__(self, task_manager: TaskManager):
        self.tm = task_manager

    @property
    def name(self) -> str:
        return "task_tool"

    @property
    def description(self) -> str:
        return "Dispatch and manage background autonomous worker swarms."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: 'create', 'list', 'status', 'stop'"
                },
                "goal": {
                    "type": "string",
                    "description": "Required if action is 'create'."
                },
                "task_id": {
                    "type": "string",
                    "description": "Required if action is 'status' or 'stop'."
                }
            },
            "required": ["action"]
        }

    def can_use_tool(self, **kwargs) -> bool:
        return True

    async def call(self, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        action = kwargs.get("action")
        
        yield {"type": "progress", "message": f"Task System -> {action}..."}
        
        try:
            if action == "create":
                task_id = await self.tm.create_task(kwargs.get("goal", ""))
                yield {"type": "result", "data": {"task_id": task_id, "status": "Dispatched"}}
            elif action == "list":
                tasks = await self.tm.list_tasks()
                yield {"type": "result", "data": tasks}
            elif action == "status":
                status = await self.tm.get_task(kwargs.get("task_id", ""))
                yield {"type": "result", "data": status}
            elif action == "stop":
                await self.tm.stop_task(kwargs.get("task_id", ""))
                yield {"type": "result", "data": {"message": "Stopped task"}}
            else:
                yield {"type": "error", "message": "Invalid action"}
        except Exception as e:
            yield {"type": "error", "message": str(e)}
