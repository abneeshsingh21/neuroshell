# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Terminal Markdown & Document Presentation Engine for NeuroShell.
Transforms raw Markdown, GitHub READMEs, and HTML documentation into
beautifully styled, executive-grade terminal documents with Unicode frames,
pill badges, arranged tables, and clean word-wrapped prose.
"""

from __future__ import annotations

import html
import os
import re
import shutil
import sys
from typing import Sequence

from ui.table_formatter import (
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_MAGENTA,
    C_MUTED,
    C_RED,
    C_RESET,
    C_WHITE,
    C_YELLOW,
    AdaptiveTableFormatter,
    strip_ansi,
    visual_len,
)

# Color accents for document components
C_CARD_BORDER = "\033[38;5;69m"
C_TAG_BG = "\033[48;5;236m\033[38;5;153m"
C_HEADER_ACCENT = "\033[38;5;75m"
C_SUBHEADER_ACCENT = "\033[38;5;141m"
C_LINK_COLOR = "\033[38;5;117m"
C_QUOTE_BAR = "\033[38;5;213m"


class TerminalMarkdownRenderer:
    """
    Parses and styles raw Markdown + HTML into high-contrast,
    perfectly arranged terminal layouts.
    """

    def __init__(self, target_width: int | None = None):
        cols = shutil.get_terminal_size(fallback=(85, 24)).columns
        self.width = max(50, min(105, target_width or (cols - 4)))
        self.table_formatter = AdaptiveTableFormatter(max_width=self.width)

    def render(self, raw_text: str, title: str | None = None) -> str:
        """Render a raw markdown or HTML document into styled terminal text."""
        if not raw_text or not raw_text.strip():
            return f"\n  {C_MUTED}(Empty Document){C_RESET}\n"

        lines = raw_text.splitlines()

        # 1. Parse top GitHub metadata if present
        meta_title = title or ""
        meta_desc = ""
        content_start = 0

        if len(lines) >= 3 and lines[0].startswith("name:\t"):
            meta_title = lines[0].split("\t", 1)[1].strip()
            if lines[1].startswith("description:\t"):
                meta_desc = lines[1].split("\t", 1)[1].strip()
            # Skip past metadata boundary '--'
            for idx, line in enumerate(lines[:6]):
                if line.strip() == "--":
                    content_start = idx + 1
                    break

        content_lines = lines[content_start:]
        text_content = "\n".join(content_lines)

        output: list[str] = []

        # Render Top Document Header Card
        if meta_title:
            output.append(self._render_doc_header(meta_title, meta_desc))

        # Process the body
        rendered_body = self._render_body(text_content)
        output.append(rendered_body)

        # Render Bottom Document Footer Card
        output.append(self._render_doc_footer(meta_title))

        return "\n".join(output)

    def _render_doc_header(self, title: str, description: str) -> str:
        """Render executive top header banner."""
        banner_w = self.width
        title_str = f" 📖 Document: {title} "
        remaining_bar = "─" * max(2, banner_w - len(title_str) - 2)
        top = f"  {C_CYAN}╭{C_BOLD}{C_WHITE}{title_str}{C_CYAN}{remaining_bar}╮{C_RESET}"
        
        body_lines = []
        if description:
            wrapped = self._wrap_text(description, banner_w - 6)
            for wl in wrapped:
                body_lines.append(f"  {C_CYAN}│{C_RESET}   {C_MUTED}{wl}{C_RESET}")
            sep = f"  {C_CYAN}├{'─' * (banner_w - 2)}┤{C_RESET}"
            body_lines.append(sep)

        bottom = f"  {C_CYAN}╰{'─' * (banner_w - 2)}╯{C_RESET}"
        parts = [top]
        if body_lines:
            parts.extend(body_lines)
        parts.append(bottom)
        return "\n".join(parts) + "\n"

    def _render_doc_footer(self, title: str) -> str:
        """Render subtle bottom footer bar."""
        banner_w = self.width
        footer_label = " ✔ End of Document "
        vis_len = visual_len(footer_label)
        bar = "─" * max(2, banner_w - vis_len - 2)
        return f"\n  {C_MUTED}╰{footer_label}{bar}╯{C_RESET}\n"

    def _render_body(self, text: str) -> str:
        """Parse elements block by block."""
        # Normalize HTML breaks & special tags
        text = self._pre_sanitize_html(text)

        # Split into blocks separated by blank lines or headers/tables
        lines = text.splitlines()
        rendered_blocks: list[str] = []
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]
            trimmed = line.strip()

            # Skip empty lines
            if not trimmed:
                i += 1
                continue

            # 1. Code Block (```)
            if trimmed.startswith("```"):
                code_lines = []
                lang = trimmed.strip("`").strip()
                i += 1
                while i < n and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                if i < n:
                    i += 1  # Skip closing ```
                rendered_blocks.append(self._render_code_block(code_lines, lang))
                continue

            # 2. Markdown Table Block (| ... |)
            if trimmed.startswith("|") and trimmed.endswith("|"):
                table_lines = []
                while i < n and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                    table_lines.append(lines[i].strip())
                    i += 1
                rendered_blocks.append(self._render_table_block(table_lines))
                continue

            # 3. Headers (#, ##, ###)
            header_match = re.match(r"^(#{1,6})\s+(.+)$", trimmed)
            if header_match:
                level = len(header_match.group(1))
                heading = header_match.group(2).strip()
                rendered_blocks.append(self._render_header(heading, level))
                i += 1
                continue

            # 4. Blockquotes (> ...)
            if trimmed.startswith(">"):
                quote_lines = []
                while i < n and lines[i].strip().startswith(">"):
                    quote_lines.append(re.sub(r"^>\s*", "", lines[i].strip()))
                    i += 1
                rendered_blocks.append(self._render_blockquote(quote_lines))
                continue

            # 5. Horizontal rule (---, ***, ___)
            if re.match(r"^[-*_]{3,}$", trimmed):
                bar = "─" * (self.width - 4)
                rendered_blocks.append(f"  {C_MUTED}{bar}{C_RESET}")
                i += 1
                continue

            # 6. Bullet / Numbered List Item
            list_match = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.+)$", line)
            if list_match:
                indent_str = list_match.group(1)
                bullet_sym = list_match.group(2)
                item_text = list_match.group(3)
                rendered_blocks.append(self._render_list_item(item_text, bullet_sym, len(indent_str)))
                i += 1
                continue

            # 7. Regular paragraph / prose
            paragraph_lines = [line]
            i += 1
            while i < n:
                nxt = lines[i]
                nxt_trim = nxt.strip()
                if not nxt_trim or nxt_trim.startswith(("#", "```", "|", ">", "---", "***")) or re.match(r"^\s*([-*+]|\d+\.)\s+", nxt):
                    break
                paragraph_lines.append(nxt)
                i += 1

            p_text = " ".join(l.strip() for l in paragraph_lines if l.strip())
            rendered_blocks.append(self._render_paragraph(p_text))

        return "\n\n".join(b for b in rendered_blocks if b.strip())

    def _pre_sanitize_html(self, text: str) -> str:
        """Pre-processes HTML tags, breaks, badges, and containers."""
        # Replace <br>, <br/>, <br /> with newline
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

        # Transform shield badges inside links: <a href="url"><img src="...badge/Name..." alt="Alt" /></a>
        def _replace_shield_badge(m: re.Match) -> str:
            url = m.group(1)
            img_src = m.group(2)
            alt = m.group(3) or ""
            # Extract badge title
            badge_name = alt
            name_m = re.search(r"badge/([A-Za-z0-9_\-\.\s]+)-", img_src)
            if name_m:
                badge_name = name_m.group(1).replace("_", " ")
            if not badge_name:
                badge_name = "Link"

            icon = "🔗"
            b_lower = badge_name.lower()
            if "linkedin" in b_lower:
                icon = "💼"
            elif "email" in b_lower or "mail" in b_lower:
                icon = "✉"
            elif "github" in b_lower:
                icon = "🐙"
            elif "portfolio" in b_lower or "web" in b_lower:
                icon = "🌐"

            return f" [{icon} {badge_name}]({url}) "

        text = re.sub(
            r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>\s*<img\s+[^>]*src=["\']([^"\']+)["\'](?:\s+alt=["\']([^"\']*)["\'])?[^>]*/>\s*</a>',
            _replace_shield_badge,
            text,
            flags=re.IGNORECASE,
        )

        # Transform skillicons: <img src="...skillicons.dev/icons?i=py,c,cpp..." />
        def _replace_skillicons(m: re.Match) -> str:
            icons = m.group(1).split(",")
            icon_names = [ic.strip().capitalize() for ic in icons if ic.strip()]
            return f"**🛠 Tech Stack:** " + ", ".join(icon_names)

        text = re.sub(r'<img\s+[^>]*src=["\'][^"\']*skillicons\.dev/icons\?i=([a-zA-Z0-9_,]+)[^"\']*["\'][^>]*/>', _replace_skillicons, text, flags=re.IGNORECASE)

        # Transform contribution grid snake / stats graphs
        text = re.sub(
            r'<img\s+[^>]*alt=["\']Contribution Graph["\'][^>]*/>',
            "📊 **[GitHub Activity & Contribution Graph]**",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r'<img\s+[^>]*src=["\'][^"\']*github-readme-stats\.vercel\.app[^"\']*["\'][^>]*/>',
            "📊 **[GitHub Profile Stats & Top Languages]**",
            text,
            flags=re.IGNORECASE,
        )

        # Transform generic images: <img ... alt="Alt" ... />
        def _replace_img(m: re.Match) -> str:
            alt = m.group(1) or "Image"
            return f" [🖼 {alt.strip()}] "

        text = re.sub(r'<img\s+[^>]*alt=["\']([^"\']+)["\'][^>]*/>', _replace_img, text, flags=re.IGNORECASE)
        # Remove leftover img tags
        text = re.sub(r'<img\s+[^>]*/>', '', text, flags=re.IGNORECASE)

        # Unpack <sub>...</sub> and <sup>...</sup>
        text = re.sub(r'<sub[^>]*>(.*?)</sub>', r'✨ \1 ✨', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<sup[^>]*>(.*?)</sup>', r'[\1]', text, flags=re.IGNORECASE | re.DOTALL)

        # Unpack structural containers <div>, </div>, <p>, </p>, <picture>, </picture>, <source ...>
        text = re.sub(r'</?(?:div|p|picture|span|section|article)[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<source\s+[^>]*>', '', text, flags=re.IGNORECASE)

        # Unescape HTML entities (&nbsp;, &amp;, &lt;, &gt;, &#39;)
        text = text.replace("&nbsp;", " ")
        text = html.unescape(text)

        return text

    def _render_header(self, text: str, level: int) -> str:
        """Render distinct section headers with styling."""
        clean_text = self._inline_format(text)
        vis_t_len = visual_len(clean_text)

        if level == 1:
            bar_len = max(2, self.width - vis_t_len - 6)
            bar = "━" * bar_len
            return f"\n  {C_BOLD}{C_CYAN}━━━ {clean_text} {bar}{C_RESET}"
        elif level == 2:
            bar_len = max(2, self.width - vis_t_len - 6)
            bar = "─" * bar_len
            return f"\n  {C_BOLD}{C_MAGENTA}◆ {clean_text} {C_MUTED}{bar}{C_RESET}"
        else:
            return f"  {C_BOLD}{C_YELLOW}▸ {clean_text}{C_RESET}"

    def _render_blockquote(self, lines: Sequence[str]) -> str:
        """Render callout / quote block with left accent bar."""
        full_text = " ".join(lines)
        clean_text = self._inline_format(full_text).strip()
        wrapped = self._wrap_text(clean_text, self.width - 8)
        rendered = []
        for idx, wl in enumerate(wrapped):
            quote_mark = "❝ " if idx == 0 else "  "
            rendered.append(f"  {C_QUOTE_BAR}│{C_RESET} {C_DIM}{C_WHITE}{quote_mark}{wl}{C_RESET}")
        return "\n".join(rendered)

    def _render_list_item(self, text: str, bullet: str, indent: int) -> str:
        """Render a clean list item."""
        clean_text = self._inline_format(text)
        indent_sp = "  " + ("  " * (indent // 2))
        icon = f"{C_CYAN}•{C_RESET} " if bullet in ("-", "*", "+") else f"{C_YELLOW}{bullet}{C_RESET} "
        prefix_len = visual_len(strip_ansi(icon))
        wrapped = self._wrap_text(clean_text, self.width - len(indent_sp) - prefix_len - 2)

        if not wrapped:
            return f"{indent_sp}{icon}"

        res = [f"{indent_sp}{icon}{wrapped[0]}"]
        cont_indent = " " * (len(indent_sp) + prefix_len)
        for wl in wrapped[1:]:
            res.append(f"{cont_indent}{wl}")
        return "\n".join(res)

    def _render_paragraph(self, text: str) -> str:
        """Render wrapped prose with inline formatting."""
        clean_text = self._inline_format(text)
        wrapped = self._wrap_text(clean_text, self.width - 4)
        return "\n".join("  " + wl for wl in wrapped)

    def _render_code_block(self, lines: Sequence[str], lang: str) -> str:
        """Render a styled code box."""
        bw = self.width
        lang_label = f" ⌠ {lang or 'Code'} ⌡ "
        top_bar = "─" * max(2, bw - len(lang_label) - 2)
        top = f"  {C_YELLOW}╭{C_BOLD}{C_WHITE}{lang_label}{C_YELLOW}{top_bar}╮{C_RESET}"
        body = []
        for idx, l in enumerate(lines[:50]):
            code_line = l[: bw - 8]
            num = f"{idx + 1:2d} │ "
            body.append(f"  {C_YELLOW}│{C_RESET} {C_MUTED}{num}{C_GREEN}{code_line}{C_RESET}")
        bottom = f"  {C_YELLOW}╰{'─' * (bw - 2)}╯{C_RESET}"
        return top + "\n" + "\n".join(body) + "\n" + bottom

    def _render_table_block(self, lines: Sequence[str]) -> str:
        """
        Parses Markdown table.
        If it represents a Project Card (1 column with title, description, and badges),
        renders it as an executive rounded card.
        Otherwise, renders via AdaptiveTableFormatter.
        """
        parsed_rows: list[list[str]] = []
        for l in lines:
            if re.match(r"^\|(?:\s*:?-+:?\s*\|)+$", l):
                continue
            cells = [c.strip() for c in l.strip("|").split("|")]
            parsed_rows.append(cells)

        if not parsed_rows:
            return ""

        # Check if this is a Single-Column Project Card (e.g., Title in row 0, Description in row 1, tags in row 2)
        if len(parsed_rows[0]) == 1 and len(parsed_rows) >= 2:
            return self._render_project_card(parsed_rows)

        # Standard multi-column table
        headers = parsed_rows[0]
        data_rows = parsed_rows[1:] if len(parsed_rows) > 1 else []
        # Format inline elements in cells
        clean_headers = [self._inline_format(h) for h in headers]
        clean_data = [[self._inline_format(c) for c in row] for row in data_rows]

        return self.table_formatter.render_table(headers=clean_headers, rows=clean_data)

    def _render_project_card(self, rows: list[list[str]]) -> str:
        """Render an executive project card box."""
        card_w = self.width
        title_raw = rows[0][0]
        desc_raw = rows[1][0] if len(rows) > 1 else ""
        tags_raw = rows[2][0] if len(rows) > 2 else ""

        # Extract URL from title if [Title](URL)
        link_url = ""
        link_m = re.search(r"\[(.*?)\]\((https?://[^\)]+)\)", title_raw)
        if link_m:
            title_text = link_m.group(1)
            link_url = link_m.group(2)
        else:
            title_text = title_raw

        title_formatted = self._inline_format(title_text)
        vis_title_len = visual_len(title_formatted)
        top_bar = "─" * max(2, card_w - vis_title_len - 4)
        top = f"  {C_CARD_BORDER}╭─ {C_BOLD}{C_WHITE}{title_formatted} {C_CARD_BORDER}{top_bar}╮{C_RESET}"

        card_lines: list[str] = [top]

        # Link URL line
        if link_url:
            card_lines.append(f"  {C_CARD_BORDER}│{C_RESET}  {C_CYAN}🔗 {C_LINK_COLOR}{link_url}{C_RESET}")
            card_lines.append(f"  {C_CARD_BORDER}│{C_RESET}")

        # Description body
        if desc_raw:
            desc_clean = self._inline_format(desc_raw)
            wrapped_desc = self._wrap_text(desc_clean, card_w - 6)
            for wl in wrapped_desc:
                card_lines.append(f"  {C_CARD_BORDER}│{C_RESET}  {wl}")

        # Tags / Badges
        if tags_raw:
            card_lines.append(f"  {C_CARD_BORDER}│{C_RESET}")
            # Format badges
            badges_clean = self._inline_format(tags_raw)
            wrapped_badges = self._wrap_text(f"🏷  {badges_clean}", card_w - 6)
            for wbl in wrapped_badges:
                card_lines.append(f"  {C_CARD_BORDER}│{C_RESET}  {wbl}")

        bottom = f"  {C_CARD_BORDER}╰{'─' * (card_w - 2)}╯{C_RESET}"
        card_lines.append(bottom)
        return "\n".join(card_lines)

    def _inline_format(self, text: str) -> str:
        """Format inline markdown elements: links, bold, italic, code, kbd."""
        # 1. Format <kbd>Tag</kbd> -> [ Tag ]
        text = re.sub(
            r"<kbd>(.*?)</kbd>",
            f"{C_TAG_BG} \\1 {C_RESET}",
            text,
            flags=re.IGNORECASE,
        )

        # 2. Format inline code `code`
        text = re.sub(r"`([^`]+)`", f"{C_YELLOW}\\1{C_RESET}", text)

        # 3. Format markdown links [Text](URL)
        def _replace_link(m: re.Match) -> str:
            label = m.group(1)
            url = m.group(2)
            if label.strip() == url.strip():
                return f"{C_CYAN}{url}{C_RESET}"
            return f"{C_BOLD}{C_WHITE}{label}{C_RESET} {C_MUTED}({C_CYAN}{url}{C_MUTED}){C_RESET}"

        text = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", _replace_link, text)

        # 4. Format bold **text** or __text__
        text = re.sub(r"\*\*([^\*]+)\*\*", f"{C_BOLD}{C_WHITE}\\1{C_RESET}", text)
        text = re.sub(r"__([^_]+)__", f"{C_BOLD}{C_WHITE}\\1{C_RESET}", text)

        # 5. Format italic *text* or _text_
        text = re.sub(r"(?<!\*)\*([^\*\n]+)\*(?!\*)", f"{C_DIM}{C_WHITE}\\1{C_RESET}", text)

        return text

    def _wrap_text(self, text: str, max_w: int) -> list[str]:
        """Wrap prose cleanly respecting ANSI escape sequences."""
        words = text.split(" ")
        lines: list[str] = []
        cur_line: list[str] = []
        cur_len = 0

        for w in words:
            if not w:
                continue
            w_vis_len = visual_len(w)
            if cur_len + w_vis_len + (1 if cur_line else 0) <= max_w:
                cur_line.append(w)
                cur_len += w_vis_len + (1 if len(cur_line) > 1 else 0)
            else:
                if cur_line:
                    lines.append(" ".join(cur_line))
                cur_line = [w]
                cur_len = w_vis_len

        if cur_line:
            lines.append(" ".join(cur_line))

        return lines or [""]


# CLI Entrypoint: python -m ui.markdown_renderer [file_path_or_text]
if __name__ == "__main__":
    renderer = TerminalMarkdownRenderer()
    raw_input = ""

    if len(sys.argv) > 1:
        target = sys.argv[1]
        if target == "-":
            raw_input = sys.stdin.read()
        elif os.path.isfile(target):
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                raw_input = f.read()
        else:
            raw_input = " ".join(sys.argv[1:])
    else:
        # Default: read stdin if pipe, else test with sample
        if not sys.stdin.isatty():
            raw_input = sys.stdin.read()

    if raw_input:
        print(renderer.render(raw_input))
    else:
        # Test demonstration
        sample = """name:\tabneeshsingh21/abneeshsingh21
description:\tProduction Profile
--
<div align="center">
  <img src="assets/banner.svg" alt="Abneesh Singh - AI Systems Architect" width="100%" />
</div>
<br/>
<div align="center">
  <a href="https://www.linkedin.com/in/abneesh-singh001" target="_blank"><img src="https://img.shields.io/badge/LinkedIn-000000?style=for-the-badge&logo=linkedin&logoColor=white" alt="LinkedIn" /></a>
  <a href="mailto:singhabneesh250@gmail.com"><img src="https://img.shields.io/badge/Email-000000?style=for-the-badge&logo=gmail&logoColor=white" alt="Email" /></a>
  <a href="https://github.com/abneeshsingh21" target="_blank"><img src="https://img.shields.io/badge/GitHub-000000?style=for-the-badge&logo=github&logoColor=white" alt="GitHub" /></a>
</div>

## ⸻ Engineering Projects

| 🧠 [NeuroShell — Intelligent AI Terminal](https://github.com/abneeshsingh21/neuroshell) |
| :--- |
| Spearheaded development of a hybrid C++ and Python engine for natural language to shell command translation, supporting 6 LLM providers with smart cloud-to-local fallback. Delivered a 2,500-phrase machine learning offline engine, a 4-layer safety system, PII scrubbing, and a desktop monitoring dashboard backed by 85 automated tests. |
| <kbd>C++ / Python</kbd> &nbsp; <kbd>NLP</kbd> &nbsp; <kbd>Systems Architecture</kbd> &nbsp; <kbd>Automated Testing</kbd> |

---

## ⸻ Engineering Standard

> *My engineering philosophy is precision through abstraction — removing every layer of unnecessary complexity between a user's intent and the system's execution.*

<sub>Building with precision · Shipping with purpose · Thinking in ecosystems</sub>
"""
        print(renderer.render(sample))
