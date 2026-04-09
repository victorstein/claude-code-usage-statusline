#!/usr/bin/env python3
"""Claude Code status line: shows Pro subscription usage alongside context window info.

Reads Claude Code session JSON from stdin and outputs a colored status line.
Rate limit data (5-hour and 7-day usage) is provided directly by Claude Code.

Requirements:
  - Claude Code v2.1+ (provides rate_limits in stdin JSON)
  - Python 3.8+

No pip dependencies required - uses only Python stdlib.
"""

import json
import os
import sys
from datetime import datetime, timezone

# =============================================================================
# Color Themes
# =============================================================================

RESET = "\033[0m"

# Catppuccin Mocha (default)
THEMES = {
    "catppuccin-mocha": {
        "green": "\033[38;2;166;227;161m",   # #a6e3a1
        "yellow": "\033[38;2;249;226;175m",  # #f9e2af
        "peach": "\033[38;2;250;179;135m",   # #fab387
        "red": "\033[38;2;243;139;168m",     # #f38ba8
        "accent": "\033[38;2;180;190;254m",  # #b4befe (lavender)
        "label": "\033[38;2;166;173;200m",   # #a6adc8 (subtext0)
        "dim": "\033[38;2;127;132;156m",     # #7f849c (overlay1)
    },
    "catppuccin-latte": {
        "green": "\033[38;2;64;160;43m",     # #40a02b
        "yellow": "\033[38;2;223;142;29m",   # #df8e1d
        "peach": "\033[38;2;254;100;11m",    # #fe640b
        "red": "\033[38;2;210;15;57m",       # #d20f39
        "accent": "\033[38;2;114;135;253m",  # #7287fd (lavender)
        "label": "\033[38;2;108;111;133m",   # #6c6f85 (subtext0)
        "dim": "\033[38;2;140;143;161m",     # #8c8fa1 (overlay1)
    },
    "tokyo-night": {
        "green": "\033[38;2;158;206;106m",   # #9ece6a
        "yellow": "\033[38;2;224;175;104m",  # #e0af68
        "peach": "\033[38;2;255;158;100m",   # #ff9e64
        "red": "\033[38;2;247;118;142m",     # #f7768e
        "accent": "\033[38;2;122;162;247m",  # #7aa2f7 (blue)
        "label": "\033[38;2;86;95;137m",     # #565f89 (comment)
        "dim": "\033[38;2;68;75;106m",       # #444b6a
    },
    "gruvbox": {
        "green": "\033[38;2;184;187;38m",    # #b8bb26
        "yellow": "\033[38;2;250;189;47m",   # #fabd2f
        "peach": "\033[38;2;254;128;25m",    # #fe8019
        "red": "\033[38;2;251;73;52m",       # #fb4934
        "accent": "\033[38;2;131;165;152m",  # #83a598 (blue)
        "label": "\033[38;2;168;153;132m",   # #a89984 (fg4)
        "dim": "\033[38;2;124;111;100m",     # #7c6f64 (bg4)
    },
    "plain": {
        "green": "\033[32m",
        "yellow": "\033[33m",
        "peach": "\033[33m",
        "red": "\033[31m",
        "accent": "\033[34m",
        "label": "\033[37m",
        "dim": "\033[90m",
    },
}

# Theme selection: set CLAUDE_USAGE_THEME env var, or defaults to catppuccin-mocha
THEME_NAME = os.environ.get("CLAUDE_USAGE_THEME", "catppuccin-mocha")
THEME = THEMES.get(THEME_NAME, THEMES["catppuccin-mocha"])

BAR_WIDTH = 10
BAR_FILLED = "\u2588"  # █
BAR_EMPTY = "\u2591"   # ░


# =============================================================================
# Formatting
# =============================================================================

def color_for_pct(pct):
    pct = int(pct)
    if pct >= 90:
        return THEME["red"]
    if pct >= 70:
        return THEME["peach"]
    if pct >= 50:
        return THEME["yellow"]
    return THEME["green"]


def mini_bar(pct):
    pct = int(pct)
    filled = max(0, min(BAR_WIDTH, pct * BAR_WIDTH // 100))
    color = color_for_pct(pct)
    return f"{color}{BAR_FILLED * filled}{THEME['dim']}{BAR_EMPTY * (BAR_WIDTH - filled)}{RESET}"


def format_reset_time(resets_at):
    if not resets_at:
        return ""
    try:
        reset_dt = datetime.fromtimestamp(resets_at, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = (reset_dt - now).total_seconds()
        if diff < 0:
            return "resetting"
        hours = int(diff // 3600)
        minutes = int((diff % 3600) // 60)
        if hours >= 24:
            days = hours // 24
            rem_hours = hours % 24
            return f"~{days}d{rem_hours}h"
        return f"~{hours}h{minutes:02d}m"
    except Exception:
        return ""


def format_output(session_data):
    parts = []

    model = session_data.get("model", {}).get("display_name", "")
    if model:
        parts.append(f"{THEME['accent']}[{model}]{RESET}")

    ctx = session_data.get("context_window", {})
    ctx_pct = int(ctx.get("used_percentage", 0))
    parts.append(f"{THEME['label']}Ctx{RESET} {mini_bar(ctx_pct)} {color_for_pct(ctx_pct)}{ctx_pct}%{RESET}")

    rate_limits = session_data.get("rate_limits")
    if rate_limits:
        five_hour = rate_limits.get("five_hour")
        if five_hour:
            pct = round(float(five_hour.get("used_percentage", 0)))
            reset = format_reset_time(five_hour.get("resets_at"))
            reset_str = f" {THEME['dim']}{reset}{RESET}" if reset else ""
            parts.append(f"{THEME['label']}5h{RESET} {mini_bar(pct)} {color_for_pct(pct)}{pct}%{RESET}{reset_str}")

        seven_day = rate_limits.get("seven_day")
        if seven_day:
            pct = round(float(seven_day.get("used_percentage", 0)))
            reset = format_reset_time(seven_day.get("resets_at"))
            reset_str = f" {THEME['dim']}{reset}{RESET}" if reset else ""
            parts.append(f"{THEME['label']}7d{RESET} {mini_bar(pct)} {color_for_pct(pct)}{pct}%{RESET}{reset_str}")

    sep = f" {THEME['dim']}\u2502{RESET} "
    print(sep.join(parts))


# =============================================================================
# Main
# =============================================================================

def main():
    try:
        session_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        session_data = {}

    format_output(session_data)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
