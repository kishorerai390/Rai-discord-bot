"""
Automated Moderation (AutoMod) Rule Engine.
Evaluates incoming chat messages and applies configured actions:
- Delete message
- Log warning
- Apply automatic timeout (10m, 1h)
- Escalating penalties
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Optional, Tuple
import discord

from security.antispam import ContentInspector

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.AutoMod")


class AutoModEnforcer:
    def __init__(self, bot: SentinelBot):
        self.bot = bot

    async def enforce(
        self,
        message: discord.Message,
        reason: str,
        action: str = "timeout",
        timeout_minutes: int = 10,
    ) -> Tuple[str, str]:
        """
        Executes configured penalty and returns (action_word, summary).
        """
        member = message.author
        if not isinstance(member, discord.Member):
            return "FLAGGED", "Non-member author"

        # 1. Delete message
        try:
            await message.delete()
        except Exception:
            pass

        action_word = "MUTED"
        punishment_str = f"Deleted Message + {timeout_minutes}m Timeout"

        # 2. Apply punishment
        if action == "timeout":
            try:
                until = discord.utils.utcnow() + datetime.timedelta(minutes=timeout_minutes)
                await member.timeout(until, reason=f"AutoMod: {reason}")
                action_word = "MUTED"
            except Exception as e:
                logger.warning(f"Could not timeout {member.name}: {e}")
                action_word = "FLAGGED"
                punishment_str = "Deleted Message (Timeout failed: Bot hierarchy)"
        elif action == "kick":
            try:
                await member.kick(reason=f"AutoMod: {reason}")
                action_word = "KICKED"
                punishment_str = "Kicked from Server"
            except Exception:
                action_word = "FLAGGED"
        elif action == "warn":
            await self.bot.db.add_warning(message.guild.id, member.id, self.bot.user.id, f"AutoMod: {reason}")
            action_word = "WARNED"
            punishment_str = "Deleted Message + Logged Warning"
        else:
            action_word = "REMOVED"
            punishment_str = "Deleted Message Only"

        # 3. Public notification
        try:
            await message.channel.send(
                f"🚫 **{member.name}** was **{action_word}** by AutoMod ({reason}).",
                delete_after=10.0,
            )
        except Exception:
            pass

        return action_word, punishment_str
