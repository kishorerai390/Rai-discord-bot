"""
Neko Songs — Independent Discord Music Bot Configuration and Secret Management.
Decoupled architecture strictly separated from Main Rai Bot.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment file (.env)
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    load_dotenv()

# Neko Songs / MusicMaid Brand Identity
BOT_NAME: str = "MusicMaid"
BOT_BRAND_TAG: str = "🐾 MUSICMAID"
MUSIC_BOT_VERSION: str = "2.2.0"

# Import Theme & Emoji Tokens
from music_bot.theme import (
    COLOR_PRIMARY,
    COLOR_CYAN,
    COLOR_MIDNIGHT,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_PREMIUM,
    COLOR_VIOLET,
)
from music_bot.emojis import EmojiManager

# Brand Palette (Backward-Compatible + Premium Theme Aliases)
COLOR_MIDNIGHT_BLACK: int = COLOR_MIDNIGHT
COLOR_NEON_BLUE: int = COLOR_INFO
COLOR_ELECTRIC_CYAN: int = COLOR_CYAN
COLOR_WHITE: int = 0xFFFFFF
COLOR_VIOLET_ACCENT: int = COLOR_PRIMARY

# Neko / MusicMaid Personality Dialogues
DIALOGUE_JOIN: str = "🐾 MusicMaid has entered the listening room!"
DIALOGUE_START: str = "🎵 Found it! Let's listen."
DIALOGUE_EMPTY_QUEUE: str = "🐾 The queue is empty. Ready for another song!"
DIALOGUE_UNPLAYABLE: str = "😿 I found the request, but couldn't resolve a playable audio source."
DIALOGUE_NOTHING_PLAYABLE: str = DIALOGUE_UNPLAYABLE
DIALOGUE_UNAVAILABLE: str = "🐾 Music source is temporarily unavailable. Please try again later."
DIALOGUE_PLAYBACK_END: str = "🎶 That was a good one!"


def _clean_token(t: Optional[str]) -> str:
    if not t:
        return ""
    t = str(t).strip()
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    return t

# Neko Songs / Music Maid Bot Credentials
# Prioritizes MUSIC_BOT_TOKEN / NEKO_SONGS_BOT_TOKEN; falls back seamlessly to DISCORD_TOKEN
MUSIC_BOT_TOKEN: str = (
    _clean_token(os.getenv("MUSIC_BOT_TOKEN"))
    or _clean_token(os.getenv("NEKO_SONGS_BOT_TOKEN"))
    or _clean_token(os.getenv("DISCORD_TOKEN"))
    or _clean_token(os.getenv("BOT_TOKEN"))
)
NEKO_SONGS_BOT_TOKEN: str = MUSIC_BOT_TOKEN

MUSIC_BOT_ID: int = int(os.getenv("MUSIC_BOT_ID", "1556676516274905218"))
MUSIC_PREFIX: str = os.getenv("MUSIC_BOT_PREFIX", "m!").strip()
LOG_LEVEL_STR: str = os.getenv("LOG_LEVEL", "INFO").upper()

# Database path for independent Music Bot state
_db_env = os.getenv("MUSIC_DATABASE_PATH", "data/music.db").strip()
MUSIC_DATABASE_PATH: Path = BASE_DIR / _db_env if not Path(_db_env).is_absolute() else Path(_db_env)

# Directories
MUSIC_LOGS_DIR: Path = BASE_DIR / "logs" / "music"
MUSIC_LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Audio / Player Settings
MAX_QUEUE_SIZE: int = int(os.getenv("MUSIC_MAX_QUEUE_SIZE", "200"))
DEFAULT_VOLUME: int = int(os.getenv("MUSIC_DEFAULT_VOLUME", "80"))
AUTO_LEAVE_TIMEOUT_SECONDS: int = int(os.getenv("MUSIC_AUTO_LEAVE_TIMEOUT", "300"))
COMMAND_SYNC_MODE: str = os.getenv("COMMAND_SYNC_MODE", "global").lower().strip()
_test_guild_raw = os.getenv("TEST_GUILD_ID", "").strip()
TEST_GUILD_ID: Optional[int] = int(_test_guild_raw) if _test_guild_raw.isdigit() else None

# Lavalink Settings (Optional)
LAVALINK_ENABLED: bool = os.getenv("LAVALINK_ENABLED", "false").lower() == "true"
LAVALINK_HOST: str = os.getenv("LAVALINK_HOST", "127.0.0.1")
LAVALINK_PORT: int = int(os.getenv("LAVALINK_PORT", "2333"))
LAVALINK_PASSWORD: str = os.getenv("LAVALINK_PASSWORD", "youshallnotpass")

# Optional Redis Cache
REDIS_URL: str = os.getenv("REDIS_URL", "").strip()

# Volume and Premium Limits
STANDARD_VOLUME_CAP: int = int(os.getenv("STANDARD_VOLUME_CAP", "100"))
PREMIUM_VOLUME_CAP: int = int(os.getenv("PREMIUM_VOLUME_CAP", "150"))

# Rate Limiting
MUSIC_RATE_LIMIT_COUNT: int = int(os.getenv("MUSIC_RATE_LIMIT_COUNT", "6"))
MUSIC_RATE_LIMIT_WINDOW_SECONDS: float = float(os.getenv("MUSIC_RATE_LIMIT_WINDOW", "30.0"))

# Public Website and Web Platform URLs
MUSICMAID_DEFAULT_URL: str = "https://rai-discord-bot.onrender.com"


def is_valid_public_https_url(url: Optional[str]) -> bool:
    """Validate that a URL is a legitimate public HTTPS/HTTP URL not bound to localhost."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip()
    try:
        from urllib.parse import urlparse
        parsed = urlparse(u)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = (parsed.hostname or "").lower().strip()
        if not hostname:
            return False
        # Reject loopback and local addresses
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return False
        if hostname.startswith("192.168.") or hostname.startswith("10.") or hostname.endswith(".local"):
            return False
        # Public domains must have at least one period
        if "." not in hostname:
            return False
        return True
    except Exception:
        return False


def get_musicmaid_website_url() -> Optional[str]:
    """
    Resolve and validate the authoritative public MusicMaid website URL.
    Prioritizes:
    1. MUSICMAID_WEBSITE_URL
    2. RENDER_EXTERNAL_URL
    3. PUBLIC_URL
    4. WEB_BASE_URL
    5. Fallback production default: https://rai-discord-bot.onrender.com
    Returns None if no valid public URL is configured or if only localhost is provided.
    """
    candidates = [
        os.getenv("MUSICMAID_WEBSITE_URL", "").strip(),
        os.getenv("RENDER_EXTERNAL_URL", "").strip(),
        os.getenv("PUBLIC_URL", "").strip(),
        os.getenv("WEB_BASE_URL", "").strip(),
        MUSICMAID_DEFAULT_URL,
    ]
    for cand in candidates:
        if cand and is_valid_public_https_url(cand):
            return cand.rstrip("/")
    return None


def get_premium_plans_url() -> Optional[str]:
    """
    Resolve and validate the optional MusicMaid premium plans URL if one exists.
    Returns configured MUSICMAID_PREMIUM_URL or falls back to {get_website_url()}/premium.
    """
    prem_cand = os.getenv("MUSICMAID_PREMIUM_URL", "").strip()
    if prem_cand and is_valid_public_https_url(prem_cand):
        return prem_cand.rstrip("/")
    base = get_website_url()
    if base:
        return f"{base}/premium"
    return None


# =============================================================================
# STRIPE PAYMENT & SUBSCRIPTION SETTINGS
# =============================================================================
STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip()
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_PRICE_MONTHLY: str = os.getenv("STRIPE_PRICE_MONTHLY", "").strip()
STRIPE_PRICE_YEARLY: str = os.getenv("STRIPE_PRICE_YEARLY", "").strip()
PREMIUM_CURRENCY: str = os.getenv("PREMIUM_CURRENCY", "USD").strip().upper()
PREMIUM_MONTHLY_AMOUNT_CENTS: int = int(os.getenv("PREMIUM_MONTHLY_AMOUNT_CENTS", "499"))
PREMIUM_YEARLY_AMOUNT_CENTS: int = int(os.getenv("PREMIUM_YEARLY_AMOUNT_CENTS", "4999"))


def is_stripe_configured() -> bool:
    """Return True if Stripe secret key is present."""
    return bool(STRIPE_SECRET_KEY)


def get_payment_public_config() -> dict[str, Any]:
    """Return public payment provider details and plans for frontend rendering."""
    return {
        "configured": is_stripe_configured(),
        "provider": "stripe",
        "publishable_key": STRIPE_PUBLISHABLE_KEY,
        "currency": PREMIUM_CURRENCY,
        "plans": {
            "monthly": {
                "id": "monthly",
                "name": "MusicMaid Premium Monthly",
                "price_id": STRIPE_PRICE_MONTHLY,
                "amount": PREMIUM_MONTHLY_AMOUNT_CENTS / 100.0,
                "amount_cents": PREMIUM_MONTHLY_AMOUNT_CENTS,
                "interval": "month",
                "badge": "MOST POPULAR",
            },
            "yearly": {
                "id": "yearly",
                "name": "MusicMaid Premium Yearly",
                "price_id": STRIPE_PRICE_YEARLY,
                "amount": PREMIUM_YEARLY_AMOUNT_CENTS / 100.0,
                "amount_cents": PREMIUM_YEARLY_AMOUNT_CENTS,
                "interval": "year",
                "badge": "BEST VALUE (2 MONTHS FREE)",
            },
        },
    }


# Spotify Web API Settings & OAuth Configuration
SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
SPOTIFY_REDIRECT_URI: str = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback").strip()



def is_spotify_configured() -> bool:
    """Check if official Spotify Web API credentials are provided."""
    return bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET)


def get_masked_spotify_credentials() -> dict[str, str]:
    """Return masked credentials for diagnostics without leaking secrets."""
    cid_masked = f"{SPOTIFY_CLIENT_ID[:4]}...{SPOTIFY_CLIENT_ID[-4:]}" if len(SPOTIFY_CLIENT_ID) >= 8 else ("SET" if SPOTIFY_CLIENT_ID else "NOT_SET")
    sec_masked = f"{SPOTIFY_CLIENT_SECRET[:3]}...{SPOTIFY_CLIENT_SECRET[-3:]}" if len(SPOTIFY_CLIENT_SECRET) >= 6 else ("SET" if SPOTIFY_CLIENT_SECRET else "NOT_SET")
    return {
        "client_id": cid_masked,
        "client_secret": sec_masked,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "is_configured": str(is_spotify_configured()),
    }



def is_music_token_valid() -> bool:
    """Validate token format without revealing its content."""
    tok = NEKO_SONGS_BOT_TOKEN
    if not tok:
        return False
    parts = tok.split(".")
    return len(parts) >= 2 and len(tok) > 30


def get_masked_music_token() -> str:
    """Return a masked representation of the token for diagnostics."""
    tok = NEKO_SONGS_BOT_TOKEN
    if not tok:
        return "NOT_SET"
    if len(tok) < 10:
        return "INVALID_TOO_SHORT"
    return f"{tok[:4]}...{tok[-4:]}"
