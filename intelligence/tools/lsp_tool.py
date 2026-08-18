# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
import asyncio
from collections.abc import AsyncGenerator
from typing import Any, Dict

from intelligence.lsp.lsp_client import LSPClient
from intelligence.tools.base_tool import BaseTool


class LSPTool(BaseTool):
    """
    Sub-agent tool that binds to an active Language Server Protocol (LSP) instance
    to resolve symbols, references, and definitions accurately.
    """
    def __init__(self, lsp_client: LSPClient):
        self.lsp = lsp_client

    @property
    def name(self) -> str:
        return "lsp_tool"

    @property
    def description(self) -> str:
        return "Query precise code definitions and AST references using a language server."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action to perform: 'definition' or 'references'."
                },
                "file_uri": {
                    "type": "string",
                    "description": "Absolute file URI"
                },
                "line": {"type": "integer"},
                "character": {"type": "integer"}
            },
            "required": ["action", "file_uri", "line", "character"]
        }

    def can_use_tool(self, **kwargs) -> bool:
        return True

    async def call(self, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        action = kwargs.get("action")
        uri = kwargs.get("file_uri")
        line = kwargs.get("line")
        char = kwargs.get("character")

        yield {"type": "progress", "message": f"Querying LSP for {action} at {uri}:{line}:{char}..."}

        loop = asyncio.get_running_loop()

        def _fetch():
            if action == "definition":
                return self.lsp.get_definition(uri, line, char)
            return {"error": "Unsupported LSP action"}

        try:
            res = await loop.run_in_executor(None, _fetch)
            if "error" in res:
                yield {"type": "error", "message": res["error"]}
            else:
                yield {"type": "result", "data": res}
        except Exception as e:
            yield {"type": "error", "message": str(e)}
