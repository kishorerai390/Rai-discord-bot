"""
Modular Timeout and Untimeout Operations for Rai Moderation.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional, Tuple
import discord

from config.permissions import can_moderate

logger = logging.getLogger("Rai.Moderation.Timeout")


class TimeoutService:
    @staticmethod
    async def execute_timeout(
        moderator: discord.Member,
        target: discord.Member,
        seconds: int,
        reason: str,
    ) -> Tuple[bool, str]:
        can_mod, err = can_moderate(moderator, target, target.guild.me)
        if not can_mod:
            return False, err

        if seconds < 10 or seconds > (28 * 86400):
            return False, "Duration must be between 10 seconds and 28 days."

        until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
        try:
            await target.timeout(until, reason=f"{reason} (Timed out by {moderator})")
            return True, f"Successfully timed out {target.mention}."
        except Exception as e:
            return False, str(e)

    @staticmethod
    async def execute_untimeout(
        moderator: discord.Member,
        target: discord.Member,
        reason: str,
    ) -> Tuple[bool, str]:
        can_mod, err = can_moderate(moderator, target, target.guild.me)
        if not can_mod:
            return False, err

        try:
            await target.timeout(None, reason=f"{reason} (Untimed out by {moderator})")
            return True, f"Successfully removed timeout for {target.mention}."
        except Exception as e:
            return False, str(e)
