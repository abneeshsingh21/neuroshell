# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Unified Terminal Harvester Pipeline for NeuroShell.
Chains WebScraper and UniversalDownloader into a seamless bulk asset,
document, and structured data pipeline:
- Scrapes web pages / documentation portals concurrently
- Extracts and adaptively formats HTML tables into Unicode console tables or CSV/JSON
- Identifies downloadable documents (.pdf, .csv, .zip, .xlsx, .docx, images)
- Streams bulk asset downloads with HTTP resume, SHA-256 integrity, and progress bars
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

# Ensure neuroshell root is on sys.path regardless of execution CWD
_NEUROSHELL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _NEUROSHELL_ROOT not in sys.path:
    sys.path.insert(0, _NEUROSHELL_ROOT)

from ui.table_formatter import AdaptiveTableFormatter
from operations.downloader import UniversalDownloader, DownloadResult
from operations.scraper import WebScraper, PageScrapeResult, ScrapedTable, ScrapedLink


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
class HarvestSummary:
    """Consolidated results of a harvest operation."""
    urls_scraped: list[str] = field(default_factory=list)
    total_tables_extracted: int = 0
    total_documents_found: int = 0
    total_downloads_completed: int = 0
    downloads: list[DownloadResult] = field(default_factory=list)
    tables: list[ScrapedTable] = field(default_factory=list)
    elapsed_seconds: float = 0.0


class TerminalHarvester:
    """
    Unified harvester orchestrator: Scraper -> Harvester -> Downloader.
    """

    def __init__(self, dest_dir: Path | str | None = None, timeout_s: int = 25):
        self.dest_dir = Path(dest_dir) if dest_dir else (Path.home() / "Downloads" / "Harvester")
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        self.scraper = WebScraper(timeout_s=timeout_s)
        self.downloader = UniversalDownloader(default_dir=self.dest_dir)
        self.formatter = AdaptiveTableFormatter()

    def harvest(
        self,
        urls: str | Sequence[str],
        doc_type: str | None = None,
        extract_tables: bool = True,
        download_docs: bool = True,
        max_downloads: int = 20,
        render_tables: bool = True,
        save_csv: Path | str | None = None,
    ) -> HarvestSummary:
        """Execute unified harvest workflow across given URLs or search query."""
        t0 = time.time()
        import re

        page_results: list[PageScrapeResult] = []
        url_list: list[str] = []

        # Check if search mode
        if isinstance(urls, str) and (urls.lower().startswith("search:") or urls.lower().startswith("search ")):
            query = re.sub(r"^search:?\s*", "", urls, flags=re.IGNORECASE).strip()
            print(f"\n  {C_BOLD}{C_MAGENTA}🌾 NeuroShell Universal Harvester (Web Search Discovery){C_RESET}")
            print(f"  {C_MUTED}Query: '{query}' • Destination: {self.dest_dir}{C_RESET}\n")
            page_results = self.scraper.search_and_scrape(query, limit=5, mode="all")
            url_list = [p.url for p in page_results if p.url]
        # Check if batch file
        elif isinstance(urls, str) and (urls.startswith(("-f ", "--file ")) or (os.path.isfile(urls) and urls.endswith((".txt", ".urls")))):
            p = Path(urls.replace("-f ", "").replace("--file ", "").strip())
            if p.is_file():
                url_list = [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
            else:
                url_list = []
            print(f"\n  {C_BOLD}{C_MAGENTA}🌾 NeuroShell Universal Harvester (Batch URL File){C_RESET}")
            print(f"  {C_MUTED}File: {p.name} ({len(url_list)} URLs) • Destination: {self.dest_dir}{C_RESET}\n")
            page_results = self.scraper.scrape_multi(url_list, mode="all") if url_list else []
        else:
            url_list = [u.strip() for u in (urls.split(",") if isinstance(urls, str) else urls) if u.strip()]
            if not url_list:
                print(f"  {C_RED}❌ Harvester error: No valid target URLs provided.{C_RESET}")
                return HarvestSummary()

            print(f"\n  {C_BOLD}{C_MAGENTA}🌾 NeuroShell Universal Harvester{C_RESET}")
            print(f"  {C_MUTED}Targets: {len(url_list)} URL(s) • Destination: {self.dest_dir}{C_RESET}\n")

            if len(url_list) == 1:
                page_results = [self.scraper.scrape_url(url_list[0], mode="all")]
            else:
                page_results = self.scraper.scrape_multi(url_list, mode="all")

        # Multi-Site Extraction Overview Matrix
        if len(page_results) > 1:
            matrix_rows = []
            for idx, r in enumerate(page_results):
                status_str = "OK" if not r.error else "FAILED"
                doc_count = len([l for l in r.links if l.is_document])
                matrix_rows.append([
                    str(idx + 1),
                    r.url[:40],
                    (r.title[:28] + "...") if len(r.title) > 28 else (r.title or "-"),
                    str(len(r.tables)),
                    str(doc_count),
                    f"{r.elapsed_seconds:.2f}s",
                    status_str,
                ])
            print(self.formatter.render_table(
                headers=["#", "TARGET URL", "TITLE", "TABLES", "DOCS", "TIME", "STATUS"],
                rows=matrix_rows,
                title="Multi-Site Harvester Matrix",
            ) + "\n")

        summary = HarvestSummary(urls_scraped=url_list)
        all_doc_links: list[ScrapedLink] = []
        seen_urls: set[str] = set()

        for res in page_results:
            if res.error:
                print(f"  {C_YELLOW}⚠ Failed to scrape {res.url}: {res.error}{C_RESET}")
                continue

            # Accumulate tables
            if extract_tables and res.tables:
                summary.tables.extend(res.tables)
                summary.total_tables_extracted += len(res.tables)

            # Accumulate document links
            for link in res.links:
                if link.is_document and link.url not in seen_urls:
                    # Filter by doc_type if specified
                    if doc_type:
                        dtype = doc_type.lower().lstrip(".")
                        if dtype != "all" and link.doc_type != dtype and not link.url.lower().endswith(f".{dtype}"):
                            continue
                    seen_urls.add(link.url)
                    all_doc_links.append(link)

        summary.total_documents_found = len(all_doc_links)

        # 2. Render or Save Extracted Tables
        if extract_tables and summary.tables:
            print(f"  {C_BOLD}{C_CYAN}📊 Extracted {len(summary.tables)} Table(s):{C_RESET}\n")
            for idx, tbl in enumerate(summary.tables[:5]):  # Show up to 5 tables
                if render_tables and tbl.headers:
                    print(self.formatter.render_table(
                        headers=tbl.headers,
                        rows=tbl.rows[:15],  # First 15 rows
                        title=f"Table {idx + 1}" + (f": {tbl.caption}" if tbl.caption else "")
                    ))
                    if len(tbl.rows) > 15:
                        print(f"  {C_MUTED}... and {len(tbl.rows) - 15} more rows.{C_RESET}\n")
                    print()

            if save_csv:
                csv_path = Path(save_csv)
                csv_path.parent.mkdir(parents=True, exist_ok=True)
                with open(csv_path, "w", encoding="utf-8") as f:
                    for tbl in summary.tables:
                        f.write(tbl.to_csv())
                        f.write("\n\n")
                print(f"  {C_GREEN}✔ Exported all tables to: {csv_path}{C_RESET}\n")

        # 3. Bulk Download Discovered Documents
        if download_docs and all_doc_links:
            docs_to_download = all_doc_links[:max_downloads]
            print(f"  {C_BOLD}{C_CYAN}⬇ Downloading {len(docs_to_download)} Discovered Document(s)...{C_RESET}\n")

            download_rows = []
            for idx, doc in enumerate(docs_to_download):
                print(f"  [{idx + 1}/{len(docs_to_download)}] Downloading: {doc.text} ({doc.doc_type.upper() or 'FILE'})")
                dl_res = self.downloader.download(
                    doc.url,
                    destination=self.dest_dir,
                    show_progress=True,
                )
                summary.downloads.append(dl_res)
                if dl_res.success:
                    summary.total_downloads_completed += 1
                    status = "SUCCESS"
                    size_mb = f"{dl_res.bytes_downloaded / (1024 * 1024):.2f}"
                else:
                    status = "FAILED"
                    size_mb = "0.00"

                download_rows.append([
                    str(idx + 1),
                    dl_res.destination.name if dl_res.destination else os.path.basename(doc.url),
                    doc.doc_type.upper() or "FILE",
                    size_mb,
                    status,
                ])

            # Render Summary Table
            if download_rows:
                print("\n  " + self.formatter.render_table(
                    headers=["#", "DOWNLOADED FILE", "TYPE", "SIZE (MB)", "STATUS"],
                    rows=download_rows,
                    title="Harvest Download Summary"
                ))
        elif not all_doc_links and download_docs:
            print(f"  {C_MUTED}No downloadable document files matching criteria were found.{C_RESET}\n")

        summary.elapsed_seconds = time.time() - t0
        print(f"\n  {C_GREEN}✔ Harvest finished in {summary.elapsed_seconds:.2f}s "
              f"({summary.total_tables_extracted} tables, {summary.total_downloads_completed} files downloaded){C_RESET}\n")
        return summary


def main():
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("search", "-s", "--search"):
        query_words = []
        dest_val = None
        type_val = None
        csv_val = None
        no_tables_val = False
        no_download_val = False
        max_val = 20

        i = 2
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg in ("--type", "-t") and i + 1 < len(sys.argv):
                type_val = sys.argv[i + 1]
                i += 2
            elif arg in ("--dest", "-d") and i + 1 < len(sys.argv):
                dest_val = sys.argv[i + 1]
                i += 2
            elif arg in ("--max", "-m") and i + 1 < len(sys.argv):
                max_val = int(sys.argv[i + 1])
                i += 2
            elif arg in ("--csv", "-c") and i + 1 < len(sys.argv):
                csv_val = sys.argv[i + 1]
                i += 2
            elif arg == "--no-tables":
                no_tables_val = True
                i += 1
            elif arg == "--no-download":
                no_download_val = True
                i += 1
            else:
                query_words.append(arg)
                i += 1

        harvester = TerminalHarvester(dest_dir=dest_val)
        harvester.harvest(
            urls=f"search: {' '.join(query_words)}",
            doc_type=type_val,
            extract_tables=not no_tables_val,
            download_docs=not no_download_val,
            max_downloads=max_val,
            save_csv=csv_val,
        )
        return

    parser = argparse.ArgumentParser(description="NeuroShell Universal Web Harvester & Data Pipeline")
    parser.add_argument("urls", help="Target URL, comma-separated list of URLs, or path to URL text file")
    parser.add_argument("--type", "-t", default=None, help="Filter document types (pdf, csv, zip, docx, all)")
    parser.add_argument("--dest", "-d", default=None, help="Target download directory")
    parser.add_argument("--max", "-m", type=int, default=20, help="Maximum number of files to download")
    parser.add_argument("--no-tables", action="store_true", help="Skip table extraction")
    parser.add_argument("--no-download", action="store_true", help="Skip downloading files (discover only)")
    parser.add_argument("--csv", default=None, help="Save extracted tables to CSV file")

    args = parser.parse_args()
    harvester = TerminalHarvester(dest_dir=args.dest)
    harvester.harvest(
        urls=args.urls,
        doc_type=args.type,
        extract_tables=not args.no_tables,
        download_docs=not args.no_download,
        max_downloads=args.max,
        save_csv=args.csv,
    )


if __name__ == "__main__":
    main()
