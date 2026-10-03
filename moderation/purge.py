"""
Modular Message Purge and Bulk Deletion Service for Rai.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple
import discord

logger = logging.getLogger("Rai.Moderation.Purge")


class PurgeService:
    @staticmethod
    async def purge_channel(
        channel: discord.TextChannel,
        limit: int = 10,
        user: Optional[discord.Member | discord.User] = None,
    ) -> Tuple[int, str]:
        if limit < 1 or limit > 100:
            return 0, "Limit must be between 1 and 100."

        def check(m: discord.Message) -> bool:
            if user:
                return m.author.id == user.id
            return True

        try:
            deleted = await channel.purge(limit=limit, check=check)
            return len(deleted), f"Successfully purged {len(deleted)} message(s)."
        except Exception as e:
            return 0, str(e)
