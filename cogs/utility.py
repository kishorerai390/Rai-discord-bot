"""
Utility and Server Information Cog.
Features:
- /serverinfo, /userinfo, /roleinfo, /channelinfo, /botinfo, /avatar
- Interactive /help command with Select Menu categories
"""

from __future__ import annotations

import datetime
import os
import platform
import sys
import time
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed

if TYPE_CHECKING:
    from main import SentinelBot


# ==========================================
# INTERACTIVE /HELP SELECT VIEW
# ==========================================

class HelpCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Security & Anti-Nuke", description="Server defense, thresholds, lockdown", emoji="🛡️", value="security"),
            discord.SelectOption(label="AutoMod", description="Automated filters, spam, banned words", emoji="🤖", value="automod"),
            discord.SelectOption(label="Moderation", description="Ban, kick, timeout, warn, clear, slowmode", emoji="🔨", value="moderation"),
            discord.SelectOption(label="Welcome & Goodbye", description="Welcome messages, embeds, autorole", emoji="👋", value="welcome"),
            discord.SelectOption(label="Music", description="Play, pause, queue, volume, loop, skip", emoji="🎵", value="music"),
            discord.SelectOption(label="Tickets", description="Support panels, tickets, transcripts", emoji="🎫", value="tickets"),
            discord.SelectOption(label="Logging", description="Audit logging channels configuration", emoji="📋", value="logging"),
            discord.SelectOption(label="Autorole", description="Automatic role assignment for new members", emoji="🎭", value="autorole"),
            discord.SelectOption(label="Utility & Info", description="Server, user, role, channel, bot info", emoji="🔧", value="utility"),
            discord.SelectOption(label="Fun & Games", description="8ball, coinflip, dice, ship, poll", emoji="🎉", value="fun"),
        ]
        super().__init__(placeholder="Select a category to view commands...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        embed = create_embed(title="Help Menu", color=Colors.PRIMARY)

        if choice == "security":
            embed.title = "🛡️ Security & Anti-Nuke Commands"
            embed.description = (
                "`/security setup` — Configure action thresholds and punishments\n"
                "`/security enable` — Arm automated security defenses\n"
                "`/security disable` — Disarm automated defenses\n"
                "`/security status` — View active security thresholds and audit state\n"
                "`/security whitelist` — Manage trusted members/roles exempt from limits\n"
                "`/security lockdown` — Lock all text channels immediately\n"
                "`/security unlock` — Restore channels after lockdown\n"
                "`/security emergency-stop` — Suppress automated destructive punishments\n"
                "`/security emergency-resume` — Resume automated punishments\n"
                "`/security emergency-status` — Check kill-switch status\n"
                "`/security incidents` — Filter and review recorded security audit trail\n"
                "`/security cooldowns` — View active in-memory counters\n"
                "`/security reset-cooldown` — Reset cooldowns for a user\n"
                "`/security reset-cooldowns` — Clear all guild cooldowns"
            )
        elif choice == "automod":
            embed.title = "🤖 AutoMod Commands"
            embed.description = (
                "`/automod setup` — Configure detection filters and punishments\n"
                "`/automod enable` — Activate real-time chat filters\n"
                "`/automod disable` — Deactivate chat filters\n"
                "`/automod words` — Add, remove, or list banned words\n"
                "`/automod status` — View current AutoMod settings and active filters"
            )
        elif choice == "moderation":
            embed.title = "🔨 Moderation Commands"
            embed.description = (
                "`/ban` — Ban a member with confirmation\n"
                "`/unban` — Unban a user by their Discord ID\n"
                "`/kick` — Kick a member from the server\n"
                "`/timeout` — Mute/timeout a member (e.g. 10m, 1h, 1d)\n"
                "`/untimeout` — Remove timeout from a member\n"
                "`/warn` — Issue a formal warning to a user\n"
                "`/warnings` — Inspect recorded warnings for a user\n"
                "`/clear` — Purge messages in the current channel\n"
                "`/slowmode` — Set channel message slowmode delay\n"
                "`/lock` — Lock channel for @everyone\n"
                "`/unlock` — Unlock channel for @everyone"
            )
        elif choice == "welcome":
            embed.title = "👋 Welcome & Goodbye Commands"
            embed.description = (
                "`/welcome setup` — Configure channels, embeds, and DM settings\n"
                "`/welcome channel` — Set welcome or goodbye channel\n"
                "`/welcome message` — Customize message templates\n"
                "`/welcome role` — Configure automatic join role\n"
                "`/welcome test` — Preview welcome message in chat\n"
                "`/welcome disable` — Turn off welcome announcements"
            )
        elif choice == "music":
            embed.title = "🎵 Music Commands"
            embed.description = (
                "`/play <query>` — Search or play audio from YouTube\n"
                "`/pause` — Pause current playback\n"
                "`/resume` — Resume playback\n"
                "`/skip` — Skip to next song in queue\n"
                "`/stop` — Clear queue and stop playing\n"
                "`/queue` — View queued tracks\n"
                "`/nowplaying` — View track details and progress\n"
                "`/loop <mode>` — Toggle loop: off, song, queue\n"
                "`/shuffle` — Randomize tracks in queue\n"
                "`/volume <1-100>` — Adjust volume percentage\n"
                "`/disconnect` — Disconnect bot from voice channel"
            )
        elif choice == "tickets":
            embed.title = "🎫 Ticket Support Commands"
            embed.description = (
                "`/ticket setup` — Post an interactive ticket creation panel\n"
                "`/ticket close` — Close ticket and save transcript\n"
                "`/ticket add` — Add a member to the ticket channel\n"
                "`/ticket remove` — Remove a member from the ticket channel"
            )
        elif choice == "logging":
            embed.title = "📋 Audit Logging Commands"
            embed.description = (
                "`/logging setup` — Set default general audit channel\n"
                "`/logging set` — Route specific event categories to channels\n"
                "`/logging status` — Display active log channel routing"
            )
        elif choice == "autorole":
            embed.title = "🎭 Autorole Commands"
            embed.description = (
                "`/autorole set` — Configure role given to new members\n"
                "`/autorole remove` — Disable autorole\n"
                "`/autorole status` — Check autorole configuration"
            )
        elif choice == "utility":
            embed.title = "🔧 Utility & Info Commands"
            embed.description = (
                "`/serverinfo` — Detailed server statistics and features\n"
                "`/userinfo` — Member roles, permissions, join date\n"
                "`/roleinfo` — Role permissions, members count, color\n"
                "`/channelinfo` — Channel topic, type, permissions\n"
                "`/botinfo` — Bot latency, uptime, system stats\n"
                "`/avatar` — View and download member avatar\n"
                "`/font` — Convert text to fancy Discord Unicode fonts (Fraktur, Cursive, Small Caps, etc.)\n"
                "`/help` — Display interactive command guide"
            )
        elif choice == "fun":
            embed.title = "🎉 Fun & Games Commands"
            embed.description = (
                "`/8ball <question>` — Ask the magic 8-ball\n"
                "`/coinflip` — Flip a two-sided coin\n"
                "`/dice` — Roll a die with custom sides\n"
                "`/ship <user1> <user2>` — Calculate compatibility score\n"
                "`/poll <question> [options]` — Create an interactive reaction poll"
            )

        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(HelpCategorySelect())


class UtilityCog(commands.Cog, name="Utility"):
    """Server information, diagnostics, and utilities."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.start_time = time.time()

    @app_commands.command(name="help", description="Browse all bot commands by category")
    async def help_cmd(self, interaction: discord.Interaction):
        embed = create_embed(
            title="🛡️ Sentinel Bot Command Guide",
            description=(
                "Welcome to **Sentinel** — an all-in-one Discord bot combining:\n\n"
                "• 🛡️ **Advanced Security & Anti-Nuke**\n"
                "• 🤖 **Real-time AutoMod & Anti-Spam**\n"
                "• 🔨 **Role Hierarchy Moderation**\n"
                "• 👋 **Customizable Welcome & Goodbye**\n"
                "• 🎵 **High-Fidelity Music Streaming**\n"
                "• 🎫 **Interactive Support Tickets**\n"
                "• 📋 **Granular Audit Logging**\n"
                "• 🔧 **Server Utility & Diagnostics**\n"
                "• 🎉 **Community Fun & Games**\n\n"
                "*Select a category below to explore available commands and parameters.*"
            ),
            color=Colors.PRIMARY,
        )
        if self.bot.user.display_avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        view = HelpView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="serverinfo", description="Display detailed server information and statistics")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = create_embed(
            title=f"🏰 {guild.name}",
            color=Colors.PRIMARY,
            thumbnail_url=guild.icon.url if guild.icon else None,
        )
        embed.add_field(name="Owner", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="Created At", value=discord.utils.format_dt(guild.created_at, "D"), inline=True)

        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)
        embed.add_field(name="Members", value=f"Total: **{guild.member_count}**\nHumans: {humans} | Bots: {bots}", inline=True)
        embed.add_field(name="Channels", value=f"Text: {len(guild.text_channels)} | Voice: {len(guild.voice_channels)}", inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)

        if guild.banner:
            embed.set_image(url=guild.banner.url)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Display details about a user")
    @app_commands.describe(user="The member to inspect (defaults to yourself)")
    async def userinfo(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        member = user or interaction.user
        if not isinstance(member, discord.Member):
            member = interaction.guild.get_member(member.id) or member

        embed = create_embed(
            title=f"👤 {member.name}",
            color=member.accent_color.value if hasattr(member, "accent_color") and member.accent_color else Colors.PRIMARY,
            thumbnail_url=member.display_avatar.url,
        )
        embed.add_field(name="Display Name", value=member.display_name, inline=True)
        embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Bot?", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(name="Registered", value=discord.utils.format_dt(member.created_at, "R"), inline=True)

        if isinstance(member, discord.Member):
            if member.joined_at:
                embed.add_field(name="Joined Server", value=discord.utils.format_dt(member.joined_at, "R"), inline=True)
            embed.add_field(name="Highest Role", value=member.top_role.mention, inline=True)
            roles = [r.mention for r in member.roles if not r.is_default()]
            if roles:
                embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles[:12]), inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Display a user's avatar image")
    @app_commands.describe(user="The member whose avatar to view")
    async def avatar(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        embed = create_embed(
            title=f"🖼️ Avatar for {target.name}",
            color=Colors.PRIMARY,
            image_url=target.display_avatar.url,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roleinfo", description="Display information about a server role")
    @app_commands.describe(role="The role to inspect")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        embed = create_embed(
            title=f"🛡️ Role: @{role.name}",
            color=role.color.value or Colors.PRIMARY,
        )
        embed.add_field(name="Role ID", value=f"`{role.id}`", inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Members with Role", value=str(len(role.members)), inline=True)
        embed.add_field(name="Position", value=str(role.position), inline=True)
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        embed.add_field(name="Hoisted (Separated)", value="Yes" if role.hoist else "No", inline=True)

        key_perms = []
        if role.permissions.administrator:
            key_perms.append("Administrator")
        if role.permissions.manage_guild:
            key_perms.append("Manage Server")
        if role.permissions.ban_members:
            key_perms.append("Ban Members")
        if role.permissions.kick_members:
            key_perms.append("Kick Members")
        if role.permissions.manage_channels:
            key_perms.append("Manage Channels")
        if role.permissions.manage_roles:
            key_perms.append("Manage Roles")

        embed.add_field(name="Key Permissions", value=", ".join(key_perms) if key_perms else "None", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="channelinfo", description="Display information about a channel")
    @app_commands.describe(channel="The channel to inspect (defaults to current)")
    async def channelinfo(self, interaction: discord.Interaction, channel: Optional[discord.abc.GuildChannel] = None):
        ch = channel or interaction.channel
        embed = create_embed(
            title=f"📁 #{ch.name}",
            color=Colors.INFO,
        )
        embed.add_field(name="Channel ID", value=f"`{ch.id}`", inline=True)
        embed.add_field(name="Type", value=str(ch.type).capitalize(), inline=True)
        embed.add_field(name="Created At", value=discord.utils.format_dt(ch.created_at, "D"), inline=True)

        if isinstance(ch, discord.TextChannel):
            embed.add_field(name="Topic", value=ch.topic or "*No topic set*", inline=False)
            embed.add_field(name="Slowmode", value=f"{ch.slowmode_delay}s", inline=True)
            embed.add_field(name="NSFW?", value="Yes" if ch.nsfw else "No", inline=True)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="botinfo", description="Display Rai bot health and diagnostic statistics")
    async def botinfo(self, interaction: discord.Interaction):
        uptime_sec = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        latency_ms = round(self.bot.latency * 1000, 1)

        embed = create_embed(
            title="🤖 Rai Diagnostics",
            color=Colors.PRIMARY,
            thumbnail_url=self.bot.user.display_avatar.url if self.bot.user.display_avatar else None,
        )
        embed.add_field(name="Latency", value=f"⚡ `{latency_ms} ms`", inline=True)
        embed.add_field(name="Uptime", value=f"⏱️ `{uptime_str}`", inline=True)
        embed.add_field(name="Discord.py", value=f"`v{discord.__version__}`", inline=True)
        embed.add_field(name="Python", value=f"`v{platform.python_version()}`", inline=True)
        embed.add_field(name="Operating System", value=f"`{platform.system()} {platform.release()}`", inline=True)
        embed.add_field(name="Guilds Cached", value=str(len(self.bot.guilds)), inline=True)

        await interaction.response.send_message(embed=embed)


async def setup(bot: SentinelBot):
    await bot.add_cog(UtilityCog(bot))
