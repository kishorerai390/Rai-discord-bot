"""
Voice Connection & Auto-Leave Management for Rai Music Bot.
Monitors listener activity and disconnects gracefully on empty channels after configurable timeout.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional
import discord

from music_bot.config import AUTO_LEAVE_TIMEOUT_SECONDS
from music_bot.services.session_service import GuildMusicSession, PlaybackState

if TYPE_CHECKING:
    from music_bot.bot import RaiMusicBot

logger = logging.getLogger("RaiMusic.Voice")


class VoiceManager:
    """Manages voice connectivity and auto-leave inactivity timers with singleflight concurrency protection."""

    _guild_locks: dict[int, asyncio.Lock] = {}
    _in_flight_tasks: dict[int, asyncio.Task[Optional[discord.VoiceClient]]] = {}

    @classmethod
    def _get_guild_lock(cls, guild_id: int) -> asyncio.Lock:
        """Retrieve or create dedicated per-guild connection mutex."""
        if guild_id not in cls._guild_locks:
            cls._guild_locks[guild_id] = asyncio.Lock()
        return cls._guild_locks[guild_id]

    @classmethod
    async def join_voice_channel(
        cls, member: discord.Member, text_channel: discord.TextChannel, session: GuildMusicSession
    ) -> Optional[discord.VoiceClient]:
        """
        Ensure the bot connects to the member's voice channel.
        Singleflight-guarded: simultaneous calls for the same guild coalesce into a single connection task,
        preventing competing VoiceClient instances and UDP handshake collisions.
        """
        if not member.voice or not member.voice.channel:
            return None

        guild_id = member.guild.id

        # Concurrency Gate: If a connection task is already active for this guild, coalesce into it
        existing_task = cls._in_flight_tasks.get(guild_id)
        if existing_task and not existing_task.done():
            logger.info(
                f"[Voice] [Concurrency] Connection to voice for guild {guild_id} is already in-flight. "
                f"Coalescing simultaneous request..."
            )
            try:
                return await asyncio.shield(existing_task)
            except Exception as wait_err:
                logger.debug(f"[Voice] Coalesced wait error for guild {guild_id}: {wait_err}")

        # Acquire per-guild lock to ensure serialized connection lifecycles
        lock = cls._get_guild_lock(guild_id)
        async with lock:
            # Re-check existing in-flight task after acquiring lock
            existing_task = cls._in_flight_tasks.get(guild_id)
            if existing_task and not existing_task.done():
                try:
                    return await asyncio.shield(existing_task)
                except Exception:
                    pass

            # Create and register the in-flight worker task
            loop = asyncio.get_running_loop()
            task: asyncio.Task[Optional[discord.VoiceClient]] = loop.create_task(
                cls._execute_join_pipeline(member, text_channel, session),
                name=f"VoiceConnect-{guild_id}-{member.voice.channel.id}",
            )
            cls._in_flight_tasks[guild_id] = task
            try:
                return await task
            finally:
                if cls._in_flight_tasks.get(guild_id) is task:
                    cls._in_flight_tasks.pop(guild_id, None)

    @classmethod
    async def _execute_join_pipeline(
        cls, member: discord.Member, text_channel: discord.TextChannel, session: GuildMusicSession
    ) -> Optional[discord.VoiceClient]:
        """Internal worker executing the 5-stage voice connection sequence with granular diagnostic telemetry."""
        import time

        t_start = time.monotonic()
        target_channel = member.voice.channel if member.voice else None
        if not target_channel or not member.guild:
            return None

        guild_id = member.guild.id
        session.text_channel = text_channel

        # =========================================================================
        # STAGE 1: PRE-FLIGHT AUDIT (AFK Sentry, Bot Channel Access, Permissions)
        # =========================================================================
        # Feature 135: AFK Channel Anti-Join Sentry
        if member.guild.afk_channel and target_channel.id == member.guild.afk_channel.id:
            logger.warning(f"[Voice] [Stage 1: Pre-flight] Blocked joining AFK voice channel in guild {guild_id}")
            session.last_error = "Cannot play music in the server's AFK voice channel."
            return None

        # Cancel pending auto-leave inactivity timer
        if session.auto_leave_task and not session.auto_leave_task.done():
            session.auto_leave_task.cancel()
            session.auto_leave_task = None

        # Permissions check
        if member.guild.me:
            perms = target_channel.permissions_for(member.guild.me)
            if not perms.connect:
                err = f"Missing **Connect** permission in {target_channel.mention}"
                logger.warning(f"[Voice] [Stage 1: Pre-flight] Guild {guild_id}: {err}")
                session.last_error = err
                return None
            if not perms.speak:
                err = f"Missing **Speak** permission in {target_channel.mention}"
                logger.warning(f"[Voice] [Stage 1: Pre-flight] Guild {guild_id}: {err}")
                session.last_error = err
                return None

        stage1_ms = (time.monotonic() - t_start) * 1000
        logger.info(
            f"[Voice] [Stage 1: Pre-flight PASS] Guild {guild_id} | Channel #{target_channel.name} "
            f"({target_channel.id}) | Elapsed: {stage1_ms:.1f}ms"
        )

        # =========================================================================
        # STAGE 2: EXISTING VOICECLIENT AUDIT & REUSE / CHANNEL MOVE
        # =========================================================================
        existing_vc = member.guild.voice_client
        if existing_vc and existing_vc.is_connected():
            session.voice_client = existing_vc
            if existing_vc.channel and existing_vc.channel.id == target_channel.id:
                stage2_ms = (time.monotonic() - t_start) * 1000
                logger.info(
                    f"[Voice] [Stage 2: Existing Connection Reused] Guild {guild_id} | "
                    f"Already in target channel #{target_channel.name} | Total: {stage2_ms:.1f}ms"
                )
                return existing_vc

            logger.info(
                f"[Voice] [Stage 2: Channel Move] Moving VoiceClient from "
                f"#{existing_vc.channel.name if existing_vc.channel else 'unknown'} to #{target_channel.name}..."
            )
            try:
                await asyncio.wait_for(existing_vc.move_to(target_channel), timeout=15.0)
                session.voice_client = existing_vc
                stage2_ms = (time.monotonic() - t_start) * 1000
                logger.info(f"[Voice] [Stage 2: Channel Move PASS] Total: {stage2_ms:.1f}ms")
                return existing_vc
            except Exception as move_err:
                logger.warning(f"[Voice] [Stage 2: Move Warning] Move failed ({move_err}). Reconnecting cleanly...")

        elif existing_vc:
            # Stale / orphaned VoiceClient cleanup
            logger.info(f"[Voice] [Stage 2: Stale Cleanup] Clearing orphaned VoiceClient in guild {guild_id}...")
            try:
                await asyncio.shield(existing_vc.disconnect(force=True))
            except Exception as d_err:
                logger.debug(f"[Voice] Orphaned disconnect note: {d_err}")
            try:
                await asyncio.shield(member.guild.change_voice_state(channel=None))
            except Exception:
                pass
            # Allow Discord Gateway 1.0s to acknowledge state clearance
            await asyncio.sleep(1.0)

        # =========================================================================
        # STAGE 3-5: BOUNDED HANDSHAKE & UDP TRANSMISSION NEGOTIATION
        # =========================================================================
        max_attempts = 3
        connect_timeout = 35.0
        last_exception: Optional[Exception] = None
        failed_stage = "Gateway Handshake"

        for attempt in range(1, max_attempts + 1):
            t_attempt = time.monotonic()
            session.state = PlaybackState.CONNECTING
            logger.info(
                f"[Voice] [Stage 3: Gateway Signaling] Guild {guild_id} | Connecting to #{target_channel.name} "
                f"(Attempt {attempt}/{max_attempts}, timeout={connect_timeout}s)..."
            )

            try:
                # Initiate Discord Voice handshake (WebSocket signalling + UDP IP discovery)
                failed_stage = "Gateway & Voice WebSocket Handshake"
                vc = await asyncio.wait_for(
                    target_channel.connect(timeout=connect_timeout, reconnect=True, self_deaf=True),
                    timeout=connect_timeout + 5.0,
                )

                failed_stage = "UDP Transmission Verification"
                if vc and vc.is_connected():
                    session.voice_client = vc
                    session.state = PlaybackState.CONNECTED
                    session.last_error = None
                    total_dur_ms = (time.monotonic() - t_start) * 1000
                    logger.info(
                        f"[Voice] [Stage 4/5: UDP Handshake PASS] Guild {guild_id} | "
                        f"Connected to #{target_channel.name} in {total_dur_ms:.1f}ms (Attempt {attempt}) 🚀"
                    )
                    return vc

                # Fallback check: Did guild VoiceClient connect despite edge condition?
                if member.guild.voice_client and member.guild.voice_client.is_connected():
                    curr_vc = member.guild.voice_client
                    session.voice_client = curr_vc
                    session.state = PlaybackState.CONNECTED
                    session.last_error = None
                    total_dur_ms = (time.monotonic() - t_start) * 1000
                    logger.info(f"[Voice] [Stage 5: State Verified] VoiceClient verified connected in {total_dur_ms:.1f}ms")
                    return curr_vc

                raise RuntimeError("VoiceClient connected but is_connected() returned False.")

            except asyncio.TimeoutError as t_err:
                last_exception = t_err
                att_ms = (time.monotonic() - t_attempt) * 1000
                logger.warning(
                    f"[Voice] [Attempt {attempt} TIMEOUT] Guild {guild_id} | Failed at '{failed_stage}' "
                    f"after {att_ms:.1f}ms (Exceeded {connect_timeout}s)"
                )
                try:
                    if member.guild and member.guild.voice_client:
                        await asyncio.shield(member.guild.voice_client.disconnect(force=True))
                    if member.guild:
                        await asyncio.shield(member.guild.change_voice_state(channel=None))
                except Exception:
                    pass

                if attempt < max_attempts:
                    import random
                    backoff = (attempt * 2.0) + random.uniform(0.1, 0.5)
                    logger.info(f"[Voice] Backing off {backoff:.2f}s before retry {attempt + 1}/{max_attempts}...")
                    await asyncio.sleep(backoff)

            except discord.ClientException as ce:
                last_exception = ce
                logger.warning(f"[Voice] [Attempt {attempt} ClientException] Guild {guild_id}: {ce}")
                if member.guild and member.guild.voice_client and member.guild.voice_client.is_connected():
                    session.voice_client = member.guild.voice_client
                    session.state = PlaybackState.CONNECTED
                    session.last_error = None
                    return member.guild.voice_client
                try:
                    if member.guild and member.guild.voice_client:
                        await asyncio.shield(member.guild.voice_client.disconnect(force=True))
                    if member.guild:
                        await asyncio.shield(member.guild.change_voice_state(channel=None))
                except Exception:
                    pass
                if attempt < max_attempts:
                    await asyncio.sleep(attempt * 1.5)

            except Exception as e:
                last_exception = e
                logger.error(f"[Voice] [Attempt {attempt} Error] Unexpected error at '{failed_stage}': {e}", exc_info=True)
                try:
                    if member.guild and member.guild.voice_client:
                        await asyncio.shield(member.guild.voice_client.disconnect(force=True))
                    if member.guild:
                        await asyncio.shield(member.guild.change_voice_state(channel=None))
                except Exception:
                    pass
                if attempt < max_attempts:
                    await asyncio.sleep(attempt * 1.5)

        # All attempts failed: format actionable user diagnostic
        total_fail_ms = (time.monotonic() - t_start) * 1000
        err_msg = (
            f"Voice connection timed out after {max_attempts} attempts ({total_fail_ms:.0f}ms).\n"
            f"• **Failed Stage:** `{failed_stage}`\n"
            f"• **Target Channel:** {target_channel.mention}\n\n"
            f"💡 **How to Fix Instantly:**\n"
            f"1. In Discord, right-click/tap gear on **{target_channel.name}** ➔ **Edit Channel** ➔ **Overview**.\n"
            f"2. Scroll down to **Region Override** and change from *Automatic* to a close region (e.g. **US East**, **Rotterdam**, or **Singapore**).\n"
            f"3. Try `,play` again!"
        )
        logger.error(f"[Voice] [Connection Exhausted] Guild {guild_id}: {err_msg} (Last error: {last_exception})")
        session.state = PlaybackState.ERROR
        session.last_error = err_msg
        return None

    @classmethod
    def schedule_auto_leave(cls, bot: RaiMusicBot, session: GuildMusicSession, timeout: int = AUTO_LEAVE_TIMEOUT_SECONDS) -> None:
        """Schedule automatic disconnection if voice channel remains empty."""
        if session.twenty_four_seven:
            logger.debug(f"24/7 mode enabled in guild {session.guild_id}: auto-leave bypassed.")
            return

        if session.auto_leave_task and not session.auto_leave_task.done():
            session.auto_leave_task.cancel()

        session.auto_leave_task = asyncio.create_task(
            cls._auto_leave_worker(bot, session, timeout)
        )

    @classmethod
    async def _auto_leave_worker(cls, bot: RaiMusicBot, session: GuildMusicSession, timeout: int) -> None:
        """Waits for timeout then leaves voice if channel is still empty of human listeners."""
        try:
            logger.info(f"Auto-leave countdown ({timeout}s) initiated for guild {session.guild_id}")
            await asyncio.sleep(timeout)

            async with session.lock:
                if session.twenty_four_seven:
                    logger.info(f"Auto-leave skipped in guild {session.guild_id} (24/7 mode active).")
                    return

                if not session.voice_client or not session.voice_client.is_connected():
                    return

                channel = session.voice_client.channel
                # Check for non-bot members
                human_members = [m for m in channel.members if not m.bot]
                if not human_members:
                    logger.info(f"Auto-leaving empty voice channel in guild {session.guild_id}")
                    # Feature 112: Inactivity Sleep Fade-Out Timer (Smooth volume decay to avoid popping)
                    if session.voice_client.is_playing() and hasattr(session.voice_client.source, "volume"):
                        try:
                            start_vol = session.voice_client.source.volume
                            for factor in (0.75, 0.5, 0.25, 0.05):
                                session.voice_client.source.volume = start_vol * factor
                                await asyncio.sleep(0.4)
                        except Exception:
                            pass

                    # Checkpoint session before disconnecting so users can restore when returning
                    try:
                        from music_bot.services.session_memory_service import MusicSessionMemoryService
                        await MusicSessionMemoryService.checkpoint_session(
                            bot, session, reason="auto_leave_empty_channel"
                        )
                    except Exception as cp_err:
                        logger.warning(f"Failed to checkpoint session on auto-leave: {cp_err}")

                    session.is_intentional_stop = False
                    if session.voice_client.is_playing() or session.voice_client.is_paused():
                        session.voice_client.stop()
                    await session.voice_client.disconnect()
                    session.voice_client = None
                    session.state = PlaybackState.IDLE
                    session.recovery_status = "Saved on empty channel (Ready to resume)"

                    if session.text_channel:
                        embed = discord.Embed(
                            title="👋 AUTO DISCONNECTED",
                            description=(
                                f"Left voice channel because it remained empty for `{max(1, timeout // 60)}` minutes.\n"
                                f"💾 **Session Preserved:** Your queue and playback position were saved!\n"
                                f"Use `/music-session restore` or `/play` when you return to pick up where you left off. 🐾"
                            ),
                            color=0xED4245,
                        )
                        try:
                            await session.text_channel.send(embed=embed)
                        except Exception:
                            pass
        except asyncio.CancelledError:
            logger.debug(f"Auto-leave cancelled for guild {session.guild_id}")
        except Exception as e:
            logger.error(f"Error in auto-leave worker: {e}")
