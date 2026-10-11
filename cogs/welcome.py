"""
Customizable Welcome & Goodbye System.
Supports templates, member count formatting, avatar embeds, autorole, DMs, and test previews.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


def format_template(text: str, member: discord.Member) -> str:
    """Replaces placeholders: {user}, {username}, {server}, {member_count}."""
    return (
        text.replace("{user}", member.mention)
        .replace("{username}", member.name)
        .replace("{server}", member.guild.name)
        .replace("{member_count}", str(member.guild.member_count))
    )


def build_sticky_banner(guild: discord.Guild) -> tuple[discord.Embed, discord.ui.View]:
    """Generates an aesthetic quick-navigation bulletin and link buttons for #general-chat."""
    embed = discord.Embed(
        title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓦ᴇʟᴄᴏᴍᴇ & 𝓠ᴜɪᴄᴋ 𝓝ᴀᴠɪɢᴀᴛɪᴏɴ ✦",
        description=(
            "Welcome to **#general-chat**! Keep conversations respectful, vibrant, and fun.\n\n"
            "📌 **Quick Hubs & Navigation:**\n"
            "• 📜 <#1545502710101704714> — Server rules, conduct, and safety policy\n"
            "• 🎭 <#1545502722739150898> — Self roles, gaming squads, and theme colors\n"
            "• 🎙️ `➕・𝓒ʀᴇᴀᴛᴇ・𝕽ᴏᴏᴍ` — Instant private & gaming voice lounges\n"
            "• 🛠️ <#1554891396119531602> — Control panel to lock, rename, and manage your VC"
        ),
        color=0x9B59B6,
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(
        text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Autonomous Guide • Stickied Bulletin ✦",
        icon_url=guild.icon.url if guild.icon else None,
    )
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="📜 Rules & Guide", style=discord.ButtonStyle.link, url=f"https://discord.com/channels/{guild.id}/1545502710101704714"))
    view.add_item(discord.ui.Button(label="🎭 Pick Roles", style=discord.ButtonStyle.link, url=f"https://discord.com/channels/{guild.id}/1545502722739150898"))
    view.add_item(discord.ui.Button(label="🛠️ Room Control", style=discord.ButtonStyle.link, url=f"https://discord.com/channels/{guild.id}/1554891396119531602"))
    return embed, view


class WelcomeCog(commands.Cog, name="Welcome"):
    """Welcome, onboarding, and stickied server guidance manager."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # Track message activity in sticky-enabled channels: channel_id -> message count
        self._sticky_channels: Dict[int, int] = {1545502730699808768: 0}  # #general-chat default
        self._sticky_messages: Dict[int, Optional[int]] = {}  # channel_id -> message_id
        self._sticky_lock = asyncio.Lock()

    welcome_group = app_commands.Group(
        name="welcome",
        description="Configure welcome and goodbye system",
        default_permissions=discord.Permissions(administrator=True),
    )

    sticky_group = app_commands.Group(
        name="sticky",
        description="Manage stickied informational banners",
        default_permissions=discord.Permissions(administrator=True),
    )

    # ==========================================
    # LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        guild_cfg = await self.bot.db.get_or_create_guild_config(guild.id)
        if not guild_cfg.welcome_enabled:
            return

        w_cfg = await self.bot.db.get_welcome_config(guild.id)

        # 1. Automatic role assignment if set in welcome_config
        if w_cfg.autorole_id:
            role = guild.get_role(w_cfg.autorole_id)
            if role and guild.me.guild_permissions.manage_roles and role < guild.me.top_role:
                try:
                    await member.add_roles(role, reason="Welcome Autorole")
                except (discord.Forbidden, discord.HTTPException) as e:
                    logger.warning(f"Failed to apply autorole to {member.id}: {e}")

        # 2. Welcome Channel Message
        if w_cfg.welcome_channel_id:
            channel = guild.get_channel(w_cfg.welcome_channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                raw_msg = w_cfg.welcome_message or "Welcome to **{server}**, {user}! We now have **{member_count}** members."
                formatted_msg = format_template(raw_msg, member)

                if w_cfg.embed_enabled:
                    embed = create_embed(
                        title=f"Welcome to {guild.name}!",
                        description=formatted_msg,
                        color=Colors.SUCCESS,
                        thumbnail_url=member.display_avatar.url,
                    )
                    embed.add_field(name="Member #", value=str(guild.member_count), inline=True)
                    embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
                    if guild.icon:
                        embed.set_author(name=guild.name, icon_url=guild.icon.url)
                    try:
                        from utils.role_manager import OnboardingRoleView
                        await channel.send(content=member.mention, embed=embed, view=OnboardingRoleView())
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                else:
                    try:
                        await channel.send(formatted_msg)
                    except (discord.Forbidden, discord.HTTPException):
                        pass

        # 3. Welcome DM
        if w_cfg.dm_enabled and not member.bot:
            try:
                dm_text = format_template(
                    w_cfg.welcome_message or f"Welcome to **{guild.name}**, {member.name}! Glad to have you here.",
                    member,
                )
                await member.send(dm_text)
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        guild_cfg = await self.bot.db.get_or_create_guild_config(guild.id)
        if not guild_cfg.welcome_enabled:
            return

        w_cfg = await self.bot.db.get_welcome_config(guild.id)
        if w_cfg.goodbye_channel_id:
            channel = guild.get_channel(w_cfg.goodbye_channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                raw_msg = w_cfg.goodbye_message or "**{username}** has left the server. We now have **{member_count}** members."
                formatted_msg = format_template(raw_msg, member)

                if w_cfg.embed_enabled:
                    embed = create_embed(
                        title="Goodbye!",
                        description=formatted_msg,
                        color=Colors.DARK,
                        thumbnail_url=member.display_avatar.url,
                    )
                    try:
                        await channel.send(embed=embed)
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                else:
                    try:
                        await channel.send(formatted_msg)
                    except (discord.Forbidden, discord.HTTPException):
                        pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Detect when member passes Discord Membership Screening (Agrees to Rules) and unlock verified roles."""
        if getattr(before, "pending", False) and not getattr(after, "pending", False):
            guild = after.guild
            logger.info(f"Member {after} ({after.id}) agreed to server rules / passed membership screening in {guild.name}")
            
            roles_to_add = []
            
            # 1. Check guild welcome autorole config
            w_cfg = await self.bot.db.get_welcome_config(guild.id)
            if w_cfg and w_cfg.autorole_id:
                auto_role = guild.get_role(w_cfg.autorole_id)
                if auto_role and auto_role not in after.roles and auto_role < guild.me.top_role:
                    roles_to_add.append(auto_role)

            # 2. Known community and verified roles for main server (or by name match)
            verified_role = guild.get_role(1549504522953695269)   # ✨ ┆ VERIFIED MEMBER
            community_role = guild.get_role(1545494584203673740)  # 💖 ┆ RAI FAM
            
            if not verified_role:
                for r in guild.roles:
                    rname = r.name.lower()
                    if "verified" in rname and "member" in rname and r < guild.me.top_role:
                        verified_role = r
                        break
            if not community_role:
                for r in guild.roles:
                    rname = r.name.lower()
                    if ("rai" in rname and "fam" in rname) and r < guild.me.top_role:
                        community_role = r
                        break

            if verified_role and verified_role not in after.roles and verified_role < guild.me.top_role:
                roles_to_add.append(verified_role)
            if community_role and community_role not in after.roles and community_role < guild.me.top_role:
                roles_to_add.append(community_role)

            if roles_to_add:
                try:
                    await after.add_roles(*roles_to_add, reason="Automated Gateway: Agreed to Discord Rules & Passed Screening")
                    logger.info(f"Granted {[r.name for r in roles_to_add]} to {after} after passing screening")
                except Exception as err:
                    logger.warning(f"Failed to grant screening roles to {after}: {err}")

            # 3. Log to Security / Mod Report channel
            try:
                from utils.owner_reporter import OwnerReporter
                OwnerReporter.send_mod_report(
                    self.bot,
                    guild.id,
                    event="Membership Screening Completed",
                    user=after,
                    action_taken=f"Granted verified roles: {', '.join(f'`{r.name}`' for r in roles_to_add)}" if roles_to_add else "Verified standing confirmed",
                    details={
                        "Account Age": discord.utils.format_dt(after.created_at, "R"),
                        "Gate": "Discord Native Rule Agreement",
                    },
                )
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Monitors chat volume in stickied channels and cleanly cycles the navigation banner."""
        if message.author.bot or not message.guild or not isinstance(message.channel, discord.TextChannel):
            return

        if message.channel.id not in self._sticky_channels:
            return

        self._sticky_channels[message.channel.id] += 1
        # Re-post every 7 messages to keep it visible at the bottom of active chat
        if self._sticky_channels[message.channel.id] >= 7:
            await self._refresh_sticky_message(message.channel)

    async def _refresh_sticky_message(self, channel: discord.TextChannel) -> None:
        """Atomically deletes the previous sticky message and re-posts it at the bottom."""
        async with self._sticky_lock:
            self._sticky_channels[channel.id] = 0
            old_msg_id = self._sticky_messages.get(channel.id)
            if old_msg_id:
                try:
                    old_msg = await channel.fetch_message(old_msg_id)
                    await old_msg.delete()
                except Exception:
                    pass

            embed, view = build_sticky_banner(channel.guild)
            try:
                new_msg = await channel.send(embed=embed, view=view)
                self._sticky_messages[channel.id] = new_msg.id
            except Exception as e:
                logger.debug(f"Failed to post sticky banner in #{channel.name}: {e}")

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    @welcome_group.command(name="setup", description="Full setup wizard for welcome and goodbye messages")
    @is_admin_or_owner()
    @app_commands.describe(
        welcome_channel="Channel for welcome messages",
        goodbye_channel="Channel for goodbye messages",
        autorole="Role to automatically assign to new members",
        dm_enabled="Send welcome message as a DM to the user",
        use_embeds="Format welcome and goodbye messages inside embeds",
    )
    async def welcome_setup(
        self,
        interaction: discord.Interaction,
        welcome_channel: Optional[discord.TextChannel] = None,
        goodbye_channel: Optional[discord.TextChannel] = None,
        autorole: Optional[discord.Role] = None,
        dm_enabled: Optional[bool] = None,
        use_embeds: Optional[bool] = None,
    ):
        guild_id = interaction.guild.id
        updates = {}
        if welcome_channel:
            updates["welcome_channel_id"] = welcome_channel.id
        if goodbye_channel:
            updates["goodbye_channel_id"] = goodbye_channel.id
        if autorole:
            updates["autorole_id"] = autorole.id
        if dm_enabled is not None:
            updates["dm_enabled"] = int(dm_enabled)
        if use_embeds is not None:
            updates["embed_enabled"] = int(use_embeds)

        await self.bot.db.update_welcome_config(guild_id, **updates)
        await self.bot.db.update_guild_config(guild_id, welcome_enabled=True)

        embed = success_embed(
            "Welcome System Configured",
            f"**Welcome Channel:** {welcome_channel.mention if welcome_channel else 'Unchanged'}\n"
            f"**Goodbye Channel:** {goodbye_channel.mention if goodbye_channel else 'Unchanged'}\n"
            f"**Autorole:** {autorole.mention if autorole else 'Unchanged'}\n"
            f"**Welcome DM:** {'Enabled' if dm_enabled else 'Disabled' if dm_enabled is not None else 'Unchanged'}\n"
            f"**Embeds:** {'Enabled' if use_embeds else 'Disabled' if use_embeds is not None else 'Unchanged'}",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @welcome_group.command(name="channel", description="Set welcome or goodbye channel")
    @is_admin_or_owner()
    @app_commands.describe(
        channel_type="Which channel to set",
        channel="Target text channel",
    )
    @app_commands.choices(
        channel_type=[
            app_commands.Choice(name="Welcome Channel", value="welcome"),
            app_commands.Choice(name="Goodbye Channel", value="goodbye"),
        ]
    )
    async def welcome_channel(
        self,
        interaction: discord.Interaction,
        channel_type: app_commands.Choice[str],
        channel: discord.TextChannel,
    ):
        if channel_type.value == "welcome":
            await self.bot.db.update_welcome_config(interaction.guild.id, welcome_channel_id=channel.id)
        else:
            await self.bot.db.update_welcome_config(interaction.guild.id, goodbye_channel_id=channel.id)

        await interaction.response.send_message(
            embed=success_embed(f"{channel_type.name} Set", f"Messages will be posted to {channel.mention}."),
            ephemeral=True,
        )

    @welcome_group.command(name="message", description="Customize welcome or goodbye message template")
    @is_admin_or_owner()
    @app_commands.describe(
        message_type="Which message template to edit",
        template="Text template. Variables: {user}, {username}, {server}, {member_count}",
    )
    @app_commands.choices(
        message_type=[
            app_commands.Choice(name="Welcome Message", value="welcome"),
            app_commands.Choice(name="Goodbye Message", value="goodbye"),
        ]
    )
    async def welcome_message(
        self,
        interaction: discord.Interaction,
        message_type: app_commands.Choice[str],
        template: str,
    ):
        if message_type.value == "welcome":
            await self.bot.db.update_welcome_config(interaction.guild.id, welcome_message=template)
        else:
            await self.bot.db.update_welcome_config(interaction.guild.id, goodbye_message=template)

        await interaction.response.send_message(
            embed=success_embed(f"{message_type.name} Updated", f"New template:\n> {template}"),
            ephemeral=True,
        )

    @welcome_group.command(name="role", description="Set or clear the automatic welcome role")
    @is_admin_or_owner()
    @app_commands.describe(role="Role to assign on join (leave empty to clear)")
    async def welcome_role(self, interaction: discord.Interaction, role: Optional[discord.Role] = None):
        role_id = role.id if role else None
        await self.bot.db.update_welcome_config(interaction.guild.id, autorole_id=role_id)
        if role:
            await interaction.response.send_message(
                embed=success_embed("Welcome Role Configured", f"New members will automatically receive {role.mention}."),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=info_embed("Welcome Role Cleared", "New members will not receive an automatic role."),
                ephemeral=True,
            )

    @welcome_group.command(name="test", description="Send a preview test of welcome and goodbye messages")
    @is_admin_or_owner()
    async def welcome_test(self, interaction: discord.Interaction):
        w_cfg = await self.bot.db.get_welcome_config(interaction.guild.id)
        member = interaction.user

        raw_welcome = w_cfg.welcome_message or "Welcome to **{server}**, {user}! We now have **{member_count}** members."
        welcome_text = format_template(raw_welcome, member)

        embed = create_embed(
            title=f"Welcome to {interaction.guild.name}! (TEST PREVIEW)",
            description=welcome_text,
            color=Colors.SUCCESS,
            thumbnail_url=member.display_avatar.url,
        )
        embed.add_field(name="Member #", value=str(interaction.guild.member_count), inline=True)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)

        await interaction.response.send_message(content=f"**[Preview]** Mention: {member.mention}", embed=embed, ephemeral=True)

    @welcome_group.command(name="disable", description="Disable welcome and goodbye messages")
    @is_admin_or_owner()
    async def welcome_disable(self, interaction: discord.Interaction):
        await self.bot.db.update_guild_config(interaction.guild.id, welcome_enabled=False)
        await interaction.response.send_message(
            embed=info_embed("Welcome System Disabled", "Join and leave announcements are now disabled."),
            ephemeral=True,
        )

    # ==========================================
    # STICKY BANNER COMMANDS
    # ==========================================

    @sticky_group.command(name="refresh", description="Immediately refresh the stickied navigation banner in this channel")
    @is_admin_or_owner()
    async def sticky_refresh(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Must be executed in a text channel.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        self._sticky_channels[interaction.channel.id] = 0
        await self._refresh_sticky_message(interaction.channel)
        await interaction.followup.send("✅ Stickied bulletin refreshed at the bottom of this channel.", ephemeral=True)

    @sticky_group.command(name="toggle", description="Toggle stickied navigation banner on or off for this channel")
    @is_admin_or_owner()
    async def sticky_toggle(self, interaction: discord.Interaction):
        ch_id = interaction.channel_id
        if ch_id in self._sticky_channels:
            self._sticky_channels.pop(ch_id, None)
            old_id = self._sticky_messages.pop(ch_id, None)
            if old_id and isinstance(interaction.channel, discord.TextChannel):
                try:
                    m = await interaction.channel.fetch_message(old_id)
                    await m.delete()
                except Exception:
                    pass
            await interaction.response.send_message("❌ Stickied bulletin disabled for this channel.", ephemeral=True)
        else:
            self._sticky_channels[ch_id] = 0
            if isinstance(interaction.channel, discord.TextChannel):
                await self._refresh_sticky_message(interaction.channel)
            await interaction.response.send_message("✅ Stickied bulletin enabled for this channel.", ephemeral=True)


async def setup(bot: SentinelBot):
    await bot.add_cog(WelcomeCog(bot))
