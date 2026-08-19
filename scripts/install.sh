#!/usr/bin/env bash
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# NeuroShell Universal 1-Line Installer for macOS and Linux

set -e

VERSION="5.7.0"
REPO="abneeshsingh21/neuroshell"
GITHUB_RELEASE="https://github.com/${REPO}/releases/download/v${VERSION}"
INSTALL_DIR="/usr/local/bin"

# ANSI Colors
CYAN='\033[38;2;56;189;248m'
GREEN='\033[38;2;74;222;128m'
MAGENTA='\033[38;2;192;132;252m'
RED='\033[38;2;248;113;113m'
RESET='\033[0m'
BOLD='\033[1m'

printf "${CYAN}╭────────────────────────────────────────────────────────╮\n"
printf "│  ${BOLD}⌬ NeuroShell v%s${RESET}${CYAN} — Native Enterprise Terminal    │\n" "$VERSION"
printf "╰────────────────────────────────────────────────────────╯${RESET}\n\n"

# 1. Detect OS & CPU Architecture
OS="$(uname -s)"
ARCH="$(uname -m)"

case "${OS}" in
    Darwin*)
        PLATFORM="macos"
        ASSET="NeuroShell-macos-universal.tar.gz"
        ;;
    Linux*)
        PLATFORM="linux"
        if [ "$ARCH" = "x86_64" ]; then
            ASSET="NeuroShell-linux-x86_64.tar.gz"
        elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
            ASSET="NeuroShell-linux-aarch64.tar.gz"
        else
            echo "${RED}❌ Unsupported Linux CPU Architecture: ${ARCH}${RESET}"
            exit 1
        fi
        ;;
    *)
        echo "${RED}❌ Unsupported Operating System: ${OS}${RESET}"
        exit 1
        ;;
esac

echo "🔍 Detected Platform: ${BOLD}${PLATFORM} (${ARCH})${RESET}"

# 2. Download from GitHub Release
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "⬇️  Downloading ${ASSET} from GitHub Releases..."
DOWNLOAD_URL="${GITHUB_RELEASE}/${ASSET}"
curl -fsSL "${DOWNLOAD_URL}" -o "${TMP_DIR}/${ASSET}" || {
    echo "${RED}❌ Failed to download from ${DOWNLOAD_URL}.${RESET}"
    exit 1
}

# 3. Extract & Install
echo "📦 Extracting release archive..."
tar -xzf "${TMP_DIR}/${ASSET}" -C "${TMP_DIR}"

APP_DIR="/usr/local/share/neuroshell"

if [ "$EUID" -ne 0 ] && [ ! -w "${INSTALL_DIR}" ]; then
    SUDO="sudo"
else
    SUDO=""
fi

echo "🚀 Installing NeuroShell to ${INSTALL_DIR}/neuroshell..."
$SUDO mkdir -p "${APP_DIR}" "${INSTALL_DIR}"
$SUDO cp -R "${TMP_DIR}"/* "${APP_DIR}/"
$SUDO chmod +x "${APP_DIR}/neuroshell"
if [ -f "${APP_DIR}/neuroshell.command" ]; then
    $SUDO chmod +x "${APP_DIR}/neuroshell.command"
fi
$SUDO ln -sf "${APP_DIR}/neuroshell" "${INSTALL_DIR}/neuroshell"

# 4. Success Banner
printf "\n${GREEN}✨ NeuroShell v%s successfully installed to %s/neuroshell!${RESET}\n\n" "$VERSION" "$INSTALL_DIR"
echo "  • Open Terminal: Run ${BOLD}neuroshell${RESET}"
echo "  • Command Palette: Press ${BOLD}[F1]${RESET} or ${BOLD}[Ctrl+P]${RESET}"
echo "  • Shell Hooks: Add ${BOLD}eval \"\$(neuroshell init zsh)\"${RESET} to ~/.zshrc"
echo ""
