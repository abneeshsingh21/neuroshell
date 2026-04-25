# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
import asyncio
from typing import Any, AsyncGenerator, Dict
from intelligence.tools.base_tool import BaseTool
from intelligence.mcp.mcp_client import MCPClient

class MCPTool(BaseTool):
    """
    Sub-agent tool that binds to an MCPClient to dynamically explore
    and execute standard MCP tools/resources over HTTP.
    """
    def __init__(self, mcp_client: MCPClient):
        self.mcp = mcp_client

    @property
    def name(self) -> str:
        return "mcp_tool"

    @property
    def description(self) -> str:
        return "Interact with remote Model Context Protocol (MCP) servers to list resources or execute dynamic tools."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: 'list_resources', 'read_resource', 'list_tools', 'execute_tool'"
                },
                "uri": {
                    "type": "string",
                    "description": "Required if action is 'read_resource'."
                },
                "tool_name": {
                    "type": "string",
                    "description": "Required if action is 'execute_tool'."
                },
                "tool_params": {
                    "type": "object",
                    "description": "Parameters for 'execute_tool'."
                }
            },
            "required": ["action"]
        }

    def can_use_tool(self, **kwargs) -> bool:
        return True

    async def call(self, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        action = kwargs.get("action")
        
        yield {"type": "progress", "message": f"Communicating with MCP endpoint for action: {action}..."}
        
        try:
            if action == "list_resources":
                res = await self.mcp.list_resources()
            elif action == "read_resource":
                uri = kwargs.get("uri", "")
                from intelligence.mcp.policy_limits import PolicyLimits
                is_safe, reason = PolicyLimits().validate_path(uri)
                if not is_safe and not uri.startswith("http"):
                    res = {"error": f"Sandbox blocked resource read: {reason}"}
                else:
                    res = await self.mcp.read_resource(uri)
            elif action == "list_tools":
                res = await self.mcp.list_tools()
            elif action == "execute_tool":
                params = kwargs.get("tool_params", {})
                from intelligence.mcp.policy_limits import PolicyLimits
                policy = PolicyLimits()
                
                # Check suspicious path parameters in MCP execution
                is_blocked = False
                block_reason = ""
                for k, v in params.items():
                    if isinstance(v, str) and (k in ["path", "dir", "uri", "filename", "filepath"]):
                        safe, reason = policy.validate_path(v, require_write_access=False)
                        if not safe and not v.startswith("http"):
                            is_blocked = True
                            block_reason = reason
                            break
                            
                if is_blocked:
                    res = {"error": f"MCP execution blocked by sandbox: {block_reason}"}
                else:
                    res = await self.mcp.execute_tool(kwargs.get("tool_name", ""), params)
            else:
                res = {"error": "Invalid action"}
                
            if "error" in res:
                yield {"type": "error", "message": res["error"]}
            else:
                yield {"type": "result", "data": res}
        except Exception as e:
            yield {"type": "error", "message": str(e)}
