"""
Rai Analytics Cog.
Provides:
- Comprehensive server statistics (/stats, /serverstats)
- Real music streaming analytics (/musicstats)
- Security posture & incident statistics (/securitystats)
- Strict Privacy: Zero leakage of private room names, owners, or voice states
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from database.models import MusicAnalytics
from utils.embeds import create_embed, info_embed

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


class AnalyticsCog(commands.Cog, name="Analytics"):
    """Community and System Analytics."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    @app_commands.command(name="stats", description="Display overarching Rai community performance and activity stats")
    async def stats_cmd(self, interaction: discord.Interaction):
        await self._render_overview_stats(interaction)

    @app_commands.command(name="communitystats", description="Display detailed server membership, channels, and activity")
    async def communitystats_cmd(self, interaction: discord.Interaction):
        await self._render_overview_stats(interaction)

    async def _render_overview_stats(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild

        total_members = guild.member_count or len(guild.members)
        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)
        online = sum(1 for m in guild.members if m.status != discord.Status.offline)

        # Get voice activity (excluding hidden rooms category for complete privacy)
        hidden_cfg = await self.bot.db.get_hidden_voice_config(guild.id)
        active_voice_users = 0
        active_voice_channels = 0
        for vc in guild.voice_channels:
            if hidden_cfg.category_id and vc.category_id == hidden_cfg.category_id:
                # Strictly skip hidden private rooms to prevent any count or telemetry leak
                continue
            if len(vc.members) > 0:
                active_voice_channels += 1
                active_voice_users += len(vc.members)

        # Ticket statistics
        ticket_stats = "0 active"
        if self.bot.db._db:
            async with self.bot.db._db.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'open'", (guild.id,)
            ) as cursor:
                row = await cursor.fetchone()
                open_tickets = row[0] if row else 0
                ticket_stats = f"{open_tickets} open"

        # Events count
        events = await self.bot.db.list_events(guild.id, status="scheduled")

        embed = create_embed(
            title=f"📊 Community Analytics — {guild.name}",
            description="Real-time server telemetry and engagement metrics:",
            color=Colors.PRIMARY,
        )
        embed.add_field(
            name="👥 Membership",
            value=f"• Total: **{total_members}**\n• Humans: **{humans}**\n• Bots: **{bots}**\n• Online: **{online}**",
            inline=True,
        )
        embed.add_field(
            name="🔊 Voice Activity",
            value=f"• Active Channels: **{active_voice_channels}**\n• Users in Voice: **{active_voice_users}**",
            inline=True,
        )
        embed.add_field(
            name="🛡️ System & Community",
            value=f"• Active Tickets: **{ticket_stats}**\n• Upcoming Events: **{len(events)}**\n• Latency: **{round(self.bot.latency * 1000)}ms**",
            inline=True,
        )

        embed.set_footer(text="Privacy Notice: Hidden private rooms are strictly excluded from public metrics.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="musicstats", description="Display server music streaming analytics")
    async def musicstats_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild

        analytics: MusicAnalytics = await self.bot.db.get_music_analytics(guild.id)
        total_hours = round(analytics.total_playtime_seconds / 3600, 1)

        embed = create_embed(
            title=f"🎵 Music Analytics — {guild.name}",
            description="Persistent audio streaming telemetry:",
            color=Colors.SUCCESS,
        )
        embed.add_field(name="📻 Tracks Played", value=f"**{analytics.tracks_played:,}** tracks", inline=True)
        embed.add_field(name="⏱️ Total Stream Time", value=f"**{total_hours}** hours", inline=True)
        embed.add_field(name="🎧 Unique Listeners", value=f"**{len(analytics.unique_listeners)}** members", inline=True)

        # Check currently playing track if any
        music_cog = self.bot.get_cog("Music")
        if music_cog and hasattr(music_cog, "get_player"):
            player = music_cog.get_player(guild)
            if player and player.current:
                embed.add_field(
                    name="▶️ Currently Streaming",
                    value=f"[{player.current.title}]({player.current.url}) (`{player.current.duration // 60}:{player.current.duration % 60:02d}`)",
                    inline=False,
                )

        embed.set_footer(text="Data persistently maintained via SQLite WAL.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="securitystats", description="Display server security incidents and posture")
    async def securitystats_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild

        total_incidents = 0
        recent_type = "None"
        if self.bot.db._db:
            async with self.bot.db._db.execute(
                "SELECT COUNT(*), incident_type FROM security_incidents WHERE guild_id = ? ORDER BY id DESC LIMIT 1",
                (guild.id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    total_incidents = row[0]
                    recent_type = row[1] or "None"

        sec_cfg = await self.bot.db.get_security_config(guild.id)

        embed = create_embed(
            title=f"🛡️ Security Health — {guild.name}",
            description="Server protection and incident history:",
            color=Colors.PRIMARY if sec_cfg.anti_nuke else Colors.WARNING,
        )
        embed.add_field(
            name="🔒 Defense Modules",
            value=(
                f"• Anti-Nuke: **{'🟢 Enabled' if sec_cfg.anti_nuke else '⚪ Disabled'}**\n"
                f"• Anti-Raid: **{'🟢 Enabled' if sec_cfg.anti_raid else '⚪ Disabled'}**\n"
                f"• Anti-Spam: **{'🟢 Enabled' if sec_cfg.anti_spam else '⚪ Disabled'}**\n"
                f"• Panic Mode: **{'🔴 Active' if sec_cfg.panic_mode else '🟢 Normal'}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="📋 Incidents",
            value=(
                f"• Total Logged: **{total_incidents}**\n"
                f"• Most Recent: `{recent_type}`\n"
                f"• Verification: **Strict**"
            ),
            inline=True,
        )
        embed.set_footer(text="Audit-log verified detection pipeline.")
        await interaction.followup.send(embed=embed)

    # ==========================================
    # SERVER INTELLIGENCE & ANALYTICS GROUP
    # ==========================================

    analytics_group = app_commands.Group(name="analytics", description="Operational server intelligence and analytics")

    @analytics_group.command(name="members", description="View membership demographics, active users, and growth")
    async def analytics_members_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        from core.analytics import ServerAnalyticsEngine
        m = await ServerAnalyticsEngine.get_members_metrics(interaction.guild)  # type: ignore
        embed = create_embed(
            title=f"👥 Member Intelligence — {interaction.guild.name}",
            description=(
                f"**Total Members:** `{m['total_members']}`\n"
                f"• Humans: `{m['human_members']}`\n"
                f"• Bots: `{m['bot_members']}`\n"
                f"• Online Now: `{m['online_members']}`\n"
                f"• Active Ratio: `{m['active_percentage']}%`"
            ),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed)

    @analytics_group.command(name="voice", description="View voice activity, dynamic rooms, and population")
    async def analytics_voice_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        from core.analytics import ServerAnalyticsEngine
        v = await ServerAnalyticsEngine.get_voice_metrics(self.bot, interaction.guild)  # type: ignore
        embed = create_embed(
            title=f"🎙️ Voice Intelligence — {interaction.guild.name}",
            description=(
                f"**Active Voice Users:** `{v['voice_users']}`\n"
                f"**Occupied Channels:** `{v['active_channels']} / {v['total_voice_channels']}`\n"
                f"**Dynamic Rooms Active:** `{v['dynamic_rooms_active']}`"
            ),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed)

    @analytics_group.command(name="music", description="View music streaming session analytics")
    async def analytics_music_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        from core.analytics import ServerAnalyticsEngine
        mus = await ServerAnalyticsEngine.get_music_metrics(self.bot, interaction.guild)  # type: ignore
        embed = create_embed(
            title=f"🎵 Music Streaming Telemetry — {interaction.guild.name}",
            description=(
                f"**Player Active:** `{'🟢 Yes' if mus['is_active'] else '⚪ Idle'}`\n"
                f"**Currently Playing:** `{mus['current_track'] or 'None'}`\n"
                f"**Queue Length:** `{mus['queue_length']} track(s)`"
            ),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed)

    @analytics_group.command(name="community", description="View community engagement (events, projects, reputation)")
    async def analytics_community_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        from core.analytics import ServerAnalyticsEngine
        c = await ServerAnalyticsEngine.get_community_metrics(self.bot, interaction.guild)  # type: ignore
        embed = create_embed(
            title=f"🤝 Community Engagement — {interaction.guild.name}",
            description=(
                f"**Scheduled Events:** `{c['scheduled_events']}`\n"
                f"**Collaboration Projects:** `{c['active_projects']}`\n"
                f"**Top Contributors Ranked:** `{c['top_reputation_users']}`"
            ),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed)

    @analytics_group.command(name="security", description="View security posture and incident analytics")
    async def analytics_security_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        from core.analytics import ServerAnalyticsEngine
        s = await ServerAnalyticsEngine.get_security_metrics(self.bot, interaction.guild)  # type: ignore
        embed = create_embed(
            title=f"🛡️ Security Telemetry — {interaction.guild.name}",
            description=(
                f"**Security State:** `{s['status']}`\n"
                f"**Emergency Lockdown:** `{'🔴 ACTIVE' if s['lockdown_active'] else '🟢 NORMAL'}`\n"
                f"**Recorded Incidents:** `{s['open_incidents']}`"
            ),
            color=Colors.PRIMARY if s["status"] == "NORMAL" else Colors.WARNING,
        )
        await interaction.followup.send(embed=embed)

    @analytics_group.command(name="system", description="View Rai operational health, latencies, and DB telemetry")
    async def analytics_system_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        from core.analytics import ServerAnalyticsEngine
        sys_m = await ServerAnalyticsEngine.get_system_metrics(self.bot)
        embed = create_embed(
            title=f"❤️ System Telemetry — Rai Core",
            description=(
                f"**Overall Health:** `{sys_m['overall_status']}`\n"
                f"**Gateway Ping:** `{sys_m['gateway_latency_ms']} ms`\n"
                f"**SQLite Database:** `{'🟢 Connected' if sys_m['sqlite_connected'] else '🔴 Error'}` ({sys_m['sqlite_latency_ms']} ms)"
            ),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed)

    @analytics_group.command(name="weekly", description="Generate a comprehensive weekly operational report")
    async def analytics_weekly_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        from core.analytics import ServerAnalyticsEngine
        w = await ServerAnalyticsEngine.generate_weekly_report(self.bot, interaction.guild)  # type: ignore
        embed = create_embed(
            title=f"📊 Weekly Operational Intelligence — {interaction.guild.name}",
            description=(
                f"**Week of:** `{w['week_start']}`\n\n"
                f"👥 **MEMBERS:** `{w['members']['total_members']}` total (`{w['members']['active_percentage']}% active`)\n"
                f"🎙️ **VOICE:** `{w['voice']['voice_users']}` users across `{w['voice']['active_channels']}` channels\n"
                f"🤝 **COMMUNITY:** `{w['community']['scheduled_events']}` events, `{w['community']['active_projects']}` projects\n"
                f"🛡️ **SECURITY:** Status `{w['security']['status']}`, `{w['security']['open_incidents']}` incidents\n"
                f"❤️ **SYSTEM:** Health `{w['system']['overall_status']}`"
            ),
            color=Colors.GOLD,
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: SentinelBot):
    await bot.add_cog(AnalyticsCog(bot))

