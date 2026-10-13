"""
System upgrade: canonicalize before loop.
"""
from __future__ import annotations

from discord.ext import tasks, commands
import logging

logger = logging.getLogger("Rai.SystemUpgrade")

class SystemUpgradeCog(commands.Cog, name="SystemUpgrade"):
    def __init__(self, bot: "SentinelBot"):
        self.bot = bot
        self.live_billboard_loop.start()

    @tasks.loop(seconds=60.0)
    async def live_billboard_loop(self):
        # body omitted
        return

    @live_billboard_loop.before_loop
    async def before_billboard(self):
        try:
            await self.bot.wait_until_ready()
        except Exception:
            pass
