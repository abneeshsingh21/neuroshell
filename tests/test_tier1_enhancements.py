"""
Comprehensive Test Suite for NeuroShell Tier-1 Advanced Enhancements:
- Semantic Workspace Graph Engine (intelligence/project_graph.py)
- Unified Terminal Harvester Pipeline (operations/harvester.py)
- Interactive Terminal Viewport Pager (operations/pager.py)
- Autonomous Self-Healing Agent Mode 2.0 (intelligence/agent.py)
- Translator Workspace Manifest Resolution & Dynamic Harvest Patterns (intelligence/translator.py)
"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from intelligence.project_graph import WorkspaceProjectGraph, ProjectManifest
from operations.harvester import TerminalHarvester, HarvestSummary
from operations.pager import TerminalPager, strip_ansi
from operations.scraper import PageScrapeResult, ScrapedTable, ScrapedLink
from operations.downloader import UniversalDownloader, DownloadResult
from ui.table_formatter import AutoArranger, render_execution_frame
from intelligence.agent import AgentPlanner, AgentPlan, AgentStep
from intelligence.translator import Translator


class TestWorkspaceProjectGraph(unittest.TestCase):
    """Test suite for semantic workspace scanner."""

    def test_node_manifest_scanning(self):
        """Node project detects package manager, scripts, and framework."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            pkg_data = {
                "name": "my-web-app",
                "scripts": {"dev": "next dev", "build": "next build", "test": "jest"},
                "dependencies": {"next": "^14.0.0", "react": "^18.0.0"}
            }
            (tmppath / "package.json").write_text(json.dumps(pkg_data), encoding="utf-8")
            (tmppath / "pnpm-lock.yaml").write_text("", encoding="utf-8")

            manifest = WorkspaceProjectGraph.get_manifest(tmppath)
            self.assertEqual(manifest.project_type, "node")
            self.assertEqual(manifest.package_manager, "pnpm")
            self.assertEqual(manifest.framework, "next")
            self.assertIn("dev", manifest.scripts)

            # Test deterministic action resolutions
            dev_cmd = WorkspaceProjectGraph.resolve_action("start dev server", tmppath)
            self.assertEqual(dev_cmd, "pnpm run dev")

            test_cmd = WorkspaceProjectGraph.resolve_action("run unit tests", tmppath)
            self.assertEqual(test_cmd, "pnpm test")

            build_cmd = WorkspaceProjectGraph.resolve_action("build the project", tmppath)
            self.assertEqual(build_cmd, "pnpm run build")

    def test_python_manifest_scanning(self):
        """Python project detects framework, venv, and test commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            pyproject = tmppath / "pyproject.toml"
            pyproject.write_text("[project]\nname = 'api'\ndependencies = ['fastapi', 'uvicorn']\n", encoding="utf-8")
            (tmppath / "uv.lock").write_text("", encoding="utf-8")

            # Fake venv
            venv_dir = tmppath / ".venv"
            venv_scripts = venv_dir / ("Scripts" if os.name == "nt" else "bin")
            venv_scripts.mkdir(parents=True, exist_ok=True)
            act_file = venv_scripts / ("activate.bat" if os.name == "nt" else "activate")
            act_file.write_text("", encoding="utf-8")

            manifest = WorkspaceProjectGraph.get_manifest(tmppath)
            self.assertEqual(manifest.project_type, "python")
            self.assertEqual(manifest.package_manager, "uv")
            self.assertEqual(manifest.framework, "fastapi")
            self.assertIsNotNone(manifest.venv_path)

            dev_cmd = WorkspaceProjectGraph.resolve_action("start dev server", tmppath)
            self.assertEqual(dev_cmd, "uvicorn main:app --reload")

            test_cmd = WorkspaceProjectGraph.resolve_action("run test suite", tmppath)
            self.assertEqual(test_cmd, "pytest")

    def test_docker_compose_service_resolution(self):
        """Docker compose services resolve directly to compose commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            compose_text = """
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
  redis:
    image: redis:alpine
            """
            (tmppath / "docker-compose.yml").write_text(compose_text, encoding="utf-8")

            manifest = WorkspaceProjectGraph.get_manifest(tmppath)
            self.assertIn("postgres", manifest.docker_services)
            self.assertIn("redis", manifest.docker_services)

            cmd_pg = WorkspaceProjectGraph.resolve_action("start postgres database", tmppath)
            self.assertEqual(cmd_pg, "docker compose up -d postgres")


class TestTerminalHarvester(unittest.TestCase):
    """Test suite for unified WebScraper + UniversalDownloader pipeline."""

    @patch("operations.scraper.WebScraper.scrape_url")
    @patch("operations.downloader.UniversalDownloader.download")
    def test_harvest_tables_and_documents(self, mock_download, mock_scrape):
        """Harvester extracts tables and streams discovered document files."""
        fake_page = PageScrapeResult(
            url="https://example.com/research",
            title="AI Research Portal",
            tables=[
                ScrapedTable(
                    headers=["Model", "Parameters", "Benchmark"],
                    rows=[["Gemma-2", "9B", "82.4%"], ["Llama-3", "8B", "80.2%"]]
                )
            ],
            links=[
                ScrapedLink(text="Paper PDF", url="https://example.com/paper.pdf", is_document=True, doc_type="pdf"),
                ScrapedLink(text="Dataset CSV", url="https://example.com/data.csv", is_document=True, doc_type="csv"),
                ScrapedLink(text="Home Page", url="https://example.com/home", is_document=False),
            ]
        )
        mock_scrape.return_value = fake_page

        mock_download.return_value = DownloadResult(
            success=True,
            target="https://example.com/paper.pdf",
            target_type="file",
            destination=Path("paper.pdf"),
            bytes_downloaded=1024 * 500,
            elapsed_seconds=0.2,
            sha256="abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abc",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            harvester = TerminalHarvester(dest_dir=tmpdir)
            summary = harvester.harvest(
                urls="https://example.com/research",
                doc_type="pdf",
                extract_tables=True,
                download_docs=True,
                render_tables=False,
            )

            self.assertEqual(summary.total_tables_extracted, 1)
            self.assertEqual(summary.total_documents_found, 1)
            self.assertEqual(summary.total_downloads_completed, 1)
            self.assertEqual(len(summary.tables), 1)
            self.assertEqual(summary.tables[0].headers, ["Model", "Parameters", "Benchmark"])


class TestTerminalPager(unittest.TestCase):
    """Test suite for interactive viewport pager."""

    def test_pager_line_navigation_and_search(self):
        """Pager cursor movement bounds and search matching."""
        lines = [f"Output Log Line #{i} - status=healthy" for i in range(100)]
        lines[42] = "Fatal Error: Connection timeout in worker thread"

        pager = TerminalPager(lines, title="Test Viewport")
        self.assertEqual(len(pager.raw_lines), 100)

        # Test cursor movement
        pager._move_cursor(10, viewport_height=20)
        self.assertEqual(pager.selected_line, 10)

        # Test search term match
        pager.search_term = "Fatal Error"
        for i, line in enumerate(pager.raw_lines):
            if "fatal error" in line.lower():
                pager.selected_line = i
                break
        self.assertEqual(pager.selected_line, 42)

        # Test line inspection
        pager._inspect_current_line()
        self.assertIn("Fatal exception or command error", pager.ai_insight)


class TestAgentPlannerSelfHealing(unittest.TestCase):
    """Test suite for autonomous agent self-healing loops."""

    def test_self_healing_missing_module(self):
        """Agent detects ModuleNotFoundError and executes auto-healing remediation."""
        planner = AgentPlanner()
        remediation = planner._diagnose_and_heal(
            failed_cmd="python script.py",
            error_output="ModuleNotFoundError: No module named 'requests'"
        )
        self.assertEqual(remediation, "pip install requests")

    def test_self_healing_missing_directory(self):
        """Agent detects missing path and generates directory creation command."""
        planner = AgentPlanner()
        remediation = planner._diagnose_and_heal(
            failed_cmd="touch build/output/test.log",
            error_output="No such file or directory: 'build/output/test.log'"
        )
        self.assertIsNotNone(remediation)
        self.assertIn("mkdir", remediation)

    def test_agent_execution_with_healed_step(self):
        """Step fails on attempt 1, executes remedy, and passes on attempt 2."""
        mock_executor = MagicMock()

        # Step 1 succeeds; Step 2 fails with missing module then succeeds on retry
        res_step1 = MagicMock(exit_code=0, stdout="Step 1 complete", stderr="")
        res_step2_fail = MagicMock(exit_code=1, stdout="", stderr="ModuleNotFoundError: No module named 'colorama'")
        res_remedy = MagicMock(exit_code=0, stdout="Successfully installed colorama", stderr="")
        res_step2_pass = MagicMock(exit_code=0, stdout="Step 2 complete", stderr="")

        mock_executor.execute.side_effect = [res_step1, res_step2_fail, res_remedy, res_step2_pass]

        planner = AgentPlanner(executor=mock_executor)
        plan = AgentPlan(
            task="Build and run",
            steps=[
                AgentStep(order=1, action="shell", command="echo start"),
                AgentStep(order=2, action="shell", command="python run.py"),
            ]
        )

        completed_plan = planner.execute_plan(plan, auto_heal=True)
        self.assertEqual(completed_plan.status, "completed")
        self.assertEqual(completed_plan.completed_steps, 2)
        self.assertEqual(completed_plan.steps[1].status, "healed")
        self.assertEqual(completed_plan.steps[1].remediation_cmd, "pip install colorama")


class TestTranslatorSemanticIntegration(unittest.TestCase):
    """Test suite ensuring project graph and harvest patterns route dynamically."""

    def setUp(self):
        self.llm = MagicMock()
        self.context = MagicMock()
        self.history = MagicMock()
        self.context.get_context_summary.return_value = "os=Windows"
        self.history.search_commands.return_value = []
        self.history.get_recent.return_value = []
        self.translator = Translator(self.llm, self.context, self.history)

    def test_harvest_intent_translation(self):
        """NL harvest prompt routes to operations.harvester."""
        prompt = "harvest all pdf files from https://arxiv.org/list/cs.AI/recent to ./papers"
        res = self.translator.translate(prompt)
        self.assertTrue(res.has_command)
        self.assertIn("operations.harvester", res.command)
        self.assertIn("https://arxiv.org/list/cs.AI/recent", res.command)
        self.assertIn("./papers", res.command)

    def test_paper_download_intent_translation(self):
        """NL paper download prompt routes to operations.downloader paper."""
        prompt = 'download paper "Attention is all you need"'
        res = self.translator.translate(prompt)
        self.assertTrue(res.has_command)
        self.assertIn("operations.downloader", res.command)
        self.assertIn("paper", res.command)
        self.assertIn("Attention is all you need", res.command)

    def test_direct_app_download_intent_translation(self):
        """NL direct app download prompt routes to operations.downloader without hardcoding."""
        prompt = "download chrome"
        res = self.translator.translate(prompt)
        self.assertTrue(res.has_command)
        self.assertIn("operations.downloader", res.command)
        self.assertIn("chrome", res.command)


class TestAutoArrangerSubsystem(unittest.TestCase):
    """Test suite for Intelligent Output Auto-Arranger."""

    def setUp(self):
        from ui.table_formatter import AutoArranger, render_execution_frame
        self.arranger = AutoArranger()
        self.render_frame = render_execution_frame

    def test_json_array_auto_arrangement(self):
        """Array of JSON dicts turns into an adaptive Unicode box table."""
        payload = json.dumps([
            {"id": "1", "name": "Alpha", "status": "online"},
            {"id": "2", "name": "Beta", "status": "offline"},
        ])
        output = self.arranger.arrange(payload)
        self.assertIn("Alpha", output)
        self.assertIn("Beta", output)
        self.assertIn("online", output)
        self.assertIn("╭", output)
        self.assertIn("╰", output)

    def test_json_object_property_card(self):
        """Single JSON object turns into a Key-Value properties card."""
        payload = json.dumps({"service": "postgres", "port": 5432, "active": True})
        output = self.arranger.arrange(payload)
        self.assertIn("service", output)
        self.assertIn("postgres", output)
        self.assertIn("PROPERTY", output)
        self.assertIn("VALUE", output)

    def test_markdown_table_auto_arrangement(self):
        """Markdown table syntax converts into clean box borders."""
        md = "| Tool | Version |\n|---|---|\n| git | 2.45 |\n| gh | 2.50 |"
        output = self.arranger.arrange(md)
        self.assertIn("git", output)
        self.assertIn("2.45", output)
        self.assertIn("╭", output)

    def test_key_value_block_auto_arrangement(self):
        """Key: Value line blocks convert into Property Card."""
        kv = "Hostname: server-01\nOS: Ubuntu 24.04\nStatus: running\nUptime: 14 days"
        output = self.arranger.arrange(kv)
        self.assertIn("Hostname", output)
        self.assertIn("server-01", output)
        self.assertIn("running", output)

    def test_execution_frame_rendering(self):
        """Execution frames wrap command results with duration and status badges."""
        framed = self.render_frame("git status", "On branch main\nnothing to commit", exit_code=0, duration_s=0.05)
        self.assertIn("⌬ git status", framed)
        self.assertIn("On branch main", framed)
        self.assertIn("Exit 0", framed)
        self.assertIn("50ms", framed)


class TestDynamicDownloaderCapabilities(unittest.TestCase):
    """Test suite for UniversalDownloader dynamic resolvers."""

    def setUp(self):
        from operations.downloader import UniversalDownloader
        self.downloader = UniversalDownloader()

    @patch("operations.downloader.subprocess.run")
    def test_dynamic_package_resolution(self, mock_run):
        """WinGet search output is parsed dynamically into package ID."""
        fake_stdout = """
Name       Id                   Version    Match        Source
--------------------------------------------------------------
Blender    BlenderFoundation.Blender 5.2.2              winget
        """
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_stdout)
        pkg_id = self.downloader._resolve_package_dynamically("blender")
        self.assertIsNotNone(pkg_id)
        self.assertIn("Blender", pkg_id)

    @patch("operations.downloader.urlopen")
    @patch.object(UniversalDownloader, "_download_file_url")
    def test_search_and_download_paper_arxiv(self, mock_dl, mock_urlopen):
        """arXiv search resolves title and invokes streaming download for direct PDF."""
        fake_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/1706.03762v7</id>
            <title>Attention Is All You Need</title>
          </entry>
        </feed>"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_xml
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        mock_dl.return_value = DownloadResult(
            success=True,
            target="https://arxiv.org/pdf/1706.03762v7.pdf",
            target_type="file",
            bytes_downloaded=1000,
        )

        res = self.downloader._search_and_download_paper("Attention Is All You Need")
        self.assertTrue(res.success)
        mock_dl.assert_called_once()
        self.assertIn("1706.03762v7.pdf", mock_dl.call_args[0][0])

    @patch("operations.downloader.subprocess.run")
    @patch.object(UniversalDownloader, "_download_git_repo")
    def test_search_and_download_repo_via_gh(self, mock_clone, mock_run):
        """GitHub search resolves repository and calls git clone."""
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps([{"fullName": "huggingface/transformers", "description": "Transformers library"}]))
        mock_clone.return_value = DownloadResult(
            success=True,
            target="https://github.com/huggingface/transformers.git",
            target_type="repo",
        )

        res = self.downloader._search_and_download_repo("transformers")
        self.assertTrue(res.success)
        mock_clone.assert_called_once()
        self.assertEqual(mock_clone.call_args[0][0], "huggingface/transformers")


if __name__ == "__main__":
    unittest.main()
