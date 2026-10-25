"""
MusicMaid — Dynamic Discord Presence & Activity Management Service.
Centralizes bot presence updates across playing, idle, and recovery states.
Respects Discord Gateway rate limits and enforces strict data sanitization.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

import discord
from music_bot.config import BOT_NAME
from music_bot.services.session_service import GuildMusicSession, PlaybackState, SessionManager

if TYPE_CHECKING:
    from music_bot.bot import RaiMusicBot

logger = logging.getLogger("MusicMaid.Presence")

# Constants
DEFAULT_IDLE_ACTIVITY: str = "24/7 high-fidelity lossless music player."
DEFAULT_RECOVERY_ACTIVITY: str = "Restoring session..."
MAX_ACTIVITY_LEN: int = 120  # Discord allows up to 128 chars, 120 provides safe buffer
MIN_UPDATE_INTERVAL_SECONDS: float = 20.0  # Discord gateway presence update cooldown

PRESENCE_CONFIG_FILE = Path("data/presence_config.json")

STATUS_MAP = {
    "online": discord.Status.online,
    "idle": discord.Status.idle,
    "dnd": discord.Status.dnd,
    "invisible": discord.Status.invisible,
}

ACTIVITY_TYPE_MAP = {
    "listening": discord.ActivityType.listening,
    "playing": discord.ActivityType.playing,
    "watching": discord.ActivityType.watching,
    "competing": discord.ActivityType.competing,
    "custom": discord.ActivityType.custom,
}


class DynamicPresenceService:
    """Enterprise centralized dynamic presence coordinator for MusicMaid."""

    _last_update_time: float = 0.0
    _last_signature: Optional[str] = None
    _lock = asyncio.Lock()
    _loop_task: Optional[asyncio.Task] = None

    # Owner presence control configuration
    _mode: str = "dynamic"  # "dynamic" | "manual"
    _custom_status: str = "online"  # "online" | "idle" | "dnd" | "invisible"
    _custom_activity_type: str = "listening"  # "listening" | "playing" | "watching" | "competing" | "custom"
    _custom_activity_text: str = ""
    _custom_idle_text: Optional[str] = None
    _signature_symbol: str = "vr_headset"  # "vr_headset" | "music_note" | "soundwave" | "radio" | "vinyl" | "energy_core"
    _config_loaded: bool = False

    ALLOWED_SYMBOLS = {
        "vr_headset",
        "music_note",
        "soundwave",
        "radio",
        "vinyl",
        "energy_core",
    }

    @classmethod
    def load_config(cls) -> None:
        """Load persistent presence settings from disk if available."""
        cls._config_loaded = True
        if PRESENCE_CONFIG_FILE.exists():
            try:
                with open(PRESENCE_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cls._mode = data.get("mode", "dynamic")
                    cls._custom_status = data.get("status", "online")
                    cls._custom_activity_type = data.get("activity_type", "listening")
                    cls._custom_activity_text = data.get("activity_text", "")
                    cls._custom_idle_text = data.get("idle_text") or None
                    sym = data.get("signature_symbol", "vr_headset")
                    cls._signature_symbol = sym if sym in cls.ALLOWED_SYMBOLS else "vr_headset"
            except Exception as e:
                logger.warning(f"Could not load presence config: {e}")

    @classmethod
    def save_config(cls) -> None:
        """Persist presence settings to disk."""
        try:
            PRESENCE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(PRESENCE_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "mode": cls._mode,
                    "status": cls._custom_status,
                    "activity_type": cls._custom_activity_type,
                    "activity_text": cls._custom_activity_text,
                    "idle_text": cls._custom_idle_text or "",
                    "signature_symbol": cls._signature_symbol,
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save presence config: {e}")

    @classmethod
    def get_state(cls, bot: Optional[Any] = None) -> Dict[str, Any]:
        """Return full presence control state and 5 independent live telemetry dimensions:
        1. configured_status: Desired status chosen by owner (online, idle, dnd, invisible)
        2. gateway_connected: Truthful Gateway socket connection status (True/False)
        3. discord_presence: Current visible status reported by Discord Gateway
        4. voice_connected: Whether bot is connected to active voice channel
        5. playback_state: Current playback state across cluster ('playing' | 'paused' | 'recovering' | 'idle' | 'unavailable')
        """
        if not cls._config_loaded:
            cls.load_config()

        live_activity_name = ""
        # 1. Configured presence
        configured_status = cls._custom_status or "online"

        # 2. Actual gateway connection
        if bot is not None and hasattr(bot, "is_ready") and callable(bot.is_ready):
            gateway_connected = bool(bot.is_ready())
        else:
            gateway_connected = False

        # 3. Discord-visible presence
        if bot and hasattr(bot, "status") and bot.status is not None:
            discord_presence = str(bot.status.value) if hasattr(bot.status, "value") else str(bot.status)
        else:
            discord_presence = "unknown"

        if bot and hasattr(bot, "activity") and bot.activity:
            live_activity_name = getattr(bot.activity, "name", "")

        # 4. Voice connection & 5. Playback state
        sm = SessionManager.get_instance() if hasattr(SessionManager, "get_instance") else None
        sessions: list[GuildMusicSession] = sm.get_all_sessions() if sm else []

        voice_connected = False
        voice_channel_name: Optional[str] = None
        has_playing = False
        has_paused = False
        has_recovering = False

        for s in sessions:
            vc = getattr(s, "voice_client", None)
            if vc and getattr(vc, "is_connected", lambda: False)():
                voice_connected = True
                ch = getattr(vc, "channel", None)
                if ch and hasattr(ch, "name") and not voice_channel_name:
                    voice_channel_name = ch.name

            st = getattr(s, "state", None)
            if st == PlaybackState.PLAYING:
                has_playing = True
            elif st == PlaybackState.PAUSED:
                has_paused = True
            elif st == PlaybackState.RECOVERING:
                has_recovering = True

        if not gateway_connected:
            playback_state = "unavailable"
        elif has_recovering:
            playback_state = "recovering"
        elif has_playing:
            playback_state = "playing"
        elif has_paused:
            playback_state = "paused"
        else:
            playback_state = "idle"

        return {
            "mode": cls._mode,
            "status": configured_status,  # Backwards compatibility alias
            "configured_status": configured_status,
            "gateway_connected": gateway_connected,
            "discord_presence": discord_presence,
            "voice_connected": voice_connected,
            "voice_channel": voice_channel_name,
            "playback_state": playback_state,
            "activity_type": cls._custom_activity_type,
            "activity_text": cls._custom_activity_text,
            "idle_text": cls._custom_idle_text or "",
            "signature_symbol": cls._signature_symbol,
            "live_activity_name": live_activity_name,
            "live_status": discord_presence,  # Backwards compatibility
            "last_update_time": cls._last_update_time,
            "last_signature": cls._last_signature,
        }

    @classmethod
    async def update_state(
        cls,
        bot: Optional[Any],
        mode: Optional[str] = None,
        status: Optional[str] = None,
        activity_type: Optional[str] = None,
        activity_text: Optional[str] = None,
        idle_text: Optional[str] = None,
        signature_symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update presence configuration, save to disk, and immediately synchronize Discord presence."""
        if not cls._config_loaded:
            cls.load_config()

        status_changed = False
        if mode in ("dynamic", "manual"):
            cls._mode = mode
        if status in STATUS_MAP:
            if cls._custom_status != status:
                status_changed = True
            cls._custom_status = status
        if activity_type in ACTIVITY_TYPE_MAP:
            cls._custom_activity_type = activity_type
        if activity_text is not None:
            cls._custom_activity_text = str(activity_text).strip()
        if idle_text is not None:
            cleaned = str(idle_text).strip()
            cls._custom_idle_text = cleaned if cleaned else None
        if signature_symbol is not None:
            sym = str(signature_symbol).strip().lower()
            if sym in cls.ALLOWED_SYMBOLS:
                cls._signature_symbol = sym

        cls.save_config()

        update_applied = False
        if bot:
            update_applied = await cls.sync_presence(bot, force=True)

        res = cls.get_state(bot)
        res["update_applied"] = update_applied
        return res

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
        - Manual Mode: Returns owner-configured activity and owner-configured status.
        - Dynamic Mode:
          Uses owner's configured status (online, idle, dnd, invisible) with dynamically chosen activity:
          Priority 1: Active session recovery in progress -> 'Restoring session...'
          Priority 2: Genuine active playback -> '{title} • {artist}'
          Priority 3: Idle / Paused / Stopped -> custom idle text or DEFAULT_IDLE_ACTIVITY
        """
        if not cls._config_loaded:
            cls.load_config()

        # The authoritative desired status configured by the bot owner
        target_status = STATUS_MAP.get(cls._custom_status, discord.Status.online)

        # 0. Manual Override Mode Check
        if cls._mode == "manual":
            act_type = ACTIVITY_TYPE_MAP.get(cls._custom_activity_type, discord.ActivityType.listening)
            act_name = cls._custom_activity_text or "MusicMaid"
            if act_type == discord.ActivityType.custom:
                try:
                    act = discord.CustomActivity(name="Custom Status", state=act_name)
                except Exception:
                    act = discord.Activity(type=discord.ActivityType.playing, name=act_name)
            else:
                act = discord.Activity(type=act_type, name=act_name)
            sig = f"STATE:MANUAL:{cls._custom_status}:{cls._custom_activity_type}:{act_name}"
            return act, target_status, sig

        sm = SessionManager.get_instance() if hasattr(SessionManager, "get_instance") else None
        sessions: list[GuildMusicSession] = sm.get_all_sessions() if sm else []

        # 1. Recovery state check: only if health/recovery system confirms active recovery
        recovering_sessions = [
            s for s in sessions if getattr(s, "state", None) == PlaybackState.RECOVERING
        ]
        if recovering_sessions:
            sig = f"STATE:RECOVERING:{cls._custom_status}"
            act = discord.Activity(
                type=discord.ActivityType.listening,
                name=DEFAULT_RECOVERY_ACTIVITY,
            )
            return act, target_status, sig

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
            sig = f"STATE:PLAYING:{cls._custom_status}:{track.title}:{getattr(track, 'artist', '')}"
            act = discord.Activity(
                type=discord.ActivityType.listening,
                name=formatted_title,
            )
            return act, target_status, sig

        # 3. Idle / Paused state default
        sig = f"STATE:IDLE:{cls._custom_status}"
        idle_name = cls._custom_idle_text or DEFAULT_IDLE_ACTIVITY
        act = discord.Activity(
            type=discord.ActivityType.listening,
            name=idle_name,
        )
        return act, target_status, sig

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
