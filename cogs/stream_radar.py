"""
Stream Radar: canonical before_loop.
"""

from __future__ import annotations

import logging
import asyncio
import aiohttp
from discord.ext import tasks

logger = logging.getLogger("Rai.StreamRadar")

class StreamRadarCog(commands.Cog, name="Stream Radar"):
    def __init__(self, bot: "SentinelBot"):
        self.bot = bot
        self.radar_loop.start()

    @tasks.loop(minutes=3)
    async def radar_loop(self):
        # body omitted for brevity
        return

    @radar_loop.before_loop
    async def before_radar_loop(self):
        try:
            await self.bot.wait_until_ready()
        except Exception:
            pass
