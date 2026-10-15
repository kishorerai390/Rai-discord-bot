"""
Voice Connection & Auto-Leave Management for Rai Music Bot.
Monitors listener activity, manages Discord voice signaling lifecycle,
and disconnects gracefully on empty channels after configurable timeout.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import random
import time
from typing import TYPE_CHECKING, Optional, Tuple
import discord

from music_bot.config import AUTO_LEAVE_TIMEOUT_SECONDS
from music_bot.services.session_service import GuildMusicSession, PlaybackState

if TYPE_CHECKING:
    from music_bot.bot import RaiMusicBot

logger = logging.getLogger("RaiMusic.Voice")


@dataclass
class VoiceTelemetry:
    """Diagnostic telemetry captured during voice connection sequences."""
    guild_id: int
    channel_id: Optional[int] = None
    channel_name: Optional[str] = None
    attempt: int = 0
    max_attempts: int = 3
    stage: str = "Idle"
    elapsed_ms: float = 0.0
    flow_state: Optional[str] = None
    last_error: Optional[str] = None
    last_connected_at: Optional[float] = None
    success: bool = False
    cleanup_succeeded: bool = True


class VoiceManager:
    """Manages voice connectivity and auto-leave inactivity timers with singleflight concurrency protection."""

    _guild_locks: dict[int, asyncio.Lock] = {}
    _in_flight_tasks: dict[int, asyncio.Task[Optional[discord.VoiceClient]]] = {}
    _in_flight_channels: dict[int, int] = {}
    _telemetry: dict[int, VoiceTelemetry] = {}

    @classmethod
    def _get_guild_lock(cls, guild_id: int) -> asyncio.Lock:
        """Retrieve or create dedicated per-guild connection mutex."""
        if guild_id not in cls._guild_locks:
            cls._guild_locks[guild_id] = asyncio.Lock()
        return cls._guild_locks[guild_id]

    @classmethod
    def get_telemetry(cls, guild_id: int) -> Optional[VoiceTelemetry]:
        """Retrieve the latest voice connection telemetry for a guild."""
        return cls._telemetry.get(guild_id)

    @classmethod
    async def _purge_voice_client_state(cls, guild: Optional[discord.Guild]) -> bool:
        """
        Safely and thoroughly cleans up any orphaned or stale voice client state from discord.py internal tracking.
        Prevents ClientException('Already connected to a voice channel.') from poisoning subsequent connection attempts.
        """
        if not guild:
            return True
        guild_id = guild.id
        cleaned = True

        vc = getattr(guild, "voice_client", None)
        state = getattr(guild, "_state", None)

        if vc:
            try:
                vc.stop()
            except Exception:
                pass
            if hasattr(vc, "disconnect") and callable(vc.disconnect):
                try:
                    await asyncio.wait_for(vc.disconnect(force=True), timeout=2.0)
                except Exception:
                    pass
            try:
                vc.cleanup()
            except Exception:
                pass
            try:
                # Force-close websocket and transport socket without blocking on Gateway disconnect waiter
                conn = getattr(vc, "_connection", None)
                if conn:
                    if hasattr(conn, "ws") and conn.ws:
                        await conn.ws.close()
                    if hasattr(conn, "socket") and conn.socket:
                        conn.socket.close()
            except Exception:
                pass

        # Directly ensure the voice client is removed from discord.py ConnectionState dict
        if state and hasattr(state, "_voice_clients") and isinstance(state._voice_clients, dict):
            state._voice_clients.pop(guild_id, None)
        if state and hasattr(state, "_remove_voice_client"):
            try:
                state._remove_voice_client(guild_id)
            except Exception:
                pass

        # Send channel=None voice state update to Discord Gateway to reset session state
        try:
            await asyncio.shield(guild.change_voice_state(channel=None))
        except Exception as gw_err:
            logger.debug(f"[Voice] [Purge] Voice state change note for guild {guild_id}: {gw_err}")
            cleaned = False

        return cleaned

    @classmethod
    def _inspect_failed_stage(cls, guild: Optional[discord.Guild], exc: Optional[Exception]) -> Tuple[str, str, Optional[str]]:
        """
        Inspects the exact Discord voice connection flow state to pinpoint the true failure stage
        and return actionable, evidence-based user guidance.
        """
        if not guild:
            return ("Connection Initialization", "Guild information unavailable. Check bot guild permissions.", None)

        vc = getattr(guild, "voice_client", None)
        conn = getattr(vc, "_connection", None) if vc else None
        flow_state = getattr(conn, "state", None)

        flow_name = str(flow_state) if flow_state is not None else None

        # Check ConnectionFlowState enum from discord.py
        try:
            from discord.voice_state import ConnectionFlowState
        except ImportError:
            ConnectionFlowState = None

        if ConnectionFlowState and flow_state is not None:
            if flow_state in (ConnectionFlowState.disconnected, ConnectionFlowState.set_guild_voice_state):
                return (
                    "Gateway Voice State Request",
                    "Discord Gateway did not acknowledge the voice connection request in time. "
                    "The Discord Gateway may be experiencing transient latency or rate limits. Please try again.",
                    flow_name,
                )
            elif flow_state in (ConnectionFlowState.got_voice_state_update, ConnectionFlowState.got_voice_server_update):
                return (
                    "Gateway Voice Server Allocation",
                    "Discord acknowledged the voice state request, but did not allocate a voice server endpoint in time. "
                    "Discord voice server infrastructure in this region may be temporarily congested.",
                    flow_name,
                )
            elif flow_state == ConnectionFlowState.got_both_voice_updates:
                return (
                    "Voice WebSocket Handshake",
                    "Discord allocated a voice endpoint, but MusicMaid could not complete the Voice WebSocket handshake. "
                    "Check bot hosting connectivity, outbound TCP/WebSocket access, and Discord service status.",
                    flow_name,
                )
            elif flow_state == ConnectionFlowState.websocket_connected:
                return (
                    "Voice Session Ready Acknowledgment",
                    "The Voice WebSocket connected, but timed out waiting for Discord's Ready payload.",
                    flow_name,
                )
            elif flow_state == ConnectionFlowState.got_websocket_ready:
                return (
                    "UDP Voice Transport & IP Discovery",
                    "Voice WebSocket handshake succeeded, but UDP voice transport packets could not reach Discord. "
                    "Check your hosting provider's outbound UDP firewall policies. "
                    "(Optionally, temporarily changing Region Override in channel settings to a different region may route through an accessible UDP cluster).",
                    flow_name,
                )
            elif flow_state == ConnectionFlowState.got_ip_discovery:
                return (
                    "Voice Encryption Protocol Selection",
                    "UDP IP discovery succeeded, but voice transport encryption protocol negotiation timed out.",
                    flow_name,
                )

        # Check explicit dependency missing exceptions
        exc_str = str(exc or "").lower()
        if (isinstance(exc, RuntimeError) and ("davey" in exc_str or "dave" in exc_str)) or "davey" in exc_str:
            return (
                "Voice Dependency Missing (davey)",
                "The 'davey' library is missing in the bot hosting environment. Discord voice channels require the DAVE protocol for voice encryption. "
                "Add `davey>=0.1.0` or `discord.py[voice]` to requirements.txt and re-deploy.",
                flow_name,
            )

        if (isinstance(exc, RuntimeError) and "pynacl" in exc_str) or "nacl" in exc_str:
            return (
                "Voice Dependency Missing (PyNaCl)",
                "The PyNaCl cryptographic library is not installed or failed to initialize. "
                "Discord voice connections require PyNaCl for packet encryption. Please ensure PyNaCl is installed.",
                flow_name,
            )

        try:
            from discord.opus import OpusNotLoaded
            is_opus_err = isinstance(exc, OpusNotLoaded)
        except ImportError:
            is_opus_err = False

        if is_opus_err or (isinstance(exc, RuntimeError) and "opus" in exc_str) or "opus" in exc_str:
            return (
                "Voice Dependency Missing (Opus)",
                "The Opus audio codec library (libopus) is not loaded or missing on this system. "
                "Voice streaming requires libopus. Please ensure libopus is installed in the hosting environment.",
                flow_name,
            )

        if isinstance(exc, discord.errors.Forbidden) or "permission" in exc_str:
            return (
                "Discord Permission Denied",
                "MusicMaid was rejected with 403 Forbidden. Please verify that the bot has 'Connect' and 'Speak' permissions.",
                flow_name,
            )

        if isinstance(exc, discord.ClientException):
            return (
                "Gateway Voice State Desynchronization",
                "Internal Discord voice client state desynchronized with Discord Gateway. Stale session state was purged; please try again.",
                flow_name,
            )

        if isinstance(exc, asyncio.TimeoutError):
            return (
                "Gateway & Voice WebSocket Handshake",
                "Voice connection timed out during signaling. Check bot gateway connection and hosting outbound network stability.",
                flow_name,
            )

        return (
            "Voice Signaling & Connection",
            f"Voice connection encountered an unexpected error: {exc or 'Unknown error'}. Check bot logs.",
            flow_name,
        )

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
        target_channel = member.voice.channel

        # Concurrency Gate: Check if a connection task is already active for this guild
        existing_task = cls._in_flight_tasks.get(guild_id)
        if existing_task and not existing_task.done():
            in_flight_ch = cls._in_flight_channels.get(guild_id)
            if in_flight_ch == target_channel.id:
                logger.info(
                    f"[Voice] [Concurrency] Connection to voice for guild {guild_id} (#{target_channel.name}) "
                    f"is already in-flight. Coalescing simultaneous request..."
                )
                try:
                    return await asyncio.shield(existing_task)
                except Exception as wait_err:
                    logger.debug(f"[Voice] Coalesced wait error for guild {guild_id}: {wait_err}")
            else:
                logger.info(
                    f"[Voice] [Concurrency] Superseding in-flight connection for guild {guild_id}: "
                    f"target channel changed to #{target_channel.name}"
                )
                existing_task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(existing_task), timeout=1.5)
                except (Exception, asyncio.CancelledError):
                    pass

        # Acquire per-guild lock to ensure serialized connection lifecycles
        lock = cls._get_guild_lock(guild_id)
        async with lock:
            # Re-check existing in-flight task after acquiring lock
            existing_task = cls._in_flight_tasks.get(guild_id)
            if existing_task and not existing_task.done():
                try:
                    return await asyncio.shield(existing_task)
                except (Exception, asyncio.CancelledError):
                    pass

            # Create and register the in-flight worker task
            loop = asyncio.get_running_loop()
            task: asyncio.Task[Optional[discord.VoiceClient]] = loop.create_task(
                cls._execute_join_pipeline(member, text_channel, session),
                name=f"VoiceConnect-{guild_id}-{target_channel.id}",
            )
            cls._in_flight_tasks[guild_id] = task
            cls._in_flight_channels[guild_id] = target_channel.id
            try:
                return await task
            finally:
                if cls._in_flight_tasks.get(guild_id) is task:
                    cls._in_flight_tasks.pop(guild_id, None)
                cls._in_flight_channels.pop(guild_id, None)

    @classmethod
    async def _execute_join_pipeline(
        cls, member: discord.Member, text_channel: discord.TextChannel, session: GuildMusicSession
    ) -> Optional[discord.VoiceClient]:
        """Internal worker executing the voice connection sequence with granular diagnostic telemetry."""
        t_start = time.monotonic()
        target_channel = member.voice.channel if member.voice else None
        if not target_channel or not member.guild:
            return None

        guild_id = member.guild.id
        session.text_channel = text_channel

        # Initialize telemetry record
        telemetry = VoiceTelemetry(
            guild_id=guild_id,
            channel_id=target_channel.id,
            channel_name=target_channel.name,
            stage="Pre-flight",
        )
        cls._telemetry[guild_id] = telemetry

        # =========================================================================
        # STAGE 1: PRE-FLIGHT AUDIT (AFK Sentry, Bot Channel Access, Permissions)
        # =========================================================================
        if member.guild.afk_channel and target_channel.id == member.guild.afk_channel.id:
            logger.warning(f"[Voice] [Stage 1: Pre-flight] Blocked joining AFK voice channel in guild {guild_id}")
            err = "Cannot play music in the server's AFK voice channel."
            session.last_error = err
            telemetry.last_error = err
            telemetry.stage = "AFK Channel Sentry"
            return None

        # Channel user limit check (if full and bot lacks move_members permission)
        user_limit = getattr(target_channel, "user_limit", 0)
        members_list = getattr(target_channel, "members", [])
        if isinstance(user_limit, int) and user_limit > 0:
            if isinstance(members_list, (list, tuple)) and len(members_list) >= user_limit:
                bot_perms = target_channel.permissions_for(member.guild.me) if member.guild.me else None
                if not (bot_perms and bot_perms.move_members):
                    err = f"Voice channel {target_channel.mention} is full (`{len(members_list)}/{user_limit}`)."
                    logger.warning(f"[Voice] [Stage 1: Pre-flight] Guild {guild_id}: {err}")
                    session.last_error = err
                    telemetry.last_error = err
                    telemetry.stage = "Channel Full"
                    return None

        # Cancel pending auto-leave inactivity timer
        if session.auto_leave_task and not session.auto_leave_task.done():
            session.auto_leave_task.cancel()
            session.auto_leave_task = None

        # Permissions check: Fast-fail permanent permission errors without retries
        if member.guild.me:
            perms = target_channel.permissions_for(member.guild.me)
            if not perms.connect:
                err = f"Missing **Connect** permission in {target_channel.mention}"
                logger.warning(f"[Voice] [Stage 1: Pre-flight] Guild {guild_id}: {err}")
                session.last_error = err
                telemetry.last_error = err
                telemetry.stage = "Missing Connect Permission"
                return None
            if not perms.speak:
                err = f"Missing **Speak** permission in {target_channel.mention}"
                logger.warning(f"[Voice] [Stage 1: Pre-flight] Guild {guild_id}: {err}")
                session.last_error = err
                telemetry.last_error = err
                telemetry.stage = "Missing Speak Permission"
                return None

        # Dependency check: Fast-fail if PyNaCl, davey, or Opus is missing in the runtime
        try:
            from discord.voice_client import has_nacl, has_dave
        except ImportError:
            try:
                from discord.voice_client import has_nacl  # type: ignore
                has_dave = True
            except ImportError:
                has_nacl = False
                has_dave = False

        if not has_nacl:
            err = "PyNaCl library is missing in the bot environment. Discord voice requires PyNaCl."
            logger.error(f"[Voice] [Stage 1: Pre-flight FAIL] Guild {guild_id}: {err}")
            err_msg = (
                f"Voice connection failed: Missing required voice dependency (PyNaCl).\n"
                f"• **Failed Stage:** `Voice Dependency Missing (PyNaCl)`\n"
                f"• **Target Channel:** {target_channel.mention}\n\n"
                f"💡 **Recommended Action:**\nInstall `PyNaCl>=1.5.0` in the hosting environment to enable voice support."
            )
            session.state = PlaybackState.ERROR
            session.last_error = err_msg
            telemetry.last_error = err
            telemetry.stage = "Voice Dependency Missing (PyNaCl)"
            telemetry.success = False
            return None

        if not has_dave:
            err = "The 'davey' library is missing in the bot environment. Discord requires davey for voice encryption."
            logger.error(f"[Voice] [Stage 1: Pre-flight FAIL] Guild {guild_id}: {err}")
            err_msg = (
                f"Voice connection failed: Missing required voice dependency (davey).\n"
                f"• **Failed Stage:** `Voice Dependency Missing (davey)`\n"
                f"• **Target Channel:** {target_channel.mention}\n\n"
                f"💡 **Recommended Action:**\nInstall `davey>=0.1.0` (or `pip install \"discord.py[voice]\"`) in the bot hosting environment to enable Discord E2EE voice support."
            )
            session.state = PlaybackState.ERROR
            session.last_error = err_msg
            telemetry.last_error = err
            telemetry.stage = "Voice Dependency Missing (davey)"
            telemetry.success = False
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
                telemetry.stage = "Connected (Reused)"
                telemetry.success = True
                telemetry.elapsed_ms = stage2_ms
                telemetry.last_connected_at = time.time()
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
                telemetry.stage = "Connected (Moved)"
                telemetry.success = True
                telemetry.elapsed_ms = stage2_ms
                telemetry.last_connected_at = time.time()
                return existing_vc
            except Exception as move_err:
                logger.warning(f"[Voice] [Stage 2: Move Warning] Move failed ({move_err}). Purging state before reconnect...")
                await cls._purge_voice_client_state(member.guild)

        elif existing_vc:
            # Stale / orphaned VoiceClient cleanup
            logger.info(f"[Voice] [Stage 2: Stale Cleanup] Clearing orphaned VoiceClient in guild {guild_id}...")
            await cls._purge_voice_client_state(member.guild)
            await asyncio.sleep(0.5)

        # =========================================================================
        # STAGE 3-5: BOUNDED HANDSHAKE & UDP TRANSMISSION NEGOTIATION
        # =========================================================================
        max_attempts = 3
        last_exception: Optional[Exception] = None
        current_stage = "Gateway Signaling"

        for attempt in range(1, max_attempts + 1):
            t_attempt = time.monotonic()
            session.state = PlaybackState.CONNECTING
            telemetry.attempt = attempt

            # Dynamic timeout per attempt: 15s on first attempt, 20s on retries
            connect_timeout = 15.0 if attempt == 1 else 20.0

            logger.info(
                f"[Voice] [Stage 3: Gateway Signaling] Guild {guild_id} | Connecting to #{target_channel.name} "
                f"(Attempt {attempt}/{max_attempts}, timeout={connect_timeout}s)..."
            )

            # Ensure discord.py's internal state dict has no stale voice client key before connect()
            state = getattr(member.guild, "_state", None)
            if state and hasattr(state, "_voice_clients") and isinstance(state._voice_clients, dict):
                state._voice_clients.pop(guild_id, None)

            try:
                current_stage = "Gateway & Voice WebSocket Handshake"
                telemetry.stage = current_stage

                vc = await asyncio.wait_for(
                    target_channel.connect(timeout=connect_timeout, reconnect=True, self_deaf=True),
                    timeout=connect_timeout + 3.0,
                )

                current_stage = "UDP Transmission Verification"
                telemetry.stage = current_stage

                if vc and vc.is_connected():
                    session.voice_client = vc
                    session.state = PlaybackState.CONNECTED
                    session.last_error = None
                    total_dur_ms = (time.monotonic() - t_start) * 1000
                    logger.info(
                        f"[Voice] [Stage 4/5: UDP Handshake PASS] Guild {guild_id} | "
                        f"Connected to #{target_channel.name} in {total_dur_ms:.1f}ms (Attempt {attempt}) 🚀"
                    )
                    telemetry.stage = "Connected"
                    telemetry.success = True
                    telemetry.elapsed_ms = total_dur_ms
                    telemetry.last_connected_at = time.time()
                    return vc

                # Fallback check: Did guild VoiceClient connect despite edge condition?
                if member.guild.voice_client and member.guild.voice_client.is_connected():
                    curr_vc = member.guild.voice_client
                    session.voice_client = curr_vc
                    session.state = PlaybackState.CONNECTED
                    session.last_error = None
                    total_dur_ms = (time.monotonic() - t_start) * 1000
                    logger.info(f"[Voice] [Stage 5: State Verified] VoiceClient verified connected in {total_dur_ms:.1f}ms")
                    telemetry.stage = "Connected"
                    telemetry.success = True
                    telemetry.elapsed_ms = total_dur_ms
                    telemetry.last_connected_at = time.time()
                    return curr_vc

                raise RuntimeError("VoiceClient connect returned but is_connected() is False.")

            except asyncio.CancelledError:
                logger.info(f"[Voice] Connection task cancelled for guild {guild_id}.")
                await cls._purge_voice_client_state(member.guild)
                telemetry.stage = "Cancelled"
                raise

            except discord.ClientException as ce:
                last_exception = ce
                logger.warning(f"[Voice] [Attempt {attempt} ClientException] Guild {guild_id}: {ce}")

                # Check if guild VoiceClient is actually connected and in target channel
                curr_vc = member.guild.voice_client
                if curr_vc and curr_vc.is_connected() and curr_vc.channel and curr_vc.channel.id == target_channel.id:
                    session.voice_client = curr_vc
                    session.state = PlaybackState.CONNECTED
                    session.last_error = None
                    total_dur_ms = (time.monotonic() - t_start) * 1000
                    telemetry.stage = "Connected"
                    telemetry.success = True
                    telemetry.elapsed_ms = total_dur_ms
                    telemetry.last_connected_at = time.time()
                    return curr_vc

                # Desynchronization detected: purge stale state before retry
                current_stage = "Gateway Voice State Desynchronization"
                telemetry.stage = current_stage
                await cls._purge_voice_client_state(member.guild)

                if attempt < max_attempts:
                    backoff = (attempt * 1.0) + random.uniform(0.1, 0.4)
                    logger.info(f"[Voice] Backing off {backoff:.2f}s after ClientException before retry {attempt + 1}...")
                    await asyncio.sleep(backoff)

            except asyncio.TimeoutError as t_err:
                last_exception = t_err
                att_ms = (time.monotonic() - t_attempt) * 1000
                stage_name, _, flow_name = cls._inspect_failed_stage(member.guild, t_err)
                current_stage = stage_name
                telemetry.stage = current_stage
                telemetry.flow_state = flow_name

                logger.warning(
                    f"[Voice] [Attempt {attempt} TIMEOUT] Guild {guild_id} | Failed at '{current_stage}' "
                    f"(flow_state={flow_name}) after {att_ms:.1f}ms (Timeout={connect_timeout}s)"
                )
                await cls._purge_voice_client_state(member.guild)

                if attempt < max_attempts:
                    backoff = (attempt * 1.5) + random.uniform(0.2, 0.5)
                    logger.info(f"[Voice] Backing off {backoff:.2f}s before retry {attempt + 1}/{max_attempts}...")
                    await asyncio.sleep(backoff)

            except Exception as e:
                last_exception = e
                stage_name, _, flow_name = cls._inspect_failed_stage(member.guild, e)
                current_stage = stage_name
                telemetry.stage = current_stage
                telemetry.flow_state = flow_name
                logger.error(f"[Voice] [Attempt {attempt} Error] Unexpected error at '{current_stage}': {e}", exc_info=True)
                await cls._purge_voice_client_state(member.guild)

                # Fast-fail without retries on unrecoverable/permanent errors
                e_str = str(e).lower()
                is_permanent = (
                    isinstance(e, discord.errors.Forbidden)
                    or "pynacl" in e_str
                    or "davey" in e_str
                    or "dave" in e_str
                    or "opus" in e_str
                    or "not installed" in e_str
                )
                if is_permanent:
                    logger.info(f"[Voice] Non-retriable error '{stage_name}' detected. Fast-failing attempt loop.")
                    break

                if attempt < max_attempts:
                    backoff = (attempt * 1.5) + random.uniform(0.2, 0.5)
                    await asyncio.sleep(backoff)

        # All attempts failed: format evidence-based user diagnostic
        total_fail_ms = (time.monotonic() - t_start) * 1000
        stage_title, stage_advice, flow_name = cls._inspect_failed_stage(member.guild, last_exception)

        attempts_made = telemetry.attempt or 1
        if isinstance(last_exception, asyncio.TimeoutError):
            fail_header = f"Voice connection timed out after {attempts_made} attempt{'s' if attempts_made > 1 else ''} ({total_fail_ms:.0f}ms)."
        else:
            err_detail = str(last_exception) if last_exception else "Connection failure"
            fail_header = f"Voice connection failed after {attempts_made} attempt{'s' if attempts_made > 1 else ''} ({total_fail_ms:.0f}ms): {err_detail}."

        err_msg = (
            f"Voice connection failed: {fail_header}\n"
            f"• **Failed Stage:** `{stage_title}`\n"
            f"• **Target Channel:** {target_channel.mention}\n\n"
            f"💡 **Recommended Action:**\n{stage_advice}"
        )
        logger.error(f"[Voice] [Connection Exhausted] Guild {guild_id}: {err_msg} (Last error: {last_exception})")

        telemetry.stage = stage_title
        telemetry.elapsed_ms = total_fail_ms
        telemetry.last_error = str(last_exception)
        telemetry.success = False

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
