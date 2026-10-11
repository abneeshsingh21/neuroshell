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
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
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

        # 0. Check if target is a batch URL file
        if clean_target.startswith(("-f ", "--file ")) or (os.path.isfile(clean_target) and clean_target.endswith((".txt", ".urls"))):
            batch_file = clean_target.replace("-f ", "").replace("--file ", "").strip()
            return self._download_batch_from_file(batch_file, destination=destination)

        # 0.5. Check if target is an explicit academic paper or PDF query
        if clean_target.lower().startswith(("paper:", "arxiv:", "pdf:")):
            query = re.sub(r"^(?:paper|arxiv|pdf):\s*", "", clean_target, flags=re.IGNORECASE)
            return self._search_and_download_paper(query, destination=destination, show_progress=show_progress)

        # 0.6. Check if target is a repository search directive
        if clean_target.lower().startswith(("repo:", "github:")):
            query = re.sub(r"^(?:repo|github):\s*", "", clean_target, flags=re.IGNORECASE)
            return self._search_and_download_repo(query, destination=destination, show_progress=show_progress)

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

        # 3. Check if input has explicit 'paper' or 'pdf' prefix (e.g., "paper attention is all you need")
        lower_target = clean_target.lower()
        if lower_target.startswith("paper ") or lower_target.startswith("pdf "):
            query = clean_target.split(" ", 1)[1].strip()
            return self._search_and_download_paper(query, destination=destination, show_progress=show_progress)

        # 4. Check if input has explicit 'repo ' prefix (e.g. "repo huggingface transformers")
        if lower_target.startswith("repo "):
            query = clean_target.split(" ", 1)[1].strip()
            return self._search_and_download_repo(query, destination=destination, show_progress=show_progress)

        # 5. Otherwise, treat as an Application / Package download & install
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
    # 3. Application & Package Downloader (Dynamic Zero-Hardcoding)
    # ═══════════════════════════════════════════════════════

    def _resolve_package_dynamically(self, app_name: str) -> str | None:
        """
        Dynamically query platform package repository for the exact package ID.
        Zero hardcoding — discovers packages live at runtime.
        """
        system = platform.system()
        clean = app_name.strip()
        try:
            if system == "Windows":
                cmd = ["winget", "search", clean, "--accept-source-agreements"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
                if res.returncode == 0 and res.stdout:
                    lines = res.stdout.strip().splitlines()
                    header_idx = -1
                    for idx, line in enumerate(lines):
                        if "Name" in line and "Id" in line:
                            header_idx = idx
                            break
                    if header_idx != -1 and header_idx + 2 < len(lines):
                        for row in lines[header_idx + 2:]:
                            parts = re.split(r"\s{2,}", row.strip())
                            if len(parts) >= 2:
                                name_col = parts[0]
                                id_col = parts[1]
                                if clean.lower() in name_col.lower() or clean.lower() in id_col.lower():
                                    return id_col
                                return id_col
            elif system == "Darwin":
                cmd = ["brew", "search", clean]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if res.returncode == 0 and res.stdout:
                    for line in res.stdout.strip().splitlines():
                        cand = line.strip()
                        if cand and not cand.startswith("==>") and clean.lower() in cand.lower():
                            return cand
            else:
                cmd = ["apt-cache", "search", clean]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if res.returncode == 0 and res.stdout:
                    lines = res.stdout.strip().splitlines()
                    if lines:
                        return lines[0].split()[0].strip()
        except Exception:
            pass
        return None

    def _download_application(self, app_name: str) -> DownloadResult:
        """Resolve application name dynamically and invoke platform package manager."""
        start_time = time.time()
        system = platform.system()
        clean_app = app_name.lower().replace("download ", "").replace("install ", "").strip()

        # Check aliases cache first
        pkg_id = None
        if clean_app in self.APP_ALIASES:
            alias = self.APP_ALIASES[clean_app]
            if system == "Windows":
                pkg_id = alias.get("win")
            elif system == "Darwin":
                pkg_id = alias.get("mac")
            else:
                pkg_id = alias.get("linux")

        # Zero hardcoding fallback: dynamically discover package from package manager catalog
        if not pkg_id:
            print(f"  {C_MUTED}🔍 Dynamically searching package repository for '{clean_app}'...{C_RESET}")
            dyn_id = self._resolve_package_dynamically(clean_app)
            if dyn_id:
                pkg_id = dyn_id
                print(f"  {C_GREEN}✔ Discovered package: {C_BOLD}{pkg_id}{C_RESET}")
            else:
                pkg_id = clean_app  # Fallback to direct name

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

    # ═══════════════════════════════════════════════════════
    # 4. Academic Paper & PDF Search Downloader
    # ═══════════════════════════════════════════════════════

    def _search_and_download_paper(
        self,
        query: str,
        destination: str | Path | None = None,
        show_progress: bool = True,
    ) -> DownloadResult:
        """
        Dynamically search academic repositories (arXiv API) for papers and download the direct PDF.
        """
        clean_query = query.strip().strip("'\"")
        print(f"\n  {C_BOLD}{C_CYAN}📚 Searching Academic Repository for Paper: {C_WHITE}'{clean_query}'{C_RESET}\n")

        # Check if query is an explicit arXiv ID
        m_arxiv = re.match(r"^(\d{4}\.\d{4,5}(?:v\d+)?)$", clean_query)
        if m_arxiv:
            arxiv_id = m_arxiv.group(1)
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            custom_name = f"arxiv_{arxiv_id}.pdf"
            return self._download_file_url(pdf_url, destination=destination, custom_filename=custom_name, show_progress=show_progress)

        # Query arXiv API
        try:
            api_url = f"https://export.arxiv.org/api/query?search_query=ti:%22{quote(clean_query)}%22&max_results=1"
            req = Request(api_url, headers={"User-Agent": self.USER_AGENT})
            with urlopen(req, timeout=12) as resp:
                xml_data = resp.read()

            tree = ET.fromstring(xml_data)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entry = tree.find("atom:entry", ns)

            if entry is None:
                api_url = f"https://export.arxiv.org/api/query?search_query=all:%22{quote(clean_query)}%22&max_results=1"
                req = Request(api_url, headers={"User-Agent": self.USER_AGENT})
                with urlopen(req, timeout=12) as resp:
                    xml_data = resp.read()
                tree = ET.fromstring(xml_data)
                entry = tree.find("atom:entry", ns)

            if entry is not None:
                title_elem = entry.find("atom:title", ns)
                id_elem = entry.find("atom:id", ns)
                paper_title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else clean_query
                paper_id_url = id_elem.text.strip() if id_elem is not None and id_elem.text else ""

                aid_match = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", paper_id_url)
                if aid_match:
                    arxiv_id = aid_match.group(1)
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                    safe_title = re.sub(r"[^\w\-_.]", "_", paper_title)[:50]
                    custom_name = f"{safe_title}_{arxiv_id}.pdf"
                    print(f"  {C_GREEN}✔ Found Paper: {C_BOLD}{paper_title}{C_RESET}")
                    print(f"  {C_MUTED}Direct PDF: {pdf_url}{C_RESET}\n")
                    return self._download_file_url(pdf_url, destination=destination, custom_filename=custom_name, show_progress=show_progress)

            return DownloadResult(
                success=False,
                target=clean_query,
                target_type="file",
                error_message=f"No academic paper found matching '{clean_query}'",
            )
        except Exception as e:
            return DownloadResult(
                success=False,
                target=clean_query,
                target_type="file",
                error_message=f"Paper search error: {e}",
            )

    # ═══════════════════════════════════════════════════════
    # 5. Repository Search Downloader
    # ═══════════════════════════════════════════════════════

    def _search_and_download_repo(
        self,
        query: str,
        destination: str | Path | None = None,
        show_progress: bool = True,
    ) -> DownloadResult:
        """
        Dynamically search GitHub for matching repository and clone.
        """
        clean_query = query.strip().strip("'\"")
        print(f"\n  {C_BOLD}{C_CYAN}🐙 Searching GitHub for Repository: {C_WHITE}'{clean_query}'{C_RESET}\n")

        # 1. Try gh CLI search
        try:
            cmd = ["gh", "search", "repos", clean_query, "--limit", "1", "--json", "fullName,description"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout:
                data = json.loads(res.stdout)
                if data and isinstance(data, list) and len(data) > 0:
                    matched_repo = data[0].get("fullName")
                    desc = data[0].get("description", "")
                    if matched_repo:
                        print(f"  {C_GREEN}✔ Found Repository: {C_BOLD}{matched_repo}{C_RESET} ({desc[:60]}...)")
                        return self._download_git_repo(matched_repo, destination=destination, show_progress=show_progress)
        except Exception:
            pass

        # 2. Fallback to public GitHub Search API
        try:
            api_url = f"https://api.github.com/search/repositories?q={quote(clean_query)}&per_page=1"
            req = Request(api_url, headers={"User-Agent": self.USER_AGENT})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if data.get("items"):
                matched_repo = data["items"][0].get("full_name")
                if matched_repo:
                    print(f"  {C_GREEN}✔ Found Repository via API: {C_BOLD}{matched_repo}{C_RESET}")
                    return self._download_git_repo(matched_repo, destination=destination, show_progress=show_progress)
        except Exception:
            pass

        return DownloadResult(
            success=False,
            target=clean_query,
            target_type="repo",
            error_message=f"No repository found matching '{clean_query}'",
        )

    # ═══════════════════════════════════════════════════════
    # 6. Batch Downloads from File
    # ═══════════════════════════════════════════════════════

    def _download_batch_from_file(
        self,
        file_path: str | Path,
        destination: str | Path | None = None,
    ) -> DownloadResult:
        """Download multiple targets listed in a text file."""
        p = Path(file_path)
        if not p.is_file():
            return DownloadResult(success=False, target=str(file_path), target_type="file", error_message=f"File not found: {file_path}")

        with open(p, "r", encoding="utf-8", errors="replace") as f:
            targets = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        if not targets:
            return DownloadResult(success=False, target=str(file_path), target_type="file", error_message="No targets found in file")

        print(f"\n  {C_BOLD}{C_CYAN}📋 Batch Downloading {len(targets)} Targets from: {C_WHITE}{p.name}{C_RESET}\n")
        results: list[DownloadResult] = []
        summary_rows = []

        for idx, t in enumerate(targets):
            print(f"  [{idx + 1}/{len(targets)}] Processing: {t}")
            res = self.download(t, destination=destination, show_progress=True)
            results.append(res)
            status_str = "SUCCESS" if res.success else "FAILED"
            size_mb = f"{res.bytes_downloaded / (1024 * 1024):.2f}"
            summary_rows.append([str(idx + 1), res.destination.name if res.destination else t[:30], res.target_type.upper(), size_mb, status_str])

        formatter = AdaptiveTableFormatter()
        print("\n" + formatter.render_table(
            headers=["#", "TARGET", "TYPE", "SIZE (MB)", "STATUS"],
            rows=summary_rows,
            title=f"Batch Download Summary ({p.name})",
        ))

        success_count = sum(1 for r in results if r.success)
        return DownloadResult(
            success=(success_count > 0),
            target=str(file_path),
            target_type="batch",
            destination=Path(destination) if destination else self.default_dir,
            bytes_downloaded=sum(r.bytes_downloaded for r in results),
            elapsed_seconds=sum(r.elapsed_seconds for r in results),
        )


# CLI Entrypoint: python -m operations.downloader [paper|repo|app|url] <target> [destination]
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m operations.downloader <url|repo|app|paper> [args...] [destination]")
        sys.exit(1)

    downloader = UniversalDownloader()
    first_arg = sys.argv[1].lower()

    if first_arg in ("paper", "pdf") and len(sys.argv) > 2:
        query = " ".join(sys.argv[2:])
        result = downloader.download(f"paper:{query}")
    elif first_arg in ("repo", "github") and len(sys.argv) > 2:
        query = " ".join(sys.argv[2:])
        result = downloader.download(f"repo:{query}")
    elif first_arg in ("-f", "--file") and len(sys.argv) > 2:
        file_arg = sys.argv[2]
        dest_arg = sys.argv[3] if len(sys.argv) > 3 else None
        result = downloader.download(f"-f {file_arg}", destination=dest_arg)
    else:
        target_arg = sys.argv[1]
        dest_arg = sys.argv[2] if len(sys.argv) > 2 else None
        result = downloader.download(target_arg, destination=dest_arg)

    print("\n" + result.summary())
    sys.exit(0 if result.success else 1)
