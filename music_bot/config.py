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
MUSIC_BOT_VERSION: str = "2.1.0"

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

# Neko Songs Bot Credentials
# Prioritizes NEKO_SONGS_BOT_TOKEN; falls back gracefully to MUSIC_BOT_TOKEN
NEKO_SONGS_BOT_TOKEN: str = os.getenv(
    "NEKO_SONGS_BOT_TOKEN", os.getenv("MUSIC_BOT_TOKEN", "")
).strip()
MUSIC_BOT_TOKEN: str = NEKO_SONGS_BOT_TOKEN

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
