"""
Dedicated Discord Client and Gateway Manager for Rai Music Bot.
Operates completely independently with its own intents, heartbeat, database, and life cycle.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
import discord
from discord.ext import commands, tasks

from music_bot.commands.music_cog import MusicCog
from music_bot.config import (
    COMMAND_SYNC_MODE,
    MUSIC_BOT_ID,
    MUSIC_BOT_VERSION,
    MUSIC_PREFIX,
    TEST_GUILD_ID,
)
from music_bot.database.db import MusicDatabase
from music_bot.services.session_service import SessionManager

logger = logging.getLogger("RaiMusic.Client")


class RaiMusicBot(commands.Bot):
    """Independent Discord Bot application powering Rai Music."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        intents.messages = True
        intents.message_content = True  # For natural music requests in designated channel

        super().__init__(
            command_prefix=commands.when_mentioned_or(MUSIC_PREFIX),
            intents=intents,
            help_command=None,
        )

        self.db = MusicDatabase()
        self.session_manager = SessionManager.get_instance()
        self.started_at = asyncio.get_event_loop().time()

    async def setup_hook(self) -> None:
        """Executed during bot startup before connecting to Discord Gateway."""
        logger.info("Initializing Rai Music Bot subsystem...")

        # 1. Connect independent database
        await self.db.connect()

        # 2. Add MusicCog
        await self.add_cog(MusicCog(self))

        # 3. Synchronize application commands
        try:
            if COMMAND_SYNC_MODE == "guild" and TEST_GUILD_ID:
                guild = discord.Object(id=TEST_GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(f"Synchronized {len(synced)} slash commands to test guild {TEST_GUILD_ID}")
            else:
                synced = await self.tree.sync()
                logger.info(f"Synchronized {len(synced)} global slash commands for Rai Music Bot")
        except Exception as e:
            logger.error(f"Failed to synchronize slash commands: {e}")

        # 4. Start heartbeat background loop
        self.heartbeat_loop.start()

    async def on_ready(self) -> None:
        logger.info(
            f"🎵 Rai Music Bot online as {self.user.name}#{self.user.discriminator} (ID: {self.user.id})"
        )
        logger.info(f"Serving {len(self.guilds)} guilds with independent music architecture.")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="/music play | /play",
            ),
            status=discord.Status.online,
        )

    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """Monitor voice states for auto-leave behavior when channel becomes empty."""
        if member.bot:
            return

        # Check if user left a channel where Music Bot is currently connected
        if before.channel and (not after.channel or before.channel.id != after.channel.id):
            session = await self.session_manager.get_session(member.guild.id)
            if session.voice_client and session.voice_client.channel.id == before.channel.id:
                humans = [m for m in before.channel.members if not m.bot]
                if not humans:
                    from music_bot.services.voice_service import VoiceManager
                    VoiceManager.schedule_auto_leave(self, session)

    @tasks.loop(seconds=15.0)
    async def heartbeat_loop(self) -> None:
        """Periodically broadcast heartbeat for Main Rai, API, and Website discovery."""
        if not self.user:
            return

        active = self.session_manager.get_active_sessions_count()
        playing = self.session_manager.get_playing_sessions_count()

        try:
            await self.db.update_heartbeat(
                bot_id=self.user.id,
                version=MUSIC_BOT_VERSION,
                status="ONLINE",
                active_sessions=active,
                playing_count=playing,
            )
        except Exception as e:
            logger.debug(f"Heartbeat write error: {e}")

    @heartbeat_loop.before_loop
    async def before_heartbeat(self) -> None:
        await self.wait_until_ready()

    async def close(self) -> None:
        """Gracefully release all resources, voice connections, and DB handles."""
        logger.info("Initiating graceful shutdown for Rai Music Bot...")
        self.heartbeat_loop.cancel()

        # Disconnect all active voice clients
        for session in self.session_manager.get_all_sessions():
            if session.voice_client and session.voice_client.is_connected():
                try:
                    session.queue.clear()
                    if session.voice_client.is_playing():
                        session.voice_client.stop()
                    await session.voice_client.disconnect(force=True)
                except Exception:
                    pass

        # Close database
        await self.db.close()
        await super().close()
        logger.info("Rai Music Bot shutdown complete.")
