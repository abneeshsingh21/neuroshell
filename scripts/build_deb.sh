#!/usr/bin/env bash
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Build Debian/Ubuntu .deb package for NeuroShell

set -e

VERSION="5.4.0"
ARCH="amd64"
PKG_NAME="neuroshell_${VERSION}_${ARCH}"
BUILD_ROOT="/tmp/${PKG_NAME}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "📦 Building Debian Package: ${PKG_NAME}.deb..."

rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT/DEBIAN"
mkdir -p "$BUILD_ROOT/usr/local/bin"
mkdir -p "$BUILD_ROOT/usr/share/neuroshell"
mkdir -p "$BUILD_ROOT/usr/share/doc/neuroshell"

# 1. Copy Binary
cp "$ROOT_DIR/dist/neuroshell" "$BUILD_ROOT/usr/local/bin/neuroshell"
chmod 755 "$BUILD_ROOT/usr/local/bin/neuroshell"

# 2. Copy Documentation
cp "$ROOT_DIR/README.md" "$BUILD_ROOT/usr/share/doc/neuroshell/"
cp "$ROOT_DIR/LICENSE" "$BUILD_ROOT/usr/share/doc/neuroshell/copyright"

# 3. Create Control File
cat << EOF > "$BUILD_ROOT/DEBIAN/control"
Package: neuroshell
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: Abneesh Singh <abneesh@neuroshell.dev>
Description: Tier-1 Autonomous AI Terminal & Shell Engine
 NeuroShell translates plain English to system commands, prevents destructive
 operations with Zero-Trust safety guardrails, and provides sub-millisecond
 ConPTY/PTY interactive performance.
EOF

# 4. Build Package
dpkg-deb --build "$BUILD_ROOT" "$ROOT_DIR/dist/${PKG_NAME}.deb"

echo "✅ Successfully created: dist/${PKG_NAME}.deb"
