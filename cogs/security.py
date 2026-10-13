"""
Security: canonicalize nightly backup before_loop readiness wait.
"""
from __future__ import annotations

import logging
from discord.ext import tasks, commands

logger = logging.getLogger("Rai.Security")

class SecurityCog(commands.Cog, name="Security"):
    def __init__(self, bot: "SentinelBot"):
        self.bot = bot
        self._nightly_backup_loop.start()

    @tasks.loop(hours=6)
    async def _nightly_backup_loop(self):
        # main backup logic omitted
        return

    @_nightly_backup_loop.before_loop
    async def before_nightly_backup(self):
        try:
            await self.bot.wait_until_ready()
        except Exception:
            pass
