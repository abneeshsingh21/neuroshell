# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
import asyncio

# Import Phase 5 stuff
from intelligence.lsp.lsp_client import LSPClient
from intelligence.mcp.mcp_client import MCPClient
from intelligence.modes.plan_mode import PlanModeController
from intelligence.tasks.task_manager import TaskManager
from intelligence.tools.lsp_tool import LSPTool
from intelligence.tools.mcp_tool import MCPTool
from intelligence.tools.mode_tools import ModeTool
from intelligence.tools.task_tools import TaskSystemTool
from intelligence.voice.audio_capture import AudioCapture
from intelligence.voice.whisper_bridge import WhisperBridge


async def run_tests():
    print("Testing LSP subsystem...")
    # Mocking standard subprocess creation
    lsp = LSPClient(["bash", "-c", "echo {}"])
    LSPTool(lsp)
    print("LSP loaded.")

    print("Testing MCP subsystem...")
    mcp_client = MCPClient("http://localhost:8080", api_key="test")
    MCPTool(mcp_client)
    print("MCP loaded.")

    print("Testing Tasks Swarm...")
    tm = TaskManager()
    TaskSystemTool(tm)
    task_id = await tm.create_task("do a test")
    t_stat = await tm.get_task(task_id)
    assert t_stat["goal"] == "do a test"
    print("Tasks loaded.")

    print("Testing Voice Subsystem...")
    try:
        AudioCapture()
        WhisperBridge(api_key="123")
        print("Voice loaded.")
    except Exception as e:
        print(f"Voice skipped/warning: {e}")

    print("Testing Mode Tools...")
    pmc = PlanModeController()
    ModeTool(pmc)
    pmc.enter_plan_mode()
    assert pmc.is_active is True
    pmc.exit_plan_mode()
    assert pmc.is_active is False
    print("Modes loaded.")

if __name__ == "__main__":
    asyncio.run(run_tests())
