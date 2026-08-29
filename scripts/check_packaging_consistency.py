#!/usr/bin/env python3
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Cross-manifest version & pin consistency gate (Phase 10 — Distribution).

NeuroShell ships through six channels that each carry a version string
(PyPI metadata, native host header, Homebrew formula, winget, scoop, AUR,
Debian) and four that pin artifact digests. History shows how easily they
drift — the Homebrew formula sat two minor versions behind while the code
moved on. This tool is the gate: it fails the build when *any* declared
version disagrees with the others, when a manifest references a floating
``releases/latest`` URL, or when a digest pin is neither a real sha256 nor
the explicit ``REPLACE_AT_RELEASE`` sentinel.

Checked version sources (must all agree):

* ``__version__.py``                     — ``__version__ = "X.Y.Z"``
* ``pyproject.toml``                     — ``[project] version``
* ``cpp_engine/launcher/version.hpp``    — ``NEUROSHELL_VERSION`` string
  **and** the ``_MAJOR``/``_MINOR``/``_PATCH`` integer macros
* ``Formula/neuroshell.rb``              — ``version "X.Y.Z"``
* ``packaging/winget/*.yaml``            — every ``PackageVersion:``
* ``packaging/scoop/neuroshell.json``    — ``"version"``
* ``packaging/aur/PKGBUILD``             — ``pkgver=``
* ``packaging/debian/control``           — ``Version:`` (+ changelog head)
* ``CHANGELOG.md``                       — topmost ``## [X.Y.Z]`` entry

Pin policy:

* digest fields (``InstallerSha256``/``hash``/``sha256sums_*``/``sha256 "…"``)
  must be 64 lowercase hex chars **or** the sentinel ``REPLACE_AT_RELEASE``
  (resolved at release time by ``render`` below — the release workflow fails
  if a sentinel survives into a tagged build);
* no manifest under ``packaging/`` or ``Formula/`` may reference a floating
  ``releases/latest`` URL — every download URL pins an exact tag.

Subcommands:

* ``check`` (default) — run all assertions; exit 1 with a report on drift.
* ``render``          — produce final manifests with real digests:
  ``render --sha256-file checksums.txt --out-dir dist/packaging`` reads a
  ``sha256sum``-format checksums file, replaces every sentinel whose asset
  name appears in it, verifies every URL carries the expected tag, and
  writes the ready-to-submit manifests (the repo templates are untouched).

A pytest wrapper (``tests/test_packaging_consistency.py``) runs ``check`` in
CI so drift can never land silently again.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]  # overridable via --root
SENTINEL = "REPLACE_AT_RELEASE"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class ConsistencyError(Exception):
    """One or more consistency checks failed."""


def _read(path: Path) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Version extractors — each returns the version string claimed by one source
# ─────────────────────────────────────────────────────────────────────────────

def version_from_dunder() -> str:
    m = re.search(r'__version__\s*=\s*"([^"]+)"', _read(Path("__version__.py")))
    if not m:
        raise ConsistencyError("__version__.py: no __version__ assignment found")
    return m.group(1)


def version_from_pyproject() -> str:
    try:
        import tomllib  # Python >= 3.11
    except ModuleNotFoundError:
        m = re.search(r'^version\s*=\s*"([^"]+)"', _read(Path("pyproject.toml")),
                      re.MULTILINE)
        if not m:
            raise ConsistencyError("pyproject.toml: no [project] version found") from None
        return m.group(1)
    data = tomllib.loads(_read(Path("pyproject.toml")))
    v = data.get("project", {}).get("version")
    if not v:
        raise ConsistencyError("pyproject.toml: [project].version missing")
    return str(v)


def version_from_header() -> tuple[str, tuple[int, int, int]]:
    text = _read(Path("cpp_engine/launcher/version.hpp"))
    m = re.search(r'#define\s+NEUROSHELL_VERSION\s+"([^"]+)"', text)
    if not m:
        raise ConsistencyError("version.hpp: NEUROSHELL_VERSION not found")
    major = re.search(r"#define\s+NEUROSHELL_VERSION_MAJOR\s+(\d+)", text)
    minor = re.search(r"#define\s+NEUROSHELL_VERSION_MINOR\s+(\d+)", text)
    patch = re.search(r"#define\s+NEUROSHELL_VERSION_PATCH\s+(\d+)", text)
    if not (major and minor and patch):
        raise ConsistencyError("version.hpp: MAJOR/MINOR/PATCH macros incomplete")
    return m.group(1), (int(major.group(1)), int(minor.group(1)), int(patch.group(1)))


def version_from_formula() -> str:
    m = re.search(r'^\s*version\s+"([^"]+)"', _read(Path("Formula/neuroshell.rb")),
                  re.MULTILINE)
    if not m:
        raise ConsistencyError("Formula/neuroshell.rb: no version declaration found")
    return m.group(1)


def versions_from_winget() -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    winget_dir = REPO_ROOT / "packaging" / "winget"
    for f in sorted(winget_dir.glob("*.yaml")):
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"^PackageVersion:\s*(\S+)", text, re.MULTILINE):
            results.append((f.name, m.group(1)))
    if not results:
        raise ConsistencyError("packaging/winget: no PackageVersion found")
    return results


def version_from_scoop() -> str:
    data = json.loads(_read(Path("packaging/scoop/neuroshell.json")))
    v = data.get("version")
    if not v:
        raise ConsistencyError("packaging/scoop/neuroshell.json: version missing")
    return str(v)


def version_from_aur() -> str:
    m = re.search(r"^pkgver=(\S+)", _read(Path("packaging/aur/PKGBUILD")),
                  re.MULTILINE)
    if not m:
        raise ConsistencyError("packaging/aur/PKGBUILD: pkgver not found")
    return m.group(1)


def version_from_debian() -> tuple[str, str]:
    control = re.search(r"^Version:\s*(\S+)", _read(Path("packaging/debian/control")),
                        re.MULTILINE)
    changelog = re.search(r"^neuroshell\s+\((\S+?)\)", _read(Path("packaging/debian/changelog")),
                          re.MULTILINE)
    if not control:
        raise ConsistencyError("packaging/debian/control: Version field missing")
    if not changelog:
        raise ConsistencyError("packaging/debian/changelog: no version stanza found")
    return control.group(1), changelog.group(1)


def version_from_changelog() -> str:
    m = re.search(r"^##\s*\[([^\]\s]+)\]", _read(Path("CHANGELOG.md")), re.MULTILINE)
    if not m:
        raise ConsistencyError("CHANGELOG.md: no '## [X.Y.Z]' entry found")
    return m.group(1)


# ─────────────────────────────────────────────────────────────────────────────
# Pin policy checks
# ─────────────────────────────────────────────────────────────────────────────

def check_pins_and_urls() -> list[str]:
    """Return a list of policy violations (empty = clean)."""
    problems: list[str] = []
    targets = [REPO_ROOT / "Formula", REPO_ROOT / "packaging"]
    digest_patterns = [
        re.compile(r"InstallerSha256:\s*(\S+)"),
        re.compile(r'"hash":\s*"([^"]+)"'),
        re.compile(r"sha256sums(?:_\w+)?=\(([^)]*)\)", re.MULTILINE | re.DOTALL),
        re.compile(r'sha256\s+"([0-9a-f]{64}|[A-Z_]+)"'),  # Homebrew
    ]
    for base in targets:
        for f in sorted(base.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(REPO_ROOT)
            text = f.read_text(encoding="utf-8", errors="replace")
            if "releases/latest" in text or "releases/download/latest" in text:
                problems.append(f"{rel}: floating 'releases/latest' URL "
                                f"(must pin an exact tag)")
            for pat in digest_patterns:
                for m in pat.finditer(text):
                    for token in re.findall(r"'([^']+)'|\"([^\"]+)\"", m.group(0)) \
                            if "sha256sums" in pat.pattern else [(m.group(1), "")]:
                        value = token[0] or token[1]
                        if value in {SENTINEL} or SHA256_RE.match(value):
                            continue
                        if not SHA256_RE.match(value):
                            problems.append(
                                f"{rel}: digest '{value[:24]}…' is neither a "
                                f"sha256 nor the {SENTINEL} sentinel")
    return problems


# ─────────────────────────────────────────────────────────────────────────────
# check / render
# ─────────────────────────────────────────────────────────────────────────────

def collect_versions() -> dict[str, str | list]:
    header_str, header_macros = version_from_header()
    deb_control, deb_changelog = version_from_debian()
    winget = versions_from_winget()
    return {
        "__version__.py": version_from_dunder(),
        "pyproject.toml": version_from_pyproject(),
        "cpp_engine/launcher/version.hpp": header_str,
        "cpp_engine/launcher/version.hpp [macros]":
            ".".join(str(x) for x in header_macros),
        "Formula/neuroshell.rb": version_from_formula(),
        "packaging/winget": [v for _, v in winget],
        "packaging/scoop/neuroshell.json": version_from_scoop(),
        "packaging/aur/PKGBUILD": version_from_aur(),
        "packaging/debian/control": deb_control,
        "packaging/debian/changelog": deb_changelog.split("-")[0],
        "CHANGELOG.md (top entry)": version_from_changelog(),
    }


def cmd_check(args: argparse.Namespace) -> int:
    problems: list[str] = []
    versions = collect_versions()
    flat: list[tuple[str, str]] = []
    for source, value in versions.items():
        if isinstance(value, list):
            for v in value:
                flat.append((source, v))
        else:
            flat.append((source, value))

    # Majority vote: the canonical version is what most manifests declare;
    # outliers are blamed by name (a single drifted file is obvious, a split
    # tree is an error in itself).
    counts: dict[str, int] = {}
    for _, v in flat:
        counts[v] = counts.get(v, 0) + 1
    expected = max(counts, key=counts.get)  # noqa: PLW2901 — max by count
    if len(counts) > 1:
        for source, value in flat:
            if value != expected:
                problems.append(f"{source}: version {value} != {expected} "
                                f"(majority; {counts[value]} of {len(flat)} "
                                f"declarations)")

    if not SEMVER_RE.match(expected):
        problems.append(f"canonical version {expected!r} is not X.Y.Z semver")

    # version.hpp macros must equal the string's parts
    header_str, header_macros = version_from_header()
    if header_str != ".".join(str(x) for x in header_macros):
        problems.append(f"version.hpp: string {header_str} != "
                        f"macros {header_macros}")

    problems += check_pins_and_urls()

    if problems:
        print(f"FAIL: {len(problems)} consistency problem(s):", file=sys.stderr)
        for p_ in problems:
            print(f"  - {p_}", file=sys.stderr)
        return 1
    print(f"OK: {len(flat)} version declarations agree on {expected}; "
          f"digest pins and download URLs conform to policy")
    return 0


def _load_checksums(path: Path) -> dict[str, str]:
    sums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition(" ")
        name = name.strip().lstrip("*")
        if not SHA256_RE.match(digest) or not name:
            raise ConsistencyError(f"bad checksums line: {line!r}")
        sums[name] = digest
    return sums


def _download_assets(text: str) -> list[str]:
    """Asset names from every pinned download URL, in document order.

    Handles both plain URLs (…/download/<tag>/<name>) and PKGBUILD's
    ``<name>::<url>`` alias form (the alias is what the checksum refers to).
    """
    assets: list[str] = []
    for m in re.finditer(r"releases/download/[^\s'\")]+/([A-Za-z0-9._-]+)", text):
        assets.append(m.group(1))
    for m in re.finditer(r"([A-Za-z0-9._-]+)::https?://", text):
        if m.group(1) not in assets:
            assets.append(m.group(1))
    return assets


def cmd_render(args: argparse.Namespace) -> int:
    sums = _load_checksums(Path(args.sha256_file))
    out_dir = Path(args.out_dir)
    sources = [REPO_ROOT / "Formula", REPO_ROOT / "packaging"]
    missing: list[str] = []
    rendered_files: list[Path] = []

    for base in sources:
        for f in sorted(base.rglob("*")):
            if not f.is_file():
                continue
            text = f.read_text(encoding="utf-8")
            rel = f.relative_to(REPO_ROOT)
            if not _sentinel_spans(text):
                continue
            # Pair every sentinel occurrence with an asset name. Manifests
            # declare one digest per download URL, in document order — zip
            # them; a lone asset with multiple sentinels (not our case) is
            # ambiguous and rejected.
            assets = _download_assets(text)
            sentinel_count = len(_sentinel_spans(text))
            if not assets:
                missing.append(f"{rel}: sentinel with no download URL to bind")
                continue
            if sentinel_count == len(assets):
                spans = _sentinel_spans(text)
                pairs = [(span, asset) for span, asset in zip(spans, assets, strict=True)]
            elif sentinel_count == 1:
                pairs = [(_sentinel_spans(text)[0], assets[0])]
            else:
                missing.append(
                    f"{rel}: {sentinel_count} sentinels but {len(assets)} "
                    f"download URLs — cannot pair unambiguously")
                continue
            unresolved = [a for _, a in pairs if a not in sums]
            if unresolved:
                missing.append(f"{rel}: no checksum for asset(s) {unresolved}")
                continue
            # replace from the end so earlier spans stay valid
            new_text = text
            for span, asset in sorted(pairs, key=lambda x: x[0][0], reverse=True):
                s, e = span
                new_text = new_text[:s] + sums[asset] + new_text[e:]
            target = out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(new_text, encoding="utf-8")
            print(f"rendered {rel} -> {target}")
            rendered_files.append(target)

    if missing:
        print("FAIL: unresolved sentinels:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 1

    # every rendered download URL must pin the expected release tag
    tag = args.tag
    bad_urls: list[str] = []
    for target in rendered_files:
        for url in re.findall(r"https://[^\s'\")]+/download/[^\s'\")]+",
                              target.read_text(encoding="utf-8")):
            if f"/{tag}/" not in url:
                bad_urls.append(f"{target.name}: {url}")
    if bad_urls:
        print("FAIL: URLs not pinned to the release tag:", file=sys.stderr)
        for u in bad_urls:
            print(f"  - {u}", file=sys.stderr)
        return 1
    print(f"OK: rendered {len(rendered_files)} manifest(s) with real digests; "
          f"all download URLs pinned to {tag}")
    return 0


def _sentinel_spans(text: str) -> list[tuple[int, int]]:
    """Spans of sentinel occurrences that are *values*, not comment mentions.

    A `#` earlier on the same line marks a comment in every manifest syntax
    here (YAML, Ruby, bash); value positions like
    ``sha256 "REPLACE_AT_RELEASE" # note`` still count (the ``#`` comes
    after the span)."""
    spans: list[tuple[int, int]] = []
    idx = text.find(SENTINEL)
    while idx != -1:
        line_start = text.rfind("\n", 0, idx) + 1
        prefix = text[line_start:idx]
        if "#" not in prefix:
            spans.append((idx, idx + len(SENTINEL)))
        idx = text.find(SENTINEL, idx + len(SENTINEL))
    return spans


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="check_packaging_consistency.py",
        description="Assert version + digest-pin consistency across every "
                    "NeuroShell distribution manifest.")
    sub = ap.add_subparsers(dest="cmd")

    c = sub.add_parser("check", help="verify all manifests agree")
    c.add_argument("--root", default=None,
                   help="repository root (default: derived from this script)")
    c.set_defaults(func=cmd_check)

    r = sub.add_parser("render", help="render final manifests with real digests")
    r.add_argument("--sha256-file", required=True,
                   help="sha256sum-format file of release assets")
    r.add_argument("--tag", required=True, help="release tag, e.g. v5.18.0")
    r.add_argument("--out-dir", default="dist/packaging")
    r.add_argument("--root", default=None,
                   help="repository root (default: derived from this script)")
    r.set_defaults(func=cmd_render)

    args = ap.parse_args(argv or ["check"])
    global REPO_ROOT  # noqa: PLW0603 — CLI-scope override for CI/testing
    if getattr(args, "root", None):
        REPO_ROOT = Path(args.root).resolve()
    try:
        return args.func(args)
    except (ConsistencyError, OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
