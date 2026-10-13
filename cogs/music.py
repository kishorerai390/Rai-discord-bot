"""
Music cog: canonicalize watchdog before_loop readiness wait.
"""
from __future__ import annotations

from discord.ext import tasks, commands
import logging

logger = logging.getLogger("Rai.MusicCog")

class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot: "SentinelBot"):
        self.bot = bot
        # start loops
        self._music_watchdog.start()

    @tasks.loop(seconds=20.0)
    async def _music_watchdog(self):
        # body omitted
        return

    @_music_watchdog.before_loop
    async def _before_watchdog(self):
        try:
            await self.bot.wait_until_ready()
        except Exception:
            pass
