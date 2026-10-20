"""
Advanced Rythm-Style Persistent Music Session Memory Engine for Rai Music Bot.
Handles:
1. Automated periodic and state-change position checkpoints.
2. Graceful shutdown snapshotting and startup recovery coordinator.
3. User return-later session preservation (/music-session save/restore/list/forget).
4. Multi-guild isolation, per-guild concurrency serialization, and idempotency.
5. Unexpected voice disconnect detection with exponential backoff & jitter reconnection.
6. Automatic session retention expiration (pinned sessions exempt).
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
import json
import logging
import random
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
import uuid

import discord

from music_bot.database.models import (
    MusicGuildSettings,
    PersistentMusicSession,
    QueuedTrack,
)
from music_bot.services.session_service import GuildMusicSession, LoopMode, PlaybackState

if TYPE_CHECKING:
    from music_bot.bot import RaiMusicBot

logger = logging.getLogger("RaiMusic.SessionMemory")


class MusicSessionMemoryService:
    """Master coordinator for persistent Rythm-style music session recovery and memory."""

    _reconnecting_guilds: set[int] = set()
    _recovery_tasks: dict[int, asyncio.Task[None]] = {}

    # =========================================================================
    # 1. PLAYBACK CHECKPOINT PERSISTENCE (PHASE 3)
    # =========================================================================

    @classmethod
    async def checkpoint_session(
        cls,
        bot: RaiMusicBot,
        session: GuildMusicSession,
        reason: str = "periodic",
    ) -> Optional[PersistentMusicSession]:
        """Atomically checkpoints live playback position, queue, and player settings."""
        if not bot.db or not bot.db._db:
            return None

        # Avoid checkpointing empty/idle sessions unless they have a preserved queue
        if not session.current_track and len(session.queue) == 0:
            return None

        try:
            cur_pos = session.progress_seconds
            is_paused = session.is_paused

            # Build or update persistent session model
            stable_id = ""
            provider = "youtube"
            title = ""
            duration = 0
            url = ""

            if session.current_track:
                stable_id = getattr(session.current_track, "id", "") or session.current_track.url
                title = session.current_track.title
                duration = session.current_track.duration
                url = session.current_track.url
                if "spotify" in url.lower():
                    provider = "spotify"

            # Determine recovery mode from guild settings
            guild_settings = await bot.db.get_guild_settings(session.guild_id)
            recovery_mode = getattr(guild_settings, "recovery_mode", "MANUAL")
            retention_days = getattr(guild_settings, "session_retention_days", 7)
            now = datetime.now(timezone.utc)
            expires_at = (now + timedelta(days=retention_days)).isoformat()

            vc_id = session.voice_client.channel.id if session.voice_client and session.voice_client.channel else None
            tc_id = session.text_channel.id if session.text_channel else None

            pers_session = PersistentMusicSession(
                guild_id=session.guild_id,
                session_id=session.session_id,
                session_name=session.session_name or "Active Session",
                session_status="PAUSED" if is_paused else ("ACTIVE" if session.is_playing else "SAVED"),
                current_track=session.current_track,
                current_track_title=title,
                stable_track_identifier=stable_id,
                source_provider=provider,
                source_url=url,
                track_duration=duration,
                last_known_position=cur_pos,
                is_paused=is_paused,
                queue=list(session.queue),
                history=list(session.history),
                loop_mode=session.loop_mode.value,
                shuffle_enabled=False,
                volume=session.volume,
                voice_channel_id=vc_id,
                text_channel_id=tc_id,
                created_by_user_id=None,
                created_by_user_name=None,
                created_at=now.isoformat(),
                updated_at=now.isoformat(),
                last_checkpoint=now.isoformat(),
                expires_at=expires_at,
                recovery_attempts=session.recovery_attempts,
                schema_version=1,
                is_pinned=False,
                recovery_mode=recovery_mode,
            )

            await bot.db.save_persistent_session(pers_session)
            session.last_checkpoint_pos = cur_pos
            session.last_checkpoint_time = time.time()
            logger.debug(
                f"[SessionMemory] Checkpoint saved for guild {session.guild_id} ({reason}): "
                f"track='{title}' pos={cur_pos}s paused={is_paused} queue_len={len(session.queue)}"
            )
            return pers_session
        except Exception as e:
            logger.warning(f"[SessionMemory] Failed to checkpoint session for guild {session.guild_id}: {e}")
            return None

    @classmethod
    async def checkpoint_all_active_sessions(cls, bot: RaiMusicBot, reason: str = "periodic") -> int:
        """Iterates over all active guild sessions and checkpoints their current state."""
        count = 0
        sessions = bot.session_manager.get_all_sessions()
        for session in sessions:
            if session.is_active or session.current_track or len(session.queue) > 0:
                res = await cls.checkpoint_session(bot, session, reason=reason)
                if res:
                    count += 1
        return count

    # =========================================================================
    # 2. USER RETURN-LATER SESSIONS (/music-session save/restore/list) (PHASE 5)
    # =========================================================================

    @classmethod
    async def save_named_session(
        cls,
        bot: RaiMusicBot,
        session: GuildMusicSession,
        name: str,
        user: discord.User | discord.Member,
        pinned: bool = False,
        expires_days: int = 7,
    ) -> Tuple[bool, str, Optional[PersistentMusicSession]]:
        """Saves a named session for user return-later restoration with exact order and position."""
        if not bot.db:
            return False, "Database is currently unavailable.", None

        if not session.current_track and len(session.queue) == 0:
            return False, "No active song or queued tracks to save.", None

        session_id = f"sess_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(days=expires_days)).isoformat()

        cur_pos = session.progress_seconds
        is_paused = session.is_paused

        title = session.current_track.title if session.current_track else ""
        url = session.current_track.url if session.current_track else ""
        duration = session.current_track.duration if session.current_track else 0
        provider = "youtube"
        if "spotify" in url.lower():
            provider = "spotify"

        vc_id = session.voice_client.channel.id if session.voice_client and session.voice_client.channel else None
        tc_id = session.text_channel.id if session.text_channel else None

        pers = PersistentMusicSession(
            guild_id=session.guild_id,
            session_id=session_id,
            session_name=name.strip(),
            session_status="SAVED",
            current_track=session.current_track,
            current_track_title=title,
            stable_track_identifier=url,
            source_provider=provider,
            source_url=url,
            track_duration=duration,
            last_known_position=cur_pos,
            is_paused=is_paused,
            queue=list(session.queue),
            history=list(session.history),
            loop_mode=session.loop_mode.value,
            shuffle_enabled=False,
            volume=session.volume,
            voice_channel_id=vc_id,
            text_channel_id=tc_id,
            created_by_user_id=user.id,
            created_by_user_name=str(user),
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            last_checkpoint=now.isoformat(),
            expires_at=expires_at,
            recovery_attempts=0,
            schema_version=1,
            is_pinned=pinned,
            recovery_mode="MANUAL",
        )

        try:
            await bot.db.save_persistent_session(pers)
            logger.info(
                f"[SessionMemory] Named session '{name}' ({session_id}) saved by {user} in guild {session.guild_id} "
                f"with {len(pers.queue)} upcoming tracks at pos={cur_pos}s"
            )
            return True, f"Successfully saved session **{name}** (`{session_id}`)", pers
        except Exception as e:
            logger.error(f"[SessionMemory] Error saving named session in guild {session.guild_id}: {e}", exc_info=True)
            return False, f"Failed to save session record: {e}", None

    @classmethod
    async def restore_session(
        cls,
        bot: RaiMusicBot,
        guild: discord.Guild,
        target_voice_channel: discord.VoiceChannel | discord.StageChannel,
        text_channel: discord.TextChannel | discord.VoiceChannel | discord.Thread,
        session_id_or_name: Optional[str] = None,
        requested_by_user: Optional[discord.Member] = None,
        recovery_mode: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[PersistentMusicSession]]:
        """Restores a saved music session into the active guild player with position and order preservation."""
        if not bot.db:
            return False, "Database connection is not available.", None

        session = await bot.session_manager.get_session(guild.id)

        # Enforce strict per-guild concurrency serialization to prevent double-playback
        async with session.lock:
            # 1. Locate the session record
            saved: Optional[PersistentMusicSession] = None
            if session_id_or_name:
                saved = await bot.db.get_persistent_session(guild.id, session_id_or_name.strip())
                if not saved:
                    saved = await bot.db.get_persistent_session_by_name(guild.id, session_id_or_name.strip())
            else:
                saved = await bot.db.get_persistent_session(guild.id, None)

            if not saved:
                return False, "❌ No saved music session found for this server.", None

            if saved.session_status == "TERMINATED":
                return False, "❌ That session has been terminated and cannot be restored.", None

            # 2. Check channel permissions
            perms = target_voice_channel.permissions_for(guild.me)
            if not perms.connect or not perms.speak:
                return False, f"❌ Bot lacks **Connect** or **Speak** permissions in {target_voice_channel.mention}.", None

            # 3. Determine active recovery mode
            if not recovery_mode:
                guild_settings = await bot.db.get_guild_settings(guild.id)
                recovery_mode = getattr(guild_settings, "recovery_mode", saved.recovery_mode or "MANUAL")

            # 4. Connect to Voice Channel if not connected
            try:
                from music_bot.services.voice_service import VoiceManager
                vc = await asyncio.wait_for(
                    VoiceManager.join_voice_channel(requested_by_user or guild.me, text_channel, session),  # type: ignore
                    timeout=10.0,
                )
                if not vc:
                    return False, f"❌ Could not establish voice connection to {target_voice_channel.mention}.", None
            except Exception as e:
                return False, f"❌ Voice connection error: {e}", None

            # 5. Restore settings, volume, loop mode
            session.volume = saved.volume
            session.loop_mode = LoopMode(saved.loop_mode) if saved.loop_mode in ["off", "track", "queue"] else LoopMode.OFF
            session.text_channel = text_channel  # type: ignore
            session.session_id = saved.session_id
            session.session_name = saved.session_name
            session.is_intentional_stop = False

            # 6. Reconstruct Queue in exact original order
            session.queue = deque([t for t in saved.queue])
            session.history = list(saved.history)

            # 7. Resume Playback or Queue-Only
            from music_bot.services.player_service import MusicPlayerService
            from music_bot.services.resolver_service import AudioResolver

            if recovery_mode == "QUEUE_ONLY" or not saved.current_track:
                # Mode QUEUE_ONLY: Restore queue without starting audio
                saved.session_status = "RESTORED"
                await bot.db.save_persistent_session(saved)
                return (
                    True,
                    f"✅ Restored **{len(session.queue)}** queued tracks in exact order (Queue-Only mode). Use `/music play` to begin.",
                    saved,
                )

            # Track playback recovery
            track_to_play = saved.current_track
            # Calculate position: never advance position if session was saved while paused!
            start_pos = saved.last_known_position
            if saved.is_paused:
                start_pos = saved.last_known_position

            logger.info(
                f"[SessionMemory] Restoring session '{saved.session_name}' ({saved.session_id}) in {guild.name}: "
                f"track='{track_to_play.title}', pos={start_pos}s, queue_len={len(session.queue)}"
            )

            # Re-resolve fresh stream URL if needed
            try:
                if not track_to_play.stream_url:
                    fresh = await asyncio.wait_for(
                        AudioResolver.resolve_track(track_to_play.url, track_to_play.requester_id, track_to_play.requester_name),
                        timeout=12.0,
                    )
                    if fresh and fresh.stream_url:
                        track_to_play.stream_url = fresh.stream_url
            except Exception as res_err:
                logger.warning(f"[SessionMemory] Stream re-resolution error for '{track_to_play.title}': {res_err}")

            if start_pos and start_pos > 3:
                success = await MusicPlayerService.resume_track_stream(bot, session, track_to_play, start_pos)
                if not success:
                    # Fallback to start of track if seeking failed
                    await MusicPlayerService.start_playback(bot, session, track_to_play)
            else:
                await MusicPlayerService.start_playback(bot, session, track_to_play)

            # Update session status in database
            saved.session_status = "RESTORED"
            saved.recovery_attempts = 0
            await bot.db.save_persistent_session(saved)

            msg = (
                f"🎶 **Restored Session:** **{saved.session_name}**\n"
                f"• Resumed track: **{track_to_play.title}** at `{start_pos}s`\n"
                f"• Queue preserved: **{len(session.queue)}** upcoming tracks\n"
                f"• Volume: **{session.volume}%** • Loop: **{session.loop_mode.value.title()}**"
            )
            return True, msg, saved

    # =========================================================================
    # 3. VOICE DISCONNECT & RECOVERY WITH BACKOFF (PHASE 7)
    # =========================================================================

    @classmethod
    async def handle_unexpected_disconnect(
        cls,
        bot: RaiMusicBot,
        guild_id: int,
        channel_id: Optional[int] = None,
    ) -> None:
        task = cls._recovery_tasks.get(guild_id)
        if task and not task.done():
            logger.debug(f"[SessionMemory] Guild {guild_id} recovery is already running; joining the existing recovery.")
            await asyncio.shield(task)
            return

        task = asyncio.create_task(
            cls._run_unexpected_disconnect(bot, guild_id, channel_id),
            name=f"VoiceRecovery-{guild_id}",
        )
        cls._recovery_tasks[guild_id] = task
        cls._reconnecting_guilds.add(guild_id)

        def _cleanup_recovery(done_task: asyncio.Task[None]) -> None:
            if cls._recovery_tasks.get(guild_id) is done_task:
                cls._recovery_tasks.pop(guild_id, None)
                cls._reconnecting_guilds.discard(guild_id)
            if not done_task.cancelled():
                exception = done_task.exception()
                if exception:
                    logger.error(
                        "[SessionMemory] Recovery task failed for guild %s: %s",
                        guild_id,
                        exception,
                        exc_info=(type(exception), exception, exception.__traceback__),
                    )

        task.add_done_callback(_cleanup_recovery)
        await asyncio.shield(task)

    @classmethod
    async def cancel_recovery_tasks(cls) -> None:
        tasks = list(cls._recovery_tasks.items())
        for _, task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        for guild_id, task in tasks:
            if cls._recovery_tasks.get(guild_id) is task:
                cls._recovery_tasks.pop(guild_id, None)
            cls._reconnecting_guilds.discard(guild_id)

    @classmethod
    async def _run_unexpected_disconnect(
        cls,
        bot: RaiMusicBot,
        guild_id: int,
        channel_id: Optional[int] = None,
    ) -> None:
        """Handles sudden voice disconnection with bounded exponential backoff and jitter."""
        session = bot.session_manager.get_session_sync(guild_id)
        if not session:
            return

        # Do NOT reconnect if the disconnect was explicitly commanded by the user (/leave, /disconnect, /247 disable)
        if getattr(session, "is_intentional_disconnect", False):
            logger.info(f"[SessionMemory] Guild {guild_id} voice disconnect was intentional user leave; skipping recovery.")
            return

        # Check authoritative 24/7 status
        is_247 = getattr(session, "twenty_four_seven", False)
        g_set = None
        if bot and getattr(bot, "db", None) and hasattr(bot.db, "get_guild_settings"):
            try:
                g_set = await bot.db.get_guild_settings(guild_id)
                if g_set and g_set.twenty_four_seven_enabled:
                    is_247 = True
                    session.twenty_four_seven = True
            except Exception:
                pass

        try:
            logger.warning(
                f"[SessionMemory] Unexpected voice disconnect detected in guild {guild_id} "
                f"(24/7: {is_247})! Initiating bounded recovery..."
            )
            session.state = PlaybackState.RECOVERING
            try:
                from music_bot.services.presence_service import DynamicPresenceService
                asyncio.create_task(DynamicPresenceService.sync_presence(bot, force=True))
            except Exception:
                pass

            # 1. Immediate checkpoint of last known position
            try:
                await cls.checkpoint_session(bot, session, reason="unexpected_disconnect")
            except Exception as cp_err:
                logger.debug(f"[SessionMemory] Checkpoint on disconnect notice: {cp_err}")

            guild = bot.get_guild(guild_id)
            if not guild:
                return

            connected_vc = guild.voice_client
            if connected_vc and connected_vc.is_connected():
                session.voice_client = connected_vc
                session.state = (
                    PlaybackState.PLAYING if connected_vc.is_playing() else PlaybackState.CONNECTED
                )
                logger.info(
                    "[SessionMemory] Guild %s already has a healthy voice connection; recovery will not replace it.",
                    guild_id,
                )
                return

            saved = None
            if bot.db:
                try:
                    saved = await bot.db.get_persistent_session(guild_id)
                except Exception:
                    pass

            # Resolve target voice channel: parameter > saved session > guild settings > previous channel
            target_ch_id = channel_id
            if not target_ch_id and saved and saved.voice_channel_id:
                target_ch_id = saved.voice_channel_id
            if not target_ch_id and g_set and g_set.twenty_four_seven_channel_id:
                target_ch_id = g_set.twenty_four_seven_channel_id
            if not target_ch_id and session.voice_client and session.voice_client.channel:
                target_ch_id = session.voice_client.channel.id

            # If neither 24/7 mode nor an active saved session exists, abort recovery
            if not is_247 and (not saved or not saved.current_track):
                logger.info(f"[SessionMemory] Guild {guild_id}: Neither 24/7 mode nor active queue exists. Recovery not required.")
                session.state = PlaybackState.IDLE
                return

            if not target_ch_id:
                logger.info(f"[SessionMemory] Guild {guild_id}: No target voice channel recorded. Waiting for user summon.")
                session.state = PlaybackState.IDLE
                return

            vc_channel = guild.get_channel(target_ch_id)
            if not vc_channel:
                try:
                    vc_channel = await guild.fetch_channel(target_ch_id)
                except Exception:
                    pass

            from music_bot.services.voice_service import VoiceManager
            if not vc_channel or not VoiceManager.is_valid_music_voice_channel(vc_channel):
                logger.warning(f"[SessionMemory] Guild {guild_id}: Target voice channel {target_ch_id} is missing or an invalid stat/AFK channel. Aborting reconnect.")
                session.state = PlaybackState.IDLE
                return

            if guild.me:
                perms = vc_channel.permissions_for(guild.me)
                if not perms.connect or not perms.speak:
                    logger.warning(f"[SessionMemory] Lacking Connect/Speak permissions in #{vc_channel.name}. Aborting reconnect.")
                    session.state = PlaybackState.ERROR
                    return

            text_ch = (guild.get_channel(saved.text_channel_id or 0) if saved else None) or session.text_channel

            # 2. Bounded Exponential Backoff with Jitter (e.g. 2s, 4s, 8s, max 3 attempts)
            delays = [2.0, 4.0, 8.0]
            reconnected = False
            reused_connection = False

            for attempt, base_delay in enumerate(delays, 1):
                session.recovery_attempts = attempt
                jitter = random.uniform(0.1, 0.9)
                delay = base_delay + jitter
                logger.info(f"[SessionMemory] Reconnection attempt {attempt}/3 for guild {guild_id} to #{vc_channel.name} in {delay:.2f}s...")
                await asyncio.sleep(delay)

                try:
                    from music_bot.services.voice_service import VoiceManager
                    connected_vc = guild.voice_client
                    if connected_vc and connected_vc.is_connected():
                        session.voice_client = connected_vc
                        if connected_vc.channel and connected_vc.channel.id == vc_channel.id:
                            reconnected = True
                            reused_connection = True
                            break
                        session.state = (
                            PlaybackState.PLAYING if connected_vc.is_playing() else PlaybackState.CONNECTED
                        )
                        logger.info(
                            "[SessionMemory] Guild %s acquired a healthy connection in another channel; "
                            "stale recovery will not move it.",
                            guild_id,
                        )
                        return
                    vc = await asyncio.wait_for(
                        VoiceManager.join_voice_channel(
                            guild.me,
                            text_ch,
                            session,
                            target_channel=vc_channel,
                            reuse_connected_only=True,
                        ),  # type: ignore
                        timeout=50.0,
                    )
                    if vc and vc.is_connected():
                        reconnected = True
                        break
                    connected_vc = guild.voice_client
                    if connected_vc and connected_vc.is_connected():
                        session.voice_client = connected_vc
                        session.state = (
                            PlaybackState.PLAYING if connected_vc.is_playing() else PlaybackState.CONNECTED
                        )
                        logger.info(
                            "[SessionMemory] Guild %s retained a healthy voice connection; "
                            "stale recovery stopped.",
                            guild_id,
                        )
                        return
                except Exception as e:
                    logger.debug(f"[SessionMemory] Attempt {attempt} failed: {e}")

            if not reconnected:
                logger.error(f"[SessionMemory] All 3 bounded reconnection attempts failed for guild {guild_id}.")
                session.state = PlaybackState.ERROR
                session.recovery_status = "Disconnected (Will retry in 24/7 guardian loop)"
                return

            logger.info(f"[SessionMemory] Successfully reconnected to #{vc_channel.name} in {guild.name}!")
            session.recovery_status = "Connected (24/7 active)"

            # 3. Resume playback at checkpoint if track was playing
            if not reused_connection and saved and saved.current_track and saved.session_status != "PAUSED":
                from music_bot.services.player_service import MusicPlayerService
                pos = saved.last_known_position
                if pos > 3:
                    await MusicPlayerService.resume_track_stream(bot, session, saved.current_track, pos)
                else:
                    await MusicPlayerService.start_playback(bot, session, saved.current_track)

            session.state = PlaybackState.PLAYING if (session.voice_client and session.voice_client.is_playing()) else PlaybackState.CONNECTED
        except Exception as err:
            logger.error(f"[SessionMemory] Disconnect recovery handler error for guild {guild_id}: {err}", exc_info=True)
        finally:
            try:
                from music_bot.services.presence_service import DynamicPresenceService
                asyncio.create_task(DynamicPresenceService.sync_presence(bot, force=True))
            except Exception:
                pass

    # =========================================================================
    # 4. STARTUP RECOVERY COORDINATOR (PHASE 4)
    # =========================================================================

    @classmethod
    async def startup_recovery_coordinator(cls, bot: RaiMusicBot) -> int:
        """Validates database schema and restores eligible sessions across all guilds on startup."""
        if not bot.db:
            return 0

        recovered_count = 0
        try:
            eligible_sessions = await bot.db.get_all_eligible_auto_resume_sessions()
            logger.info(f"[SessionMemory] Found {len(eligible_sessions)} session(s) eligible for startup recovery.")

            for saved in eligible_sessions:
                guild = bot.get_guild(saved.guild_id)
                if not guild:
                    continue

                vc_channel = guild.get_channel(saved.voice_channel_id or 0)
                if not isinstance(vc_channel, (discord.VoiceChannel, discord.StageChannel)):
                    continue

                text_channel = guild.get_channel(saved.text_channel_id or 0)
                if not isinstance(text_channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread)):
                    text_channel = vc_channel  # Fallback

                session = await bot.session_manager.get_session(guild.id)
                if session.is_active:
                    continue  # Already active, do not interrupt

                logger.info(f"[SessionMemory] Auto-recovering session for {guild.name} (#{vc_channel.name})...")
                success, msg, _ = await cls.restore_session(
                    bot=bot,
                    guild=guild,
                    target_voice_channel=vc_channel,
                    text_channel=text_channel,
                    session_id_or_name=saved.session_id,
                    recovery_mode=saved.recovery_mode,
                )
                if success:
                    recovered_count += 1
                    try:
                        if text_channel:
                            await text_channel.send(f"🔄 **Auto-Resume Notice:** {msg}")
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"[SessionMemory] Startup recovery coordinator encountered an error: {e}", exc_info=True)

        return recovered_count

    # =========================================================================
    # 5. RETENTION & CLEANUP (PHASE 9)
    # =========================================================================

    @classmethod
    async def cleanup_expired_sessions(cls, bot: RaiMusicBot) -> int:
        """Purges expired unpinned sessions."""
        if not bot.db:
            return 0
        try:
            purged = await bot.db.cleanup_expired_persistent_sessions()
            if purged > 0:
                logger.info(f"[SessionMemory] Cleaned up {purged} expired persistent session record(s).")
            return purged
        except Exception as e:
            logger.warning(f"[SessionMemory] Error cleaning expired sessions: {e}")
            return 0
