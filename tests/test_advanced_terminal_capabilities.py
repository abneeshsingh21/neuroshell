"""
Comprehensive Test Suite for Advanced Terminal Capabilities:
- Adaptive Table & Output Presentation Engine (ui/table_formatter.py)
- Universal Terminal Downloader Engine (operations/downloader.py)
- Multi-Site Web Scraper & Harvester (operations/scraper.py)
- Dynamic Intelligence Translations for Downloads and Scraping (intelligence/translator.py)
"""

import os
import platform
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import io

from ui.table_formatter import AdaptiveTableFormatter, ColumnSpec, strip_ansi
from operations.downloader import UniversalDownloader, DownloadResult
from operations.scraper import (
    WebScraper,
    PageScrapeResult,
    ScrapedTable,
    ScrapedLink,
    CleanTextExtractor,
    TableExtractor,
    LinkExtractor,
)
from intelligence.translator import Translator


class TestAdaptiveTableFormatter(unittest.TestCase):
    """Test suite for responsive terminal table layout engine."""

    def setUp(self):
        self.headers = ["Repository", "Access", "Description", "Updated"]
        self.rows = [
            ["facebook/react", "public", "The library for web and native user interfaces with rich components", "2026-04-10T14:22:00Z"],
            ["my-org/private-repo", "private", "Internal confidential system backend microservices orchestration", "2026-03-01T09:15:30Z"],
            ["minimal", "public", "Short", "2026-01-01T00:00:00Z"]
        ]

    def test_wide_terminal_rendering(self):
        """Tables render cleanly without artificial truncation on wide consoles."""
        formatter = AdaptiveTableFormatter(style="rounded", max_width=120)
        output = formatter.render_table(self.headers, self.rows)
        lines = output.splitlines()

        # Check box border presence
        clean_first = strip_ansi(lines[0])
        clean_last = strip_ansi(lines[-1])
        self.assertTrue(clean_first.strip().startswith("╭"))
        self.assertTrue(clean_last.strip().startswith("╰"))
        # Verify all headers are present
        header_line = strip_ansi(lines[1])
        self.assertIn("Repository", header_line)
        self.assertIn("Access", header_line)
        self.assertIn("Description", header_line)
        self.assertIn("Updated", header_line)

        # Width of all lines should not exceed max_width + margin
        for line in lines:
            self.assertLessEqual(len(strip_ansi(line)), 125)

    def test_narrow_terminal_truncation(self):
        """Tables adaptively truncate auxiliary descriptions when terminal is narrow."""
        formatter = AdaptiveTableFormatter(style="rounded", max_width=65)
        output = formatter.render_table(self.headers, self.rows)
        lines = output.splitlines()

        for line in lines:
            self.assertLessEqual(len(strip_ansi(line)), 70)

        # Truncation ellipsis should be present on long descriptions
        self.assertTrue(any("..." in strip_ansi(line) for line in lines))

    def test_ascii_border_mode(self):
        """ASCII borders are rendered cleanly when ascii style is requested."""
        formatter = AdaptiveTableFormatter(style="ascii", max_width=80)
        output = formatter.render_table(self.headers, self.rows)
        lines = output.splitlines()

        clean_first = strip_ansi(lines[0]).strip()
        clean_last = strip_ansi(lines[-1]).strip()
        clean_header = strip_ansi(lines[1]).strip()
        self.assertTrue(clean_first.startswith("+"))
        self.assertTrue(clean_last.startswith("+"))
        self.assertTrue(clean_header.startswith("|"))

    def test_tsv_and_csv_stream_parsing(self):
        """TSV/CSV raw terminal streams are cleanly converted into box-drawing tables."""
        tsv_data = (
            "org/repo-one\tpublic\tMain api server\t2026-04-01\n"
            "org/repo-two\tprivate\tCore auth engine\t2026-04-02\n"
        )
        formatter = AdaptiveTableFormatter(style="rounded", max_width=90)
        table = formatter.format_tsv(tsv_data, title="Repos")
        clean_table = strip_ansi(table)
        self.assertIn("repo-one", clean_table)
        self.assertIn("repo-two", clean_table)
        self.assertIn("Core auth engine", clean_table)

    def test_timestamp_and_badge_formatting(self):
        """Color badges and timestamps format correctly."""
        formatter = AdaptiveTableFormatter()
        pub_cell = formatter._colorize_cell("public", 2)
        self.assertIn("public", pub_cell)
        priv_cell = formatter._colorize_cell("private", 2)
        self.assertIn("private", priv_cell)

        ts_cell = formatter._colorize_cell("2026-10-12T00:15:30Z", 3)
        self.assertIn("2026-10-12", ts_cell)


class TestUniversalDownloader(unittest.TestCase):
    """Test suite for universal downloading engine across files, apps, and repos."""

    def setUp(self):
        self.downloader = UniversalDownloader()

    def test_git_repo_url_detection(self):
        """Downloader accurately detects git repository URLs."""
        self.assertTrue(self.downloader._is_git_target("https://github.com/torvalds/linux.git"))
        self.assertTrue(self.downloader._is_git_target("https://github.com/torvalds/linux"))
        self.assertTrue(self.downloader._is_git_target("git@github.com:torvalds/linux.git"))
        self.assertFalse(self.downloader._is_git_target("https://example.com/document.pdf"))
        self.assertFalse(self.downloader._is_git_target("https://example.com/archive.zip"))

    @patch("subprocess.run")
    def test_git_clone_dispatch(self, mock_subproc):
        """Git URLs trigger subprocess clone commands."""
        mock_subproc.return_value = MagicMock(returncode=0, stderr="")
        with tempfile.TemporaryDirectory() as tmpdir:
            res = self.downloader.download("https://github.com/torvalds/linux.git", destination=tmpdir, show_progress=False)
            self.assertTrue(res.success)
            self.assertEqual(res.target_type, "repo")
            mock_subproc.assert_called_once()
            args = mock_subproc.call_args[0][0]
            self.assertEqual(args[0], "git")
            self.assertEqual(args[1], "clone")

    def test_cross_platform_app_alias_resolution(self):
        """Applications resolve to known package aliases."""
        self.assertIn("vscode", self.downloader.APP_ALIASES)
        self.assertEqual(self.downloader.APP_ALIASES["vscode"]["win"], "Microsoft.VisualStudioCode")
        self.assertEqual(self.downloader.APP_ALIASES["vscode"]["mac"], "visual-studio-code")
        self.assertEqual(self.downloader.APP_ALIASES["vscode"]["linux"], "code")

        self.assertIn("chrome", self.downloader.APP_ALIASES)
        self.assertEqual(self.downloader.APP_ALIASES["chrome"]["win"], "Google.Chrome")

    @patch("operations.downloader.urlopen")
    def test_file_download_with_sha256(self, mock_urlopen):
        """Direct file streaming computes SHA-256 and handles content headers."""
        fake_content = b"NeuroShell Test File Payload 1234567890"
        mock_resp = MagicMock()
        mock_resp.headers = {
            "Content-Length": str(len(fake_content)),
            "Content-Disposition": 'attachment; filename="test_doc.pdf"'
        }
        mock_resp.read.side_effect = [fake_content, b""]
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            res = self.downloader.download(
                "https://example.com/test_doc.pdf",
                destination=tmpdir,
                show_progress=False
            )
            self.assertTrue(res.success)
            self.assertEqual(res.target_type, "file")
            self.assertEqual(res.bytes_downloaded, len(fake_content))
            self.assertEqual(len(res.sha256), 64)
            self.assertTrue(res.destination.exists())


class TestWebScraper(unittest.TestCase):
    """Test suite for multi-site web scraping and extraction engine."""

    def setUp(self):
        self.scraper = WebScraper()
        self.sample_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Test Page</title></head>
        <body>
            <nav><a href="/home">Home</a></nav>
            <h1>Main Article Heading</h1>
            <p>This is the first paragraph with important text.</p>
            <table id="data">
                <thead>
                    <tr><th>Name</th><th>Score</th><th>Status</th></tr>
                </thead>
                <tbody>
                    <tr><td>Alice</td><td>95</td><td>Pass</td></tr>
                    <tr><td>Bob</td><td>88</td><td>Pass</td></tr>
                </tbody>
            </table>
            <div class="downloads">
                <a href="https://example.com/report.pdf">Download PDF Report</a>
                <a href="https://example.com/archive.zip">Download ZIP</a>
                <a href="https://other.org/page">External Link</a>
            </div>
            <footer>Copyright 2026</footer>
        </body>
        </html>
        """

    def test_clean_text_extractor(self):
        """CleanTextExtractor extracts core content while omitting boilerplate."""
        extractor = CleanTextExtractor()
        extractor.feed(self.sample_html)
        text = extractor.get_markdown()

        self.assertIn("Main Article Heading", text)
        self.assertIn("This is the first paragraph", text)
        # Nav and footer tags should be excluded
        self.assertNotIn("Home", text)
        self.assertNotIn("Copyright 2026", text)

    def test_table_extractor(self):
        """TableExtractor converts HTML tables into ScrapedTable records."""
        extractor = TableExtractor()
        extractor.feed(self.sample_html)
        tables = extractor.tables

        self.assertEqual(len(tables), 1)
        tbl = tables[0]
        self.assertEqual(tbl.headers, ["Name", "Score", "Status"])
        self.assertEqual(len(tbl.rows), 2)
        self.assertEqual(tbl.rows[0], ["Alice", "95", "Pass"])
        self.assertEqual(tbl.rows[1], ["Bob", "88", "Pass"])

        dicts = tbl.to_dicts()
        self.assertEqual(len(dicts), 2)
        self.assertEqual(dicts[0]["Name"], "Alice")
        self.assertEqual(dicts[1]["Score"], "88")

    def test_link_extractor_document_filtering(self):
        """LinkExtractor identifies URLs and flags downloadable documents."""
        extractor = LinkExtractor(base_url="https://example.com")
        extractor.feed(self.sample_html)

        self.assertTrue(len(extractor.links) >= 3)
        docs = [link for link in extractor.links if link.is_document]
        self.assertEqual(len(docs), 2)
        doc_urls = [d.url for d in docs]
        self.assertIn("https://example.com/report.pdf", doc_urls)
        self.assertIn("https://example.com/archive.zip", doc_urls)

    @patch.object(WebScraper, "fetch_raw_html")
    def test_single_url_scrape(self, mock_fetch):
        """Single URL scraping pipeline correctly populates PageScrapeResult."""
        mock_fetch.return_value = (self.sample_html, 200)

        result = self.scraper.scrape_url("https://example.com/test", mode="all")
        self.assertEqual(result.url, "https://example.com/test")
        self.assertEqual(result.title, "Test Page")
        self.assertIn("Main Article Heading", result.markdown_content)
        self.assertEqual(len(result.tables), 1)
        self.assertEqual(len(result.links), 4)

    @patch.object(WebScraper, "fetch_raw_html")
    def test_concurrent_multi_url_scrape(self, mock_fetch):
        """Multi-site scraping runs concurrently across worker threads."""
        mock_fetch.return_value = (self.sample_html, 200)

        urls = ["https://example.com/site1", "https://example.com/site2", "https://example.com/site3"]
        results = self.scraper.scrape_multi(urls, max_workers=3)
        self.assertEqual(len(results), 3)
        result_urls = {r.url for r in results}
        for u in urls:
            self.assertIn(u, result_urls)


class TestIntelligenceTranslationDynamicIntents(unittest.TestCase):
    """Test suite ensuring natural language download and scrape intents resolve dynamically."""

    def setUp(self):
        self.llm = MagicMock()
        self.context = MagicMock()
        self.history = MagicMock()
        self.context.get_context_summary.return_value = "os=Windows"
        self.history.search_commands.return_value = []
        self.history.get_recent.return_value = []
        self.translator = Translator(self.llm, self.context, self.history)

    def test_file_download_intent_translation(self):
        """NL prompts for downloading files route directly to operations.downloader."""
        prompt = "download file from https://example.com/papers/research.pdf"
        res = self.translator.translate(prompt)
        self.assertTrue(res.has_command)
        self.assertIn("operations.downloader", res.command)
        self.assertIn("https://example.com/papers/research.pdf", res.command)

    def test_repo_download_intent_translation(self):
        """NL prompts for downloading git repositories route to operations.downloader."""
        prompt = "download git repo https://github.com/torvalds/linux"
        res = self.translator.translate(prompt)
        self.assertTrue(res.has_command)
        self.assertIn("operations.downloader", res.command)
        self.assertIn("https://github.com/torvalds/linux", res.command)

    def test_app_install_intent_translation(self):
        """NL prompts for downloading terminal/desktop applications route to app installer."""
        prompt = "download app vscode"
        res = self.translator.translate(prompt)
        self.assertTrue(res.has_command)
        self.assertIn("operations.downloader", res.command)
        self.assertIn("vscode", res.command)

    def test_web_scrape_intent_translation(self):
        """NL prompts for scraping websites route to operations.scraper."""
        prompt = "scrape data from https://news.ycombinator.com"
        res = self.translator.translate(prompt)
        self.assertTrue(res.has_command)
        self.assertIn("operations.scraper", res.command)
        self.assertIn("https://news.ycombinator.com", res.command)

    def test_table_scraping_intent_translation(self):
        """NL prompts for extracting tables route to scraper with --mode tables."""
        prompt = "extract tables from https://en.wikipedia.org/wiki/List_of_countries"
        res = self.translator.translate(prompt)
        self.assertTrue(res.has_command)
        self.assertIn("operations.scraper", res.command)
        self.assertIn("--mode tables", res.command)
        self.assertIn("https://en.wikipedia.org/wiki/List_of_countries", res.command)


if __name__ == "__main__":
    unittest.main()
