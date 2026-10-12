"""
Security Plugin Management Cog.
Provides slash commands (/plugin list, info, reload, toggle) and dispatches lifecycle events.
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

logger = logging.getLogger("Sentinel.Cogs.Plugins")


class PluginsCog(commands.Cog, name="Plugins"):
    """Modular Security Plugin Manager."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    async def cog_load(self) -> None:
        """Initialize plugin engine if not already created and load all plugins."""
        if not hasattr(self.bot, "plugin_engine"):
            from core.plugin_engine import SecurityPluginEngine
            self.bot.plugin_engine = SecurityPluginEngine(self.bot)

        await self.bot.plugin_engine.load_all()

    # =========================================================================
    # EVENT DISPATCHERS
    # =========================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Dispatch incoming messages to security plugin chain."""
        if hasattr(self.bot, "plugin_engine"):
            await self.bot.plugin_engine.dispatch_message(message)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Dispatch member joins to security plugin chain."""
        if hasattr(self.bot, "plugin_engine"):
            await self.bot.plugin_engine.dispatch_member_join(member)

    # =========================================================================
    # SLASH COMMANDS (/PLUGIN)
    # =========================================================================

    plugin_group = app_commands.Group(
        name="plugin",
        description="Manage Sentinel security extensions and modular plugins",
        default_permissions=discord.Permissions(administrator=True),
    )

    @plugin_group.command(name="list", description="List all registered security plugins")
    async def plugin_list(self, interaction: discord.Interaction) -> None:
        """Display loaded plugins and their health status."""
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
            return

        engine = getattr(self.bot, "plugin_engine", None)
        if not engine:
            await interaction.response.send_message("⚠️ Plugin engine is not initialized.", ephemeral=True)
            return

        metrics = engine.get_all_metrics()
        if not metrics:
            embed = info_embed(
                "🧩 Security Plugins",
                "No plugins are currently registered in `security_plugins/`.",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = create_embed(
            title="🧩 Sentinel Security Plugin Registry",
            description=f"Managing **{len(metrics)}** active security modules with dynamic lifecycle hooks.",
            color=Colors.PRIMARY,
        )

        for m in metrics:
            status_icon = "🟢 ACTIVE" if m["enabled"] else "🔴 DISABLED"
            uptime_min = m["uptime_seconds"] // 60
            embed.add_field(
                name=f"{m['name']} `v{m['version']}` [{status_icon}]",
                value=(
                    f"**Author:** {m['author']}\n"
                    f"**Desc:** {m['description']}\n"
                    f"**Events Intercepted:** `{m['intercept_count']}` | **Errors:** `{m['error_count']}`\n"
                    f"**Uptime:** `{uptime_min}m`"
                ),
                inline=False,
            )

        embed.set_footer(text="Use /plugin reload <name> to hot-reload code without restarting.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @plugin_group.command(name="info", description="View detailed telemetry for a specific plugin")
    @app_commands.describe(name="Name of the plugin")
    async def plugin_info(self, interaction: discord.Interaction, name: str) -> None:
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
            return

        engine = getattr(self.bot, "plugin_engine", None)
        if not engine or name not in engine.plugins:
            await interaction.response.send_message(f"❌ Plugin `{name}` not found in registry.", ephemeral=True)
            return

        plugin = engine.plugins[name]
        m = plugin.get_metrics()

        embed = create_embed(
            title=f"🧩 Plugin Telemetry: {plugin.name}",
            description=plugin.description,
            color=Colors.SUCCESS if plugin.enabled else Colors.ERROR,
        )
        embed.add_field(name="Status", value="🟢 Enabled" if plugin.enabled else "🔴 Disabled", inline=True)
        embed.add_field(name="Version", value=f"`v{plugin.version}`", inline=True)
        embed.add_field(name="Author", value=plugin.author, inline=True)
        embed.add_field(name="Events Processed", value=f"`{m['events_processed']}`", inline=True)
        embed.add_field(name="Threats Intercepted", value=f"`{m['intercept_count']}`", inline=True)
        embed.add_field(name="Errors Trapped", value=f"`{m['error_count']}`", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @plugin_group.command(name="toggle", description="Enable or disable a security plugin")
    @app_commands.describe(name="Name of the plugin")
    async def plugin_toggle(self, interaction: discord.Interaction, name: str) -> None:
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
            return

        engine = getattr(self.bot, "plugin_engine", None)
        if not engine or name not in engine.plugins:
            await interaction.response.send_message(f"❌ Plugin `{name}` not found.", ephemeral=True)
            return

        plugin = engine.plugins[name]
        plugin.enabled = not plugin.enabled
        new_state = "enabled" if plugin.enabled else "disabled"

        embed = success_embed(
            "Plugin Updated",
            f"Plugin **{plugin.name}** has been **{new_state}**.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @plugin_group.command(name="reload", description="Hot-reload a security plugin code from disk")
    @app_commands.describe(name="Name of the plugin file (without .py)")
    async def plugin_reload(self, interaction: discord.Interaction, name: str) -> None:
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
            return

        engine = getattr(self.bot, "plugin_engine", None)
        if not engine:
            await interaction.response.send_message("⚠️ Plugin engine not initialized.", ephemeral=True)
            return

        success = await engine.reload_plugin(name)
        if success:
            embed = success_embed(
                "Plugin Reloaded",
                f"Successfully hot-reloaded plugin **{name}** from disk with zero downtime! ⚡",
            )
        else:
            embed = error_embed(
                "Reload Failed",
                f"Failed to reload plugin **{name}**. Check server console logs for details.",
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: SentinelBot) -> None:
    await bot.add_cog(PluginsCog(bot))
