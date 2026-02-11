#!/usr/bin/env python3
"""Claude Code status line: shows Pro subscription usage alongside context window info.

Reads Claude Code session JSON from stdin, fetches usage data from claude.ai API
(with Chrome cookie auto-extraction on macOS), and outputs a colored status line.

Requirements:
  - macOS (for Chrome cookie extraction via Keychain)
  - Google Chrome with an active claude.ai session
  - Python 3.8+
  - openssl CLI (ships with macOS)

No pip dependencies required - uses only Python stdlib and macOS system tools.

Cache: ~/.cache/claude-usage/cache.json
"""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

# =============================================================================
# Constants
# =============================================================================

HOME = os.path.expanduser("~")
CACHE_DIR = os.path.join(HOME, ".cache", "claude-usage")
CACHE_FILE = os.path.join(CACHE_DIR, "cache.json")
LOCK_FILE = os.path.join(CACHE_DIR, "cache.lock")

COOKIE_TTL = 1800  # 30 minutes
USAGE_TTL = 60  # 60 seconds
LOCK_STALE_SECONDS = 30
SUBPROCESS_TIMEOUT = 5

CHROME_BASE = os.path.join(HOME, "Library", "Application Support", "Google", "Chrome")
CHROME_PROFILES = ["Default", "Profile 1", "Profile 2", "Profile 3"]

API_BASE = "https://claude.ai/api/organizations"

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
# Stdin parsing
# =============================================================================

def parse_stdin():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data


# =============================================================================
# Cache
# =============================================================================

def load_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(cache):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp_path = CACHE_FILE + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(cache, f)
        os.rename(tmp_path, CACHE_FILE)
    except OSError:
        pass


def is_stale(entry, ttl_key="expires_at"):
    if not entry or ttl_key not in entry:
        return True
    return time.time() > entry[ttl_key]


def acquire_lock():
    try:
        if os.path.exists(LOCK_FILE):
            lock_age = time.time() - os.path.getmtime(LOCK_FILE)
            if lock_age < LOCK_STALE_SECONDS:
                return False
            os.unlink(LOCK_FILE)
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except OSError:
        return False


def release_lock():
    try:
        os.unlink(LOCK_FILE)
    except OSError:
        pass


# =============================================================================
# Chrome cookie extraction (macOS)
# =============================================================================

def get_chrome_encryption_key():
    result = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage", "-a", "Chrome"],
        capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    password = result.stdout.strip()
    return hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), b"saltysalt", 1003, dklen=16)


def decrypt_cookie(encrypted_value, key, db_version):
    if not encrypted_value or len(encrypted_value) < 4:
        return ""
    prefix = encrypted_value[:3]
    if prefix not in (b"v10", b"v11"):
        return ""
    ciphertext = encrypted_value[3:]
    hex_key = key.hex()
    hex_iv = "20" * 16

    result = subprocess.run(
        ["openssl", "enc", "-d", "-aes-128-cbc", "-K", hex_key, "-iv", hex_iv, "-nopad"],
        input=ciphertext, capture_output=True, timeout=SUBPROCESS_TIMEOUT,
    )
    if result.returncode != 0:
        return ""
    decrypted = result.stdout
    if not decrypted:
        return ""

    # Strip PKCS7 padding
    pad_len = decrypted[-1]
    if 1 <= pad_len <= 16 and all(b == pad_len for b in decrypted[-pad_len:]):
        decrypted = decrypted[:-pad_len]

    # Chrome 130+ (DB version >= 24): skip 32-byte SHA256 prefix
    if db_version >= 24 and len(decrypted) > 32:
        decrypted = decrypted[32:]

    try:
        return decrypted.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def extract_chrome_cookies():
    key = get_chrome_encryption_key()
    if not key:
        return None

    for profile in CHROME_PROFILES:
        cookies_path = os.path.join(CHROME_BASE, profile, "Cookies")
        if not os.path.exists(cookies_path):
            continue

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(tmp_fd)
        try:
            shutil.copy2(cookies_path, tmp_path)
            for ext in ("-wal", "-shm"):
                src = cookies_path + ext
                if os.path.exists(src):
                    shutil.copy2(src, tmp_path + ext)

            conn = sqlite3.connect(tmp_path)
            try:
                db_version = 0
                try:
                    row = conn.execute("SELECT value FROM meta WHERE key='version'").fetchone()
                    if row:
                        db_version = int(row[0])
                except Exception:
                    pass

                rows = conn.execute(
                    "SELECT name, encrypted_value, host_key FROM cookies "
                    "WHERE host_key IN ('.claude.ai', '.claude.com', 'claude.ai', 'claude.com') "
                    "AND name IN ('sessionKey', 'lastActiveOrg')"
                ).fetchall()
            finally:
                conn.close()

            session_key = None
            org_id = None
            for name, encrypted_value, _host_key in rows:
                decrypted = decrypt_cookie(encrypted_value, key, db_version)
                if not decrypted:
                    continue
                if name == "sessionKey":
                    session_key = decrypted
                elif name == "lastActiveOrg":
                    org_id = decrypted

            if session_key and org_id:
                return {"session_key": session_key, "org_id": org_id}
        except Exception:
            continue
        finally:
            for ext in ("", "-wal", "-shm"):
                try:
                    os.unlink(tmp_path + ext)
                except OSError:
                    pass

    return None


# =============================================================================
# API fetch
# =============================================================================

def fetch_usage(session_key, org_id):
    url = f"{API_BASE}/{org_id}/usage"
    req = urllib.request.Request(url, headers={
        "Cookie": f"sessionKey={session_key}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://claude.ai/",
        "Origin": "https://claude.ai",
    })
    try:
        with urllib.request.urlopen(req, timeout=SUBPROCESS_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


# =============================================================================
# Background refresh
# =============================================================================

def background_refresh(cache):
    if not acquire_lock():
        return

    pid = os.fork()
    if pid != 0:
        return

    # Child process
    try:
        os.setsid()
        now = time.time()

        cookies = cache.get("cookies")
        if is_stale(cookies):
            result = extract_chrome_cookies()
            if result:
                cache["cookies"] = {
                    **result,
                    "fetched_at": now,
                    "expires_at": now + COOKIE_TTL,
                }
                save_cache(cache)
            else:
                release_lock()
                os._exit(0)

        cookies = cache.get("cookies", {})
        sk = cookies.get("session_key")
        oid = cookies.get("org_id")
        if not sk or not oid:
            release_lock()
            os._exit(0)

        usage = fetch_usage(sk, oid)
        if usage:
            cache["usage"] = {
                **usage,
                "fetched_at": now,
                "expires_at": now + USAGE_TTL,
            }
            save_cache(cache)
    except Exception:
        pass
    finally:
        release_lock()
        os._exit(0)


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
        ts = resets_at.replace("Z", "+00:00")
        from datetime import datetime, timezone
        reset_dt = datetime.fromisoformat(ts)
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


def format_output(session_data, usage):
    parts = []

    model = session_data.get("model", {}).get("display_name", "")
    if model:
        parts.append(f"{THEME['accent']}[{model}]{RESET}")

    ctx = session_data.get("context_window", {})
    ctx_pct = int(ctx.get("used_percentage", 0))
    parts.append(f"{THEME['label']}Ctx{RESET} {mini_bar(ctx_pct)} {color_for_pct(ctx_pct)}{ctx_pct}%{RESET}")

    if usage:
        five_hour = usage.get("five_hour")
        if five_hour:
            pct = int(five_hour.get("utilization", 0))
            reset = format_reset_time(five_hour.get("resets_at"))
            reset_str = f" {THEME['dim']}{reset}{RESET}" if reset else ""
            parts.append(f"{THEME['label']}5h{RESET} {mini_bar(pct)} {color_for_pct(pct)}{pct}%{RESET}{reset_str}")

        seven_day = usage.get("seven_day")
        if seven_day:
            pct = int(seven_day.get("utilization", 0))
            reset = format_reset_time(seven_day.get("resets_at"))
            reset_str = f" {THEME['dim']}{reset}{RESET}" if reset else ""
            parts.append(f"{THEME['label']}7d{RESET} {mini_bar(pct)} {color_for_pct(pct)}{pct}%{RESET}{reset_str}")
    elif usage is None:
        pass
    else:
        parts.append(f"{THEME['dim']}Usage: ?{RESET}")

    sep = f" {THEME['dim']}\u2502{RESET} "
    print(sep.join(parts))


# =============================================================================
# Main
# =============================================================================

def main():
    session_data = parse_stdin()
    cache = load_cache()

    cookies = cache.get("cookies")
    usage_entry = cache.get("usage")

    needs_refresh = is_stale(cookies) or is_stale(usage_entry)
    if needs_refresh:
        background_refresh(cache)

    usage = None
    if usage_entry and "five_hour" in usage_entry:
        usage = usage_entry

    format_output(session_data, usage)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
