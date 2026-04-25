# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Terminal UI — Production Grade
Spinners, syntax highlighting, pagination, responsive layout, notification toasts.
"""

import os
import sys
import json
import re
from typing import Optional, Callable
from contextlib import contextmanager

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.columns import Columns
    from rich.markdown import Markdown
    from rich.syntax import Syntax
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.live import Live
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


class NeuroShellUI:
    """
    Production-grade terminal UI.

    Features:
    - Spinner/progress for long-running commands
    - Syntax highlighting (Python, JSON, YAML, SQL, etc.)
    - Responsive layout (adapts to terminal width)
    - Output pagination for long outputs
    - Notification toasts
    - Theme integration
    """

    PROVENANCE_COLORS = {
        "LLM": "#00d4ff", "CACHED": "#00ff88",
        "PATTERN": "#ff6ec7", "HISTORY": "#ffaa00",
        "NLP": "#b388ff", "DEP": "#80deea", "FALLBACK": "#666666",
    }

    LANG_MAP = {
        "py": "python", "js": "javascript", "ts": "typescript",
        "json": "json", "yaml": "yaml", "yml": "yaml",
        "sql": "sql", "sh": "bash", "bash": "bash",
        "xml": "xml", "html": "html", "css": "css",
        "toml": "toml", "ini": "ini", "diff": "diff",
        "rs": "rust", "go": "go", "java": "java",
        "cpp": "cpp", "c": "c", "rb": "ruby",
    }

    def __init__(self, theme=None):
        self.console = Console(force_terminal=True, color_system="truecolor") if HAS_RICH else None
        self.theme = theme
        self._page_size = 50  # lines per page

    @property
    def width(self) -> int:
        """Get terminal width for responsive layout."""
        if self.console:
            return self.console.width
        try:
            return os.get_terminal_size().columns
        except OSError:
            return 80

    # ═══════════════════════════════════════════════════════
    # Banner & Health
    # ═══════════════════════════════════════════════════════

    def print_banner(self):
        if not self.console:
            print("═══ NeuroShell v4 — AI Terminal ═══")
            return

        banner = Text()
        banner.append("╔══════════════════════════════════════════════════╗\n", style="bold cyan")
        banner.append("║   ", style="bold cyan")
        banner.append("🧠 NeuroShell", style="bold white")
        banner.append(" v4", style="bold magenta")
        banner.append(" — AI-Powered Terminal", style="dim white")
        banner.append("   ║\n", style="bold cyan")
        banner.append("║   ", style="bold cyan")
        banner.append("12 Layers • 41 Modules • NLP + LLM", style="dim cyan")
        banner.append("       ║\n", style="bold cyan")
        banner.append("╚══════════════════════════════════════════════════╝", style="bold cyan")
        self.console.print(banner)

    def print_health_report(self, report):
        if not self.console:
            print(report.summary())
            return

        table = Table(
            title="System Health Check", box=box.ROUNDED,
            border_style="cyan", show_header=False,
        )
        table.add_column("Status", width=3)
        table.add_column("Component", width=15)
        table.add_column("Details")

        for check in report.checks:
            icon = "✅" if check.healthy else "❌"
            style = "green" if check.healthy else "red"
            table.add_row(icon, check.component, check.message, style=style)

        self.console.print(table)

    # ═══════════════════════════════════════════════════════
    # Spinners & Progress
    # ═══════════════════════════════════════════════════════

    @contextmanager
    def spinner(self, message: str = "Processing..."):
        """Context manager for spinner during long operations."""
        if not self.console or not HAS_RICH:
            print(f"... {message}")
            yield
            return

        with Progress(
            SpinnerColumn("dots"),
            TextColumn("[bold cyan]{task.description}"),
            TimeElapsedColumn(),
            console=self.console,
            transient=True,
        ) as progress:
            task = progress.add_task(message, total=None)
            yield progress
            progress.update(task, completed=True)

    def progress_bar(self, total: int, description: str = "Progress"):
        """Create a progress bar for known-length operations."""
        if not self.console or not HAS_RICH:
            return None
        return Progress(
            SpinnerColumn(), TextColumn("[bold cyan]{task.description}"),
            BarColumn(), TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(), console=self.console,
        )

    # ═══════════════════════════════════════════════════════
    # Syntax Highlighting
    # ═══════════════════════════════════════════════════════

    def print_code(self, code: str, language: str = "python", line_numbers: bool = True):
        """Print syntax-highlighted code."""
        if not self.console or not HAS_RICH:
            print(code)
            return

        syntax = Syntax(
            code, language, theme="monokai",
            line_numbers=line_numbers,
            word_wrap=True,
        )
        self.console.print(syntax)

    def print_highlighted(self, output: str, language_hint: str = ""):
        """Auto-detect and syntax-highlight output."""
        lang = self.LANG_MAP.get(language_hint, language_hint)
        if lang and self.console and HAS_RICH:
            try:
                syntax = Syntax(output, lang, theme="monokai", word_wrap=True)
                self.console.print(syntax)
                return
            except Exception:
                pass
        # Fallback to plain output
        if self.console:
            self.console.print(output, end="")
        else:
            print(output, end="")

    # ═══════════════════════════════════════════════════════
    # Pagination
    # ═══════════════════════════════════════════════════════

    def print_paged(self, text: str, page_size: int = 0):
        """Print long output with pagination."""
        if not page_size:
            page_size = self._page_size

        lines = text.split("\n")
        if len(lines) <= page_size:
            if self.console:
                self.console.print(text, end="")
            else:
                print(text, end="")
            return

        for i in range(0, len(lines), page_size):
            chunk = "\n".join(lines[i:i + page_size])
            if self.console:
                self.console.print(chunk)
            else:
                print(chunk)

            if i + page_size < len(lines):
                remaining = len(lines) - i - page_size
                # In GUI mode sys.stdin is not a real tty — skip pagination pause
                import sys as _sys
                if not hasattr(_sys.stdin, 'isatty') or not _sys.stdin.isatty():
                    continue  # auto-print all pages without blocking
                try:
                    resp = input(f"\n--- {remaining} more lines (Enter=more, q=quit) ---\n")
                    if resp.strip().lower() == "q":
                        break
                except (EOFError, KeyboardInterrupt, OSError, ValueError):
                    break

    # ═══════════════════════════════════════════════════════
    # Command Results
    # ═══════════════════════════════════════════════════════

    def print_result(self, command: str, result, provenance=None, language_hint: str = "", parsed_output=None):
        if not self.console:
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(f"ERROR: {result.stderr}", file=sys.stderr)
            return

        # Syntax-highlighted output based on language hint
        if result.stdout:
            rendered_structured = False
            if parsed_output is not None:
                rendered_structured = self._print_structured_output(parsed_output, result.stdout)

            if not rendered_structured and language_hint:
                self.console.print("\n")
                self.print_highlighted(result.stdout, language_hint)
            elif not rendered_structured:
                # If plain text, it was already streamed during execution.
                # Just ensure there's a trailing newline.
                if not result.stdout.endswith("\n"):
                    self.console.print()

        if result.stderr and result.exit_code != 0:
            self.console.print(f"\n[red]Error:[/red] {result.stderr.strip()}")

        # Status line
        status_parts = []
        if result.duration_ms > 0:
            status_parts.append(f"[dim]{result.duration_ms:.0f}ms[/dim]")
        if result.exit_code != 0:
            status_parts.append(f"[red]exit {result.exit_code}[/red]")
        if provenance:
            color = self.PROVENANCE_COLORS.get(provenance.source.value, "white")
            status_parts.append(f"[{color}]{provenance.badge}[/{color}]")
        if status_parts:
            self.console.print(" ".join(status_parts))

    def _print_structured_output(self, parsed_output, raw_output: str) -> bool:
        """Render known structured outputs with richer views."""
        output_type = getattr(getattr(parsed_output, "output_type", None), "value", "")

        if output_type == "json":
            data = getattr(parsed_output, "structured_data", None)
            if data is None:
                return False
            pretty = json.dumps(data, indent=2, ensure_ascii=False)
            self.print_code(pretty, language="json", line_numbers=False)
            return True

        if output_type in {"table", "csv"}:
            return self._print_rich_table(raw_output)

        if output_type == "key_value":
            data = getattr(parsed_output, "structured_data", None)
            if not isinstance(data, dict) or not data:
                return False
            kv = Table(box=box.SIMPLE_HEAD, show_header=True)
            kv.add_column("Key", style="bold cyan")
            kv.add_column("Value", style="white")
            for key, value in data.items():
                kv.add_row(str(key), str(value))
            self.console.print(kv)
            return True

        if output_type == "log":
            return self._print_colored_logs(raw_output)

        return False

    def _print_rich_table(self, raw_output: str) -> bool:
        """Best-effort conversion of plain text tabular output to a Rich table."""
        lines = [line.rstrip() for line in raw_output.splitlines() if line.strip()]
        if len(lines) < 2:
            return False

        # Try pipe-delimited first
        if any("|" in line for line in lines[:3]):
            rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]
        else:
            rows = [re.split(r"\s{2,}", line.strip()) for line in lines]

        if len(rows) < 2:
            return False

        col_count = max(len(r) for r in rows)
        if col_count < 2:
            return False

        # Normalize rows to rectangular shape.
        norm_rows = [r + [""] * (col_count - len(r)) for r in rows]
        headers = norm_rows[0]
        body = norm_rows[1:]

        table = Table(box=box.SIMPLE_HEAVY, show_header=True)
        for idx, header in enumerate(headers):
            name = header if header else f"col_{idx + 1}"
            table.add_column(name, overflow="fold")

        for row in body:
            table.add_row(*[str(cell) for cell in row])

        self.console.print(table)
        return True

    def _print_colored_logs(self, raw_output: str) -> bool:
        """Render logs with severity-aware color accents."""
        lines = raw_output.splitlines()
        if not lines:
            return False

        level_styles = {
            "ERROR": "bold red",
            "FATAL": "bold red",
            "CRITICAL": "bold red",
            "WARN": "yellow",
            "WARNING": "yellow",
            "INFO": "cyan",
            "DEBUG": "dim",
            "TRACE": "dim",
        }

        for line in lines:
            upper = line.upper()
            style = "white"
            for level, level_style in level_styles.items():
                if level in upper:
                    style = level_style
                    break
            self.console.print(line, style=style)

        return True

    def print_safety(self, safety_result):
        if not self.console:
            print(f"{safety_result.badge} {safety_result.reason}")
            return
        colors = {"SAFE": "green", "CAUTION": "yellow", "DANGER": "red bold", "BLOCKED": "red bold reverse"}
        style = colors.get(safety_result.risk_level.value, "white")
        self.console.print(f"[{style}]{safety_result.badge} {safety_result.reason}[/{style}]")

    def print_translation(self, translation):
        if not self.console:
            print(f"→ {translation.command}")
            return

        prov = ""
        if translation.provenance:
            color = self.PROVENANCE_COLORS.get(translation.provenance.source.value, "white")
            prov = f" [{color}]{translation.provenance.badge}[/{color}]"

        self.console.print(
            f"  [bold cyan]→[/bold cyan] [bold white]{translation.command}[/bold white]"
            f"  [dim]({translation.confidence:.0%} confidence)[/dim]{prov}"
        )
        if translation.explanation:
            self.console.print(f"  [dim]{translation.explanation}[/dim]")

    def print_fix(self, fix_result):
        if not self.console:
            print(f"Fix: {fix_result.fix_command}")
            return
        prov = ""
        if fix_result.provenance:
            color = self.PROVENANCE_COLORS.get(fix_result.provenance.source.value, "white")
            prov = f" [{color}]{fix_result.provenance.badge}[/{color}]"
        self.console.print(f"\n  [bold green]🔧 Fix:[/bold green] [bold]{fix_result.fix_command}[/bold]{prov}")
        self.console.print(f"  [dim]{fix_result.explanation}[/dim]")

    def print_explanation(self, explain_result):
        if not self.console:
            print(explain_result.summary)
            return

        self.console.print(f"\n[bold cyan]📖 {explain_result.summary}[/bold cyan]")
        if hasattr(explain_result, 'source') and explain_result.source:
            self.console.print(f"  [dim]Source: {explain_result.source}[/dim]")
        for part in explain_result.breakdown:
            self.console.print(f"  [bold]{part.get('part', '')}[/bold] → {part.get('meaning', '')}")
        if explain_result.risks and explain_result.risks != ["none"] and explain_result.risks != ["No significant risks"]:
            self.console.print(f"  [yellow]⚠️ Risks: {', '.join(explain_result.risks)}[/yellow]")
        if hasattr(explain_result, 'examples') and explain_result.examples:
            self.console.print(f"  [dim]Examples: {', '.join(explain_result.examples)}[/dim]")
        if explain_result.related_commands:
            self.console.print(f"  [dim]Related: {', '.join(explain_result.related_commands)}[/dim]")

    def print_pipeline(self, pipeline_result):
        """Print pipeline builder result."""
        if not self.console:
            print(f"Pipeline: {pipeline_result.pipeline}")
            return

        source = "[dim](template)[/dim]" if pipeline_result.from_template else "[dim](LLM)[/dim]"
        self.console.print(f"\n[bold cyan]🔗 Pipeline {source}[/bold cyan]")
        self.console.print(f"  [bold white]{pipeline_result.pipeline}[/bold white]")
        for i, step in enumerate(pipeline_result.steps, 1):
            cmd = step.get("command", "")
            purpose = step.get("purpose", "")
            self.console.print(f"  [dim]{i}.[/dim] {cmd} — [dim]{purpose}[/dim]")
        if pipeline_result.validation_errors:
            for err in pipeline_result.validation_errors:
                self.console.print(f"  [yellow]⚠ {err}[/yellow]")

    # ═══════════════════════════════════════════════════════
    # Notifications & Messages
    # ═══════════════════════════════════════════════════════

    def toast(self, message: str, style: str = "info"):
        """Print a non-blocking notification toast."""
        styles = {"info": "cyan", "success": "green", "warning": "yellow", "error": "red"}
        icons = {"info": "ℹ", "success": "✔", "warning": "⚠", "error": "✖"}
        color = styles.get(style, "white")
        icon = icons.get(style, "•")
        if self.console:
            self.console.print(f"  [{color}]{icon} {message}[/{color}]")
        else:
            print(f"  {icon} {message}")

    def print_hint(self, hint: str):
        if self.console:
            self.console.print(f"[dim italic]{hint}[/dim italic]")
        else:
            print(hint)

    def print_error(self, message: str):
        if self.console:
            self.console.print(f"[red]❌ {message}[/red]")
        else:
            print(f"ERROR: {message}")

    def print_info(self, message: str):
        if self.console:
            self.console.print(f"[cyan]{message}[/cyan]")
        else:
            print(message)

    def print_success(self, message: str):
        if self.console:
            self.console.print(f"[green]✔ {message}[/green]")
        else:
            print(f"OK: {message}")

    def confirm(self, message: str) -> bool:
        """Ask for Y/n confirmation. Auto-approves in GUI/non-tty mode."""
        import sys as _sys
        # GUI mode: stdin is not a real tty — auto-confirm (user already pressed Run)
        if not hasattr(_sys.stdin, 'isatty') or not _sys.stdin.isatty():
            return True  # silent auto-approve — no print to avoid polluting terminal
        if self.console:
            self.console.print(f"[yellow]{message}[/yellow] ", end="")
        else:
            print(f"{message} ", end="")
        try:
            response = input("[Y/n] ").strip().lower()
        except (EOFError, OSError, ValueError):
            return True  # safe default — auto-approve
        return response in ("y", "yes", "")

    def get_prompt(self, cwd: str, git_branch: str = "", env_name: str = "", network: bool = True) -> str:
        """Build rich prompt with status indicators."""
        parts = []

        # Virtual env indicator
        if env_name:
            parts.append(f"({env_name})")

        # Shorten path
        home = str(os.path.expanduser("~"))
        display_cwd = cwd.replace(home, "~")
        parts.append(display_cwd)

        if git_branch:
            parts.append(f"({git_branch})")

        # Network indicator
        if not network:
            parts.append("[offline]")

        return f"🧠 {' '.join(parts)} ❯ "
