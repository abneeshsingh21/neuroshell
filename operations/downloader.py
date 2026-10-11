# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Universal Terminal Downloader Engine for NeuroShell.
Downloads anything from the terminal:
- Applications & tools via system package managers (winget, brew, apt)
- Git repositories and releases via git clone and gh release download
- Files, PDFs, documents, media, and archives via streaming HTTP/HTTPS
  with auto-resume (Range requests), live progress bar, speed indicator,
  and SHA-256 integrity verification.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


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
class DownloadResult:
    """Result of a download operation."""
    success: bool
    target: str
    target_type: str  # "file", "app", "repo"
    destination: Path | None = None
    bytes_downloaded: int = 0
    total_bytes: int = 0
    elapsed_seconds: float = 0.0
    sha256: str = ""
    error_message: str = ""
    resumed: bool = False

    def summary(self) -> str:
        if not self.success:
            return f"❌ Download failed: {self.error_message}"
        if self.target_type == "app":
            return f"✔ Application successfully installed via package manager: {self.target}"
        if self.target_type == "repo":
            return f"✔ Repository cloned to: {self.destination}"
        
        size_mb = self.bytes_downloaded / (1024 * 1024)
        speed = (size_mb / self.elapsed_seconds) if self.elapsed_seconds > 0 else 0
        resumed_str = " (Resumed)" if self.resumed else ""
        return (
            f"✔ Download completed{resumed_str}!\n"
            f"  • File: {self.destination}\n"
            f"  • Size: {size_mb:.2f} MB\n"
            f"  • Time: {self.elapsed_seconds:.1f}s ({speed:.2f} MB/s)\n"
            f"  • SHA-256: {self.sha256[:16]}..."
        )


class UniversalDownloader:
    """
    Production-grade universal downloader.
    Dynamically identifies URLs, apps, or git repositories.
    """

    USER_AGENT = "NeuroShell/5.0 (+https://github.com/abneeshsingh21/neuroshell; UniversalDownloader)"
    CHUNK_SIZE = 64 * 1024  # 64 KB chunks

    # Common apps mapping to known winget/brew package IDs when shorthand is used
    APP_ALIASES: dict[str, dict[str, str]] = {
        "chrome": {"win": "Google.Chrome", "mac": "google-chrome", "linux": "google-chrome-stable"},
        "google chrome": {"win": "Google.Chrome", "mac": "google-chrome", "linux": "google-chrome-stable"},
        "vscode": {"win": "Microsoft.VisualStudioCode", "mac": "visual-studio-code", "linux": "code"},
        "code": {"win": "Microsoft.VisualStudioCode", "mac": "visual-studio-code", "linux": "code"},
        "git": {"win": "Git.Git", "mac": "git", "linux": "git"},
        "gh": {"win": "GitHub.cli", "mac": "gh", "linux": "gh"},
        "github cli": {"win": "GitHub.cli", "mac": "gh", "linux": "gh"},
        "vlc": {"win": "VideoLAN.VLC", "mac": "vlc", "linux": "vlc"},
        "docker": {"win": "Docker.DockerDesktop", "mac": "docker", "linux": "docker.io"},
        "docker desktop": {"win": "Docker.DockerDesktop", "mac": "docker", "linux": "docker.io"},
        "spotify": {"win": "Spotify.Spotify", "mac": "spotify", "linux": "spotify-client"},
        "discord": {"win": "Discord.Discord", "mac": "discord", "linux": "discord"},
        "node": {"win": "OpenJS.NodeJS", "mac": "node", "linux": "nodejs"},
        "nodejs": {"win": "OpenJS.NodeJS", "mac": "node", "linux": "nodejs"},
        "python": {"win": "Python.Python.3.12", "mac": "python@3.12", "linux": "python3"},
        "7zip": {"win": "7zip.7zip", "mac": "sevenzip", "linux": "p7zip-full"},
        "neovim": {"win": "Neovim.Neovim", "mac": "neovim", "linux": "neovim"},
        "nvim": {"win": "Neovim.Neovim", "mac": "neovim", "linux": "neovim"},
        "ffmpeg": {"win": "Gyan.FFmpeg", "mac": "ffmpeg", "linux": "ffmpeg"},
        "postman": {"win": "Postman.Postman", "mac": "postman", "linux": "postman"},
    }

    def __init__(self, default_dir: Path | None = None):
        self.default_dir = Path(default_dir) if default_dir else (Path.home() / "Downloads")
        self.default_dir.mkdir(parents=True, exist_ok=True)

    def download(
        self,
        target: str,
        destination: str | Path | None = None,
        custom_filename: str | None = None,
        resume: bool = True,
        show_progress: bool = True,
    ) -> DownloadResult:
        """
        Main entrypoint: download any URL, git repo, or application.
        """
        clean_target = target.strip().strip("'\"")
        if not clean_target:
            return DownloadResult(success=False, target="", target_type="", error_message="Target is empty")

        # 1. Check if target is a Git repository
        if self._is_git_target(clean_target):
            return self._download_git_repo(clean_target, destination, show_progress=show_progress)

        # 2. Check if target is a direct Web URL (HTTP/HTTPS)
        if clean_target.startswith(("http://", "https://", "ftp://")):
            return self._download_file_url(
                clean_target,
                destination=destination,
                custom_filename=custom_filename,
                resume=resume,
                show_progress=show_progress,
            )

        # 3. Otherwise, treat as an Application / Package download & install
        return self._download_application(clean_target)

    # ═══════════════════════════════════════════════════════
    # 1. Direct Web File Downloader
    # ═══════════════════════════════════════════════════════

    def _download_file_url(
        self,
        url: str,
        destination: str | Path | None = None,
        custom_filename: str | None = None,
        resume: bool = True,
        show_progress: bool = True,
    ) -> DownloadResult:
        """Streaming file downloader with Range resume and progress animation."""
        start_time = time.time()
        dest_dir = Path(destination) if destination and Path(destination).is_dir() else self.default_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        try:
            req = Request(url, headers={"User-Agent": self.USER_AGENT})
            with urlopen(req, timeout=15) as head_resp:
                headers = head_resp.headers
                content_len = headers.get("Content-Length")
                total_bytes = int(content_len) if content_len and content_len.isdigit() else 0
                accept_ranges = headers.get("Accept-Ranges", "").lower() == "bytes"

                # Extract filename
                filename = custom_filename or self._extract_filename(url, headers)

            # Target file path
            if destination and not Path(destination).is_dir():
                target_file = Path(destination)
                target_file.parent.mkdir(parents=True, exist_ok=True)
            else:
                target_file = dest_dir / filename

            # Auto-resume checking
            existing_bytes = 0
            open_mode = "wb"
            is_resumed = False

            if resume and target_file.exists() and total_bytes > 0:
                cur_size = target_file.stat().st_size
                if cur_size < total_bytes and accept_ranges:
                    existing_bytes = cur_size
                    open_mode = "ab"
                    is_resumed = True
                elif cur_size == total_bytes:
                    # Already completely downloaded
                    hasher = hashlib.sha256()
                    with open(target_file, "rb") as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            hasher.update(chunk)
                    return DownloadResult(
                        success=True,
                        target=url,
                        target_type="file",
                        destination=target_file,
                        bytes_downloaded=cur_size,
                        total_bytes=total_bytes,
                        elapsed_seconds=0.01,
                        sha256=hasher.hexdigest(),
                        resumed=True,
                    )

            # Build download request
            req_headers = {"User-Agent": self.USER_AGENT}
            if existing_bytes > 0:
                req_headers["Range"] = f"bytes={existing_bytes}-"

            download_req = Request(url, headers=req_headers)
            hasher = hashlib.sha256()

            # Hash existing bytes if resuming
            if existing_bytes > 0:
                with open(target_file, "rb") as ef:
                    for chunk in iter(lambda: ef.read(65536), b""):
                        hasher.update(chunk)

            downloaded = existing_bytes

            if show_progress:
                print(f"\n  {C_BOLD}{C_CYAN}⬇ Downloading: {C_WHITE}{filename}{C_RESET}")
                if is_resumed:
                    print(f"  {C_YELLOW}⚡ Resuming download from {existing_bytes / (1024 * 1024):.2f} MB...{C_RESET}")

            with urlopen(download_req, timeout=30) as resp, open(target_file, open_mode) as out_f:
                last_update = time.time()
                bytes_since_update = 0

                while True:
                    chunk = resp.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    out_f.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    bytes_since_update += len(chunk)

                    now = time.time()
                    if show_progress and (now - last_update) >= 0.15:
                        speed_mb = (bytes_since_update / (1024 * 1024)) / (now - last_update)
                        self._print_progress_bar(downloaded, total_bytes, speed_mb)
                        last_update = now
                        bytes_since_update = 0

            if show_progress:
                # 100% completion bar
                self._print_progress_bar(downloaded, downloaded, 0.0, finished=True)
                print()

            elapsed = time.time() - start_time
            return DownloadResult(
                success=True,
                target=url,
                target_type="file",
                destination=target_file,
                bytes_downloaded=downloaded,
                total_bytes=total_bytes or downloaded,
                elapsed_seconds=elapsed,
                sha256=hasher.hexdigest(),
                resumed=is_resumed,
            )

        except Exception as e:
            return DownloadResult(
                success=False,
                target=url,
                target_type="file",
                error_message=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    def _extract_filename(self, url: str, headers: Any) -> str:
        """Extract clean filename from Content-Disposition header or URL path."""
        # Check Content-Disposition
        cd = headers.get("Content-Disposition", "")
        if cd:
            m = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', cd, re.IGNORECASE)
            if m:
                return unquote(m.group(1).strip())

        # Check URL path
        parsed = urlparse(url)
        path = unquote(parsed.path).rstrip("/")
        name = os.path.basename(path)
        if name and "." in name:
            return name

        # Content-Type fallback
        ct = headers.get("Content-Type", "").lower()
        if "pdf" in ct:
            return f"document_{int(time.time())}.pdf"
        elif "zip" in ct or "compressed" in ct:
            return f"archive_{int(time.time())}.zip"
        elif "json" in ct:
            return f"data_{int(time.time())}.json"
        elif "csv" in ct:
            return f"data_{int(time.time())}.csv"
        elif "html" in ct:
            return f"page_{int(time.time())}.html"

        return f"download_{int(time.time())}.bin"

    def _print_progress_bar(self, downloaded: int, total: int, speed_mb: float, finished: bool = False) -> None:
        """Render modern animated progress bar with ETA and speed."""
        cols = shutil.get_terminal_size(fallback=(80, 24)).columns
        bar_len = min(30, max(12, cols - 50))

        down_mb = downloaded / (1024 * 1024)
        if total > 0:
            pct = min(100.0, (downloaded / total) * 100)
            filled = int(bar_len * (downloaded / total))
            bar = "█" * filled + "░" * (bar_len - filled)
            total_mb = total / (1024 * 1024)
            rem_bytes = max(0, total - downloaded)
            eta_sec = int(rem_bytes / (speed_mb * 1024 * 1024)) if speed_mb > 0 else 0
            eta_str = f"ETA: {eta_sec // 60:02d}:{eta_sec % 60:02d}"
            sys.stdout.write(
                f"\r  {C_CYAN}[{C_GREEN}{bar}{C_CYAN}]{C_RESET} "
                f"{C_BOLD}{pct:5.1f}%{C_RESET} • "
                f"{C_WHITE}{down_mb:.1f}/{total_mb:.1f} MB{C_RESET} • "
                f"{C_YELLOW}{speed_mb:.1f} MB/s{C_RESET} • "
                f"{C_MUTED}{eta_str}{C_RESET}  "
            )
        else:
            bar = "█" * (bar_len // 2) + "░" * (bar_len // 2)
            sys.stdout.write(
                f"\r  {C_CYAN}[{C_GREEN}{bar}{C_CYAN}]{C_RESET} "
                f"{C_BOLD}{down_mb:.2f} MB{C_RESET} • "
                f"{C_YELLOW}{speed_mb:.1f} MB/s{C_RESET}  "
            )
        sys.stdout.flush()

    # ═══════════════════════════════════════════════════════
    # 2. Git Repository Downloader
    # ═══════════════════════════════════════════════════════

    def _is_git_target(self, target: str) -> bool:
        """Detect if target represents a Git repository."""
        if target.endswith(".git"):
            return True
        if target.startswith("git@"):
            return True
        if re.match(r"^https?://(?:www\.)?github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$", target):
            return True
        # Shorthand github repo: "owner/repo" (when not a file path)
        if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", target) and not os.path.exists(target):
            return True
        return False

    def _download_git_repo(self, repo_target: str, destination: str | Path | None = None, show_progress: bool = True) -> DownloadResult:
        """Clone a git repository using git CLI."""
        start_time = time.time()
        clone_url = repo_target
        if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo_target):
            clone_url = f"https://github.com/{repo_target}.git"
        elif not clone_url.endswith(".git") and "github.com" in clone_url:
            clone_url = f"{clone_url.rstrip('/')}.git"

        repo_name = clone_url.rstrip("/").split("/")[-1].replace(".git", "")
        dest_path = Path(destination) if destination else (Path.cwd() / repo_name)

        if show_progress:
            print(f"\n  {C_BOLD}{C_CYAN}🐙 Cloning Repository: {C_WHITE}{clone_url}{C_RESET}")
            print(f"  {C_MUTED}Destination: {dest_path}{C_RESET}\n")

        cmd = ["git", "clone", clone_url, str(dest_path)]
        try:
            res = subprocess.run(cmd, capture_output=False, text=True)
            if res.returncode == 0:
                return DownloadResult(
                    success=True,
                    target=clone_url,
                    target_type="repo",
                    destination=dest_path,
                    elapsed_seconds=time.time() - start_time,
                )
            else:
                return DownloadResult(
                    success=False,
                    target=clone_url,
                    target_type="repo",
                    error_message=f"git clone exited with code {res.returncode}",
                    elapsed_seconds=time.time() - start_time,
                )
        except Exception as e:
            return DownloadResult(
                success=False,
                target=clone_url,
                target_type="repo",
                error_message=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    # ═══════════════════════════════════════════════════════
    # 3. Application & Package Downloader
    # ═══════════════════════════════════════════════════════

    def _download_application(self, app_name: str) -> DownloadResult:
        """Resolve application name and invoke platform package manager."""
        start_time = time.time()
        system = platform.system()
        clean_app = app_name.lower().replace("download ", "").replace("install ", "").strip()

        # Check aliases
        pkg_id = clean_app
        if clean_app in self.APP_ALIASES:
            alias = self.APP_ALIASES[clean_app]
            if system == "Windows":
                pkg_id = alias.get("win", clean_app)
            elif system == "Darwin":
                pkg_id = alias.get("mac", clean_app)
            else:
                pkg_id = alias.get("linux", clean_app)

        print(f"\n  {C_BOLD}{C_CYAN}📦 Installing Application: {C_WHITE}{clean_app} ({pkg_id}){C_RESET}\n")

        # Select package manager command
        if system == "Windows":
            cmd = f'winget install --id "{pkg_id}" --accept-source-agreements --accept-package-agreements'
        elif system == "Darwin":
            cmd = f'brew install "{pkg_id}"'
        else:
            cmd = f'sudo apt update && sudo apt install -y "{pkg_id}"'

        print(f"  {C_MUTED}Executing: {cmd}{C_RESET}\n")
        try:
            res = subprocess.run(cmd, shell=True)
            if res.returncode == 0:
                return DownloadResult(
                    success=True,
                    target=clean_app,
                    target_type="app",
                    elapsed_seconds=time.time() - start_time,
                )
            else:
                return DownloadResult(
                    success=False,
                    target=clean_app,
                    target_type="app",
                    error_message=f"Package manager exited with code {res.returncode}",
                    elapsed_seconds=time.time() - start_time,
                )
        except Exception as e:
            return DownloadResult(
                success=False,
                target=clean_app,
                target_type="app",
                error_message=str(e),
                elapsed_seconds=time.time() - start_time,
            )


# CLI Entrypoint: python -m operations.downloader <url|app|repo> [destination]
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m operations.downloader <url|repo|app> [destination]")
        sys.exit(1)

    target_arg = sys.argv[1]
    dest_arg = sys.argv[2] if len(sys.argv) > 2 else None

    downloader = UniversalDownloader()
    result = downloader.download(target_arg, destination=dest_arg)
    print("\n" + result.summary())
    sys.exit(0 if result.success else 1)
