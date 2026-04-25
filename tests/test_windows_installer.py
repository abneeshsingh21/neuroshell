"""Tests for Windows MSI installer script generation."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestWindowsInstaller(unittest.TestCase):
    def test_render_wxs_contains_expected_fields(self):
        from scripts.build_windows_msi import render_wxs

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            exe = root / "NeuroShell.exe"
            exe.write_bytes(b"fake")
            wxs = render_wxs(exe_path=exe, wxs_path=root / "installer.wxs", version="4.2.0")

            content = wxs.read_text(encoding="utf-8")
            self.assertIn("Package", content)
            self.assertIn('Version="4.2.0"', content)
            self.assertIn("NeuroShell", content)
            # render_wxs uses exe.parent.resolve().as_posix() + "/**" as glob
            self.assertIn(exe.parent.resolve().as_posix(), content)
