# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Enhanced TUI Dashboard
Rich live display with panels for recent commands, system metrics,
error rate, and context-aware suggestions.
"""

import os
import time
from typing import Optional

try:
    import psutil
except ImportError:
    psutil = None

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


class Dashboard:
    """Interactive TUI dashboard for NeuroShell."""

    def __init__(self, history_store=None, metrics_tracker=None,
                 project_detector=None, config=None):
        self.history = history_store
        self.metrics = metrics_tracker
        self.project_detector = project_detector
        self.config = config
        self.console = Console() if HAS_RICH else None

    def show(self):
        """Display the full dashboard."""
        if not HAS_RICH:
            self._show_plain()
            return

        self.console.clear()
        self.console.print()

        # Header
        self.console.print(Panel(
            "[bold cyan]🧠 NeuroShell Dashboard[/bold cyan]",
            style="cyan",
        ))

        # Create panels
        panels = []

        # System metrics panel
        sys_table = self._system_metrics_panel()
        panels.append(Panel(sys_table, title="⚡ System", border_style="green", width=38))

        # Recent commands panel
        cmd_table = self._recent_commands_panel()
        panels.append(Panel(cmd_table, title="📜 Recent Commands", border_style="blue", width=42))

        self.console.print(Columns(panels, padding=(0, 1)))
        self.console.print()

        # Session stats panel
        stats_table = self._session_stats_panel()
        self.console.print(Panel(stats_table, title="📊 Session Stats", border_style="yellow"))

        # Project info panel
        if self.project_detector:
            project_info = self.project_detector.get_startup_message()
            if project_info:
                self.console.print(Panel(project_info, title="📁 Project", border_style="magenta"))

        self.console.print()
        self.console.print("[dim]Press Enter to return to shell...[/dim]")

    def _system_metrics_panel(self) -> str:
        """Build system metrics content."""
        lines = []

        if psutil:
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(os.getcwd())

            lines.append(f"  CPU:  {'█' * int(cpu / 5)}{'░' * (20 - int(cpu / 5))} {cpu:.0f}%")
            mem_pct = mem.percent
            lines.append(f"  RAM:  {'█' * int(mem_pct / 5)}{'░' * (20 - int(mem_pct / 5))} {mem_pct:.0f}%")
            lines.append(f"  Disk: {disk.free / (1024**3):.1f} GB free")
            lines.append(f"  Procs: {len(psutil.pids())} running")
        else:
            lines.append("  (psutil not available)")

        return "\n".join(lines)

    def _recent_commands_panel(self) -> str:
        """Build recent commands content."""
        lines = []

        if self.history:
            try:
                recent = self.history.get_recent(8)
                for r in recent:
                    icon = "✅" if r.exit_code == 0 else "❌"
                    cmd_short = r.command[:35] + "..." if len(r.command) > 35 else r.command
                    dur = f"{r.duration_ms:.0f}ms" if r.duration_ms else ""
                    lines.append(f"  {icon} {cmd_short} {dur}")
            except Exception:
                lines.append("  No commands yet")
        else:
            lines.append("  No history available")

        return "\n".join(lines) if lines else "  No commands yet"

    def _session_stats_panel(self) -> str:
        """Build session statistics content."""
        lines = []

        if self.metrics:
            try:
                stats = self.metrics.summary() if hasattr(self.metrics, 'summary') else ""
                if isinstance(stats, str):
                    lines.append(stats)
                elif isinstance(stats, dict):
                    for key, value in stats.items():
                        lines.append(f"  {key}: {value}")
            except Exception:
                lines.append("  No metrics available")
        else:
            lines.append("  No metrics tracker available")

        return "\n".join(lines) if lines else "  No data yet"

    def _show_plain(self):
        """Fallback plain-text dashboard."""
        print("\n" + "=" * 60)
        print("  🧠 NeuroShell Dashboard")
        print("=" * 60)

        if psutil:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory()
            print(f"  CPU: {cpu}% | RAM: {mem.percent}% | Free: {mem.available / (1024**3):.1f} GB")

        if self.history:
            try:
                recent = self.history.get_recent(5)
                print("\n  Recent Commands:")
                for r in recent:
                    icon = "✓" if r.exit_code == 0 else "✗"
                    print(f"    {icon} {r.command[:50]}")
            except Exception:
                pass

        print("\n" + "=" * 60)
        print("  Press Enter to return...")
