# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
MagicDocs — Self-Updating Knowledge Base

A background service that automatically updates project context documentation.
After a coding session (or triggered by significant events), MagicDocs uses an LLM
to scan the session transcript and recent file changes, then silently updates
a `.neuroshell/project_context.md` file so the AI's understanding of the project
is always up to date.
"""

import threading
from pathlib import Path


class MagicDocs:
    def __init__(self, llm_client):
        self.llm = llm_client
        self.trigger_lock = threading.Lock()

    def find_project_context(self) -> Path:
        """Locates the project context file. Creates it if missing."""
        # Check standard location
        ns_dir = Path.home() / ".neuroshell"
        ns_dir.mkdir(parents=True, exist_ok=True)
        ctx_file = ns_dir / "project_context.md"

        if not ctx_file.exists():
            ctx_file.write_text("# MAGIC DOC: Project Context\n\nThis document is automatically maintained by NeuroShell MagicDocs.\n", encoding="utf-8")

        return ctx_file

    def get_context_content(self) -> str:
        """Reads the current magic document."""
        ctx_file = self.find_project_context()
        try:
            return ctx_file.read_text(encoding="utf-8")
        except Exception:
            return ""

    def update_magic_doc(self, transcript: str, ui_callback: callable = None):
        """
        Post-sampling hook. Called in a background thread after an agent finishes a task.
        """
        # Ensure only one update happens at a time
        if not self.trigger_lock.acquire(blocking=False):
            return # Already updating

        try:
            current_doc = self.get_context_content()

            prompt = f"""You are MagicDocs, a background documentation maintaining agent.
Review the following active conversation transcript and determine if any permanent architectural decisions, API routes, or new project patterns were established.
If so, rewrite the Project Context document to incorporate these new facts. 
Only output the raw markdown of the entirely rewritten document. Do not wrap in markdown code blocks.

=== CURRENT PROJECT CONTEXT ===
{current_doc}

=== TRANSCRIPT ===
{transcript}
"""

            # In production, route to a fast model like Groq LLaMA 3
            updated_doc = self.llm.generate(prompt, "You are an expert technical writer and knowledge base manager.")

            if updated_doc:
                # Remove markdown fences if it incorrectly added them
                if updated_doc.startswith("```markdown") or updated_doc.startswith("```"):
                    updated_doc = "\n".join(updated_doc.split("\n")[1:-1])

                ctx_file = self.find_project_context()
                ctx_file.write_text(updated_doc.strip(), encoding="utf-8")

                if ui_callback:
                    ui_callback("MagicDocs updated project_context.md silently.")

        except Exception as e:
            if ui_callback:
                ui_callback(f"MagicDocs error: {e}")
        finally:
            self.trigger_lock.release()
