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
import logging
import time
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Colors
from config.permissions import can_moderate, is_admin_or_owner
from utils.embeds import create_embed, error_embed, info_embed, warning_embed
from utils.font_generator import AVAILABLE_STYLES, transform_text
from utils.mod_inspector import ModInspectorView, build_mod_view_embed

logger = logging.getLogger(__name__)

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


class FontDropdown(discord.ui.Select):
    def __init__(self, original_text: str, current_style: str = "small_caps"):
        self.original_text = original_text
        self.current_style = current_style
        options = []
        for key, label, example in AVAILABLE_STYLES[:25]:
            options.append(
                discord.SelectOption(
                    label=label,
                    value=key,
                    description=example[:50] if example else None,
                    default=(key == current_style),
                )
            )
        super().__init__(
            placeholder="Select a font style...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0] if getattr(self, "values", None) else self.current_style
        self.current_style = selected
        for opt in self.options:
            opt.default = (opt.value == selected)
        transformed = transform_text(self.original_text, selected)
        embed = create_embed(
            title="✨ Font Generator",
            description=f"```\n{transformed}\n```\n**Preview:**\n{transformed}",
            color=Colors.PRIMARY,
        )
        embed.set_footer(text=f"Style: {selected}")
        if getattr(self, "view", None):
            await interaction.response.edit_message(embed=embed, view=self.view)
        else:
            await interaction.response.edit_message(embed=embed)


class FontSelectView(discord.ui.View):
    def __init__(self, original_text: str, current_style: str = "small_caps"):
        super().__init__(timeout=180.0)
        self.original_text = original_text
        self.current_style = current_style
        self.dropdown = FontDropdown(original_text, current_style)
        self.add_item(self.dropdown)

    @discord.ui.button(label="Copy Text", style=discord.ButtonStyle.secondary, emoji="📋")
    async def copy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        styled = transform_text(self.original_text, self.current_style)
        await interaction.response.send_message(f"```{styled}```", ephemeral=True)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(HelpCategorySelect())


class UtilityCog(commands.Cog, name="Utility"):
    """Server information, diagnostics, and utilities."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.start_time = time.time()
        self._afk_users: dict[tuple[int, int], tuple[str, float]] = {}
        self._status_index: int = 0
        self._presence_loop = self._rotate_presence.start()

    def cog_unload(self):
        self._presence_loop.cancel()

    @tasks.loop(minutes=3)
    async def _rotate_presence(self):
        """Auto-Rotating Bot Rich Presence."""
        await self.bot.wait_until_ready()
        total_members = sum(g.member_count or len(g.members) for g in self.bot.guilds)
        statuses = [
            discord.Activity(type=discord.ActivityType.watching, name="✦ ʀᴀɪ ʀᴀᴍ ✦"),
            discord.Activity(type=discord.ActivityType.listening, name="/stream in #general-chat"),
            discord.Activity(type=discord.ActivityType.watching, name=f"{total_members:,} Members"),
            discord.Activity(type=discord.ActivityType.competing, name="Voice Rooms • /help"),
        ]
        status = statuses[self._status_index % len(statuses)]
        self._status_index += 1
        try:
            await self.bot.change_presence(activity=status, status=discord.Status.online)
        except Exception as e:
            logger.debug(f"Could not rotate bot presence: {e}")

    @_rotate_presence.before_loop
    async def _before_rotate_presence(self):
        try:
            ready_call = self.bot.wait_until_ready()
            if asyncio.iscoroutine(ready_call):
                await ready_call
        except Exception:
            pass

    @app_commands.command(name="afk", description="Set an AFK status message to inform members when you are mentioned")
    @app_commands.describe(status="Reason you are away (e.g., Studying, Sleeping, Grinding ranked)")
    async def afk(self, interaction: discord.Interaction, status: str = "AFK"):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        self._afk_users[(guild.id, interaction.user.id)] = (status, time.time())
        embed = discord.Embed(
            description=f"💤 {interaction.user.mention} is now **AFK**: *{status}*",
            color=Colors.PRIMARY,
        )
        embed.set_footer(text="I will notify anyone who mentions you and clear your AFK when you talk.")
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Manages AFK status clearance on speaking and notifications on mention."""
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return

        guild = message.guild
        now = time.time()

        # 1. Author was AFK -> Welcome them back and clear AFK status
        afk_key = (guild.id, message.author.id)
        if afk_key in self._afk_users:
            status, afk_ts = self._afk_users[afk_key]
            # Ignore messages sent within 3 seconds of setting AFK
            if now - afk_ts > 3.0:
                self._afk_users.pop(afk_key, None)
                elapsed_secs = int(now - afk_ts)
                if elapsed_secs < 60:
                    dur_str = f"{elapsed_secs}s"
                elif elapsed_secs < 3600:
                    dur_str = f"{elapsed_secs // 60}m"
                else:
                    dur_str = f"{elapsed_secs // 3600}h {(elapsed_secs % 3600) // 60}m"
                try:
                    await message.channel.send(
                        f"👋 Welcome back {message.author.mention}! I've cleared your AFK status. *(Away for {dur_str})*",
                        delete_after=8.0,
                    )
                except Exception:
                    pass

        # 2. Check if any mentioned users are currently AFK
        if message.mentions:
            for mentioned in message.mentions:
                if mentioned.id == message.author.id or mentioned.bot:
                    continue
                m_key = (guild.id, mentioned.id)
                if m_key in self._afk_users:
                    status, afk_ts = self._afk_users[m_key]
                    elapsed_secs = int(now - afk_ts)
                    if elapsed_secs < 60:
                        dur_str = f"{elapsed_secs}s ago"
                    elif elapsed_secs < 3600:
                        dur_str = f"{elapsed_secs // 60}m ago"
                    else:
                        dur_str = f"{elapsed_secs // 3600}h {(elapsed_secs % 3600) // 60}m ago"
                    try:
                        await message.channel.send(
                            f"💤 **{mentioned.display_name}** is currently AFK: *{status}* ({dur_str})",
                            delete_after=10.0,
                        )
                    except Exception:
                        pass
                    break

    @app_commands.command(name="font", description="Convert text into stylized Unicode Discord fonts")
    @app_commands.describe(text="The text to convert", style="Initial font style")
    async def font(self, interaction: discord.Interaction, text: str, style: str = "small_caps"):
        transformed = transform_text(text, style)
        embed = create_embed(
            title="✨ Font Generator",
            description=f"```\n{transformed}\n```\n**Preview:**\n{transformed}",
            color=Colors.PRIMARY,
        )
        embed.set_footer(text=f"Style: {style}")
        view = FontSelectView(text, style)
        await interaction.response.send_message(embed=embed, view=view)

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

    @app_commands.command(name="userinfo", description="Display details and verification standing about a user")
    @app_commands.describe(user="The member to inspect (defaults to yourself)")
    async def userinfo(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        member = user or interaction.user
        if not isinstance(member, discord.Member) and interaction.guild:
            member = interaction.guild.get_member(member.id) or member

        # If requester is staff inspecting in a guild, offer the interactive Mod View
        is_staff = can_moderate(interaction.user) or is_admin_or_owner(interaction.user)
        if is_staff and isinstance(member, discord.Member):
            embed = await build_mod_view_embed(self.bot, member, interaction.user)
            view = ModInspectorView(member, self.bot)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        embed = create_embed(
            title=f"👤 {member.name}",
            color=member.accent_color.value if hasattr(member, "accent_color") and member.accent_color else Colors.PRIMARY,
            thumbnail_url=member.display_avatar.url,
        )
        embed.add_field(name="Display Name", value=member.display_name, inline=True)
        embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Bot Account", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(name="Registered", value=discord.utils.format_dt(member.created_at, "R"), inline=True)

        if isinstance(member, discord.Member):
            if member.joined_at:
                embed.add_field(name="Joined Server", value=discord.utils.format_dt(member.joined_at, "R"), inline=True)
            is_pending = getattr(member, "pending", False)
            embed.add_field(name="Rules Agreed", value="⏳ Pending" if is_pending else "✅ Verified", inline=True)
            embed.add_field(name="Highest Role", value=member.top_role.mention, inline=True)
            roles = [r.mention for r in member.roles if not r.is_default() and "───" not in r.name]
            if roles:
                embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles[:16]), inline=False)

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

    @app_commands.command(name="nickstyle", description="Style your server nickname with aesthetic fonts and symbols")
    @app_commands.describe(
        style="Select font style",
        text="Custom nickname text to style (defaults to your current name)",
    )
    @app_commands.choices(
        style=[
            app_commands.Choice(name="ᴀᴇsᴛʜᴇᴛɪᴄ ╏ Small Caps", value="small_caps"),
            app_commands.Choice(name="𝖇𝖔𝖑𝖉 𝖌𝖔𝖙𝖍𝖎𝖈 ╏ Bold Fraktur", value="bold_gothic"),
            app_commands.Choice(name="𝓫𝓸𝓵𝓭 𝓼𝓬𝓻𝓲𝓹𝓽 ╏ Bold Cursive", value="bold_script"),
            app_commands.Choice(name="𝕕𝕠𝕦𝕓𝕝𝕖 ╏ Blackboard Double-Struck", value="double_struck"),
            app_commands.Choice(name="✦ ɴᴀᴍᴇ ✦ ╏ Cyberpunk Stars", value="cyberpunk"),
            app_commands.Choice(name="w i d e ╏ Aesthetic Spaced", value="wide"),
        ]
    )
    async def nickstyle_command(self, interaction: discord.Interaction, style: str, text: Optional[str] = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        member = interaction.user
        guild = interaction.guild
        base_text = text.strip() if text else member.display_name

        if style == "cyberpunk":
            transformed = f"✦ {transform_text(base_text, 'small_caps')} ✦"
        elif style == "wide":
            transformed = " ".join(base_text)
        else:
            transformed = transform_text(base_text, style)

        target_nick = transformed[:32]

        if not guild.me.guild_permissions.manage_nicknames:
            await interaction.response.send_message("❌ Bot lacks `Manage Nicknames` permission.", ephemeral=True)
            return

        if member.id == guild.owner_id:
            await interaction.response.send_message(
                embed=info_embed(
                    "Server Owner Preview",
                    f"Discord prevents bots from changing the Server Owner's nickname.\n\n**Styled Nickname Preview:**\n`{target_nick}`\n\nYou can copy and paste it into your server profile!",
                ),
                ephemeral=True,
            )
            return

        mem_pos = getattr(member.top_role, "position", 0)
        bot_pos = getattr(guild.me.top_role, "position", 0)
        if isinstance(mem_pos, int) and isinstance(bot_pos, int) and mem_pos >= bot_pos:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Role Hierarchy Notice",
                    f"Your highest role is higher than or equal to the bot's role.\n\n**Styled Nickname Preview:**\n`{target_nick}`\n\nYou can manually paste it into your profile!",
                ),
                ephemeral=True,
            )
            return

        try:
            old_nick = member.display_name
            await member.edit(nick=target_nick, reason=f"Aesthetic Nickname Styler ({style})")
            embed = discord.Embed(
                title="✨ Nickname Styled Successfully",
                description=(
                    f"**Previous:** `{old_nick}`\n"
                    f"**New Nickname:** `{target_nick}`\n\n"
                    f"Applied style: **`{style}`**"
                ),
                color=Colors.PRIMARY,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to update nickname: {e}", ephemeral=True)

    @app_commands.command(name="pulse", description="Real-time heartbeat, voice room activity, and server diagnostics")
    async def pulse_command(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        voice_members = [m for m in guild.members if m.voice and m.voice.channel]
        voice_count = len(voice_members)
        streamers_count = sum(1 for m in voice_members if m.voice and m.voice.self_stream)
        voice_channels_active = len({m.voice.channel.id for m in voice_members if m.voice and m.voice.channel})

        total_members = guild.member_count or len(guild.members)
        online_members = sum(1 for m in guild.members if m.status != discord.Status.offline)
        bot_count = sum(1 for m in guild.members if m.bot)
        human_count = max(0, total_members - bot_count)

        latency_ms = round(self.bot.latency * 1000, 1)
        uptime_sec = int(time.time() - self.start_time)
        hrs, rem = divmod(uptime_sec, 3600)
        mins, _ = divmod(rem, 60)

        embed = discord.Embed(
            title=f"📊 ✦ 𝕾ᴇʀᴠᴇʀ 𝕻ᴜʟsᴇ ╏ {guild.name} ✦",
            description="Real-time vitality heartbeat and community activity metrics:\n",
            color=0x5865F2,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name="👥 Population",
            value=(
                f"• Total Members: **{total_members:,}**\n"
                f"• Humans: **{human_count:,}** ╏ Bots: **{bot_count}**\n"
                f"• Online Now: **{online_members:,}**"
            ),
            inline=True,
        )

        embed.add_field(
            name="🎙️ Voice Activity",
            value=(
                f"• In Voice: **{voice_count} members**\n"
                f"• Active Channels: **{voice_channels_active}**\n"
                f"• Live Streamers: **{streamers_count} 📺**"
            ),
            inline=True,
        )

        embed.add_field(
            name="⚡ System Diagnostics",
            value=(
                f"• Bot Latency: **`{latency_ms} ms`**\n"
                f"• Bot Uptime: **`{hrs}h {mins}m`**\n"
                f"• Security Shield: **ARMED 🛡️**"
            ),
            inline=False,
        )

        embed.set_footer(text="✦ ʀᴀɪ Autonomous Ecosystem • Real-Time Pulse ✦")
        await interaction.response.send_message(embed=embed)


async def setup(bot: SentinelBot):
    await bot.add_cog(UtilityCog(bot))
