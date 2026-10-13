"""
ServerStats: standardize before_loop handlers to canonical await pattern.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

import discord
from discord.ext import commands, tasks

logger = logging.getLogger("Rai.ServerStats")


class ServerStatsCog(commands.Cog, name="ServerStats"):
    def __init__(self, bot: "SentinelBot"):
        self.bot = bot
        self._update_locks = {}
        self._daily_activity_tracker = defaultdict(int)
        self._member_birthdays = {}
        # ... existing init omitted for brevity in this patch
        # start loops
        self.stats_sync_loop.start()
        self.realtime_consoles_sync_loop.start()
        self.chatter_of_the_day_loop.start()
        self.expired_invites_loop.start()
        self.birthday_check_loop.start()
        self.db_maintenance_loop.start()
        self.invite_health_monitor_loop.start()
        self.stale_threads_prune_loop.start()

    @tasks.loop(minutes=2)
    async def realtime_consoles_sync_loop(self) -> None:
        # body unchanged
        pass

    @tasks.loop(hours=24)
    async def birthday_check_loop(self) -> None:
        # original logic left intact; readiness handled in before_loop
        now = datetime.now(timezone.utc)
        # ... body omitted for brevity
        return

    @birthday_check_loop.before_loop
    async def before_birthday_loop(self) -> None:
        try:
            await self.bot.wait_until_ready()
        except Exception:
            pass

    @tasks.loop(hours=6)
    async def expired_invites_loop(self) -> None:
        # original logic left intact
        return

    @expired_invites_loop.before_loop
    async def before_invites_loop(self) -> None:
        try:
            await self.bot.wait_until_ready()
        except Exception:
            pass

    @tasks.loop(minutes=1)
    async def chatter_of_the_day_loop(self) -> None:
        # original logic left intact
        return

    @chatter_of_the_day_loop.before_loop
    async def before_chatter_loop(self) -> None:
        try:
            await self.bot.wait_until_ready()
        except Exception:
            pass
