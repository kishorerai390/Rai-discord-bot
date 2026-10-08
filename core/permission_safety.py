"""
Centralized Discord Permission-Failure Handling Engine for 『RΛI』.

Core Responsibilities:
1. Intercepts and classifies Discord API permission failures (discord.Forbidden, missing permissions,
   channel overwrites, role hierarchy violations).
2. Never crashes, hangs, or affects unrelated subsystems (Security, Music, Database).
3. Never falsely reports success (returns structured PermissionResult with clear diagnostics).
4. Provides centralized `permission_safe_execute` executor with pre-flight checks and fallback execution.
5. Deduplicates repeated permission failures within a configurable time window to prevent log flooding.
6. Enforces strict per-guild isolation (failures in Guild A never affect Guild B).
7. Isolates voice/music permission failures from core security operations.
8. Provides automated guild permission auditing across functional modules.
"""

from __future__ import annotations

import asyncio
import datetime
import enum
import logging
import random
import string
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple, TypeVar, Union

import discord

from config import Colors
from utils.embeds import alert_embed, error_embed

logger = logging.getLogger("Rai.PermissionSafety")

T = TypeVar("T")


def generate_incident_id(prefix: str = "PF") -> str:
    """Generates unique incident identifier (e.g. #PF-0042)."""
    digits = "".join(random.choices(string.digits, k=5))
    return f"#{prefix}-{digits}"


class PermissionFailureType(enum.Enum):
    MISSING_BOT_PERMISSION = "MISSING_BOT_PERMISSION"
    ROLE_HIERARCHY_VIOLATION = "ROLE_HIERARCHY_VIOLATION"
    CHANNEL_PERMISSION_DENIED = "CHANNEL_PERMISSION_DENIED"
    CANNOT_MODERATE_TARGET = "CANNOT_MODERATE_TARGET"
    DISCORD_FORBIDDEN = "DISCORD_FORBIDDEN"
    UNKNOWN_PERMISSION_FAILURE = "UNKNOWN_PERMISSION_FAILURE"


# Mapping from operational action names to required Discord permissions
ACTION_REQUIRED_PERMISSIONS: Dict[str, List[str]] = {
    "delete_message": ["manage_messages"],
    "purge_messages": ["manage_messages", "read_message_history"],
    "timeout_member": ["moderate_members"],
    "remove_timeout": ["moderate_members"],
    "kick_member": ["kick_members"],
    "ban_member": ["ban_members"],
    "unban_member": ["ban_members"],
    "manage_channel": ["manage_channels"],
    "lock_channel": ["manage_channels"],
    "unlock_channel": ["manage_channels"],
    "manage_roles": ["manage_roles"],
    "add_role": ["manage_roles"],
    "remove_role": ["manage_roles"],
    "view_audit_logs": ["view_audit_log"],
    "connect_voice": ["connect"],
    "speak_voice": ["speak"],
    "move_voice_member": ["move_members"],
    "disconnect_voice_member": ["move_members"],
}


def human_permission_name(perm_key: str) -> str:
    """Converts a permission attribute key to a clean title (e.g. 'manage_messages' -> 'Manage Messages')."""
    return perm_key.replace("_", " ").title()


def check_role_hierarchy(
    target: Union[discord.Member, discord.Role],
    bot_member: discord.Member,
) -> Tuple[bool, str]:
    """
    Validates role hierarchy between bot and target member/role.
    Safe against MagicMock objects in test environments.
    """
    if not bot_member:
        return True, ""

    guild = getattr(bot_member, "guild", None)
    owner_id = getattr(guild, "owner_id", None)

    # 1. Target is Guild Owner
    if isinstance(target, discord.Member) and owner_id and target.id == owner_id:
        return False, "Target is the server owner."

    # 2. Target is Bot itself
    if isinstance(target, discord.Member) and target.id == bot_member.id:
        return False, "RAI cannot perform administrative actions on itself."

    # 3. Position comparison
    try:
        target_role = getattr(target, "top_role", target)
        bot_role = getattr(bot_member, "top_role", None)

        target_pos = getattr(target_role, "position", 0)
        bot_pos = getattr(bot_role, "position", 0)

        if not isinstance(target_pos, (int, float)):
            target_pos = 0
        if not isinstance(bot_pos, (int, float)):
            bot_pos = 0

        if target_pos >= bot_pos:
            target_name = getattr(target_role, "name", "Target")
            bot_name = getattr(bot_role, "name", "Bot")
            return (
                False,
                f"Target role ({target_name}) is higher than or equal to RAI's highest role ({bot_name}).",
            )
    except Exception as e:
        logger.debug(f"Role hierarchy inspection note: {e}")

    return True, ""


@dataclass
class PermissionResult:
    """Structured response object for every permission-checked operation."""
    success: bool
    action: str
    guild_id: int
    channel_id: Optional[int] = None
    target_id: Optional[int] = None
    subsystem: str = "Core"
    failure_type: Optional[PermissionFailureType] = None
    reason: Optional[str] = None
    required_permissions: List[str] = field(default_factory=list)
    missing_permissions: List[str] = field(default_factory=list)
    fallback_used: bool = False
    fallback_result: Optional[Any] = None
    incident_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    result_data: Optional[Any] = None

    def format_user_message(self) -> str:
        """Formatted response strictly adhering to Rule 2 (never claim success if rejected)."""
        if self.success:
            return f"✅ Action `{self.action}` completed successfully."
        reason_str = self.reason or "Missing required Discord permissions"
        return f"❌ Action `{self.action}` could not be completed: {reason_str}"

    def to_result(self) -> Any:
        """Convert PermissionResult into a core Result instance."""
        from core.results import Result, ResultStatus, ErrorCodes
        if self.success:
            return Result.ok(data=self.result_data, incident_id=self.incident_id)

        status_map = {
            PermissionFailureType.ROLE_HIERARCHY_VIOLATION: (
                ResultStatus.ROLE_HIERARCHY_BLOCKED,
                ErrorCodes.ROLE_HIERARCHY_BLOCKED,
            ),
            PermissionFailureType.CHANNEL_PERMISSION_DENIED: (
                ResultStatus.CHANNEL_PERMISSION_DENIED,
                ErrorCodes.CHANNEL_PERMISSION_DENIED,
            ),
            PermissionFailureType.MISSING_BOT_PERMISSION: (
                ResultStatus.BOT_MISSING_PERMISSION,
                ErrorCodes.BOT_MISSING_PERMISSION,
            ),
            PermissionFailureType.CANNOT_MODERATE_TARGET: (
                ResultStatus.ROLE_HIERARCHY_BLOCKED,
                ErrorCodes.ROLE_HIERARCHY_BLOCKED,
            ),
            PermissionFailureType.DISCORD_FORBIDDEN: (
                ResultStatus.PERMISSION_DENIED,
                ErrorCodes.BOT_MISSING_PERMISSION,
            ),
        }
        res_status, code = status_map.get(
            self.failure_type,
            (ResultStatus.PERMISSION_DENIED, ErrorCodes.BOT_MISSING_PERMISSION),
        )
        return Result.fail(
            status=res_status,
            code=code,
            message=self.reason or "Permission check failed",
            incident_id=self.incident_id,
            data=self.result_data,
        )



class PermissionFailureTracker:
    """
    Sliding-window failure deduplication and telemetry engine.
    Ensures that repeating identical permission failures do not flood staff channels.
    Strictly isolated per-guild.
    """

    _instance: Optional[PermissionFailureTracker] = None

    def __init__(self, window_seconds: float = 60.0):
        self.window_seconds = window_seconds
        # guild_id -> key -> {count, first_seen, last_seen, channel_id, subsystem, alerted}
        self._guild_failures: Dict[int, Dict[str, Dict[str, Any]]] = defaultdict(dict)

    @classmethod
    def get_instance(cls) -> PermissionFailureTracker:
        if cls._instance is None:
            cls._instance = PermissionFailureTracker()
        return cls._instance

    def record_failure(
        self,
        guild_id: int,
        action: str,
        channel_id: Optional[int],
        failure_type: PermissionFailureType,
        reason: str,
        subsystem: str = "Core",
    ) -> Tuple[bool, int]:
        """
        Records a failure and determines whether a staff alert should be dispatched.
        Returns (should_alert, blocked_count).
        """
        now = time.time()
        dedup_key = f"{action}:{channel_id or 0}:{failure_type.value}"

        guild_records = self._guild_failures[guild_id]
        record = guild_records.get(dedup_key)

        if not record or (now - record["first_seen"]) > self.window_seconds:
            # New window cycle: Alert immediately
            guild_records[dedup_key] = {
                "count": 1,
                "first_seen": now,
                "last_seen": now,
                "action": action,
                "channel_id": channel_id,
                "subsystem": subsystem,
                "reason": reason,
                "alerted": True,
            }
            return True, 1
        else:
            record["count"] += 1
            record["last_seen"] = now
            # Suppress alert to prevent flooding
            return False, record["count"]

    def get_guild_summary(self, guild_id: int) -> List[Dict[str, Any]]:
        """Returns summarized active failure records for a guild."""
        now = time.time()
        active = []
        for key, rec in list(self._guild_failures.get(guild_id, {}).items()):
            if now - rec["last_seen"] <= self.window_seconds * 5:
                active.append(rec)
        return active

    def clear_guild(self, guild_id: int) -> None:
        if guild_id in self._guild_failures:
            del self._guild_failures[guild_id]


async def permission_safe_execute(
    action: str,
    guild: discord.Guild,
    operation: Callable[[], Coroutine[Any, Any, T]],
    channel: Optional[Union[discord.TextChannel, discord.VoiceChannel, discord.abc.GuildChannel]] = None,
    target: Optional[Union[discord.Member, discord.Role]] = None,
    subsystem: str = "Security",
    fallback: Optional[Callable[[], Coroutine[Any, Any, Any]]] = None,
    notify_channel: Optional[discord.TextChannel] = None,
    security_threat_context: Optional[str] = None,
    bot: Optional[Any] = None,
) -> PermissionResult:
    """
    Centralized Permission Execution Wrapper.
    
    1. Pre-flight Role Hierarchy Check:
       Blocks calls before Discord API if target member or role is higher than bot.
    2. Pre-flight Permission Validation:
       Validates bot has necessary guild or channel permissions before dispatching request.
    3. Failure Isolation:
       Catches discord.Forbidden without crashing the calling system.
    4. Fallback Execution:
       Safely triggers alternative mitigation when primary action is rejected.
    5. Security Alert Escalation:
       If security threat detected, notifies staff with clear 'Detection: SUCCESS, Moderation: FAILED'.
    """
    bot_member = getattr(guild, "me", None)
    required_perms = ACTION_REQUIRED_PERMISSIONS.get(action, [])
    tracker = PermissionFailureTracker.get_instance()
    incident_id = generate_incident_id()

    # ----------------------------------------------------
    # 1. Pre-flight Role Hierarchy Check
    # ----------------------------------------------------
    if target and bot_member:
        can_act, hierarchy_reason = check_role_hierarchy(target, bot_member)
        if not can_act:
            logger.warning(
                f"[ROLE_HIERARCHY_VIOLATION] Guild {guild.id}: Cannot execute '{action}' on target "
                f"(ID: {getattr(target, 'id', 'unknown')}): {hierarchy_reason}"
            )
            should_alert, blocked_count = tracker.record_failure(
                guild.id, action, getattr(channel, "id", None),
                PermissionFailureType.ROLE_HIERARCHY_VIOLATION, hierarchy_reason, subsystem
            )

            # Fallback Execution
            fallback_res = None
            if fallback:
                try:
                    fallback_res = await fallback()
                except Exception as fe:
                    logger.debug(f"Fallback execution note: {fe}")

            # Security Threat Notification
            if security_threat_context and should_alert:
                await _dispatch_security_permission_alert(
                    guild=guild,
                    threat_context=security_threat_context,
                    action_attempted=action,
                    reason=hierarchy_reason,
                    incident_id=incident_id,
                    notify_channel=notify_channel,
                    bot=bot,
                )

            # Record in SQLite (resilient)
            await _record_failure_db(
                bot, incident_id, guild.id, action, "ROLE_HIERARCHY_VIOLATION",
                hierarchy_reason, subsystem, getattr(channel, "id", None),
                getattr(target, "id", None), None, bool(fallback)
            )

            return PermissionResult(
                success=False,
                action=action,
                guild_id=guild.id,
                channel_id=getattr(channel, "id", None),
                target_id=getattr(target, "id", None),
                subsystem=subsystem,
                failure_type=PermissionFailureType.ROLE_HIERARCHY_VIOLATION,
                reason=hierarchy_reason,
                required_permissions=required_perms,
                fallback_used=bool(fallback),
                fallback_result=fallback_res,
                incident_id=incident_id,
            )

    # ----------------------------------------------------
    # 2. Pre-flight Permission Validation
    # ----------------------------------------------------
    missing_perms = []
    if bot_member and required_perms:
        if channel and hasattr(channel, "permissions_for"):
            try:
                ch_perms = channel.permissions_for(bot_member)
                for req in required_perms:
                    if not getattr(ch_perms, req, False):
                        missing_perms.append(req)
            except Exception:
                pass
        else:
            g_perms = getattr(bot_member, "guild_permissions", None)
            if g_perms:
                for req in required_perms:
                    if not getattr(g_perms, req, False):
                        missing_perms.append(req)

    if missing_perms:
        missing_names = ", ".join(human_permission_name(p) for p in missing_perms)
        fail_reason = f"Missing required permission: {missing_names}"
        logger.warning(
            f"[MISSING_BOT_PERMISSION] Guild {guild.id}: Cannot execute '{action}' - {fail_reason}"
        )
        should_alert, blocked_count = tracker.record_failure(
            guild.id, action, getattr(channel, "id", None),
            PermissionFailureType.MISSING_BOT_PERMISSION, fail_reason, subsystem
        )

        fallback_res = None
        if fallback:
            try:
                fallback_res = await fallback()
            except Exception as fe:
                logger.debug(f"Fallback execution note: {fe}")

        if security_threat_context and should_alert:
            await _dispatch_security_permission_alert(
                guild=guild,
                threat_context=security_threat_context,
                action_attempted=action,
                reason=fail_reason,
                incident_id=incident_id,
                notify_channel=notify_channel,
                bot=bot,
            )

        await _record_failure_db(
            bot, incident_id, guild.id, action, "MISSING_BOT_PERMISSION",
            fail_reason, subsystem, getattr(channel, "id", None),
            getattr(target, "id", None), missing_perms[0], bool(fallback)
        )

        return PermissionResult(
            success=False,
            action=action,
            guild_id=guild.id,
            channel_id=getattr(channel, "id", None),
            target_id=getattr(target, "id", None),
            subsystem=subsystem,
            failure_type=PermissionFailureType.MISSING_BOT_PERMISSION,
            reason=fail_reason,
            required_permissions=required_perms,
            missing_permissions=missing_perms,
            fallback_used=bool(fallback),
            fallback_result=fallback_res,
            incident_id=incident_id,
        )

    # ----------------------------------------------------
    # 3. Safe Execution with Exception Boundary
    # ----------------------------------------------------
    try:
        res = await operation()
        return PermissionResult(
            success=True,
            action=action,
            guild_id=guild.id,
            channel_id=getattr(channel, "id", None),
            target_id=getattr(target, "id", None),
            subsystem=subsystem,
            required_permissions=required_perms,
            result_data=res,
        )

    except discord.Forbidden as e:
        fail_reason = e.text or "Discord API rejected operation with 403 Forbidden"
        logger.warning(
            f"[DISCORD_FORBIDDEN] Guild {guild.id}: Action '{action}' forbidden by Discord: {fail_reason}"
        )
        should_alert, blocked_count = tracker.record_failure(
            guild.id, action, getattr(channel, "id", None),
            PermissionFailureType.DISCORD_FORBIDDEN, fail_reason, subsystem
        )

        fallback_res = None
        if fallback:
            try:
                fallback_res = await fallback()
            except Exception as fe:
                logger.debug(f"Fallback execution note: {fe}")

        if security_threat_context and should_alert:
            await _dispatch_security_permission_alert(
                guild=guild,
                threat_context=security_threat_context,
                action_attempted=action,
                reason=fail_reason,
                incident_id=incident_id,
                notify_channel=notify_channel,
                bot=bot,
            )

        await _record_failure_db(
            bot, incident_id, guild.id, action, "DISCORD_FORBIDDEN",
            fail_reason, subsystem, getattr(channel, "id", None),
            getattr(target, "id", None), required_perms[0] if required_perms else None, bool(fallback)
        )

        return PermissionResult(
            success=False,
            action=action,
            guild_id=guild.id,
            channel_id=getattr(channel, "id", None),
            target_id=getattr(target, "id", None),
            subsystem=subsystem,
            failure_type=PermissionFailureType.DISCORD_FORBIDDEN,
            reason=fail_reason,
            required_permissions=required_perms,
            fallback_used=bool(fallback),
            fallback_result=fallback_res,
            incident_id=incident_id,
        )

    except discord.HTTPException as e:
        err_msg = f"Discord HTTP error ({e.status}): {e.text}"
        logger.warning(f"[DISCORD_HTTP_ERROR] Guild {guild.id} during '{action}': {err_msg}")
        return PermissionResult(
            success=False,
            action=action,
            guild_id=guild.id,
            channel_id=getattr(channel, "id", None),
            target_id=getattr(target, "id", None),
            subsystem=subsystem,
            failure_type=PermissionFailureType.UNKNOWN_PERMISSION_FAILURE,
            reason=err_msg,
            required_permissions=required_perms,
            incident_id=incident_id,
        )

    except Exception as e:
        logger.error(f"[UNEXPECTED_OP_ERROR] Guild {guild.id} during '{action}': {e}", exc_info=True)
        return PermissionResult(
            success=False,
            action=action,
            guild_id=guild.id,
            channel_id=getattr(channel, "id", None),
            target_id=getattr(target, "id", None),
            subsystem=subsystem,
            failure_type=PermissionFailureType.UNKNOWN_PERMISSION_FAILURE,
            reason=str(e),
            required_permissions=required_perms,
            incident_id=incident_id,
        )


async def _dispatch_security_permission_alert(
    guild: discord.Guild,
    threat_context: str,
    action_attempted: str,
    reason: str,
    incident_id: str,
    notify_channel: Optional[discord.TextChannel] = None,
    bot: Optional[Any] = None,
) -> None:
    """
    Dispatches a structured security alert when automatic moderation fails.
    Explicitly notifies staff WITHOUT mass-mentions (@everyone/@here).
    """
    target_ch = notify_channel
    if not target_ch and bot and hasattr(bot, "db"):
        try:
            log_cfg = await bot.db.get_logging_config(guild.id)
            if log_cfg and log_cfg.security_channel_id:
                target_ch = guild.get_channel(log_cfg.security_channel_id)
        except Exception:
            pass

    if not target_ch:
        # Fallback to system channel
        target_ch = getattr(guild, "system_channel", None)

    if not target_ch or not hasattr(target_ch, "send"):
        return

    embed = discord.Embed(
        title="『RΛI』 • SECURITY ALERT",
        color=getattr(Colors, "CRITICAL", Colors.ERROR),
        description=(
            f"**Threat detected:** {threat_context}\n"
            f"**Detection:** `SUCCESS`\n"
            f"**Automatic moderation:** `FAILED`\n"
            f"**Attempted Action:** `{action_attempted}`\n"
            f"**Reason:** {reason}\n\n"
            f"⚠️ **Administrator action required.**\n"
            f"Please verify RAI's role hierarchy and server permissions."
        ),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.set_footer(text=f"Incident Ref: {incident_id} • Staff Action Required")

    try:
        await target_ch.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),  # Strictly prevents mass pings
        )
    except Exception as e:
        logger.debug(f"Could not dispatch security permission alert to #{target_ch.name}: {e}")


async def _record_failure_db(
    bot: Optional[Any],
    incident_id: str,
    guild_id: int,
    action: str,
    failure_type: str,
    reason: str,
    subsystem: str,
    channel_id: Optional[int],
    target_id: Optional[int],
    required_perm: Optional[str],
    fallback_used: bool,
) -> None:
    """Non-blocking resilient DB writer that never crashes if database is locked."""
    if not bot or not hasattr(bot, "db"):
        return
    try:
        await bot.db.record_permission_failure(
            incident_id=incident_id,
            guild_id=guild_id,
            action=action,
            failure_type=failure_type,
            reason=reason,
            subsystem=subsystem,
            channel_id=channel_id,
            target_id=target_id,
            required_permission=required_perm,
            fallback_used=fallback_used,
        )
    except Exception as e:
        logger.debug(f"Permission failure DB write note: {e}")


# ==========================================
# PERMISSION AUDIT ENGINE
# ==========================================

MODULE_PERMISSION_REQUIREMENTS: Dict[str, Dict[str, List[str]]] = {
    "Security": {
        "Message Delete": ["manage_messages"],
        "Threat History": ["read_message_history"],
    },
    "Moderation": {
        "Timeout": ["moderate_members"],
        "Kick": ["kick_members"],
        "Ban": ["ban_members"],
    },
    "Anti-Nuke / Lockdown": {
        "Channel Lock": ["manage_channels"],
        "Role Guard": ["manage_roles"],
    },
    "Audit Log": {
        "Audit Trail": ["view_audit_log"],
    },
    "Voice / Music": {
        "Voice Connect": ["connect"],
        "Voice Speak": ["speak"],
    },
}


def audit_guild_permissions(guild: discord.Guild) -> Dict[str, Any]:
    """
    Performs comprehensive permission audit for a guild across functional modules.
    Returns structured audit dictionary suitable for REST APIs, dashboards, and embeds.
    """
    bot_member = getattr(guild, "me", None)
    if not bot_member:
        return {"status": "UNKNOWN", "modules": {}}

    perms = getattr(bot_member, "guild_permissions", None)
    if not perms:
        return {"status": "UNKNOWN", "modules": {}}

    is_admin = bool(perms.administrator)
    audit_results: Dict[str, Dict[str, Any]] = {}
    overall_status = "AVAILABLE"

    for module_name, features in MODULE_PERMISSION_REQUIREMENTS.items():
        module_features = {}
        missing_count = 0
        total_count = len(features)

        for feature_name, req_perms in features.items():
            if is_admin:
                module_features[feature_name] = {"available": True, "missing": []}
            else:
                missing = [p for p in req_perms if not getattr(perms, p, False)]
                if missing:
                    missing_count += 1
                    module_features[feature_name] = {"available": False, "missing": missing}
                else:
                    module_features[feature_name] = {"available": True, "missing": []}

        if is_admin or missing_count == 0:
            status = "AVAILABLE"
        elif missing_count == total_count:
            status = "UNAVAILABLE"
            overall_status = "PARTIAL" if overall_status != "UNAVAILABLE" else overall_status
        else:
            status = "PARTIAL"
            overall_status = "PARTIAL"

        audit_results[module_name] = {
            "status": status,
            "features": module_features,
        }

    return {
        "guild_id": guild.id,
        "guild_name": guild.name,
        "is_administrator": is_admin,
        "overall_status": overall_status,
        "modules": audit_results,
    }


def create_permission_audit_embed(guild: discord.Guild) -> discord.Embed:
    """Generates an administrator-facing visual Matrix embed of current permission health."""
    audit = audit_guild_permissions(guild)
    is_admin = audit.get("is_administrator", False)

    status_icon_map = {
        "AVAILABLE": "✅ Available",
        "PARTIAL": "⚠️ Partial",
        "UNAVAILABLE": "❌ Missing",
    }

    color = Colors.SUCCESS if audit["overall_status"] == "AVAILABLE" else (
        Colors.WARNING if audit["overall_status"] == "PARTIAL" else getattr(Colors, "CRITICAL", Colors.ERROR)
    )

    embed = discord.Embed(
        title="『RΛI』 • PERMISSION AUDIT MATRIX",
        color=color,
        description=(
            f"**Target Citadel:** {guild.name}\n"
            f"**Administrator Bypass:** {'Active (Full Permissions)' if is_admin else 'Inactive (Explicit Verification)'}\n"
            f"**Operational Status:** `{audit['overall_status']}`\n\n"
            "Evaluated against all core autonomous security, moderation, and voice subsystems."
        ),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )

    icons = {
        "Security": "🛡️",
        "Moderation": "🔨",
        "Anti-Nuke / Lockdown": "🔒",
        "Audit Log": "📋",
        "Voice / Music": "🎵",
    }

    for mod_name, mod_data in audit["modules"].items():
        icon = icons.get(mod_name, "⚙️")
        lines = []
        for feat_name, feat_data in mod_data["features"].items():
            if feat_data["available"]:
                lines.append(f"• `{feat_name}`: ✅ Available")
            else:
                missing_str = ", ".join(human_permission_name(p) for p in feat_data["missing"])
                lines.append(f"• `{feat_name}`: ❌ Missing ({missing_str})")

        val_text = f"**Status:** {status_icon_map.get(mod_data['status'], mod_data['status'])}\n" + "\n".join(lines)
        embed.add_field(name=f"{icon} {mod_name}", value=val_text, inline=False)

    embed.set_footer(text="RAI Permission Safety Matrix • Run /security permissions audit")
    return embed
