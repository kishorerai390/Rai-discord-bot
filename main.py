"""
Sentinel - All-in-One Discord Platform (Security, Anti-Nuke, AutoMod, Moderation, Music, Tickets, Logging, Utility, Fun)
Main Application Entry Point.
"""

from __future__ import annotations

import logging
import os
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

import asyncio

# Import modular SentinelBot from core
from core.bot import SentinelBot, COGS_LIST

__all__ = ["SentinelBot", "COGS_LIST"]


async def _start_music_bot_with_restarts(music_bot, music_token, max_restarts: int = 5):
    """
    Start the music bot and automatically restart it on unexpected exit.
    Uses exponential backoff between restarts.
    """
    restart_count = 0
    backoff = 1.0

    while True:
        try:
            await music_bot.start(music_token)
            logger.info("Music bot exited cleanly.")
            break
        except asyncio.CancelledError:
            logger.info("Music bot supervisor cancelled.")
            try:
                await music_bot.close()
            except Exception:
                pass
            break
        except Exception as e:
            restart_count += 1
            logger.warning(
                f"Music bot crashed/unexpectedly stopped (attempt {restart_count}): {e}",
                exc_info=True,
            )
            if 0 < max_restarts <= restart_count:
                logger.critical("Max music bot restart attempts reached. Giving up.")
                break
            jitter = min(5.0, backoff * 0.1)
            sleep_for = backoff + (jitter * (0.5 - (ord(os.urandom(1)) / 255.0)))
            logger.info(f"Restarting music bot in {sleep_for:.1f}s...")
            await asyncio.sleep(max(1.0, sleep_for))
            backoff = min(backoff * 2.0, 300.0)


def main():
    print("=" * 60)
    print("          🛡️ RAI DISCORD BOT & MUSICMAID ECOSYSTEM 🎵         ")
    print("      Autonomous Security Sentinel + 24/7 Hi-Fi Music Engine   ")
    print("=" * 60)

    # Validate primary security token
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
    from utils.instance_lock import SingleInstanceLock, InstanceAlreadyRunningError, MUSIC_LOCK_PORT

    instance_lock = SingleInstanceLock()
    try:
        instance_lock.acquire()
    except InstanceAlreadyRunningError as e:
        print(f"\n[WARNING] {e}")
        print("Startup aborted to prevent duplicate bot instances and message spam.\n")
        sys.exit(0)

    # Detect and prepare Independent Music Bot (Neko Songs / MusicMaid)
    music_bot = None
    music_token = None
    music_lock = None
    try:
        from music_bot.config import (
            MUSIC_BOT_TOKEN,
            get_masked_music_token,
            is_music_token_valid,
        )
        if is_music_token_valid():
            from music_bot.bot import NekoSongsBot
            music_token = MUSIC_BOT_TOKEN
            music_lock_file = config.ROOT_DIR / ".neko_songs.lock"
            music_lock = SingleInstanceLock(port=MUSIC_LOCK_PORT, lock_file=music_lock_file)
            try:
                music_lock.acquire()
                music_bot = NekoSongsBot()
                print(f"[ECOSYSTEM] Music Bot configured ({get_masked_music_token()}). Running alongside Rai Sentinel 24/7.")
            except InstanceAlreadyRunningError:
                print("[WARNING] Another standalone Neko Songs process is already running. Proceeding with Rai Sentinel only.")
                music_lock = None
                music_bot = None
        else:
            print("[INFO] Music Bot token not configured. Running Rai Sentinel in standalone mode.")
    except Exception as e:
        logger.warning(f"Could not initialize Music Bot for ecosystem launcher: {e}")

    bot = SentinelBot()
    if music_bot and hasattr(bot, "keep_alive"):
        bot.keep_alive.music_bot = music_bot

    async def run_ecosystem():
        async with bot:
            if music_bot and music_token:
                music_task = asyncio.create_task(_start_music_bot_with_restarts(music_bot, music_token))
                try:
                    logger.info("Starting Rai Sentinel and supervised Neko Songs...")
                    await bot.start(DISCORD_TOKEN)
                finally:
                    if not music_task.done():
                        music_task.cancel()
                        try:
                            await music_task
                        except Exception:
                            pass
                    try:
                        await music_bot.close()
                    except Exception:
                        pass
            else:
                await bot.start(DISCORD_TOKEN)

    try:
        asyncio.run(run_ecosystem())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping ecosystem.")
    except Exception as e:
        if "LoginFailure" in type(e).__name__:
            print("\n[ERROR] Discord rejected one of the bot tokens! Please check your DISCORD_TOKEN / MUSIC_BOT_TOKEN in .env or Render.")
            sys.exit(2)
        logger.critical(f"Critical startup failure: {e}", exc_info=True)
        sys.exit(1)
    finally:
        instance_lock.release()
        if music_lock:
            try:
                music_lock.release()
            except Exception:
                pass


if __name__ == "__main__":
    main()
