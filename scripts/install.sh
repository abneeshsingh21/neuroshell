#!/usr/bin/env bash
# NeuroShell Linux/macOS Installation Script
# This script installs the CLI globally by creating a wrapper script.

set -e

# Detect OS
OS="$(uname -s)"
case "${OS}" in
    Linux*)     MACHINE=Linux;;
    Darwin*)    MACHINE=Mac;;
    *)          echo "Unsupported OS: ${OS}" && exit 1;;
esac

echo "========================================="
echo "🧠 Installing NeuroShell for $MACHINE"
echo "========================================="

# Ensure Python 3.10+
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed. Please install Python 3.10+."
    exit 1
fi

# Ensure pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ Error: pip3 is not installed."
    exit 1
fi

# Get absolute path of the project directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

echo "📦 Installing Python dependencies..."
python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" || {
    echo "⚠️ Failed to install dependencies globally. Attempting user install..."
    python3 -m pip install --user -r "$SCRIPT_DIR/requirements.txt"
}

INSTALL_DIR="/usr/local/bin"
BIN_NAME="neuroshell"

# Create a wrapper script
WRAPPER_SCRIPT="/tmp/neuroshell_wrapper.sh"
cat << EOF > "$WRAPPER_SCRIPT"
#!/usr/bin/env bash
export NEUROSHELL_ROOT="$SCRIPT_DIR"
export PYTHONUTF8=1
python3 "$SCRIPT_DIR/neuroshell_cli.py" "\$@"
EOF
chmod +x "$WRAPPER_SCRIPT"

echo "🔗 Creating global symlink at $INSTALL_DIR/$BIN_NAME"
if [ -w "$INSTALL_DIR" ]; then
    mv "$WRAPPER_SCRIPT" "$INSTALL_DIR/$BIN_NAME"
else
    echo "⚠️  Needs sudo to write to $INSTALL_DIR"
    sudo mv "$WRAPPER_SCRIPT" "$INSTALL_DIR/$BIN_NAME"
fi

echo "========================================="
echo "✅ Installation Complete!"
echo ""
echo "Run 'neuroshell --setup' to configure your LLM provider."
echo "========================================="
