"""
Security Verification and Captive Portal Gate.
Implements interactive verification buttons and role granting.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.Verification")


class VerificationGate:
    def __init__(self, bot: SentinelBot):
        self.bot = bot

    async def verify_member(self, member: discord.Member) -> bool:
        """Grants configured verified role and logs completion."""
        guild = member.guild
        cfg = await self.bot.db.get_verification_config(guild.id)
        if not cfg.enabled or not cfg.verified_role_id:
            return False

        role = guild.get_role(cfg.verified_role_id)
        if not role:
            return False

        try:
            await member.add_roles(role, reason="Passed security verification")
            logger.info(f"Verified member {member.name} ({member.id}) in {guild.name}")
            return True
        except Exception as e:
            logger.warning(f"Could not assign verified role to {member.name}: {e}")
            return False
