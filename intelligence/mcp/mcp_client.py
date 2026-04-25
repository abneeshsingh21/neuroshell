# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
MCP Client — Model Context Protocol
Orchestrates connections to standard MCP servers allowing NeuroShell AI
to retrieve dynamic resources, prompts, and tool abstractions securely.
"""

import json
import httpx
from typing import Dict, Any, List

class MCPClient:
    def __init__(self, endpoint_url: str, api_key: str = None):
        self.endpoint_url = endpoint_url.rstrip('/')
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    async def list_resources(self) -> List[Dict[str, Any]]:
        """Fetch available context resources exposed by the MCP server."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.endpoint_url}/mcp/resources", headers=self.headers)
            resp.raise_for_status()
            return resp.json().get("resources", [])

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """Fetch the exact text content of an MCP resource."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.endpoint_url}/mcp/resources/read", params={"uri": uri}, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Fetch custom tools exposed by the MCP environment."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.endpoint_url}/mcp/tools", headers=self.headers)
            resp.raise_for_status()
            return resp.json().get("tools", [])

    async def execute_tool(self, name: str, params: dict) -> Dict[str, Any]:
        """Request the MCP server to execute one of its local tools."""
        async with httpx.AsyncClient() as client:
            payload = {"name": name, "parameters": params}
            resp = await client.post(f"{self.endpoint_url}/mcp/tools/execute", json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()
