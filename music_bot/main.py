"""
Rai Music Bot Main Entry Point.
Launches the dedicated, independent Music Discord application.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Configure UTF-8 on Windows
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

from music_bot.config import (
    MUSIC_BOT_TOKEN,
    MUSIC_LOGS_DIR,
    get_masked_music_token,
    is_music_token_valid,
)

# Configure logging to dedicated music log file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(MUSIC_LOGS_DIR / "music.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("RaiMusic")

from music_bot.bot import RaiMusicBot


def main():
    print("=" * 55)
    print("             RAI MUSIC DISCORD BOT               ")
    print("         Independent Audio Architecture          ")
    print("=" * 55)

    if not is_music_token_valid():
        print("\n[ERROR] MUSIC_BOT_TOKEN is missing or invalid in your .env file!")
        print(f"Current Token State: {get_masked_music_token()}")
        print("\nTo start the music bot:")
        print("1. Set MUSIC_BOT_TOKEN in .env")
        print("2. Ensure Voice & Message Content intents are enabled.")
        print("3. Rerun: python music_main.py\n")
        sys.exit(2)

    # Acquire instance lock for music bot
    from utils.instance_lock import SingleInstanceLock, InstanceAlreadyRunningError
    lock_file = Path(__file__).resolve().parent.parent / ".music_bot.lock"
    lock = SingleInstanceLock(lock_file=lock_file)
    try:
        lock.acquire()
    except InstanceAlreadyRunningError as e:
        print(f"\n[WARNING] {e}")
        print("Startup aborted to prevent duplicate Music Bot instances.\n")
        sys.exit(0)

    bot = RaiMusicBot()

    try:
        bot.run(MUSIC_BOT_TOKEN, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping Rai Music Bot.")
    except Exception as e:
        if "LoginFailure" in type(e).__name__:
            print("\n[ERROR] Discord rejected MUSIC_BOT_TOKEN! Please check your credentials.")
            sys.exit(2)
        logger.critical(f"Critical music bot failure: {e}", exc_info=True)
        sys.exit(1)
    finally:
        lock.release()


if __name__ == "__main__":
    main()
