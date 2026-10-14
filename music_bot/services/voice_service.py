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
    """Manages voice connectivity and auto-leave inactivity timers."""

    @classmethod
    async def join_voice_channel(
        cls, member: discord.Member, text_channel: discord.TextChannel, session: GuildMusicSession
    ) -> Optional[discord.VoiceClient]:
        """Ensure the bot connects to the member's voice channel."""
        if not member.voice or not member.voice.channel:
            return None

        target_channel = member.voice.channel

        # Feature 135: AFK Channel Anti-Join Sentry
        if member.guild and member.guild.afk_channel and target_channel.id == member.guild.afk_channel.id:
            logger.warning(f"Prevented joining AFK voice channel in guild {member.guild.id}")
            return None

        # Cancel any pending auto-leave timer
        if session.auto_leave_task and not session.auto_leave_task.done():
            session.auto_leave_task.cancel()
            session.auto_leave_task = None

        session.text_channel = text_channel

        # Pre-flight channel permission check
        if member.guild and member.guild.me:
            perms = target_channel.permissions_for(member.guild.me)
            if not perms.connect:
                logger.warning(
                    f"Cannot join voice channel '{target_channel.name}' ({target_channel.id}) "
                    f"in guild '{member.guild.name}': Missing CONNECT permission."
                )
                session.last_error = f"Missing **Connect** permission in {target_channel.mention if hasattr(target_channel, 'mention') else target_channel.name}"
                return None
            if not perms.speak:
                logger.warning(
                    f"Cannot join voice channel '{target_channel.name}' ({target_channel.id}) "
                    f"in guild '{member.guild.name}': Missing SPEAK permission."
                )
                session.last_error = f"Missing **Speak** permission in {target_channel.mention if hasattr(target_channel, 'mention') else target_channel.name}"
                return None

        # Reuse or clean up existing voice client in the guild
        existing_vc = member.guild.voice_client if member.guild else None
        if existing_vc and existing_vc.is_connected():
            session.voice_client = existing_vc
            if existing_vc.channel.id != target_channel.id:
                logger.info(f"[Voice] Moving connected voice client to target channel #{target_channel.name} ({target_channel.id})...")
                try:
                    await asyncio.wait_for(existing_vc.move_to(target_channel), timeout=15.0)
                except Exception as move_err:
                    logger.warning(f"[Voice] Error moving voice client: {move_err}")
            return existing_vc
        elif existing_vc:
            logger.info(f"[Voice] Stale or non-connected VoiceClient detected in guild {member.guild.id}. Cleaning up before connecting...")
            try:
                await existing_vc.disconnect(force=True)
            except Exception as d_err:
                logger.debug(f"[Voice] Stale disconnect notice: {d_err}")
            try:
                if member.guild:
                    await member.guild.change_voice_state(channel=None)
            except Exception:
                pass
            await asyncio.sleep(1.5)

        max_attempts = 3
        connect_timeout = 45.0
        last_exception: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                session.state = PlaybackState.CONNECTING
                logger.info(
                    f"[Voice] Connecting to #{target_channel.name} ({target_channel.id}) "
                    f"in guild '{member.guild.name}' (attempt {attempt}/{max_attempts}, timeout={connect_timeout}s)..."
                )
                vc = await asyncio.wait_for(
                    target_channel.connect(timeout=connect_timeout, reconnect=True, self_deaf=True),
                    timeout=connect_timeout + 5.0,
                )
                session.voice_client = vc
                session.state = PlaybackState.CONNECTED
                session.last_error = None
                logger.info(
                    f"[Voice] Successfully connected to #{target_channel.name} in '{member.guild.name}'. "
                    f"Voice UDP audio transmission negotiated successfully."
                )
                return vc

            except asyncio.TimeoutError as t_err:
                last_exception = t_err
                logger.warning(
                    f"[Voice] Connection timed out on attempt {attempt}/{max_attempts} for #{target_channel.name} "
                    f"during signalling / UDP state negotiation. (Exceeded {connect_timeout}s)"
                )
                try:
                    if member.guild and member.guild.voice_client:
                        await member.guild.voice_client.disconnect(force=True)
                    if member.guild:
                        await member.guild.change_voice_state(channel=None)
                except Exception:
                    pass

                if attempt < max_attempts:
                    backoff = attempt * 2.0
                    logger.info(f"[Voice] Backing off for {backoff:.1f}s before retry {attempt + 1}/{max_attempts}...")
                    await asyncio.sleep(backoff)

            except discord.ClientException as ce:
                last_exception = ce
                logger.warning(f"[Voice] ClientException during voice connect on attempt {attempt}: {ce}")
                # Check if voice client was established despite exception
                if member.guild and member.guild.voice_client and member.guild.voice_client.is_connected():
                    curr_vc = member.guild.voice_client
                    session.voice_client = curr_vc
                    session.state = PlaybackState.CONNECTED
                    session.last_error = None
                    if curr_vc.channel and curr_vc.channel.id != target_channel.id:
                        try:
                            await curr_vc.move_to(target_channel)
                        except Exception as m_err:
                            logger.warning(f"[Voice] Could not move to {target_channel.name}: {m_err}")
                    return curr_vc
                try:
                    if member.guild and member.guild.voice_client:
                        await member.guild.voice_client.disconnect(force=True)
                    if member.guild:
                        await member.guild.change_voice_state(channel=None)
                except Exception:
                    pass
                if attempt < max_attempts:
                    await asyncio.sleep(attempt * 1.0)

            except Exception as e:
                last_exception = e
                logger.error(f"[Voice] Unexpected error connecting to voice #{target_channel.id} on attempt {attempt}: {e}")
                try:
                    if member.guild and member.guild.voice_client:
                        await member.guild.voice_client.disconnect(force=True)
                    if member.guild:
                        await member.guild.change_voice_state(channel=None)
                except Exception:
                    pass
                if attempt < max_attempts:
                    await asyncio.sleep(attempt * 1.0)

        # All attempts failed: report diagnostic
        err_msg = (
            f"Voice connection failed after {max_attempts} attempts: "
            f"Timed out during Discord voice signalling / UDP transmission negotiation.\n"
            f"💡 **Network & UDP Diagnostic:**\n"
            f"• Outbound UDP audio packets to Discord voice media servers (ports 50000–65535) could not be negotiated.\n"
            f"• Ensure your firewall, router NAT, or host provider allows outbound UDP traffic.\n"
            f"• If a VPN is active, try disabling it or switching locations.\n"
            f"• Ensure MusicMaid has Connect and Speak permissions in {target_channel.mention}."
        )
        logger.error(f"[Voice] {err_msg} (Last exception: {last_exception})")
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
