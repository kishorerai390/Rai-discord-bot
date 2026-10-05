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

        # Cancel any pending auto-leave timer
        if session.auto_leave_task and not session.auto_leave_task.done():
            session.auto_leave_task.cancel()
            session.auto_leave_task = None

        session.text_channel = text_channel

        if session.voice_client and session.voice_client.is_connected():
            if session.voice_client.channel.id != target_channel.id:
                await session.voice_client.move_to(target_channel)
            return session.voice_client

        try:
            session.state = PlaybackState.CONNECTING
            vc = await target_channel.connect(timeout=15.0, reconnect=True)
            session.voice_client = vc
            session.state = PlaybackState.CONNECTED
            return vc
        except Exception as e:
            logger.error(f"Failed to connect to voice channel {target_channel.id}: {e}")
            session.state = PlaybackState.ERROR
            return None

    @classmethod
    def schedule_auto_leave(cls, bot: RaiMusicBot, session: GuildMusicSession, timeout: int = AUTO_LEAVE_TIMEOUT_SECONDS) -> None:
        """Schedule automatic disconnection if voice channel remains empty."""
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
                if not session.voice_client or not session.voice_client.is_connected():
                    return

                channel = session.voice_client.channel
                # Check for non-bot members
                human_members = [m for m in channel.members if not m.bot]
                if not human_members:
                    logger.info(f"Auto-leaving empty voice channel in guild {session.guild_id}")
                    session.queue.clear()
                    if session.voice_client.is_playing():
                        session.voice_client.stop()
                    await session.voice_client.disconnect()
                    session.voice_client = None
                    session.reset()

                    if session.text_channel:
                        embed = discord.Embed(
                            title="👋 AUTO DISCONNECTED",
                            description=f"Left voice channel because it remained empty for `{timeout // 60}` minutes.",
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
