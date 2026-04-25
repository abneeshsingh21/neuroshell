# NeuroShell Auto-Update Checker
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
"""
Lightweight GitHub release checker. Compares local version against
the latest GitHub release tag and notifies the user if an update
is available. No auto-download — user controls the upgrade.
"""

import json
import logging
import urllib.request
from typing import Optional
from config import __version__

_log = logging.getLogger("neuroshell.update_checker")

_GITHUB_API = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
_DEFAULT_OWNER = "abneeshsingh21"
_DEFAULT_REPO = "neuroshell"


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse 'v1.2.3' or '1.2.3' into (1, 2, 3)."""
    clean = v.lstrip("vV").strip()
    parts = []
    for p in clean.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts) or (0,)


def check_for_update(
    owner: str = _DEFAULT_OWNER,
    repo: str = _DEFAULT_REPO,
    timeout: float = 5.0,
) -> Optional[dict]:
    """
    Check GitHub for a newer release.
    
    Returns dict with keys: available, latest, current, url
    or None on failure.
    """
    try:
        url = _GITHUB_API.format(owner=owner, repo=repo)
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "NeuroShell"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        latest_tag = data.get("tag_name", "0.0.0")
        latest_ver = _parse_version(latest_tag)
        current_ver = _parse_version(__version__)

        return {
            "available": latest_ver > current_ver,
            "latest": latest_tag,
            "current": __version__,
            "url": data.get("html_url", ""),
            "notes": data.get("body", "")[:200],
        }
    except Exception as exc:
        _log.debug("Update check failed: %s", exc)
        return None
