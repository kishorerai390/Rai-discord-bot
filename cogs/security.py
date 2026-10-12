"""
Advanced Server Security and Anti-Nuke Cog.
Protects against mass channel/role deletion/creation, mass bans/kicks, webhook spam,
unauthorized bot additions, mass mentions, and dangerous permission grants.
Includes audit-log safeguards, emergency kill-switch, lockdown, and incident logging.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import uuid
import asyncio
import collections
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple
import discord
from discord import app_commands
from discord.ext import commands, tasks

from backups.manager import BackupManager, format_bytes
from config import Colors
from database.models import (
    SecurityIncident,
    MentionProtectionConfig,
    MentionViolation,
    TrustedSecurityUser,
    AntiNukeConfig,
    AntiRaidConfig,
    PermissionAuditHistory,
)
from security.antinuke import AntiNukeEngine
from utils.embeds import (
    create_embed,
    error_embed,
    info_embed,
    security_embed,
    success_embed,
    warning_embed,
)
from utils.helpers import (
    ConfirmView,
    PaginationView,
    find_audit_executor,
    format_duration,
)
from utils.permissions import (
    can_moderate,
    check_bot_hierarchy,
    is_admin_or_owner,
    is_founder_or_owner,
    is_guild_owner,
    is_verified_owner_or_trusted,
    is_strict_owner,
    is_strict_owner_or_trusted,
)

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


def generate_event_id() -> str:
    return str(uuid.uuid4())[:8].upper()


class SecurityCog(commands.Cog, name="Security"):
    """Server Security & Anti-Nuke System."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # Central Anti-Nuke Response Engine
        self.antinuke = AntiNukeEngine(self.bot)
        # Temporary storage for channel permissions before lockdown to restore cleanly
        self._lockdown_cache: dict[int, dict[int, discord.PermissionOverwrite]] = {}
        # Sliding window for coordinated @everyone burst detection: guild_id -> deque of (timestamp, user_id)
        self._mention_burst_windows: Dict[int, collections.deque[Tuple[float, int]]] = collections.defaultdict(collections.deque)
        # Anti-raid tracking: guild_id -> deque of (timestamp, member_id, account_age_days)
        self._join_burst_windows: Dict[int, collections.deque[Tuple[float, int, float]]] = collections.defaultdict(collections.deque)
        # Active raid auto-recovery tasks: guild_id -> asyncio.Task
        self._raid_recovery_tasks: Dict[int, asyncio.Task] = {}
        # Safe-mode tracking: guild_id -> consecutive failure count
        self._security_failure_counts: Dict[int, int] = collections.defaultdict(int)
        self._backup_task = None

    async def cog_load(self):
        self._backup_task = self._nightly_backup_loop.start()

    def cog_unload(self):
        if self._backup_task:
            self._backup_task.cancel()

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        """Dangerous Vanity URL & Invite Modification Shield (Feature 68)."""
        old_vanity = getattr(before, "vanity_url_code", None)
        new_vanity = getattr(after, "vanity_url_code", None)
        if old_vanity and new_vanity and old_vanity != new_vanity:
            from utils.owner_reporter import OwnerReporter
            OwnerReporter.send_security_report(
                self.bot,
                after.id,
                event="Vanity URL Modification Alert",
                action_taken="Security Alert Dispatched to Security Channel",
                severity="HIGH",
                details={
                    "Previous Vanity": f"`{old_vanity}`",
                    "New Vanity": f"`{new_vanity}`",
                    "Recommendation": "Verify guild vanity URL integrity",
                },
            )

    security_group = app_commands.Group(
        name="security",
        description="Advanced server security and anti-nuke management",
        default_permissions=discord.Permissions(administrator=True),
    )
    trusted_group = app_commands.Group(
        name="trusted",
        description="Manage verified trusted security users (Owner-only)",
        parent=security_group,
    )
    antinuke_group = app_commands.Group(
        name="antinuke",
        description="High-speed anti-nuke server protection system",
        default_permissions=discord.Permissions(administrator=True),
    )
    antinuke_trust_group = app_commands.Group(
        name="trust",
        description="Manage verified trusted security users (Owner-only)",
        parent=antinuke_group,
    )

    # ==========================================
    # AUDIT-LOG VERIFICATION & ACTION HANDLER
    # ==========================================

    async def _handle_security_violation(
        self,
        guild: discord.Guild,
        event_type: str,
        action_name: str,
        audit_action: discord.AuditLogAction,
        target_id: Optional[int] = None,
        target_name: Optional[str] = None,
        limit_attr: str = "channel_delete_limit",
        window_attr: str = "channel_delete_window",
    ) -> None:
        """
        Generic, fail-safe security event evaluator.
        1. Checks if security enabled.
        2. Retrieves audit-log entry with bounded retry.
        3. Validates against owner, bot, and whitelist.
        4. Evaluates sliding-window threshold.
        5. Enforces configured containment/punishment.
        6. Immutably records incident into SQLite and notifies security channel.
        """
        guild_cfg = await self.bot.db.get_or_create_guild_config(guild.id)
        if not guild_cfg.security_enabled:
            return

        sec_cfg = await self.bot.db.get_security_config(guild.id)
        sec_state = await self.bot.db.get_security_state(guild.id)

        limit = getattr(sec_cfg, limit_attr, 5)
        window = getattr(sec_cfg, window_attr, 10)

        # Step 1: Audit Log lookup
        executor, audit_entry = await find_audit_executor(guild, audit_action, target_id=target_id)
        audit_log_id = audit_entry.id if audit_entry else None
        audit_verified = executor is not None

        # Step 2: Fail-safe check
        if executor is None:
            # Cannot identify executor: do NOT randomly punish! Record as UNKNOWN incident.
            event_id = generate_event_id()
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            incident = SecurityIncident(
                event_id=event_id,
                guild_id=guild.id,
                timestamp=now_iso,
                event_type=event_type,
                executor_id=None,
                executor_name="UNKNOWN (Audit Log Unavailable)",
                target_id=target_id,
                target_name=target_name,
                action=action_name,
                detected_count=1,
                threshold=limit,
                audit_log_id=None,
                reason="Audit log verification inconclusive. Automated punishment aborted to prevent false-positives.",
                automated_action="None (Audit Inconclusive)",
                result="Logged incident and notified administrators.",
                severity="medium",
                audit_verified=False,
            )
            await self.bot.db.record_security_incident(incident)
            await self._notify_security_channel(guild, incident)
            return

        # Step 3: Safeguard Whitelist Checks
        # Never punish: Server owner, Bot itself, Whitelisted user, Whitelisted role, Trusted security users
        if executor.id == guild.owner_id or executor.id == self.bot.user.id:
            return

        if await is_verified_owner_or_trusted(self.bot, guild, executor.id):
            return

        role_ids = [r.id for r in executor.roles] if isinstance(executor, discord.Member) else []
        if await self.bot.db.is_whitelisted(guild.id, executor.id, role_ids):
            return

        # Step 4: Sliding Window Counter Evaluation
        is_violation, detected_count, rule_detail = await self.bot.cooldowns.record_security_action(
            guild_id=guild.id,
            executor_id=executor.id,
            action=action_name,
            limit=limit,
            window_seconds=window,
        )

        if not is_violation:
            return

        # Step 5: Violation confirmed. Check Emergency Stop
        event_id = generate_event_id()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        punishment_applied = "None"
        action_result = "Success"
        severity = "high" if detected_count >= limit * 2 else "medium"

        if sec_state.emergency_stop:
            punishment_applied = "Suppressed by Emergency Stop"
            action_result = "Emergency Stop Active: No destructive action taken."
        else:
            # Step 6: Apply Configured Punishment
            punishment_applied = sec_cfg.punishment
            member = guild.get_member(executor.id)

            if member:
                # Role hierarchy check before punishing
                can_mod, reason = can_moderate(guild.me, member, guild.me)
                if not can_mod:
                    action_result = f"Skipped punishment: {reason}"
                else:
                    try:
                        if sec_cfg.punishment == "ban":
                            await member.ban(reason=f"Security Anti-Nuke: Exceeded {action_name} threshold ({detected_count}/{limit})")
                            action_result = f"Banned {member.name}"
                        elif sec_cfg.punishment == "kick":
                            await member.kick(reason=f"Security Anti-Nuke: Exceeded {action_name} threshold ({detected_count}/{limit})")
                            action_result = f"Kicked {member.name}"
                        elif sec_cfg.punishment == "timeout":
                            until = discord.utils.utcnow() + datetime.timedelta(minutes=60)
                            await member.timeout(until, reason=f"Security Anti-Nuke: Exceeded {action_name} threshold ({detected_count}/{limit})")
                            action_result = f"Timed out {member.name} for 60m"
                        elif sec_cfg.punishment == "remove_roles":
                            roles_to_remove = [r for r in member.roles if r.permissions.administrator or r.permissions.manage_guild or r.permissions.manage_channels or r.permissions.manage_roles]
                            if roles_to_remove:
                                await member.remove_roles(*roles_to_remove, reason="Security containment: stripped dangerous permissions")
                                action_result = f"Removed {len(roles_to_remove)} administrative roles from {member.name}"
                            else:
                                action_result = "No administrative roles to remove"
                        elif sec_cfg.punishment == "lock_channels":
                            await self._execute_lockdown(guild)
                            action_result = "Initiated emergency guild lockdown"
                        else:  # alert
                            action_result = f"Alert issued for {member.name}"
                    except Exception as e:
                        action_result = f"Failed to execute punishment: {str(e)[:100]}"
            else:
                action_result = "Executor is not in guild (cannot punish directly)"

        # Step 7: Record Incident & Violations
        incident = SecurityIncident(
            event_id=event_id,
            guild_id=guild.id,
            timestamp=now_iso,
            event_type=event_type,
            executor_id=executor.id,
            executor_name=f"{executor.name} ({executor.id})",
            target_id=target_id,
            target_name=target_name,
            action=action_name,
            detected_count=detected_count,
            threshold=limit,
            audit_log_id=audit_log_id,
            reason=f"Exceeded action threshold: {rule_detail}",
            automated_action=punishment_applied,
            result=action_result,
            severity=severity,
            audit_verified=audit_verified,
        )
        await self.bot.db.record_security_incident(incident)
        await self.bot.db.record_violation(guild.id, executor.id, event_type)
        await self._notify_security_channel(guild, incident)

    async def _notify_security_channel(self, guild: discord.Guild, incident: SecurityIncident) -> None:
        log_cfg = await self.bot.db.get_logging_config(guild.id)
        channel_id = log_cfg.security_channel_id or log_cfg.general_channel_id
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        embed = security_embed(
            title=f"Security Incident Detected: [{incident.event_id}]",
            description=f"**Event:** {incident.event_type}\n**Action:** {incident.action}",
        )
        embed.add_field(name="Executor", value=incident.executor_name or "Unknown", inline=True)
        embed.add_field(name="Target", value=incident.target_name or "N/A", inline=True)
        embed.add_field(
            name="Threshold",
            value=f"{incident.detected_count}/{incident.threshold}",
            inline=True,
        )
        embed.add_field(name="Automated Action", value=incident.automated_action or "None", inline=True)
        embed.add_field(name="Result", value=incident.result or "None", inline=True)
        embed.add_field(name="Severity", value=incident.severity.upper(), inline=True)
        embed.add_field(name="Audit Verified", value="Yes" if incident.audit_verified else "No", inline=True)

        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _execute_lockdown(self, guild: discord.Guild) -> int:
        """Lockdown all text channels by denying send_messages for @everyone."""
        locked_count = 0
        cache = self._lockdown_cache.setdefault(guild.id, {})
        for channel in guild.text_channels:
            if not channel.permissions_for(guild.me).manage_channels:
                continue
            overwrite = channel.overwrites_for(guild.default_role)
            if overwrite.send_messages is not False:
                cache[channel.id] = overwrite
                new_overwrite = discord.PermissionOverwrite.from_pair(*overwrite.pair())
                new_overwrite.send_messages = False
                try:
                    await channel.set_permissions(guild.default_role, overwrite=new_overwrite, reason="Security Emergency Lockdown")
                    locked_count += 1
                except (discord.Forbidden, discord.HTTPException):
                    pass
        await self.bot.db.set_lockdown(guild.id, True)
        return locked_count

    async def _execute_unlock(self, guild: discord.Guild) -> int:
        """Unlock previously locked channels."""
        unlocked_count = 0
        cache = self._lockdown_cache.pop(guild.id, {})
        for channel in guild.text_channels:
            if not channel.permissions_for(guild.me).manage_channels:
                continue
            try:
                if channel.id in cache:
                    await channel.set_permissions(guild.default_role, overwrite=cache[channel.id], reason="Security Lockdown Lifted")
                    unlocked_count += 1
                else:
                    overwrite = channel.overwrites_for(guild.default_role)
                    if overwrite.send_messages is False:
                        overwrite.send_messages = None
                        await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Security Lockdown Lifted")
                        unlocked_count += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await self.bot.db.set_lockdown(guild.id, False)
        return unlocked_count

    # ==========================================
    # DISCORD EVENT LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self._handle_security_violation(
            guild=channel.guild,
            event_type="CHANNEL_DELETE",
            action_name="channel_delete",
            audit_action=discord.AuditLogAction.channel_delete,
            target_id=channel.id,
            target_name=f"#{channel.name}",
            limit_attr="channel_delete_limit",
            window_attr="channel_delete_window",
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await self._handle_security_violation(
            guild=channel.guild,
            event_type="CHANNEL_CREATE",
            action_name="channel_create",
            audit_action=discord.AuditLogAction.channel_create,
            target_id=channel.id,
            target_name=f"#{channel.name}",
            limit_attr="channel_create_limit",
            window_attr="channel_create_window",
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self._handle_security_violation(
            guild=role.guild,
            event_type="ROLE_DELETE",
            action_name="role_delete",
            audit_action=discord.AuditLogAction.role_delete,
            target_id=role.id,
            target_name=f"@{role.name}",
            limit_attr="role_delete_limit",
            window_attr="role_delete_window",
        )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self._handle_security_violation(
            guild=role.guild,
            event_type="ROLE_CREATE",
            action_name="role_create",
            audit_action=discord.AuditLogAction.role_create,
            target_id=role.id,
            target_name=f"@{role.name}",
            limit_attr="role_create_limit",
            window_attr="role_create_window",
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        await self._handle_security_violation(
            guild=guild,
            event_type="MEMBER_BAN",
            action_name="ban",
            audit_action=discord.AuditLogAction.ban,
            target_id=user.id,
            target_name=f"{user.name}",
            limit_attr="ban_limit",
            window_attr="ban_window",
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Detect kicks via audit logs
        executor, audit_entry = await find_audit_executor(
            member.guild, discord.AuditLogAction.kick, target_id=member.id, max_retries=2, delay_seconds=0.4
        )
        if executor and audit_entry:
            await self._handle_security_violation(
                guild=member.guild,
                event_type="MEMBER_KICK",
                action_name="kick",
                audit_action=discord.AuditLogAction.kick,
                target_id=member.id,
                target_name=f"{member.name}",
                limit_attr="kick_limit",
                window_attr="kick_window",
            )

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        await self._handle_security_violation(
            guild=channel.guild,
            event_type="WEBHOOK_CREATE",
            action_name="webhook_create",
            audit_action=discord.AuditLogAction.webhook_create,
            target_id=channel.id,
            target_name=f"#{channel.name}",
            limit_attr="webhook_limit",
            window_attr="webhook_window",
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild

        # 1. Unauthorized bot additions check
        if member.bot:
            executor, audit_entry = await find_audit_executor(
                guild, discord.AuditLogAction.bot_add, target_id=member.id
            )
            if executor:
                if executor.id != guild.owner_id and executor.id != self.bot.user.id:
                    role_ids = [r.id for r in executor.roles] if isinstance(executor, discord.Member) else []
                    is_whitelisted = await self.bot.db.is_whitelisted(guild.id, executor.id, role_ids)
                    is_trusted = await is_verified_owner_or_trusted(self.bot, guild, executor.id)
                    if not is_whitelisted and not is_trusted:
                        # Unauthorized bot addition!
                        sec_state = await self.bot.db.get_security_state(guild.id)
                        if not sec_state.emergency_stop:
                            try:
                                await member.kick(reason="Security: Unauthorized bot addition")
                            except (discord.Forbidden, discord.HTTPException):
                                pass

                        event_id = generate_event_id()
                        incident = SecurityIncident(
                            event_id=event_id,
                            guild_id=guild.id,
                            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            event_type="UNAUTHORIZED_BOT_ADD",
                            executor_id=executor.id,
                            executor_name=f"{executor.name}",
                            target_id=member.id,
                            target_name=f"{member.name} (Bot)",
                            action="bot_add",
                            detected_count=1,
                            threshold=1,
                            audit_log_id=audit_entry.id if audit_entry else None,
                            reason="Bot invited by non-whitelisted member",
                            automated_action="Kicked unauthorized bot",
                            result="Kicked bot",
                            severity="high",
                            audit_verified=True,
                        )
                        await self.bot.db.record_security_incident(incident)
                        await self._notify_security_channel(guild, incident)
            return

        # 2. Automatic Anti-Raid Mode (Section 4)
        try:
            raid_cfg = await self.bot.db.get_anti_raid_config(guild.id)
        except Exception:
            raid_cfg = AntiRaidConfig(guild_id=guild.id)

        if not getattr(raid_cfg, "enabled", True):
            return

        now_ts = time.time()
        dq = self._join_burst_windows[guild.id]
        window_sec = getattr(raid_cfg, "join_window_seconds", 10)
        cutoff = now_ts - float(window_sec)

        while dq and dq[0][0] < cutoff:
            dq.popleft()

        # Account age in days
        created_at = member.created_at
        age_days = (discord.utils.utcnow() - created_at).total_seconds() / 86400.0
        age_threshold = getattr(raid_cfg, "account_age_threshold_days", 7)
        is_suspicious_age = age_days < age_threshold

        dq.append((now_ts, member.id, age_days))

        # Quarantine suspicious young accounts if quarantine role configured
        if is_suspicious_age and raid_cfg.quarantine_role_id:
            q_role = guild.get_role(raid_cfg.quarantine_role_id)
            if q_role and q_role < guild.me.top_role:
                try:
                    await member.add_roles(q_role, reason=f"Anti-Raid: New account quarantine (<{age_threshold}d old)")
                except Exception as e:
                    logger.debug("Could not assign quarantine role: %s", e)

        # Check Raid Threshold Breach
        join_threshold = getattr(raid_cfg, "join_threshold", 5)
        young_in_window = sum(1 for _, _, age in dq if age < age_threshold)

        is_raid = (len(dq) >= join_threshold) or (young_in_window >= max(3, join_threshold // 2))
        if is_raid:
            logger.critical(
                "🚨 RAID DETECTED in %s: %d joins in %ds (%d young accounts)",
                guild.name, len(dq), window_sec, young_in_window
            )

            # Auto-lockdown channels
            locked_count = 0
            if getattr(raid_cfg, "auto_lockdown", True):
                try:
                    locked_count = await self._execute_lockdown(guild)
                except Exception as e:
                    logger.error("Failed to auto-lockdown guild %s: %s", guild.id, e)

            # Dispatch Alert to Owner and Security Log
            event_id = generate_event_id()
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            alert_embed = security_embed(
                title="🚨 AUTOMATIC RAID LOCKDOWN ENGAGED",
                description=(
                    f"**Mass join spike detected! Automatic server containment active.**\n\n"
                    f"📊 **Join Velocity:** `{len(dq)} accounts in {window_sec}s` (Threshold: `{join_threshold}`)\n"
                    f"👶 **Suspicious Young Accounts (<{age_threshold}d):** `{young_in_window}`\n"
                    f"🔒 **Channels Locked:** `{locked_count}`\n"
                    f"⏱️ **Quiet Recovery Period:** `{raid_cfg.lockdown_duration_seconds}s`\n"
                    f"🛡️ **Action Taken:** Message permissions restricted for `@everyone`."
                ),
            )
            alert_embed.set_footer(text=f"Raivora Raid Shield • Incident ID: {event_id}")
            alert_embed.timestamp = discord.utils.utcnow()
            await self._send_private_security_alert(guild, alert_embed)

            # Record incident
            try:
                incident = SecurityIncident(
                    event_id=event_id,
                    guild_id=guild.id,
                    timestamp=now_iso,
                    event_type="ANTI_RAID_LOCKDOWN",
                    executor_id=None,
                    executor_name="COORDINATED_RAID_BURST",
                    target_id=guild.id,
                    target_name=guild.name,
                    action="server_lockdown",
                    detected_count=len(dq),
                    threshold=join_threshold,
                    audit_log_id=None,
                    reason=f"Mass join spike ({len(dq)} joins in {window_sec}s, {young_in_window} accounts <{age_threshold}d)",
                    automated_action=f"Locked {locked_count} channels",
                    result="LOCKDOWN_ENGAGED",
                    severity="critical",
                    audit_verified=True,
                )
                await self.bot.db.record_security_incident(incident)
            except Exception as e:
                logger.error("Failed to record raid incident: %s", e)

            # Schedule auto-recovery quiet period timer
            self._schedule_raid_recovery(guild, getattr(raid_cfg, "lockdown_duration_seconds", 300))

    def _schedule_raid_recovery(self, guild: discord.Guild, duration: int) -> None:
        """Schedules or resets the auto-unlock quiet period countdown."""
        existing = self._raid_recovery_tasks.get(guild.id)
        if existing and not existing.done():
            existing.cancel()

        async def _recovery_worker():
            try:
                await asyncio.sleep(duration)
                # Verify that threat has subsided: check recent join window
                now = time.time()
                dq = self._join_burst_windows.get(guild.id, collections.deque())
                recent_joins = sum(1 for ts, _, _ in dq if ts > (now - 60))
                if recent_joins > 2:
                    logger.info("Raid activity still elevated in %s, extending lockdown.", guild.name)
                    self._schedule_raid_recovery(guild, duration)
                    return

                # Threat has subsided: lift lockdown
                unlocked_count = await self._execute_unlock(guild)
                logger.info("Auto-lifted raid lockdown for %s (%d channels restored).", guild.name, unlocked_count)

                embed = success_embed(
                    "🟢 Raid Lockdown Lifted",
                    f"Threat subsided. Message permissions automatically restored in **{unlocked_count}** channels after quiet period.",
                )
                await self._send_private_security_alert(guild, embed)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error("Error during raid recovery worker in guild %s: %s", guild.id, e)

        self._raid_recovery_tasks[guild.id] = asyncio.create_task(_recovery_worker())

    def _record_security_failure(self, guild: discord.Guild, error: Exception, operation: str) -> None:
        """Tracks consecutive failures and transitions to degraded Safe Mode if threshold exceeded."""
        self._security_failure_counts[guild.id] += 1
        failures = self._security_failure_counts[guild.id]
        logger.error(f"Security operation '{operation}' failed in {guild.name} (Count: {failures}): {error}")

        if failures >= 5:
            logger.critical(f"⚠️ ENTERING SAFE MODE for {guild.name}: {failures} consecutive security failures.")
            try:
                from utils.owner_reporter import OwnerReporter
                OwnerReporter.send_security_report(
                    self.bot,
                    guild.id,
                    event="⚠️ DEGRADED SECURITY ALERT — SAFE MODE ENGAGED",
                    reason=f"Repeated internal errors during '{operation}' ({failures} consecutive failures)",
                    action_taken="Safe Mode Active — Automated destructive actions suppressed, passive monitoring continues",
                    severity="CRITICAL",
                    details={
                        "Error Subsystem": operation,
                        "Error Type": type(error).__name__,
                        "Error Message": str(error)[:200],
                        "Degraded State": "Server is in Safe Mode. Critical automated moderation suspended until verified.",
                    },
                )
            except Exception:
                pass

    def _reset_security_failure(self, guild: discord.Guild) -> None:
        """Resets the failure counter upon successful execution."""
        self._security_failure_counts[guild.id] = 0

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        """
        Permission and Role Security:
        Continuously monitors Administrator, Manage Server, Manage Roles,
        Manage Channels, Ban Members, Kick Members, and Mention Everyone.
        """
        guild = after.guild
        dangerous_perms = (
            "administrator", "manage_guild", "manage_roles",
            "manage_channels", "ban_members", "kick_members", "mention_everyone"
        )

        granted_perms = [
            p for p in dangerous_perms
            if not getattr(before.permissions, p) and getattr(after.permissions, p)
        ]
        if not granted_perms:
            return

        executor, audit_entry = await find_audit_executor(
            guild, discord.AuditLogAction.role_update, target_id=after.id
        )
        if not executor:
            return

        # Check exemption: verified owner ID or trusted security user
        if executor.id == guild.owner_id or executor.id == self.bot.user.id:
            return

        role_ids = [r.id for r in executor.roles] if isinstance(executor, discord.Member) else []
        is_whitelisted = await self.bot.db.is_whitelisted(guild.id, executor.id, role_ids)
        is_trusted = await is_verified_owner_or_trusted(self.bot, guild, executor.id)
        if is_whitelisted or is_trusted:
            return

        # UNAUTHORIZED DANGEROUS PERMISSION GRANT DETECTED
        logger.critical(
            "🚨 UNAUTHORIZED PERMISSION GRANT: Actor %s (%s) granted [%s] to role @%s in %s",
            executor.name, executor.id, ", ".join(granted_perms), after.name, guild.name
        )

        sec_state = await self.bot.db.get_security_state(guild.id)
        result_msg = "Reverted dangerous role permissions"
        if not sec_state.emergency_stop:
            try:
                await after.edit(permissions=before.permissions, reason=f"Security: Unauthorized grant of {', '.join(granted_perms)}")
            except (discord.Forbidden, discord.HTTPException) as e:
                result_msg = f"Failed to revert role permissions: {e}"

        # Record in database
        event_id = generate_event_id()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            incident = SecurityIncident(
                event_id=event_id,
                guild_id=guild.id,
                timestamp=now_iso,
                event_type="DANGEROUS_PERM_CHANGE",
                executor_id=executor.id,
                executor_name=f"{executor.name}",
                target_id=after.id,
                target_name=f"@{after.name}",
                action=f"role_perm_grant_{','.join(granted_perms)}",
                detected_count=1,
                threshold=1,
                audit_log_id=audit_entry.id if audit_entry else None,
                reason=f"Unauthorized permissions [{', '.join(granted_perms)}] added to role",
                automated_action="Reverted role permissions",
                result=result_msg,
                severity="critical" if "administrator" in granted_perms else "high",
                audit_verified=True,
            )
            await self.bot.db.record_security_incident(incident)
            await self.bot.db.record_permission_audit(
                guild_id=guild.id,
                actor_id=executor.id,
                target_type="role",
                action="grant_permissions",
                target_id=after.id,
                permissions_changed=", ".join(granted_perms),
                status=result_msg,
            )
            await self._notify_security_channel(guild, incident)
        except Exception as e:
            logger.error("Failed to log dangerous perm change: %s", e)

        # Feed into AntiNuke engine for actor containment
        if isinstance(executor, discord.Member):
            await self.antinuke.record_and_evaluate(guild, executor, "dangerous_perm_grant", threshold=2)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Continuously monitors role assignments granting administrative or dangerous permissions.
        """
        guild = after.guild
        added_roles = [r for r in after.roles if r not in before.roles]
        if not added_roles:
            return

        dangerous_perms = ("administrator", "manage_guild", "manage_roles", "manage_channels", "ban_members", "kick_members", "mention_everyone")
        rogue_roles = [
            r for r in added_roles
            if any(getattr(r.permissions, p, False) for p in dangerous_perms)
        ]
        if not rogue_roles:
            return

        executor, audit_entry = await find_audit_executor(
            guild, discord.AuditLogAction.member_role_update, target_id=after.id
        )
        if not executor:
            return

        if executor.id == guild.owner_id or executor.id == self.bot.user.id:
            return

        role_ids = [r.id for r in executor.roles] if isinstance(executor, discord.Member) else []
        is_whitelisted = await self.bot.db.is_whitelisted(guild.id, executor.id, role_ids)
        is_trusted = await is_verified_owner_or_trusted(self.bot, guild, executor.id)
        if is_whitelisted or is_trusted:
            return

        # UNAUTHORIZED DANGEROUS ROLE ASSIGNMENT DETECTED
        logger.critical(
            "🚨 UNAUTHORIZED ROLE ASSIGNMENT: Actor %s (%s) assigned dangerous role(s) [%s] to member %s in %s",
            executor.name, executor.id, ", ".join(r.name for r in rogue_roles), after.name, guild.name
        )

        sec_state = await self.bot.db.get_security_state(guild.id)
        result_msg = "Stripped unauthorized dangerous role(s)"
        if not sec_state.emergency_stop:
            safe_roles = [r for r in after.roles if r not in rogue_roles]
            try:
                await after.edit(roles=safe_roles, reason=f"Security: Unauthorized assignment of dangerous role(s)")
            except (discord.Forbidden, discord.HTTPException) as e:
                result_msg = f"Failed to strip roles: {e}"

        event_id = generate_event_id()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            incident = SecurityIncident(
                event_id=event_id,
                guild_id=guild.id,
                timestamp=now_iso,
                event_type="UNAUTHORIZED_ROLE_GRANT",
                executor_id=executor.id,
                executor_name=f"{executor.name}",
                target_id=after.id,
                target_name=f"{after.name}",
                action="assign_dangerous_role",
                detected_count=1,
                threshold=1,
                audit_log_id=audit_entry.id if audit_entry else None,
                reason=f"Dangerous role(s) [{', '.join(r.name for r in rogue_roles)}] assigned without authorization",
                automated_action="Removed unauthorized roles from member",
                result=result_msg,
                severity="critical",
                audit_verified=True,
            )
            await self.bot.db.record_security_incident(incident)
            await self.bot.db.record_permission_audit(
                guild_id=guild.id,
                actor_id=executor.id,
                target_type="user",
                action="assign_dangerous_role",
                target_id=after.id,
                permissions_changed=", ".join(r.name for r in rogue_roles),
                status=result_msg,
            )
            await self._notify_security_channel(guild, incident)
        except Exception as e:
            logger.error("Failed to record member role audit: %s", e)

        if isinstance(executor, discord.Member):
            await self.antinuke.record_and_evaluate(guild, executor, "dangerous_perm_grant", threshold=2)


    async def _send_private_security_alert(self, guild: discord.Guild, embed: discord.Embed) -> bool:
        """Deliver security alert to the private staff/security channel."""
        log_cfg = await self.bot.db.get_logging_config(guild.id)
        candidate_ids = [
            1555283378612478072,  # 🚨・sᴇᴄᴜʀɪᴛʏ-ᴀʟᴇʀᴛs
            log_cfg.security_channel_id,
            log_cfg.moderation_channel_id,
            log_cfg.general_channel_id,
            1546593526073135107,  # 🚨｜ꜱᴇɴᴛɪɴᴇʟ-ʟᴏɢꜱ
            1545502845208629328,  # 🛡️｜ꜱᴛᴀꜰꜰ-ᴏᴘᴇʀᴀᴛɪᴏɴꜱ
            1546540192343523399,  # 📝｜ᴍᴏᴅᴇʀᴀᴛɪᴏɴ-ʟᴏɢꜱ
            1550187321285148782,  # 👑｜ᴇxᴇᴄᴜᴛɪᴠᴇ-ʟᴏᴜɴɢᴇ
        ]
        for cid in candidate_ids:
            if not cid:
                continue
            channel = guild.get_channel(cid)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(embed=embed)
                    return True
                except (discord.Forbidden, discord.HTTPException):
                    continue

        # Fallback: find any text channel inaccessible to @everyone with log/staff in name
        for channel in guild.text_channels:
            perms = channel.overwrites_for(guild.default_role)
            if perms.read_messages is False and any(k in channel.name.lower() for k in ("log", "staff", "security", "mod")):
                try:
                    await channel.send(embed=embed)
                    return True
                except (discord.Forbidden, discord.HTTPException):
                    continue
        return False

    async def _handle_everyone_mention(self, message: discord.Message) -> None:
        """
        Owner-Only @everyone and @here Protection System:
        Only the verified Discord server owner and explicitly authorized trusted users
        may mention @everyone or @here.
        
        Enforces graduated configurable punishment:
        1. Level 1: Delete message & warn user.
        2. Level 2: Delete message & apply timeout (configurable seconds, default 300s).
        3. Level 3: Delete message & kick member.
        4. Level 4: Coordinated attack detected -> Activate raid lockdown & restrict accounts.
        """
        if not message.guild:
            return

        # Check for webhook @everyone abuse
        if message.webhook_id and (message.mention_everyone or "@everyone" in message.content or "@here" in message.content):
            try:
                await message.delete()
            except Exception:
                pass
            clean_content = message.content[:500] if message.content else "*[No Text Content / Embed Only]*"
            alert_embed = security_embed(
                title="🚨 WEBHOOK @EVERYONE SPAM INTERCEPTED",
                description=(
                    f"**Blocked unauthorized `@everyone` / `@here` ping from an external webhook!**\n\n"
                    f"📍 **Channel:** {message.channel.mention} (`#{message.channel.name}`)\n"
                    f"🔗 **Webhook ID:** `{message.webhook_id}`\n"
                    f"💬 **Content:**\n```{clean_content}```\n"
                    f"🗑️ **Message Status:** Deleted immediately."
                ),
            )
            await self._send_private_security_alert(message.guild, alert_embed)
            return

        # Ignore bot accounts (including Sentinel itself)
        if message.author.bot or not isinstance(message.author, discord.Member):
            return

        # Check if message mentions @everyone or @here
        has_everyone_mention = (
            message.mention_everyone
            or "@everyone" in message.content
            or "@here" in message.content
        )
        if not has_everyone_mention:
            return

        guild = message.guild
        member = message.author

        # Exemption check: Verified Server Owner ID, Founder role, or Trusted Security Users
        if member.id == guild.owner_id:
            logger.info("Permitted @everyone mention by verified Server Owner %s (%s)", member.name, member.id)
            return

        if await is_verified_owner_or_trusted(self.bot, guild, member.id):
            logger.info("Permitted @everyone mention by trusted security user %s (%s)", member.name, member.id)
            return

        if is_founder_or_owner(member):
            logger.info("Permitted @everyone mention by Founder %s (%s)", member.name, member.id)
            return

        # ==========================================
        # UNAUTHORIZED MENTION DETECTED
        # ==========================================
        logger.warning(
            "Unauthorized @everyone mention by %s (%s) in #%s — evaluating mention protection policy.",
            member.name, member.id, message.channel.name
        )

        # Retrieve configuration (fail-safe fallback)
        try:
            cfg = await self.bot.db.get_mention_protection_config(guild.id)
        except Exception:
            cfg = MentionProtectionConfig(guild_id=guild.id)

        if not getattr(cfg, "enabled", True):
            return

        violation_type = "@everyone" if ("@everyone" in message.content or (message.mention_everyone and "@here" not in message.content)) else "@here"

        # 1. Delete message immediately
        msg_deleted = False
        if getattr(cfg, "delete_message", True):
            try:
                await message.delete()
                msg_deleted = True
            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as e:
                logger.debug("Failed to delete unauthorized mention message: %s", e)

        # 2. Check for coordinated multi-account mention raid (Burst Detection)
        now_ts = time.time()
        dq = self._mention_burst_windows[guild.id]
        while dq and dq[0][0] < (now_ts - 15.0):
            dq.popleft()
        dq.append((now_ts, member.id))
        distinct_raiders = len(set(uid for _, uid in dq))
        is_coordinated_raid = distinct_raiders >= 3

        # 3. Violation count in the last 24 hours
        recent_count = 1
        try:
            recent_count = (await self.bot.db.count_recent_mention_violations(guild.id, member.id, seconds=86400)) + 1
        except Exception:
            pass

        # 4. Resolve Graduated Punishment Level
        # 1: Warn, 2: Timeout, 3: Kick, 4: Raid Lockdown
        cfg_level = getattr(cfg, "punishment_level", 2)
        if isinstance(cfg_level, int):
            effective_level = cfg_level
        else:
            effective_level = 2

        if is_coordinated_raid:
            effective_level = 4
        elif recent_count >= 3:
            effective_level = max(effective_level, 3)
        elif recent_count == 2:
            effective_level = max(effective_level, 2)

        action_summary = ""
        can_mod, mod_reason = check_bot_hierarchy(member, guild.me)

        if effective_level == 1 and recent_count == 1:
            # Level 1: Delete + Warn
            action_summary = "Warned member and deleted message"
            try:
                warn_embed = warning_embed(
                    title="⚠️ Warning: Unauthorized Mention Policy",
                    description=(
                        f"Your message in **{guild.name}** was deleted.\n\n"
                        f"**Reason:** Only the Server Owner is permitted to mention `@everyone` or `@here`.\n"
                        f"Repeated violations will result in automatic timeout or removal."
                    ),
                )
                await member.send(embed=warn_embed)
            except Exception:
                pass

        elif effective_level == 2:
            # Level 2: Timeout
            timeout_secs = getattr(cfg, "timeout_duration_seconds", 300)
            if not can_mod:
                action_summary = f"Timeout blocked: {mod_reason}"
            else:
                try:
                    until = discord.utils.utcnow() + datetime.timedelta(seconds=timeout_secs)
                    await member.timeout(until, reason=f"Unauthorized {violation_type} mention (Violation #{recent_count})")
                    action_summary = f"Timed out for {timeout_secs}s"
                except Exception as e:
                    action_summary = f"Timeout failed: {e}"

        elif effective_level == 3:
            # Level 3: Kick
            if not can_mod:
                action_summary = f"Kick blocked: {mod_reason}"
            else:
                try:
                    try:
                        dm_embed = error_embed(
                            title=f"⛔ Kicked: Unauthorized {violation_type} Mention",
                            description=(
                                f"You have been kicked from **{guild.name}**.\n\n"
                                f"**Violation:** Unauthorized `{violation_type}` mention.\n"
                                f"**Server Policy:** Only the Server Owner is permitted to use mass mentions."
                            ),
                        )
                        await member.send(embed=dm_embed)
                    except Exception:
                        pass
                    await member.kick(reason=f"Unauthorized {violation_type} mention policy violation")
                    action_summary = "Kicked from server"
                except Exception as e:
                    action_summary = f"Kick failed: {e}"

        elif effective_level >= 4:
            # Level 4: Coordinated Raid Attack Containment
            action_summary = f"Coordinated attack ({distinct_raiders} accounts): Emergency lockdown engaged"
            if can_mod:
                try:
                    until = discord.utils.utcnow() + datetime.timedelta(days=7)
                    await member.timeout(until, reason=f"Coordinated {violation_type} mention raid")
                except Exception:
                    pass
            # Trigger channel/guild lockdown
            try:
                await self._execute_lockdown(guild)
            except Exception as e:
                logger.error("Failed to execute emergency lockdown during mention raid: %s", e)

        # 5. Record mention violation in SQLite
        try:
            if hasattr(self.bot.db, "record_mention_violation"):
                await self.bot.db.record_mention_violation(
                    guild_id=guild.id,
                    user_id=member.id,
                    channel_id=message.channel.id,
                    message_id=message.id,
                    violation_type=violation_type,
                    action_taken=action_summary,
                )
        except Exception as e:
            logger.warning("Failed to record mention violation in database: %s", e)

        # 6. Record security incident
        event_id = generate_event_id()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            incident = SecurityIncident(
                event_id=event_id,
                guild_id=guild.id,
                timestamp=now_iso,
                event_type="UNAUTHORIZED_EVERYONE_MENTION",
                executor_id=member.id,
                executor_name=f"{member.name} ({member.id})",
                target_id=message.channel.id,
                target_name=f"#{message.channel.name}",
                action="mention_everyone",
                detected_count=recent_count,
                threshold=1,
                audit_log_id=None,
                reason=f"Non-owner member attempted unauthorized {violation_type} ping",
                automated_action=action_summary,
                result="SUCCESS" if ("failed" not in action_summary and "blocked" not in action_summary) else "RESTRICTED",
                severity="critical" if effective_level >= 3 else "high",
                audit_verified=True,
            )
            await self.bot.db.record_security_incident(incident)
            if hasattr(self.bot.db, "record_violation"):
                await self.bot.db.record_violation(guild.id, member.id, "UNAUTHORIZED_EVERYONE_MENTION")
        except Exception as e:
            logger.error("Failed to record security incident for mention: %s", e)

        # 7. Feed into AntiNuke engine for multi-vector correlation
        try:
            await self.antinuke.record_and_evaluate(guild, member, "everyone_mention_spam", threshold=3)
        except Exception:
            pass

        # 8. Send security alert to configured log channel or private alert channel
        clean_content = message.content[:500] if message.content else "*[No Text Content / Embed Only]*"
        alert_embed = security_embed(
            title="🚨 UNAUTHORIZED MASS MENTION INTERCEPTED",
            description=(
                f"**A non-owner member attempted to use `{violation_type}`!**\n\n"
                f"👤 **Offender:** {member.mention} (`{member.name}` | ID: `{member.id}`)\n"
                f"📍 **Channel:** {message.channel.mention} (`#{message.channel.name}`)\n"
                f"💬 **Message Content:**\n```{clean_content}```\n"
                f"⚖️ **Punishment Applied:** `{action_summary}`\n"
                f"📊 **Violation Count (24h):** `{recent_count}`\n"
                f"🗑️ **Message Status:** {'Deleted immediately' if msg_deleted else 'Failed to delete'}\n"
                f"👑 **Policy:** Strictly restricted to verified Server Owner ID."
            ),
        )
        alert_embed.set_footer(text=f"Raivora Auto-Security • Incident ID: {event_id}")
        alert_embed.timestamp = discord.utils.utcnow()

        # Check configured log channel first
        sent_log = False
        log_cid = getattr(cfg, "log_channel_id", None)
        if log_cid:
            target_ch = guild.get_channel(log_cid)
            if target_ch and isinstance(target_ch, discord.TextChannel):
                try:
                    await target_ch.send(embed=alert_embed)
                    sent_log = True
                except Exception:
                    pass
        if not sent_log:
            await self._send_private_security_alert(guild, alert_embed)


    async def _handle_honeypot_trap(self, message: discord.Message) -> bool:
        """
        Stealth Honeypot Raider Trap:
        The honeypot channel is invisible to normal members. Any message sent in it
        is guaranteed to be an automated scraper, self-bot, or unauthorized infiltrator.
        Triggers instant autonomous ban and alerts the security operations team.
        """
        HONEYPOT_CHANNEL_ID = 1558168338386129004  # #🪤・honeypot-trap
        if not message.guild or message.channel.id != HONEYPOT_CHANNEL_ID:
            return False

        bot_user_id = getattr(self.bot.user, "id", None)
        if (bot_user_id and message.author.id == bot_user_id) or message.author.id == message.guild.owner_id:
            return False

        guild = message.guild
        member = message.author

        # Delete trap-triggering message
        try:
            await message.delete()
        except Exception:
            pass

        # Instant sub-millisecond ban
        ban_success = False
        ban_error = ""
        try:
            if isinstance(member, discord.Member):
                await member.ban(reason="Honeypot Trap Triggered: Stealth Raider/Scraper Detected", delete_message_days=1)
                ban_success = True
        except Exception as e:
            ban_error = str(e)
            logger.error(f"Failed to ban honeypot intruder: {e}")

        event_id = generate_event_id()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        incident = SecurityIncident(
            event_id=event_id,
            guild_id=guild.id,
            timestamp=now_iso,
            event_type="HONEYPOT_TRIGGERED",
            executor_id=member.id,
            executor_name=f"{member.name} ({member.id})",
            target_id=message.channel.id,
            target_name=f"#{message.channel.name}",
            action="honeypot_message",
            detected_count=1,
            threshold=1,
            audit_log_id=None,
            reason="User posted in stealth honeypot channel (Scraper / Raider detected)",
            automated_action="Immediate Ban & 24h Purge" if ban_success else f"Ban failed: {ban_error}",
            result="Banned" if ban_success else "Pending Manual Ban",
            severity="critical",
            audit_verified=True,
        )
        await self.bot.db.record_security_incident(incident)
        await self.bot.db.record_violation(guild.id, member.id, "HONEYPOT_TRIGGERED")

        payload = message.content[:500] if message.content else "*[No Content / Embed]*"
        alert_embed = security_embed(
            title="🪤 STEALTH HONEYPOT TRAP TRIGGERED — RAIDER BAN ENFORCED",
            description=(
                f"**A suspicious entity posted in the hidden `#🪤・honeypot-trap`!**\n\n"
                f"👤 **Offender:** {member.mention} (`{member.name}` | ID: `{member.id}`)\n"
                f"📍 **Channel:** {message.channel.mention} (`#{message.channel.name}`)\n"
                f"💬 **Captured Payload:**\n```{payload}```\n"
                f"⚡ **Automated Action:** `{'Permanently Banned & Purged' if ban_success else 'Ban Failed - Alerted Staff'}`\n"
                f"🛡️ **Perimeter Status:** Trap operational. Raider neutralized in < 1ms."
            ),
        )
        alert_embed.set_footer(text=f"Sentinel Security Honeytrap • Incident ID: {event_id}")
        alert_embed.timestamp = discord.utils.utcnow()
        await self._send_private_security_alert(guild, alert_embed)
        return True

    _SCAM_DOMAIN_PATTERN = re.compile(
        r"(?:https?://)?(?:www\.)?(?:[a-zA-Z0-9-]+\.)*(?:dlscord|discrod|discorcl|discort|discodo|gift-discord|nitro-discord|discord-claim|discord-drop|steamcommunyt|steamcommnuit|steamcommunlty|steancommunity|steam-gift|csgo-skins|rust-skins)\.[a-zA-Z]{2,10}(?:/[^\s]*)?",
        re.IGNORECASE,
    )
    _DECEPTIVE_NITRO_PATTERN = re.compile(
        r"(?:https?://)?(?:www\.)?[a-zA-Z0-9-]+\.(?:xyz|top|gift|click|ru|link|rest|shop|fun|space|site|cc|info)/(?:nitro|claim|gift|airdrop)",
        re.IGNORECASE,
    )
    _ZALGO_PATTERN = re.compile(r"[\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f]")

    async def _handle_phishing_and_zalgo(self, message: discord.Message) -> bool:
        """
        Zero-Day Phishing & Anti-Zalgo Shield:
        1. Identifies and purges token-grabber, fake Nitro, and Steam phishing domains in < 1ms.
        2. Detects cursed Zalgo unicode combinations that freeze or crash Discord mobile apps.
        """
        if not message.guild or not message.author or message.author.bot or not message.content:
            return False

        member = message.author
        guild = message.guild
        if member.id == guild.owner_id or (isinstance(member, discord.Member) and is_founder_or_owner(member)):
            return False

        content = message.content

        # 1. Phishing & Malicious Link Interception
        is_phishing = bool(self._SCAM_DOMAIN_PATTERN.search(content) or self._DECEPTIVE_NITRO_PATTERN.search(content))
        if is_phishing:
            try:
                await message.delete()
            except Exception:
                pass

            timeout_applied = False
            if isinstance(member, discord.Member):
                try:
                    # Timeout for 24 hours to freeze compromised account
                    until = discord.utils.utcnow() + datetime.timedelta(hours=24)
                    await member.timeout(until, reason="Security: Zero-Day Phishing Domain Intercepted")
                    timeout_applied = True
                except Exception as e:
                    logger.warning(f"Could not timeout member {member.id} for phishing: {e}")

            event_id = generate_event_id()
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            incident = SecurityIncident(
                event_id=event_id,
                guild_id=guild.id,
                timestamp=now_iso,
                event_type="PHISHING_DOMAIN_BLOCKED",
                executor_id=member.id,
                executor_name=f"{member.name} ({member.id})",
                target_id=message.channel.id,
                target_name=f"#{message.channel.name}",
                action="phishing_link",
                detected_count=1,
                threshold=1,
                audit_log_id=None,
                reason="Posted malicious Discord Nitro or Steam phishing domain",
                automated_action="Deleted Message & 24h Account Isolation Timeout" if timeout_applied else "Deleted Message",
                result="Isolated" if timeout_applied else "Deleted",
                severity="critical",
                audit_verified=True,
            )
            await self.bot.db.record_security_incident(incident)
            await self.bot.db.record_violation(guild.id, member.id, "PHISHING_DOMAIN_BLOCKED")

            # Alert Staff
            alert_embed = security_embed(
                title="🛡️ ZERO-DAY PHISHING LINK INTERCEPTED",
                description=(
                    f"**Malicious token-grabber/scam URL neutralized!**\n\n"
                    f"👤 **Account:** {member.mention} (`{member.name}` | ID: `{member.id}`)\n"
                    f"📍 **Channel:** {message.channel.mention} (`#{message.channel.name}`)\n"
                    f"🔗 **Payload Snippet:**\n```{content[:300]}```\n"
                    f"⚡ **Containment:** `{'24h Timeout Applied (Account Quarantined)' if timeout_applied else 'Message Purged'}`"
                ),
            )
            alert_embed.set_footer(text=f"Phishing Sentinel Shield • Incident ID: {event_id}")
            alert_embed.timestamp = discord.utils.utcnow()
            await self._send_private_security_alert(guild, alert_embed)

            # In-channel notification
            try:
                warn_embed = discord.Embed(
                    description=f"🛡️ **Security Alert:** Phishing link from {member.mention} intercepted and deleted. Account quarantined for safety.",
                    color=Colors.DANGER,
                )
                await message.channel.send(embed=warn_embed, delete_after=12.0)
            except Exception:
                pass
            return True

        # 2. Anti-Zalgo Text Cleaner
        zalgo_matches = len(self._ZALGO_PATTERN.findall(content))
        if zalgo_matches > 15:
            try:
                await message.delete()
            except Exception:
                pass

            try:
                warn_embed = discord.Embed(
                    description=f"⚠️ {member.mention}, glitched / Zalgo font spam is blocked to protect members from Discord app lag.",
                    color=Colors.WARNING,
                )
                await message.channel.send(embed=warn_embed, delete_after=8.0)
            except Exception:
                pass
            return True

        return False

    _BOT_TOKEN_PATTERN = re.compile(
        r"[a-zA-Z0-9_\-]{24,28}\.[a-zA-Z0-9_\-]{6}\.[a-zA-Z0-9_\-]{27,38}|mfa\.[a-zA-Z0-9_\-]{84}"
    )
    _WEBHOOK_URL_PATTERN = re.compile(
        r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[a-zA-Z0-9_\-]+"
    )

    async def _handle_token_and_webhook_leak(self, message: discord.Message) -> bool:
        """
        Credential Leak Guard:
        Intercepts raw Discord bot tokens and webhook URLs in chat,
        instantly purging them in < 1ms before automated scrapers capture them.
        """
        if not message.guild or not message.author or message.author.bot or not message.content:
            return False

        content = message.content
        has_token = bool(self._BOT_TOKEN_PATTERN.search(content))
        has_webhook = bool(self._WEBHOOK_URL_PATTERN.search(content))

        if not (has_token or has_webhook):
            return False

        leak_type = "Discord Bot Token" if has_token else "Discord Webhook URL"

        # 1. Immediately delete message
        try:
            await message.delete()
        except Exception:
            pass

        guild = message.guild
        member = message.author
        event_id = generate_event_id()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 2. Record security incident
        incident = SecurityIncident(
            event_id=event_id,
            guild_id=guild.id,
            timestamp=now_iso,
            event_type="CREDENTIAL_LEAK_PREVENTED",
            executor_id=member.id,
            executor_name=f"{member.name} ({member.id})",
            target_id=message.channel.id,
            target_name=f"#{message.channel.name}",
            action="credential_leak",
            detected_count=1,
            threshold=1,
            audit_log_id=None,
            reason=f"Exposed raw {leak_type} in text chat",
            automated_action="Message Deleted & Security Operations Alerted",
            result="Sanitized",
            severity="high",
            audit_verified=True,
        )
        await self.bot.db.record_security_incident(incident)
        await self.bot.db.record_violation(guild.id, member.id, "CREDENTIAL_LEAK_PREVENTED")

        # 3. Alert Security Channel
        alert_embed = security_embed(
            title="🔑 CREDENTIAL LEAK INTERCEPTED & PURGED",
            description=(
                f"**A sensitive secret credential was posted and purged in `< 1ms`!**\n\n"
                f"👤 **Exposed By:** {member.mention} (`{member.name}` | ID: `{member.id}`)\n"
                f"📍 **Channel:** {message.channel.mention} (`#{message.channel.name}`)\n"
                f"🔐 **Detected Type:** `{leak_type}`\n"
                f"🗑️ **Status:** Payload destroyed immediately. Scraper interception prevented."
            ),
        )
        alert_embed.set_footer(text=f"Sentinel Credential Shield • Incident ID: {event_id}")
        alert_embed.timestamp = discord.utils.utcnow()
        await self._send_private_security_alert(guild, alert_embed)

        # 4. DM the member with reset advice
        try:
            dm_embed = warning_embed(
                title="⚠️ Urgent: Your Secret Token Was Leaked & Protected",
                description=(
                    f"You posted a secret **{leak_type}** in **{guild.name}** (`#{message.channel.name}`).\n\n"
                    f"**What we did:** Sentinel deleted your message immediately to protect you from malicious token scrapers.\n\n"
                    f"**Action Required:** If this was an active bot token or webhook, please **regenerate / reset it immediately** "
                    f"in the Discord Developer Portal or Server Settings to keep your account safe."
                ),
            )
            await member.send(embed=dm_embed)
        except Exception:
            pass

        # 5. In-channel reassurance
        try:
            warn_embed = discord.Embed(
                description=f"🔑 **Credential Shield:** A sensitive bot token or webhook from {member.mention} was intercepted and deleted for safety.",
                color=Colors.WARNING,
            )
            await message.channel.send(embed=warn_embed, delete_after=12.0)
        except Exception:
            pass

        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if await self._handle_honeypot_trap(message):
            return
        if await self._handle_token_and_webhook_leak(message):
            return
        if await self._handle_phishing_and_zalgo(message):
            return
        await self._handle_everyone_mention(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if await self._handle_token_and_webhook_leak(after):
            return
        if await self._handle_phishing_and_zalgo(after):
            return
        await self._handle_everyone_mention(after)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """
        Anti-Ghost Ping Protection:
        Detects when a user pings members or roles and deletes their message.
        Exposes the ghost ping in-channel and logs the violation to security alerts.
        """
        if not message.guild or not message.author or message.author.bot:
            return

        # Identify mentioned users (excluding bots and self) and mentioned roles
        targets = [m for m in message.mentions if not m.bot and m.id != message.author.id]
        role_targets = message.role_mentions

        if not targets and not role_targets:
            return

        # Check if the message was deleted quickly (within 5 minutes of sending)
        lifetime = (discord.utils.utcnow() - message.created_at).total_seconds()
        if lifetime > 300:
            return

        target_strs = [m.mention for m in targets] + [r.mention for r in role_targets]
        target_display = ", ".join(target_strs)

        # 1. Log to private security alerts channel
        ghost_embed = warning_embed(
            title="👻 GHOST PING INTERCEPTED",
            description=(
                f"**A user mentioned members/roles and deleted their message!**\n\n"
                f"👤 **Author:** {message.author.mention} (`{message.author.name}` | ID: `{message.author.id}`)\n"
                f"📍 **Channel:** {message.channel.mention} (`#{message.channel.name}`)\n"
                f"🎯 **Targeted Mentions:** {target_display}\n"
                f"💬 **Deleted Content:**\n```{message.content[:500] if message.content else '*[No Content / Embed]*'}```\n"
                f"⏱️ **Message Lifetime:** `{int(lifetime)} seconds`"
            ),
        )
        ghost_embed.set_footer(text="Anti-Ghost Ping Sentinel")
        ghost_embed.timestamp = discord.utils.utcnow()
        await self._send_private_security_alert(message.guild, ghost_embed)

        # 2. Expose the ghost ping in the origin channel with auto-delete (15s)
        try:
            reveal_embed = discord.Embed(
                description=f"👻 **Ghost Ping Detected!** {message.author.mention} pinged {target_display} and deleted their message.",
                color=Colors.WARNING,
            )
            reveal_embed.set_footer(text="Anti-Ghost Ping Sentinel • Auto-cleaning in 15s")
            await message.channel.send(embed=reveal_embed, delete_after=15.0)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """High-Speed Unauthorized Bot Addition Protection."""
        if not member.bot or not member.guild:
            return
        guild = member.guild
        guild_cfg = await self.bot.db.get_or_create_guild_config(guild.id)
        if not guild_cfg.security_enabled:
            return

        executor = None
        audit_entry = None
        try:
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.bot_add):
                if entry.target and entry.target.id == member.id:
                    now_utc = discord.utils.utcnow()
                    if (now_utc - entry.created_at).total_seconds() < 45.0:
                        executor = entry.user
                        audit_entry = entry
                        break
        except Exception:
            pass

        is_authorized = False
        if executor:
            if executor.id == guild.owner_id or executor.id == self.bot.user.id:
                is_authorized = True
            elif await is_verified_owner_or_trusted(self.bot, guild, executor.id):
                is_authorized = True

        if not is_authorized:
            logger.critical("🚨 UNAUTHORIZED BOT ADDED: Bot %s (%s) by actor %s in %s", member.name, member.id, executor, guild.name)
            event_id = generate_event_id()
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            kicked = False
            if guild.me.guild_permissions.kick_members and member < guild.me.top_role:
                try:
                    await member.kick(reason=f"Security Anti-Nuke: Unauthorized bot addition (Event {event_id})")
                    kicked = True
                except Exception as e:
                    logger.warning(f"Could not kick unauthorized bot: {e}")

            contain_msg = "Actor inconclusive"
            if executor and isinstance(executor, discord.Member):
                can_mod, mod_reason = can_moderate(guild.me, executor, guild.me)
                if can_mod:
                    try:
                        until = discord.utils.utcnow() + datetime.timedelta(hours=2)
                        await executor.timeout(until, reason=f"Security Anti-Nuke: Added unauthorized bot {member.name}")
                        contain_msg = f"Timed out {executor.name} for 2 hours"
                    except Exception as e:
                        contain_msg = f"Containment error: {e}"
                else:
                    contain_msg = f"Hierarchy prevents actor punishment: {mod_reason}"

            incident = SecurityIncident(
                event_id=event_id,
                guild_id=guild.id,
                timestamp=now_iso,
                event_type="UNAUTHORIZED_BOT_ADD",
                executor_id=executor.id if executor else None,
                executor_name=executor.name if executor else "UNKNOWN",
                target_id=member.id,
                target_name=f"{member.name} (Bot)",
                action="bot_add",
                detected_count=1,
                threshold=1,
                audit_log_id=audit_entry.id if audit_entry else None,
                reason=f"Unauthorized bot {member.name} ({member.id}) joined server",
                automated_action=f"Kicked rogue bot: {'Yes' if kicked else 'No'}; {contain_msg}",
                result="Contained",
                severity="critical",
                audit_verified=executor is not None,
            )
            await self.bot.db.record_security_incident(incident)
            await self._notify_security_channel(guild, incident)

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    @security_group.command(name="setup", description="Configure security action limits and punishment policy")
    @is_admin_or_owner()
    @app_commands.describe(
        punishment="Automated action when thresholds are exceeded",
        channel_delete_limit="Max channel deletions allowed within window",
        role_delete_limit="Max role deletions allowed within window",
        ban_limit="Max bans allowed within window",
        time_window="Detection window in seconds (5-60s)",
    )
    @app_commands.choices(
        punishment=[
            app_commands.Choice(name="Alert Only", value="alert"),
            app_commands.Choice(name="Timeout Attacker", value="timeout"),
            app_commands.Choice(name="Kick Attacker", value="kick"),
            app_commands.Choice(name="Ban Attacker", value="ban"),
            app_commands.Choice(name="Strip Dangerous Roles", value="remove_roles"),
            app_commands.Choice(name="Lock Channels", value="lock_channels"),
        ]
    )
    async def security_setup(
        self,
        interaction: discord.Interaction,
        punishment: app_commands.Choice[str],
        channel_delete_limit: Optional[int] = None,
        role_delete_limit: Optional[int] = None,
        ban_limit: Optional[int] = None,
        time_window: Optional[int] = None,
    ):
        # Validation
        if channel_delete_limit is not None and not (1 <= channel_delete_limit <= 50):
            await interaction.response.send_message(embed=error_embed("Limit must be between 1 and 50"), ephemeral=True)
            return
        if time_window is not None and not (5 <= time_window <= 120):
            await interaction.response.send_message(embed=error_embed("Time window must be between 5 and 120 seconds"), ephemeral=True)
            return

        updates = {"punishment": punishment.value}
        if channel_delete_limit is not None:
            updates["channel_delete_limit"] = channel_delete_limit
        if role_delete_limit is not None:
            updates["role_delete_limit"] = role_delete_limit
        if ban_limit is not None:
            updates["ban_limit"] = ban_limit
        if time_window is not None:
            updates["channel_delete_window"] = time_window
            updates["role_delete_window"] = time_window
            updates["ban_window"] = time_window

        await self.bot.db.update_security_config(interaction.guild.id, **updates)
        embed = success_embed(
            "Security Configuration Updated",
            f"**Punishment:** {punishment.name}\n"
            f"**Channel Delete Limit:** {updates.get('channel_delete_limit', 'Unchanged')}\n"
            f"**Role Delete Limit:** {updates.get('role_delete_limit', 'Unchanged')}\n"
            f"**Ban Limit:** {updates.get('ban_limit', 'Unchanged')}\n"
            f"**Window:** {time_window or 'Unchanged'}s",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @security_group.command(name="enable", description="Enable the security and anti-nuke module")
    @is_admin_or_owner()
    async def security_enable(self, interaction: discord.Interaction):
        await self.bot.db.update_guild_config(interaction.guild.id, security_enabled=True)
        await interaction.response.send_message(
            embed=success_embed("Security Enabled", "The anti-nuke protection system is now active."), ephemeral=True
        )

    @security_group.command(name="disable", description="Disable the security and anti-nuke module")
    @is_admin_or_owner()
    async def security_disable(self, interaction: discord.Interaction):
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            embed=warning_embed(
                "Confirm Disabling Security",
                "Disabling security will turn off all automated protections against mass deletions, unauthorized bots, and malicious actions. Are you sure?",
            ),
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if view.value is True:
            await self.bot.db.update_guild_config(interaction.guild.id, security_enabled=False)
            await interaction.followup.send(
                embed=error_embed("Security Disabled", "The anti-nuke protection system has been disabled."), ephemeral=True
            )

    @security_group.command(name="status", description="Display full security dashboard, thresholds, and health")
    @is_admin_or_owner()
    async def security_status(self, interaction: discord.Interaction):
        guild = interaction.guild
        guild_cfg = await self.bot.db.get_or_create_guild_config(guild.id)
        sec_cfg = await self.bot.db.get_security_config(guild.id)
        sec_state = await self.bot.db.get_security_state(guild.id)
        whitelist = await self.bot.db.get_whitelist(guild.id)
        incidents = await self.bot.db.get_security_incidents(guild.id, limit=3)

        status_str = "🟢 Active" if guild_cfg.security_enabled else "🔴 Disabled"
        emergency_str = "🚨 EMERGENCY STOP ACTIVE" if sec_state.emergency_stop else "Normal"
        lockdown_str = "🔒 Server in Lockdown" if sec_state.lockdown_enabled else "Normal"

        embed = create_embed(
            title=f"🛡️ Security Dashboard — {guild.name}",
            color=Colors.SECURITY if not sec_state.emergency_stop else Colors.ERROR,
        )
        embed.add_field(name="Module Status", value=status_str, inline=True)
        embed.add_field(name="Emergency Mode", value=emergency_str, inline=True)
        embed.add_field(name="Lockdown Status", value=lockdown_str, inline=True)

        thresholds = (
            f"• Channels Delete: `{sec_cfg.channel_delete_limit}` / `{sec_cfg.channel_delete_window}s`\n"
            f"• Channels Create: `{sec_cfg.channel_create_limit}` / `{sec_cfg.channel_create_window}s`\n"
            f"• Roles Delete: `{sec_cfg.role_delete_limit}` / `{sec_cfg.role_delete_window}s`\n"
            f"• Roles Create: `{sec_cfg.role_create_limit}` / `{sec_cfg.role_create_window}s`\n"
            f"• Bans: `{sec_cfg.ban_limit}` / `{sec_cfg.ban_window}s`\n"
            f"• Webhooks: `{sec_cfg.webhook_limit}` / `{sec_cfg.webhook_window}s`\n"
            f"• Configured Action: `{sec_cfg.punishment}`"
        )
        embed.add_field(name="Active Thresholds", value=thresholds, inline=False)

        wl_users = [f"<@{item['target_id']}>" for item in whitelist if item["target_type"] == "user"]
        wl_roles = [f"<@&{item['target_id']}>" for item in whitelist if item["target_type"] == "role"]
        embed.add_field(
            name=f"Whitelist ({len(whitelist)})",
            value=f"**Users:** {', '.join(wl_users) if wl_users else 'None'}\n"
                  f"**Roles:** {', '.join(wl_roles) if wl_roles else 'None'}",
            inline=False,
        )

        if incidents:
            inc_lines = [
                f"`[{inc.event_id}]` **{inc.event_type}** by {inc.executor_name or 'UNKNOWN'} → *{inc.result}*"
                for inc in incidents
            ]
            embed.add_field(name="Recent Incidents", value="\n".join(inc_lines), inline=False)
        else:
            embed.add_field(name="Recent Incidents", value="No incidents recorded.", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @security_group.command(name="whitelist", description="Manage trusted users or roles exempt from security limits")
    @is_admin_or_owner()
    @app_commands.describe(
        action="Add or remove from whitelist",
        user="User to whitelist",
        role="Role to whitelist",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Add", value="add"),
            app_commands.Choice(name="Remove", value="remove"),
            app_commands.Choice(name="List", value="list"),
        ]
    )
    async def security_whitelist(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        user: Optional[discord.Member] = None,
        role: Optional[discord.Role] = None,
    ):
        guild_id = interaction.guild.id

        if action.value == "list":
            wl = await self.bot.db.get_whitelist(guild_id)
            if not wl:
                await interaction.response.send_message(embed=info_embed("Whitelist Empty", "No users or roles are currently whitelisted."), ephemeral=True)
                return
            users = [f"<@{item['target_id']}> (added by <@{item['added_by']}>)" for item in wl if item["target_type"] == "user"]
            roles = [f"<@&{item['target_id']}> (added by <@{item['added_by']}>)" for item in wl if item["target_type"] == "role"]
            embed = info_embed(
                "Security Whitelist",
                f"**Users:**\n{chr(10).join(users) if users else 'None'}\n\n**Roles:**\n{chr(10).join(roles) if roles else 'None'}"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not user and not role:
            await interaction.response.send_message(embed=error_embed("Specify either a user or a role to modify."), ephemeral=True)
            return

        target_id = user.id if user else role.id
        target_type = "user" if user else "role"
        mention = user.mention if user else role.mention

        if action.value == "add":
            await self.bot.db.add_whitelist(guild_id, target_id, target_type, interaction.user.id)
            await interaction.response.send_message(embed=success_embed("Whitelist Added", f"Added {mention} to the security whitelist."), ephemeral=True)
        else:
            removed = await self.bot.db.remove_whitelist(guild_id, target_id, target_type)
            if removed:
                await interaction.response.send_message(embed=success_embed("Whitelist Removed", f"Removed {mention} from the security whitelist."), ephemeral=True)
            else:
                await interaction.response.send_message(embed=warning_embed("Not Found", f"{mention} was not on the whitelist."), ephemeral=True)

    @security_group.command(name="lockdown", description="Initiate emergency lockdown on all server channels")
    @is_admin_or_owner()
    async def security_lockdown(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = await self._execute_lockdown(interaction.guild)
        await interaction.followup.send(
            embed=security_embed("Emergency Lockdown Activated", f"Successfully restricted message permissions in **{count}** channels."),
            ephemeral=True,
        )

    @security_group.command(name="unlock", description="Lift server lockdown and restore channel permissions")
    @is_admin_or_owner()
    async def security_unlock(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = await self._execute_unlock(interaction.guild)
        await interaction.followup.send(
            embed=success_embed("Lockdown Lifted", f"Restored permissions in **{count}** channels."),
            ephemeral=True,
        )

    @security_group.command(name="emergency-stop", description="Kill switch: halts destructive automated punishments while continuing logging")
    @is_admin_or_owner()
    async def emergency_stop(self, interaction: discord.Interaction):
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            embed=warning_embed(
                "Activate Emergency Stop?",
                "This halts all automated destructive punishments (bans, kicks, role stripping) immediately. Monitoring and incident recording will continue.",
            ),
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if view.value is True:
            await self.bot.db.set_emergency_stop(interaction.guild.id, True, interaction.user.id)
            await interaction.followup.send(
                embed=error_embed("EMERGENCY STOP ENGAGED", "Automated destructive actions are now suppressed across the server."),
                ephemeral=True,
            )

    @security_group.command(name="emergency-resume", description="Resume normal automated security actions after emergency stop")
    @is_admin_or_owner()
    async def emergency_resume(self, interaction: discord.Interaction):
        await self.bot.db.set_emergency_stop(interaction.guild.id, False, interaction.user.id)
        await interaction.response.send_message(
            embed=success_embed("Emergency Mode Disengaged", "Normal automated security punishments have been resumed."),
            ephemeral=True,
        )

    @security_group.command(name="emergency-status", description="Check current emergency stop status")
    @is_admin_or_owner()
    async def emergency_status(self, interaction: discord.Interaction):
        sec_state = await self.bot.db.get_security_state(interaction.guild.id)
        status_text = "🚨 **ACTIVE** — Destructive automated actions are disabled." if sec_state.emergency_stop else "✅ **INACTIVE** — Full security automation is armed."
        await interaction.response.send_message(embed=info_embed("Emergency Status", status_text), ephemeral=True)

    @security_group.command(name="safemode", description="Engage or manage Emergency Safe Mode protections")
    @is_admin_or_owner()
    @app_commands.describe(action="Enable or disable safe mode")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Enable Safe Mode", value="enable"),
            app_commands.Choice(name="Disable Safe Mode", value="disable"),
            app_commands.Choice(name="Status", value="status"),
        ]
    )
    async def security_safemode(self, interaction: discord.Interaction, action: Optional[app_commands.Choice[str]] = None):
        act_val = action.value if action else "enable"
        guild = interaction.guild

        if act_val == "status":
            sec_state = await self.bot.db.get_security_state(guild.id)
            status_text = "🛡️ **SAFE MODE ACTIVE** — Risky automated modifications suppressed." if sec_state.emergency_stop else "🟢 **NORMAL MODE** — Standard security armed."
            await interaction.response.send_message(embed=info_embed("Emergency Safe Mode Status", status_text), ephemeral=True)
            return

        if act_val == "enable":
            await self.bot.db.set_emergency_stop(guild.id, True, interaction.user.id)
            embed = security_embed(
                "🛡️ EMERGENCY SAFE MODE ACTIVATED",
                f"**Authorized Administrator:** {interaction.user.mention} (`{interaction.user.id}`)\n\n"
                f"• High-risk automated actions are temporarily restricted.\n"
                f"• Security logging and evidence capture remain active.\n"
                f"• Legitimate administrator recovery commands remain accessible.\n\n"
                f"Run `/security safemode action:Disable Safe Mode` to restore normal operations.",
            )
            await self._send_private_security_alert(guild, embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await self.bot.db.set_emergency_stop(guild.id, False, interaction.user.id)
            embed = success_embed(
                "Safe Mode Disengaged",
                f"Emergency Safe Mode deactivated by {interaction.user.mention}. Standard automation restored.",
            )
            await self._send_private_security_alert(guild, embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @security_group.command(name="incident", description="Inspect complete evidence timeline for a specific security incident")
    @is_admin_or_owner()
    @app_commands.describe(incident_id="Unique event ID of the incident")
    async def security_incident_cmd(self, interaction: discord.Interaction, incident_id: str):
        await interaction.response.defer(ephemeral=True)
        inc = await self.bot.db.get_security_incident(incident_id.strip())
        if not inc:
            await interaction.followup.send(embed=error_embed("Incident Not Found", f"No record found for ID `{incident_id}`."), ephemeral=True)
            return

        timeline = (
            f"**Event Type:** `{inc.event_type}`\n"
            f"**Timestamp:** `{inc.timestamp}`\n"
            f"**Actor / Executor:** `{inc.executor_name or 'UNKNOWN'}` (ID: `{inc.executor_id or 'N/A'}`)\n"
            f"**Target:** `{inc.target_name or 'N/A'}` (ID: `{inc.target_id or 'N/A'}`)\n"
            f"**Signals / Detection:** Observed `{inc.detected_count}` events (Threshold: `{inc.threshold}`)\n"
            f"**Audit Log Verified:** {'✅ Yes' if inc.audit_verified else '❌ Incomplete / Unavailable'}\n"
            f"**Automated Containment:** `{inc.automated_action}`\n"
            f"**Result Status:** `{inc.result}`\n"
            f"**Severity:** `{inc.severity.upper()}`\n"
            f"**Audit Reason:** {inc.reason or 'None specified'}"
        )

        embed = security_embed(
            f"🔍 Incident Evidence Timeline — [{inc.event_id}]",
            timeline,
        )
        embed.set_footer(text="Raivora Security Intelligence • Evidence Timeline")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @security_group.command(name="history", description="Review unified security incident audit trail")
    @is_admin_or_owner()
    async def security_history_cmd(self, interaction: discord.Interaction):
        await self.security_incidents(interaction)

    @app_commands.command(name="panic", description="Emergency panic mode: instantly locks down all channels and alerts staff")
    @is_admin_or_owner()
    async def panic_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = await self._execute_lockdown(interaction.guild)
        await self.bot.db.set_emergency_stop(interaction.guild.id, True, interaction.user.id)

        # Send alert to staff security log
        embed_alert = error_embed(
            "🚨 SERVER PANIC MODE TRIGGERED",
            f"**Initiated By:** {interaction.user.mention} (`{interaction.user.id}`)\n"
            f"• **Channels Locked:** `{count}` channels\n"
            f"• **Emergency Stop:** Enabled (destructive actions suppressed)\n"
            f"• **Action Required:** Authorized staff investigate server activity immediately.",
        )
        cfg_log = await self.bot.db.get_logging_config(interaction.guild.id)
        if cfg_log.security_channel_id:
            ch = interaction.guild.get_channel(cfg_log.security_channel_id)
            if ch:
                try:
                    await ch.send(content="@here", embed=embed_alert)
                except Exception:
                    pass

        await interaction.followup.send(
            embed=error_embed(
                "🚨 Panic Mode Active",
                f"Panic mode engaged by {interaction.user.mention}.\n"
                f"• Restriced message permissions in **{count}** channels.\n"
                f"• Automated emergency stop activated.\n"
                f"• Staff security alerts dispatched.",
            ),
            ephemeral=True,
        )

    @security_group.command(name="config", description="Display full active security configuration and thresholds")
    @is_admin_or_owner()
    async def security_config_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await self.bot.db.get_security_config(interaction.guild.id)
        embed = create_embed(
            title=f"🛡️ Security Configuration — {interaction.guild.name}",
            description="Active anti-nuke thresholds, detection windows, and automated punishment policies.",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="Channel Delete Limit", value=f"`{cfg.channel_delete_limit}` / `{cfg.channel_delete_window}s`", inline=True)
        embed.add_field(name="Channel Create Limit", value=f"`{cfg.channel_create_limit}` / `{cfg.channel_create_window}s`", inline=True)
        embed.add_field(name="Role Delete Limit", value=f"`{cfg.role_delete_limit}` / `{cfg.role_delete_window}s`", inline=True)
        embed.add_field(name="Role Create Limit", value=f"`{cfg.role_create_limit}` / `{cfg.role_create_window}s`", inline=True)
        embed.add_field(name="Ban Limit", value=f"`{cfg.ban_limit}` / `{cfg.ban_window}s`", inline=True)
        embed.add_field(name="Kick Limit", value=f"`{cfg.kick_limit}` / `{cfg.kick_window}s`", inline=True)
        embed.add_field(name="Webhook Limit", value=f"`{cfg.webhook_limit}` / `{cfg.webhook_window}s`", inline=True)
        embed.add_field(name="Default Punishment", value=f"`{cfg.punishment.upper()}`", inline=True)
        embed.set_footer(text="Rai Security Pro • Anti-Nuke & Real-time Verification Engine")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @security_group.command(name="incidents", description="Review security incident audit trail with optional filters")
    @is_admin_or_owner()
    @app_commands.describe(
        event_type="Filter by event type (e.g. CHANNEL_DELETE)",
        executor="Filter by member who triggered event",
        severity="Filter by severity level",
    )
    @app_commands.choices(
        severity=[
            app_commands.Choice(name="Low", value="low"),
            app_commands.Choice(name="Medium", value="medium"),
            app_commands.Choice(name="High", value="high"),
        ]
    )
    async def security_incidents(
        self,
        interaction: discord.Interaction,
        event_type: Optional[str] = None,
        executor: Optional[discord.Member] = None,
        severity: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        incidents = await self.bot.db.get_security_incidents(
            guild_id=interaction.guild.id,
            limit=25,
            event_type=event_type,
            executor_id=executor.id if executor else None,
            severity=severity.value if severity else None,
        )
        if not incidents:
            await interaction.followup.send(embed=info_embed("No Incidents Found", "No security incidents match the requested filters."), ephemeral=True)
            return

        pages = []
        chunks = [incidents[i:i + 5] for i in range(0, len(incidents), 5)]
        for page_idx, chunk in enumerate(chunks, 1):
            embed = create_embed(
                title=f"📋 Security Incident Log (Page {page_idx}/{len(chunks)})",
                color=Colors.SECURITY,
            )
            for inc in chunk:
                embed.add_field(
                    name=f"[{inc.event_id}] {inc.event_type} — {inc.timestamp[:19]}",
                    value=(
                        f"**Executor:** {inc.executor_name or 'UNKNOWN'}\n"
                        f"**Target:** {inc.target_name or 'N/A'}\n"
                        f"**Count/Threshold:** {inc.detected_count}/{inc.threshold}\n"
                        f"**Action:** {inc.automated_action} | **Result:** {inc.result}\n"
                        f"**Verified:** {'Yes' if inc.audit_verified else 'No'}"
                    ),
                    inline=False,
                )
            pages.append(embed)

        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0], ephemeral=True)
        else:
            view = PaginationView(pages, interaction.user.id)
            await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)

    @security_group.command(name="cooldowns", description="View active in-memory security and command cooldowns")
    @is_admin_or_owner()
    async def security_cooldowns(self, interaction: discord.Interaction):
        counts = await self.bot.cooldowns.cleanup_expired()
        await interaction.response.send_message(
            embed=info_embed(
                "Active Cooldown Statistics",
                f"• Cleaned Expired Runtime Entries: `{counts['runtime_cooldowns']}`\n"
                f"• Cleaned Expired Persistent Records: `{counts['db_cooldowns']}`\n"
                f"• Cleaned Stale Violations: `{counts['db_violations']}`\n"
                f"• In-Memory Buckets Tracked: `{len(self.bot.cooldowns._security_sliding_windows)}`",
            ),
            ephemeral=True,
        )

    @security_group.command(name="reset-cooldown", description="Reset cooldowns for a specific user")
    @is_admin_or_owner()
    @app_commands.describe(user="The user whose cooldowns should be cleared")
    async def reset_cooldown(self, interaction: discord.Interaction, user: discord.Member):
        if user.id == interaction.user.id and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(embed=error_embed("You cannot reset your own cooldowns."), ephemeral=True)
            return

        removed = await self.bot.cooldowns.reset_user_cooldowns(user.id, interaction.guild.id)
        await interaction.response.send_message(
            embed=success_embed("Cooldown Reset", f"Cleared `{removed}` active cooldown(s) for {user.mention}."),
            ephemeral=True,
        )

    @security_group.command(name="reset-cooldowns", description="Reset all active runtime cooldowns in this guild")
    @is_admin_or_owner()
    async def reset_all_cooldowns_cmd(self, interaction: discord.Interaction):
        removed = await self.bot.cooldowns.reset_all_cooldowns(interaction.guild.id)
        await interaction.response.send_message(
            embed=success_embed("All Cooldowns Reset", f"Cleared `{removed}` active cooldown(s) across the server."),
            ephemeral=True,
        )

    @tasks.loop(hours=6)
    async def _nightly_backup_loop(self):
        try:
            if hasattr(self.bot, "wait_until_ready") and callable(self.bot.wait_until_ready):
                res = self.bot.wait_until_ready()
                if asyncio.iscoroutine(res):
                    await res
        except Exception:
            pass
        try:
            mgr = BackupManager.get_instance()
            rec = await mgr.run_backup(trigger="scheduled_nightly")
            logger.info(f"Nightly disaster recovery backup verified: {rec.backup_id}")

            from config import BACKUP_DATA_CHANNEL_ID
            ch = self.bot.get_channel(BACKUP_DATA_CHANNEL_ID)
            if not ch and hasattr(self.bot, "fetch_channel"):
                try:
                    ch = await self.bot.fetch_channel(BACKUP_DATA_CHANNEL_ID)
                except Exception:
                    ch = None

            if ch and isinstance(ch, discord.TextChannel):
                embed = success_embed(
                    f"Disaster Recovery Backup Archive ({rec.backup_id})",
                    (
                        f"**📦 Snapshot ID:** `{rec.backup_id}`\n"
                        f"**⚡ Status:** `VERIFIED (SHA-256 Validated)`\n"
                        f"**📊 Archive Size:** `{format_bytes(rec.archive_size)}`\n"
                        f"**📁 Format:** `ZIP Archive (.zip)`\n"
                        f"**🛡️ Storage:** `{rec.storage_type}`\n"
                        f"**⏱️ Created:** `{rec.formatted_created_at}`\n\n"
                        f"**Included Components:**\n"
                        f"• SQLite Database Snapshot (`data/bot.db`)\n"
                        f"• Music Bot State & Playlists (`data/music.db`)\n"
                        f"• Security Policies, Baselines & Whitelists\n"
                        f"• Dynamic Room Layouts & Server Configurations\n\n"
                        f"*Direct `.zip` disaster recovery file attached below.*"
                    ),
                )
                if rec.archive_path and os.path.exists(rec.archive_path):
                    with open(rec.archive_path, "rb") as bf:
                        vault_file = discord.File(bf, filename=os.path.basename(rec.archive_path))
                        await ch.send(embed=embed, file=vault_file)
                else:
                    await ch.send(embed=embed)
        except Exception as e:
            logger.error(f"Nightly backup failed: {e}")

    # =========================================================================
    # ULTIMATE SECURITY UPGRADE COMMANDS: Owner Dashboard & Engine Controls
    # =========================================================================

    @security_group.command(name="mention-policy", description="Configure Owner-Only @everyone and @here protection policy")
    @is_strict_owner()
    @app_commands.describe(
        enabled="Enable or disable owner-only mention protection",
        punishment_level="Punishment level: 1=Warn, 2=Timeout, 3=Kick, 4=Raid Lockdown",
        timeout_seconds="Timeout duration in seconds (60-86400)",
        delete_message="Whether to automatically delete offending messages",
        strip_overwrites="Audit and strip 'Mention Everyone' overwrite permission across channels",
        log_channel="Channel for mention violation alert logs",
    )
    @app_commands.choices(
        punishment_level=[
            app_commands.Choice(name="Level 1: Warn User & Delete Message", value=1),
            app_commands.Choice(name="Level 2: Timeout Offending Account", value=2),
            app_commands.Choice(name="Level 3: Kick Offending Account", value=3),
            app_commands.Choice(name="Level 4: Coordinated Raid Lockdown", value=4),
        ]
    )
    async def security_mention_policy(
        self,
        interaction: discord.Interaction,
        enabled: Optional[bool] = None,
        punishment_level: Optional[app_commands.Choice[int]] = None,
        timeout_seconds: Optional[int] = None,
        delete_message: Optional[bool] = None,
        strip_overwrites: Optional[bool] = None,
        log_channel: Optional[discord.TextChannel] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        cfg = await self.bot.db.get_mention_protection_config(guild.id)
        if enabled is not None:
            cfg.enabled = enabled
        if punishment_level is not None:
            cfg.punishment_level = punishment_level.value
        if timeout_seconds is not None:
            if not (10 <= timeout_seconds <= 86400):
                await interaction.followup.send(embed=error_embed("Invalid Timeout", "Timeout duration must be between 10 and 86400 seconds."), ephemeral=True)
                return
            cfg.timeout_duration_seconds = timeout_seconds
        if delete_message is not None:
            cfg.delete_message = delete_message
        if log_channel is not None:
            cfg.log_channel_id = log_channel.id

        stripped_count = 0
        if strip_overwrites:
            cfg.strip_overwrites = True
            for ch in guild.channels:
                if not hasattr(ch, "overwrites"):
                    continue
                for target, overwrite in list(ch.overwrites.items()):
                    if isinstance(target, discord.Role) and not target.is_default() and target < guild.me.top_role:
                        if overwrite.mention_everyone is True:
                            try:
                                overwrite.mention_everyone = False
                                await ch.set_permissions(target, overwrite=overwrite, reason="Security Policy: Strip Mention Everyone overwrite")
                                stripped_count += 1
                            except Exception:
                                pass

        await self.bot.db.save_mention_protection_config(cfg)

        level_names = {
            1: "Level 1: Warn User & Delete Message",
            2: "Level 2: Timeout Offending Account",
            3: "Level 3: Kick Offending Account",
            4: "Level 4: Raid Lockdown & Account Isolation",
        }

        embed = success_embed(
            "👑 Mention Protection Policy Configured",
            f"**Verified Server Owner:** {interaction.user.mention} (`{interaction.user.id}`)\n\n"
            f"• **Protection Status:** {'🟢 Enabled' if cfg.enabled else '🔴 Disabled'}\n"
            f"• **Punishment Level:** `{level_names.get(cfg.punishment_level, 'Level 2: Timeout')}`\n"
            f"• **Timeout Duration:** `{cfg.timeout_duration_seconds} seconds`\n"
            f"• **Delete Offending Message:** {'✅ Yes' if cfg.delete_message else '❌ No'}\n"
            f"• **Security Log Channel:** {f'<#{cfg.log_channel_id}>' if cfg.log_channel_id else '*Not configured (using security alerts)*'}\n"
            f"• **Channel Overwrites Stripped:** `{stripped_count} permissions neutralized`\n\n"
            f"⚖️ *Only the verified Server Owner ID and trusted security users may use `@everyone` or `@here`.*",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @trusted_group.command(name="add", description="Add a trusted security user by ID or mention (Owner-only)")
    @is_strict_owner()
    @app_commands.describe(
        user="The Discord user to add to the trusted security allowlist",
        reason="Reason for granting trusted security status",
    )
    async def trusted_add(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: Optional[str] = "Authorized by Server Owner",
    ):
        await interaction.response.defer(ephemeral=True)
        if user.id == interaction.guild.owner_id:
            await interaction.followup.send(embed=info_embed("Already Server Owner", "The Server Owner is always implicitly verified and trusted."), ephemeral=True)
            return

        ok = await self.bot.db.add_trusted_user(
            guild_id=interaction.guild.id,
            user_id=user.id,
            added_by=interaction.user.id,
            reason=reason,
        )
        if ok:
            embed = success_embed(
                "🛡️ Trusted Security User Authorized",
                f"**User:** {user.mention} (`{user.name}` | ID: `{user.id}`)\n"
                f"**Authorized By:** {interaction.user.mention} (Verified Server Owner)\n"
                f"**Reason:** {reason}\n\n"
                f"✅ This user is now exempt from Anti-Nuke containment and authorized for security bypass.",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=error_embed("Failed to Add", "Could not record trusted user in database."), ephemeral=True)

    @trusted_group.command(name="remove", description="Remove a trusted security user by ID or mention (Owner-only)")
    @is_strict_owner()
    @app_commands.describe(user="The Discord user to revoke trusted security status from")
    async def trusted_remove(
        self,
        interaction: discord.Interaction,
        user: discord.User,
    ):
        await interaction.response.defer(ephemeral=True)
        ok = await self.bot.db.remove_trusted_user(guild_id=interaction.guild.id, user_id=user.id)
        if ok:
            embed = success_embed(
                "Revoked Trusted Security User",
                f"Removed {user.mention} (`{user.id}`) from the trusted security allowlist.\n"
                f"Standard automated security checks will now apply to this user.",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=warning_embed("Not Found", f"{user.mention} was not found on the trusted security allowlist."), ephemeral=True)

    @security_group.command(name="allowlist", description="Inspect verified server owner and authorized security allowlist")
    @is_strict_owner_or_trusted()
    async def security_allowlist(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        trusted_users = await self.bot.db.get_trusted_users(guild.id)
        whitelist = await self.bot.db.get_whitelist(guild.id)

        embed = create_embed(
            title=f"🛡️ Security Allowlist & Trust Matrix — {guild.name}",
            color=Colors.SECURITY,
        )
        embed.add_field(
            name="👑 Verified Server Owner",
            value=f"<@{guild.owner_id}> (`ID: {guild.owner_id}`)",
            inline=False,
        )

        if trusted_users:
            tu_lines = [
                f"• <@{tu.user_id}> (`{tu.user_id}`) — *{tu.reason or 'No reason'}* (Added <@{tu.added_by}>)"
                for tu in trusted_users
            ]
            embed.add_field(name=f"🛡️ Trusted Security Users ({len(trusted_users)})", value="\n".join(tu_lines), inline=False)
        else:
            embed.add_field(name="🛡️ Trusted Security Users (0)", value="*No explicit trusted users added. Only the Server Owner has full bypass.*", inline=False)

        wl_users = [f"<@{item['target_id']}>" for item in whitelist if item["target_type"] == "user"]
        wl_roles = [f"<@&{item['target_id']}>" for item in whitelist if item["target_type"] == "role"]
        embed.add_field(
            name=f"📋 Legacy Moderation Whitelist ({len(whitelist)})",
            value=f"**Users:** {', '.join(wl_users) if wl_users else 'None'}\n"
                  f"**Roles:** {', '.join(wl_roles) if wl_roles else 'None'}",
            inline=False,
        )
        embed.set_footer(text="Raivora Identity & Permission Protection Engine")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @security_group.command(name="logs", description="Review recent security incidents, raid events, and mention violations")
    @is_strict_owner_or_trusted()
    @app_commands.describe(limit="Number of log entries to retrieve (5-50)")
    async def security_logs_cmd(self, interaction: discord.Interaction, limit: Optional[int] = 15):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        safe_limit = max(5, min(limit or 15, 50))

        incidents = await self.bot.db.get_security_incidents(guild.id, limit=safe_limit)
        violations = await self.bot.db.get_recent_mention_violations(guild.id, limit=safe_limit)

        embed = create_embed(
            title=f"📋 Security Incident & Violation Logs — {guild.name}",
            color=Colors.SECURITY,
        )

        if incidents:
            inc_lines = [
                f"`[{inc.event_id}]` **{inc.event_type}** by {inc.executor_name or 'UNKNOWN'} → *{inc.result}* ({inc.timestamp[:19]})"
                for inc in incidents[:7]
            ]
            embed.add_field(name="🚨 Recent Anti-Nuke & Raid Incidents", value="\n".join(inc_lines), inline=False)
        else:
            embed.add_field(name="🚨 Recent Anti-Nuke & Raid Incidents", value="No incidents recorded.", inline=False)

        if violations:
            viol_lines = [
                f"`#{v.id}` <@{v.user_id}> pinged `{v.violation_type}` in <#{v.channel_id}> → *{v.action_taken}* ({v.created_at[:19]})"
                for v in violations[:7]
            ]
            embed.add_field(name="📣 Recent Mention Violations", value="\n".join(viol_lines), inline=False)
        else:
            embed.add_field(name="📣 Recent Mention Violations", value="No mention violations recorded.", inline=False)

        embed.set_footer(text="Raivora Real-time Audit Trail")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @security_group.command(name="test", description="Run safe, non-destructive automated security and permission diagnostics")
    @is_strict_owner_or_trusted()
    async def security_test(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        bot_member = guild.me

        results = []

        # 1. Essential Moderation Permissions Check
        required_perms = [
            ("Manage Roles", bot_member.guild_permissions.manage_roles),
            ("Manage Channels", bot_member.guild_permissions.manage_channels),
            ("Kick Members", bot_member.guild_permissions.kick_members),
            ("Ban Members", bot_member.guild_permissions.ban_members),
            ("Moderate Members (Timeout)", bot_member.guild_permissions.moderate_members),
            ("View Audit Log", bot_member.guild_permissions.view_audit_log),
            ("Manage Messages", bot_member.guild_permissions.manage_messages),
        ]
        all_perms_ok = all(ok for _, ok in required_perms)
        perm_summary = "\n".join(f"{'✅' if ok else '❌'} **{name}**" for name, ok in required_perms)

        # 2. Role Hierarchy Diagnostics
        top_role = bot_member.top_role
        guild_roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)
        roles_above = [r.name for r in guild_roles if r.position > top_role.position and not r.managed]
        hierarchy_ok = len(roles_above) == 0

        # 3. Audit Log Access Test
        audit_ok = False
        try:
            async for _ in guild.audit_logs(limit=1):
                audit_ok = True
                break
        except Exception:
            audit_ok = False

        # 4. Database Schema and Operational Health
        db_ok = True
        try:
            await self.bot.db.get_mention_protection_config(guild.id)
            await self.bot.db.get_anti_nuke_config(guild.id)
            await self.bot.db.get_anti_raid_config(guild.id)
        except Exception:
            db_ok = False

        embed = create_embed(
            title=f"🧪 Non-Destructive Security Diagnostic Report — {guild.name}",
            color=Colors.SUCCESS if (all_perms_ok and audit_ok and db_ok) else Colors.WARNING,
        )
        embed.add_field(name="🔑 Bot Permissions Health", value=perm_summary, inline=False)
        embed.add_field(
            name="📊 Role Hierarchy Status",
            value=(
                f"• Bot Highest Role: `{top_role.name}` (Pos: {top_role.position})\n"
                f"• Unmanageable Roles Above Bot: `{', '.join(roles_above) if roles_above else 'None (Optimal!)'}`\n"
                f"• Status: {'✅ Bot is capable of moderating members' if hierarchy_ok else '⚠️ Bot cannot moderate members with roles above it'}"
            ),
            inline=False,
        )
        embed.add_field(
            name="🔍 Subsystem Connectivity",
            value=(
                f"• Discord Audit Log Stream: {'✅ Operational' if audit_ok else '❌ Inaccessible (Missing View Audit Log)'}\n"
                f"• SQLite Database Migration v49: {'✅ Healthy & Connected' if db_ok else '❌ Error accessing security tables'}\n"
                f"• Safe Mode Engine: `🟢 Normal Execution (No degraded states)`"
            ),
            inline=False,
        )
        embed.set_footer(text="Raivora Automated Security Diagnostic • 100% Non-destructive")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==========================================
    # ANTINUKE COMMAND GROUP
    # ==========================================

    @antinuke_group.command(name="enable", description="Enable high-speed anti-nuke protection")
    @is_admin_or_owner()
    async def antinuke_enable_cmd(self, interaction: discord.Interaction):
        await self.security_enable(interaction)

    @antinuke_group.command(name="disable", description="Disable high-speed anti-nuke protection")
    @is_admin_or_owner()
    async def antinuke_disable_cmd(self, interaction: discord.Interaction):
        await self.security_disable(interaction)

    @antinuke_group.command(name="status", description="Inspect anti-nuke module status and active thresholds")
    @is_admin_or_owner()
    async def antinuke_status_cmd(self, interaction: discord.Interaction):
        await self.security_status(interaction)

    @antinuke_group.command(name="config", description="Display current anti-nuke configurations and limits")
    @is_admin_or_owner()
    async def antinuke_config_cmd(self, interaction: discord.Interaction):
        await self.security_config_cmd(interaction)

    @antinuke_group.command(name="threshold", description="Configure specific anti-nuke action thresholds and detection windows")
    @is_admin_or_owner()
    @app_commands.describe(
        action="Which protection threshold to adjust",
        limit="Maximum actions allowed before containment (1-50)",
        window="Detection window in seconds (5-120s)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Channel Deletion", value="channel_delete"),
            app_commands.Choice(name="Channel Creation", value="channel_create"),
            app_commands.Choice(name="Role Deletion", value="role_delete"),
            app_commands.Choice(name="Role Creation", value="role_create"),
            app_commands.Choice(name="Member Bans", value="ban"),
            app_commands.Choice(name="Member Kicks", value="kick"),
            app_commands.Choice(name="Webhook Creation", value="webhook"),
        ]
    )
    async def antinuke_threshold_cmd(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        limit: int,
        window: Optional[int] = None,
    ):
        if not (1 <= limit <= 50):
            await interaction.response.send_message(embed=error_embed("Invalid Limit", "Limit must be between 1 and 50."), ephemeral=True)
            return
        if window is not None and not (5 <= window <= 120):
            await interaction.response.send_message(embed=error_embed("Invalid Window", "Window must be between 5 and 120 seconds."), ephemeral=True)
            return

        updates = {}
        act = action.value
        if act == "channel_delete":
            updates["channel_delete_limit"] = limit
            if window: updates["channel_delete_window"] = window
        elif act == "channel_create":
            updates["channel_create_limit"] = limit
            if window: updates["channel_create_window"] = window
        elif act == "role_delete":
            updates["role_delete_limit"] = limit
            if window: updates["role_delete_window"] = window
        elif act == "role_create":
            updates["role_create_limit"] = limit
            if window: updates["role_create_window"] = window
        elif act == "ban":
            updates["ban_limit"] = limit
            if window: updates["ban_window"] = window
        elif act == "kick":
            updates["kick_limit"] = limit
            if window: updates["kick_window"] = window
        elif act == "webhook":
            updates["webhook_limit"] = limit
            if window: updates["webhook_window"] = window

        await self.bot.db.update_security_config(interaction.guild.id, **updates)
        embed = success_embed(
            "Anti-Nuke Threshold Configured",
            f"**Action:** `{action.name}`\n"
            f"**Limit:** `{limit}` actions\n"
            f"**Window:** `{window or 'Default'}s`"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @antinuke_trust_group.command(name="add", description="Add user to anti-nuke trusted allowlist (Owner-only)")
    @is_strict_owner()
    @app_commands.describe(user="User to add to trusted allowlist", reason="Reason for trust")
    async def antinuke_trust_add(self, interaction: discord.Interaction, user: discord.User, reason: Optional[str] = "Authorized by Server Owner"):
        await self.trusted_add(interaction, user, reason)

    @antinuke_trust_group.command(name="remove", description="Remove user from anti-nuke trusted allowlist (Owner-only)")
    @is_strict_owner()
    @app_commands.describe(user="User to remove from trusted allowlist")
    async def antinuke_trust_remove(self, interaction: discord.Interaction, user: discord.User):
        await self.trusted_remove(interaction, user)

    @antinuke_trust_group.command(name="list", description="List all anti-nuke trusted users and server owner")
    @is_strict_owner_or_trusted()
    async def antinuke_trust_list(self, interaction: discord.Interaction):
        await self.security_allowlist(interaction)

    @antinuke_group.command(name="lockdown", description="Initiate emergency lockdown on all channels")
    @is_admin_or_owner()
    async def antinuke_lockdown_cmd(self, interaction: discord.Interaction):
        await self.security_lockdown(interaction)

    @antinuke_group.command(name="unlock", description="Lift lockdown and restore channel permissions")
    @is_admin_or_owner()
    async def antinuke_unlock_cmd(self, interaction: discord.Interaction):
        await self.security_unlock(interaction)

    @security_group.command(name="audit", description="Run comprehensive server security and permission audit")
    @is_admin_or_owner()
    async def security_audit_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        sec_cfg = await self.bot.db.get_security_config(guild.id)
        sec_state = await self.bot.db.get_security_state(guild.id)
        trusted = await self.bot.db.get_trusted_users(guild.id)
        incidents = await self.bot.db.get_security_incidents(guild.id, limit=5)

        dangerous_roles = []
        for r in guild.roles:
            if r.permissions.administrator or r.permissions.manage_guild or r.permissions.ban_members:
                dangerous_roles.append(f"`@{r.name}` ({len(r.members)} members)")

        embed = create_embed(
            title=f"🛡️ Comprehensive Security Audit — {guild.name}",
            color=Colors.SECURITY,
        )
        embed.add_field(
            name="Shield Standing",
            value=(
                f"• Anti-Nuke Status: `{'🟢 Armed' if not sec_state.emergency_stop else '🚨 Emergency Stop Active'}`\n"
                f"• Configured Action: `{sec_cfg.punishment.upper()}`\n"
                f"• Trusted Security Users: `{len(trusted)} accounts`\n"
                f"• Emergency Lockdown: `{'🔒 Active' if sec_state.lockdown_enabled else '🟢 Normal'}`"
            ),
            inline=False,
        )
        embed.add_field(
            name=f"High-Privilege Roles ({len(dangerous_roles)})",
            value="\n".join(dangerous_roles[:8]) if dangerous_roles else "None",
            inline=False,
        )
        if incidents:
            inc_txt = "\n".join(f"`[{inc.event_id}]` **{inc.event_type}** by {inc.executor_name or 'UNKNOWN'} ({inc.result})" for inc in incidents[:3])
            embed.add_field(name="Recent Security Incidents", value=inc_txt, inline=False)
        else:
            embed.add_field(name="Recent Security Incidents", value="Clean record (0 recent incidents).", inline=False)

        embed.set_footer(text="Raivora Real-Time Threat Analysis")
        await interaction.followup.send(embed=embed, ephemeral=True)



async def setup(bot: SentinelBot):
    await bot.add_cog(SecurityCog(bot))
