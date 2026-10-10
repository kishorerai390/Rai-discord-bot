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

# Ensure root directory is in sys.path
root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

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
logger = logging.getLogger("NekoSongs")

from music_bot.bot import NekoSongsBot


def main():
    print("=" * 60)
    print("           🐱 NEKO SONGS — DISCORD MUSIC BOT            ")
    print("     Cute, Futuristic & Independent Audio Companion      ")
    print("=" * 60)

    if not is_music_token_valid():
        print("\n[ERROR] NEKO_SONGS_BOT_TOKEN is missing or unconfigured!")
        print(f"Current Token State: {get_masked_music_token()}")
        print("\nTo start Neko Songs:")
        print("1. Set NEKO_SONGS_BOT_TOKEN=<your_token> in .env (or MUSIC_BOT_TOKEN)")
        print("2. Ensure Voice and Message Content intents are enabled.")
        print("3. Rerun: npm run start:neko  OR  python music_main.py\n")
        sys.exit(2)

    # Acquire instance lock for Neko Songs bot
    from utils.instance_lock import SingleInstanceLock, InstanceAlreadyRunningError, MUSIC_LOCK_PORT
    lock_file = Path(__file__).resolve().parent.parent / ".neko_songs.lock"
    lock = SingleInstanceLock(port=MUSIC_LOCK_PORT, lock_file=lock_file)
    try:
        lock.acquire()
    except InstanceAlreadyRunningError as e:
        print(f"\n[WARNING] {e}")
        print("Startup aborted to prevent duplicate Neko Songs instances.\n")
        sys.exit(0)

    bot = NekoSongsBot()

    try:
        bot.run(MUSIC_BOT_TOKEN, log_handler=None)
    except KeyboardInterrupt:
        logger.info("🐾 Keyboard interrupt received. Stopping Neko Songs.")
    except Exception as e:
        if "LoginFailure" in type(e).__name__:
            print("\n[ERROR] Discord rejected the bot token! Please verify NEKO_SONGS_BOT_TOKEN.")
            sys.exit(2)
        logger.critical(f"Critical Neko Songs failure: {e}", exc_info=True)
        sys.exit(1)
    finally:
        lock.release()


if __name__ == "__main__":
    main()
