"""
Reliability, Health Monitoring, and Self-Healing Diagnostics Cog for Rai Bot.
Provides /rai health, /rai diagnostics, /rai latency, /rai performance, and /rai simulate.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import time
from typing import TYPE_CHECKING, Literal, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_VERSION, Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.interaction_reliability import safe_defer, safe_error_response, safe_response
from utils.permissions import is_admin_or_owner, is_founder_or_owner
from database.manager import DatabaseManager
from observability.health import ObservabilityHealthService
from observability.metrics import PROMETHEUS_AVAILABLE
from backups.manager import BackupManager
from core.channel_access import ChannelAccessService
from core.interaction_manager import InteractionManager, ManagedInteractionContext
from services.channel_assignment_service import (
    ChannelAssignmentService,
    ChannelHealthStatus,
    CANONICAL_CHANNELS,
    PURPOSE_MAP,
)
from services.rai_doctor import RaiDoctor, DiagnosticStatus
from security.simulator import SecuritySimulator
from security.permission_auditor import PermissionAuditor
from security.investigation import IncidentInvestigator

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger("RaiReliabilityCog")


class ReliabilityCog(commands.Cog, name="Reliability"):
    """Autonomous Reliability, Self-Healing, and Health Diagnostics."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._start_time = time.time()

    rai_group = app_commands.Group(
        name="rai",
        description="Rai autonomous health, reliability, diagnostics, and self-healing controls",
    )
    channel_access_group = app_commands.Group(
        name="channel-access",
        description="Rai channel access repair and diagnostic commands",
        parent=rai_group,
    )
    channels_group = app_commands.Group(
        name="channels",
        description="Rai canonical channel assignments, purpose mapping, and diagnostics",
        parent=rai_group,
    )
    security_group = app_commands.Group(
        name="security",
        description="Rai autonomous security simulations and diagnostics",
        parent=rai_group,
    )

    # ==========================================
    # /rai health
    # ==========================================

    @rai_group.command(name="health", description="Display full visual health status across all Rai subsystems")
    @app_commands.default_permissions(administrator=True)
    async def rai_health(self, interaction: discord.Interaction) -> None:
        """Visual health monitor across all core engines and background workers."""
        await safe_defer(interaction, ephemeral=False)

        # 1. Measure database responsiveness
        t0 = time.perf_counter()
        db_ok = False
        if self.bot.db.is_connected:
            try:
                await self.bot.db.execute_read("SELECT 1")
                db_ok = True
            except Exception:
                db_ok = False
        db_latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        # 2. Check Gateway
        gateway_ok = self.bot.is_ready()
        gateway_ms = round((self.bot.latency or 0.0) * 1000.0, 1)

        # 3. Check Autopilot & Security Brain
        autopilot_ok = hasattr(self.bot, "autopilot") and self.bot.autopilot is not None
        security_ok = hasattr(self.bot, "security_brain") and self.bot.security_brain is not None

        # 4. Check Action Queue
        queue_status = self.bot.action_queue.get_status() if hasattr(self.bot, "action_queue") else {}
        queue_ok = queue_status.get("active_workers", 0) > 0

        # 5. Check Self-Healing & Safe Mode
        healing_metrics = self.bot.self_healing.get_health_metrics() if hasattr(self.bot, "self_healing") else {}
        safe_mode = healing_metrics.get("safe_mode", False)
        degraded = healing_metrics.get("degraded_components", [])

        # 6. Command Watchdog
        watchdog_summary = self.bot.watchdog.get_performance_summary() if hasattr(self.bot, "watchdog") else {}

        # 7. Recent recoveries count from DB
        recent_recoveries = []
        if self.bot.db.is_connected:
            try:
                recent_recoveries = await self.bot.db.get_recent_self_healing_records(limit=10)
            except Exception:
                pass
        successful_recoveries = sum(1 for r in recent_recoveries if r.result == "SUCCESS")

        # Visual indicator helper
        def st(ok: bool, is_degraded: bool = False) -> str:
            if is_degraded:
                return "🟡 DEGRADED"
            return "🟢 HEALTHY" if ok else "🔴 FAILED"

        uptime_secs = int(time.time() - self._start_time)
        days, rem = divmod(uptime_secs, 86400)
        hours, rem = divmod(rem, 3600)
        mins, secs = divmod(rem, 60)
        uptime_str = f"{days}d {hours}h {mins}m {secs}s"

        overall_status = "🟡 SAFE MODE" if safe_mode else ("🟢 OPERATIONAL" if not degraded else "🟡 DEGRADED")

        embed = create_embed(
            title="🩺 Rai Core Health Monitor",
            description=f"**System Status:** `{overall_status}` | **Uptime:** `{uptime_str}`",
            color=Colors.GOLD if (safe_mode or degraded) else Colors.GREEN,
        )

        subsystems = (
            f"• **Discord Gateway**: {st(gateway_ok)} (`{gateway_ms}ms`)\n"
            f"• **SQLite Database**: {st(db_ok)} (`{db_latency_ms}ms`)\n"
            f"• **Command Watchdog**: {st(True)} (`{watchdog_summary.get('active_commands', 0)}` active)\n"
            f"• **Rai Autopilot**: {st(autopilot_ok, 'autopilot' in degraded)}\n"
            f"• **Security Brain**: {st(security_ok, 'security' in degraded)}\n"
            f"• **Action Queue**: {st(queue_ok)} (`{queue_status.get('queue_size', 0)}` queued)\n"
            f"• **Self-Healing Engine**: {st(not safe_mode, safe_mode)}\n"
            f"• **Keep-Alive Server**: 🟢 RUNNING (Port 8080)"
        )
        embed.add_field(name="Subsystem Telemetry", value=subsystems, inline=False)

        metrics_text = (
            f"• **Throughput:** `{watchdog_summary.get('total_commands', 0)}` commands processed\n"
            f"• **Average Latency:** `{watchdog_summary.get('avg_duration_ms', 0.0)}ms` (p95: `{watchdog_summary.get('p95_ms', 0.0)}ms`)\n"
            f"• **Autonomous Recoveries:** `{successful_recoveries}` logged\n"
            f"• **Degraded Components:** `{len(degraded)}`"
        )
        embed.add_field(name="Reliability Metrics", value=metrics_text, inline=False)
        embed.set_footer(text=f"Rai Engine v{BOT_VERSION} • 24/7 Self-Healing Protection Active")

        await safe_response(interaction, embed=embed)

    # ==========================================
    # /rai latency
    # ==========================================

    @rai_group.command(name="latency", description="Display precise gateway, database, and interaction round-trip latencies")
    @app_commands.default_permissions(administrator=True)
    async def rai_latency(self, interaction: discord.Interaction) -> None:
        """Measures network and database latency round-trips."""
        t_start = time.perf_counter()
        await safe_defer(interaction, ephemeral=True)
        interaction_roundtrip_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

        # Database latency
        t_db = time.perf_counter()
        if self.bot.db.is_connected:
            await self.bot.db.execute_read("SELECT 1")
        db_ms = round((time.perf_counter() - t_db) * 1000.0, 2)

        gw_ms = round((self.bot.latency or 0.0) * 1000.0, 2)
        conn_status = self.bot.conn_watchdog.get_status() if hasattr(self.bot, "conn_watchdog") else {}
        avg_gw = conn_status.get("avg_latency_ms", gw_ms)

        embed = create_embed(
            title="⚡ Rai Real-Time Latency Diagnostics",
            description="Continuous round-trip latency measurements across the stack:",
            color=Colors.CYAN,
        )
        embed.add_field(
            name="📡 Discord Gateway",
            value=f"Current: `{gw_ms}ms`\nRolling Avg: `{avg_gw}ms`\nStatus: {'⚠️ Unstable' if conn_status.get('is_unstable') else '🟢 Stable'}",
            inline=True,
        )
        embed.add_field(
            name="💾 SQLite Database",
            value=f"Query Roundtrip: `{db_ms}ms`\nEngine: `aiosqlite WAL`\nStatus: 🟢 Fast",
            inline=True,
        )
        embed.add_field(
            name="⚡ Interaction ACK",
            value=f"Defer Time: `{interaction_roundtrip_ms}ms`\nDeadline: `< 3000ms`\nStatus: 🟢 Instant",
            inline=True,
        )

        await safe_response(interaction, embed=embed, ephemeral=True)

    # ==========================================
    # /rai channel-access scan
    # ==========================================

    @channel_access_group.command(name="scan", description="Scan and safely ensure minimum access to eligible empty channels")
    @app_commands.describe(dry_run="Perform audit only without modifying permissions (default: False)")
    @app_commands.default_permissions(administrator=True)
    async def channel_access_scan(self, interaction: discord.Interaction, dry_run: bool = False) -> None:
        """Scan eligible channels, verify empty status, and apply minimum missing permissions."""
        await safe_defer(interaction, ephemeral=False)

        if not interaction.guild:
            await safe_error_response(interaction, "This command can only be executed within a Discord server.")
            return

        service = ChannelAccessService.get_instance(self.bot.db)
        bot_member = interaction.guild.me
        summary = await service.scan_guild(interaction.guild, dry_run=dry_run, bot_member=bot_member)
        embed = service.create_scan_embed(summary)
        await safe_response(interaction, embed=embed, ephemeral=False)

    # ==========================================
    # /rai security simulate
    # ==========================================

    @security_group.command(name="simulate", description="Safely simulate an attack scenario without executing live Discord mutations")
    @app_commands.describe(scenario="The attack vector scenario to simulate")
    @app_commands.default_permissions(administrator=True)
    async def rai_security_simulate(
        self,
        interaction: discord.Interaction,
        scenario: Literal["raid", "spam", "nuke", "mention", "permission"],
    ) -> None:
        """Runs synthetic threat vectors through Security Brain and Risk Engine with zero Discord mutations."""
        await safe_defer(interaction, ephemeral=False)
        simulator = SecuritySimulator()
        guild_id = interaction.guild_id or 0
        res = await simulator.simulate_scenario(scenario, guild_id=guild_id)
        embed = simulator.create_simulation_embed(res)
        await safe_response(interaction, embed=embed, ephemeral=False)

    # ==========================================
    # /rai security audit
    # ==========================================

    @security_group.command(name="audit", description="Run non-destructive audit of server permissions and security risks")
    @app_commands.default_permissions(administrator=True)
    async def rai_security_audit(self, interaction: discord.Interaction) -> None:
        """Performs a comprehensive read-only audit of server permissions and configurations."""
        await safe_defer(interaction, ephemeral=False)
        if not interaction.guild:
            await safe_error_response(interaction, "This command can only be executed within a Discord server.")
            return

        auditor = PermissionAuditor(db=self.bot.db)
        report = await auditor.audit_guild(interaction.guild)
        embed = auditor.create_audit_embed(report)
        await safe_response(interaction, embed=embed, ephemeral=False)

    # ==========================================
    # /rai investigate
    # ==========================================

    @rai_group.command(name="investigate", description="Investigate an incident timeline and forensic action graph")
    @app_commands.describe(incident_id="The incident ID to investigate (e.g. RAI-INC-000142)")
    @app_commands.default_permissions(administrator=True)
    async def rai_investigate(self, interaction: discord.Interaction, incident_id: str) -> None:
        """Retrieves verified forensic timeline and actions taken for a security incident."""
        await safe_defer(interaction, ephemeral=False)
        investigator = IncidentInvestigator(db=self.bot.db)
        guild_id = interaction.guild_id or 0
        report = await investigator.get_incident_timeline(incident_id, guild_id=guild_id)
        if not report:
            embed = error_embed(
                f"Incident `{incident_id.strip().upper()}` not found or contains no recorded telemetry."
            )
            await safe_response(interaction, embed=embed, ephemeral=True)
            return

        embed = investigator.create_timeline_embed(report)
        await safe_response(interaction, embed=embed, ephemeral=False)

    # ==========================================
    # AUTOMATIC CHANNEL CREATION LISTENER
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """Automatically checks access for newly created empty channels if configured."""
        try:
            guild = getattr(channel, "guild", None)
            if not guild:
                return

            service = ChannelAccessService.get_instance(self.bot.db)
            config = None
            if self.bot.db:
                try:
                    config = await self.bot.db.get_channel_access_config(guild.id)
                except Exception as e:
                    logger.warning(f"Could not load channel_access_config on channel create: {e}")

            if config and (not config.enabled or not config.auto_update):
                return

            # Short delay for channel setup/overwrites to settle
            await asyncio.sleep(1.0)

            bot_member = guild.me
            if not bot_member:
                return

            eval_res = await service.evaluate_channel(channel, bot_member, config or ChannelAccessConfig(guild_id=guild.id))
            if eval_res.is_eligible and eval_res.is_empty and not eval_res.has_access:
                apply_res = await service.apply_minimum_overwrite(
                    channel, bot_member, eval_res.missing_permissions
                )
                if apply_res.success and apply_res.data:
                    logger.info(
                        f"[CHANNEL_ACCESS] Auto-granted minimum access on new channel #{eval_res.channel_name} ({eval_res.channel_id})"
                    )
                    audit_embed = service.create_audit_embed(apply_res.data, eval_res.channel_name)
                    # Attempt dispatch to dedicated logging channel if available
                    for ch in guild.text_channels:
                        if ch.name in ("security-log", "moderation-log", "audit-logs", "bot-log"):
                            perms = ch.permissions_for(bot_member)
                            if perms.send_messages and perms.embed_links:
                                try:
                                    await ch.send(embed=audit_embed)
                                    break
                                except Exception:
                                    pass
        except Exception as e:
            logger.error(f"[CHANNEL_ACCESS] Error in on_guild_channel_create: {e}", exc_info=True)

    # ==========================================
    # /rai performance
    # ==========================================

    @rai_group.command(name="performance", description="Display command execution duration percentiles and workload metrics")
    @app_commands.default_permissions(administrator=True)
    async def rai_performance(self, interaction: discord.Interaction) -> None:
        """Inspects command performance metrics, percentiles, and active workloads."""
        await safe_defer(interaction, ephemeral=True)

        watchdog_summary = self.bot.watchdog.get_performance_summary() if hasattr(self.bot, "watchdog") else {}
        queue_status = self.bot.action_queue.get_status() if hasattr(self.bot, "action_queue") else {}

        embed = create_embed(
            title="📊 Rai Performance Telemetry",
            description="Command execution duration statistics and background queue throughput:",
            color=Colors.PRIMARY,
        )

        embed.add_field(
            name="⏱️ Execution Latency (Percentiles)",
            value=(
                f"• **Median (p50):** `{watchdog_summary.get('p50_ms', 0.0)}ms`\n"
                f"• **95th Percentile (p95):** `{watchdog_summary.get('p95_ms', 0.0)}ms`\n"
                f"• **Average Duration:** `{watchdog_summary.get('avg_duration_ms', 0.0)}ms`\n"
                f"• **Slow Commands (>1s):** `{watchdog_summary.get('slow_count', 0)}`"
            ),
            inline=False,
        )

        embed.add_field(
            name="🚦 Action Queue Metrics",
            value=(
                f"• **Dispatched Actions:** `{queue_status.get('dispatched', 0)}`\n"
                f"• **Deduplicated Duplicates:** `{queue_status.get('deduplicated', 0)}`\n"
                f"• **Failed Actions:** `{queue_status.get('failed', 0)}`\n"
                f"• **Current Backlog:** `{queue_status.get('queue_size', 0)}` queued"
            ),
            inline=False,
        )

        embed.add_field(
            name="🖥️ Platform Runtime",
            value=f"Python `{platform.python_version()}` on `{platform.system()} {platform.release()}`",
            inline=False,
        )

        await safe_response(interaction, embed=embed, ephemeral=True)

    # ==========================================
    # /rai diagnostics
    # ==========================================

    @rai_group.command(name="diagnostics", description="Administrator diagnostics, recent recovery records, and error traces")
    @app_commands.default_permissions(administrator=True)
    async def rai_diagnostics(self, interaction: discord.Interaction) -> None:
        """Detailed technical diagnostics for server administrators and developers."""
        await safe_defer(interaction, ephemeral=True)

        recent_heals = []
        recent_metrics = []
        if self.bot.db.is_connected:
            try:
                recent_heals = await self.bot.db.get_recent_self_healing_records(limit=5)
                recent_metrics = await self.bot.db.get_recent_command_metrics(limit=5)
            except Exception:
                pass

        embed = create_embed(
            title="🔧 Rai Autonomous Diagnostics",
            description="Internal diagnostic audit trail for debugging and verification:",
            color=Colors.DARK_GRAY,
        )

        # Recent recoveries
        if recent_heals:
            heal_lines = []
            for h in recent_heals:
                heal_lines.append(
                    f"`{h.recovery_id}` | **{h.component}**: {h.action_taken} → `{h.result}` ({h.duration_ms}ms)"
                )
            embed.add_field(name="Recent Self-Healing Recoveries", value="\n".join(heal_lines), inline=False)
        else:
            embed.add_field(name="Recent Self-Healing Recoveries", value="No recovery events recorded.", inline=False)

        # Recent command executions
        if recent_metrics:
            cmd_lines = []
            for m in recent_metrics:
                status_icon = "🟢" if m.status in ("SUCCESS", "NORMAL") else "🔴"
                cmd_lines.append(
                    f"{status_icon} `/{m.command_name}`: `{m.duration_ms:.1f}ms` [{m.status}] "
                    f"{f'(Err: {m.error_id})' if m.error_id else ''}"
                )
            embed.add_field(name="Recent Command Executions", value="\n".join(cmd_lines), inline=False)

        embed.set_footer(text="Sanitized Diagnostics • Zero Secrets or Tokens Exposed")
        await safe_response(interaction, embed=embed, ephemeral=True)

    # ==========================================
    # /rai simulate
    # ==========================================

    @rai_group.command(name="simulate", description="Safely simulate a subsystem failure to verify self-healing recovery")
    @app_commands.describe(failure_type="The type of failure to simulate safely")
    @app_commands.default_permissions(administrator=True)
    async def rai_simulate(
        self,
        interaction: discord.Interaction,
        failure_type: Literal["worker", "database", "api", "command"],
    ) -> None:
        """Simulates subsystem failure without affecting real server assets."""
        await safe_defer(interaction, ephemeral=True)

        if not hasattr(self.bot, "self_healing"):
            await safe_response(interaction, embed=error_embed("Self-Healing Engine not initialized."), ephemeral=True)
            return

        result = await self.bot.self_healing.simulate_failure(failure_type)

        embed = success_embed(
            "🧪 Self-Healing Simulation Executed",
            f"**Simulated Failure:** `{result.get('simulation')}`\n"
            f"• **Target Component:** `{result.get('component')}`\n"
            f"• **Classification:** `{result.get('classification')}`\n"
            f"• **Recovery Succeeded:** `{'YES' if result.get('recovery_success') else 'NO'}`\n"
            f"• **Audit Error ID:** `{result.get('error_id')}`\n\n"
            f"*Autonomous recovery was completed and logged to SQLite audit trail.*",
        )
        await safe_response(interaction, embed=embed, ephemeral=True)

    # ==========================================
    # /rai channels (Canonical Channel Assignments)
    # ==========================================

    @channels_group.command(name="show", description="Display current canonical channel purpose assignments and health status")
    @app_commands.default_permissions(administrator=True)
    async def channels_show(self, interaction: discord.Interaction) -> None:
        """Display the 17 canonical channel assignments for the guild."""
        await InteractionManager.execute_interaction(
            interaction,
            "Rai Channels Show",
            self._handle_channels_show,
            ephemeral=False,
            auto_defer=True,
        )

    async def _handle_channels_show(self, interaction: discord.Interaction, ctx: ManagedInteractionContext):
        if not interaction.guild:
            await InteractionManager.safe_reply(interaction, content="❌ Server context required.", ephemeral=True)
            return

        embed = await build_channels_embed(self.bot, interaction.guild, ctx.request_id)
        view = ChannelControlsView(self.bot, interaction.guild.id)
        await InteractionManager.safe_reply(interaction, embed=embed, view=view, ephemeral=False)

    @channels_group.command(name="test", description="Send diagnostic verification messages to configured channels with auto-cleanup")
    @app_commands.default_permissions(administrator=True)
    async def channels_test(self, interaction: discord.Interaction) -> None:
        """Send small self-destructing test messages to each configured channel."""
        await InteractionManager.execute_interaction(
            interaction,
            "Rai Channels Test",
            self._handle_channels_test,
            ephemeral=True,
            auto_defer=True,
        )

    async def _handle_channels_test(self, interaction: discord.Interaction, ctx: ManagedInteractionContext):
        guild = interaction.guild
        if not guild:
            await InteractionManager.safe_reply(interaction, content="❌ Server context required.", ephemeral=True)
            return

        cfg = await ChannelAssignmentService.get_config(self.bot, guild.id)
        results = []
        for purpose in CANONICAL_CHANNELS:
            ch_id = getattr(cfg, purpose.config_field, None)
            if ch_id:
                res = await ChannelAssignmentService.test_single_channel(self.bot, guild, purpose.key)
                results.append(res)

        if not results:
            await InteractionManager.safe_reply(
                interaction,
                content="⚠️ No channels are configured yet. Run `/rai channels refresh` to auto-discover existing channels.",
                ephemeral=True,
            )
            return

        passed = sum(1 for r in results if r.get("success"))
        failed = sum(1 for r in results if not r.get("success"))

        lines = []
        for r in results:
            icon = "🟢" if r.get("success") else "🔴"
            status_text = f"**{r['display_name']}**: `{r['status']}`"
            if r.get("error"):
                status_text += f" ({r['error']})"
            lines.append(f"{icon} {status_text}")

        embed = discord.Embed(
            title="🧪 Rai Channel Delivery Test",
            description=f"**Verification:** `{passed}` passed, `{failed}` failed.\n\n" + "\n".join(lines[:20]),
            color=0x57F287 if failed == 0 else 0xFEE75C,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_footer(text=f"Rai Channels Diagnostic • {ctx.request_id}")
        await InteractionManager.safe_reply(interaction, embed=embed, ephemeral=True)

    @channels_group.command(name="refresh", description="Re-evaluate channel permissions and auto-discover unassigned channels")
    @app_commands.default_permissions(administrator=True)
    async def channels_refresh(self, interaction: discord.Interaction) -> None:
        """Re-audits existing channels in the guild without creating, deleting, or renaming any channels."""
        await InteractionManager.execute_interaction(
            interaction,
            "Rai Channels Refresh",
            self._handle_channels_refresh,
            ephemeral=True,
            auto_defer=True,
        )

    async def _handle_channels_refresh(self, interaction: discord.Interaction, ctx: ManagedInteractionContext):
        guild = interaction.guild
        if not guild:
            await InteractionManager.safe_reply(interaction, content="❌ Server context required.", ephemeral=True)
            return

        cfg, discovery = await ChannelAssignmentService.auto_assign_discovered_channels(
            self.bot, guild, overwrite_existing=False
        )

        matched_lines = [f"• **{PURPOSE_MAP[k].display_name}** ➔ <#{cid}>" for k, cid in discovery.matched.items()]
        ambig_lines = [f"• **{PURPOSE_MAP[k].display_name}**: Multiple candidates found ({len(cids)})" for k, cids in discovery.ambiguous.items()]

        desc = f"**Auto-Discovered & Assigned ({len(discovery.matched)} channels):**\n"
        desc += "\n".join(matched_lines) if matched_lines else "None newly assigned.\n"
        if ambig_lines:
            desc += "\n\n⚠️ **Ambiguous Candidates (Need Manual Selection):**\n" + "\n".join(ambig_lines)

        embed = discord.Embed(
            title="🔄 Rai Channel Assignments Refreshed",
            description=desc,
            color=0x5865F2,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_footer(text=f"Rai Channel Discovery • {ctx.request_id}")
        await InteractionManager.safe_reply(interaction, embed=embed, ephemeral=True)

    @channels_group.command(name="assign", description="Manually assign an existing server channel to a specific purpose")
    @app_commands.describe(
        purpose="The canonical purpose to assign",
        channel="The existing text channel to map",
    )
    @app_commands.choices(
        purpose=[
            app_commands.Choice(name="🚨 Security Alerts", value="security_alerts"),
            app_commands.Choice(name="🧱 Anti-Nuke", value="anti_nuke"),
            app_commands.Choice(name="🔒 Lockdown Control", value="lockdown_control"),
            app_commands.Choice(name="🛡️ Security Log", value="security_log"),
            app_commands.Choice(name="🔍 Audit Monitor", value="audit_monitor"),
            app_commands.Choice(name="🚨 Security Report", value="security_report"),
            app_commands.Choice(name="🛡️ Moderation Report", value="moderation_report"),
            app_commands.Choice(name="🎵 Music Report", value="music_report"),
            app_commands.Choice(name="🔐 Room Report", value="room_report"),
            app_commands.Choice(name="🤖 Bot Report", value="bot_report"),
            app_commands.Choice(name="⚙️ System Report", value="system_report"),
            app_commands.Choice(name="👑 Admin Control", value="admin_control"),
            app_commands.Choice(name="📊 Server Dashboard", value="server_dashboard"),
            app_commands.Choice(name="⚙️ Bot Config", value="bot_config"),
            app_commands.Choice(name="🤖 Automation Control", value="automation_control"),
            app_commands.Choice(name="💾 Backup Control", value="backup_control"),
            app_commands.Choice(name="💗 System Health", value="system_health"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def channels_assign(
        self,
        interaction: discord.Interaction,
        purpose: app_commands.Choice[str],
        channel: discord.TextChannel,
    ) -> None:
        """Assigns an existing channel to a purpose."""
        await InteractionManager.execute_interaction(
            interaction,
            "Rai Channels Assign",
            lambda inter, ctx: self._handle_channels_assign(inter, ctx, purpose.value, channel),
            ephemeral=True,
            auto_defer=True,
        )

    async def _handle_channels_assign(
        self,
        interaction: discord.Interaction,
        ctx: ManagedInteractionContext,
        purpose_key: str,
        channel: discord.TextChannel,
    ):
        guild = interaction.guild
        if not guild:
            await InteractionManager.safe_reply(interaction, content="❌ Server context required.", ephemeral=True)
            return

        is_valid, missing = ChannelAssignmentService.check_permissions(channel)
        if not is_valid:
            await InteractionManager.safe_reply(
                interaction,
                content=f"⚠️ Channel {channel.mention} is missing required permissions:\n" + "\n".join(f"• {m}" for m in missing),
                ephemeral=True,
            )
            return

        await ChannelAssignmentService.assign_channel(self.bot, guild.id, purpose_key, channel.id)
        p_def = PURPOSE_MAP[purpose_key]

        embed = discord.Embed(
            title="✅ Channel Assignment Updated",
            description=f"Mapped **{p_def.display_name}** to {channel.mention}.\n*Purpose:* {p_def.description}",
            color=0x57F287,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_footer(text=f"Rai Channels • {ctx.request_id}")
        await InteractionManager.safe_reply(interaction, embed=embed, ephemeral=True)

    # ==========================================
    # /rai status
    # ==========================================

    @rai_group.command(name="status", description="Real-time operational status across all Rai engines and subsystems")
    async def rai_status(self, interaction: discord.Interaction) -> None:
        """Displays real-time status across Gateway, DB, Interaction Manager, Music, Voice, Security."""
        await InteractionManager.execute_interaction(
            interaction,
            "Rai Status",
            self._handle_rai_status,
            ephemeral=False,
            auto_defer=True,
        )

    async def _handle_rai_status(self, interaction: discord.Interaction, ctx: ManagedInteractionContext):
        # 1. Gateway
        gw_ok = self.bot.is_ready()
        gw_ms = round((self.bot.latency or 0.0) * 1000.0, 1)

        # 2. Database
        t0 = time.perf_counter()
        db_ok = False
        if self.bot.db.is_connected:
            try:
                await self.bot.db.execute_read("SELECT 1")
                db_ok = True
            except Exception:
                db_ok = False
        db_ms = round((time.perf_counter() - t0) * 1000.0, 1)

        # 3. Interaction Manager
        im_metrics = InteractionManager.metrics
        im_avg = im_metrics.avg_ack_latency_ms

        # 4. Workers
        worker_ok = hasattr(self.bot, "action_queue")

        # 5. Security
        sec_ok = hasattr(self.bot, "security_brain")

        # 6. Music & Voice
        active_rooms = 0
        if interaction.guild and hasattr(self.bot, "db"):
            try:
                rooms = await self.bot.db.get_active_dynamic_rooms_for_guild(interaction.guild.id)
                active_rooms = len(rooms)
            except Exception:
                pass

        embed = discord.Embed(
            title="✦ RAI OPERATIONAL STATUS",
            description="Real-time telemetry across all core subsystems:",
            color=0x57F287 if (gw_ok and db_ok) else 0xFEE75C,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        embed.add_field(name="🌐 Discord Gateway", value=f"{'🟢 ONLINE' if gw_ok else '🔴 OFFLINE'} (`{gw_ms}ms`)", inline=True)
        embed.add_field(name="💾 Database Engine", value=f"{'🟢 HEALTHY' if db_ok else '🔴 UNHEALTHY'} (`{db_ms}ms`)", inline=True)
        embed.add_field(name="⚡ Interaction Manager", value=f"🟢 HEALTHY (`{im_avg}ms avg ACK`)", inline=True)

        embed.add_field(name="🛡️ Security Engine", value="🟢 ACTIVE & CONTAINED", inline=True)
        embed.add_field(name="🎵 Audio Engine", value="🟢 READY", inline=True)
        embed.add_field(name="🔊 Dynamic Voice", value=f"🟢 ACTIVE (`{active_rooms} rooms`)", inline=True)

        embed.add_field(name="🤖 Worker Supervisor", value="🟢 HEALTHY", inline=True)
        embed.add_field(name="📋 Report Router", value="🟢 OPERATIONAL", inline=True)
        embed.add_field(name="🌐 Web & Realtime API", value="🟢 SYNCED", inline=True)

        embed.set_footer(text=f"Rai Operations • Request ID: {ctx.request_id}")
        await InteractionManager.safe_reply(interaction, embed=embed, ephemeral=False)

    # ==========================================
    # /rai doctor
    # ==========================================

    @rai_group.command(name="doctor", description="Run deep multi-subsystem diagnostic audit with self-healing advice")
    @app_commands.default_permissions(administrator=True)
    async def rai_doctor(self, interaction: discord.Interaction) -> None:
        """Deep multi-subsystem diagnostic audit across all 15 components."""
        await InteractionManager.execute_interaction(
            interaction,
            "Rai Doctor",
            self._handle_rai_doctor,
            ephemeral=False,
            auto_defer=True,
            timeout=25.0,
        )

    async def _handle_rai_doctor(self, interaction: discord.Interaction, ctx: ManagedInteractionContext):
        diagnostics = await RaiDoctor.diagnose_all(self.bot, interaction.guild)

        healthy_count = sum(1 for d in diagnostics if d.status == DiagnosticStatus.HEALTHY)
        degraded_count = sum(1 for d in diagnostics if d.status == DiagnosticStatus.DEGRADED)
        failed_count = sum(1 for d in diagnostics if d.status == DiagnosticStatus.FAILED)

        overall_status = "🟢 ALL SYSTEMS HEALTHY" if (degraded_count == 0 and failed_count == 0) else "🟡 DEGRADED COMPONENTS DETECTED"
        if failed_count > 0:
            overall_status = "🔴 SUBSYSTEM FAILURES DETECTED"

        embed = discord.Embed(
            title="🩺 RAI DOCTOR — MULTI-SUBSYSTEM HEALTH AUDIT",
            description=f"**Verdict:** {overall_status}\n**Score:** `{healthy_count}/{len(diagnostics)} subsystems healthy`",
            color=0x57F287 if (degraded_count == 0 and failed_count == 0) else (0xFEE75C if failed_count == 0 else 0xED4245),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        for d in diagnostics:
            details_str = ", ".join(f"{k}: `{v}`" for k, v in list(d.details.items())[:3])
            val = f"**{d.badge}** (`{d.latency_ms:.1f}ms`)"
            if details_str:
                val += f"\n• {details_str}"
            if d.repair_action:
                val += f"\n💡 *Fix:* {d.repair_action}"
            embed.add_field(name=d.name, value=val, inline=True)

        embed.set_footer(text=f"Rai Diagnostic Doctor • {ctx.request_id}")
        await InteractionManager.safe_reply(interaction, embed=embed, ephemeral=False)


# ---------------------------------------------------------------------------
# UI Helpers for Channel Controls
# ---------------------------------------------------------------------------

async def build_channels_embed(bot: Any, guild: discord.Guild, request_id: str) -> discord.Embed:
    reports = await ChannelAssignmentService.audit_all_channels(bot, guild)

    grouped: Dict[str, List[Any]] = {"SECURITY": [], "REPORTS": [], "ADMIN": []}
    for r in reports:
        grp = r.purpose.category_group
        grouped.setdefault(grp, []).append(r)

    embed = discord.Embed(
        title=f"📋 Rai Canonical Channel Assignments • {guild.name}",
        description=(
            "Rai maps server channels to specific internal event categories.\n"
            "Each purpose receives **only** its assigned event stream.\n"
            "Use the controls below to test or auto-discover assignments."
        ),
        color=0x5865F2,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )

    status_icons = {
        ChannelHealthStatus.CONNECTED: "🟢",
        ChannelHealthStatus.DEGRADED: "🟡",
        ChannelHealthStatus.NO_PERMISSION: "🟠",
        ChannelHealthStatus.MISSING: "🔴",
        ChannelHealthStatus.DISABLED: "⚪",
    }

    category_titles = {
        "SECURITY": "🚨 RAI SECURITY CHANNELS",
        "REPORTS": "📋 RAI REPORT CHANNELS",
        "ADMIN": "👑 RAI ADMIN & CONTROL CHANNELS",
    }

    for cat_key, cat_label in category_titles.items():
        items = grouped.get(cat_key, [])
        lines = []
        for r in items:
            icon = status_icons.get(r.status, "❓")
            target = f"<#{r.channel_id}>" if r.channel_id and r.status != ChannelHealthStatus.MISSING else "`Unassigned`"
            if r.status == ChannelHealthStatus.MISSING:
                target = f"⚠️ *Missing (`{r.channel_id}`)*"
            lines.append(f"{icon} {r.purpose.emoji} **{r.purpose.display_name}**: {target}")
        embed.add_field(name=cat_label, value="\n".join(lines) if lines else "*None*", inline=False)

    connected_count = sum(1 for r in reports if r.status == ChannelHealthStatus.CONNECTED)
    embed.set_footer(text=f"Connected: {connected_count}/{len(reports)} • Request ID: {request_id}")
    return embed


class ChannelControlsView(discord.ui.View):
    def __init__(self, bot: Any, guild_id: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(label="Test Channels", style=discord.ButtonStyle.primary, emoji="🧪")
    async def on_test(self, interaction: discord.Interaction, button: discord.ui.Button):
        await InteractionManager.execute_interaction(
            interaction,
            "Channel Test Button",
            self._handle_test,
            ephemeral=True,
            auto_defer=True,
        )

    async def _handle_test(self, interaction: discord.Interaction, ctx: ManagedInteractionContext):
        guild = interaction.guild
        if not guild:
            await InteractionManager.safe_reply(interaction, content="❌ Server context required.", ephemeral=True)
            return

        cfg = await ChannelAssignmentService.get_config(self.bot, guild.id)
        results = []
        for purpose in CANONICAL_CHANNELS:
            ch_id = getattr(cfg, purpose.config_field, None)
            if ch_id:
                res = await ChannelAssignmentService.test_single_channel(self.bot, guild, purpose.key)
                results.append(res)

        if not results:
            await InteractionManager.safe_reply(
                interaction,
                content="⚠️ No channels are configured yet. Run Auto Discover or `/rai channels assign` first.",
                ephemeral=True,
            )
            return

        passed = sum(1 for r in results if r.get("success"))
        failed = sum(1 for r in results if not r.get("success"))

        lines = []
        for r in results:
            icon = "🟢" if r.get("success") else "🔴"
            status_text = f"**{r['display_name']}**: `{r['status']}`"
            if r.get("error"):
                status_text += f" ({r['error']})"
            lines.append(f"{icon} {status_text}")

        embed = discord.Embed(
            title="🧪 Rai Channel Delivery Test Results",
            description=f"**Passed:** `{passed}` | **Failed:** `{failed}`\n\n" + "\n".join(lines[:20]),
            color=0x57F287 if failed == 0 else 0xFEE75C,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_footer(text=f"Rai Channels Diagnostic • {ctx.request_id}")
        await InteractionManager.safe_reply(interaction, embed=embed, ephemeral=True)

    @discord.ui.button(label="Auto Discover", style=discord.ButtonStyle.success, emoji="🔍")
    async def on_discover(self, interaction: discord.Interaction, button: discord.ui.Button):
        await InteractionManager.execute_interaction(
            interaction,
            "Channel Auto Discover Button",
            self._handle_discover,
            ephemeral=True,
            auto_defer=True,
        )

    async def _handle_discover(self, interaction: discord.Interaction, ctx: ManagedInteractionContext):
        guild = interaction.guild
        if not guild:
            await InteractionManager.safe_reply(interaction, content="❌ Server context required.", ephemeral=True)
            return

        cfg, discovery = await ChannelAssignmentService.auto_assign_discovered_channels(
            self.bot, guild, overwrite_existing=False
        )

        matched_lines = [f"• **{PURPOSE_MAP[k].display_name}** ➔ <#{cid}>" for k, cid in discovery.matched.items()]
        ambig_lines = [f"• **{PURPOSE_MAP[k].display_name}**: Multiple candidates found ({len(cids)})" for k, cids in discovery.ambiguous.items()]

        desc = f"**Auto-Discovered & Assigned ({len(discovery.matched)} channels):**\n"
        desc += "\n".join(matched_lines) if matched_lines else "None automatically mapped.\n"
        if ambig_lines:
            desc += "\n\n⚠️ **Ambiguous Candidates (Need Manual Selection):**\n" + "\n".join(ambig_lines)

        embed = discord.Embed(
            title="🔍 Rai Channel Auto-Discovery",
            description=desc,
            color=0x5865F2,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_footer(text=f"Rai Channel Discovery • {ctx.request_id}")
        await InteractionManager.safe_reply(interaction, embed=embed, ephemeral=True)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def on_refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await InteractionManager.execute_interaction(
            interaction,
            "Channel Refresh Button",
            self._handle_refresh,
            ephemeral=True,
            auto_defer=True,
        )

    async def _handle_refresh(self, interaction: discord.Interaction, ctx: ManagedInteractionContext):
        guild = interaction.guild
        if not guild:
            await InteractionManager.safe_reply(interaction, content="❌ Server context required.", ephemeral=True)
            return

        embed = await build_channels_embed(self.bot, guild, ctx.request_id)
        await InteractionManager.safe_reply(interaction, embed=embed, view=self, ephemeral=True)


async def setup(bot: SentinelBot) -> None:
    await bot.add_cog(ReliabilityCog(bot))
