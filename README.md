# Claude Code Usage Status Line

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) status line plugin that displays your **Claude Pro subscription usage** directly in the CLI — session limits, weekly limits, and reset times, all at a glance.

![Status line showing model, context window, 5-hour session usage, and 7-day weekly usage with colored progress bars](./screenshot.png)

```
[Opus] │ Ctx ████░░░░░░ 42% │ 5h █░░░░░░░░░ 16% ~4h30m │ 7d █░░░░░░░░░ 14% ~2d23h
```

## Features

- **Pro usage tracking** — 5-hour session and 7-day weekly utilization percentages
- **Reset countdowns** — time remaining until each limit resets
- **Context window** — current context window usage from Claude Code
- **Color-coded bars** — green → yellow → orange → red as usage increases
- **Zero dependencies** — pure Python stdlib, no `pip install` needed
- **Non-blocking** — background refresh via `os.fork()`, status line renders in ~40ms
- **Auto-authentication** — extracts session tokens from Chrome cookies automatically
- **Multiple themes** — Catppuccin Mocha/Latte, Tokyo Night, Gruvbox, or plain ANSI

## Requirements

- **macOS** (Chrome cookie extraction uses Keychain + SQLite)
- **Google Chrome** with an active [claude.ai](https://claude.ai) session
- **Python 3.8+**
- **Claude Code** v2.1+

## Installation

One-liner:

```bash
curl -fsSL https://raw.githubusercontent.com/victorstein/claude-code-usage-statusline/main/install.sh | bash
```

Or clone and run locally:

```bash
git clone https://github.com/victorstein/claude-code-usage-statusline.git
cd claude-code-usage-statusline
bash install.sh
```

The installer:
1. Downloads the script to `~/.claude/scripts/`
2. Configures `~/.claude/settings.json` with the status line command
3. Preserves any existing settings

### Manual Installation

If you prefer to set it up yourself:

```bash
mkdir -p ~/.claude/scripts
curl -fsSL https://raw.githubusercontent.com/victorstein/claude-code-usage-statusline/main/claude-usage-statusline.py \
  -o ~/.claude/scripts/claude-usage-statusline.py
chmod +x ~/.claude/scripts/claude-usage-statusline.py
```

Then add to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/scripts/claude-usage-statusline.py"
  }
}
```

## Usage

1. Make sure you're logged into [claude.ai](https://claude.ai) in Chrome
2. Start (or restart) a Claude Code session
3. Send a message — the status line appears at the bottom after the first response
4. On the very first run, cookies are extracted in the background. Usage data appears after the second response.

### What the numbers mean

| Segment | Description |
|---------|-------------|
| `[Opus]` | Current model |
| `Ctx 42%` | Context window utilization |
| `5h 16% ~4h30m` | 5-hour rolling session usage, resets in 4h 30m |
| `7d 14% ~2d23h` | 7-day rolling weekly usage, resets in 2d 23h |

### Color thresholds

| Usage | Color | Meaning |
|-------|-------|---------|
| 0–49% | Green | Plenty of capacity |
| 50–69% | Yellow | Moderate usage |
| 70–89% | Orange | Getting close to limits |
| 90–100% | Red | Near or at limit |

## Themes

Set the `CLAUDE_USAGE_THEME` environment variable to switch color themes:

```bash
# Add to your ~/.zshrc or ~/.bashrc
export CLAUDE_USAGE_THEME="catppuccin-mocha"  # default
```

Available themes:
- `catppuccin-mocha` — dark, pastel (default)
- `catppuccin-latte` — light, pastel
- `tokyo-night` — dark, vibrant
- `gruvbox` — dark, warm
- `plain` — basic ANSI colors (works everywhere)

## How It Works

1. **Claude Code** runs the script after each assistant response, piping session data (model, context window %) as JSON to stdin
2. The script reads a **cache file** (`~/.cache/claude-usage/cache.json`) for usage data
3. If the cache is stale, it **forks a background child process** to refresh data — the parent returns immediately with cached values
4. The background process:
   - Extracts `sessionKey` and `orgId` from Chrome's encrypted cookie database (via macOS Keychain + AES-128-CBC decryption)
   - Calls `https://claude.ai/api/organizations/{orgId}/usage`
   - Writes results to the cache file atomically

### Cache TTLs

| Data | TTL | Reason |
|------|-----|--------|
| Chrome cookies | 30 min | Expensive extraction (Keychain + SQLite + AES) |
| Usage API response | 60 sec | Keep data fresh without rate limiting |

### Security

- Session tokens are cached locally at `~/.cache/claude-usage/cache.json` with standard user file permissions
- No data is sent anywhere except to `claude.ai`'s own API
- The Chrome Keychain password prompt may appear on first run (macOS will ask to allow access)

## Troubleshooting

**Status line is empty / no usage data:**
- Make sure you're logged into claude.ai in Chrome
- Check if the cache was created: `cat ~/.cache/claude-usage/cache.json`
- Try running manually: `echo '{"model":{"display_name":"Opus"},"context_window":{"used_percentage":25}}' | python3 ~/.claude/scripts/claude-usage-statusline.py`

**Getting `?` for usage:**
- The API might be rate-limiting. Wait 60 seconds and send another message.
- Check if your Chrome session is still valid by visiting claude.ai

**Keychain prompt keeps appearing:**
- Click "Always Allow" when macOS asks about Chrome Safe Storage access

**Want to clear the cache:**
```bash
rm -rf ~/.cache/claude-usage/
```

## Uninstall

```bash
rm ~/.claude/scripts/claude-usage-statusline.py
rm -rf ~/.cache/claude-usage/
# Remove the "statusLine" key from ~/.claude/settings.json
```

## Credits

Inspired by [claude-code-usage-x-bar](https://github.com/GustavoGomez092/claude-code-usage-x-bar) by Gustavo Gomez.

## License

[MIT](LICENSE)
