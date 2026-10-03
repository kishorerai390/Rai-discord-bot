"""
Modular Anti-Nuke Protection Engine for Rai.
Guards servers against rogue administrators, compromised accounts, and rogue bots.
Monitors:
- Mass channel deletion / creation
- Mass role deletion / creation
- Mass bans / kicks
- Dangerous permission changes (Administrator, Manage Guild)
- Webhook creation and spam abuse
- Rogue bot invitations
Uses a strict Whitelist / Trusted system to prevent false positives against verified founders.
"""

from __future__ import annotations

import collections
import logging
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple
import discord

from config import FOUNDER_ROLE_ID, BOT_USER_ID

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.AntiNuke")


class AntiNukeEngine:
    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # (guild_id, user_id, action_type) -> deque of timestamps
        self._action_windows: Dict[Tuple[int, int, str], collections.deque[float]] = collections.defaultdict(collections.deque)
        self._contained_users: Set[Tuple[int, int]] = set()

    async def is_trusted(self, guild: discord.Guild, member: discord.Member) -> bool:
        """Evaluates whether an actor is trusted and exempt from Anti-Nuke containment."""
        if member.id == guild.owner_id:
            return True
        if member.id == self.bot.user.id or member.id == BOT_USER_ID:
            return True

        # Check Founder role
        for r in getattr(member, "roles", []):
            if r.id == FOUNDER_ROLE_ID or "founder" in r.name.lower():
                return True

        # Check database whitelist
        role_ids = [r.id for r in member.roles]
        if await self.bot.db.is_whitelisted(guild.id, member.id, role_ids):
            return True

        return False

    async def record_and_evaluate(
        self,
        guild: discord.Guild,
        actor: discord.Member,
        action_type: str,
        threshold: int = 3,
        window_seconds: float = 15.0,
    ) -> bool:
        """
        Records an administrative action and checks if actor exceeded threshold.
        Returns True if threshold exceeded (nuke attempt detected).
        """
        if await self.is_trusted(guild, actor):
            return False

        key = (guild.id, actor.id, action_type)
        now = time.time()
        dq = self._action_windows[key]

        # Prune older than window
        cutoff = now - window_seconds
        while dq and dq[0] < cutoff:
            dq.popleft()

        dq.append(now)

        if len(dq) >= threshold:
            logger.critical(
                f"🚨 ANTI-NUKE TRIGGERED: Actor {actor.name} ({actor.id}) in {guild.name} exceeded {action_type} ({len(dq)}/{threshold})"
            )
            await self.contain_actor(guild, actor, f"Anti-Nuke: Mass {action_type}")
            return True

        return False

    async def contain_actor(self, guild: discord.Guild, actor: discord.Member, reason: str) -> None:
        """Safely strips dangerous permissions or applies immediate timeout containment."""
        contained_key = (guild.id, actor.id)
        if contained_key in self._contained_users:
            return
        self._contained_users.add(contained_key)

        try:
            # 1. Apply timeout (28 days max containment)
            import datetime
            until = discord.utils.utcnow() + datetime.timedelta(days=28)
            await actor.timeout(until, reason=f"Anti-Nuke Containment: {reason}")
            logger.info(f"Contained rogue actor {actor.name} with 28d timeout.")
        except Exception as e:
            logger.warning(f"Could not timeout rogue actor {actor.name}: {e}")

        # 2. Dispatch critical alert to owner
        try:
            from utils.owner_reporter import OwnerReporter
            OwnerReporter.send_security_report(
                self.bot,
                guild.id,
                event="Anti-Nuke Containment Executed",
                user=actor,
                reason=reason,
                action_taken="28-day emergency quarantine applied",
                severity="CRITICAL",
            )
        except Exception:
            pass
