#!/usr/bin/env bash
set -euo pipefail

REPO="victorstein/claude-code-usage-statusline"
RAW_URL="https://raw.githubusercontent.com/$REPO/main/claude-usage-statusline.py"
INSTALL_DIR="$HOME/.claude/scripts"
INSTALL_PATH="$INSTALL_DIR/claude-usage-statusline.py"
SETTINGS_FILE="$HOME/.claude/settings.json"

echo ""
echo "  Claude Code Usage Status Line"
echo "  =============================="
echo ""

# ── Prerequisites ──────────────────────────────────────────────────────────

if [[ "$(uname)" != "Darwin" ]]; then
    echo "  Error: This tool currently only supports macOS."
    echo "  Chrome cookie extraction requires macOS Keychain access."
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "  Error: python3 is required but not found."
    echo "  Install it via: brew install python3"
    exit 1
fi

if ! command -v openssl &>/dev/null; then
    echo "  Error: openssl is required but not found (should ship with macOS)."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 8 ]]; then
    echo "  Error: Python 3.8+ is required (found $PYTHON_VERSION)."
    exit 1
fi

echo "  Prerequisites OK (Python $PYTHON_VERSION, macOS $(sw_vers -productVersion))"
echo ""

# ── Download & install script ──────────────────────────────────────────────

echo "  Installing script to $INSTALL_PATH..."
mkdir -p "$INSTALL_DIR"

# If running from a local clone, copy from there; otherwise download
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || SCRIPT_DIR=""
if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/claude-usage-statusline.py" ]]; then
    cp "$SCRIPT_DIR/claude-usage-statusline.py" "$INSTALL_PATH"
else
    if command -v curl &>/dev/null; then
        curl -fsSL "$RAW_URL" -o "$INSTALL_PATH"
    elif command -v wget &>/dev/null; then
        wget -qO "$INSTALL_PATH" "$RAW_URL"
    else
        echo "  Error: curl or wget is required to download the script."
        exit 1
    fi
fi

chmod +x "$INSTALL_PATH"
echo "  Done."
echo ""

# ── Configure Claude Code settings ────────────────────────────────────────

if [[ -f "$SETTINGS_FILE" ]]; then
    if python3 -c "import json; d=json.load(open('$SETTINGS_FILE')); assert 'statusLine' in d" 2>/dev/null; then
        echo "  statusLine already configured in $SETTINGS_FILE"
        echo "  Current config:"
        python3 -c "import json; d=json.load(open('$SETTINGS_FILE')); print('  ' + json.dumps(d.get('statusLine')))"
        echo ""
        read -rp "  Overwrite with new config? [y/N] " answer
        if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
            echo ""
            echo "  Skipping settings update. Add manually to $SETTINGS_FILE:"
            echo ""
            echo "    \"statusLine\": {"
            echo "      \"type\": \"command\","
            echo "      \"command\": \"python3 $INSTALL_PATH\""
            echo "    }"
            echo ""
            exit 0
        fi
    fi

    python3 -c "
import json
with open('$SETTINGS_FILE') as f:
    settings = json.load(f)
settings['statusLine'] = {
    'type': 'command',
    'command': 'python3 $INSTALL_PATH'
}
with open('$SETTINGS_FILE', 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')
"
else
    mkdir -p "$(dirname "$SETTINGS_FILE")"
    cat > "$SETTINGS_FILE" << SETTINGS
{
  "statusLine": {
    "type": "command",
    "command": "python3 $INSTALL_PATH"
  }
}
SETTINGS
fi

echo "  Settings updated: $SETTINGS_FILE"
echo ""

# ── Done ───────────────────────────────────────────────────────────────────

echo "  Installation complete!"
echo ""
echo "  Next steps:"
echo "    1. Make sure you're logged into claude.ai in Chrome"
echo "    2. Start (or restart) a Claude Code session"
echo "    3. The status line appears after the first assistant response"
echo "    4. Usage data appears after the second response (first run extracts cookies)"
echo ""
echo "  Optional - set a color theme in your shell profile:"
echo "    export CLAUDE_USAGE_THEME=catppuccin-mocha   # (default)"
echo "    export CLAUDE_USAGE_THEME=tokyo-night"
echo "    export CLAUDE_USAGE_THEME=gruvbox"
echo ""
