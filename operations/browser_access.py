# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Production browser access helpers with optional Playwright automation."""

from __future__ import annotations

import importlib.util
import re
import webbrowser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class BrowserAccessManager:
    """Provide safe browser operations for open/fetch/extract/screenshot."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("URL must include http/https scheme and host")

    @staticmethod
    def _playwright_available() -> bool:
        return importlib.util.find_spec("playwright") is not None

    def status(self) -> dict:
        return {
            "playwright_installed": self._playwright_available(),
            "screenshot_ready": self._playwright_available(),
            "fetch_ready": True,
        }

    def open_url(self, url: str) -> str:
        self._validate_url(url)
        opened = webbrowser.open(url)
        if opened:
            return f"Opened browser tab: {url}"
        return f"Browser launch requested (handler may be blocked): {url}"

    def fetch_html(self, url: str, timeout_s: int = 20, max_bytes: int = 1024 * 1024) -> str:
        self._validate_url(url)
        req = Request(url, headers={"User-Agent": "NeuroShell/4.0 (+browser-access)"})
        with urlopen(req, timeout=timeout_s) as resp:
            data = resp.read(max_bytes)
        return data.decode("utf-8", errors="replace")

    def extract_text(self, url: str, timeout_s: int = 20, max_chars: int = 3000) -> str:
        html = self.fetch_html(url, timeout_s=timeout_s)
        cleaned = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", html)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars] + "..."
        return cleaned

    def screenshot(self, url: str, output_path: Path, timeout_ms: int = 20000) -> Path:
        self._validate_url(url)
        if not self._playwright_available():
            raise RuntimeError(
                "Playwright is not installed. Install with: pip install playwright && playwright install chromium"
            )

        from playwright.sync_api import sync_playwright  # type: ignore

        output_path = Path(output_path)
        if not output_path.is_absolute():
            output_path = self.workspace_root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                page.screenshot(path=str(output_path), full_page=True)
            finally:
                browser.close()

        return output_path
