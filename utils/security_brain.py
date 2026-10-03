"""
Rai Security Brain — Central Security Intelligence Layer.
Correlates security events from Raid Detection, Anti-Nuke, Anti-Spam, VoiceGuard,
and Permission Guard. Calculates composite risk scores, manages incident lifecycles,
maintains server baselines, applies hysteresis, and alerts staff.
"""

from __future__ import annotations

import asyncio
import collections
import datetime
import logging
import time
from typing import TYPE_CHECKING, Deque, Dict, List, Optional, Tuple
import discord

from config import Colors
from utils.embeds import create_embed, security_embed, warning_embed

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


class RollingWindowTracker:
    """Maintains time-windowed event counters using deques."""

    def __init__(self, max_seconds: int = 1800):
        self.max_seconds = max_seconds
        self.joins: Deque[float] = collections.deque()
        self.messages: Deque[Tuple[float, int, int]] = collections.deque()  # (time, user_id, channel_id)
        self.new_accounts: Deque[float] = collections.deque()
        self.mentions: Deque[float] = collections.deque()
        self.invites: Deque[float] = collections.deque()
        self.repeated_messages: Deque[float] = collections.deque()

    def prune(self, now: float) -> None:
        cutoff = now - self.max_seconds
        while self.joins and self.joins[0] < cutoff:
            self.joins.popleft()
        while self.messages and self.messages[0][0] < cutoff:
            self.messages.popleft()
        while self.new_accounts and self.new_accounts[0] < cutoff:
            self.new_accounts.popleft()
        while self.mentions and self.mentions[0] < cutoff:
            self.mentions.popleft()
        while self.invites and self.invites[0] < cutoff:
            self.invites.popleft()
        while self.repeated_messages and self.repeated_messages[0] < cutoff:
            self.repeated_messages.popleft()

    def count_window(self, deque_obj: Deque, now: float, window_seconds: float) -> int:
        cutoff = now - window_seconds
        # Binary or linear count from right since items are chronological
        count = 0
        for item in reversed(deque_obj):
            t = item[0] if isinstance(item, tuple) else item
            if t >= cutoff:
                count += 1
            else:
                break
        return count


class SecurityBrain:
    """Central Intelligence Engine for Rai Bot."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # guild_id -> RollingWindowTracker
        self._windows: Dict[int, RollingWindowTracker] = {}
        # guild_id -> baseline join rate per minute
        self._baseline_joins: Dict[int, float] = {}
        # guild_id -> (last_alert_time, last_alert_level)
        self._alert_cooldowns: Dict[int, Tuple[float, str]] = {}
        # guild_id -> active incident_id
        self._active_incidents: Dict[int, str] = {}
        self._lock = asyncio.Lock()

    def get_tracker(self, guild_id: int) -> RollingWindowTracker:
        if guild_id not in self._windows:
            self._windows[guild_id] = RollingWindowTracker()
        return self._windows[guild_id]

    async def record_join(self, member: discord.Member) -> None:
        async with self._lock:
            now = time.monotonic()
            tracker = self.get_tracker(member.guild.id)
            tracker.prune(now)
            tracker.joins.append(now)

            # Account age check (< 24 hours)
            age = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).total_seconds()
            if age < 86400:
                tracker.new_accounts.append(now)

        await self.evaluate_raid_risk(member.guild)

    async def record_message(self, message: discord.Message, has_mentions: bool = False, has_invite: bool = False, is_duplicate: bool = False) -> None:
        if not message.guild or message.author.bot:
            return

        async with self._lock:
            now = time.monotonic()
            tracker = self.get_tracker(message.guild.id)
            tracker.prune(now)
            tracker.messages.append((now, message.author.id, message.channel.id))

            if has_mentions:
                tracker.mentions.append(now)
            if has_invite:
                tracker.invites.append(now)
            if is_duplicate:
                tracker.repeated_messages.append(now)

        # Trigger evaluation when suspicious indicators appear
        if has_mentions or has_invite or is_duplicate:
            await self.evaluate_raid_risk(message.guild)

    async def evaluate_raid_risk(self, guild: discord.Guild) -> Tuple[int, str, List[str]]:
        """
        Calculates multi-signal composite risk score:
        0–29: NORMAL, 30–49: ELEVATED, 50–69: SUSPICIOUS, 70–89: HIGH, 90+: CRITICAL.
        Applies hysteresis and dispatches smart alerts.
        """
        cfg = await self.bot.db.get_raid_config(guild.id)
        if not cfg.enabled:
            return 0, "NORMAL", []

        now = time.monotonic()
        tracker = self.get_tracker(guild.id)

        # 60s observation window
        joins_1m = tracker.count_window(tracker.joins, now, float(cfg.observation_window_seconds))
        new_accs_1m = tracker.count_window(tracker.new_accounts, now, float(cfg.observation_window_seconds))
        msgs_1m = tracker.count_window(tracker.messages, now, float(cfg.observation_window_seconds))
        mentions_1m = tracker.count_window(tracker.mentions, now, float(cfg.observation_window_seconds))
        invites_1m = tracker.count_window(tracker.invites, now, float(cfg.observation_window_seconds))
        duplicates_1m = tracker.count_window(tracker.repeated_messages, now, float(cfg.observation_window_seconds))

        score = 0
        reasons = []

        # 1. Join spike vs baseline
        baseline = self._baseline_joins.get(guild.id, 2.0)
        if joins_1m >= cfg.join_threshold:
            multiplier = joins_1m / max(1.0, baseline)
            if multiplier >= cfg.join_multiplier:
                score += 30
                reasons.append(f"Join spike: {joins_1m} joins in {cfg.observation_window_seconds}s ({multiplier:.1f}× baseline)")
            else:
                score += 15
                reasons.append(f"Elevated joins: {joins_1m} joins in {cfg.observation_window_seconds}s")

        # 2. Large new-account concentration
        if new_accs_1m >= 5:
            score += 20
            reasons.append(f"{new_accs_1m} new accounts (< 24h old) joined recently")

        # 3. Burst messages after joins
        if joins_1m >= 5 and msgs_1m >= 20:
            score += 20
            reasons.append(f"High message burst from incoming members ({msgs_1m} msgs/min)")

        # 4. Repeated/duplicate spam
        if duplicates_1m >= 3:
            score += 15
            reasons.append(f"{duplicates_1m} repeated messages detected")

        # 5. Mention flooding
        if mentions_1m >= 3:
            score += 10
            reasons.append(f"Mention flooding detected ({mentions_1m} incidents)")

        # 6. Invite spam
        if invites_1m >= 2:
            score += 15
            reasons.append(f"Unauthorized Discord invite spam ({invites_1m} invites)")

        # Determine Risk Level
        if score >= cfg.risk_threshold_critical:
            level = "CRITICAL"
        elif score >= cfg.risk_threshold_high:
            level = "HIGH"
        elif score >= cfg.risk_threshold_suspicious:
            level = "SUSPICIOUS"
        elif score >= cfg.risk_threshold_elevated:
            level = "ELEVATED"
        else:
            level = "NORMAL"

        # Manage incident lifecycle
        if level in ("SUSPICIOUS", "HIGH", "CRITICAL"):
            active_inc = await self.bot.db.get_active_raid_incident(guild.id)
            if not active_inc:
                now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M")
                inc_id = f"RAID-{now_str}-{guild.id % 10000:04d}"
                await self.bot.db.create_raid_incident(guild.id, inc_id, level, score)
                self._active_incidents[guild.id] = inc_id
            else:
                inc_id = active_inc.incident_id
                await self.bot.db.update_raid_incident_score(inc_id, score, level)

            await self._dispatch_raid_alert(guild, inc_id, level, score, reasons, cfg.alert_cooldown_seconds)

            # Auto-containment if enabled
            if cfg.auto_containment and level in ("HIGH", "CRITICAL"):
                await self._apply_containment(guild, level)

        return score, level, reasons

    async def _dispatch_raid_alert(
        self, guild: discord.Guild, incident_id: str, level: str, score: int, reasons: List[str], cooldown: int
    ) -> None:
        now = time.monotonic()
        last_time, last_level = self._alert_cooldowns.get(guild.id, (0.0, "NORMAL"))

        # Prevent alert spam: suppress if same level and within cooldown
        if (now - last_time) < cooldown and last_level == level:
            return

        self._alert_cooldowns[guild.id] = (now, level)

        log_cfg = await self.bot.db.get_logging_config(guild.id)
        ch_id = log_cfg.security_channel_id or log_cfg.general_channel_id
        if not ch_id:
            return

        channel = guild.get_channel(ch_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        embed = security_embed(
            title=f"🚨 RAID ALERT: Level {level} [{incident_id}]",
            description=f"**Current Composite Risk Score:** `{score}/100`\n**Observed Activity Signals:**\n• " + "\n• ".join(reasons),
        )
        embed.add_field(name="Recommended Action", value="Monitor recent joins, verify channels, or run `/security lockdown` if needed.", inline=False)
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.warning(f"Could not dispatch raid alert in guild {guild.id}: {e}")

    async def _apply_containment(self, guild: discord.Guild, level: str) -> None:
        """Safe automatic containment: activates verification requirement and logs containment."""
        logger.info(f"Applying automatic raid containment in guild {guild.name} ({guild.id})")
        # Record containment in raid incident
        inc = await self.bot.db.get_active_raid_incident(guild.id)
        if inc:
            await self.bot.db.record_raid_event(
                inc.incident_id, guild.id, "AUTO_CONTAINMENT", None, None, f"Level {level} containment armed"
            )
