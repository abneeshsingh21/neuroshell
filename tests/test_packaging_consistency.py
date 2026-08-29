# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
"""Tests for scripts/check_packaging_consistency.py — the cross-manifest
version/digest gate that keeps brew, winget, scoop, AUR, Debian, PyPI and the
native header from drifting apart (they did before Phase 10: the Homebrew
formula sat at 5.8.0 while the code shipped 5.17.0).

The first test runs the gate against the real repo and is the CI tripwire;
the rest exercise drift detection, pin policy, and release-time rendering on
temporary copies.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check_packaging_consistency.py"


def run_gate(cwd):
    return subprocess.run([sys.executable, str(SCRIPT), "check", "--root", str(cwd)],
                          capture_output=True, text=True, cwd=str(cwd))


class TestRepoIsConsistent:
    def test_gate_passes_on_repo(self):
        r = run_gate(REPO)
        assert r.returncode == 0, r.stderr
        m = re.search(r"agree on (\d+\.\d+\.\d+)", r.stdout)
        assert m, r.stdout
        assert m.group(1) == "5.18.0"

    def test_gate_sees_every_declared_source(self):
        r = run_gate(REPO)
        n = int(re.search(r"OK: (\d+) version declarations", r.stdout).group(1))
        # __version__, pyproject, version.hpp, version.hpp[macros], Formula,
        # winget (2 files), scoop, AUR, debian control, debian changelog,
        # CHANGELOG top entry
        assert n >= 12


class TestDriftDetection:
    @pytest.fixture()
    def repo_copy(self, tmp_path):
        """Shallow copy of the manifest files (no .git, no sources needed)."""
        for rel in ("__version__.py", "pyproject.toml", "CHANGELOG.md",
                    "cpp_engine/launcher/version.hpp", "Formula/neuroshell.rb",
                    "packaging/winget/neuroshell.yaml",
                    "packaging/winget/neuroshell.installer.yaml",
                    "packaging/winget/neuroshell.locale.yaml",
                    "packaging/scoop/neuroshell.json",
                    "packaging/aur/PKGBUILD",
                    "packaging/debian/control",
                    "packaging/debian/changelog",
                    "packaging/debian/copyright"):
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((REPO / rel).read_text())
        return tmp_path

    def test_version_drift_fails(self, repo_copy):
        p = repo_copy / "__version__.py"
        p.write_text(p.read_text().replace("5.18.0", "5.19.0"))
        r = run_gate(repo_copy)
        assert r.returncode == 1
        assert "__version__.py: version 5.19.0" in r.stderr

    def test_header_macro_drift_fails(self, repo_copy):
        p = repo_copy / "cpp_engine/launcher/version.hpp"
        p.write_text(p.read_text().replace(
            "#define NEUROSHELL_VERSION_MINOR 18",
            "#define NEUROSHELL_VERSION_MINOR 19"))
        r = run_gate(repo_copy)
        assert r.returncode == 1
        assert "macros" in r.stderr

    def test_floating_latest_url_fails(self, repo_copy):
        p = repo_copy / "packaging/scoop/neuroshell.json"
        data = json.loads(p.read_text())
        data["architecture"]["64bit"]["url"] = \
            "https://github.com/x/y/releases/latest/download/z.zip"
        p.write_text(json.dumps(data))
        r = run_gate(repo_copy)
        assert r.returncode == 1
        assert "releases/latest" in r.stderr

    def test_bad_digest_pin_fails(self, repo_copy):
        p = repo_copy / "packaging/winget/neuroshell.installer.yaml"
        p.write_text(p.read_text().replace(
            "InstallerSha256: REPLACE_AT_RELEASE",
            "InstallerSha256: sha256-of-trust-me"))
        r = run_gate(repo_copy)
        assert r.returncode == 1
        assert "neither a sha256 nor the REPLACE_AT_RELEASE sentinel" in r.stderr

    def test_real_sha256_pin_accepted(self, repo_copy):
        p = repo_copy / "packaging/winget/neuroshell.installer.yaml"
        p.write_text(p.read_text().replace(
            "InstallerSha256: REPLACE_AT_RELEASE",
            "InstallerSha256: " + "ab" * 32))
        assert run_gate(repo_copy).returncode == 0

    def test_changelog_lag_fails(self, repo_copy):
        """The bug this gate originally caught: CHANGELOG top entry behind."""
        p = repo_copy / "CHANGELOG.md"
        p.write_text("## [5.17.0] — old\n\nstuff\n\n" + p.read_text())
        r = run_gate(repo_copy)
        assert r.returncode == 1
        assert "CHANGELOG.md (top entry)" in r.stderr


class TestRender:
    @pytest.fixture()
    def render_env(self, tmp_path):
        for rel in ("Formula/neuroshell.rb",
                    "packaging/winget/neuroshell.installer.yaml",
                    "packaging/scoop/neuroshell.json",
                    "packaging/aur/PKGBUILD"):
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((REPO / rel).read_text())
        digest = "cd" * 32
        sums = tmp_path / "checksums.txt"
        sums.write_text(
            f"{digest}  NeuroShell-windows-x64.zip\n"
            f"{digest}  NeuroShell-linux-x86_64.tar.gz\n"
            f"{digest}  NeuroShell-linux-arm64.tar.gz\n"
            f"{digest}  NeuroShell-macos-universal.tar.gz\n")
        return tmp_path, sums, digest

    def test_render_resolves_sentinels(self, render_env):
        root, sums, digest = render_env
        out = root / "dist" / "packaging"
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "render", "--root", str(root),
             "--sha256-file", str(sums), "--tag", "v5.18.0",
             "--out-dir", str(out)],
            capture_output=True, text=True, cwd=str(root))
        assert r.returncode == 0, r.stderr
        rendered = (out / "packaging" / "scoop" / "neuroshell.json").read_text()
        assert digest in rendered and "REPLACE_AT_RELEASE" not in rendered
        winget = (out / "packaging" / "winget" / "neuroshell.installer.yaml").read_text()
        assert digest in winget
        # repo templates untouched
        assert "REPLACE_AT_RELEASE" in (root / "packaging/scoop/neuroshell.json").read_text()

    def test_render_fails_on_missing_asset_digest(self, render_env):
        root, sums, _ = render_env
        sums.write_text("ab" * 32 + "  something-else.bin\n")
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "render", "--root", str(root),
             "--sha256-file", str(sums), "--tag", "v5.18.0",
             "--out-dir", str(root / "dist" / "packaging")],
            capture_output=True, text=True, cwd=str(root))
        assert r.returncode == 1
        assert "unresolved sentinels" in r.stderr

    def test_render_fails_on_wrong_tag_urls(self, render_env):
        root, sums, _ = render_env
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "render", "--root", str(root),
             "--sha256-file", str(sums), "--tag", "v5.99.0",
             "--out-dir", str(root / "dist" / "packaging")],
            capture_output=True, text=True, cwd=str(root))
        assert r.returncode == 1
        assert "not pinned to the release tag" in r.stderr

    def test_render_rejects_malformed_checksums(self, render_env):
        root, sums, _ = render_env
        sums.write_text("nothex  file.bin\n")
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "render", "--root", str(root),
             "--sha256-file", str(sums), "--tag", "v5.18.0",
             "--out-dir", str(root / "out")],
            capture_output=True, text=True, cwd=str(root))
        assert r.returncode == 2
        assert "bad checksums line" in r.stderr


class TestBuildDebScript:
    def test_version_comes_from_single_source(self):
        """build_deb.sh must not carry its own hardcoded VERSION ever again."""
        text = (REPO / "scripts" / "build_deb.sh").read_text()
        assert "VERSION=" in text
        assert not re.search(r'^VERSION="5\.\d+\.\d+"', text, re.MULTILINE), \
            "build_deb.sh must read the version from __version__.py"
        assert "packaging/debian/control" in text
        assert "gzip -9n" in text  # reproducible changelog
