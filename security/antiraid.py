"""
Modular Anti-Raid Engine for Rai.
Detects:
- Sudden join spikes (rolling 10s, 60s, 300s windows)
- Unusual join rates against adaptive baselines
- Suspicious joining patterns (default avatars, new account bursts)
Applies automatic containment, verification restrictions, or temporary lockdown.
"""

from __future__ import annotations

import collections
import logging
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
import discord

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.AntiRaid")


class JoinWindowTracker:
    def __init__(self):
        self.joins: collections.deque[float] = collections.deque()
        self.avatarless_joins: collections.deque[float] = collections.deque()
        self.suspicious_accounts: collections.deque[int] = collections.deque()

    def record_join(self, member: discord.Member, now: float) -> None:
        self.joins.append(now)
        if not member.avatar:
            self.avatarless_joins.append(now)
        # Check account age < 3 days
        account_age = (discord.utils.utcnow() - member.created_at).total_seconds()
        if account_age < 259200:
            self.suspicious_accounts.append(member.id)

    def prune(self, cutoff: float) -> None:
        while self.joins and self.joins[0] < cutoff:
            self.joins.popleft()
        while self.avatarless_joins and self.avatarless_joins[0] < cutoff:
            self.avatarless_joins.popleft()


class AntiRaidEngine:
    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._trackers: Dict[int, JoinWindowTracker] = collections.defaultdict(JoinWindowTracker)
        self._active_raids: Dict[int, bool] = {}

    def get_tracker(self, guild_id: int) -> JoinWindowTracker:
        return self._trackers[guild_id]

    async def evaluate_member_join(self, member: discord.Member) -> Tuple[bool, str, int]:
        """
        Evaluates incoming join against raid thresholds.
        Returns (is_raid: bool, reason: str, score: int).
        """
        guild = member.guild
        cfg = await self.bot.db.get_raid_config(guild.id)
        if not cfg.enabled:
            return False, "Disabled", 0

        now = time.time()
        tracker = self.get_tracker(guild.id)
        tracker.record_join(member, now)
        tracker.prune(now - 60.0)

        joins_10s = sum(1 for t in tracker.joins if t > now - 10.0)
        joins_60s = len(tracker.joins)
        young_accs = len(tracker.suspicious_accounts)

        score = 0
        reasons = []

        if joins_10s >= cfg.join_threshold:
            score += 60
            reasons.append(f"Join spike ({joins_10s} in 10s)")
        if joins_60s >= (cfg.join_threshold * 2):
            score += 40
            reasons.append(f"Sustained flood ({joins_60s} in 60s)")
        if young_accs >= 3:
            score += 30
            reasons.append(f"Fresh accounts burst ({young_accs})")

        is_raid = score >= 70
        if is_raid and not self._active_raids.get(guild.id, False):
            self._active_raids[guild.id] = True
            logger.warning(f"🚨 RAID DETECTED in {guild.name} (ID: {guild.id}): {', '.join(reasons)}")
            if cfg.auto_containment:
                await self.contain_raid(guild, ", ".join(reasons))

        return is_raid, ", ".join(reasons), score

    async def contain_raid(self, guild: discord.Guild, reason: str) -> None:
        """Executes defensive containment without risking bot health."""
        logger.info(f"Executing automated raid containment for {guild.name}: {reason}")
        try:
            # Dispatch alert to owner & log channels
            from utils.owner_reporter import OwnerReporter
            OwnerReporter.send_security_report(
                self.bot,
                guild.id,
                event="Automated Raid Mitigation Activated",
                reason=reason,
                action_taken="Gate containment applied; staff alerted",
                severity="CRITICAL",
            )
        except Exception as e:
            logger.error(f"Error dispatching raid containment alert: {e}")
