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

# Student Developer Mode & Payment Gateway Toggles
# PAYMENTS_ENABLED defaults to False for safe, student/developer-friendly showcase mode.
# When False, the website displays plans & feature comparisons in "Developer Preview / Coming Soon",
# checkout buttons are disabled with friendly guidance, and no real transactions are processed.
PAYMENTS_ENABLED: bool = os.getenv("PAYMENTS_ENABLED", "false").lower() == "true"

# MusicMaid Brand Identity
BOT_NAME: str = os.getenv("BOT_NAME", "MusicMaid")
STUDIO_BRAND_NAME: str = "MusicMaid Studios"
BOT_BRAND_TAG: str = "🎧 MUSICMAID"
BOT_ABOUT_ME: str = "Your music, your vibe. 🎧"
BOT_TAGLINE: str = "Your music, your vibe. 🎧"
MUSIC_BOT_VERSION: str = "2.7.0"

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

# Personality Dialogues
DIALOGUE_JOIN: str = "✨ MusicMaid has entered the listening room!"
DIALOGUE_START: str = "🎵 Found it! Let's listen."
DIALOGUE_EMPTY_QUEUE: str = "✨ The queue is empty. Ready for another song!"
DIALOGUE_UNPLAYABLE: str = "😿 I found the request, but couldn't resolve a playable audio source."
DIALOGUE_NOTHING_PLAYABLE: str = DIALOGUE_UNPLAYABLE
DIALOGUE_UNAVAILABLE: str = "✨ Music source is temporarily unavailable. Please try again later."
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

# Bot Owner & Founder IDs (Full unconditional VIP bypass for all Premium features)
_raw_owners = (
    os.getenv("BOT_CREATOR_ID")
    or os.getenv("CREATOR_ID")
    or os.getenv("DEVELOPER_ID")
    or os.getenv("BOT_OWNER_IDS")
    or os.getenv("BOT_OWNER_ID")
    or os.getenv("OWNER_ID")
    or os.getenv("FOUNDER_ID")
    or "1457380609641938981"
)
BOT_OWNER_IDS: set[int] = {
    int(x.strip()) for x in _raw_owners.replace(";", ",").split(",") if x.strip().isdigit()
}
# Guarantee primary developers / founders Rai and server owners are always included
BOT_OWNER_IDS.add(1457380609641938981)
BOT_OWNER_IDS.add(1457382179981099090)
BOT_OWNER_ID: int = next(iter(BOT_OWNER_IDS), 1457380609641938981)


def register_bot_owner(user_id: Optional[int | str]) -> None:
    """Dynamically register a bot owner/creator ID (e.g. from Discord application_info)."""
    if not user_id:
        return
    try:
        uid = int(user_id)
        BOT_OWNER_IDS.add(uid)
    except (ValueError, TypeError):
        pass


def is_bot_owner(user_id: Optional[int | str]) -> bool:
    """Return True if user_id matches a configured Bot Owner/Developer."""
    if not user_id:
        return False
    try:
        uid = int(user_id)
        return uid in BOT_OWNER_IDS or uid in (1457380609641938981, 1457382179981099090)
    except (ValueError, TypeError):
        return False

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
        os.getenv("PUBLIC_BASE_URL", "").strip(),
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


# Function aliases for website URL resolution
get_website_url = get_musicmaid_website_url
get_public_web_url = get_musicmaid_website_url


def get_premium_plans_url() -> Optional[str]:
    """
    Resolve and validate the optional MusicMaid premium plans URL if one exists.
    Returns None if not configured, nonexistent, or invalid.
    """
    for key in ("MUSICMAID_PREMIUM_URL", "PREMIUM_PLANS_URL"):
        cand = os.getenv(key, "").strip()
        if cand and is_valid_public_https_url(cand):
            return cand.rstrip("/")
    return None


# =============================================================================
# PAYMENT & SUBSCRIPTION SETTINGS (RAZORPAY & STRIPE)
# =============================================================================
PAYMENT_PROVIDER: str = os.getenv("PAYMENT_PROVIDER", "razorpay").lower().strip()

# Razorpay Settings (Primary for India - UPI, Cards, NetBanking)
RAZORPAY_KEY_ID: str = os.getenv("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET: str = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
RAZORPAY_WEBHOOK_SECRET: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()
PREMIUM_MONTHLY_AMOUNT_INR: int = int(os.getenv("PREMIUM_MONTHLY_AMOUNT_INR", "199"))
PREMIUM_YEARLY_AMOUNT_INR: int = int(os.getenv("PREMIUM_YEARLY_AMOUNT_INR", "1799"))

# Stripe Settings (International fallback)
STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip()
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_PRICE_MONTHLY: str = os.getenv("STRIPE_PRICE_MONTHLY", "").strip()
STRIPE_PRICE_YEARLY: str = os.getenv("STRIPE_PRICE_YEARLY", "").strip()
PREMIUM_CURRENCY: str = os.getenv("PREMIUM_CURRENCY", "INR" if PAYMENT_PROVIDER == "razorpay" else "USD").strip().upper()
PREMIUM_MONTHLY_AMOUNT_CENTS: int = int(os.getenv("PREMIUM_MONTHLY_AMOUNT_CENTS", "499"))
PREMIUM_YEARLY_AMOUNT_CENTS: int = int(os.getenv("PREMIUM_YEARLY_AMOUNT_CENTS", "4999"))


def is_razorpay_configured() -> bool:
    """Return True if Razorpay key and secret are present."""
    return bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


def is_stripe_configured() -> bool:
    """Return True if Stripe secret key is present."""
    return bool(STRIPE_SECRET_KEY)


def is_payment_configured() -> bool:
    """Return True if the selected payment provider has valid credentials."""
    if PAYMENT_PROVIDER == "razorpay":
        return is_razorpay_configured()
    return is_stripe_configured()


def is_payment_enabled() -> bool:
    """Return True only if payments are explicitly enabled AND provider is configured."""
    return PAYMENTS_ENABLED and is_payment_configured()


def get_payment_public_config() -> dict[str, Any]:
    """Return public payment provider details and plans for frontend rendering."""
    provider = PAYMENT_PROVIDER
    if provider == "razorpay":
        currency = "INR"
        currency_symbol = "₹"
        monthly_amt = PREMIUM_MONTHLY_AMOUNT_INR
        yearly_amt = PREMIUM_YEARLY_AMOUNT_INR
        pub_key = RAZORPAY_KEY_ID if is_payment_enabled() else ""
    else:
        currency = PREMIUM_CURRENCY
        currency_symbol = "$"
        monthly_amt = PREMIUM_MONTHLY_AMOUNT_CENTS / 100.0
        yearly_amt = PREMIUM_YEARLY_AMOUNT_CENTS / 100.0
        pub_key = STRIPE_PUBLISHABLE_KEY if is_payment_enabled() else ""

    return {
        "configured": is_payment_configured(),
        "enabled": is_payment_enabled(),
        "payments_enabled": PAYMENTS_ENABLED,
        "is_student_mode": not PAYMENTS_ENABLED,
        "student_notice": (
            "Student Developer Showcase Mode: Real transactions are currently disabled (PAYMENTS_ENABLED=false). "
            "Explore features, plan architecture, and comparisons below."
        ),
        "provider": provider,
        "publishable_key": pub_key,
        "key_id": RAZORPAY_KEY_ID if is_payment_enabled() else "",
        "currency": currency,
        "currency_symbol": currency_symbol,
        "plans": {
            "monthly": {
                "id": "monthly",
                "name": "NyxTune Premium Monthly",
                "amount": monthly_amt,
                "amount_formatted": f"{currency_symbol}{monthly_amt}",
                "interval": "month",
                "badge": "MOST POPULAR",
            },
            "yearly": {
                "id": "yearly",
                "name": "NyxTune Premium Yearly",
                "amount": yearly_amt,
                "amount_formatted": f"{currency_symbol}{yearly_amt}",
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
