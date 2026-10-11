# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Adaptive Table & Layout Presentation Engine for NeuroShell.
Dynamically calculates terminal widths, allocates proportional column budgets,
applies Unicode box-drawing borders, color badges, and clean ellipsis truncation
so output never wraps messily across console lines.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any, Sequence


# ANSI Color Codes
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"
C_WHITE = "\033[37m"
C_MUTED = "\033[90m"


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences to compute visual character length."""
    return re.sub(r"\x1b\[[0-9;]*[mK]", "", text)


def visual_len(text: str) -> int:
    """Compute visual width of text in terminal."""
    return len(strip_ansi(text))


@dataclass
class ColumnSpec:
    """Column definition for adaptive table."""
    name: str
    min_width: int = 4
    max_width: int = 60
    align: str = "left"  # "left", "right", "center"
    is_flex: bool = False
    color: str = ""


class AdaptiveTableFormatter:
    """
    Renders beautifully aligned, terminal-responsive Unicode tables.
    Guarantees zero ugly line-wrapping and clean truncations.
    """

    # Box-drawing styles
    STYLES = {
        "rounded": {
            "top_left": "╭", "top_mid": "┬", "top_right": "╮",
            "mid_left": "├", "mid_mid": "┼", "mid_right": "┤",
            "bot_left": "╰", "bot_mid": "┴", "bot_right": "╯",
            "horiz": "─", "vert": "│",
        },
        "ascii": {
            "top_left": "+", "top_mid": "+", "top_right": "+",
            "mid_left": "+", "mid_mid": "+", "mid_right": "+",
            "bot_left": "+", "bot_mid": "+", "bot_right": "+",
            "horiz": "-", "vert": "|",
        },
        "double": {
            "top_left": "╔", "top_mid": "╦", "top_right": "╗",
            "mid_left": "╠", "mid_mid": "╬", "mid_right": "╣",
            "bot_left": "╚", "bot_mid": "╩", "bot_right": "╝",
            "horiz": "═", "vert": "║",
        },
    }

    def __init__(self, style: str = "rounded", max_width: int | None = None):
        self.style_name = style if style in self.STYLES else "rounded"
        self.box = self.STYLES[self.style_name]
        self._explicit_max_width = max_width

    def get_terminal_width(self) -> int:
        """Dynamically detect terminal width with safe fallbacks."""
        if self._explicit_max_width:
            return self._explicit_max_width
        try:
            cols = shutil.get_terminal_size(fallback=(100, 24)).columns
            return max(40, cols - 2)  # 2 margin spaces
        except Exception:
            return 100

    def render_table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[Any]],
        title: str | None = None,
        column_specs: Sequence[ColumnSpec] | None = None,
    ) -> str:
        """
        Render headers and rows into an aligned, width-budgeted table.
        """
        if not headers and not rows:
            return ""

        term_width = self.get_terminal_width()
        num_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
        if num_cols == 0:
            return ""

        # Normalize string cells
        str_headers = [str(h) for h in headers]
        str_rows = [[str(cell) for cell in row] for row in rows]

        # Calculate natural content widths
        col_max_content = [visual_len(h) for h in str_headers]
        if not col_max_content:
            col_max_content = [0] * num_cols

        for row in str_rows:
            for i in range(min(num_cols, len(row))):
                col_max_content[i] = max(col_max_content[i], visual_len(row[i]))

        # Calculate available budget for cell contents:
        # border overhead = 1 (left) + 1 (right) + (num_cols - 1) (inner borders) + num_cols * 2 (paddings)
        overhead = 1 + 1 + (num_cols - 1) + (num_cols * 2)
        available_content_width = max(num_cols * 4, term_width - overhead)

        # Allocate column widths based on specs or proportional budgeting
        allocated_widths = self._budget_columns(
            num_cols=num_cols,
            col_max_content=col_max_content,
            available_width=available_content_width,
            column_specs=column_specs,
        )

        b = self.box
        out = []

        # Optional Title Banner
        if title:
            out.append(f"  {C_BOLD}{C_CYAN}⌬ {title}{C_RESET}")

        # Top border
        top_line = (
            "  " + C_CYAN + b["top_left"]
            + b["top_mid"].join(b["horiz"] * (w + 2) for w in allocated_widths)
            + b["top_right"] + C_RESET
        )
        out.append(top_line)

        # Header row
        if str_headers:
            header_cells = []
            for i, h in enumerate(str_headers):
                w = allocated_widths[i]
                padded = self._align_and_truncate(h, w, align="center" if i == 0 else "left")
                header_cells.append(f" {C_BOLD}{C_WHITE}{padded}{C_RESET} ")
            header_line = "  " + C_CYAN + b["vert"] + (C_CYAN + b["vert"] + C_RESET).join(header_cells) + C_CYAN + b["vert"] + C_RESET
            out.append(header_line)

            # Header separator
            mid_line = (
                "  " + C_CYAN + b["mid_left"]
                + b["mid_mid"].join(b["horiz"] * (w + 2) for w in allocated_widths)
                + b["mid_right"] + C_RESET
            )
            out.append(mid_line)

        # Data rows
        for row in str_rows:
            row_cells = []
            for i in range(num_cols):
                val = row[i] if i < len(row) else ""
                w = allocated_widths[i]
                align = "center" if (i == 0 and len(val) <= 4) else "left"
                
                # Check for smart color badge
                styled_val = self._colorize_cell(val, i)
                cell_plain = strip_ansi(val)
                padded_plain = self._align_and_truncate(cell_plain, w, align=align)
                
                # If colorized, apply color with proper padding
                if styled_val != cell_plain and visual_len(styled_val) == visual_len(cell_plain):
                    # Replace stripped value in padding
                    padded = padded_plain.replace(cell_plain, styled_val, 1)
                elif styled_val != cell_plain:
                    # Truncated styled
                    padded = self._style_truncated_cell(cell_plain, styled_val, w, align)
                else:
                    padded = padded_plain

                row_cells.append(f" {padded} ")

            row_line = "  " + C_CYAN + b["vert"] + (C_CYAN + b["vert"] + C_RESET).join(row_cells) + C_CYAN + b["vert"] + C_RESET
            out.append(row_line)

        # Bottom border
        bot_line = (
            "  " + C_CYAN + b["bot_left"]
            + b["bot_mid"].join(b["horiz"] * (w + 2) for w in allocated_widths)
            + b["bot_right"] + C_RESET
        )
        out.append(bot_line)

        return "\n".join(out)

    def _budget_columns(
        self,
        num_cols: int,
        col_max_content: list[int],
        available_width: int,
        column_specs: Sequence[ColumnSpec] | None = None,
    ) -> list[int]:
        """Proportionally budget column widths to guarantee zero wrapping."""
        widths = [max(4, c) for c in col_max_content]

        total_desired = sum(widths)
        if total_desired <= available_width:
            return widths

        # Smart priority budgeting:
        # Give essential identity columns (ID, Name/Repo, Status, Date) their required widths,
        # and let the long narrative column (Description, Message, Details) absorb the rest.
        allocated = list(widths)
        fixed_sum = 0
        flex_indices = []

        # Identify flex columns (columns that can shrink, typically longer text > 16)
        # and fixed/identity columns (shorter labels <= 16)
        for i, w in enumerate(widths):
            if w <= 16:
                allocated[i] = w
                fixed_sum += w
            else:
                flex_indices.append(i)

        if not flex_indices:
            flex_indices = list(range(num_cols))
            fixed_sum = 0

        remaining_budget = available_width - fixed_sum
        if remaining_budget >= len(flex_indices) * 6:
            flex_desired = sum(widths[i] for i in flex_indices) or 1
            for idx in flex_indices:
                ratio = widths[idx] / flex_desired
                allocated[idx] = max(6, int(remaining_budget * ratio))
        else:
            for i in range(num_cols):
                allocated[i] = 4
            leftover = max(0, available_width - (num_cols * 4))
            if leftover > 0:
                largest_idx = widths.index(max(widths))
                allocated[largest_idx] += leftover

        return allocated

    def _align_and_truncate(self, text: str, width: int, align: str = "left") -> str:
        """Truncate with ellipsis if text exceeds width, then align."""
        vlen = visual_len(text)
        if vlen > width:
            if width <= 3:
                return text[:width]
            return text[: width - 3] + "..."

        pad_needed = width - vlen
        if align == "right":
            return (" " * pad_needed) + text
        elif align == "center":
            left_pad = pad_needed // 2
            right_pad = pad_needed - left_pad
            return (" " * left_pad) + text + (" " * right_pad)
        else:
            return text + (" " * pad_needed)

    def _colorize_cell(self, text: str, col_idx: int) -> str:
        """Apply contextual high-contrast colors and badges."""
        stripped = text.strip()
        lower = stripped.lower()

        # Visibilities & permissions
        if lower == "public":
            return f"{C_GREEN}public{C_RESET}"
        elif lower == "private":
            return f"{C_MAGENTA}private{C_RESET}"
        elif lower in ("internal", "protected"):
            return f"{C_YELLOW}{stripped}{C_RESET}"

        # Status indicators
        if lower in ("success", "active", "running", "online", "true", "yes", "ok"):
            return f"{C_GREEN}{stripped}{C_RESET}"
        elif lower in ("failed", "error", "stopped", "offline", "false", "no", "dead"):
            return f"{C_RED}{stripped}{C_RESET}"
        elif lower in ("pending", "warning", "paused", "waiting"):
            return f"{C_YELLOW}{stripped}{C_RESET}"

        # Dates / timestamps
        if re.match(r"^\d{4}-\d{2}-\d{2}(?:T|\s)?.*$", stripped):
            date_part = stripped.split("T")[0] if "T" in stripped else stripped[:10]
            return f"{C_MUTED}{date_part}{C_RESET}"

        # Index column
        if col_idx == 0 and stripped.isdigit():
            return f"{C_MUTED}{stripped}{C_RESET}"

        # Primary name column (Repo / App / File name)
        if col_idx == 1:
            return f"{C_BOLD}{C_WHITE}{text}{C_RESET}"

        return text

    def _style_truncated_cell(self, plain: str, styled: str, width: int, align: str) -> str:
        truncated = self._align_and_truncate(plain, width, align=align)
        # Apply style to truncated content
        if C_GREEN in styled:
            return f"{C_GREEN}{truncated}{C_RESET}"
        elif C_MAGENTA in styled:
            return f"{C_MAGENTA}{truncated}{C_RESET}"
        elif C_RED in styled:
            return f"{C_RED}{truncated}{C_RESET}"
        elif C_YELLOW in styled:
            return f"{C_YELLOW}{truncated}{C_RESET}"
        elif C_MUTED in styled:
            return f"{C_MUTED}{truncated}{C_RESET}"
        elif C_BOLD in styled:
            return f"{C_BOLD}{C_WHITE}{truncated}{C_RESET}"
        return truncated

    def format_tsv(self, tsv_data: str, headers: Sequence[str] | None = None, title: str | None = None) -> str:
        """Parse raw TSV string (e.g. from gh repo list, docker ps, etc.) into an aligned table."""
        lines = [line.strip() for line in tsv_data.strip().splitlines() if line.strip()]
        if not lines:
            return f"  {C_MUTED}No items found.{C_RESET}"

        rows = []
        for line in lines:
            parts = [p.strip() for p in line.split("\t")]
            rows.append(parts)

        # Detect headers or inject standard headers
        if headers is None:
            if len(rows[0]) == 4:
                # Standard GitHub repo format: name, desc, visibility, updatedAt
                headers = ["#", "REPOSITORY", "VISIBILITY", "UPDATED", "DESCRIPTION"]
                # Reorganize rows with index and standard order
                formatted_rows = []
                for idx, r in enumerate(rows):
                    name = r[0] if len(r) > 0 else ""
                    # Sometimes desc is empty: name \t visibility \t date
                    if len(r) == 3:
                        desc = "-"
                        vis = r[1]
                        up = r[2][:10] if len(r[2]) >= 10 else r[2]
                    elif len(r) >= 4:
                        desc = r[1]
                        vis = r[2]
                        up = r[3][:10] if len(r[3]) >= 10 else r[3]
                    else:
                        desc = "-"
                        vis = "public"
                        up = "-"
                    formatted_rows.append([str(idx + 1), name, vis, up, desc])
                return self.render_table(headers=headers, rows=formatted_rows, title=title)
            else:
                headers = [f"COL {i + 1}" for i in range(len(rows[0]))]

        # Add index if requested
        formatted_rows = []
        for idx, r in enumerate(rows):
            formatted_rows.append([str(idx + 1)] + r)
        final_headers = ["#"] + list(headers)

        return self.render_table(headers=final_headers, rows=formatted_rows, title=title)



class AutoArranger:
    """
    Intelligent Output Auto-Arranger.
    Inspects arbitrary terminal output, detects its underlying structure,
    and returns a well-arranged, beautifully aligned layout.
    Supported shapes:
    1. JSON (array of objects -> Adaptive Table; single object -> Key-Value Card / syntax tree)
    2. CSV (Comma-separated values with uniform columns -> Adaptive Table)
    3. TSV (Tab-separated values -> Adaptive Table)
    4. Markdown Table (| Col 1 | Col 2 | -> Adaptive Table)
    5. Key-Value Blocks ("Key: Value" or "Key = Value" -> 2-column Property Card)
    6. Space-aligned Columnar (detects multiple spaces separating columns)
    7. Plain text (indented with left margin, clean padding)
    """

    def __init__(self, formatter: AdaptiveTableFormatter | None = None):
        self.formatter = formatter or AdaptiveTableFormatter()

    def arrange(self, raw_text: str, title: str | None = None) -> str:
        text = raw_text.strip()
        if not text:
            return ""

        # 1. Try JSON detection
        if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
            try:
                data = json.loads(text)
                if isinstance(data, list) and len(data) > 0 and all(isinstance(item, dict) for item in data):
                    # Table from JSON array of objects
                    headers = list({k: True for item in data for k in item.keys()}.keys())
                    rows = [[str(item.get(h, "")) for h in headers] for item in data]
                    return self.formatter.render_table(headers=headers, rows=rows, title=title or "JSON Data Table")
                elif isinstance(data, dict):
                    # Key-Value Property Card
                    headers = ["PROPERTY", "VALUE"]
                    rows = [[str(k), json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)] for k, v in data.items()]
                    return self.formatter.render_table(headers=headers, rows=rows, title=title or "Object Properties")
                else:
                    return self.format_json_syntax(text)
            except Exception:
                pass

        # 2. Try Markdown Table detection
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) >= 2 and all(l.startswith("|") and l.endswith("|") for l in lines[:2]):
            try:
                header_line = lines[0]
                headers = [c.strip() for c in header_line.strip("|").split("|")]
                start_row = 1
                if len(lines) > 1 and re.match(r"^\|(?:\s*:?-+:?\s*\|)+$", lines[1]):
                    start_row = 2
                rows = []
                for l in lines[start_row:]:
                    if l.startswith("|") and l.endswith("|"):
                        rows.append([c.strip() for c in l.strip("|").split("|")])
                if headers and rows:
                    return self.formatter.render_table(headers=headers, rows=rows, title=title or "Markdown Table")
            except Exception:
                pass

        # 3. Try TSV detection
        tsv_lines = [l for l in lines if "\t" in l]
        if len(tsv_lines) >= 2 and len(tsv_lines) >= len(lines) * 0.7:
            try:
                return self.formatter.format_tsv(text, title=title)
            except Exception:
                pass

        # 4. Try CSV detection (uniform commas >= 1 per line, consistent column count)
        if len(lines) >= 2:
            try:
                reader = csv.reader(io.StringIO(text))
                parsed_rows = list(reader)
                if len(parsed_rows) >= 2 and len(parsed_rows[0]) >= 2:
                    col_count = len(parsed_rows[0])
                    if all(len(r) == col_count for r in parsed_rows[:15]):
                        headers = parsed_rows[0]
                        rows = parsed_rows[1:]
                        return self.formatter.render_table(headers=headers, rows=rows, title=title or "CSV Dataset")
            except Exception:
                pass

        # 5. Try Key-Value blocks (lines with "Key: Value" or "Key = Value")
        kv_pairs = []
        is_all_kv = True
        for line in lines[:25]:
            m = re.match(r"^([A-Za-z0-9_\-\.\s]{1,32})[:=]\s*(.+)$", line)
            if m:
                kv_pairs.append([m.group(1).strip(), m.group(2).strip()])
            else:
                is_all_kv = False
                break
        if is_all_kv and len(kv_pairs) >= 3:
            return self.formatter.render_table(headers=["PROPERTY", "VALUE"], rows=kv_pairs, title=title or "System Properties")

        # 6. Try multi-column space alignment (e.g., docker ps, ps aux, kubectl)
        if len(lines) >= 2:
            split_rows = [re.split(r"\s{2,}", l) for l in lines]
            if len(split_rows[0]) >= 2 and all(len(r) >= 2 for r in split_rows[:8]):
                headers = split_rows[0]
                rows = split_rows[1:]
                return self.formatter.render_table(headers=headers, rows=rows, title=title)

        # Fallback: Clean left-padded text
        return "\n".join("  " + l for l in lines)

    def format_json_syntax(self, json_str: str) -> str:
        """Pretty-prints and colorizes JSON with high-contrast keys and values."""
        try:
            parsed = json.loads(json_str) if isinstance(json_str, str) else json_str
            formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
            colored_lines = []
            for line in formatted.splitlines():
                # Colorize keys
                line = re.sub(r'(".*?")(?=\s*:)', f"{C_CYAN}\\1{C_RESET}", line)
                # Colorize strings
                line = re.sub(r'(:\s*)(".*?")', f"\\1{C_GREEN}\\2{C_RESET}", line)
                # Colorize numbers
                line = re.sub(r'(:\s*)(\b\d+\.?\d*\b)', f"\\1{C_YELLOW}\\2{C_RESET}", line)
                # Colorize booleans / null
                line = re.sub(r'(:\s*)(\btrue\b|\bfalse\b|\bnull\b)', f"\\1{C_MAGENTA}\\2{C_RESET}", line)
                colored_lines.append("  " + line)
            return "\n".join(colored_lines)
        except Exception:
            return json_str


def render_execution_frame(command: str, output: str, exit_code: int = 0, duration_s: float = 0.0) -> str:
    """Wraps output in a clean, modern terminal frame with timing and status badges."""
    cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    frame_width = max(40, min(100, cols - 4))

    # Header
    cmd_label = f" ⌬ {command} "
    header_bar = "─" * max(2, frame_width - len(cmd_label) - 2)
    header = f"  {C_CYAN}╭{C_BOLD}{C_WHITE}{cmd_label}{C_CYAN}{header_bar}╮{C_RESET}"

    # Body
    body_lines = [f"  {C_CYAN}│{C_RESET} {line}" for line in output.splitlines()]

    # Footer with badge
    status_badge = f"{C_GREEN}✔ Exit 0{C_RESET}" if exit_code == 0 else f"{C_RED}❌ Exit {exit_code}{C_RESET}"
    timing = f"{duration_s:.2f}s" if duration_s >= 1.0 else f"{int(duration_s * 1000)}ms"
    footer_text = f" {status_badge} • {C_MUTED}{timing}{C_RESET} "
    vis_footer_len = visual_len(strip_ansi(footer_text))
    footer_bar = "─" * max(2, frame_width - vis_footer_len - 2)
    footer = f"  {C_CYAN}╰{footer_text}{C_CYAN}{footer_bar}╯{C_RESET}"

    return header + "\n" + "\n".join(body_lines) + "\n" + footer


# CLI Entrypoint: python -m ui.table_formatter [--auto | --table | --json] [input_file_or_string]
if __name__ == "__main__":
    arranger = AutoArranger()
    input_text = ""

    if len(sys.argv) > 1:
        flag = sys.argv[1]
        if flag in ("--json", "-j"):
            arg = sys.argv[2] if len(sys.argv) > 2 else "-"
            if arg == "-":
                input_text = sys.stdin.read()
            elif os.path.isfile(arg):
                with open(arg, "r", encoding="utf-8", errors="replace") as f:
                    input_text = f.read()
            else:
                input_text = arg
            print(arranger.format_json_syntax(input_text))
            sys.exit(0)
        elif flag in ("--auto", "-a", "--table", "-t"):
            arg = sys.argv[2] if len(sys.argv) > 2 else "-"
            if arg == "-":
                input_text = sys.stdin.read()
            elif os.path.isfile(arg):
                with open(arg, "r", encoding="utf-8", errors="replace") as f:
                    input_text = f.read()
            else:
                input_text = arg
            print(arranger.arrange(input_text))
            sys.exit(0)
        else:
            arg = sys.argv[1]
            if arg == "-":
                input_text = sys.stdin.read()
            elif os.path.isfile(arg):
                with open(arg, "r", encoding="utf-8", errors="replace") as f:
                    input_text = f.read()
            else:
                input_text = arg
            print(arranger.arrange(input_text))
            sys.exit(0)

    # Built-in demonstration if run with zero arguments
    sample_tsv = (
        "abneeshsingh21/neuroshell\tProduction NeuroShell AI Terminal\tpublic\t2026-10-11T18:20:44Z\n"
        "abneeshsingh21/konvert\tDeterministic English-to-Code Compiler — Write English, Ship Code\tpublic\t2026-10-06T00:15:14Z\n"
        "abneeshsingh21/syting\tNext-generation dating application backend\tprivate\t2026-10-01T15:42:36Z\n"
    )
    print(arranger.arrange(sample_tsv, title="GitHub Repositories"))


