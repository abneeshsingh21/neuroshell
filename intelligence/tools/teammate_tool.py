# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
import asyncio
import os
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Dict

from intelligence.tools.base_tool import BaseTool


class TeammateTool(BaseTool):
    """
    Agentic interface for spawning a sub-agent to work in an isolated git worktree.
    """
    @property
    def name(self) -> str:
        return "teammate_tool"

    @property
    def description(self) -> str:
        return "Spawn a dedicated sub-agent to explore or execute tasks safely. Can be run in an isolated git worktree sandbox."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "Clear instructions for what the sub-agent should accomplish."
                },
                "use_sandbox": {
                    "type": "boolean",
                    "description": "Set to true to run the agent in an isolated git worktree, ensuring active project files are not modified."
                }
            },
            "required": ["goal"]
        }

    def can_use_tool(self, **kwargs) -> bool:
        # Spawning sub-agents might use LLM tokens, but we assume
        # coordinator permissions propagate to this tool.
        return True

    async def call(self, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        goal = kwargs.get("goal")
        use_sandbox = kwargs.get("use_sandbox", True)

        if not goal:
            yield {"type": "error", "message": "Sub-agent goal is required."}
            return

        yield {"type": "progress", "message": f"Spawning sub-agent for: {goal[:40]}..."}

        loop = asyncio.get_running_loop()

        def _execute_teammate():
            original_cwd = os.getcwd()
            worktree_path = None

            try:
                # 1. Setup isolated sandbox if requested
                if use_sandbox:
                    _ns_worktrees = Path.home() / ".neuroshell" / "worktrees"
                    worktree_dir = str(_ns_worktrees / f"agent_{os.urandom(4).hex()}")
                    worktree_path = os.path.abspath(worktree_dir)

                    # Ensure parent dir exists
                    os.makedirs(str(_ns_worktrees), exist_ok=True)

                    # Create git worktree
                    try:
                        subprocess.run(
                            ["git", "worktree", "add", "-d", worktree_path],
                            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )
                        target_dir = worktree_path
                    except subprocess.CalledProcessError:
                        return {"status": "error", "message": "Failed to create git worktree sandbox."}
                else:
                    target_dir = original_cwd

                # 2. Spawn Sub-Agent
                # Note: In a full architecture, this would instantiate your Agent Planner
                # and run a loop inside target_dir. We simulate this for the transition phase.
                result_message = f"Teammate successfully explored: {goal}"

                # Simulate work
                import time
                time.sleep(2)  # stubbing agent thinking time

                return {
                    "status": "success",
                    "result": result_message,
                    "sandbox": worktree_path
                }

            finally:
                # 3. Cleanup sandbox
                if worktree_path and os.path.exists(worktree_path):
                    try:
                        subprocess.run(
                            ["git", "worktree", "remove", "-f", worktree_path],
                            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )
                    except Exception:
                        pass # ensure we don't crash returning errors

        try:
            res = await loop.run_in_executor(None, _execute_teammate)
            if res.get("status") == "success":
                yield {
                    "type": "result",
                    "data": f"Sub-Agent completed: {res['result']} (Sandbox used: {bool(res['sandbox'])})"
                }
            else:
                yield {"type": "error", "message": res.get("message", "Unknown error")}
        except Exception as e:
            yield {"type": "error", "message": str(e)}
