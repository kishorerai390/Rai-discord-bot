"""
Utility cog: small cleanup for before_loop handling to use canonical await self.bot.wait_until_ready()
"""

from __future__ import annotations

import asyncio
import inspect
import time
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.owner_reporter import OwnerReporter
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.UtilityCog")


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(HelpCategorySelect())


class UtilityCog(commands.Cog, name="Utility"):
    """Server information, diagnostics, and utilities."""

    info_group = app_commands.Group(name="info", description="Server, user, role, and channel information")

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.start_time = time.time()
        self._afk_users: dict[tuple[int, int], tuple[str, float]] = {}
        self._status_index: int = 0

    async def cog_load(self):
        if not self._rotate_presence.is_running():
            self._rotate_presence.start()

    def cog_unload(self):
        if self._rotate_presence.is_running():
            self._rotate_presence.cancel()

    @tasks.loop(minutes=3)
    async def _rotate_presence(self):
        """Auto-Rotating Bot Rich Presence."""
        # The readiness wait is performed in the before_loop handler.
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
        # Canonical, simple wait to avoid un-awaited coroutine variants.
        try:
            await self.bot.wait_until_ready()
        except Exception:
            # If wait fails for any reason, allow the loop to continue startup attempts.
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
