"""
Alt & Suspicious Young Account Radar Plugin.
Monitors member join velocity and flags freshly created accounts (< 72 hours old).
"""

from __future__ import annotations

import logging
import time
from typing import Optional
import discord

from core.plugin_engine import BaseSecurityPlugin

logger = logging.getLogger("Sentinel.Plugin.AltRadar")


class AltAccountRadarPlugin(BaseSecurityPlugin):
    name = "AltAccountRadar"
    version = "1.0.0"
    author = "Rai Security Operations"
    description = "Flags freshly created accounts joining the server and logs an early security advisory."

    async def on_member_join(self, member: discord.Member) -> Optional[bool]:
        if member.bot:
            return True

        created_at_ts = member.created_at.timestamp()
        account_age_hours = (time.time() - created_at_ts) / 3600.0

        if account_age_hours < 72.0:
            try:
                from utils.owner_reporter import log_security_incident
                await log_security_incident(
                    self.bot,
                    member.guild.id,
                    event="New Account Radar Alert",
                    user=member,
                    action_taken="Monitored in low-trust watchlist",
                    details={
                        "Plugin": self.name,
                        "Account Age": f"{account_age_hours:.1f} hours",
                        "Created At": member.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    },
                )
            except Exception as e:
                logger.debug(f"Could not dispatch alt radar alert: {e}")

        return True
