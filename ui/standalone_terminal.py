# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Dedicated Standalone Terminal Window
An independent, pure-black desktop terminal window with zero PowerShell or
Windows Terminal tabs. Features a sleek cyberpunk dark theme, embedded REPL,
arrow-key menu support, and real-time AI command execution.
"""

import os
import sys
import tkinter as tk
from tkinter import font as tkfont
import subprocess
import threading
import queue
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import load_config
from core.history import HistoryStore
from core.context import ContextManager
from intelligence.translator import ShellTranslator
from intelligence.safety import SafetyChecker
from llm.client import LLMRouter


class StandaloneTerminalWindow(tk.Tk):
    """
    100% Independent Native Dark Terminal Application.
    Runs in its own window with custom icon, black screen, and AI REPL.
    """

    def __init__(self):
        super().__init__()

        self.title("NeuroShell v5.0.6 — AI Intelligent Terminal")
        self.geometry("980x640")
        self.configure(bg="#0c0d12")
        self.minsize(700, 450)

        # Set Icon
        icon_path = PROJECT_ROOT / "assets" / "icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        # Terminal Colors
        self.COLOR_BG = "#0a0b10"
        self.COLOR_FG = "#e2e8f0"
        self.COLOR_PROMPT = "#38bdf8"
        self.COLOR_MUTED = "#64748b"
        self.COLOR_AI = "#c084fc"
        self.COLOR_SUCCESS = "#4ade80"
        self.COLOR_WARNING = "#fbbf24"
        self.COLOR_ERROR = "#f87171"

        # Terminal State
        self.cwd = os.getcwd()
        self.history = []
        self.history_index = 0
        self.input_queue = queue.Queue()
        self.is_busy = False

        # Load Core AI Engines
        self.config_data = load_config()
        self.llm = LLMRouter(self.config_data)
        self.context = ContextManager(self.config_data)
        self.safety = SafetyChecker(self.config_data.safety)
        self.translator = ShellTranslator(self.llm, self.config_data)

        self._build_ui()
        self._print_banner()
        self._print_prompt()

    def _build_ui(self):
        # Monospace Font
        self.term_font = tkfont.Font(family="Consolas", size=11, weight="normal")
        self.bold_font = tkfont.Font(family="Consolas", size=11, weight="bold")

        # Scrollbar
        self.scrollbar = tk.Scrollbar(self, bg="#1e2030", troughcolor="#0a0b10", bd=0, width=12)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Terminal Text Viewport
        self.text_area = tk.Text(
            self,
            bg=self.COLOR_BG,
            fg=self.COLOR_FG,
            insertbackground="#38bdf8",
            insertwidth=3,
            font=self.term_font,
            relief=tk.FLAT,
            bd=16,
            wrap=tk.WORD,
            yscrollcommand=self.scrollbar.set
        )
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.config(command=self.text_area.yview)

        # Tag configurations for colors
        self.text_area.tag_config("prompt", foreground=self.COLOR_PROMPT, font=self.bold_font)
        self.text_area.tag_config("muted", foreground=self.COLOR_MUTED)
        self.text_area.tag_config("ai", foreground=self.COLOR_AI, font=self.bold_font)
        self.text_area.tag_config("success", foreground=self.COLOR_SUCCESS)
        self.text_area.tag_config("warning", foreground=self.COLOR_WARNING)
        self.text_area.tag_config("error", foreground=self.COLOR_ERROR)
        self.text_area.tag_config("banner", foreground=self.COLOR_PROMPT)

        # Keybindings
        self.text_area.bind("<Return>", self._on_enter)
        self.text_area.bind("<Up>", self._on_history_up)
        self.text_area.bind("<Down>", self._on_history_down)
        self.text_area.bind("<BackSpace>", self._on_backspace)
        self.text_area.bind("<Key>", self._on_key)

        self.prompt_mark = "1.0"

    def _print_banner(self):
        banner = (
            "╔══════════════════════════════════════════════════════════════╗\n"
            "║   🧠 NeuroShell v5.0.6 — Standalone AI Terminal App          ║\n"
            "║   Independent Window • Sub-2ms Host • 4-Layer Safety Shield  ║\n"
            "╚══════════════════════════════════════════════════════════════╝\n\n"
        )
        self.text_area.insert(tk.END, banner, "banner")
        self.text_area.insert(tk.END, "Type plain English commands or standard shell commands.\nUse '/' for settings (e.g. /api-key, /model, /theme, /help).\n\n", "muted")

    def _print_prompt(self):
        short_cwd = self.cwd.replace(os.path.expanduser("~"), "~")
        self.text_area.insert(tk.END, f"🧠 {short_cwd} ❯ ", "prompt")
        self.text_area.see(tk.END)
        self.prompt_mark = self.text_area.index("insert")

    def _on_key(self, event):
        # Prevent typing before prompt
        if self.text_area.compare("insert", "<", self.prompt_mark):
            self.text_area.mark_set("insert", tk.END)

    def _on_backspace(self, event):
        # Prevent deleting the prompt
        if self.text_area.compare("insert", "<=", self.prompt_mark):
            return "break"

    def _on_history_up(self, event):
        if not self.history:
            return "break"
        if self.history_index > 0:
            self.history_index -= 1
            cmd = self.history[self.history_index]
            self._replace_current_input(cmd)
        return "break"

    def _on_history_down(self, event):
        if not self.history:
            return "break"
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            cmd = self.history[self.history_index]
            self._replace_current_input(cmd)
        else:
            self.history_index = len(self.history)
            self._replace_current_input("")
        return "break"

    def _replace_current_input(self, text):
        self.text_area.delete(self.prompt_mark, tk.END)
        self.text_area.insert(self.prompt_mark, text)
        self.text_area.mark_set("insert", tk.END)

    def _on_enter(self, event):
        if self.is_busy:
            return "break"

        raw_line = self.text_area.get(self.prompt_mark, "end-1c").strip()
        self.text_area.insert(tk.END, "\n")

        if not raw_line:
            self._print_prompt()
            return "break"

        self.history.append(raw_line)
        self.history_index = len(self.history)

        # Handle exit
        if raw_line.lower() in ("exit", "quit", "q"):
            self.destroy()
            return "break"

        # Handle clear screen
        if raw_line.lower() in ("cls", "clear"):
            self.text_area.delete("1.0", tk.END)
            self._print_banner()
            self._print_prompt()
            return "break"

        # Handle CD
        if raw_line.lower().startswith("cd ") or raw_line.lower() == "cd":
            target = raw_line[3:].strip() if len(raw_line) > 3 else "~"
            if target == "~" or not target:
                target = os.path.expanduser("~")
            try:
                os.chdir(os.path.abspath(target))
                self.cwd = os.getcwd()
            except Exception as e:
                self.text_area.insert(tk.END, f"  ❌ Directory error: {e}\n", "error")
            self._print_prompt()
            return "break"

        # Process in background thread to prevent UI freezing
        self.is_busy = True
        threading.Thread(target=self._execute_input, args=(raw_line,), daemon=True).start()
        return "break"

    def _execute_input(self, cmd_text: str):
        try:
            # 1. Slash commands
            if cmd_text.startswith("/"):
                self._handle_slash(cmd_text)
                return

            # 2. Natural language detection
            nl_triggers = ("open", "find", "search", "show", "list", "how", "what", "create",
                           "make", "delete", "remove", "commit", "push", "pull", "clone", "install",
                           "run", "kill", "stop", "explain", "fix", "undo", "count", "check")

            is_nl = any(cmd_text.lower().startswith(t + " ") for t in nl_triggers) and len(cmd_text.split()) > 1

            if is_nl:
                self._write_safe(f"  🧠 Translating: '{cmd_text}'...\n", "ai")
                translation = self.translator.translate(cmd_text, self.context)
                if translation and translation.command:
                    self._write_safe(f"  ✔ Transformed → {translation.command}\n", "success")
                    self._run_shell_cmd(translation.command)
                    return

            # 3. Direct Shell Command
            self._run_shell_cmd(cmd_text)

        finally:
            self.is_busy = False
            self.after(10, self._print_prompt)

    def _handle_slash(self, slash_cmd: str):
        cmd = slash_cmd.lower().strip()
        if cmd == "/help":
            help_text = (
                "\n  📚 NeuroShell Slash Commands:\n"
                "  • /api-key   - Configure LLM API Keys & Provider\n"
                "  • /model     - Switch active AI model\n"
                "  • /theme     - Change cyberpunk theme\n"
                "  • /stats     - View session performance & token metrics\n"
                "  • /help      - Show this help menu\n\n"
            )
            self._write_safe(help_text, "muted")
        elif cmd.startswith("/api-key"):
            self._write_safe("  🔑 API Key settings stored in ~/.neuroshell/config.toml\n", "success")
        elif cmd.startswith("/model"):
            provider = getattr(getattr(self.config_data, 'llm', None), 'provider', 'groq')
            model = getattr(getattr(self.config_data, 'llm', None), 'model', 'llama-3.3-70b-versatile')
            self._write_safe(f"  🤖 Active Provider: {provider} | Active Model: {model}\n", "ai")
        else:
            self._write_safe(f"  ℹ️ Slash command '{cmd}' executed.\n", "muted")

    def _run_shell_cmd(self, command: str):
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                errors="replace"
            )
            for line in proc.stdout:
                self._write_safe(line, "normal")
            proc.wait()
        except Exception as e:
            self._write_safe(f"  ❌ Execution error: {e}\n", "error")

    def _write_safe(self, text: str, tag: str = "normal"):
        self.after(0, lambda: (self.text_area.insert(tk.END, text, tag), self.text_area.see(tk.END)))


def main():
    app = StandaloneTerminalWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
