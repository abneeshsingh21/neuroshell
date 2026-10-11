# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Test Suite for NeuroShell Universal App Uninstaller, Asset Deleter Subsystem,
and Plain-English Error Shield with Actionable Smart Auto-Fixes.
"""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from intelligence.smart_open import SmartOpenEngine
from operations.deleter import ASSET_CATEGORIES, AssetDeleter, DeleteSummary
from operations.uninstaller import InstalledApp, UniversalUninstaller


class TestUniversalUninstaller:
    """Validates installed application discovery and uninstallation pipeline."""

    def test_discover_installed_apps_returns_list(self):
        uninstaller = UniversalUninstaller()
        apps = uninstaller.discover_installed_apps()
        assert isinstance(apps, list)
        # Verify app structures
        for app in apps[:10]:
            assert isinstance(app, InstalledApp)
            assert isinstance(app.name, str)
            assert len(app.name) > 0
            assert isinstance(app.source, str)

    def test_discover_with_query_filtering(self):
        uninstaller = UniversalUninstaller()
        # Query known system or common terms
        query_results = uninstaller.discover_installed_apps("windows")
        assert isinstance(query_results, list)
        for app in query_results:
            assert "windows" in app.name.lower() or "windows" in app.publisher.lower()

    def test_print_app_list_runs_without_exceptions(self, capsys):
        uninstaller = UniversalUninstaller()
        uninstaller.print_app_list("test_non_existent_app_xyz_123")
        captured = capsys.readouterr()
        assert "No installed software found" in captured.out or "Installed Software" in captured.out

    @patch("subprocess.run")
    def test_uninstall_execution_flow(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        uninstaller = UniversalUninstaller()
        
        # Inject dummy app into discovery
        dummy_app = InstalledApp(
            name="DummyTestApp",
            version="1.0.0",
            publisher="TestOrg",
            source="TestRegistry",
            uninstall_command="dummy_uninstall.exe /S",
            is_silent_capable=True,
        )
        with patch.object(uninstaller, "discover_installed_apps", return_value=[dummy_app]):
            with patch("builtins.input", return_value="y"):
                res = uninstaller.uninstall("DummyTestApp", silent=True)
                assert res.success is True
                assert res.app_name == "DummyTestApp"
                assert mock_run.called


class TestAssetDeleterSubsystem:
    """Validates multi-format asset deletion, semantic categories, and 4-layer Safety Shield."""

    @pytest.fixture
    def test_sandbox(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="neuroshell_delete_test_"))
        trash_dir = temp_dir / ".neuroshell" / "trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        
        # Create test assets
        (temp_dir / "photo1.png").write_bytes(b"dummy png content 12345")
        (temp_dir / "photo2.jpg").write_bytes(b"dummy jpg content 67890")
        (temp_dir / "video1.mp4").write_bytes(b"dummy mp4 video stream")
        (temp_dir / "clip.mkv").write_bytes(b"dummy mkv video content")
        (temp_dir / "data.tmp").write_text("temporary debug data")
        (temp_dir / "build.log").write_text("build system logs")
        (temp_dir / "keep_code.py").write_text("print('do not delete me')")

        sub_folder = temp_dir / "nested_cache"
        sub_folder.mkdir()
        (sub_folder / "cached_item.cache").write_text("cache entry")

        yield temp_dir, trash_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_safety_shield_blocks_protected_system_paths(self):
        deleter = AssetDeleter()
        # Protected root paths
        assert deleter.is_protected("C:\\") is True
        assert deleter.is_protected("C:/") is True
        assert deleter.is_protected("C:\\Windows") is True
        assert deleter.is_protected("C:\\Windows\\System32") is True
        assert deleter.is_protected("/") is True
        assert deleter.is_protected("/etc") is True
        assert deleter.is_protected("/usr") is True

        # Attempting to delete protected path must fail and block
        summary = deleter.delete("C:\\Windows")
        assert summary.success is False
        assert len(summary.deleted_paths) == 0

    def test_delete_semantic_category_images(self, test_sandbox):
        sandbox, trash = test_sandbox
        deleter = AssetDeleter(cwd=sandbox)

        summary = deleter.delete("images", force=False)
        assert summary.success is True
        assert summary.items_deleted == 2  # photo1.png and photo2.jpg
        assert not (sandbox / "photo1.png").exists()
        assert not (sandbox / "photo2.jpg").exists()
        assert (sandbox / "video1.mp4").exists()
        assert (sandbox / "keep_code.py").exists()

    def test_delete_semantic_category_videos(self, test_sandbox):
        sandbox, trash = test_sandbox
        deleter = AssetDeleter(cwd=sandbox)

        summary = deleter.delete("videos", force=False)
        assert summary.success is True
        assert summary.items_deleted == 2  # video1.mp4 and clip.mkv
        assert not (sandbox / "video1.mp4").exists()
        assert not (sandbox / "clip.mkv").exists()
        assert (sandbox / "photo1.png").exists()

    def test_delete_single_file_and_directory(self, test_sandbox):
        sandbox, trash = test_sandbox
        deleter = AssetDeleter(cwd=sandbox)

        # Delete single file
        summary_file = deleter.delete("data.tmp", force=False)
        assert summary_file.success is True
        assert not (sandbox / "data.tmp").exists()

        # Delete directory
        summary_dir = deleter.delete("nested_cache", force=False)
        assert summary_dir.success is True
        assert not (sandbox / "nested_cache").exists()

    def test_dry_run_does_not_remove_files(self, test_sandbox):
        sandbox, trash = test_sandbox
        deleter = AssetDeleter(cwd=sandbox)

        summary = deleter.delete("images", dry_run=True)
        assert summary.success is True
        assert summary.items_deleted == 2
        # Files must still exist on disk after dry run
        assert (sandbox / "photo1.png").exists()
        assert (sandbox / "photo2.jpg").exists()


class TestSmartOpenEngineEnhancements:
    """Validates dynamic open capabilities for applications, browsers, and folders."""

    def test_resolve_chrome_browser(self):
        engine = SmartOpenEngine()
        res = engine.try_resolve("open chrome browser")
        assert res is not None
        assert "chrome" in res.command.lower()

    def test_resolve_vscode(self):
        engine = SmartOpenEngine()
        res = engine.try_resolve("open vscode")
        assert res is not None
        assert "code" in res.command.lower()

    def test_resolve_notepad(self):
        engine = SmartOpenEngine()
        res = engine.try_resolve("open notepad")
        assert res is not None
        assert "notepad" in res.command.lower()

    def test_resolve_explorer_cwd(self):
        engine = SmartOpenEngine()
        res = engine.try_resolve("open .")
        assert res is not None
        assert res.command != ""
