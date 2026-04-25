"""Tests for desktop release packaging utilities."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDesktopReleaseScript(unittest.TestCase):
    def test_build_command_windows_add_data_separator(self):
        from scripts.build_desktop_release import build_command

        root = Path("C:/repo/neuroshell")
        cmd = build_command(root, root / "release/dist", root / "release/build", system_name="windows")
        joined = " ".join(str(x) for x in cmd)
        self.assertIn("assets;assets", joined)

    def test_build_command_linux_add_data_separator(self):
        from scripts.build_desktop_release import build_command

        root = Path("/repo/neuroshell")
        cmd = build_command(root, root / "release/dist", root / "release/build", system_name="linux")
        joined = " ".join(str(x) for x in cmd)
        self.assertIn("assets:assets", joined)

    def test_logo_assets_exist(self):
        repo = Path(__file__).resolve().parents[1]
        self.assertTrue((repo / "assets" / "logo.svg").exists())
        self.assertTrue((repo / "assets" / "icon.ico").exists())
        self.assertTrue((repo / "assets" / "logo.png").exists())
