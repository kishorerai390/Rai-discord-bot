"""
Autorole Cog.
Automatically assigns a configured role to members when they join the server.
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


class AutoroleCog(commands.Cog, name="Autorole"):
    """Automatic member role assignment on join."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    autorole_group = app_commands.Group(
        name="autorole",
        description="Automatic role assignment for new members",
        default_permissions=discord.Permissions(manage_roles=True),
    )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        guild_cfg = await self.bot.db.get_or_create_guild_config(guild.id)
        if not guild_cfg.autorole_enabled:
            return

        w_cfg = await self.bot.db.get_welcome_config(guild.id)
        if not w_cfg.autorole_id:
            return

        role = guild.get_role(w_cfg.autorole_id)
        if not role:
            return

        # Check permissions & hierarchy
        if not guild.me.guild_permissions.manage_roles or role >= guild.me.top_role:
            logger.warning(f"Cannot assign autorole {role.name} in {guild.name}: hierarchy or permission missing.")
            return

        try:
            await member.add_roles(role, reason="Autorole assignment on join")
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.error(f"Failed to grant autorole to {member.name}: {e}")

    @autorole_group.command(name="set", description="Set the automatic role given to new members upon joining")
    @is_admin_or_owner()
    @app_commands.describe(role="The role to assign")
    async def autorole_set(self, interaction: discord.Interaction, role: discord.Role):
        guild = interaction.guild
        if role >= guild.me.top_role:
            await interaction.response.send_message(
                embed=error_embed("Hierarchy Error", f"The role {role.mention} is higher than or equal to my highest role ({guild.me.top_role.mention}). I cannot assign it."),
                ephemeral=True,
            )
            return

        if role.is_default() or role.managed:
            await interaction.response.send_message(
                embed=error_embed("Invalid Role", "Cannot assign @everyone or integration-managed roles."),
                ephemeral=True,
            )
            return

        await self.bot.db.update_welcome_config(guild.id, autorole_id=role.id)
        await self.bot.db.update_guild_config(guild.id, autorole_enabled=True)
        await interaction.response.send_message(
            embed=success_embed("Autorole Configured", f"New members will now automatically be assigned {role.mention}."),
            ephemeral=True,
        )

    @autorole_group.command(name="remove", description="Disable and remove the configured autorole")
    @is_admin_or_owner()
    async def autorole_remove(self, interaction: discord.Interaction):
        await self.bot.db.update_welcome_config(interaction.guild.id, autorole_id=None)
        await self.bot.db.update_guild_config(interaction.guild.id, autorole_enabled=False)
        await interaction.response.send_message(
            embed=info_embed("Autorole Disabled", "New members will no longer automatically receive a role."),
            ephemeral=True,
        )

    @autorole_group.command(name="status", description="Display current autorole status")
    async def autorole_status(self, interaction: discord.Interaction):
        guild = interaction.guild
        guild_cfg = await self.bot.db.get_or_create_guild_config(guild.id)
        w_cfg = await self.bot.db.get_welcome_config(guild.id)

        role = guild.get_role(w_cfg.autorole_id) if w_cfg.autorole_id else None
        role_str = role.mention if role else "*None configured*"

        embed = create_embed(
            title=f"🎭 Autorole Status — {guild.name}",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="Status", value="🟢 Enabled" if guild_cfg.autorole_enabled and role else "🔴 Disabled", inline=True)
        embed.add_field(name="Target Role", value=role_str, inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: SentinelBot):
    await bot.add_cog(AutoroleCog(bot))
