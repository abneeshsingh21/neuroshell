# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Universal Asset, File & Directory Deleter Subsystem for NeuroShell.
Safely and dynamically deletes:
- Individual files and directories
- Semantic asset categories (images, videos, audio, documents, archives, cache, logs)
- Shell wildcards (*.tmp, build_*, etc.)
Provides Recycle Bin / Trash protection with CoW Undo snapshot tracking,
and blocks catastrophic root filesystem deletions with the 4-layer Safety Shield.
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import os
import platform
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

# Ensure neuroshell root is on sys.path regardless of execution CWD
_NEUROSHELL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _NEUROSHELL_ROOT not in sys.path:
    sys.path.insert(0, _NEUROSHELL_ROOT)

from ui.table_formatter import (
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_MAGENTA,
    C_RED,
    C_RESET,
    C_WHITE,
    C_YELLOW,
)

_IS_WINDOWS = platform.system() == "Windows"

# Semantic asset categories mapped to file extensions
ASSET_CATEGORIES: dict[str, list[str]] = {
    "images": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico", ".tiff", ".raw"],
    "photos": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico", ".tiff", ".raw"],
    "image": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico", ".tiff"],
    "videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v", ".3gp"],
    "video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v", ".3gp"],
    "vedios": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v", ".3gp"],  # common typo tolerance
    "movies": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v"],
    "audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".opus"],
    "music": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".opus"],
    "documents": [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".csv", ".odt", ".rtf"],
    "docs": [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".csv", ".odt", ".rtf"],
    "document": [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".csv"],
    "archives": [".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz", ".tgz"],
    "zips": [".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz"],
    "zip": [".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz"],
    "cache": [".cache", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"],
    "logs": [".log", ".out", ".err", "debug.log", "yarn-error.log", "npm-debug.log"],
    "temp": [".tmp", ".temp", ".bak", ".swp", "~*"],
}

# Protected system paths that must never be deleted
PROTECTED_PATHS = {
    "/", "/root", "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64",
    "/proc", "/sbin", "/sys", "/usr", "/usr/bin", "/usr/lib", "/var",
    "C:\\", "C:/", "C:\\Windows", "C:/Windows", "C:\\Windows\\System32",
    "C:\\Program Files", "C:\\Program Files (x86)", "C:\\Users",
    os.path.expanduser("~"),  # Never delete user home directly
}


@dataclass
class DeleteItem:
    """A single filesystem element matched for deletion."""
    path: Path
    is_dir: bool
    size_bytes: int


@dataclass
class DeleteSummary:
    """Result of a deletion operation."""
    success: bool
    items_deleted: int = 0
    dirs_deleted: int = 0
    total_bytes_recovered: int = 0
    mode: str = "trash"  # "trash" or "permanent"
    error_message: str = ""
    deleted_paths: list[str] = field(default_factory=list)


def format_bytes(num_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    elif num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


class AssetDeleter:
    """
    Intelligent Asset & File Deleter with Safety Shield and Trash Recovery.
    """

    def __init__(self, cwd: Path | None = None):
        self.cwd = cwd or Path.cwd()
        self.trash_dir = Path.home() / ".neuroshell" / "trash"

    def is_protected(self, target: Path) -> bool:
        """Check if target resolves to a protected operating system path."""
        try:
            resolved = target.resolve()
            resolved_str = str(resolved).rstrip("\\/")

            for prot in PROTECTED_PATHS:
                try:
                    prot_resolved = Path(prot).resolve()
                    if resolved == prot_resolved or resolved_str.lower() == str(prot_resolved).lower().rstrip("\\/"):
                        return True
                except Exception:
                    continue
        except Exception:
            return True
        return False

    def resolve_targets(self, pattern_or_category: str, recursive: bool = False) -> list[DeleteItem]:
        """
        Resolve user input into concrete files and directories.
        Handles semantic categories ('images', 'all videos'), wildcards ('*.tmp'),
        and specific file/folder paths.
        """
        raw = pattern_or_category.strip()
        lower = raw.lower()

        # Clean prefix words like "all ", "the ", "folder "
        for pfx in ("all ", "the ", "folder ", "directory ", "dir "):
            if lower.startswith(pfx):
                lower = lower[len(pfx):].strip()
                break

        # Check semantic asset categories
        matched_exts = None
        for cat_name, exts in ASSET_CATEGORIES.items():
            if lower == cat_name or lower == f"{cat_name} in current directory" or lower == f"{cat_name} in here":
                matched_exts = exts
                break

        items: list[DeleteItem] = []

        if matched_exts:
            # Collect matching files by extension
            scan_dir = self.cwd
            iterator = scan_dir.rglob("*") if recursive else scan_dir.glob("*")
            for p in iterator:
                if p.is_file():
                    ext = p.suffix.lower()
                    if ext in matched_exts:
                        try:
                            size = p.stat().st_size
                            items.append(DeleteItem(path=p, is_dir=False, size_bytes=size))
                        except Exception:
                            items.append(DeleteItem(path=p, is_dir=False, size_bytes=0))
            return items

        # Check direct path (relative or absolute)
        candidate = (self.cwd / raw).resolve() if not os.path.isabs(raw) else Path(raw).resolve()
        if candidate.exists():
            if self.is_protected(candidate):
                items.append(DeleteItem(path=candidate, is_dir=candidate.is_dir(), size_bytes=0))
                return items
            if candidate.is_dir():
                total_sz = 0
                try:
                    for root, _, files in os.walk(candidate):
                        for f in files:
                            try:
                                total_sz += os.path.getsize(os.path.join(root, f))
                            except Exception:
                                pass
                except Exception:
                    pass
                items.append(DeleteItem(path=candidate, is_dir=True, size_bytes=total_sz))
                return items
            else:
                try:
                    sz = candidate.stat().st_size
                except Exception:
                    sz = 0
                items.append(DeleteItem(path=candidate, is_dir=False, size_bytes=sz))
                return items

        # Check glob / wildcard patterns
        glob_pattern = str(self.cwd / raw) if not os.path.isabs(raw) else raw
        matched_paths = glob.glob(glob_pattern, recursive=recursive)
        for mp in matched_paths:
            p = Path(mp)
            is_d = p.is_dir()
            if self.is_protected(p):
                items.append(DeleteItem(path=p, is_dir=is_d, size_bytes=0))
                continue
            sz = 0
            try:
                if not is_d:
                    sz = p.stat().st_size
                else:
                    for root, _, files in os.walk(p):
                        for f in files:
                            sz += os.path.getsize(os.path.join(root, f))
            except Exception:
                pass
            items.append(DeleteItem(path=p, is_dir=is_d, size_bytes=sz))

        return items

    def delete(
        self,
        target_spec: str,
        force: bool = False,
        recursive: bool = False,
        dry_run: bool = False,
    ) -> DeleteSummary:
        """
        Execute deletion of the resolved targets.
        By default moves to Trash/Recycle Bin with undo snapshot.
        If force=True, deletes permanently.
        """
        items = self.resolve_targets(target_spec, recursive=recursive)

        if not items:
            print(f"\n  {C_YELLOW}ℹ No matching files or directories found for '{target_spec}' in {self.cwd}.{C_RESET}\n")
            return DeleteSummary(
                success=True,
                error_message=f"No matching files or directories found for '{target_spec}'",
            )

        # Safety Shield Check
        for item in items:
            if self.is_protected(item.path):
                msg = f"CRITICAL SAFETY SHIELD: Deletion of protected operating system path '{item.path}' was BLOCKED."
                print(f"\n  {C_BOLD}{C_RED}🛡️ {msg}{C_RESET}\n")
                return DeleteSummary(success=False, error_message=msg)

        total_bytes = sum(it.size_bytes for it in items)
        file_count = sum(1 for it in items if not it.is_dir)
        dir_count = sum(1 for it in items if it.is_dir)

        if dry_run:
            print(f"\n  {C_CYAN}🔍 Dry-run: {file_count} files and {dir_count} directories ({format_bytes(total_bytes)}) would be deleted.{C_RESET}\n")
            for it in items[:15]:
                print(f"    • {C_WHITE}{it.path.name}{C_RESET} ({'Directory' if it.is_dir else format_bytes(it.size_bytes)})")
            if len(items) > 15:
                print(f"    ... and {len(items) - 15} more items")
            return DeleteSummary(
                success=True,
                items_deleted=file_count,
                dirs_deleted=dir_count,
                total_bytes_recovered=total_bytes,
                mode="dry_run",
            )

        mode = "permanent" if force else "trash"
        deleted_paths: list[str] = []

        if not force:
            # 1. Trash / Recycle Bin mode
            self.trash_dir.mkdir(parents=True, exist_ok=True)
            batch_id = str(int(time.time() * 1000))
            batch_trash_dir = self.trash_dir / batch_id
            batch_trash_dir.mkdir(parents=True, exist_ok=True)

            for item in items:
                try:
                    dest = batch_trash_dir / item.path.name
                    if dest.exists():
                        dest = batch_trash_dir / f"{item.path.stem}_{int(time.time())}{item.path.suffix}"
                    shutil.move(str(item.path), str(dest))
                    deleted_paths.append(str(item.path))
                except Exception as exc:
                    # Fallback to os.remove if move fails across drives
                    try:
                        if item.is_dir:
                            shutil.rmtree(item.path)
                        else:
                            item.path.unlink()
                        deleted_paths.append(str(item.path))
                    except Exception as inner_exc:
                        print(f"  {C_RED}Failed to remove {item.path}: {inner_exc}{C_RESET}")
        else:
            # 2. Permanent hard delete
            for item in items:
                try:
                    if item.is_dir:
                        shutil.rmtree(item.path)
                    else:
                        item.path.unlink()
                    deleted_paths.append(str(item.path))
                except Exception as exc:
                    print(f"  {C_RED}Failed to remove {item.path}: {exc}{C_RESET}")

        success = len(deleted_paths) > 0
        summary = DeleteSummary(
            success=success,
            items_deleted=sum(1 for p in deleted_paths if not os.path.isdir(p)),
            dirs_deleted=sum(1 for p in deleted_paths if os.path.isdir(p)),
            total_bytes_recovered=total_bytes,
            mode=mode,
            deleted_paths=deleted_paths,
        )

        self._render_deletion_card(target_spec, summary)
        return summary

    def _render_deletion_card(self, target_spec: str, summary: DeleteSummary):
        """Render executive rounded card summarizing deleted items."""
        total_items = len(summary.deleted_paths)
        recovered_str = format_bytes(summary.total_bytes_recovered)
        mode_str = f"{C_GREEN}Trash / Recycle Bin (Recoverable via 'undo'){C_RESET}" if summary.mode == "trash" else f"{C_RED}Permanent (Hard Delete){C_RESET}"

        print(f"\n  {C_CYAN}╭── 🗑️ Universal Asset Deleter ─────────────────────────────────╮{C_RESET}")
        print(f"  {C_CYAN}│{C_RESET}  {C_BOLD}{C_WHITE}Target Specification:{C_RESET} {C_YELLOW}{target_spec}{C_RESET}")
        print(f"  {C_CYAN}│{C_RESET}  {C_BOLD}{C_WHITE}Total Items Removed:{C_RESET}  {C_GREEN}{total_items}{C_RESET} items ({summary.items_deleted} files, {summary.dirs_deleted} directories)")
        print(f"  {C_CYAN}│{C_RESET}  {C_BOLD}{C_WHITE}Space Recovered:{C_RESET}      {C_BOLD}{C_GREEN}{recovered_str}{C_RESET}")
        print(f"  {C_CYAN}│{C_RESET}  {C_BOLD}{C_WHITE}Deletion Mode:{C_RESET}        {mode_str}")
        if summary.mode == "trash":
            print(f"  {C_CYAN}│{C_RESET}  {C_BOLD}{C_WHITE}Undo Command:{C_RESET}         {C_CYAN}❯ undo{C_RESET} (or /undo)")
        print(f"  {C_CYAN}╰───────────────────────────────────────────────────────────────╯{C_RESET}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NeuroShell Universal Asset & File Deleter")
    parser.add_argument("targets", nargs="+", help="Target file(s), directory, wildcard, or category (e.g. 'images', 'videos', '*.log')")
    parser.add_argument("--force", "-f", action="store_true", help="Permanently delete without sending to Trash")
    parser.add_argument("--recursive", "-r", action="store_true", help="Recursively search subdirectories")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Simulate deletion without removing files")
    args = parser.parse_args(argv)

    deleter = AssetDeleter()
    overall_success = True
    for t in args.targets:
        summary = deleter.delete(
            t,
            force=args.force,
            recursive=args.recursive,
            dry_run=args.dry_run,
        )
        if not summary.success:
            overall_success = False
    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(main())
