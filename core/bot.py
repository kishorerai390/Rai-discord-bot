"""
Core SentinelBot Implementation with Strict Failure Isolation.
Orchestrates:
- Lifecycle management (startup, ready, resumed, graceful shutdown)
- Supervisor and Rate Limiter integration
- Transparent gateway response patching
- Isolated error boundaries between Security and Music
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from typing import List, Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from config import (
    BOT_PREFIX,
    COMMAND_SYNC_MODE,
    DISCORD_TOKEN,
    TEST_GUILD_ID,
    get_log_level,
    get_masked_token,
    is_token_valid,
)
from core.errors import generate_error_id
from core.supervisor import SystemSupervisor
from core.rate_limiter import GlobalRateLimiter
from core.health import HealthService
from core.tasks import BackgroundTaskManager
from database.database import Database
from database.migrations import run_migrations
from utils.cooldowns import CooldownManager
from utils.embeds import error_embed
from utils.interaction_reliability import (
    DuplicateInteractionGuard,
    InteractionResponseManager,
    PUBLIC_COMMANDS,
    safe_response,
)

logger = logging.getLogger("SentinelBot")

COGS_LIST: List[str] = [
    "cogs.security",
    "cogs.automod",
    "cogs.moderation",
    "cogs.welcome",
    "cogs.music",
    "cogs.soundboard",
    "cogs.tickets",
    "cogs.logging",
    "cogs.autorole",
    "cogs.utility",
    "cogs.suggestions",
    "cogs.raid",
    "cogs.voiceguard",
    "cogs.settings",
    "cogs.verification",
    "cogs.temp_voice",
    "cogs.autopilot",
    "cogs.serverstats",
    "cogs.reliability",
    "cogs.roles",
    "cogs.mention_notifications",
    "cogs.hidden_voice",
    "cogs.gaming",
    "cogs.creator",
    "cogs.movies",
    "cogs.events",
    "cogs.analytics",
    "cogs.ai_watchdog",
    "cogs.economy",
    "cogs.matchmaker",
    "cogs.ai_companion",
    "cogs.game_stats",
    "cogs.stream_radar",
    "cogs.ai_vision",
    "cogs.lyrics",
    "cogs.growth",
]


class SentinelBot(commands.Bot):
    """Production-grade All-in-One Discord Platform with Subsystem Isolation."""

    def __init__(self):
        # -------------------------------------------------------------
        # PRIVILEGED INTENTS AUDIT JUSTIFICATION:
        # 1. intents.members = True (REQUIRED):
        #    - Security Anti-Raid detection (join bursts, bot attacks)
        #    - Verification, AutoRole & Welcome gateways (member join triggers)
        #    - Dynamic VC ownership, co-host, and room DJ delegation checks
        #    - Dynamic Server Owner lookup (guild.owner_id resolution)
        # 2. intents.message_content = True (REQUIRED):
        #    - Security Anti-Spam & Mass Mention attack detection (<@USER_ID>)
        #    - Phishing, scam link & forbidden content filtering in AutoMod
        #    - Natural Language Owner Control (processing conversational instructions)
        # 3. intents.presences = False (INTENTIONALLY DISABLED):
        #    - Presences intent is NOT required by Rai security or music.
        #    - Preserves user privacy and cuts gateway event volume by >60%.
        # -------------------------------------------------------------
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.presences = False

        super().__init__(
            command_prefix=BOT_PREFIX,
            intents=intents,
            help_command=None,
        )

        self._start_time = time.time()
        self.db = Database(config.DATABASE_PATH)
        self.cooldowns = CooldownManager(self.db)
        self.rate_limiter = GlobalRateLimiter(max_concurrency=4)
        self.supervisor = SystemSupervisor(self)
        self.interaction_guard = DuplicateInteractionGuard(ttl_seconds=60.0)

        # Legacy and extended components
        from utils.security_brain import SecurityBrain
        from utils.keep_alive import KeepAliveServer
        from utils.autopilot import AutopilotEngine
        from utils.command_watchdog import CommandWatchdog
        from utils.action_queue import GlobalActionQueue
        from utils.self_healing import RaiSelfHealingEngine
        from utils.connection_watchdog import DiscordConnectionWatchdog
        from utils.role_manager import RoleManager

        self.security_brain = SecurityBrain(self)
        self.keep_alive = KeepAliveServer(bot=self)
        self.autopilot = AutopilotEngine(self)
        self.action_queue = GlobalActionQueue(self)
        self.watchdog = CommandWatchdog(self)
        self.self_healing = RaiSelfHealingEngine(self)
        self.conn_watchdog = DiscordConnectionWatchdog(self)
        self.role_manager = RoleManager(self)

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Global interaction entry point with duplicate protection."""
        if self.interaction_guard.is_duplicate(interaction.id):
            logger.debug(f"Duplicate interaction {interaction.id} dropped.")
            return

        if interaction.type == discord.InteractionType.component:
            cid = interaction.data.get("custom_id", "")
            if cid.startswith("inc_"):
                from utils.ai_incident_responder import handle_incident_interaction
                try:
                    handled = await handle_incident_interaction(self, interaction)
                    if handled:
                        return
                except Exception as e:
                    logger.error(f"Error handling incident interaction {cid}: {e}", exc_info=True)

    async def _tree_interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Global Slash Command Guard:
        1. Checks duplicates.
        2. Records start timing in CommandWatchdog.
        3. Acknowledges/defers interaction at gateway level within milliseconds.
        """
        if self.interaction_guard.is_duplicate(interaction.id):
            return False

        self.watchdog.record_start(interaction)

        if not interaction.response.is_done():
            cmd_name = interaction.command.name if interaction.command else ""
            is_ephemeral = cmd_name not in PUBLIC_COMMANDS
            try:
                await interaction.response.defer(ephemeral=is_ephemeral, thinking=True)
                self.watchdog.record_ack(interaction)
            except Exception as e:
                logger.debug(f"Immediate ACK note for {interaction.id}: {e}")

        return True

    async def setup_hook(self) -> None:
        """Sequential startup safety with subsystem isolation."""
        InteractionResponseManager.install_patches()

        # Pre-flight directory verification
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

        logger.info("Initializing database and storage engines...")
        try:
            await self.db.connect()
        except Exception as e:
            logger.critical(f"Database connect error during startup: {e}")

        # Start core background supervisors
        self.rate_limiter.start()
        self.supervisor.start()
        await self.keep_alive.start()

        self.cooldowns.start_cleanup_loop(interval_seconds=60)
        self.action_queue.start()
        self.watchdog.start()
        self.self_healing.start()
        self.conn_watchdog.start()

        # Restart Recovery: invalidate stale timers and reset stale voice sessions
        from services.timeout_manager import TimeoutManager
        from services.voice_session_service import VoiceSessionManager
        TimeoutManager.get_instance().invalidate_stale_timers()
        VoiceSessionManager.get_instance(self).cleanup_stale_sessions()

        # Load extension cogs with failure isolation (if Music fails, security loads fine)
        logger.info("Loading extension cogs...")
        for cog in COGS_LIST:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded extension: {cog}")
            except Exception as e:
                logger.error(f"Failed to load extension {cog}: {e}", exc_info=True)
                # If a non-essential cog fails, record degraded status in supervisor
                if "music" in cog:
                    self.supervisor.subsystems["Music"].record_failure(f"Extension load failed: {e}")

        # Register all active background loops with central BackgroundTaskManager
        task_mgr = BackgroundTaskManager.get_instance()
        for cog_name, cog in self.cogs.items():
            for attr_name in dir(cog):
                try:
                    attr = getattr(cog, attr_name, None)
                    if isinstance(attr, tasks.Loop):
                        task_mgr.register_loop(attr)
                except Exception:
                    pass

        self.autopilot.start()
        self.tree.interaction_check = self._tree_interaction_check
        self.tree.on_error = self.on_app_command_error

        # Synchronize slash commands
        logger.info(f"Synchronizing slash commands (mode: {COMMAND_SYNC_MODE})...")
        try:
            if COMMAND_SYNC_MODE == "guild" and TEST_GUILD_ID:
                guild_obj = discord.Object(id=TEST_GUILD_ID)
                self.tree.copy_global_to(guild=guild_obj)
                synced = await self.tree.sync(guild=guild_obj)
                logger.info(f"Commands synced to test guild: {len(synced)}")
            else:
                synced = await self.tree.sync()
                logger.info(f"Commands synchronized globally: {len(synced)}")
        except Exception as e:
            logger.error(f"Command synchronization note: {e}")

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Global error handler for slash commands with diagnostic Error IDs."""
        error_id = generate_error_id()
        cmd_name = interaction.command.name if interaction.command else "unknown"

        if isinstance(error, app_commands.CommandOnCooldown):
            msg = f"⏳ This command is on cooldown. Try again in `{round(error.retry_after, 1)}s`."
            await safe_response(interaction, content=msg, ephemeral=True)
            self.watchdog.record_end(interaction, status="COOLDOWN")
            return

        elif isinstance(error, app_commands.MissingPermissions):
            missing = ", ".join(f"`{p}`" for p in error.missing_permissions)
            embed = error_embed("Missing Permissions", f"You need the following permissions:\n{missing}")
            self.watchdog.record_end(interaction, status="FORBIDDEN")
        elif isinstance(error, app_commands.BotMissingPermissions):
            missing = ", ".join(f"`{p}`" for p in error.missing_permissions)
            embed = error_embed("Bot Missing Permissions", f"Bot requires:\n{missing}")
            self.watchdog.record_end(interaction, status="FORBIDDEN")
        elif isinstance(error, app_commands.CheckFailure):
            embed = error_embed(
                "Access Denied",
                "⛔ **Major Permission Access Restricted**\n\n"
                "This administrative command is restricted exclusively to the **Server Founder** (`rf.rai_006`).",
            )
            self.watchdog.record_end(interaction, status="CHECK_FAILURE")
        else:
            logger.error(f"[{error_id}] Unhandled app command error in /{cmd_name}: {error}", exc_info=True)
            embed = error_embed(
                "Request Failed",
                f"⚠️ Rai encountered an operational note while processing `/{cmd_name}`.\n\n"
                f"**Diagnostic ID:** `{error_id}`\n"
                f"*Security subsystems remain fully active.*",
            )
            await self.self_healing.handle_component_error("command_pipeline", error, error_id)
            self.watchdog.record_end(interaction, status="FAILED", error_id=error_id)

        await safe_response(interaction, embed=embed, ephemeral=True)

    async def on_app_command_completion(
        self, interaction: discord.Interaction, command: app_commands.Command
    ) -> None:
        self.watchdog.record_end(interaction, status="SUCCESS")

    async def on_resumed(self) -> None:
        self.conn_watchdog.record_reconnect()
        self.conn_watchdog.record_resume()
        self.supervisor.subsystems["Gateway"].record_healthy({"resumed": True})

    async def on_disconnect(self) -> None:
        self.conn_watchdog.record_disconnect("Gateway socket disconnect")
        self.supervisor.subsystems["Gateway"].record_degraded("Gateway socket disconnected")

    async def on_ready(self) -> None:
        self.conn_watchdog.record_identify()
        logger.info("=" * 45)
        logger.info(f"Rai Bot online as: {self.user} (ID: {self.user.id})")
        logger.info(f"Connected Guilds: {len(self.guilds)}")
        logger.info("=" * 45)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="over your server | /help",
            )
        )
        try:
            from utils.owner_reporter import OwnerReporter
            for guild in self.guilds:
                # Do NOT broadcast startup announcements to servers unless explicitly permitted by the server owner
                cfg = None
                if hasattr(self, "db") and self.db:
                    try:
                        cfg = await self.db.get_owner_reports_config(guild.id)
                    except Exception:
                        cfg = None

                if not cfg or not getattr(cfg, "startup_reports_enabled", False):
                    continue

                cmd_count = len(self.tree.get_commands())
                OwnerReporter.send_system_report(
                    self,
                    guild.id,
                    event="Bot Core Online & Synchronized",
                    component="Gateway & Command Registry",
                    status="HEALTHY",
                    details={
                        "Identity": f"{self.user} (`{self.user.id}`)",
                        "Commands": f"`{cmd_count}` Registered",
                        "Heartbeat Ping": f"`{int(self.latency * 1000)}ms`",
                    },
                )
        except Exception as e:
            logger.warning(f"Could not dispatch startup telemetry: {e}")

    async def close(self) -> None:
        """Graceful shutdown preserving state without corrupting persistent data."""
        logger.info("Initiating graceful shutdown for Rai Bot...")
        self.supervisor.stop()
        self.rate_limiter.stop()
        self.autopilot.stop()
        self.action_queue.stop()
        self.watchdog.stop()
        self.self_healing.stop()
        self.conn_watchdog.stop()

        # Disconnect all voice clients cleanly
        for vc in self.voice_clients:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass

        await self.keep_alive.stop()
        self.cooldowns.stop_cleanup_loop()
        await self.db.close()
        await super().close()
        logger.info("Rai Bot shutdown complete.")
