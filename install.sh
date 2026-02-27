#!/bin/bash
# CalSynTUI+ Installation Script
# This script sets up the environment for CalSynTUI+

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 CalSynTUI+ Installer"
echo "======================"
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed."
    echo "   Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2]))}')
echo "✅ Found Python $PYTHON_VERSION"

# Create virtual environment
echo ""
echo "📦 Creating virtual environment..."
python3 -m venv "$SCRIPT_DIR/.venv"

# Activate virtual environment
source "$SCRIPT_DIR/.venv/bin/activate"

# Upgrade pip
echo ""
echo "📥 Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo ""
echo "📥 Installing dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt"

# Make launcher executable
echo ""
echo "🔧 Making CalSynTUI+ executable..."
chmod +x "$SCRIPT_DIR/CalSynTUI+"

# Create symlink in /usr/local/bin (optional, requires sudo)
if [ "$1" = "--global" ]; then
    echo ""
    echo "🔗 Creating global symlink (requires sudo)..."
    sudo ln -sf "$SCRIPT_DIR/CalSynTUI+" /usr/local/bin/CalSynTUI+
    echo "✅ You can now run 'CalSynTUI+' from anywhere!"
else
    echo ""
    echo "✅ Installation complete!"
    echo ""
    echo "📝 To run CalSynTUI+, use one of these commands:"
    echo "   cd $SCRIPT_DIR && ./CalSynTUI+"
    echo "   or"
    echo "   $SCRIPT_DIR/.venv/bin/python3 CalibreSynapseTUI.py"
    echo ""
    echo "📝 To enable global access (run from anywhere), run:"
    echo "   ./install.sh --global"
fi

echo ""
echo "✨ All done! Happy reading!"
