"""
Dedicated Discord Client and Gateway Manager for Neko Songs.
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
    BOT_NAME,
    COMMAND_SYNC_MODE,
    MUSIC_BOT_ID,
    MUSIC_BOT_VERSION,
    MUSIC_PREFIX,
    TEST_GUILD_ID,
)
from music_bot.database.db import MusicDatabase
from music_bot.services.session_service import SessionManager

logger = logging.getLogger("NekoSongs.Client")


async def _determine_prefix(bot: NekoSongsBot, message: discord.Message) -> List[str]:
    """Dynamic multi-prefix resolver with per-guild customization support."""
    prefixes: List[str] = []
    if message.guild:
        guild_pref = await bot.get_guild_prefix(message.guild.id)
        if guild_pref:
            prefixes.append(guild_pref)
    if not prefixes:
        prefixes.append(",")
    if "m!" not in prefixes:
        prefixes.append("m!")
    return commands.when_mentioned_or(*prefixes)(bot, message)


class NekoSongsBot(commands.Bot):
    """Independent Discord Bot application powering Neko Songs."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        intents.messages = True
        intents.message_content = True  # For prefix & natural requests

        super().__init__(
            command_prefix=_determine_prefix,
            intents=intents,
            help_command=None,
        )

        self.db = MusicDatabase()
        self.session_manager = SessionManager.get_instance()
        self._prefix_cache: Dict[int, str] = {}
        import time
        self.started_at = time.time()
        self.is_upgrading: bool = False

    async def get_guild_prefix(self, guild_id: int) -> str:
        """Fetch custom prefix for guild with in-memory caching."""
        if guild_id in self._prefix_cache:
            return self._prefix_cache[guild_id]
        try:
            settings = await self.db.get_guild_settings(guild_id)
            prefix = settings.prefix or ","
            self._prefix_cache[guild_id] = prefix
            return prefix
        except Exception:
            return ","

    def set_cached_prefix(self, guild_id: int, prefix: str) -> None:
        """Update prefix in memory cache."""
        self._prefix_cache[guild_id] = prefix

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Global interaction interceptor to eliminate 'The application did not respond' during updates."""
        if getattr(self, "is_upgrading", False):
            embed = discord.Embed(
                title="⚙️ The upgrade is in process, please wait...",
                description=(
                    "The music bot is currently updating its code and components.\n\n"
                    "⏳ **Seamless Continuity Active:**\n"
                    "• Your song position and queue are safely saved.\n"
                    "• The song will resume playing right where it left off (not from the beginning)!\n\n"
                    "Please wait a few seconds and try again."
                ),
                color=0xFEE75C,
            )
            embed.set_footer(text="Neko Songs • Continuous Live Playback")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception:
                pass
            return

        # Fallback safeguard: guarantee no music component button times out
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
            if custom_id.startswith("music_btn_") and not interaction.response.is_done():
                try:
                    await interaction.response.defer(ephemeral=True)
                except Exception:
                    pass

    async def on_message(self, message: discord.Message) -> None:
        """Process messages and dispatch prefix commands with upgrade gatekeeper."""
        if message.author.bot:
            return

        if getattr(self, "is_upgrading", False):
            prefix = await self.get_guild_prefix(message.guild.id) if message.guild else ","
            if message.content.startswith(prefix) or message.content.startswith(","):
                embed = discord.Embed(
                    title="⚙️ The upgrade is in process, please wait...",
                    description=(
                        "The music bot is currently updating its code.\n\n"
                        "⏳ **Playback will resume right where it left off!** Please wait a few seconds."
                    ),
                    color=0xFEE75C,
                )
                try:
                    await message.reply(embed=embed, delete_after=8)
                except Exception:
                    pass
                return

        await self.process_commands(message)

    async def setup_hook(self) -> None:
        """Executed during bot startup before connecting to Discord Gateway."""
        logger.info(f"Initializing {BOT_NAME} subsystem...")

        # 1. Connect independent database
        await self.db.connect()

        # 2. Add MusicCog
        await self.add_cog(MusicCog(self))

        # 2a. Register persistent Now Playing control view so buttons across restarts always work
        try:
            from music_bot.services.player_service import NowPlayingControlView
            self.add_view(NowPlayingControlView())
            logger.info("Registered persistent NowPlayingControlView for zero-timeout music controls.")
        except Exception as e:
            logger.warning(f"Could not register persistent NowPlayingControlView: {e}")

        # 2b. Global Tree Error Handler & Upgrade Interceptor
        async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
            orig = getattr(error, "original", error)
            if isinstance(orig, discord.NotFound) and getattr(orig, "code", None) == 10062:
                logger.debug(f"Ignored expired/unknown interaction in {interaction.command}")
                return

            if isinstance(orig, asyncio.TimeoutError):
                msg = "⏱️ **Audio Request Timed Out:** The audio search or voice connection took too long to respond. Please try again with a direct URL or different query."
            else:
                msg = f"⚠️ **Music Command Notice:** {str(orig or error)}"

            logger.error(f"App command error in {interaction.command}: {error}", exc_info=orig)
            try:
                if interaction.response.is_done():
                    try:
                        await interaction.edit_original_response(content=msg, embed=None, view=None)
                    except Exception:
                        await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
            except Exception:
                pass
        self.tree.on_error = on_tree_error

        async def tree_interaction_check(interaction: discord.Interaction) -> bool:
            if getattr(self, "is_upgrading", False):
                embed = discord.Embed(
                    title="⚙️ The upgrade is in process, please wait...",
                    description=(
                        "The music bot is currently updating its code and components.\n\n"
                        "⏳ **Seamless Continuity Active:**\n"
                        "• Your song position and queue are safely saved.\n"
                        "• The song will resume playing right where it left off (not from the beginning)!\n\n"
                        "Please wait a few seconds and try again."
                    ),
                    color=0xFEE75C,
                )
                embed.set_footer(text="Neko Songs • Continuous Live Playback")
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                    else:
                        await interaction.followup.send(embed=embed, ephemeral=True)
                except Exception:
                    pass
                return False
            return True
        self.tree.interaction_check = tree_interaction_check

        # 3. Synchronize application commands
        try:
            if COMMAND_SYNC_MODE == "guild" and TEST_GUILD_ID:
                guild = discord.Object(id=TEST_GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(f"Synchronized {len(synced)} slash commands to test guild {TEST_GUILD_ID}")
            else:
                synced = await self.tree.sync()
                logger.info(f"Synchronized {len(synced)} global slash commands for {BOT_NAME}")
        except Exception as e:
            logger.error(f"Failed to synchronize slash commands: {e}")

        # 4. Start background loops
        self.heartbeat_loop.start()
        self.maintenance_loop.start()
        self.snapshot_loop.start()

    @tasks.loop(seconds=5.0)
    async def snapshot_loop(self) -> None:
        """Continuously snapshots live track positions and handles gapless audio pre-caching."""
        try:
            from music_bot.services.player_service import MusicPlayerService
            await MusicPlayerService.snapshot_all_active_sessions(self)

            # Feature: Gapless Transition Audio Buffer Pre-Caching (at >=85% song progress)
            for session in self.session_manager.get_all_sessions():
                if session.is_playing and session.current_track and session.current_track.duration > 15:
                    if (session.elapsed_seconds / session.current_track.duration) >= 0.85:
                        if session.queue and not getattr(session.queue[0], "_precached", False):
                            session.queue[0]._precached = True
                            asyncio.create_task(MusicPlayerService._precache_track(session.queue[0]))

                # Feature: Neko DJ Non-Stop Pre-Buffer (maintains continuous queue flow at >=70% progress)
                if session.is_playing and session.current_track and (getattr(session, "dj_enabled", False) or session.autoplay):
                    if len(session.queue) == 0 and session.current_track.duration > 15:
                        if (session.elapsed_seconds / session.current_track.duration) >= 0.70:
                            if not getattr(session, "_dj_prequeued", False):
                                session._dj_prequeued = True
                                async def _buffer_next_dj(s=session):
                                    try:
                                        from music_bot.services.dj_service import NekoDJService
                                        rec = await NekoDJService.get_recommendation(self, s)
                                        if rec and len(s.queue) == 0:
                                            s.queue.append(rec[0])
                                            logger.info(f"Neko DJ Non-Stop pre-buffered: '{rec[0].title}'")
                                    except Exception:
                                        pass
                                asyncio.create_task(_buffer_next_dj())
        except Exception:
            pass

    @snapshot_loop.before_loop
    async def before_snapshot(self) -> None:
        await self.wait_until_ready()

    @tasks.loop(hours=24.0)
    async def maintenance_loop(self) -> None:
        """Feature 139: Automated Music Database DR Snapshots."""
        if not self.db or not self.db._db:
            return
        try:
            import aiosqlite
            backup_dir = Path("data/backups")
            backup_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
            dest = backup_dir / f"music-{ts}.db"
            async with aiosqlite.connect(str(dest)) as target_db:
                await self.db._db.backup(target_db)
            logger.info(f"Autonomous Music DB DR snapshot created: {dest.name}")
        except Exception as e:
            logger.debug(f"Music backup snapshot note: {e}")

    @maintenance_loop.before_loop
    async def before_maintenance(self) -> None:
        await self.wait_until_ready()

    async def on_ready(self) -> None:
        logger.info(
            f"🎵 {BOT_NAME} online as {self.user.name}#{self.user.discriminator} (ID: {self.user.id})"
        )
        logger.info(f"Serving {len(self.guilds)} guilds with independent audio architecture.")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="/music play | Neko Songs 🐱",
            ),
            status=discord.Status.online,
        )

        # Non-blocking background cleanup of guild command copies (prevents on_ready gateway stall)
        async def _cleanup_guild_commands():
            if COMMAND_SYNC_MODE != "guild":
                for guild in self.guilds:
                    try:
                        self.tree.clear_commands(guild=guild)
                        await self.tree.sync(guild=guild)
                        logger.info(f"Cleaned guild command copies in {guild.name} ({guild.id}) to eliminate duplicates.")
                    except Exception as e:
                        logger.debug(f"Guild command cleanup notice for {guild.name}: {e}")
        asyncio.create_task(_cleanup_guild_commands())

        # Feature 109: Auto-Resume active music sessions across restarts
        if self.db:
            try:
                active_saved = await self.db.get_active_sessions()
                for saved in active_saved:
                    guild = self.get_guild(saved["guild_id"])
                    if not guild:
                        continue
                    vc_channel = guild.get_channel(saved.get("voice_channel_id") or 0)
                    text_channel = guild.get_channel(saved.get("text_channel_id") or 0)
                    if isinstance(vc_channel, (discord.VoiceChannel, discord.StageChannel)):
                        session = await self.session_manager.get_session(guild.id)
                        if not session.is_active:
                            session.volume = saved.get("volume", 80)
                            session.text_channel = text_channel
                            vc = await vc_channel.connect(timeout=15.0, reconnect=True)
                            session.voice_client = vc
                            from collections import deque
                            from music_bot.database.models import QueuedTrack
                            if saved.get("history"):
                                session.history = [QueuedTrack.from_dict(t) for t in saved["history"]]
                            if saved.get("queue"):
                                session.queue = deque([QueuedTrack.from_dict(t) for t in saved["queue"]])

                            if saved.get("current_track"):
                                track = QueuedTrack.from_dict(saved["current_track"])
                                from music_bot.services.player_service import MusicPlayerService
                                start_pos = saved.get("position_seconds") or 0
                                if start_pos and start_pos > 3:
                                    await MusicPlayerService.resume_track_stream(self, session, track, start_pos)
                                    logger.info(f"Auto-resumed playback in guild {guild.id} on #{vc_channel.name} at {start_pos}s (where it left off) with {len(session.queue)} in queue, {len(session.history)} in history!")
                                else:
                                    await MusicPlayerService.start_playback(self, session, track)
                                    logger.info(f"Auto-resumed playback in guild {guild.id} on #{vc_channel.name} with {len(session.queue)} in queue, {len(session.history)} in history")
            except Exception as e:
                logger.warning(f"Session auto-resume error: {e}")

            # Auto-Join 24/7 Guild Voice Channels
            try:
                twenty_four_seven_guilds = await self.db.get_all_247_guilds()
                for g_set in twenty_four_seven_guilds:
                    guild = self.get_guild(g_set.guild_id)
                    if not guild:
                        continue
                    session = await self.session_manager.get_session(guild.id)
                    session.twenty_four_seven = True
                    if not session.is_active:
                        target_vc_id = g_set.twenty_four_seven_channel_id
                        vc_channel = guild.get_channel(target_vc_id) if target_vc_id else None
                        if not vc_channel:
                            for ch in guild.voice_channels:
                                if ch.permissions_for(guild.me).connect:
                                    vc_channel = ch
                                    break
                        if isinstance(vc_channel, (discord.VoiceChannel, discord.StageChannel)):
                            try:
                                vc = await vc_channel.connect(timeout=15.0, reconnect=True)
                                session.voice_client = vc
                                logger.info(f"24/7 mode: Connected to #{vc_channel.name} in {guild.name}")
                            except Exception as vc_err:
                                logger.warning(f"Failed to 24/7 connect in guild {guild.id}: {vc_err}")
            except Exception as e:
                logger.warning(f"24/7 guilds recovery error: {e}")

        # Initialize Autonomous Dependency & Extractor Updater
        try:
            from music_bot.services.updater_service import MusicAutoUpdater
            MusicAutoUpdater.start_background_updater(self)
        except Exception as e:
            logger.warning(f"Failed to start MusicAutoUpdater: {e}")

    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """Monitor voice states for auto-leave behavior, 24/7 recovery, and stage ducking."""
        # Reconnect 24/7 channels if bot was involuntarily disconnected
        if member.id == self.user.id and not after.channel and before.channel:
            session = await self.session_manager.get_session(member.guild.id)
            if session.twenty_four_seven:
                logger.info(f"Involuntary 24/7 disconnect in guild {member.guild.id}. Reconnecting in 3s...")
                async def _reconnect():
                    await asyncio.sleep(3.0)
                    try:
                        if not session.is_active and before.channel:
                            vc = await before.channel.connect(timeout=15.0, reconnect=True)
                            session.voice_client = vc
                            logger.info(f"Reconnected 24/7 voice channel in guild {member.guild.id}")
                    except Exception as err:
                        logger.warning(f"24/7 reconnection failed: {err}")
                asyncio.create_task(_reconnect())
            return

        if member.bot:
            return

        # Feature 107: Autonomous Voice-Ducking for Stage Announcements
        if before.channel and after.channel and before.channel.id == after.channel.id:
            session = await self.session_manager.get_session(member.guild.id)
            if session.is_playing and session.ducking_enabled and session.voice_client and session.voice_client.channel.id == after.channel.id:
                if before.suppress and not after.suppress:
                    if hasattr(session.voice_client.source, "volume"):
                        session.voice_client.source.volume = max(0.1, (session.volume / 100.0) * 0.25)
                elif not before.suppress and after.suppress:
                    if hasattr(session.voice_client.source, "volume"):
                        session.voice_client.source.volume = session.volume / 100.0

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
        """Gracefully release all resources, voice connections, and DB handles with state preservation."""
        logger.info(f"Initiating graceful shutdown for {BOT_NAME}...")
        self.heartbeat_loop.cancel()
        self.maintenance_loop.cancel()
        self.snapshot_loop.cancel()

        # Feature 109: Save exact playback position & queues across restarts before disconnect
        try:
            from music_bot.services.player_service import MusicPlayerService
            await MusicPlayerService.snapshot_all_active_sessions(self)
            logger.info("Saved all active music sessions & playback timestamps before shutdown.")
        except Exception as e:
            logger.debug(f"Pre-shutdown snapshot notice: {e}")

        # Disconnect all active voice clients without wiping the stored queue
        for session in self.session_manager.get_all_sessions():
            if session.voice_client and session.voice_client.is_connected():
                try:
                    if session.voice_client.is_playing():
                        session.voice_client.stop()
                    await session.voice_client.disconnect(force=True)
                except Exception:
                    pass

        # Close database
        await self.db.close()
        await super().close()
        logger.info(f"{BOT_NAME} shutdown complete.")


# Backwards compatibility alias
RaiMusicBot = NekoSongsBot

