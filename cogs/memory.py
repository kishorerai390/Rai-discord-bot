"""
RAI — SERVER MEMORY & PROFILE COG.
Provides:
- /rai context: View current server memory & temporary conversation context
- /rai remember: Save server-scoped preferences, schedules, channel purposes, or templates
- /rai forget: Remove remembered operational data
- /rai profile: Server Profile configuration (Server type, automation level, security level)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from core.memory import MemoryService
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.MemoryCog")


class MemoryCog(commands.Cog, name="Memory"):
    """Server Memory and Profile Management."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    rai_group = app_commands.Group(name="rai", description="Rai server memory and profile configuration")

    @rai_group.command(name="context", description="View active server memory context and current conversation session")
    async def context_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("❌ Guild context required.", ephemeral=True)
            return

        memories = await MemoryService.list_memories(self.bot, interaction.guild.id)
        embed = create_embed(
            title=f"🧠 RAI Server Context — {interaction.guild.name}",
            description=f"Persistent operational memories stored for this server (**{len(memories)}** items):",
            color=Colors.PRIMARY,
        )

        if memories:
            for m in memories[:15]:
                cat = f"[{m['category'].upper()}]" if m.get("category") else ""
                val_preview = m['memory_value'][:80] + ("..." if len(m['memory_value']) > 80 else "")
                embed.add_field(name=f"🔑 {m['memory_key']} {cat}", value=val_preview, inline=False)
        else:
            embed.description = "No operational memory stored yet. Teach Rai with `/rai remember <key> <value>`!"

        embed.set_footer(text="Memory is strictly isolated to this server and never leaks.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @rai_group.command(name="remember", description="Store a server preference, operational rule, or schedule in Rai's memory")
    @app_commands.describe(
        key="The topic or identifier (e.g. 'movie_night', 'rules_channel', 'tournament_day')",
        value="The content or instruction to remember",
        category="Category tag (e.g. 'events', 'operations', 'rooms', 'rules')",
    )
    async def remember_cmd(
        self,
        interaction: discord.Interaction,
        key: str,
        value: str,
        category: Optional[str] = "general",
    ):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("❌ Guild context required.", ephemeral=True)
            return

        if not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only administrators and server managers can configure server memory.", ephemeral=True)
            return

        await MemoryService.remember(
            bot=self.bot,
            guild_id=interaction.guild.id,
            key=key,
            value=value,
            category=category or "general",
            created_by=interaction.user.id,
        )

        embed = success_embed(
            title="🧠 Memory Saved",
            description=f"Rai will remember:\n\n**Key:** `{key.strip().lower()}`\n**Value:** {value}\n**Category:** `{category}`",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @rai_group.command(name="forget", description="Remove an item from Rai's server memory")
    @app_commands.describe(key="The key identifier to delete")
    async def forget_cmd(self, interaction: discord.Interaction, key: str):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("❌ Guild context required.", ephemeral=True)
            return

        if not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only administrators and server managers can delete server memory.", ephemeral=True)
            return

        deleted = await MemoryService.forget(self.bot, interaction.guild.id, key)
        if deleted:
            await interaction.followup.send(f"✅ Removed `{key}` from Rai's server memory.", ephemeral=True)
        else:
            await interaction.followup.send(f"ℹ️ Key `{key}` was not found in server memory.", ephemeral=True)

    @rai_group.command(name="profile", description="View or edit the server Rai operational profile")
    @app_commands.describe(
        action="Profile action (view, edit, reset)",
        server_type="Server style (Community, Gaming, Creator, Studio)",
        automation_level="Automation tier (LOW, MEDIUM, HIGH)",
        security_level="Security tier (STANDARD, HIGH, MAXIMUM)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="View Profile", value="view"),
            app_commands.Choice(name="Edit Profile", value="edit"),
            app_commands.Choice(name="Reset Profile", value="reset"),
        ],
        automation_level=[
            app_commands.Choice(name="High (Full Auto)", value="HIGH"),
            app_commands.Choice(name="Medium (Semi-Auto)", value="MEDIUM"),
            app_commands.Choice(name="Low (Assisted Only)", value="LOW"),
        ],
        security_level=[
            app_commands.Choice(name="Maximum Security", value="MAXIMUM"),
            app_commands.Choice(name="High Defense", value="HIGH"),
            app_commands.Choice(name="Standard Defense", value="STANDARD"),
        ],
    )
    async def profile_cmd(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        server_type: Optional[str] = None,
        automation_level: Optional[app_commands.Choice[str]] = None,
        security_level: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("❌ Guild context required.", ephemeral=True)
            return

        guild_id = interaction.guild.id

        if action.value == "reset":
            if not is_admin_or_owner(interaction.user):
                await interaction.followup.send("❌ Only administrators can reset the server profile.", ephemeral=True)
                return
            await self.bot.db._db.execute("DELETE FROM server_profiles WHERE guild_id = ?", (guild_id,))
            await self.bot.db._db.commit()
            profile = await self.bot.db.get_server_profile(guild_id)
            await interaction.followup.send("🔄 Server profile reset to defaults.", ephemeral=True)
            return

        if action.value == "edit":
            if not is_admin_or_owner(interaction.user):
                await interaction.followup.send("❌ Only administrators can edit the server profile.", ephemeral=True)
                return
            current = await self.bot.db.get_server_profile(guild_id)
            new_type = server_type or current["server_type"]
            new_auto = automation_level.value if automation_level else current["automation_level"]
            new_sec = security_level.value if security_level else current["security_level"]
            profile = await self.bot.db.upsert_server_profile(
                guild_id=guild_id,
                server_type=new_type,
                automation_level=new_auto,
                security_level=new_sec,
                modules_enabled=current.get("modules_enabled", {}),
            )
            await interaction.followup.send("✅ Server profile updated.", ephemeral=True)
            return

        # View profile
        profile = await self.bot.db.get_server_profile(guild_id)
        embed = create_embed(
            title=f"👑 RAI SERVER PROFILE — {interaction.guild.name}",
            description=(
                f"**Server Type:** `{profile['server_type']}`\n"
                f"**Automation Level:** `{profile['automation_level']}`\n"
                f"**Security Level:** `{profile['security_level']}`\n\n"
                f"**Active Subsystems:**\n"
                f"• Dynamic Rooms: `ENABLED 🟢`\n"
                f"• Music: `ENABLED 🟢`\n"
                f"• Events: `ENABLED 🟢`\n"
                f"• Collaboration Projects: `ENABLED 🟢`\n"
                f"• Reputation: `ENABLED 🟢`\n"
                f"• Natural Language: `ENABLED 🟢`\n"
                f"• Analytics: `ENABLED 🟢`"
            ),
            color=Colors.PRIMARY,
        )
        embed.set_footer(text="Profiles are strictly scoped per-guild.")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: SentinelBot):
    await bot.add_cog(MemoryCog(bot))
