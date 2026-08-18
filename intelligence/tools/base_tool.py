# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any, Dict


class BaseTool(ABC):
    """
    Abstract Base Class for all NeuroShell Agent Tools.
    Modeled after Claude Code's tool protocol where tools yield progressive
    status updates before returning their final result.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The identifier name of the tool, used by the model."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """A detailed description of what the tool does."""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        """
        JSON Schema of the tool's input parameters.
        Returns a dict matching the OpenAI / Anthropic tool schema format.
        """
        pass

    def can_use_tool(self, **kwargs) -> bool:
        """
        Permission gateway for the tool.
        Returns True if the tool can execute without interactive approval.
        Override to implement tool-specific safety checks.
        """
        return True

    @abstractmethod
    async def call(self, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute the tool asynchronously and yield status updates.
        
        Yields dictionaries with keys like:
        - `type`: 'progress' | 'result' | 'error'
        - `message`: User-facing progress message (e.g. "Cloning repo...")
        - `data`: The final result string/dict when type == 'result'
        """
        pass
