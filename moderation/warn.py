"""
Modular Warning System with SQLite Persistence for Rai Moderation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional
import discord

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.Moderation.Warn")


class WarnService:
    @staticmethod
    async def add_warn(
        bot: SentinelBot,
        guild_id: int,
        target_id: int,
        moderator_id: int,
        reason: str,
    ) -> int:
        return await bot.db.add_warning(guild_id, target_id, moderator_id, reason)

    @staticmethod
    async def get_warns(
        bot: SentinelBot,
        guild_id: int,
        target_id: int,
    ):
        return await bot.db.get_warnings(guild_id, target_id)

    @staticmethod
    async def clear_warns(
        bot: SentinelBot,
        guild_id: int,
        target_id: int,
    ) -> int:
        return await bot.db.clear_warnings(guild_id, target_id)
