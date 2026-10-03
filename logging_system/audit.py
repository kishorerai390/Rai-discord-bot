"""
Structured General Audit and Recovery Event Logger for Rai.
Logs moderation events, recovery attempts, worker failures, and permission changes.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional
import discord

from config import Colors

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.Audit")


class AuditLogger:
    @staticmethod
    async def log_recovery_event(
        bot: SentinelBot,
        component: str,
        reason: str,
        success: bool,
    ) -> None:
        """Logs component self-recovery event."""
        logger.info(f"[Recovery Audit] Component '{component}' recovery: {'SUCCESS' if success else 'FAILED'} (Reason: {reason})")

    @staticmethod
    async def log_moderation_event(
        bot: SentinelBot,
        guild: discord.Guild,
        action: str,
        target: discord.User | discord.Member,
        moderator: discord.Member,
        reason: str,
    ) -> None:
        """Logs staff disciplinary action to moderation channel."""
        try:
            log_cfg = await bot.db.get_logging_config(guild.id)
            ch_id = log_cfg.moderation_channel_id or log_cfg.general_channel_id
            if not ch_id:
                return
            channel = guild.get_channel(ch_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                return

            embed = discord.Embed(
                title=f"🔨 Moderation: {action}",
                color=Colors.ERROR if "Ban" in action or "Kick" in action else Colors.WARNING,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            embed.add_field(name="Target", value=f"{target.mention} (`{target.id}`)", inline=True)
            embed.add_field(name="Moderator", value=f"{moderator.mention}", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            await channel.send(embed=embed)
        except Exception as e:
            logger.debug(f"Could not log mod action: {e}")
