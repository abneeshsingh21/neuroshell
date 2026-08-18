#!/usr/bin/env bash
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Build macOS Universal2 (Apple Silicon arm64 + Intel x86_64) Fat Binary

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

mkdir -p "$ROOT_DIR/dist"

echo "🍎 Compiling NeuroShell macOS Universal2 (arm64 + x86_64) Native C++20 Terminal..."

if ! command -v clang++ >/dev/null 2>&1; then
    echo "❌ Error: clang++ not found on system. Install Xcode Command Line Tools (xcode-select --install)."
    exit 1
fi

clang++ -O3 -std=c++20 \
    -arch arm64 -arch x86_64 \
    "$ROOT_DIR/cpp_engine/launcher/main.cpp" \
    -o "$ROOT_DIR/dist/neuroshell"

chmod +x "$ROOT_DIR/dist/neuroshell"

echo "✅ Build Complete: dist/neuroshell (Universal2 arm64 + x86_64)"
lipo -info "$ROOT_DIR/dist/neuroshell" || true
