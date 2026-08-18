# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Coordinator — Swarm Task Manager

This module implements the CoordinatorMode which serves as the router
for sub-agents and background tasks. Rather than one monolith LLM,
the Coordinator evaluates the query and spawns specialized Tools or Agents.
"""

from collections.abc import AsyncGenerator
from typing import Any, Dict


class Coordinator:
    """
    Central router for the Agent Swarm.
    Evaluates Natural Language input and delegates to specific tools or sub-agents.
    """
    def __init__(self, llm_client, context_manager):
        self.llm_client = llm_client
        self.context = context_manager
        self._tools_registry = {}
        self._register_default_tools()

    def _register_default_tools(self):
        # We lazily import to avoid circular dependencies
        try:
            from intelligence.smart_open import SmartOpenTool
            from operations.git_ops import GitTool

            # Register specific tools
            self.register_tool(SmartOpenTool())
            self.register_tool(GitTool())
        except ImportError:
            pass

    def register_tool(self, tool):
        self._tools_registry[tool.name] = tool

    async def route_request(self, user_input: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Evaluate the prompt and route to a tool or agent stream.
        """
        # Yield an initial progress event
        yield {"type": "progress", "message": "Coordinator evaluating request..."}

        # Determine intent (simplified router for now)
        intent = self._detect_intent(user_input)

        if intent == "smart_open":
            tool = self._tools_registry.get("smart_open_tool")
            if tool:
                yield {"type": "progress", "message": "Delegating to SmartOpen Agent..."}
                async for chunk in tool.call(query=user_input):
                    yield chunk
                return

        elif intent == "git":
            tool = self._tools_registry.get("git_tool")
            if tool:
                yield {"type": "progress", "message": "Delegating to Git Agent..."}
                # For Git, in a real implementation we'd use LLM to extract arguments
                # Here we mock a basic status call
                async for chunk in tool.call(action="status"):
                    yield chunk
                return

        # Default fallback to Translator / Local Execution
        yield {"type": "progress", "message": "No dedicated agent found, routing to local Translator..."}
        # In a fully connected implementation, this would invoke the stripped-down Translator
        # For now we yield a placeholder fallback result
        yield {"type": "result", "data": "Routed to command execution fallback"}

    def _detect_intent(self, user_input: str) -> str:
        """
        Detects if the query should be routed to a specific agent using heuristics.
        In the future, this can use a fast LLM classification call.
        """
        lower = user_input.lower()
        if lower.startswith("open ") or lower.startswith("launch "):
            return "smart_open"
        if "git" in lower or "clone" in lower:
            return "git"

        return "general"
