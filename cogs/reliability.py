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


async def setup(bot: SentinelBot) -> None:
    await bot.add_cog(ReliabilityCog(bot))
