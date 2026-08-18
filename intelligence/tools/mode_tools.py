# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
from collections.abc import AsyncGenerator
from typing import Any, Dict

from intelligence.modes.plan_mode import PlanModeController
from intelligence.tools.base_tool import BaseTool


class ModeTool(BaseTool):
    """
    Sub-agent tool that allows the coordinating Agent to deliberately
    lock or unlock its execution capabilities to prevent runaway destruction.
    """
    def __init__(self, mode_controller: PlanModeController):
        self.mc = mode_controller

    @property
    def name(self) -> str:
        return "mode_tool"

    @property
    def description(self) -> str:
        return "Enter or exit 'Plan Mode' to safely construct architecture trees before execution."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "'enter_plan_mode', 'exit_plan_mode', 'add_thought'"
                },
                "content": {
                    "type": "string",
                    "description": "The thought or plan block string to append."
                }
            },
            "required": ["action"]
        }

    def can_use_tool(self, **kwargs) -> bool:
        return True

    async def call(self, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        action = kwargs.get("action")
        content = kwargs.get("content", "")

        yield {"type": "progress", "message": f"Mode System -> {action}..."}

        try:
            if action == "enter_plan_mode":
                self.mc.enter_plan_mode()
                yield {"type": "result", "data": {"status": "Locked in Plan Mode"}}
            elif action == "exit_plan_mode":
                self.mc.exit_plan_mode()
                yield {"type": "result", "data": {"status": "Execution Unlocked"}}
            elif action == "add_thought":
                if not self.mc.is_active:
                    yield {"type": "error", "message": "Must enter plan mode first."}
                    return
                self.mc.add_to_plan(content)
                yield {"type": "result", "data": {"status": "Thought recorded"}}
            else:
                yield {"type": "error", "message": "Invalid action"}
        except Exception as e:
            yield {"type": "error", "message": str(e)}
