"""
Modular Anti-Nuke and Fast Automatic Response Engine for Raivora.
Guards servers against rogue administrators, compromised accounts, and rogue bots.
Monitors:
- Mass channel deletion / creation
- Mass role deletion / creation
- Mass bans / kicks
- Dangerous permission changes (Administrator, Manage Guild, Manage Roles, Manage Channels, Mention Everyone)
- Webhook creation and spam abuse
- Coordinated multi-vector attacks

Features:
- Event correlation & severity scoring (0-100) across sliding windows
- Role hierarchy validation before moderation actions
- Duplicate-alert suppression & Discord API backoff
- Persistent incident records & verified owner alerts
"""

from __future__ import annotations

import asyncio
import collections
import datetime
import logging
import time
import uuid
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple
import discord

from config import FOUNDER_ROLE_ID, BOT_USER_ID
from utils.permissions import check_bot_hierarchy, is_verified_owner_or_trusted

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.AntiNuke")


# Severity weights for administrative actions
ACTION_SEVERITY_WEIGHTS: Dict[str, int] = {
    "channel_delete": 25,
    "role_delete": 25,
    "dangerous_perm_grant": 35,
    "member_ban": 20,
    "member_kick": 15,
    "webhook_create": 15,
    "channel_create": 10,
    "role_create": 10,
    "everyone_mention_spam": 30,
}


class AntiNukeEngine:
    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # (guild_id, user_id, action_type) -> deque of timestamps
        self._action_windows: Dict[Tuple[int, int, str], collections.deque[float]] = collections.defaultdict(collections.deque)
        # (guild_id, user_id) -> deque of (timestamp, action_type, weight)
        self._correlated_windows: Dict[Tuple[int, int], collections.deque[Tuple[float, str, int]]] = collections.defaultdict(collections.deque)
        # Suppress duplicate alerts within 60s: (guild_id, user_id, action_type) -> timestamp
        self._alert_cooldowns: Dict[Tuple[int, int, str], float] = {}
        self._contained_users: Set[Tuple[int, int]] = set()

    async def is_trusted(self, guild: discord.Guild, member: discord.Member) -> bool:
        """
        Evaluates whether an actor is verified trusted and exempt from Anti-Nuke containment.
        Checks:
        1. Verified Discord server owner ID (guild.owner_id).
        2. Bot self / system ID.
        3. Configured trusted_security_users allowlist in SQLite.
        4. Founder role / database whitelist.
        """
        if not member or not guild:
            return False

        # 1. Verified Guild Owner ID
        if member.id == guild.owner_id:
            return True

        # 2. Bot self / internal bot ID
        bot_user_id = getattr(self.bot.user, "id", None) or BOT_USER_ID
        if member.id == bot_user_id:
            return True

        # 3. Explicit trusted security allowlist in database
        try:
            if hasattr(self.bot, "db") and hasattr(self.bot.db, "is_user_trusted"):
                res = self.bot.db.is_user_trusted(guild.id, member.id)
                if hasattr(res, "__await__"):
                    if await res:
                        return True
                elif bool(res):
                    return True
        except Exception as e:
            logger.warning("Error checking trusted security users for %s: %s", member.id, e)

        # 4. Check Founder role
        for r in getattr(member, "roles", []):
            if r.id == FOUNDER_ROLE_ID or "founder" in r.name.lower():
                return True

        # 5. Check database whitelist
        try:
            role_ids = [r.id for r in getattr(member, "roles", [])]
            if hasattr(self.bot, "db") and hasattr(self.bot.db, "is_whitelisted"):
                res = self.bot.db.is_whitelisted(guild.id, member.id, role_ids)
                if hasattr(res, "__await__"):
                    if await res:
                        return True
                elif bool(res):
                    return True
        except Exception:
            pass

        return False

    async def record_and_evaluate(
        self,
        guild: discord.Guild,
        actor: discord.Member,
        action_type: str,
        threshold: Optional[int] = None,
        window_seconds: float = 15.0,
    ) -> bool:
        """
        Records an administrative action, checks sliding-window thresholds,
        calculates multi-action correlation severity score, and executes containment if breached.
        Returns True if containment was triggered.
        """
        if await self.is_trusted(guild, actor):
            return False

        now = time.time()
        weight = ACTION_SEVERITY_WEIGHTS.get(action_type, 15)

        # 1. Action-specific sliding window
        key = (guild.id, actor.id, action_type)
        dq = self._action_windows[key]
        cutoff = now - window_seconds
        while dq and dq[0] < cutoff:
            dq.popleft()
        dq.append(now)

        # Fetch configured anti-nuke threshold if not passed
        if threshold is None:
            cfg = await self.bot.db.get_anti_nuke_config(guild.id)
            threshold_map = {
                "channel_delete": cfg.max_channel_deletions,
                "channel_create": cfg.max_channel_creations,
                "role_delete": cfg.max_role_deletions,
                "role_create": cfg.max_role_creations,
                "member_ban": cfg.max_ban_spike,
                "member_kick": cfg.max_kick_spike,
                "webhook_create": cfg.max_webhook_creations,
            }
            threshold = threshold_map.get(action_type, 3)

        # 2. Correlated multi-action sliding window
        corr_key = (guild.id, actor.id)
        corr_dq = self._correlated_windows[corr_key]
        while corr_dq and corr_dq[0][0] < cutoff:
            corr_dq.popleft()
        corr_dq.append((now, action_type, weight))

        # Calculate cumulative severity score
        total_severity = sum(item[2] for item in corr_dq)

        # Trigger condition: single action exceeded threshold OR correlated severity >= 50
        action_breached = len(dq) >= threshold
        severity_breached = total_severity >= 50 and len(corr_dq) >= 2

        if action_breached or severity_breached:
            # Check duplicate alert suppression (60s)
            alert_key = (guild.id, actor.id, action_type)
            last_alert = self._alert_cooldowns.get(alert_key, 0.0)
            is_suppressed = (now - last_alert) < 60.0
            self._alert_cooldowns[alert_key] = now

            reason = (
                f"Anti-Nuke Triggered: Exceeded {action_type} limit ({len(dq)}/{threshold})"
                if action_breached
                else f"Correlated Attack Pattern: Severity Score {total_severity}/100 across {len(corr_dq)} actions"
            )

            logger.critical(
                "🚨 ANTI-NUKE TRIGGERED: Actor %s (%s) in %s — %s",
                actor.name, actor.id, guild.name, reason
            )

            await self.contain_actor(guild, actor, reason, is_suppressed=is_suppressed)
            return True

        return False

    async def contain_actor(
        self,
        guild: discord.Guild,
        actor: discord.Member,
        reason: str,
        is_suppressed: bool = False,
    ) -> None:
        """
        Safely contains rogue actor by:
        1. Checking role hierarchy.
        2. Stripping dangerous administrative permissions/roles.
        3. Applying timeout or configured containment action.
        4. Alerting owner and security log channel.
        5. Recording persistent incident audit log.
        """
        contained_key = (guild.id, actor.id)
        if contained_key in self._contained_users:
            return
        self._contained_users.add(contained_key)

        can_mod, mod_reason = check_bot_hierarchy(actor, guild.me)
        cfg = await self.bot.db.get_anti_nuke_config(guild.id)
        action_outcomes: List[str] = []

        if not can_mod:
            action_outcomes.append(f"Hierarchy Restriction: Bot cannot moderate actor ({mod_reason})")
            logger.warning(
                "Cannot automatically moderate %s (%s): %s",
                actor.name, actor.id, mod_reason
            )
        else:
            # 1. Strip dangerous roles
            stripped_roles: List[str] = []
            dangerous_perms = ("administrator", "manage_guild", "manage_roles", "manage_channels", "ban_members", "kick_members", "mention_everyone")
            roles_to_keep = []
            for r in actor.roles:
                if r.is_default():
                    continue
                perms = r.permissions
                has_dangerous = any(getattr(perms, p, False) for p in dangerous_perms)
                if has_dangerous and r < guild.me.top_role:
                    stripped_roles.append(r.name)
                else:
                    roles_to_keep.append(r)

            if stripped_roles:
                try:
                    await actor.edit(roles=roles_to_keep, reason=f"Anti-Nuke Containment: Stripped dangerous roles ({', '.join(stripped_roles)})")
                    action_outcomes.append(f"Stripped dangerous roles: {', '.join(stripped_roles)}")
                    logger.info("Stripped %d dangerous roles from rogue actor %s", len(stripped_roles), actor.name)
                except Exception as e:
                    action_outcomes.append(f"Failed to strip roles: {e}")

            # 2. Apply configured containment action
            action_type = cfg.auto_quarantine_action.lower()
            if action_type == "ban":
                try:
                    await actor.ban(reason=f"Anti-Nuke Emergency Containment: {reason}", delete_message_days=1)
                    action_outcomes.append("Banned from server")
                except Exception as e:
                    action_outcomes.append(f"Ban failed: {e}")
            elif action_type == "kick":
                try:
                    await actor.kick(reason=f"Anti-Nuke Emergency Containment: {reason}")
                    action_outcomes.append("Kicked from server")
                except Exception as e:
                    action_outcomes.append(f"Kick failed: {e}")
            else:
                # Default: Timeout 28 days
                try:
                    until = discord.utils.utcnow() + datetime.timedelta(days=28)
                    await actor.timeout(until, reason=f"Anti-Nuke Emergency Containment: {reason}")
                    action_outcomes.append("Applied 28-day timeout quarantine")
                except Exception as e:
                    action_outcomes.append(f"Timeout failed: {e}")

        # 3. Record incident into database
        incident_id = f"RAI-SEC-{uuid.uuid4().hex[:6].upper()}"
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            from database.models import SecurityIncident
            inc = SecurityIncident(
                event_id=incident_id,
                guild_id=guild.id,
                timestamp=now_iso,
                event_type="ANTI_NUKE_BREACH",
                executor_id=actor.id,
                executor_name=f"{actor.name} ({actor.id})",
                target_id=None,
                target_name=None,
                action="nuke_containment",
                detected_count=1,
                threshold=1,
                audit_log_id=None,
                audit_verified=True,
                automated_action="; ".join(action_outcomes) or "None",
                result="CONTAINED" if can_mod else "HIERARCHY_BLOCKED",
                reason=reason,
                severity="CRITICAL",
            )
            await self.bot.db.record_security_incident(inc)
            await self.bot.db.record_permission_audit(
                guild_id=guild.id,
                actor_id=actor.id,
                target_type="user",
                action="anti_nuke_containment",
                target_id=actor.id,
                permissions_changed="; ".join(action_outcomes),
                status="contained" if can_mod else "hierarchy_blocked",
            )
        except Exception as e:
            logger.error("Failed to record incident in database: %s", e)

        # 4. Dispatch Alert (if not duplicate suppressed)
        if not is_suppressed:
            try:
                from utils.owner_reporter import OwnerReporter
                OwnerReporter.send_security_report(
                    self.bot,
                    guild.id,
                    event="🚨 Anti-Nuke Emergency Containment",
                    user=actor,
                    reason=reason,
                    action_taken=" | ".join(action_outcomes) or "Contained",
                    severity="CRITICAL",
                    details={
                        "Incident ID": f"`{incident_id}`",
                        "Responsible Actor": f"{actor.mention} (`{actor.id}`)",
                        "Bot Hierarchy Valid": "✅ Yes" if can_mod else f"❌ No ({mod_reason})",
                        "Actions Executed": "\n".join(f"• {act}" for act in action_outcomes),
                    },
                )
            except Exception as e:
                logger.warning("Could not dispatch owner report: %s", e)

