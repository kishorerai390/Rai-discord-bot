"""
Modular Kick Operations for Rai Moderation.
"""

from __future__ import annotations

import logging
from typing import Tuple
import discord

from config.permissions import can_moderate

logger = logging.getLogger("Rai.Moderation.Kick")


class KickService:
    @staticmethod
    async def execute_kick(
        moderator: discord.Member,
        target: discord.Member,
        reason: str,
    ) -> Tuple[bool, str]:
        can_mod, err = can_moderate(moderator, target, target.guild.me)
        if not can_mod:
            return False, err

        try:
            await target.kick(reason=f"{reason} (Kicked by {moderator})")
            return True, f"Successfully kicked {target.mention}."
        except Exception as e:
            return False, str(e)
