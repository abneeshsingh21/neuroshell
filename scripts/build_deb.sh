#!/usr/bin/env bash
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
#
# Build Debian/Ubuntu .deb package for NeuroShell.
#
# Phase 10 refresh: the version is read from __version__.py (single source of
# truth) and the control/changelog/copyright templates live in
# packaging/debian/ so they are covered by
# scripts/check_packaging_consistency.py. A reproducible-ish build: the
# changelog is gzip'd with -n (no timestamp in the header) and the .deb is
# emitted together with its sha256 for release checksums.txt.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 1. Single-source-of-truth version + host architecture
VERSION="$(python3 -c 'import re;print(re.search(r"__version__\s*=\s*\"([^\"]+)\"",open("'"$ROOT_DIR"'/__version__.py").read()).group(1))')"
ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')"
PKG_NAME="neuroshell_${VERSION}_${ARCH}"
BUILD_ROOT="$(mktemp -d /tmp/${PKG_NAME}.XXXXXX)"
trap 'rm -rf "$BUILD_ROOT"' EXIT

DEB_DIR="$ROOT_DIR/dist"
mkdir -p "$DEB_DIR"

echo "📦 Building Debian package: ${PKG_NAME}.deb (arch ${ARCH})..."

# 2. Layout — install paths kept identical to historical packages:
#    /usr/local/bin/neuroshell, /usr/share/neuroshell, /usr/share/doc/neuroshell
mkdir -p "$BUILD_ROOT/DEBIAN" \
         "$BUILD_ROOT/usr/local/bin" \
         "$BUILD_ROOT/usr/share/neuroshell" \
         "$BUILD_ROOT/usr/share/doc/neuroshell"

# 3. Payload: native launcher binary from dist/ (built by CMake)
if [[ ! -f "$ROOT_DIR/dist/neuroshell" ]]; then
  echo "error: dist/neuroshell not found — build it first:" >&2
  echo "  cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cp build/neuroshell dist/" >&2
  exit 1
fi
install -m 755 "$ROOT_DIR/dist/neuroshell" "$BUILD_ROOT/usr/local/bin/neuroshell"

# 4. Documentation + licenses from the packaging templates
install -m 644 "$ROOT_DIR/README.md" "$BUILD_ROOT/usr/share/doc/neuroshell/README.md"
install -m 644 "$ROOT_DIR/packaging/debian/copyright" "$BUILD_ROOT/usr/share/doc/neuroshell/copyright"
install -m 644 "$ROOT_DIR/packaging/debian/changelog" "$BUILD_ROOT/usr/share/doc/neuroshell/changelog"
gzip -9n "$BUILD_ROOT/usr/share/doc/neuroshell/changelog"   # -n: no timestamp → reproducible

# 5. DEBIAN/control from the template (version asserted consistent upstream)
sed "s/^Architecture: any$/Architecture: ${ARCH}/" \
  "$ROOT_DIR/packaging/debian/control" > "$BUILD_ROOT/DEBIAN/control"

# 6. md5sums of the payload (what dpkg verifies at unpack time)
( cd "$BUILD_ROOT" && find usr -type f -exec md5sum {} + ) > "$BUILD_ROOT/DEBIAN/md5sums"

# 7. Build
dpkg-deb --root-owner-group --build "$BUILD_ROOT" "$DEB_DIR/${PKG_NAME}.deb"

# 8. Emit the sha256 alongside (input for release checksums.txt)
SHA256="$(sha256sum "$DEB_DIR/${PKG_NAME}.deb" | awk '{print $1}')"
printf '%s  %s\n' "$SHA256" "${PKG_NAME}.deb" > "$DEB_DIR/${PKG_NAME}.deb.sha256"

echo "✅ Built: dist/${PKG_NAME}.deb"
echo "   sha256: $SHA256"
