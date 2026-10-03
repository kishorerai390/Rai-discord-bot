"""
Server Branding and Cyberpunk Structure Setup Cog for 『RΛI』.
Provides:
- /rai setup preview (Dry-run server inspection)
- /rai setup apply (Explicit confirmation deployment)
- /rai setup status (Current alignment audit)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from config.settings import Colors, Branding
from utils.branding import ServerBrandingManager, ServerStructurePlan
from utils.embeds import (
    create_embed,
    error_embed,
    info_embed,
    success_embed,
    warning_embed,
    DEFAULT_BRAND,
    DEFAULT_FOOTER,
)
from utils.interaction_reliability import safe_defer, safe_response
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger("Rai.ServerBrandingCog")


class SetupConfirmationView(discord.ui.View):
    """Interactive confirmation view requiring explicit admin approval before modifying server structure."""

    def __init__(self, cog: "ServerBrandingCog", plan: ServerStructurePlan, author: discord.Member):
        super().__init__(timeout=120.0)
        self.cog = cog
        self.plan = plan
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                embed=error_embed("Access Denied", "Only the initiating administrator can confirm this operation."),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Deploy Structure", style=discord.ButtonStyle.success, emoji="⚡", custom_id="btn_deploy_structure")
    async def confirm_deploy(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        bot_member = interaction.guild.me
        results = await ServerBrandingManager.apply_plan(interaction.guild, self.plan, bot_member)

        embed = create_embed(
            title=f"{DEFAULT_BRAND} • STRUCTURE DEPLOYED",
            color=Colors.SUCCESS,
            description=(
                f"✅ **Cyberpunk Server Architecture Deployed Successfully!**\n\n"
                f"• **Categories Created:** `{results['categories_created']}`\n"
                f"• **Channels Created:** `{results['channels_created']}`\n"
                f"• **Roles Created:** `{results['roles_created']}`\n"
                f"• **Existing Permissions:** *100% Preserved*\n\n"
                f"*Channels and categories are now aligned with the 『RΛI』 standard.*"
            ),
        )
        if results["errors"]:
            embed.add_field(
                name="⚠️ Notices",
                value="\n".join(f"• {e}" for e in results["errors"][:5]),
                inline=False,
            )

        await interaction.followup.send(embed=embed)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️", custom_id="btn_cancel_structure")
    async def cancel_deploy(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"> ⚠️ **Deployment Cancelled.** No server channels or roles were modified.",
            view=self,
        )


class ServerBrandingCog(commands.Cog, name="ServerBranding"):
    """Futuristic Cyberpunk Server Architecture and Branding Controls."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    setup_group = app_commands.Group(
        name="setup",
        description="『RΛI』 Futuristic Cyberpunk server structure and branding controls",
    )

    @setup_group.command(name="preview", description="Perform a safe dry-run preview of planned categories, channels, and roles")
    @is_admin_or_owner()
    async def setup_preview(self, interaction: discord.Interaction, include_voice: bool = False):
        """Dry-run inspection of server categories, channels, and roles."""
        await safe_defer(interaction, ephemeral=True)

        plan = ServerBrandingManager.generate_plan(interaction.guild, include_voice=include_voice)
        embed = ServerBrandingManager.format_plan_embed(plan)
        view = SetupConfirmationView(self, plan, interaction.user)

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @setup_group.command(name="apply", description="Apply the 『RΛI』 server structure after confirmation")
    @is_admin_or_owner()
    async def setup_apply(self, interaction: discord.Interaction, include_voice: bool = False):
        """Applies server categories, channels, and roles after explicit confirmation."""
        await safe_defer(interaction, ephemeral=True)

        plan = ServerBrandingManager.generate_plan(interaction.guild, include_voice=include_voice)
        embed = ServerBrandingManager.format_plan_embed(plan)
        view = SetupConfirmationView(self, plan, interaction.user)

        await interaction.followup.send(
            content="⚠️ **Administrator Confirmation Required**: Verify the structure preview below before clicking Deploy.",
            embed=embed,
            view=view,
            ephemeral=True,
        )

    @setup_group.command(name="status", description="Audit current server alignment with the 『RΛI』 branding standard")
    @is_admin_or_owner()
    async def setup_status(self, interaction: discord.Interaction):
        """Audits current server alignment."""
        await safe_defer(interaction, ephemeral=True)

        plan = ServerBrandingManager.generate_plan(interaction.guild, include_voice=True)

        total_cat = len(plan.categories_to_create)
        total_ch = len(plan.channels_to_create)
        total_roles = len(plan.roles_to_create)

        is_aligned = (total_cat == 0 and total_ch == 0 and total_roles == 0)

        embed = create_embed(
            title=f"{DEFAULT_BRAND} • SERVER ALIGNMENT STATUS",
            color=Colors.SUCCESS if is_aligned else Colors.CYBER_CYAN,
            description=(
                f"**Guild:** `{interaction.guild.name}`\n"
                f"**Overall Alignment:** {'🟢 FULLY ALIGNED' if is_aligned else '🟡 PARTIAL ALIGNMENT'}\n\n"
                f"• Missing Categories: `{total_cat}`\n"
                f"• Missing Channels: `{total_ch}`\n"
                f"• Missing Roles: `{total_roles}`\n\n"
                f"*Use `/setup preview` to inspect missing channels or `/setup apply` to deploy.*"
            ),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==========================================
    # PREFIX COMMANDS (Direct fallback for !setup & !deploy)
    # ==========================================

    @commands.group(name="setup", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def prefix_setup(self, ctx: commands.Context):
        """Prefix command for server structure setup (!setup preview or !setup apply)."""
        plan = ServerBrandingManager.generate_plan(ctx.guild, include_voice=True)
        embed = ServerBrandingManager.format_plan_embed(plan)
        view = SetupConfirmationView(self, plan, ctx.author)
        await ctx.reply(
            content="⚠️ **Administrator Confirmation Required**: Click **Deploy Structure** below to apply the cyberpunk architecture.",
            embed=embed,
            view=view,
        )

    @prefix_setup.command(name="preview")
    @commands.has_permissions(administrator=True)
    async def prefix_setup_preview(self, ctx: commands.Context, include_voice: bool = True):
        """Preview planned categories, channels, and roles (!setup preview)."""
        plan = ServerBrandingManager.generate_plan(ctx.guild, include_voice=include_voice)
        embed = ServerBrandingManager.format_plan_embed(plan)
        view = SetupConfirmationView(self, plan, ctx.author)
        await ctx.reply(embed=embed, view=view)

    @prefix_setup.command(name="apply")
    @commands.has_permissions(administrator=True)
    async def prefix_setup_apply(self, ctx: commands.Context, include_voice: bool = True):
        """Apply server structure with interactive confirmation (!setup apply)."""
        plan = ServerBrandingManager.generate_plan(ctx.guild, include_voice=include_voice)
        embed = ServerBrandingManager.format_plan_embed(plan)
        view = SetupConfirmationView(self, plan, ctx.author)
        await ctx.reply(
            content="⚠️ **Administrator Confirmation Required**: Click **Deploy Structure** below to apply the cyberpunk architecture.",
            embed=embed,
            view=view,
        )

    @commands.command(name="deploy")
    @commands.has_permissions(administrator=True)
    async def prefix_deploy(self, ctx: commands.Context, include_voice: bool = True):
        """Direct shortcut (!deploy) to deploy server structure."""
        plan = ServerBrandingManager.generate_plan(ctx.guild, include_voice=include_voice)
        embed = ServerBrandingManager.format_plan_embed(plan)
        view = SetupConfirmationView(self, plan, ctx.author)
        await ctx.reply(
            content="⚠️ **Administrator Confirmation Required**: Click **Deploy Structure** below to deploy the cyberpunk server architecture.",
            embed=embed,
            view=view,
        )

    # ==========================================
    # AUTO-STRUCTURE EVENT LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Auto-provisions structure on guild join if AUTO_STRUCTURE is enabled."""
        if getattr(Branding, "AUTO_STRUCTURE", False):
            logger.info(f"Auto-provisioning server structure on guild join for {guild.name} ({guild.id})...")
            plan = ServerBrandingManager.generate_plan(guild, include_voice=True)
            bot_member = guild.me
            results = await ServerBrandingManager.apply_plan(guild, plan, bot_member)
            logger.info(f"Auto-provision results for {guild.name}: {results}")

    @commands.Cog.listener()
    async def on_ready(self):
        """Ensures connected guilds have structure deployed if AUTO_STRUCTURE is enabled."""
        if getattr(Branding, "AUTO_STRUCTURE", False):
            for guild in self.bot.guilds:
                plan = ServerBrandingManager.generate_plan(guild, include_voice=True)
                if plan.categories_to_create or plan.channels_to_create or plan.roles_to_create:
                    logger.info(f"Auto-deploying structure for guild {guild.name} ({guild.id})...")
                    bot_member = guild.me
                    results = await ServerBrandingManager.apply_plan(guild, plan, bot_member)
                    logger.info(f"Auto-deploy results for {guild.name}: {results}")


async def setup(bot: SentinelBot):
    await bot.add_cog(ServerBrandingCog(bot))
