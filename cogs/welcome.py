"""
Customizable Welcome & Goodbye System.
Supports templates, member count formatting, avatar embeds, autorole, DMs, and test previews.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
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


class WelcomeCog(commands.Cog, name="Welcome"):
    """Welcome and goodbye message manager."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    welcome_group = app_commands.Group(
        name="welcome",
        description="Configure welcome and goodbye system",
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


async def setup(bot: SentinelBot):
    await bot.add_cog(WelcomeCog(bot))
