"""
MusicMaid — Dynamic Discord Presence & Activity Management Service.
Centralizes bot presence updates across playing, idle, and recovery states.
Respects Discord Gateway rate limits and enforces strict data sanitization.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING, Any, Optional, Tuple

import discord
from music_bot.config import BOT_NAME
from music_bot.services.session_service import GuildMusicSession, PlaybackState, SessionManager

if TYPE_CHECKING:
    from music_bot.bot import RaiMusicBot

logger = logging.getLogger("MusicMaid.Presence")

# Constants
DEFAULT_IDLE_ACTIVITY: str = "Your music, your vibe. 🎧"
DEFAULT_RECOVERY_ACTIVITY: str = "Restoring session... 🔄"
MAX_ACTIVITY_LEN: int = 120  # Discord allows up to 128 chars, 120 provides safe buffer
MIN_UPDATE_INTERVAL_SECONDS: float = 20.0  # Discord gateway presence update cooldown


class DynamicPresenceService:
    """Enterprise centralized dynamic presence coordinator for MusicMaid."""

    _last_update_time: float = 0.0
    _last_signature: Optional[str] = None
    _lock = asyncio.Lock()
    _loop_task: Optional[asyncio.Task] = None

    @classmethod
    def sanitize_track_metadata(cls, title: str, artist: Optional[str] = None) -> str:
        """
        Sanitizes and truncates track title and artist into a clean Discord activity string.
        Strips URLs, tokens, and control characters to prevent leakage.
        """
        clean_title = re.sub(r"https?://\S+", "", title or "").strip()
        # Remove extra whitespace
        clean_title = re.sub(r"\s+", " ", clean_title)

        clean_artist = re.sub(r"https?://\S+", "", artist or "").strip()
        clean_artist = re.sub(r"\s+", " ", clean_artist)

        if clean_artist and clean_artist.lower() not in clean_title.lower() and clean_artist.lower() != "unknown":
            combined = f"{clean_title} • {clean_artist}"
        else:
            combined = clean_title or "Music"

        if len(combined) > MAX_ACTIVITY_LEN:
            combined = combined[: MAX_ACTIVITY_LEN - 3].rstrip() + "..."

        return combined

    @classmethod
    def resolve_target_activity(cls, bot: Any) -> Tuple[discord.Activity, discord.Status, str]:
        """
        Determines the authoritative global Discord activity across all active guild sessions:
        Priority 1: Active session recovery in progress -> 'Restoring session... 🔄'
        Priority 2: Genuine active playback -> '{title} • {artist}'
        Priority 3: Idle / Paused / Stopped -> 'Your music, your vibe. 🎧'
        """
        sm = SessionManager.get_instance() if hasattr(SessionManager, "get_instance") else None
        sessions: list[GuildMusicSession] = sm.get_all_sessions() if sm else []

        # 1. Recovery state check: only if health/recovery system confirms active recovery
        recovering_sessions = [
            s for s in sessions if getattr(s, "state", None) == PlaybackState.RECOVERING
        ]
        if recovering_sessions:
            sig = "STATE:RECOVERING"
            act = discord.Activity(
                type=discord.ActivityType.listening,
                name=DEFAULT_RECOVERY_ACTIVITY,
            )
            return act, discord.Status.online, sig

        # 2. Playing state check: strictly genuine active playback with playing voice client
        playing_sessions = []
        for s in sessions:
            vc = getattr(s, "voice_client", None)
            vc_playing = False
            vc_paused = False
            if vc:
                if hasattr(vc, "is_playing") and callable(vc.is_playing):
                    res_play = vc.is_playing()
                    vc_playing = bool(res_play) and getattr(vc, "channel", None) is not None
                if hasattr(vc, "is_paused") and callable(vc.is_paused):
                    res_p = vc.is_paused()
                    vc_paused = (res_p is True)

            is_paused = getattr(s, "state", None) == PlaybackState.PAUSED or vc_paused

            if (
                getattr(s, "current_track", None)
                and getattr(s, "state", None) == PlaybackState.PLAYING
                and vc_playing
                and not is_paused
            ):
                playing_sessions.append(s)

        if playing_sessions:
            # Sort by track start time descending to show most recently active music session
            playing_sessions.sort(key=lambda x: getattr(x, "track_start_time", 0.0), reverse=True)
            active_sess = playing_sessions[0]
            track = active_sess.current_track
            formatted_title = cls.sanitize_track_metadata(track.title, getattr(track, "artist", None))
            sig = f"STATE:PLAYING:{track.title}:{getattr(track, 'artist', '')}"
            act = discord.Activity(
                type=discord.ActivityType.listening,
                name=formatted_title,
            )
            return act, discord.Status.online, sig

        # 3. Idle / Paused state default
        sig = "STATE:IDLE"
        act = discord.Activity(
            type=discord.ActivityType.listening,
            name=DEFAULT_IDLE_ACTIVITY,
        )
        return act, discord.Status.online, sig

    @classmethod
    async def sync_presence(cls, bot: Any, force: bool = False) -> bool:
        """
        Synchronizes bot presence with Discord Gateway safely.
        Applies rate limiting to prevent Discord 429 gateway violations.
        """
        if not bot or not getattr(bot, "is_ready", lambda: False)():
            return False

        async with cls._lock:
            act, status, sig = cls.resolve_target_activity(bot)
            now = time.monotonic()
            elapsed = now - cls._last_update_time

            # If signature hasn't changed and not forced, skip to save network roundtrip
            if sig == cls._last_signature and not force:
                return True

            # Enforce minimum update cooldown unless transition to/from idle or forced
            is_state_transition = (
                cls._last_signature is not None
                and sig.split(":")[1] != cls._last_signature.split(":")[1]
            )
            if elapsed < MIN_UPDATE_INTERVAL_SECONDS and not force and not is_state_transition:
                return False

            try:
                await bot.change_presence(activity=act, status=status)
                cls._last_update_time = now
                cls._last_signature = sig
                logger.info(f"[Presence] Updated global bot presence: '{act.name}' ({status})")
                return True
            except discord.HTTPException as http_err:
                logger.warning(f"[Presence] HTTP notice updating presence: {http_err}")
                return False
            except Exception as e:
                logger.debug(f"[Presence] Error updating presence: {e}")
                return False

    @classmethod
    def start_watchdog(cls, bot: Any) -> None:
        """Starts background watchdog task ensuring presence tracks natural playback lifecycle."""
        if cls._loop_task and not cls._loop_task.done():
            return

        async def _presence_watchdog():
            while True:
                try:
                    await asyncio.sleep(30.0)
                    if bot and getattr(bot, "is_ready", lambda: False)():
                        await cls.sync_presence(bot)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.debug(f"[Presence] Watchdog iteration error: {e}")
                    await asyncio.sleep(10.0)

        cls._loop_task = asyncio.create_task(_presence_watchdog())
        logger.info("[Presence] Dynamic presence watchdog loop started (30s interval).")
