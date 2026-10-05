"""
Rai Music Bot Configuration and Secret Management.
Independent configuration decoupled from Main Rai Bot.
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

# Music Bot Credentials
MUSIC_BOT_TOKEN: str = os.getenv("MUSIC_BOT_TOKEN", "").strip()
MUSIC_BOT_ID: int = int(os.getenv("MUSIC_BOT_ID", "1556676516274905218"))
MUSIC_BOT_VERSION: str = "2.0.0"
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
    if not MUSIC_BOT_TOKEN:
        return False
    parts = MUSIC_BOT_TOKEN.split(".")
    return len(parts) >= 2 and len(MUSIC_BOT_TOKEN) > 30


def get_masked_music_token() -> str:
    """Return a masked representation of the token for diagnostics."""
    if not MUSIC_BOT_TOKEN:
        return "NOT_SET"
    if len(MUSIC_BOT_TOKEN) < 10:
        return "INVALID_TOO_SHORT"
    return f"{MUSIC_BOT_TOKEN[:4]}...{MUSIC_BOT_TOKEN[-4:]}"
