"""
Dedicated Discord Client and Gateway Manager for Neko Songs.
Operates completely independently with its own intents, heartbeat, database, and life cycle.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from music_bot.commands.music_cog import MusicCog
from music_bot import config
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
    """Dynamic prefix resolver prioritizing custom guild prefix, ?, m!, and comma (,)."""
    prefixes: List[str] = []
    if message.guild:
        guild_pref = await bot.get_guild_prefix(message.guild.id)
        if guild_pref and guild_pref not in prefixes:
            prefixes.append(guild_pref)
    for p in ["?", config.MUSIC_PREFIX or "m!", ",", "m!"]:
        if p and p not in prefixes:
            prefixes.append(p)
    return commands.when_mentioned_or(*prefixes)(bot, message)


class NekoSongsBot(commands.Bot):
    """Independent Discord Bot application powering Neko Songs."""

    def __init__(self):
        # Discord voice Opus codec
        try:
            if not discord.opus.is_loaded():
                discord.opus._load_default()
        except Exception as opus_err:
            logger.debug(f"Opus loader notice: {opus_err}")

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
        self.started_at = time.time()
        self.is_upgrading: bool = False

    async def get_guild_prefix(self, guild_id: int) -> str:
        """Fetch custom prefix for guild with in-memory caching."""
        if guild_id in self._prefix_cache:
            return self._prefix_cache[guild_id]
        try:
            settings = await self.db.get_guild_settings(guild_id)
            prefix = settings.prefix or config.MUSIC_PREFIX or "m!"
            self._prefix_cache[guild_id] = prefix
            return prefix
        except Exception:
            return config.MUSIC_PREFIX or "m!"

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
            embed.set_footer(text="MusicMaid • Continuous Playback Active")
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

        # 2. Add MusicCog & MusicSessionCog
        await self.add_cog(MusicCog(self))
        try:
            from music_bot.commands.session_cog import MusicSessionCog
            await self.add_cog(MusicSessionCog(self))
            logger.info("Loaded MusicSessionCog for Rythm-style persistent session memory.")
        except Exception as e:
            logger.error(f"Failed to load MusicSessionCog: {e}", exc_info=True)

        try:
            from music_bot.commands.sandbox_cog import SandboxCog
            await self.add_cog(SandboxCog(self))
            logger.info("Loaded SandboxCog for safe command testing and diagnostics.")
        except Exception as e:
            logger.error(f"Failed to load SandboxCog: {e}", exc_info=True)

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
                embed.set_footer(text="MusicMaid • Continuous Playback Active")
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

        # 2c. Optional Lavalink Node Initialization (Config-flagged)
        try:
            from music_bot.services.lavalink_service import LavalinkManager
            await LavalinkManager.setup_node(self)
        except Exception as lava_err:
            logger.warning(f"Lavalink initialization notice: {lava_err}")

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
        self.web_actions_loop.start()

        # 4b. Register Support Center persistent view & Live Status Panels
        try:
            from music_bot.services.ticket_service import SupportHubView
            self.add_view(SupportHubView())
            logger.info("Registered persistent SupportHubView for instant private tickets.")
        except Exception as hub_err:
            logger.warning(f"Could not register persistent SupportHubView: {hub_err}")

        try:
            from music_bot.services.status_panel_service import StatusPanelManager
            StatusPanelManager.start_loop(self)
            logger.info("Started autonomous StatusPanelManager loop for #server-status and #voice-status.")
        except Exception as panel_err:
            logger.warning(f"Could not start StatusPanelManager: {panel_err}")

        # 5. Start Web Platform (Raivora Music Web & Community OS)
        self.web_server = None
        try:
            import os
            from web.server import RaiCommunityOSServer
            web_port = int(os.environ.get("PORT", 8080))
            self.web_server = RaiCommunityOSServer(bot=self, db=self.db, port=web_port)
            await self.web_server.start()
            logger.info(f"✦ Raivora Music Web Platform online at http://0.0.0.0:{web_port}/music ✦")
        except Exception as e:
            logger.warning(f"Could not start Web Platform: {e}")

    @tasks.loop(seconds=5.0)
    async def snapshot_loop(self) -> None:
        """Continuously snapshots live track positions and handles gapless audio pre-caching."""
        try:
            from music_bot.services.player_service import MusicPlayerService
            from music_bot.services.session_memory_service import MusicSessionMemoryService
            await MusicPlayerService.snapshot_all_active_sessions(self)
            await MusicSessionMemoryService.checkpoint_all_active_sessions(self, reason="periodic")

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
            from music_bot.services.session_memory_service import MusicSessionMemoryService
            await MusicSessionMemoryService.cleanup_expired_sessions(self)
        except Exception as e:
            logger.debug(f"Music backup snapshot note: {e}")

    @maintenance_loop.before_loop
    async def before_maintenance(self) -> None:
        await self.wait_until_ready()

    async def on_resumed(self) -> None:
        """Handle Discord Gateway session resumption cleanly and resynchronize presence and voice state."""
        latency_ms = (self.latency * 1000.0) if self.latency is not None else 0.0
        logger.info(f"✦ [Gateway Resumed] Discord Gateway session successfully resumed (latency: {latency_ms:.1f}ms). ✦")
        try:
            from music_bot.services.presence_service import DynamicPresenceService
            await DynamicPresenceService.sync_presence(self, force=True)
        except Exception as pres_err:
            logger.debug(f"[Presence] Resumption presence sync notice: {pres_err}")

        # Audit active sessions to verify voice state synchronization
        try:
            for session in self.session_manager.get_all_sessions():
                vc = session.voice_client
                if vc and not vc.is_connected() and not getattr(session, "is_intentional_stop", False):
                    guild = self.get_guild(session.guild_id)
                    actual_vc = guild.voice_client if guild else None
                    if actual_vc and actual_vc.is_connected():
                        session.voice_client = actual_vc
                        logger.info(f"[Gateway Resumed] Resynchronized VoiceClient for guild {session.guild_id}.")
        except Exception as audit_err:
            logger.debug(f"[Gateway Resumed] Session audit notice: {audit_err}")

    async def on_disconnect(self) -> None:
        """Handle Discord Gateway disconnection notice without leaking sensitive data."""
        logger.warning("✦ [Gateway Disconnected] Lost connection to Discord Gateway. Reconnect loop active... ✦")

    async def on_error(self, event_method: str, *args: Any, **kwargs: Any) -> None:
        """Sanitized global event error handler redacting sensitive configuration."""
        import sys
        import re
        exc_type, exc_val, exc_tb = sys.exc_info()
        clean_err = str(exc_val or "Event error")
        clean_err = re.sub(r"[a-zA-Z0-9_\-]{24,}\.[a-zA-Z0-9_\-]{6}\.[a-zA-Z0-9_\-]{27,}", "[REDACTED_BOT_TOKEN]", clean_err)
        logger.error(f"[Gateway Event Error] Unhandled exception in '{event_method}': {clean_err}", exc_info=(exc_type, exc_val, exc_tb))

    async def on_ready(self) -> None:
        logger.info(
            f"🎵 {BOT_NAME} online as {self.user.name}#{self.user.discriminator} (ID: {self.user.id})"
        )
        logger.info(f"Serving {len(self.guilds)} guilds with independent audio architecture.")

        # Voice Protocol Runtime Diagnostics (Safe audit for Render logs)
        import sys
        from discord.voice_client import has_nacl
        has_dave = getattr(discord.voice_client, "has_dave", False)
        try:
            import davey
            d_ver = f"v{getattr(davey, '__version__', 'loaded')}"
        except ImportError:
            d_ver = "NOT INSTALLED"

        logger.info(
            f"✦ [Voice Runtime Audit] Python: {sys.version.split()[0]} | "
            f"discord.py: v{discord.__version__} | "
            f"DAVE E2EE: {'ACTIVE ✅' if has_dave else 'INACTIVE ❌'} ({d_ver}) | "
            f"PyNaCl: {'LOADED ✅' if has_nacl else 'MISSING ❌'} | "
            f"Opus: {'LOADED ✅' if discord.opus.is_loaded() else 'MISSING ❌'} ✦"
        )
        # Dynamic Discord Presence Synchronization & Watchdog (Phase 3)
        try:
            from music_bot.services.presence_service import DynamicPresenceService
            await DynamicPresenceService.sync_presence(self, force=True)
            DynamicPresenceService.start_watchdog(self)
        except Exception as pres_err:
            logger.warning(f"[Presence] Initial presence setup error: {pres_err}")

        # Public Bot Command Integrity: Commands are registered globally during setup_hook
        logger.info(f"✦ {BOT_NAME} ready across {len(self.guilds)} guilds. Global slash commands active. ✦")

        # Auto-discover Bot Application Creator / Developer from Discord API
        try:
            app_info = await self.application_info()
            if app_info.owner:
                config.register_bot_owner(app_info.owner.id)
                if self.db:
                    await self.db.set_premium(
                        app_info.owner.id,
                        entity_type="user",
                        is_premium=True,
                        tier="owner",
                        activated_by=app_info.owner.id,
                    )
                logger.info(f"👑 Verified Bot Creator & Application Owner: {app_info.owner} ({app_info.owner.id})")
            if app_info.team:
                for member in app_info.team.members:
                    config.register_bot_owner(member.id)
                    if self.db:
                        await self.db.set_premium(
                            member.id,
                            entity_type="user",
                            is_premium=True,
                            tier="owner",
                            activated_by=member.id,
                        )
                    logger.info(f"👑 Verified Bot Team Developer: {member.id}")
        except Exception as app_err:
            logger.warning(f"Could not auto-fetch application info: {app_err}")

        # Feature 109: Auto-Resume active music sessions across restarts
        if self.db:
            try:
                active_saved = await self.db.get_active_sessions()
                for saved in active_saved:
                    if saved.get("is_paused") or saved.get("state") in ("PAUSED", "IDLE"):
                        logger.info(f"Session in guild {saved.get('guild_id')} was paused/idle before restart; will not auto-play.")
                        continue
                    guild = self.get_guild(saved["guild_id"])
                    if not guild:
                        continue
                    vc_channel = guild.get_channel(saved.get("voice_channel_id") or 0)
                    text_channel = guild.get_channel(saved.get("text_channel_id") or 0)
                    if isinstance(vc_channel, (discord.VoiceChannel, discord.StageChannel)):
                        non_bot_listeners = [m for m in getattr(vc_channel, "members", []) if not m.bot]
                        if not non_bot_listeners:
                            logger.info(f"Voice channel #{vc_channel.name} in guild {guild.id} has no human listeners; will not auto-play on boot.")
                            continue
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
                                dur = track.duration or 0
                                if dur > 10 and start_pos >= dur - 5:
                                    if session.queue:
                                        next_t = session.queue.popleft()
                                        await MusicPlayerService.start_playback(self, session, next_t)
                                        logger.info(f"Auto-resumed next queued track '{next_t.title}' in guild {guild.id} (previous completed before restart).")
                                    else:
                                        session.reset()
                                        await self.db.delete_session(guild.id)
                                        logger.info(f"Saved session in guild {guild.id} had finished playback; cleaned up.")
                                elif start_pos and start_pos > 3:
                                    await MusicPlayerService.resume_track_stream(self, session, track, start_pos)
                                    logger.info(f"Auto-resumed playback in guild {guild.id} on #{vc_channel.name} at {start_pos}s (where it left off) with {len(session.queue)} in queue, {len(session.history)} in history")
                                else:
                                    await MusicPlayerService.start_playback(self, session, track)
                                    logger.info(f"Auto-resumed playback in guild {guild.id} on #{vc_channel.name} with {len(session.queue)} in queue, {len(session.history)} in history")
            except Exception as e:
                logger.warning(f"Session auto-resume error: {e}")

            # Auto-Join 24/7 Guild Voice Channels
            try:
                from music_bot.services.voice_service import VoiceManager
                twenty_four_seven_guilds = await self.db.get_all_247_guilds()
                for g_set in twenty_four_seven_guilds:
                    guild = self.get_guild(g_set.guild_id)
                    if not guild:
                        continue
                    session = await self.session_manager.get_session(guild.id)
                    session.twenty_four_seven = True
                    if not session.is_active:
                        target_vc_id = g_set.twenty_four_seven_channel_id
                        if not target_vc_id:
                            logger.info(f"[24/7 Startup] Guild '{guild.name}' ({guild.id}): 24/7 active in DB but no target channel configured. Waiting for user summon.")
                            continue

                        vc_channel = guild.get_channel(target_vc_id)
                        if not vc_channel:
                            try:
                                vc_channel = await guild.fetch_channel(target_vc_id)
                            except Exception:
                                vc_channel = None

                        if not vc_channel or not VoiceManager.is_valid_music_voice_channel(vc_channel):
                            logger.warning(
                                f"[24/7 Startup] Guild '{guild.name}' ({guild.id}): Saved 24/7 channel {target_vc_id} is unavailable or a stat/AFK channel. Waiting for user summon."
                            )
                            continue

                        try:
                            vc = await VoiceManager.join_voice_channel(
                                guild.me, session.text_channel, session, target_channel=vc_channel
                            )
                            if vc and vc.is_connected():
                                session.voice_client = vc
                                session.is_intentional_stop = False
                                logger.info(f"24/7 mode: Connected to #{vc_channel.name} in {guild.name}")
                        except Exception as vc_err:
                            logger.warning(f"Failed to 24/7 connect in guild {guild.id}: {vc_err}")
            except Exception as e:
                logger.warning(f"24/7 guilds recovery error: {e}")

            # Start autonomous 24/7 voice guardian background watchdog
            try:
                if hasattr(self, "twenty_four_seven_guardian_loop") and not self.twenty_four_seven_guardian_loop.is_running():
                    self.twenty_four_seven_guardian_loop.start()
            except Exception as loop_err:
                logger.warning(f"Failed to start 24/7 guardian loop: {loop_err}")

        # Phase 4: Startup Recovery Coordinator for Persistent Rythm-Style Sessions
        try:
            from music_bot.services.session_memory_service import MusicSessionMemoryService
            recovered_count = await MusicSessionMemoryService.startup_recovery_coordinator(self)
            if recovered_count > 0:
                logger.info(f"Startup recovery coordinator resurrected {recovered_count} persistent music session(s).")
        except Exception as e:
            logger.warning(f"Startup recovery coordinator note: {e}")

        # Initialize Autonomous Dependency & Extractor Updater
        try:
            from music_bot.services.updater_service import MusicAutoUpdater
            pass
        except Exception as e:
            logger.warning(f"Failed to start MusicAutoUpdater: {e}")

        # Automated Dedicated Bot Role Provisioning & Hierarchy Verification
        try:
            from music_bot.services.role_service import BotRoleService
            asyncio.create_task(BotRoleService.setup_all_guilds(self, self.db))
        except Exception as role_init_err:
            logger.warning(f"Failed to schedule automated bot role setup: {role_init_err}")

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Handle new guild additions with automatic role creation and permission diagnostics."""
        logger.info(f"✨ MusicMaid joined new guild: '{guild.name}' (ID: {guild.id}) with {guild.member_count} members.")
        try:
            from music_bot.services.role_service import BotRoleService
            await BotRoleService.setup_guild_role(guild, self.db)
        except Exception as role_err:
            logger.error(f"[RoleSetup] Error setting up role for joined guild {guild.id}: {role_err}")

    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """Monitor voice states for auto-leave behavior, 24/7 recovery, and stage ducking."""
        # Phase 7: Unexpected voice disconnect detection & backoff recovery
        if member.id == self.user.id and not after.channel and before.channel:
            session = await self.session_manager.get_session(member.guild.id)
            if not getattr(session, "is_intentional_disconnect", False):
                from music_bot.services.session_memory_service import MusicSessionMemoryService
                logger.warning(
                    f"[Voice] Involuntary voice disconnect for guild '{member.guild.name}' (ID: {member.guild.id}) "
                    f"from #{before.channel.name} ({before.channel.id}). Scheduling bounded recovery..."
                )
                asyncio.create_task(
                    MusicSessionMemoryService.handle_unexpected_disconnect(
                        self, member.guild.id, channel_id=before.channel.id
                    )
                )
            else:
                logger.info(
                    f"[Voice] Intentional user disconnect for guild '{member.guild.name}'; skipping recovery."
                )
            return

        if member.bot:
            return

        # Phase 4: Dynamic Temporary Voice Room Automation
        try:
            from music_bot.services.temp_voice_service import TempVoiceRoomManager
            asyncio.create_task(TempVoiceRoomManager.handle_voice_state_update(member, before, after))
        except Exception as e:
            logger.error(f"Error in TempVoiceRoomManager: {e}")

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
                    # Pre-check: if 24/7 is active in memory or DB, bypass auto-leave immediately
                    is_247 = getattr(session, "twenty_four_seven", False)
                    if not is_247 and self.db:
                        try:
                            g_set = await self.db.get_guild_settings(member.guild.id)
                            if g_set and g_set.twenty_four_seven_enabled:
                                is_247 = True
                                session.twenty_four_seven = True
                        except Exception:
                            pass
                    if not is_247:
                        from music_bot.services.voice_service import VoiceManager
                        VoiceManager.schedule_auto_leave(self, session)
                    else:
                        logger.info(
                            f"[Voice] [24/7 Guard] User left empty channel #{before.channel.name} in guild "
                            f"{member.guild.id}, but auto-leave is suppressed (24/7 active in DB/session)."
                        )

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

    @tasks.loop(seconds=0.75)
    async def web_actions_loop(self) -> None:
        """Poll and execute actions submitted from the Raivora Music Web dashboard."""
        if not self.db or not self.is_ready():
            return
        try:
            pending = await self.db.fetch_pending_web_actions(limit=5)
            for act in pending:
                action_id = act["id"]
                guild_id = act["guild_id"]
                action_type = act["action"]
                payload = act.get("payload", {})
                user_id = act.get("user_id", 0)

                session = await self.session_manager.get_session(guild_id)
                from music_bot.services.player_service import MusicPlayerService
                from music_bot.services.session_service import PlaybackState, LoopMode

                try:
                    if action_type == "PAUSE":
                        success, msg = await MusicPlayerService.pause(self, session)
                        await self.db.mark_web_action_completed(action_id, {"status": "paused" if success else "noop", "message": msg})

                    elif action_type == "RESUME":
                        success, msg = await MusicPlayerService.resume(self, session)
                        await self.db.mark_web_action_completed(action_id, {"status": "resumed" if success else "noop", "message": msg})

                    elif action_type == "SKIP":
                        success, msg, next_t = await MusicPlayerService.skip(self, session)
                        await self.db.mark_web_action_completed(action_id, {"status": "skipped", "message": msg})

                    elif action_type == "PREVIOUS":
                        success, msg, prev_t = await MusicPlayerService.previous(self, session)
                        await self.db.mark_web_action_completed(action_id, {"status": "previous", "message": msg})

                    elif action_type == "SEEK":
                        target_sec = int(payload.get("seconds", 0))
                        success = await MusicPlayerService.seek(self, session, target_sec)
                        await self.db.mark_web_action_completed(action_id, {"status": "seeked" if success else "failed", "position": target_sec})

                    elif action_type == "VOLUME":
                        vol = max(0, min(100, int(payload.get("volume", 80))))
                        session.volume = vol
                        if session.voice_client and hasattr(session.voice_client.source, "volume"):
                            session.voice_client.source.volume = vol / 100.0
                        await MusicPlayerService.send_now_playing_panel(session)
                        await self.db.mark_web_action_completed(action_id, {"status": "volume_set", "volume": vol})

                    elif action_type == "SHUFFLE":
                        MusicPlayerService.shuffle(session)
                        await MusicPlayerService.send_now_playing_panel(session)
                        await self.db.mark_web_action_completed(action_id, {"status": "shuffled", "queue_len": len(session.queue)})

                    elif action_type == "LOOP":
                        mode_str = payload.get("mode", "off").lower()
                        session.loop_mode = LoopMode(mode_str) if mode_str in ["off", "track", "queue"] else LoopMode.OFF
                        await MusicPlayerService.send_now_playing_panel(session)
                        await self.db.mark_web_action_completed(action_id, {"status": "loop_set", "loop_mode": session.loop_mode.value})

                    elif action_type == "FILTER":
                        preset_key = payload.get("preset", "flat").lower()
                        display_name = payload.get("name", preset_key.title())
                        success = await MusicPlayerService.apply_filter_or_eq(self, session, preset_key, display_name)
                        await self.db.mark_web_action_completed(action_id, {"status": "filter_applied" if success else "failed", "preset": preset_key})

                    elif action_type == "CONNECT_VOICE":
                        from music_bot.services.voice_service import VoiceManager
                        g_obj = self.get_guild(guild_id)
                        if g_obj:
                            target_ch = None
                            if user_id:
                                m = g_obj.get_member(user_id)
                                if m and m.voice and m.voice.channel:
                                    target_ch = m.voice.channel
                            if not target_ch:
                                for ch in g_obj.voice_channels:
                                    if any(not mb.bot for mb in ch.members) and VoiceManager.is_valid_music_voice_channel(ch):
                                        target_ch = ch
                                        break
                            if target_ch:
                                await VoiceManager.join_voice_channel(g_obj.me, session.text_channel, session, target_channel=target_ch)
                        await self.db.mark_web_action_completed(action_id, {"status": "connected"})

                    elif action_type == "ENQUEUE":
                        query = payload.get("query", "").strip()
                        title_hint = payload.get("title", "").strip() or None
                        artist_hint = payload.get("artist", "").strip() or None
                        if query:
                            from music_bot.services.resolver_service import AudioResolver
                            track = await AudioResolver.resolve_track(
                                query, user_id, "Web User", title_hint=title_hint, artist_hint=artist_hint
                            )
                            if track:
                                session.queue.append(track)
                                if not session.is_playing and not session.is_paused:
                                    await MusicPlayerService.start_playback(self, session, session.queue.popleft())
                                await self.db.mark_web_action_completed(action_id, {"status": "enqueued", "title": track.title})
                            else:
                                await self.db.mark_web_action_failed(action_id, "Could not resolve audio track")
                        else:
                            await self.db.mark_web_action_failed(action_id, "Empty query")

                    elif action_type == "PLAY_NOW":
                        query = payload.get("query", "").strip()
                        title_hint = payload.get("title", "").strip() or None
                        artist_hint = payload.get("artist", "").strip() or None
                        if query:
                            from music_bot.services.resolver_service import AudioResolver
                            track = await AudioResolver.resolve_track(
                                query, user_id, "Web User", title_hint=title_hint, artist_hint=artist_hint
                            )
                            if track:
                                if session.is_playing:
                                    session.queue.appendleft(track)
                                    await MusicPlayerService.skip(self, session)
                                else:
                                    if session.voice_client and session.voice_client.is_connected():
                                        await MusicPlayerService.start_playback(self, session, track)
                                    else:
                                        session.queue.appendleft(track)
                                await MusicPlayerService.send_now_playing_panel(session)
                                await self.db.mark_web_action_completed(action_id, {"status": "playing_now", "title": track.title})
                            else:
                                await self.db.mark_web_action_failed(action_id, "Could not resolve audio track")
                        else:
                            await self.db.mark_web_action_failed(action_id, "Empty query")

                    elif action_type == "PLAY_NEXT":
                        query = payload.get("query", "").strip()
                        title_hint = payload.get("title", "").strip() or None
                        artist_hint = payload.get("artist", "").strip() or None
                        if query:
                            from music_bot.services.resolver_service import AudioResolver
                            track = await AudioResolver.resolve_track(
                                query, user_id, "Web User", title_hint=title_hint, artist_hint=artist_hint
                            )
                            if track:
                                session.queue.appendleft(track)
                                await MusicPlayerService.send_now_playing_panel(session)
                                await self.db.mark_web_action_completed(action_id, {"status": "queued_next", "title": track.title})
                            else:
                                await self.db.mark_web_action_failed(action_id, "Could not resolve audio track")
                        else:
                            await self.db.mark_web_action_failed(action_id, "Empty query")

                    elif action_type == "REMOVE":
                        idx = int(payload.get("index", 0))
                        if 0 <= idx < len(session.queue):
                            removed = session.queue[idx]
                            del session.queue[idx]
                            await self.db.mark_web_action_completed(action_id, {"status": "removed", "title": removed.title})
                        else:
                            await self.db.mark_web_action_failed(action_id, "Index out of range")

                    elif action_type == "CLEAR":
                        session.queue.clear()
                        await self.db.mark_web_action_completed(action_id, {"status": "cleared"})

                    elif action_type == "STOP":
                        await MusicPlayerService.stop(self, session)
                        await self.db.mark_web_action_completed(action_id, {"status": "stopped"})

                    else:
                        await self.db.mark_web_action_failed(action_id, f"Unknown action: {action_type}")

                except Exception as act_err:
                    logger.warning(f"Failed to execute web action {action_id} ({action_type}): {act_err}")
                    await self.db.mark_web_action_failed(action_id, str(act_err))
        except Exception as poll_err:
            logger.debug(f"Web actions poll error: {poll_err}")

    @web_actions_loop.before_loop
    async def before_web_actions(self) -> None:
        await self.wait_until_ready()

    @tasks.loop(seconds=30.0)
    async def twenty_four_seven_guardian_loop(self) -> None:
        """
        Autonomous 24/7 Voice Guardian:
        Continuously ensures all guilds with 24/7 mode enabled remain connected to their target voice channel.
        Recovers from unexpected gateway drops, network blips, or Render restart cycles with bounded backoff.
        """
        if not self.is_ready() or not self.db:
            return

        try:
            twenty_four_seven_guilds = await self.db.get_all_247_guilds()
            active_gids = {g_set.guild_id for g_set in twenty_four_seven_guilds}
            from music_bot.database.models import MusicGuildSettings
            from music_bot.services.voice_service import VoiceManager

            for g in self.guilds:
                if g.id not in active_gids:
                    s = self.session_manager.get_session_sync(g.id)
                    if s and getattr(s, "twenty_four_seven", False) and getattr(s, "voice_channel_id", None):
                        twenty_four_seven_guilds.append(
                            MusicGuildSettings(
                                guild_id=g.id,
                                twenty_four_seven_enabled=True,
                                twenty_four_seven_channel_id=s.voice_channel_id,
                            )
                        )
                        active_gids.add(g.id)

            for g_set in twenty_four_seven_guilds:
                guild = self.get_guild(g_set.guild_id)
                if not guild:
                    continue

                session = await self.session_manager.get_session(guild.id)
                session.twenty_four_seven = True

                # Only skip if the user explicitly commanded the bot to leave the voice channel
                if getattr(session, "is_intentional_disconnect", False):
                    continue

                vc = guild.voice_client
                if vc and vc.is_connected() and getattr(vc, "channel", None):
                    # Guard: If bot was mistakenly placed into a server counter/stat/AFK channel, evict it immediately
                    if not VoiceManager.is_valid_music_voice_channel(vc.channel):
                        logger.warning(
                            f"[Voice] [24/7 Guardian] Bot detected in invalid/stat channel #{vc.channel.name} "
                            f"({vc.channel.id}) in guild {guild.id}. Evicting immediately."
                        )
                        await VoiceManager._purge_voice_client_state(guild)
                        session.voice_client = None
                    else:
                        session.voice_client = vc
                        continue
                target_vc_id = g_set.twenty_four_seven_channel_id
                if not target_vc_id:
                    # STRICT GUARD: Never guess or hop into arbitrary voice channels!
                    continue

                target_vc = guild.get_channel(target_vc_id)
                if not target_vc and target_vc_id:
                    try:
                        target_vc = await guild.fetch_channel(target_vc_id)
                    except Exception:
                        pass

                if not target_vc or not VoiceManager.is_valid_music_voice_channel(target_vc):
                    logger.debug(
                        f"[Voice] [24/7 Guardian] Guild {guild.id}: Target channel {target_vc_id} is unavailable "
                        f"or an invalid stat/AFK channel. Skipping auto-reconnect."
                    )
                    continue

                if guild.me:
                    perms = target_vc.permissions_for(guild.me)
                    if not perms.connect or not perms.speak:
                        logger.warning(
                            f"[Voice] [24/7 Guardian] Guild {guild.id}: Lacking Connect or Speak permissions "
                            f"in #{target_vc.name}. Skipping auto-reconnect."
                        )
                        continue

                logger.info(
                    f"[Voice] [24/7 Guardian] Reconnecting 24/7 voice client | Guild: {guild.id} | "
                    f"Saved 24/7 State: True | Channel: #{target_vc.name} ({target_vc.id}) | "
                    f"Voice Status: Disconnected | Disconnect Reason: Gateway drop / restart"
                )

                from music_bot.services.session_memory_service import MusicSessionMemoryService
                asyncio.create_task(
                    MusicSessionMemoryService.handle_unexpected_disconnect(
                        self,
                        guild.id,
                        channel_id=target_vc.id,
                    ),
                    name=f"GuardianRecoveryRequest-{guild.id}",
                )
        except Exception as loop_err:
            logger.debug(f"[Voice] [24/7 Guardian Loop Exception] {loop_err}")

    @twenty_four_seven_guardian_loop.before_loop
    async def before_twenty_four_seven_guardian(self) -> None:
        await self.wait_until_ready()

    async def close(self) -> None:
        """Gracefully release all resources, voice connections, and DB handles with state preservation."""
        logger.info(f"Initiating graceful shutdown for {BOT_NAME}...")
        self.heartbeat_loop.cancel()
        self.maintenance_loop.cancel()
        self.snapshot_loop.cancel()
        self.web_actions_loop.cancel()
        if hasattr(self, "twenty_four_seven_guardian_loop"):
            self.twenty_four_seven_guardian_loop.cancel()
        try:
            from music_bot.services.session_memory_service import MusicSessionMemoryService
            await MusicSessionMemoryService.cancel_recovery_tasks()
        except Exception as recovery_err:
            logger.warning(f"Voice recovery shutdown cleanup notice: {recovery_err}")

        if hasattr(self, "web_server") and self.web_server:
            try:
                await self.web_server.stop()
            except Exception:
                pass

        # Feature 109 & Phase 3: Save exact persistent playback positions & queues before shutdown
        try:
            from music_bot.services.player_service import MusicPlayerService
            from music_bot.services.session_memory_service import MusicSessionMemoryService
            await MusicPlayerService.snapshot_all_active_sessions(self)
            await MusicSessionMemoryService.checkpoint_all_active_sessions(self, reason="graceful_shutdown")
            logger.info("Saved all active music sessions & persistent checkpoints before shutdown.")
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
