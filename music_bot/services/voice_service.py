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
                await existing_vc.move_to(target_channel)
            return existing_vc
        elif existing_vc:
            try:
                await existing_vc.disconnect(force=True)
            except Exception:
                pass

        try:
            session.state = PlaybackState.CONNECTING
            vc = await asyncio.wait_for(
                target_channel.connect(timeout=8.0, reconnect=True, self_deaf=True),
                timeout=8.0,
            )
            session.voice_client = vc
            session.state = PlaybackState.CONNECTED
            session.last_error = None
            return vc
        except Exception as e:
            logger.error(f"Failed to connect to voice channel {target_channel.id}: {e}")
            session.state = PlaybackState.ERROR
            session.last_error = f"Voice connection failed: {e}"
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
