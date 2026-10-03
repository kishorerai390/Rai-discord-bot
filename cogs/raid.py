"""
Automatic Raid Detection Cog for Rai.
Provides real-time event ingestion (joins, messages, account ages, mentions, invites),
rolling-window calculation via Security Brain, persistent incident tracking,
hysteresis, automatic containment, and administrative commands.
"""

from __future__ import annotations

import datetime
import logging
import time
from typing import TYPE_CHECKING, List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from database.models import RaidConfig, RaidIncident
from utils.embeds import (
    create_embed,
    error_embed,
    info_embed,
    security_embed,
    success_embed,
    warning_embed,
)
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


class RaidCog(commands.Cog, name="RaidDetection"):
    """Automated Raid Detection and Mitigation Engine."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # guild_id -> last 10 messages content cache for duplicate detection
        self._message_cache: dict[int, list[tuple[float, int, str]]] = {}

    raid_group = app_commands.Group(
        name="raid",
        description="Raid detection, incident review, and mitigation controls",
        default_permissions=discord.Permissions(administrator=True),
    )

    # ==========================================
    # EVENT LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Pass member join event to the Security Brain."""
        if not member.guild or not hasattr(self.bot, "security_brain"):
            return
        try:
            await self.bot.security_brain.record_join(member)
        except Exception as e:
            logger.error(f"Error in on_member_join raid pipeline: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Analyze message streams for raid signals (bursts, mentions, invites, duplicates)."""
        if not message.guild or message.author.bot or not hasattr(self.bot, "security_brain"):
            return

        now = time.monotonic()
        guild_id = message.guild.id

        # Cache check for duplicate content
        if guild_id not in self._message_cache:
            self._message_cache[guild_id] = []

        cache = self._message_cache[guild_id]
        cutoff = now - 60.0
        self._message_cache[guild_id] = [item for item in cache if item[0] >= cutoff]

        content_clean = message.content.strip().lower()
        is_duplicate = False
        if len(content_clean) > 8:
            match_count = sum(1 for item in self._message_cache[guild_id] if item[2] == content_clean)
            if match_count >= 2:
                is_duplicate = True

        self._message_cache[guild_id].append((now, message.author.id, content_clean))

        has_mentions = len(message.raw_mentions) >= 4 or len(message.raw_role_mentions) >= 2 or "@everyone" in message.content or "@here" in message.content
        has_invite = "discord.gg/" in message.content or "discord.com/invite/" in message.content

        try:
            await self.bot.security_brain.record_message(
                message,
                has_mentions=has_mentions,
                has_invite=has_invite,
                is_duplicate=is_duplicate,
            )
        except Exception as e:
            logger.error(f"Error in on_message raid pipeline: {e}")

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    @raid_group.command(name="status", description="Inspect raid monitoring status, current risk score, and active incidents")
    @is_admin_or_owner()
    async def raid_status(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await self.bot.db.get_raid_config(guild.id)
        active_inc = await self.bot.db.get_active_raid_incident(guild.id)

        tracker = self.bot.security_brain.get_tracker(guild.id)
        now = time.monotonic()
        joins_1m = tracker.count_window(tracker.joins, now, 60.0)
        joins_5m = tracker.count_window(tracker.joins, now, 300.0)
        joins_15m = tracker.count_window(tracker.joins, now, 900.0)
        msgs_1m = tracker.count_window(tracker.messages, now, 60.0)

        baseline = self.bot.security_brain._baseline_joins.get(guild.id, 2.0)
        score, level, reasons = await self.bot.security_brain.evaluate_raid_risk(guild)

        if active_inc:
            status_text = "🔴 INCIDENT ACTIVE"
            color = Colors.ERROR
        elif not cfg.enabled:
            status_text = "⚪ Disabled"
            color = Colors.DEFAULT
        elif level in ("HIGH", "CRITICAL"):
            status_text = "🔴 CRITICAL ALERT"
            color = Colors.ERROR
        elif level == "SUSPICIOUS":
            status_text = "🟠 SUSPICIOUS"
            color = Colors.WARNING
        elif level == "ELEVATED":
            status_text = "🟡 ELEVATED"
            color = Colors.INFO
        else:
            status_text = "🟢 Normal Monitoring"
            color = Colors.SUCCESS

        embed = create_embed(
            title=f"🛡️ Raid Protection Status — {guild.name}",
            color=color,
        )
        embed.add_field(name="Engine State", value=status_text, inline=True)
        embed.add_field(name="Current Risk Score", value=f"`{score}/100` ({level})", inline=True)
        embed.add_field(name="Auto Containment", value="🟢 Enabled" if cfg.auto_containment else "⚪ Disabled", inline=True)

        embed.add_field(
            name="Real-Time Join Activity",
            value=(
                f"• **1-min:** `{joins_1m}` joins\n"
                f"• **5-min:** `{joins_5m}` joins\n"
                f"• **15-min:** `{joins_15m}` joins\n"
                f"• **Baseline:** `{baseline:.1f}`/min"
            ),
            inline=True,
        )
        embed.add_field(
            name="Message Flow",
            value=(
                f"• **Recent Messages:** `{msgs_1m}`/min\n"
                f"• **Mentions (1m):** `{tracker.count_window(tracker.mentions, now, 60.0)}`\n"
                f"• **Invites (1m):** `{tracker.count_window(tracker.invites, now, 60.0)}`"
            ),
            inline=True,
        )

        if active_inc:
            embed.add_field(
                name="🚨 Active Incident Details",
                value=(
                    f"• **Incident ID:** `{active_inc.incident_id}`\n"
                    f"• **Started At:** {active_inc.started_at[:19]}\n"
                    f"• **Peak Score:** `{active_inc.maximum_score}`\n"
                    f"• **Current Score:** `{active_inc.current_score}`\n"
                    f"• **Status:** `{active_inc.status}`"
                ),
                inline=False,
            )

        if reasons:
            embed.add_field(name="Triggered Risk Signals", value="• " + "\n• ".join(reasons), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @raid_group.command(name="resolve", description="Manually resolve an active raid incident and restore normal state")
    @is_admin_or_owner()
    @app_commands.describe(incident_id="Incident ID to resolve (leave empty for current active incident)")
    async def raid_resolve(self, interaction: discord.Interaction, incident_id: Optional[str] = None):
        guild = interaction.guild
        if not incident_id:
            active_inc = await self.bot.db.get_active_raid_incident(guild.id)
            if not active_inc:
                await interaction.response.send_message(
                    embed=info_embed("No Active Incident", "There is currently no active raid incident in this server."),
                    ephemeral=True,
                )
                return
            incident_id = active_inc.incident_id

        resolved = await self.bot.db.resolve_raid_incident(incident_id, interaction.user.id)
        if resolved:
            if guild.id in self.bot.security_brain._active_incidents:
                del self.bot.security_brain._active_incidents[guild.id]
            await interaction.response.send_message(
                embed=success_embed(
                    "Raid Incident Resolved",
                    f"Incident `{incident_id}` has been marked as resolved by {interaction.user.mention}. Threat level reset to NORMAL.",
                ),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Resolution Failed", f"Could not find an open incident matching `{incident_id}`."),
                ephemeral=True,
            )

    @raid_group.command(name="incidents", description="Review historical raid incidents for this server")
    @is_admin_or_owner()
    async def raid_incidents(self, interaction: discord.Interaction):
        incidents = await self.bot.db.get_raid_incidents(interaction.guild.id, limit=10)
        if not incidents:
            await interaction.response.send_message(
                embed=info_embed("No Incidents", "No raid incidents have been recorded for this server."),
                ephemeral=True,
            )
            return

        embed = create_embed(title=f"📋 Raid Incident History — {interaction.guild.name}", color=Colors.SECURITY)
        for inc in incidents:
            resolved_str = f"Resolved by <@{inc.resolved_by}>" if inc.resolved_by else "Unresolved"
            embed.add_field(
                name=f"[{inc.incident_id}] Level {inc.risk_level} (Score {inc.maximum_score})",
                value=(
                    f"**Started:** {inc.started_at[:19]}\n"
                    f"**Status:** `{inc.status}`\n"
                    f"**Resolution:** {resolved_str}"
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: SentinelBot):
    await bot.add_cog(RaidCog(bot))
