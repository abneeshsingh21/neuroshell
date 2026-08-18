#!/usr/bin/env bash
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Build standalone Linux ELF binary with GCC/Clang (C++20)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

mkdir -p "$ROOT_DIR/dist"

echo "🔨 Compiling NeuroShell Linux Native C++20 Terminal..."

if command -v g++ >/dev/null 2>&1; then
    COMPILER="g++"
elif command -v clang++ >/dev/null 2>&1; then
    COMPILER="clang++"
else
    echo "❌ Error: Neither g++ nor clang++ found on system."
    exit 1
fi

$COMPILER -O3 -std=c++20 -pthread \
    "$ROOT_DIR/cpp_engine/launcher/main.cpp" \
    -o "$ROOT_DIR/dist/neuroshell"

chmod +x "$ROOT_DIR/dist/neuroshell"

echo "✅ Build Complete: dist/neuroshell"
"$ROOT_DIR/dist/neuroshell" --help || true
