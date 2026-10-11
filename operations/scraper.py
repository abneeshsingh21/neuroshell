# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Universal Multi-Site Web Scraper & Data Extractor Engine for NeuroShell.
Harvests and structures web data across single or multiple websites concurrently:
- Clean article & page markdown extraction (stripping boilerplate, ads, navbars, footers)
- Automated HTML table parsing into structured terminal tables, CSV, or JSON
- Link and downloadable document harvester (filtering for PDFs, CSVs, zips, docs)
- CSS selector and targeted element extraction
- Concurrent multi-URL crawling with ThreadPoolExecutor
- Playwright headless browser fallback for JavaScript-rendered SPAs
- Optional AI semantic schema extraction
"""

from __future__ import annotations

import csv
import html
import importlib.util
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from ui.table_formatter import AdaptiveTableFormatter


# ANSI Colors
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


@dataclass
class ScrapedTable:
    """Structured representation of an extracted HTML table."""
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    caption: str = ""

    def to_csv(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        if self.headers:
            writer.writerow(self.headers)
        writer.writerows(self.rows)
        return output.getvalue()

    def to_dicts(self) -> list[dict[str, str]]:
        if not self.headers:
            return []
        res = []
        for row in self.rows:
            d = {}
            for i, h in enumerate(self.headers):
                d[h] = row[i] if i < len(row) else ""
            res.append(d)
        return res


@dataclass
class ScrapedLink:
    """Hyperlink extracted from a webpage."""
    text: str
    url: str
    is_document: bool = False
    doc_type: str = ""  # "pdf", "csv", "zip", etc.


@dataclass
class PageScrapeResult:
    """Extraction results for a single URL."""
    url: str
    title: str = ""
    text_content: str = ""
    markdown_content: str = ""
    tables: list[ScrapedTable] = field(default_factory=list)
    links: list[ScrapedLink] = field(default_factory=list)
    status_code: int = 200
    elapsed_seconds: float = 0.0
    error: str = ""
    used_browser: bool = False


# ═══════════════════════════════════════════════════════════
# High-Efficiency Native HTML Parsers (Zero Mandatory Dependencies)
# ═══════════════════════════════════════════════════════════

class CleanTextExtractor(HTMLParser):
    """Extract clean text and structure from raw HTML, skipping noise."""
    
    IGNORE_TAGS = {
        "script", "style", "noscript", "svg", "iframe", "header",
        "footer", "nav", "aside", "form", "button", "select", "option",
    }
    BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "div", "article", "section", "tr"}

    def __init__(self):
        super().__init__()
        self._ignore_depth = 0
        self._pieces: list[str] = []
        self._title_pieces: list[str] = []
        self._in_title = False
        self._current_tag = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag_lower = tag.lower()
        self._current_tag = tag_lower
        if tag_lower in self.IGNORE_TAGS:
            self._ignore_depth += 1
        elif tag_lower == "title":
            self._in_title = True
        elif tag_lower in self.BLOCK_TAGS and self._ignore_depth == 0:
            self._pieces.append("\n")
            if tag_lower.startswith("h") and len(tag_lower) == 2 and tag_lower[1].isdigit():
                level = int(tag_lower[1])
                self._pieces.append("#" * level + " ")
            elif tag_lower == "li":
                self._pieces.append("• ")

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower in self.IGNORE_TAGS:
            self._ignore_depth = max(0, self._ignore_depth - 1)
        elif tag_lower == "title":
            self._in_title = False
        elif tag_lower in self.BLOCK_TAGS and self._ignore_depth == 0:
            self._pieces.append("\n")

    def handle_data(self, data: str):
        if self._in_title:
            self._title_pieces.append(data.strip())
        elif self._ignore_depth == 0:
            cleaned = data.strip()
            if cleaned:
                self._pieces.append(cleaned + " ")

    def get_title(self) -> str:
        return " ".join(self._title_pieces).strip()

    def get_markdown(self) -> str:
        raw = "".join(self._pieces)
        # Collapse excessive newlines
        collapsed = re.sub(r"\n{3,}", "\n\n", raw)
        return collapsed.strip()


class TableExtractor(HTMLParser):
    """Extract all <table> structures into ScrapedTable objects."""

    def __init__(self):
        super().__init__()
        self.tables: list[ScrapedTable] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._is_header_cell = False
        self._current_table: ScrapedTable | None = None
        self._current_row: list[str] = []
        self._cell_pieces: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag_lower = tag.lower()
        if tag_lower == "table":
            self._in_table = True
            self._current_table = ScrapedTable()
        elif self._in_table:
            if tag_lower == "tr":
                self._in_row = True
                self._current_row = []
            elif tag_lower in ("td", "th"):
                self._in_cell = True
                self._is_header_cell = (tag_lower == "th")
                self._cell_pieces = []

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower == "table" and self._current_table:
            self._in_table = False
            if self._current_table.rows or self._current_table.headers:
                self.tables.append(self._current_table)
            self._current_table = None
        elif self._in_table:
            if tag_lower == "tr" and self._in_row:
                self._in_row = False
                if self._current_table:
                    if not self._current_table.headers and all(self._is_header_cell for _ in self._current_row):
                        self._current_table.headers = list(self._current_row)
                    elif any(c.strip() for c in self._current_row):
                        self._current_table.rows.append(list(self._current_row))
            elif tag_lower in ("td", "th") and self._in_cell:
                self._in_cell = False
                cell_text = " ".join(self._cell_pieces).strip()
                cell_clean = re.sub(r"\s+", " ", cell_text)
                self._current_row.append(cell_clean)

    def handle_data(self, data: str):
        if self._in_cell:
            self._cell_pieces.append(data.strip())


class LinkExtractor(HTMLParser):
    """Extract all hyperlinks and identify downloadable documents."""

    DOC_EXTENSIONS = {
        "pdf": ".pdf", "csv": ".csv", "xlsx": ".xlsx", "xls": ".xls",
        "docx": ".docx", "doc": ".doc", "zip": ".zip", "tar.gz": ".tar.gz",
        "json": ".json", "xml": ".xml", "mp4": ".mp4", "mp3": ".mp3",
    }

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: list[ScrapedLink] = []
        self._in_a = False
        self._current_href = ""
        self._a_pieces: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag.lower() == "a":
            self._in_a = True
            self._a_pieces = []
            for k, v in attrs:
                if k.lower() == "href" and v:
                    self._current_href = v.strip()
                    break

    def handle_endtag(self, tag: str):
        if tag.lower() == "a" and self._in_a:
            self._in_a = False
            if self._current_href and not self._current_href.startswith(("#", "javascript:", "mailto:", "tel:")):
                abs_url = urljoin(self.base_url, self._current_href)
                text = " ".join(self._a_pieces).strip() or os.path.basename(urlparse(abs_url).path) or abs_url
                
                # Check if it's a downloadable document
                lower_url = abs_url.lower()
                doc_type = ""
                is_doc = False
                for dtype, ext in self.DOC_EXTENSIONS.items():
                    if lower_url.endswith(ext) or f"{ext}?" in lower_url:
                        is_doc = True
                        doc_type = dtype
                        break

                self.links.append(ScrapedLink(
                    text=text,
                    url=abs_url,
                    is_document=is_doc,
                    doc_type=doc_type,
                ))

    def handle_data(self, data: str):
        if self._in_a:
            self._a_pieces.append(data.strip())


# ═══════════════════════════════════════════════════════════
# WebScraper Engine
# ═══════════════════════════════════════════════════════════

class WebScraper:
    """
    Production-grade web scraper with concurrent multi-URL harvesting,
    table extraction, document discovery, and Playwright SPA fallback.
    """

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 NeuroShell/5.0"
    )

    def __init__(self, timeout_s: int = 20):
        self.timeout_s = timeout_s
        self.table_formatter = AdaptiveTableFormatter()

    @staticmethod
    def _playwright_available() -> bool:
        return importlib.util.find_spec("playwright") is not None

    def fetch_raw_html(self, url: str) -> tuple[str, int]:
        """Fetch HTML over HTTP/HTTPS with proper headers and compression support."""
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid URL: {url}. Must include http:// or https://")

        req = Request(
            url,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urlopen(req, timeout=self.timeout_s) as resp:
            data = resp.read()
            status = getattr(resp, "status", 200)
            encoding = resp.headers.get_content_charset() or "utf-8"
            return data.decode(encoding, errors="replace"), status

    def fetch_with_browser(self, url: str) -> str:
        """Fetch JavaScript-rendered single-page application via Playwright headless Chromium."""
        if not self._playwright_available():
            raise RuntimeError("Playwright is not installed. Run: pip install playwright && playwright install chromium")

        from playwright.sync_api import sync_playwright  # type: ignore

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    user_agent=self.USER_AGENT,
                    viewport={"width": 1440, "height": 900},
                )
                page.goto(url, wait_until="networkidle", timeout=self.timeout_s * 1000)
                return page.content()
            finally:
                browser.close()

    def scrape_url(
        self,
        url: str,
        mode: str = "text",
        selector: str | None = None,
        render_js: bool = False,
    ) -> PageScrapeResult:
        """Scrape and structure content from a single URL."""
        t0 = time.time()
        res = PageScrapeResult(url=url)

        try:
            raw_html = ""
            used_browser = False

            if render_js:
                raw_html = self.fetch_with_browser(url)
                used_browser = True
            else:
                try:
                    raw_html, status = self.fetch_raw_html(url)
                    res.status_code = status
                    # Check if body is suspiciously empty / client-side SPA placeholder
                    if len(raw_html) < 800 and ("<noscript" in raw_html.lower() or "javascript" in raw_html.lower()) and self._playwright_available():
                        raw_html = self.fetch_with_browser(url)
                        used_browser = True
                except Exception as net_err:
                    if self._playwright_available():
                        raw_html = self.fetch_with_browser(url)
                        used_browser = True
                    else:
                        raise net_err

            res.used_browser = used_browser

            # 1. Extract clean text & Markdown
            text_extractor = CleanTextExtractor()
            text_extractor.feed(raw_html)
            res.title = text_extractor.get_title()
            res.markdown_content = text_extractor.get_markdown()
            res.text_content = re.sub(r"[#*•]", "", res.markdown_content).strip()

            # 2. Extract HTML tables
            table_extractor = TableExtractor()
            table_extractor.feed(raw_html)
            res.tables = table_extractor.tables

            # 3. Extract links & documents
            link_extractor = LinkExtractor(base_url=url)
            link_extractor.feed(raw_html)
            res.links = link_extractor.links

            # 4. Optional CSS selector filtering
            if selector:
                res.text_content = self._filter_by_selector(raw_html, selector)

        except Exception as e:
            res.error = str(e)

        res.elapsed_seconds = time.time() - t0
        return res

    def scrape_multi(
        self,
        urls: list[str],
        mode: str = "text",
        max_workers: int = 5,
        render_js: bool = False,
    ) -> list[PageScrapeResult]:
        """Concurrently scrape multiple websites using ThreadPoolExecutor."""
        results: list[PageScrapeResult] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(self.scrape_url, u.strip(), mode=mode, render_js=render_js): u.strip()
                for u in urls if u.strip()
            }
            for future in as_completed(future_to_url):
                u = future_to_url[future]
                try:
                    res = future.result()
                    results.append(res)
                except Exception as e:
                    results.append(PageScrapeResult(url=u, error=str(e)))
        return results

    def search_and_scrape(
        self,
        query: str,
        limit: int = 5,
        mode: str = "text",
        render_js: bool = False,
    ) -> list[PageScrapeResult]:
        """
        Search the web using search discovery to locate top authority URLs,
        then concurrently scrape all discovered websites.
        """
        clean_query = query.strip()
        print(f"\n  {C_BOLD}{C_CYAN}🌐 Web Search Discovery: {C_WHITE}'{clean_query}' (Top {limit} sites){C_RESET}\n")
        discovered_urls = self._search_urls(clean_query, limit=limit)
        if not discovered_urls:
            print(f"  {C_YELLOW}⚠ No search results returned for query: '{clean_query}'{C_RESET}\n")
            return []
        print(f"  {C_MUTED}Discovered {len(discovered_urls)} URLs. Scraping concurrently...{C_RESET}\n")
        return self.scrape_multi(discovered_urls, mode=mode, render_js=render_js)

    def _search_urls(self, query: str, limit: int = 5) -> list[str]:
        """Query DuckDuckGo Lite search to extract organic search result URLs."""
        urls = []
        try:
            import urllib.parse
            data = urllib.parse.urlencode({"q": query}).encode()
            req = Request("https://lite.duckduckgo.com/lite/", data=data, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            })
            with urlopen(req, timeout=12) as resp:
                raw_html = resp.read().decode("utf-8", errors="replace")

            # Extract URLs from result links
            matches = re.findall(r'href=[\"\'](https?://[^\s\"\']+)[\"\']\s+class=[\"\']result-link', raw_html)
            for u in matches:
                if u not in urls and "duckduckgo.com" not in u:
                    urls.append(u)
                    if len(urls) >= limit:
                        break
        except Exception:
            pass
        return urls

    def _filter_by_selector(self, raw_html: str, selector: str) -> str:
        """Extract matching elements by CSS class, id, or tag name."""
        clean_sel = selector.strip()
        matches = []
        if clean_sel.startswith("."):
            cls_name = clean_sel[1:]
            pattern = re.compile(rf'<[^>]+class=["\'][^"\']*\b{re.escape(cls_name)}\b[^"\']*["\'][^>]*>(.*?)</[^>]+>', re.DOTALL | re.IGNORECASE)
            for m in pattern.finditer(raw_html):
                clean_text = re.sub(r"<[^>]+>", " ", m.group(1)).strip()
                if clean_text:
                    matches.append(clean_text)
        elif clean_sel.startswith("#"):
            id_name = clean_sel[1:]
            pattern = re.compile(rf'<[^>]+id=["\']{re.escape(id_name)}["\'][^>]*>(.*?)</[^>]+>', re.DOTALL | re.IGNORECASE)
            for m in pattern.finditer(raw_html):
                clean_text = re.sub(r"<[^>]+>", " ", m.group(1)).strip()
                if clean_text:
                    matches.append(clean_text)
        else:
            tag_name = clean_sel.lower()
            pattern = re.compile(rf'<{re.escape(tag_name)}[^>]*>(.*?)</{re.escape(tag_name)}>', re.DOTALL | re.IGNORECASE)
            for m in pattern.finditer(raw_html):
                clean_text = re.sub(r"<[^>]+>", " ", m.group(1)).strip()
                if clean_text:
                    matches.append(clean_text)

        return "\n".join(matches) if matches else f"No elements matched selector: {selector}"

    def print_result(self, result: PageScrapeResult, mode: str = "text", max_lines: int = 40) -> None:
        """Render beautiful formatted CLI output for scraped page."""
        if result.error:
            print(f"\n  {C_RED}❌ Error scraping {result.url}: {result.error}{C_RESET}\n")
            return

        browser_tag = f" {C_YELLOW}[Headless Browser]{C_RESET}" if result.used_browser else ""
        print(f"\n  {C_BOLD}{C_CYAN}🌐 Scraped: {C_WHITE}{result.url}{browser_tag}{C_RESET}")
        if result.title:
            print(f"  {C_MUTED}Title: {C_WHITE}{result.title}{C_RESET}")
        print(f"  {C_MUTED}Fetched in: {result.elapsed_seconds:.2f}s • Status: {C_GREEN}{result.status_code}{C_RESET}\n")

        if mode == "tables" or (not mode and result.tables):
            if not result.tables:
                print(f"  {C_YELLOW}⚠ No HTML tables found on this page.{C_RESET}\n")
            else:
                for idx, tbl in enumerate(result.tables):
                    print(self.table_formatter.render_table(
                        headers=tbl.headers or [f"Col {i+1}" for i in range(len(tbl.rows[0]) if tbl.rows else 0)],
                        rows=tbl.rows[:30],
                        title=f"Table {idx + 1} ({len(tbl.rows)} rows)",
                    ))
                    print()
                return

        if mode == "links":
            doc_links = [l for l in result.links if l.is_document]
            all_links = result.links[:40]
            if doc_links:
                print(f"  {C_BOLD}{C_MAGENTA}📄 Downloadable Documents Found ({len(doc_links)}):{C_RESET}")
                for dl in doc_links[:20]:
                    print(f"  • {C_CYAN}[{dl.doc_type.upper()}]{C_RESET} {C_WHITE}{dl.text}{C_RESET} → {C_MUTED}{dl.url}{C_RESET}")
                print()

            print(f"  {C_BOLD}{C_CYAN}🔗 Page Links ({len(result.links)} total):{C_RESET}")
            for l in all_links[:25]:
                print(f"  • {C_WHITE}{l.text[:40]}{C_RESET} → {C_MUTED}{l.url}{C_RESET}")
            print()
            return

        # Default text/markdown mode
        print(f"  {C_BOLD}{C_WHITE}--- Page Content ---{C_RESET}")
        lines = result.markdown_content.splitlines()
        for ln in lines[:max_lines]:
            print(f"  {ln}")
        if len(lines) > max_lines:
            print(f"\n  {C_MUTED}... [{len(lines) - max_lines} more lines. Use --out <file> to export full content]{C_RESET}")
        print()


# CLI Entrypoint: python -m operations.scraper <url(s)|search <query>|-f <file>> [--mode text|tables|links]
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m operations.scraper <url1,url2... | search <query> | -f <file>> [--mode text|tables|links] [--out <file>]")
        sys.exit(1)

    first_arg = sys.argv[1]
    mode_arg = "text"
    sel_arg = None
    out_arg = None
    render_js_arg = False
    url_list = []
    is_search = False
    search_query = ""

    # Check search mode
    if first_arg.lower() in ("search", "-s", "--search"):
        is_search = True
        search_query = " ".join([a for a in sys.argv[2:] if not a.startswith("--")])
    elif first_arg in ("-f", "--file") and len(sys.argv) > 2:
        file_path = Path(sys.argv[2])
        if file_path.is_file():
            url_list = [l.strip() for l in file_path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    elif os.path.isfile(first_arg) and first_arg.endswith((".txt", ".urls")):
        url_list = [l.strip() for l in Path(first_arg).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    else:
        url_list = [u.strip() for u in first_arg.split(",") if u.strip()]

    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--mode" and i + 1 < len(sys.argv):
            mode_arg = sys.argv[i + 1]
            i += 2
        elif arg == "--selector" and i + 1 < len(sys.argv):
            sel_arg = sys.argv[i + 1]
            i += 2
        elif arg == "--out" and i + 1 < len(sys.argv):
            out_arg = sys.argv[i + 1]
            i += 2
        elif arg == "--render-js":
            render_js_arg = True
            i += 1
        else:
            i += 1

    scraper = WebScraper()
    formatter = AdaptiveTableFormatter()

    if is_search:
        results = scraper.search_and_scrape(search_query, limit=5, mode=mode_arg, render_js=render_js_arg)
    elif len(url_list) == 1:
        res = scraper.scrape_url(url_list[0], mode=mode_arg, selector=sel_arg, render_js=render_js_arg)
        scraper.print_result(res, mode=mode_arg)
        if out_arg:
            Path(out_arg).write_text(res.markdown_content, encoding="utf-8")
            print(f"  {C_GREEN}✔ Saved content to: {out_arg}{C_RESET}\n")
        results = [res]
    else:
        print(f"\n  {C_BOLD}{C_CYAN}🌐 Concurrently scraping {len(url_list)} websites...{C_RESET}\n")
        results = scraper.scrape_multi(url_list, mode=mode_arg, render_js=render_js_arg)
        for r in results:
            scraper.print_result(r, mode=mode_arg, max_lines=12)

    # Render Multi-Site Summary Table if more than 1 result
    if len(results) > 1:
        summary_rows = []
        for idx, r in enumerate(results):
            status_badge = "OK (200)" if not r.error else "FAILED"
            clean_title = (r.title[:30] + "...") if len(r.title) > 30 else (r.title or "-")
            summary_rows.append([
                str(idx + 1),
                r.url[:40],
                clean_title,
                str(len(r.tables)),
                str(len([l for l in r.links if l.is_document])),
                f"{r.elapsed_seconds:.2f}s",
                status_badge,
            ])
        print("\n" + formatter.render_table(
            headers=["#", "TARGET URL", "TITLE", "TABLES", "DOCS", "TIME", "STATUS"],
            rows=summary_rows,
            title=f"Multi-Site Extraction Matrix ({len(results)} Sites)",
        ) + "\n")

