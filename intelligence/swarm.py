# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Swarm Intelligence — Multi-Agent Orchestrator
Inspired by Anthropic's Claude-Code Role-Based Architecture.
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional, List
from core.events import neuro_events

_log = logging.getLogger("neuroshell.swarm")

@dataclass
class SwarmResult:
    final_command: str
    explanation: str
    agents_used: List[str]
    is_safe: bool = True

class BaseAgent:
    def __init__(self, name: str, system_prompt: str, llm_client):
        self.name = name
        self.system_prompt = system_prompt
        self.llm = llm_client

    def execute(self, task: str, context: str) -> str:
        prompt = f"Workspace Context:\n{context}\n\nTask:\n{task}"
        _log.info(f"Swarm: Engaging [{self.name}]")
        
        # We use standard chat/generate but we do not want to pollute the global history
        # So we use `generate` with use_cache=False to get a raw response.
        res = self.llm.generate(prompt, self.system_prompt, use_cache=False)
        return res.text if res.success else ""


class PlanAgent(BaseAgent):
    """Read-only agent that parses the task and returns a structured breakdown without writing code."""
    def __init__(self, llm_client):
        super().__init__(
            name="PlanAgent",
            system_prompt="""You are the Architect. You cannot write actual modifications. 
Your ONLY job is to read the user's objective and break it down into explicit bullet points for the Executor.
Never output code. Keep it extremely brief and high-level.""",
            llm_client=llm_client,
        )

class VerificationAgent(BaseAgent):
    """Adversarial agent that hunts for bugs in the proposed command before execution."""
    def __init__(self, llm_client):
        super().__init__(
            name="VerificationAgent",
            system_prompt="""You are an adversarial QA engineer. You will receive a proposed shell command or python script. 
Your goal is to find bugs, security vulnerabilities (like rm -rf), or syntax errors. 
If it is safe, output the single word 'SAFE'. If it is dangerous or broken, output 'UNSAFE' followed by why.""",
            llm_client=llm_client,
        )

class GeneralPurposeAgent(BaseAgent):
    """The actual executor that writes the final shell commands."""
    def __init__(self, llm_client):
        super().__init__(
            name="GeneralPurposeAgent",
            system_prompt="""You are the Executor. You receive an Architect's plan and output the precise shell command to accomplish it.
ONLY output the shell command. Do not explain. Do not use markdown backticks unless strictly necessary.""",
            llm_client=llm_client,
        )


class SwarmOrchestrator:
    """Manages multi-agent parallel workflows for complex prompts, utilizing Git Sandbox."""
    
    def __init__(self, llm_client, context_manager=None):
        self.llm = llm_client
        self.context = context_manager
        
        # Instantiate Swarm
        self.planner = PlanAgent(llm_client)
        self.executor = GeneralPurposeAgent(llm_client)
        self.verifier = VerificationAgent(llm_client)

    def route_task(self, prompt: str) -> SwarmResult:
        """Orchestrates the Swarm Pipeline: Plan -> Execute -> Sandbox Test -> Verify."""
        ctx_summary = self.context.get_context_summary() if self.context else ""
        
        neuro_events.emit("swarm_update", "[🧠 Swarm] Intercepted complex task. Orchestrating...")
        
        agents_used = []
        
        # Step 1: Planning
        neuro_events.emit("swarm_update", "  ↳ [PlannerAgent] Drafting architectural plan...")
        plan = self.planner.execute(prompt, ctx_summary)
        agents_used.append("PlanAgent")
        neuro_events.emit("swarm_update", f"  ↳ [PlannerAgent] Done. Prepared {len(plan.splitlines())} steps.")
        
        # Step 2: Execution
        neuro_events.emit("swarm_update", "  ↳ [ExecutorAgent] Mapping plan to raw shell commands...")
        exec_payload = f"Original Request: {prompt}\nArchitect Plan:\n{plan}"
        proposed_command = self.executor.execute(exec_payload, ctx_summary)
        agents_used.append("GeneralPurposeAgent")
        neuro_events.emit("swarm_update", f"  ↳ [ExecutorAgent] Output: {proposed_command[:60]}...")
        
        # Stop reasoning tags from breaking things
        if "<think>" in proposed_command:
            import re
            proposed_command = re.sub(r'<think>.*?</think>', '', proposed_command, flags=re.DOTALL).strip()
            
        # Strip markdown fences if present
        if proposed_command.startswith("```"):
            lines = proposed_command.split("\\n")
            proposed_command = "\\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            
        proposed_command = proposed_command.strip()

        # Step 3: Verification (Adversarial Static Review)
        verification = self.verifier.execute(proposed_command, ctx_summary)
        agents_used.append("VerificationAgent")
        
        if "UNSAFE" in verification.upper():
            return SwarmResult(
                final_command="",
                explanation=f"Verification Agent Halted Execution: {verification}",
                agents_used=agents_used,
                is_safe=False
            )

        # Step 4: Sandbox Trial Run
        neuro_events.emit("swarm_update", "  ✓ [VerificationAgent] PASSED.")
        import os
        from core.sandbox import GitSandbox
        primary_dir = os.getcwd() # NeuroShell's active cwd
        sandbox = GitSandbox(primary_dir)
        
        try:
            if not sandbox.is_git_repo():
                neuro_events.emit("swarm_update", "  ⚠ [Sandbox] Target is not a git repo. Deploying naked command...")
                return SwarmResult(
                    final_command=proposed_command,
                    explanation=f"Swarm Plan: {plan[:100]}...\n[Warning: Git Sandbox disabled because cwd is not a git repo]",
                    agents_used=agents_used,
                    is_safe=True
                )
                
            neuro_events.emit("swarm_update", "  ↳ [Sandbox] Spawning ephemeral Git Worktree...")
            sandbox.create()
            
            neuro_events.emit("swarm_update", "  ↳ [Sandbox] Executing isolated test run...")
            run_result = sandbox.execute(proposed_command)
            
            if run_result.returncode != 0:
                neuro_events.emit("swarm_update", f"  ❌ [Sandbox] Trial Failed (Exit code {run_result.returncode})! Rolling back safely.")
                sandbox.cleanup()
                return SwarmResult(
                    final_command="",
                    explanation=f"Swarm Sandbox Trial Failed: Exit {run_result.returncode}\nStderr: {run_result.stderr}",
                    agents_used=agents_used,
                    is_safe=False
                )
                
            neuro_events.emit("swarm_update", "  ✓ [Sandbox] Command did not crash. Diffing changes...")
            diff_text = sandbox.diff()
            if not diff_text.strip():
                neuro_events.emit("swarm_update", "  ✓ [Sandbox] Read-only / No filesystem mutation.")
                sandbox.cleanup()
                return SwarmResult(
                    final_command=proposed_command,
                    explanation=f"Swarm Sandbox passed (No file changes). It will now run on Primary.\n\nPlan: {plan}",
                    agents_used=agents_used,
                    is_safe=True
                )
                
            neuro_events.emit("swarm_update", "  🚀 [Sandbox] Mutated files safely. Fast-forward merging to primary tree...")
            applied = sandbox.apply_to_primary()
            sandbox.cleanup()
            
            if applied:
                agents_used.append("Sandbox")
                neuro_events.emit("swarm_update", "  ✅ [Swarm] Operations fully completed and securely merged.")
                return SwarmResult(
                    final_command="echo 'NeuroShell Swarm: Operations executed and merged successfully via Sandbox.'",
                    explanation=f"Swarm autonomously wrote and merged changes using Git Sandbox.\n\nDiff Summary:\n```diff\n{diff_text[:500]}...\n```",
                    agents_used=agents_used,
                    is_safe=True
                )
            else:
                neuro_events.emit("swarm_update", "  ❌ [Swarm] Merge to primary failed.")
                return SwarmResult(
                    final_command="",
                    explanation="Swarm Sandbox trial succeeded, but apply_to_primary failed (Merge conflict?).",
                    agents_used=agents_used,
                    is_safe=False
                )
                
        except Exception as e:
            if sandbox.sandbox_dir:
                sandbox.cleanup()
            return SwarmResult(
                final_command=proposed_command,
                explanation=f"Swarm failed to use Sandbox: {e}\nExecuting naked command.",
                agents_used=agents_used,
                is_safe=True
            )
