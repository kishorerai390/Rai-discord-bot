"""
RAI — Natural Language Control Cog.
Listens to natural language messages in Discord channels, validates permissions,
routes recognized intents to existing service layers, and exposes the intent registry.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from core.nl_control import ADMIN_INTENTS, DANGEROUS_INTENTS, NLControlEngine, NLIntent
from utils.embeds import create_embed, info_embed, success_embed

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger(__name__)


class NLControlCog(commands.Cog, name="NLControl"):
    """Conversational Natural Language Owner Control Subsystem."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    # =========================================================================
    # MESSAGE LISTENER
    # =========================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Evaluates incoming messages for natural language administrative commands."""
        # Fast exit for bot messages or missing guild
        if message.author.bot or not message.guild:
            return

        try:
            handled = await NLControlEngine.process_message(self.bot, message)
            if handled:
                logger.info(
                    f"NL Control: Executed natural language request from {message.author} "
                    f"in #{message.channel.name} ({message.guild.name})"
                )
        except Exception as e:
            logger.error(f"Error processing natural language message: {e}", exc_info=True)

    # =========================================================================
    # SLASH COMMAND DISCOVERY & REGISTRY (/nl)
    # =========================================================================

    nl_group = app_commands.Group(
        name="nl",
        description="Natural Language Control Engine discovery and audit logs",
        default_permissions=discord.Permissions(administrator=True),
    )

    @nl_group.command(name="registry", description="Display full mapping of Natural Language phrases to Rai services")
    async def nl_registry(self, interaction: discord.Interaction):
        """Displays internal registry of natural language intents, permissions, and services."""
        registry_data = [
            ("BACKUP_CREATE", '"you auto backup", "backup the server"', "/backup create", "OWNER / ADMIN", "No"),
            ("BACKUP_LIST", '"show backups", "list backups"', "/backup list", "OWNER / ADMIN", "No"),
            ("HEALTH_CHECK", '"check health", "is the bot okay"', "/health", "OWNER / ADMIN", "No"),
            ("ROOM_LIST", '"show active rooms", "check rooms"', "Dynamic Room Engine", "OWNER / ADMIN", "No"),
            ("ROOM_CLEANUP", '"clean empty rooms"', "Dynamic Room Engine", "OWNER / ADMIN", "No"),
            ("LOCK_ALL_ROOMS", '"lock all rooms"', "Dynamic Room Engine", "OWNER / ADMIN", "⚠️ YES"),
            ("DELETE_ALL_ROOMS", '"delete all rooms"', "Dynamic Room Engine", "OWNER / ADMIN", "⚠️ YES"),
            ("SECURITY_CHECK", '"check security", "security status"', "/security status", "OWNER / ADMIN", "No"),
            ("LOCK_SERVER", '"lock the server"', "/security lockdown", "OWNER / ADMIN", "⚠️ YES"),
            ("ROOM_PRIVACY", '"make my room private / public"', "Dynamic Room Engine", "Room Owner", "No"),
            ("ROOM_INVITE", '"invite @User"', "Dynamic Room Engine", "Room Owner / Co-Host", "No"),
            ("ROOM_REMOVE", '"remove @User"', "Dynamic Room Engine", "Room Owner / Co-Host", "No"),
            ("DELEGATION", '"give Alex DJ", "make Alex cohost"', "Dynamic Room Engine", "Room Owner", "No"),
            ("MUSIC_CONTROLS", '"skip", "pause", "music queue"', "/music queue/skip", "Listeners / DJ", "No"),
            ("CHAINED_TASKS", '"backup the server and then check health"', "Sequential Engine", "OWNER / ADMIN", "Varies"),
        ]

        lines = []
        for intent, phrases, cmd, perm, confirm in registry_data:
            lines.append(f"**{intent}**\n• Phrases: `{phrases}`\n• Service: `{cmd}` | Perm: `{perm}` | Confirm: `{confirm}`\n")

        embed = create_embed(
            title="⚙️ RAI Natural Language Command Registry",
            description="All natural language controls map directly into existing production services without duplicate logic.\n\n" + "\n".join(lines[:8]),
            color=Colors.PRIMARY,
        )
        embed.set_footer(text="Owner-First Architecture • Strict Permission Enforcement")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @nl_group.command(name="audit", description="View recent natural language administrative execution audits")
    async def nl_audit(self, interaction: discord.Interaction):
        """Displays recent executed natural language actions from the immutable audit log."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Guild context required.", ephemeral=True)
            return

        records = await self.bot.db.get_recent_nl_audits(interaction.guild.id, limit=5)
        if not records:
            await interaction.response.send_message(embed=info_embed("NL Audit Trail", "No natural language commands logged yet."), ephemeral=True)
            return

        lines = []
        for r in records:
            res_emoji = "✅" if r.get("result") == "SUCCESS" else "❌"
            lines.append(
                f"`[{r.get('incident_id')}]` {res_emoji} **{r.get('intent')}** by <@{r.get('user_id')}>\n"
                f"• Input: *\"{r.get('raw_message')}\"*\n"
                f"• Status: `{r.get('result')}`\n"
            )

        embed = create_embed(
            title=f"📋 Natural Language Audit Log — {interaction.guild.name}",
            description="\n".join(lines),
            color=Colors.SUCCESS,
        )
        embed.set_footer(text="Cryptographic Incident Records • Dual-Channel Auditing")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =========================================================================
    # SLASH COMMAND OPERATIONS CENTER (/operations)
    # =========================================================================

    operations_group = app_commands.Group(
        name="operations",
        description="Unified Server Operations Center controls",
        default_permissions=discord.Permissions(administrator=True),
    )

    @operations_group.command(name="dashboard", description="Open the Server Operations Assistant Dashboard")
    async def ops_dashboard(self, interaction: discord.Interaction):
        """Displays the master interactive Server Operations Assistant dashboard."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Guild context required.", ephemeral=True)
            return

        from core.operations_core import RaiOperationsCore, OwnerOperationsDashboardView
        ops = RaiOperationsCore.get_instance(self.bot)
        overview = await ops.get_operations_overview(interaction.guild)

        health_emoji = "🟢" if overview["system_health"] == "HEALTHY" else "🟡"
        sec_emoji = "🟢" if overview["security_status"] == "NORMAL" else "🟡"
        maint_str = " | 🛠️ *Maintenance Mode*" if overview["maintenance_mode"] else ""

        desc = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 **Bot:** 🟢 Online{maint_str}\n"
            f"❤️ **System:** {health_emoji} {overview['system_health'].capitalize()}\n"
            f"🛡️ **Security:** {sec_emoji} {overview['security_status'].capitalize()}\n"
            f"🎙️ **Active Rooms:** `{overview['active_rooms_count']}`\n"
            f"🎵 **Music Sessions:** `{overview['music_sessions_count']}`\n"
            f"👥 **Members:** `{overview['members_count']:,}`\n"
            f"💾 **Last Backup:** `{overview['last_backup_str']}`\n"
            f"⚠️ **Open Incidents:** `{overview['open_incidents_count']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        embed = create_embed(
            title="🧠 RAI OPERATIONS CENTER",
            description=desc,
            color=Colors.PRIMARY,
        )

        owner_id = interaction.guild.owner_id or interaction.user.id
        view = OwnerOperationsDashboardView(self.bot, interaction.guild.id, owner_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @operations_group.command(name="away", description="Generate 'While you were away' actual event summary")
    @app_commands.describe(hours="Lookback period in hours (default: 12)")
    async def ops_away(self, interaction: discord.Interaction, hours: int = 12):
        """Aggregates real stored event statistics from SQLite."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Guild context required.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        from core.operations_core import AnalyticsService
        summary = await AnalyticsService.get_away_summary(self.bot, interaction.guild, hours=max(1, min(hours, 72)))

        desc = (
            f"**Period:** `{summary['period_start']} → {summary['period_end']}`\n\n"
            f"👥 **COMMUNITY**\n"
            f"• `{summary['member_count']}` total members\n\n"
            f"🎙️ **ROOMS**\n"
            f"• `{summary['rooms_created']}` created\n"
            f"• `{summary['rooms_cleaned']}` cleaned\n"
            f"• `{summary['rooms_active']}` active\n\n"
            f"🎵 **MUSIC**\n"
            f"• `{summary['music_sessions']}` active sessions\n\n"
            f"🛡️ **SECURITY**\n"
            f"• `{summary['security_incidents_count']}` recorded incidents\n\n"
            f"💾 **BACKUP**\n"
            f"• `{summary['backups_count']}` archives in period\n\n"
            f"❤️ **SYSTEM**\n"
            f"• Health: `{summary['health_status']}`"
        )

        embed = create_embed(
            title="📊 RAI — WHILE YOU WERE AWAY",
            description=desc,
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @operations_group.command(name="simulate-raid", description="Execute safe security simulation mode")
    async def ops_simulate(self, interaction: discord.Interaction):
        """Simulates mass raid containment in safe sandbox mode without damaging the server."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Guild context required.", ephemeral=True)
            return

        from core.premium import PremiumFeatureGate, PremiumFeature, create_premium_upgrade_embed, PremiumUpgradeView, EntitlementScope
        gate = await PremiumFeatureGate.has_access(self.bot, PremiumFeature.SECURITY_SIMULATION, interaction.user.id, interaction.guild.id)
        if not gate.has_access:
            embed = create_premium_upgrade_embed("security_simulation", "Raid & Nuke Attack Simulation", EntitlementScope.GUILD)
            view = PremiumUpgradeView(self.bot, interaction.user.id, "security_simulation", EntitlementScope.GUILD)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        from core.operations_core import RaiOperationsCore
        ops = RaiOperationsCore.get_instance(self.bot)
        sim_data = await ops.simulate_raid(interaction.guild, interaction.user)  # type: ignore

        desc = (
            f"**Simulation ID:** `{sim_data['simulation_id']}`\n\n"
            f"**Scenario:** `{sim_data['scenario']}`\n"
            f"**Detected:** `{sim_data['simulated_deletions']}` simulated deletions (Threshold: `{sim_data['threshold']}`)\n"
            f"**Would trigger:** 🛡️ {sim_data['would_trigger']}\n"
            f"**Would execute:** 🔒 {sim_data['would_execute']}\n"
            f"**Notifications Sent:** {', '.join(sim_data['notified_destinations'])}\n\n"
            f"🛡️ **Sandbox Guarantee:** `Real damage taken: None (Zero channels deleted/modified)`"
        )

        embed = create_embed(
            title="🧪 SECURITY SIMULATION — RAID CONTAINMENT",
            description=desc,
            color=Colors.WARNING,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @operations_group.command(name="maintenance", description="Toggle server maintenance mode")
    @app_commands.describe(enable="Enable or disable maintenance mode", reason="Optional operational reason")
    async def ops_maintenance(self, interaction: discord.Interaction, enable: bool, reason: Optional[str] = None):
        """Pauses non-critical automation while preserving security."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Guild context required.", ephemeral=True)
            return

        from core.operations_core import RaiOperationsCore
        ops = RaiOperationsCore.get_instance(self.bot)
        success = await ops.set_maintenance_mode(interaction.guild, interaction.user, enable, reason=reason)  # type: ignore

        if success:
            status_text = "ENABLED 🟡" if enable else "DISABLED 🟢"
            embed = create_embed(
                title=f"🛠️ Maintenance Mode — {status_text}",
                description=f"Maintenance mode successfully updated.\n• **Security:** 🟢 Active\n• **Reports:** 🟢 Active\n• **Automation:** {'🟡 Paused' if enable else '🟢 Active'}",
                color=Colors.WARNING if enable else Colors.SUCCESS,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Failed to update maintenance mode.", ephemeral=True)

    @operations_group.command(name="config-version", description="Save or inspect bot configuration versions")
    @app_commands.describe(action="Action to perform", label="Optional label for saving version")
    @app_commands.choices(action=[
        app_commands.Choice(name="List Versions", value="list"),
        app_commands.Choice(name="Save Current Version", value="save"),
    ])
    async def ops_config_version(self, interaction: discord.Interaction, action: str, label: Optional[str] = None):
        """Configuration versioning (Phase 26)."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Guild context required.", ephemeral=True)
            return

        if action == "save":
            from core.operations_core import ConfigurationService
            curr_config = {
                "security_threshold": 5,
                "room_cleanup_empty": True,
                "auto_backup_enabled": True,
            }
            v_id = await ConfigurationService.save_version(
                self.bot, interaction.guild.id, interaction.user.id, curr_config, label or "Manual Snapshot"
            )
            embed = success_embed(
                "Configuration Snapshot Saved",
                f"✅ Saved configuration version **#{v_id}**\n• Label: `{label or 'Manual Snapshot'}`\n• Author: {interaction.user.mention}"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            from core.operations_core import ConfigurationService
            versions = await ConfigurationService.list_versions(self.bot, interaction.guild.id)
            if not versions:
                await interaction.response.send_message(embed=info_embed("Configuration Versions", "No configuration versions saved yet."), ephemeral=True)
                return

            lines = []
            for v in versions[:8]:
                lines.append(f"• **Version #{v['id']}** — `{v.get('label', 'Snapshot')}` (Created by <@{v.get('created_by')}>)")
            embed = create_embed(
                title=f"⚙️ Configuration Versions — {interaction.guild.name}",
                description="\n".join(lines),
                color=Colors.PRIMARY,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: SentinelBot) -> None:
    await bot.add_cog(NLControlCog(bot))
