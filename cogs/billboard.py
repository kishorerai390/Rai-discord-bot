"""
Server Billboard Cog for RAI Discord Bot.
Provides the /billboard slash command group and manages autonomous live server status embeds.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from utils.server_billboard import ServerBillboardCog

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.BillboardCog")


async def setup(bot: "SentinelBot") -> None:
    await bot.add_cog(ServerBillboardCog(bot))
    logger.info("ServerBillboardCog registered successfully.")
