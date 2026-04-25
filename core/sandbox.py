# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Git Worktree Sandbox
Provides isolated execution environments for dangerous commands, allowing safe 
rollback without affecting the primary working directory.
"""

import os
import subprocess
import logging
import uuid
import shutil
from pathlib import Path
from core.events import neuro_events

_log = logging.getLogger("neuroshell.sandbox")

class GitSandbox:
    """Manages ephemeral git worktrees for safe, isolated execution."""
    
    def __init__(self, primary_workspace: str):
        self.primary = Path(primary_workspace).resolve()
        self.sandbox_dir: Path | None = None
        self.sandbox_branch: str | None = None

    def is_git_repo(self) -> bool:
        """Check if the primary workspace is a git repository."""
        return (self.primary / ".git").is_dir()

    def create(self) -> str:
        """Create a new ephemeral git worktree sandbox."""
        if not self.is_git_repo():
            raise RuntimeError("Cannot create sandbox: Workspace is not a git repository.")

        uid = str(uuid.uuid4())[:8]
        self.sandbox_branch = f"ns-sandbox-{uid}"
        
        # Place the sandbox as a sibling to the primary workspace to avoid recursive indexing
        self.sandbox_dir = self.primary.parent / f"{self.primary.name}-sandbox-{uid}"

        _log.info(f"Creating Git Sandbox: {self.sandbox_dir}")
        neuro_events.emit("swarm_update", f"  ↳ [Sandbox Internal] git worktree add {self.sandbox_branch}")
        try:
            subprocess.run(
                ["git", "worktree", "add", "-b", self.sandbox_branch, str(self.sandbox_dir)],
                cwd=str(self.primary),
                check=True,
                capture_output=True,
                text=True
            )
            return str(self.sandbox_dir)
        except subprocess.CalledProcessError as e:
            _log.error(f"Sandbox creation failed: {e.stderr}")
            raise RuntimeError(f"Sandbox creation failed: {e.stderr}")

    def execute(self, command: str) -> subprocess.CompletedProcess:
        """Execute a shell command inside the isolated sandbox."""
        if not self.sandbox_dir or not self.sandbox_dir.exists():
            raise RuntimeError("Sandbox environment is not active.")

        _log.info(f"Executing in Sandbox: {command}")
        import sys
        cmd_args = ["cmd.exe", "/c", command] if sys.platform == "win32" else ["sh", "-c", command]
        return subprocess.run(
            cmd_args,
            cwd=str(self.sandbox_dir),
            shell=False,
            capture_output=True,
            text=True
        )

    def diff(self) -> str:
        """View the diff of what the command changed in the sandbox."""
        if not self.sandbox_dir or not self.sandbox_dir.exists():
            return ""
            
        try:
            res = subprocess.run(
                ["git", "diff"],
                cwd=str(self.sandbox_dir),
                check=True,
                capture_output=True,
                text=True
            )
            return res.stdout
        except subprocess.CalledProcessError:
            return ""

    def apply_to_primary(self) -> bool:
        """Apply sandbox changes back to the primary workspace (Fast-Forward Merge)."""
        if not self.sandbox_dir or not self.sandbox_branch:
            return False

        _log.info(f"Committing sandbox changes and merging to primary.")
        neuro_events.emit("swarm_update", "  ↳ [Sandbox Internal] git add . && git commit")
        try:
            # Commit all changes in the sandbox
            subprocess.run(["git", "add", "."], cwd=str(self.sandbox_dir), check=True)
            res = subprocess.run(["git", "commit", "-m", "NeuroShell: Sandbox applied"], cwd=str(self.sandbox_dir), capture_output=True)
            
            if "nothing to commit" in res.stdout:
                _log.info("No changes to apply.")
                return True

            # Switch back to primary and merge the sandbox branch
            current_branch = subprocess.run(
                ["git", "branch", "--show-current"], 
                cwd=str(self.primary), capture_output=True, text=True
            ).stdout.strip()

            subprocess.run(
                ["git", "merge", self.sandbox_branch],
                cwd=str(self.primary),
                check=True,
                capture_output=True
            )
            return True
        except subprocess.CalledProcessError as e:
            _log.error(f"Failed to apply sandbox changes: {e}")
            return False

    def cleanup(self):
        """Destroy the ephemeral git worktree and branch."""
        if not self.sandbox_dir or not self.sandbox_branch:
            return

        _log.info(f"Cleaning up Git Sandbox: {self.sandbox_dir}")
        neuro_events.emit("swarm_update", "  ↳ [Sandbox Internal] Terminating ephemeral worktree...")
        try:
            # Force remove the worktree
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(self.sandbox_dir)],
                cwd=str(self.primary),
                capture_output=True
            )
            # Delete the temporary branch
            subprocess.run(
                ["git", "branch", "-D", self.sandbox_branch],
                cwd=str(self.primary),
                capture_output=True
            )
            
            # Failsafe cleanup map
            if self.sandbox_dir.exists():
                shutil.rmtree(self.sandbox_dir, ignore_errors=True)
                
        except Exception as e:
            _log.error(f"Sandbox cleanup failed: {e}")
        finally:
            self.sandbox_dir = None
            self.sandbox_branch = None
