"""
Rai Core Settings and Environment Configuration.
Loads environment variables, paths, database endpoints, and aesthetic color tokens.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment file (.env)
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    load_dotenv()

# Discord Bot Credentials & Settings
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "").strip()
BOT_PREFIX: str = os.getenv("BOT_PREFIX", "!").strip()
BOT_VERSION: str = "2.6.0"
LOG_LEVEL_STR: str = os.getenv("LOG_LEVEL", "INFO").upper()

# Database path & connection
_db_env = os.getenv("DATABASE_PATH", "data/bot.db").strip()
DATABASE_PATH: Path = BASE_DIR / _db_env if not Path(_db_env).is_absolute() else Path(_db_env)
DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")  # For PostgreSQL migration support

# Slash Command Sync Mode
COMMAND_SYNC_MODE: str = os.getenv("COMMAND_SYNC_MODE", "global").lower().strip()
_test_guild_raw = os.getenv("TEST_GUILD_ID", "").strip()
TEST_GUILD_ID: Optional[int] = int(_test_guild_raw) if _test_guild_raw.isdigit() else None

# Lavalink Settings (Optional for advanced music backend)
LAVALINK_HOST: str = os.getenv("LAVALINK_HOST", "127.0.0.1")
LAVALINK_PORT: int = int(os.getenv("LAVALINK_PORT", "2333"))
LAVALINK_PASSWORD: str = os.getenv("LAVALINK_PASSWORD", "youshallnotpass")
LAVALINK_ENABLED: bool = os.getenv("LAVALINK_ENABLED", "false").lower() == "true"

# Web Platform & Discord OAuth2 Settings
WEB_PORT: int = int(os.getenv("PORT", os.getenv("WEB_PORT", "8080")))
_raw_client_id = os.getenv("DISCORD_CLIENT_ID", "").strip()
if not _raw_client_id and DISCORD_TOKEN and "." in DISCORD_TOKEN:
    try:
        import base64
        _p1 = DISCORD_TOKEN.split(".")[0]
        _padded = _p1 + "=" * (-len(_p1) % 4)
        _extracted = base64.b64decode(_padded).decode("utf-8")
        if _extracted.isdigit():
            _raw_client_id = _extracted
    except Exception:
        pass
DISCORD_CLIENT_ID: str = _raw_client_id
DISCORD_CLIENT_SECRET: str = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
DISCORD_REDIRECT_URI: str = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8080/api/auth/callback").strip()
SESSION_SECRET: str = os.getenv("SESSION_SECRET", "rai_production_secret_key_change_in_production").strip()
_comm_guild_raw = (os.getenv("COMMUNITY_GUILD_ID") or os.getenv("TEST_GUILD_ID") or "1457382179981099090").strip()
COMMUNITY_GUILD_ID: int = int(_comm_guild_raw) if _comm_guild_raw.isdigit() else 1457382179981099090

# Resource & Rate Limit Defaults
MAX_QUEUE_SIZE: int = int(os.getenv("MAX_QUEUE_SIZE", "200"))
MAX_SAVED_PLAYLISTS_PER_USER: int = int(os.getenv("MAX_SAVED_PLAYLISTS_PER_USER", "25"))
CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "4"))
CIRCUIT_BREAKER_RESET_TIMEOUT: float = float(os.getenv("CIRCUIT_BREAKER_RESET_TIMEOUT", "60.0"))
DYNAMIC_VC_EMPTY_TIMEOUT_SECONDS: int = int(os.getenv("DYNAMIC_VC_EMPTY_TIMEOUT_SECONDS", "60"))
MUSIC_DUPLICATE_REQUEST_WINDOW_SECONDS: float = float(os.getenv("MUSIC_DUPLICATE_REQUEST_WINDOW_SECONDS", "30.0"))
MUSIC_USER_RATE_LIMIT_COUNT: int = int(os.getenv("MUSIC_USER_RATE_LIMIT_COUNT", "5"))
MUSIC_USER_RATE_LIMIT_WINDOW: float = float(os.getenv("MUSIC_USER_RATE_LIMIT_WINDOW", "60.0"))

# Required runtime directories
DATA_DIR: Path = BASE_DIR / "data"
BACKUPS_DIR: Path = DATA_DIR / "backups"
LOGS_DIR: Path = DATA_DIR / "logs"
CACHE_DIR: Path = DATA_DIR / "cache"
TRANSCRIPTS_DIR: Path = DATA_DIR / "transcripts"
TEMP_DIR: Path = DATA_DIR / "temp"

# Ensure essential runtime directories exist
for directory in (DATA_DIR, BACKUPS_DIR, LOGS_DIR, CACHE_DIR, TRANSCRIPTS_DIR, TEMP_DIR, BASE_DIR / "logs"):
    directory.mkdir(parents=True, exist_ok=True)

# Discord Embed Color Palette (Hex)
class Colors:
    PRIMARY = 0x5865F2    # Blurple
    SUCCESS = 0x57F287    # Green
    WARNING = 0xFEE75C    # Yellow
    ERROR = 0xED4245      # Red
    SECURITY = 0xEB459E   # Magenta/Red Alert
    INFO = 0x3498DB       # Light Blue
    DARK = 0x2B2D31       # Dark Charcoal
    GOLD = 0xF1C40F       # Gold

# Logging setup
def get_log_level() -> int:
    return getattr(logging, LOG_LEVEL_STR, logging.INFO)

def is_token_valid() -> bool:
    """Check if the token is non-empty and has typical Discord bot token structure."""
    if not DISCORD_TOKEN:
        return False
    parts = DISCORD_TOKEN.split(".")
    return len(parts) >= 2 and len(DISCORD_TOKEN) > 30

def get_masked_token() -> str:
    """Return safely masked token representation for logs."""
    if not DISCORD_TOKEN:
        return "[MISSING]"
    if len(DISCORD_TOKEN) <= 10:
        return "[INVALID_SHORT]"
    return f"{DISCORD_TOKEN[:4]}...{DISCORD_TOKEN[-4:]}"
