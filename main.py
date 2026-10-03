"""
Sentinel - All-in-One Discord Platform (Security, Anti-Nuke, AutoMod, Moderation, Music, Tickets, Logging, Utility, Fun)
Main Application Entry Point.
"""

from __future__ import annotations

import logging
import sys

# Configure UTF-8 encoding on Windows console for emoji/unicode safety
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Initialize static FFmpeg binaries if available
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception:
    pass

import config
from config import (
    DISCORD_TOKEN,
    get_log_level,
    get_masked_token,
    is_token_valid,
)

# Configure logging
logging.basicConfig(
    level=get_log_level(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOGS_DIR / "sentinel.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("SentinelBot")

# Import modular SentinelBot from core
from core.bot import SentinelBot, COGS_LIST

__all__ = ["SentinelBot", "COGS_LIST"]


def main():
    print("=" * 50)
    print("             RAI DISCORD BOT              ")
    print("=" * 50)

    # Validate token
    if not is_token_valid():
        print("\n[ERROR] DISCORD_TOKEN is missing or invalid in your .env file!")
        print(f"Current Token State: {get_masked_token()}")
        print("\nTo start the bot:")
        print("1. Open the '.env' file in this directory.")
        print("2. Set: DISCORD_TOKEN=your_actual_token_here")
        print("3. Ensure Privileged Intents (Members, Message Content) are enabled in Discord Dev Portal.")
        print("4. Rerun: python main.py\n")
        sys.exit(2)

    # Ensure single instance lock to prevent duplicate gateway listeners and message spam
    from utils.instance_lock import SingleInstanceLock, InstanceAlreadyRunningError

    instance_lock = SingleInstanceLock()
    try:
        instance_lock.acquire()
    except InstanceAlreadyRunningError as e:
        print(f"\n[WARNING] {e}")
        print("Startup aborted to prevent duplicate bot instances and message spam.\n")
        sys.exit(0)

    bot = SentinelBot()

    try:
        bot.run(DISCORD_TOKEN, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping bot.")
    except Exception as e:
        if "LoginFailure" in type(e).__name__:
            print("\n[ERROR] Discord rejected the bot token! Please check your DISCORD_TOKEN in .env.")
            sys.exit(2)
        logger.critical(f"Critical startup failure: {e}", exc_info=True)
        sys.exit(1)
    finally:
        instance_lock.release()


if __name__ == "__main__":
    main()
