# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
import os
from pathlib import Path
from typing import List


class PolicyLimits:
    """
    Enforces file-system boundary sandboxing for MCP tools and sub-agents.
    By default, restricts access exclusively to the active workspace directory
    and explicitly whitelisted system directories.
    """

    def __init__(self, workspace_root: str | None = None):
        if workspace_root:
            self.workspace_root = Path(workspace_root).resolve()
        else:
            self.workspace_root = Path(os.getcwd()).resolve()

        # System absolute paths that are inherently safe for reading (but not writing)
        self.whitelisted_read_paths: List[Path] = []

        # Define cross-platform standard desktop/downloads paths as semi-safe
        # (AI can read from them if explicitly requested, but sandbox warns)
        try:
            home = Path.home()
            self.whitelisted_read_paths.extend([
                (home / "Downloads").resolve(),
                (home / "Desktop").resolve(),
                (home / "Documents").resolve()
            ])
        except Exception:
            pass

    def validate_path(self, target_path: str, require_write_access: bool = False) -> tuple[bool, str]:
        """
        Validates if the provided path is within allowed boundaries.
        Returns (is_safe, reason).
        """
        try:
            # Resolve resolves symlinks and normalizes the path to an absolute path
            target = Path(target_path).resolve()
        except Exception as e:
            return False, f"Malformed path: {e}"

        # 1. Workspace Isolation: Any path inside the workspace is fully allowed
        try:
            if target.is_relative_to(self.workspace_root):
                # Ensure it's not targeting internal .git or secure env files directly
                if ".git" in target.parts or ".env" in target.parts:
                    return False, "Access to internal version control or environment variable files is blocked by policy."
                return True, "Allowed by workspace policy."
        except AttributeError:
            # Python < 3.9 fallback
            try:
                target.relative_to(self.workspace_root)
                if ".git" in target.parts or ".env" in target.parts:
                    return False, "Access to internal version control or environment variable files is blocked by policy."
                return True, "Allowed by workspace policy."
            except ValueError:
                pass

        # 2. Strict Write Ban Outside Workspace
        if require_write_access:
            return False, f"Write blocked. Path {target} is outside the active workspace {self.workspace_root}."

        # 3. Read Whitelisting
        for safe_path in self.whitelisted_read_paths:
            if safe_path.exists():
                try:
                    if target.is_relative_to(safe_path):
                        return True, "Read allowed by global whitelist policy."
                except AttributeError:
                    try:
                        target.relative_to(safe_path)
                        return True, "Read allowed by global whitelist policy."
                    except ValueError:
                        pass

        # If it reaches here, it's outside all allowed boundaries
        return False, f"Path {target} blocked. Exceeds MCP sandbox policy limits."
