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

# Neko Songs Brand Identity
BOT_NAME: str = "Neko Songs"
BOT_BRAND_TAG: str = "🎵 NEKO SONGS"
MUSIC_BOT_VERSION: str = "2.2.0"

# Brand Palette
COLOR_MIDNIGHT_BLACK: int = 0x0B0E14
COLOR_NEON_BLUE: int = 0x00B0FF
COLOR_ELECTRIC_CYAN: int = 0x00E5FF
COLOR_WHITE: int = 0xFFFFFF
COLOR_VIOLET_ACCENT: int = 0x9B59B6

# Neko Personality Dialogues
DIALOGUE_JOIN: str = "🐱 Neko has entered the listening room!"
DIALOGUE_START: str = "🎵 Found it! Let's listen."
DIALOGUE_EMPTY_QUEUE: str = "🐾 The queue is empty. Give Neko another song?"
DIALOGUE_UNPLAYABLE: str = "😿 I found the request, but couldn't resolve a playable audio source."
DIALOGUE_NOTHING_PLAYABLE: str = DIALOGUE_UNPLAYABLE
DIALOGUE_UNAVAILABLE: str = "🐱 Neko's music source is temporarily unavailable. Please try again later."
DIALOGUE_PLAYBACK_END: str = "🎶 That was a good one!"

# Neko Songs / Music Maid Bot Credentials
# Prioritizes MUSIC_BOT_TOKEN / NEKO_SONGS_BOT_TOKEN; falls back seamlessly to DISCORD_TOKEN
MUSIC_BOT_TOKEN: str = os.getenv(
    "MUSIC_BOT_TOKEN",
    os.getenv("NEKO_SONGS_BOT_TOKEN", os.getenv("DISCORD_TOKEN", "")),
).strip()
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

# Rate Limiting
MUSIC_RATE_LIMIT_COUNT: int = int(os.getenv("MUSIC_RATE_LIMIT_COUNT", "6"))
MUSIC_RATE_LIMIT_WINDOW_SECONDS: float = float(os.getenv("MUSIC_RATE_LIMIT_WINDOW", "30.0"))

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
