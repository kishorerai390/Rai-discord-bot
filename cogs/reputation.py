"""
Reputation: ensure before_loop uses canonical await.
"""
from __future__ import annotations

from discord.ext import tasks, commands
import logging

logger = logging.getLogger("Rai.Reputation")

class ReputationCog(commands.Cog, name="Reputation"):
    def __init__(self, bot: "SentinelBot"):
        self.bot = bot
        self.voice_xp_loop.start()

    @tasks.loop(minutes=2)
    async def voice_xp_loop(self):
        # body omitted
        return

    @voice_xp_loop.before_loop
    async def before_voice_xp(self):
        try:
            await self.bot.wait_until_ready()
        except Exception:
            pass
