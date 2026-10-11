# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Test Suite for Terminal Markdown Presentation Engine and Universal Dynamic Open Architecture.
Verifies HTML tag sanitization, project card formatting, badge rendering,
dynamic application discovery via PATH/Registry, and universal open routing.
"""

from __future__ import annotations

import os
import shutil
import unittest
from unittest.mock import MagicMock, patch

from intelligence.smart_open import SmartOpenEngine, OpenResult
from ui.markdown_renderer import TerminalMarkdownRenderer


class TestTerminalMarkdownRenderer(unittest.TestCase):
    """Verifies that markdown and HTML documents are rendered cleanly in terminal."""

    def setUp(self):
        self.renderer = TerminalMarkdownRenderer(target_width=80)

    def test_strip_html_containers_and_breaks(self):
        raw = '<div align="center"><p>Hello World</p><br/><br><span>Subtext</span></div>'
        rendered = self.renderer.render(raw)
        self.assertNotIn("<div", rendered)
        self.assertNotIn("</div>", rendered)
        self.assertNotIn("<br", rendered)
        self.assertIn("Hello World", rendered)
        self.assertIn("Subtext", rendered)

    def test_kbd_badge_rendering(self):
        raw = "Tags: <kbd>Python</kbd> &nbsp; <kbd>FastAPI</kbd>"
        rendered = self.renderer.render(raw)
        self.assertNotIn("<kbd>", rendered)
        self.assertIn("Python", rendered)
        self.assertIn("FastAPI", rendered)

    def test_shield_badge_image_conversion(self):
        raw = '<a href="https://linkedin.com/in/user"><img src="https://img.shields.io/badge/LinkedIn-000000?style=for-the-badge" alt="LinkedIn" /></a>'
        rendered = self.renderer.render(raw)
        self.assertNotIn("<img", rendered)
        self.assertNotIn("<a", rendered)
        self.assertIn("LinkedIn", rendered)

    def test_project_card_rendering(self):
        table_raw = (
            "| 🧠 [NeuroShell — Intelligent AI Terminal](https://github.com/user/neuroshell) |\n"
            "| :--- |\n"
            "| Spearheaded development of hybrid C++ and Python engine. |\n"
            "| <kbd>C++ / Python</kbd> &nbsp; <kbd>Systems Architecture</kbd> |\n"
        )
        rendered = self.renderer.render(table_raw)
        # Verify box borders are present
        self.assertIn("╭", rendered)
        self.assertIn("╰", rendered)
        self.assertIn("NeuroShell — Intelligent AI Terminal", rendered)
        self.assertIn("https://github.com/user/neuroshell", rendered)
        self.assertIn("Spearheaded development", rendered)

    def test_blockquote_callout_rendering(self):
        quote_raw = "> *My engineering philosophy is precision through abstraction.*"
        rendered = self.renderer.render(quote_raw)
        self.assertIn("│", rendered)
        self.assertIn("My engineering philosophy", rendered)

    def test_github_metadata_header_rendering(self):
        meta_raw = "name:\tabneeshsingh21/abneeshsingh21\ndescription:\tPortfolio\n--\nContent here"
        rendered = self.renderer.render(meta_raw)
        self.assertIn("📖 Document: abneeshsingh21/abneeshsingh21", rendered)
        self.assertIn("Content here", rendered)


class TestUniversalDynamicOpen(unittest.TestCase):
    """Verifies that open commands resolve dynamically from all perspectives with zero hardcoding."""

    def setUp(self):
        self.engine = SmartOpenEngine()

    def test_open_chrome_browser_alias_cleaning(self):
        res = self.engine.try_resolve("open chrome browser")
        self.assertIsNotNone(res)
        self.assertEqual(res.target_type, "app")
        self.assertIn("chrome", res.command.lower())

    def test_open_brave_browser_alias_cleaning(self):
        res = self.engine.try_resolve("open brave browser")
        self.assertIsNotNone(res)
        self.assertEqual(res.target_type, "app")
        self.assertIn("brave", res.command.lower())

    def test_open_dynamic_path_binary(self):
        with patch("shutil.which", return_value="C:\\tools\\custom_app.exe"):
            res = self.engine.try_resolve("open custom_app")
            self.assertIsNotNone(res)
            self.assertEqual(res.target_type, "app")
            self.assertIn("custom_app", res.command)

    def test_open_dynamic_windows_registry_app_path(self):
        with patch.object(self.engine, "_query_windows_app_paths", return_value="C:\\Program Files\\Blender\\blender.exe"):
            with patch("shutil.which", return_value=None):
                res = self.engine.try_resolve("open blender")
                self.assertIsNotNone(res)
                self.assertEqual(res.target_type, "app")
                self.assertIn("blender", res.command)

    def test_open_universal_fallback_process_manager(self):
        with patch("shutil.which", return_value=None):
            with patch.object(self.engine, "_query_windows_app_paths", return_value=None):
                res = self.engine.try_resolve("open some_new_editor")
                self.assertIsNotNone(res)
                self.assertEqual(res.target_type, "app")
                self.assertIn("some_new_editor", res.command)

    def test_open_url_domains_and_ports(self):
        res1 = self.engine.try_resolve("open google.com")
        self.assertIsNotNone(res1)
        self.assertEqual(res1.target_type, "url")
        self.assertIn("https://google.com", res1.command)

        res2 = self.engine.try_resolve("open localhost:3000")
        self.assertIsNotNone(res2)
        self.assertEqual(res2.target_type, "url")
        self.assertIn("http://localhost:3000", res2.command)

    def test_open_current_directory_and_folders(self):
        res = self.engine.try_resolve("open .")
        self.assertIsNotNone(res)
        self.assertEqual(res.target_type, "folder")

        res_dl = self.engine.try_resolve("open downloads")
        self.assertIsNotNone(res_dl)
        self.assertEqual(res_dl.target_type, "folder")


if __name__ == "__main__":
    unittest.main()
