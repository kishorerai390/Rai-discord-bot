"""
Modular Ban and Unban Operations for Rai Moderation.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple
import discord

from config.permissions import can_moderate

logger = logging.getLogger("Rai.Moderation.Ban")


class BanService:
    @staticmethod
    async def execute_ban(
        moderator: discord.Member,
        target: discord.Member,
        reason: str,
        delete_message_days: int = 1,
    ) -> Tuple[bool, str]:
        """Validates hierarchy and bans the target member."""
        can_mod, err = can_moderate(moderator, target, target.guild.me)
        if not can_mod:
            return False, err

        delete_seconds = min(7, max(0, delete_message_days)) * 86400
        try:
            await target.ban(reason=f"{reason} (Banned by {moderator})", delete_message_seconds=delete_seconds)
            return True, f"Successfully banned {target.mention}."
        except Exception as e:
            return False, str(e)

    @staticmethod
    async def execute_unban(
        guild: discord.Guild,
        moderator: discord.Member,
        user_id: int,
        reason: str,
    ) -> Tuple[bool, str]:
        user_obj = discord.Object(id=user_id)
        try:
            await guild.unban(user_obj, reason=f"{reason} (Unbanned by {moderator})")
            return True, f"Successfully unbanned user ID `{user_id}`."
        except discord.NotFound:
            return False, "User is not banned or does not exist."
        except Exception as e:
            return False, str(e)
