"""
Structured Security Incident Logging and Alert Formatter for Rai.
Dispatches high-value security embeds to configured security audit channels and owner feeds.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional
import discord

from config import Colors

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.SecurityLog")


class SecurityLogger:
    @staticmethod
    def format_security_alert_embed(
        event: str,
        guild_name: str,
        detected_details: str,
        action_taken: str,
        severity: str = "HIGH",
    ) -> discord.Embed:
        """
        Formats structured alert matching Section 14:
        🚨 SECURITY ALERT
        Event: Possible Raid
        Guild: Server Name
        Detected: 15 joins / 10 seconds
        Action: Enhanced verification activated
        Time: Timestamp
        """
        color = Colors.ERROR if severity == "CRITICAL" else Colors.SECURITY
        embed = discord.Embed(
            title="🚨 SECURITY ALERT",
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="📌 Event", value=event, inline=False)
        embed.add_field(name="🏛️ Guild", value=guild_name, inline=True)
        embed.add_field(name="⚡ Severity", value=f"`{severity}`", inline=True)
        embed.add_field(name="🔍 Detected", value=detected_details, inline=False)
        embed.add_field(name="🛡️ Action", value=action_taken, inline=False)
        embed.set_footer(text="Rai Autonomous Security Shield")
        return embed

    @staticmethod
    async def log_security_event(
        bot: SentinelBot,
        guild: discord.Guild,
        event: str,
        detected: str,
        action: str,
        severity: str = "HIGH",
    ) -> None:
        """Sends security alert to server log channel and owner report channel."""
        embed = SecurityLogger.format_security_alert_embed(
            event=event,
            guild_name=guild.name,
            detected_details=detected,
            action_taken=action,
            severity=severity,
        )

        # 1. Server Security Log Channel
        try:
            log_cfg = await bot.db.get_logging_config(guild.id)
            ch_id = log_cfg.security_channel_id or log_cfg.moderation_channel_id or log_cfg.general_channel_id
            if ch_id:
                channel = guild.get_channel(ch_id)
                if channel and isinstance(channel, discord.TextChannel):
                    await channel.send(embed=embed)
        except Exception as e:
            logger.debug(f"Could not send security alert to guild log: {e}")

        # 2. Owner Confidential Feed
        try:
            from utils.owner_reporter import OwnerReporter
            OwnerReporter.send_security_report(
                bot,
                guild.id,
                event=event,
                reason=detected,
                action_taken=action,
                severity=severity,
            )
        except Exception:
            pass
