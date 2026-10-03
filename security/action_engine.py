"""
Safe Action Engine and Protection Policy Gate for 『RΛI』.

Core Responsibilities:
1. Validates all proposed security actions against authoritative protection policies.
2. Performs pre-flight permission checks and role hierarchy verification using core.permission_safety.
3. Protects the current server owner (guild.owner_id) and verified founders from accidental containment.
4. Tracks action reversibility to support automatic recovery when threats subside.
5. Guarantees that success is never reported unless Discord API confirms execution.
"""

from __future__ import annotations

import asyncio
import datetime
import enum
import logging
import random
import string
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import discord

from config import FOUNDER_ROLE_ID
from core.permission_safety import check_role_hierarchy
from core.results import ErrorCodes, Result, ResultError, ResultStatus

logger = logging.getLogger("Rai.ActionEngine")


class ActionType(str, enum.Enum):
    """Categorical security mitigations."""
    TIMEOUT_USER = "timeout_user"
    REMOVE_TIMEOUT = "remove_timeout"
    KICK_USER = "kick_user"
    BAN_USER = "ban_user"
    UNBAN_USER = "unban_user"
    DELETE_MESSAGES = "delete_messages"
    LOCKDOWN_CHANNEL = "lockdown_channel"
    UNLOCK_CHANNEL = "unlock_channel"
    NOTIFY_OWNER = "notify_owner"


def generate_action_id(prefix: str = "ACT") -> str:
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    rand_chars = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{ts}-{rand_chars}"


@dataclass
class ProposedAction:
    """Action submitted for policy verification and execution."""
    action_type: ActionType
    guild_id: int
    target_id: Optional[int] = None
    target_name: Optional[str] = None
    target_type: str = "MEMBER"  # MEMBER, CHANNEL, ROLE
    reason: str = "Automated threat containment"
    severity: str = "HIGH"
    parameters: Dict[str, Any] = field(default_factory=dict)
    incident_id: Optional[str] = None
    reversible: bool = True


@dataclass
class ActionExecutionRecord:
    """Audit record of an executed or blocked security action."""
    action_id: str
    guild_id: int
    action_type: str
    target_id: Optional[int]
    status: ResultStatus
    success: bool
    reversible: bool
    previous_state: Optional[Dict[str, Any]]
    reason: str
    error_code: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


class SafeActionEngine:
    """Enforces Protection Policy and executes authorized mitigations."""

    _instance: Optional[SafeActionEngine] = None

    def __init__(self, db: Any = None):
        self.db = db
        # guild_id -> list of reversible execution records
        self._reversible_actions: Dict[int, List[ActionExecutionRecord]] = {}

    @classmethod
    def get_instance(cls, db: Any = None) -> SafeActionEngine:
        if cls._instance is None:
            cls._instance = SafeActionEngine(db)
        elif db is not None and cls._instance.db is None:
            cls._instance.db = db
        return cls._instance

    def get_reversible_actions(self, guild_id: int) -> List[ActionExecutionRecord]:
        """Returns all reversible actions taken during current threat session."""
        return list(self._reversible_actions.get(guild_id, []))

    def clear_reversible_actions(self, guild_id: int) -> None:
        """Clears reversible actions for a guild upon recovery."""
        if guild_id in self._reversible_actions:
            self._reversible_actions[guild_id].clear()

    # ==========================================
    # POLICY VALIDATION GATE
    # ==========================================

    def validate_policy(
        self,
        guild: discord.Guild,
        action: ProposedAction,
        target: Optional[Union[discord.Member, discord.abc.GuildChannel]] = None,
    ) -> Tuple[bool, Optional[str], ResultStatus, Optional[str]]:
        """
        Validates proposed action against core safety rules:
        - Target is never guild owner
        - Target is never bot itself
        - Target is never verified founder
        - Role hierarchy is strictly respected
        - Bot possesses required Discord permissions
        """
        bot_member = guild.me
        if not bot_member:
            return False, "Bot member not found in guild", ResultStatus.FAILED, ErrorCodes.INTERNAL_ERROR

        # 1. Member Target Policy
        if isinstance(target, discord.Member):
            # Never target the current server owner
            if target.id == guild.owner_id:
                return (
                    False,
                    "Protection Policy: Current server owner is immune to automated actions",
                    ResultStatus.PERMISSION_DENIED,
                    ErrorCodes.ROLE_HIERARCHY_BLOCKED,
                )

            # Never target bot itself
            if target.id == bot_member.id:
                return (
                    False,
                    "Protection Policy: Bot cannot target itself",
                    ResultStatus.PERMISSION_DENIED,
                    ErrorCodes.ROLE_HIERARCHY_BLOCKED,
                )

            # Founder role check
            for r in target.roles:
                if r.id == FOUNDER_ROLE_ID or "founder" in r.name.lower():
                    return (
                        False,
                        "Protection Policy: Verified founder is exempt from containment",
                        ResultStatus.PERMISSION_DENIED,
                        ErrorCodes.ROLE_HIERARCHY_BLOCKED,
                    )

            # Role hierarchy check
            can_moderate, hier_reason = check_role_hierarchy(target, bot_member)
            if not can_moderate:
                return (
                    False,
                    f"Role Hierarchy Blocked: {hier_reason}",
                    ResultStatus.ROLE_HIERARCHY_BLOCKED,
                    ErrorCodes.ROLE_HIERARCHY_BLOCKED,
                )

        # 2. Required Bot Permission Verification
        bot_perms = bot_member.guild_permissions
        if action.action_type in (ActionType.TIMEOUT_USER, ActionType.REMOVE_TIMEOUT):
            if not bot_perms.moderate_members:
                return (
                    False,
                    "Missing Bot Permission: Moderate Members",
                    ResultStatus.PERMISSION_DENIED,
                    ErrorCodes.MISSING_MODERATE_MEMBERS,
                )
        elif action.action_type == ActionType.KICK_USER:
            if not bot_perms.kick_members:
                return (
                    False,
                    "Missing Bot Permission: Kick Members",
                    ResultStatus.PERMISSION_DENIED,
                    ErrorCodes.MISSING_KICK_MEMBERS,
                )
        elif action.action_type in (ActionType.BAN_USER, ActionType.UNBAN_USER):
            if not bot_perms.ban_members:
                return (
                    False,
                    "Missing Bot Permission: Ban Members",
                    ResultStatus.PERMISSION_DENIED,
                    ErrorCodes.MISSING_BAN_MEMBERS,
                )
        elif action.action_type == ActionType.DELETE_MESSAGES:
            if not bot_perms.manage_messages:
                return (
                    False,
                    "Missing Bot Permission: Manage Messages",
                    ResultStatus.PERMISSION_DENIED,
                    ErrorCodes.MISSING_MANAGE_MESSAGES,
                )
        elif action.action_type in (ActionType.LOCKDOWN_CHANNEL, ActionType.UNLOCK_CHANNEL):
            if not bot_perms.manage_channels:
                return (
                    False,
                    "Missing Bot Permission: Manage Channels",
                    ResultStatus.PERMISSION_DENIED,
                    ErrorCodes.MISSING_MANAGE_CHANNELS,
                )

        return True, None, ResultStatus.SUCCESS, None

    # ==========================================
    # ACTION EXECUTION
    # ==========================================

    async def execute_action(
        self,
        guild: discord.Guild,
        action: ProposedAction,
        target: Optional[Union[discord.Member, discord.abc.GuildChannel]] = None,
    ) -> Result[ActionExecutionRecord]:
        """
        Executes a validated security mitigation and tracks state.
        """
        act_id = generate_action_id()

        # 1. Validate through Protection Policy
        allowed, fail_msg, status, err_code = self.validate_policy(guild, action, target)
        if not allowed:
            logger.warning(f"[POLICY REJECT] Action {action.action_type.value} rejected: {fail_msg}")
            return Result.fail(
                status=status,
                code=err_code or ErrorCodes.PERMISSION_DENIED,
                message=fail_msg or "Policy validation rejected action",
                data=ActionExecutionRecord(
                    action_id=act_id,
                    guild_id=guild.id,
                    action_type=action.action_type.value,
                    target_id=action.target_id,
                    status=status,
                    success=False,
                    reversible=False,
                    previous_state=None,
                    reason=fail_msg or "Policy rejection",
                    error_code=err_code,
                ),
            )

        prev_state: Optional[Dict[str, Any]] = None

        # 2. Execute on Discord API with full error trapping
        try:
            if action.action_type == ActionType.TIMEOUT_USER and isinstance(target, discord.Member):
                duration_seconds = action.parameters.get("duration_seconds", 600)
                until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
                prev_state = {"timed_out_until": str(target.timed_out_until) if target.timed_out_until else None}
                await target.timeout(until, reason=f"RAI Threat Containment: {action.reason}")

            elif action.action_type == ActionType.REMOVE_TIMEOUT and isinstance(target, discord.Member):
                await target.timeout(None, reason=f"RAI Threat Recovery: {action.reason}")

            elif action.action_type == ActionType.KICK_USER and isinstance(target, discord.Member):
                await target.kick(reason=f"RAI Threat Containment: {action.reason}")

            elif action.action_type == ActionType.BAN_USER:
                delete_seconds = action.parameters.get("delete_message_seconds", 3600)
                await guild.ban(
                    discord.Object(id=action.target_id),
                    reason=f"RAI Threat Containment: {action.reason}",
                    delete_message_seconds=delete_seconds,
                )

            elif action.action_type == ActionType.UNBAN_USER:
                await guild.unban(discord.Object(id=action.target_id), reason=f"RAI Recovery: {action.reason}")

            elif action.action_type == ActionType.LOCKDOWN_CHANNEL and isinstance(target, discord.TextChannel):
                everyone_role = guild.default_role
                current_ow = target.overwrites_for(everyone_role)
                prev_state = {"send_messages": current_ow.send_messages}
                current_ow.send_messages = False
                await target.set_permissions(everyone_role, overwrite=current_ow, reason=f"RAI Lockdown: {action.reason}")

            elif action.action_type == ActionType.UNLOCK_CHANNEL and isinstance(target, discord.TextChannel):
                everyone_role = guild.default_role
                current_ow = target.overwrites_for(everyone_role)
                current_ow.send_messages = None
                await target.set_permissions(everyone_role, overwrite=current_ow, reason=f"RAI Unlock: {action.reason}")

            else:
                return Result.fail(
                    status=ResultStatus.INVALID,
                    code=ErrorCodes.INVALID_CONFIGURATION,
                    message=f"Unsupported action type or incompatible target: {action.action_type.value}",
                )

            record = ActionExecutionRecord(
                action_id=act_id,
                guild_id=guild.id,
                action_type=action.action_type.value,
                target_id=action.target_id,
                status=ResultStatus.SUCCESS,
                success=True,
                reversible=action.reversible,
                previous_state=prev_state,
                reason=action.reason,
            )

            # Store for recovery if reversible
            if action.reversible and prev_state:
                if guild.id not in self._reversible_actions:
                    self._reversible_actions[guild.id] = []
                self._reversible_actions[guild.id].append(record)

            logger.info(
                f"[ACTION EXECUTED] {action.action_type.value} on target {action.target_id} in guild {guild.id} (ID: {act_id})"
            )
            return Result.ok(data=record)

        except discord.Forbidden as e:
            logger.warning(f"[ACTION FORBIDDEN] Cannot execute {action.action_type.value}: {e}")
            return Result.fail(
                status=ResultStatus.ROLE_HIERARCHY_BLOCKED,
                code=ErrorCodes.ROLE_HIERARCHY_BLOCKED,
                message=f"Discord Forbidden: {e}",
            )
        except discord.HTTPException as e:
            if e.status == 429:
                return Result.fail(
                    status=ResultStatus.RATE_LIMITED,
                    code=ErrorCodes.DISCORD_RATE_LIMIT,
                    message="Discord rate limit hit during action execution",
                    retryable=True,
                )
            return Result.fail(
                status=ResultStatus.DISCORD_ERROR,
                code=ErrorCodes.DISCORD_API_ERROR,
                message=f"Discord API error: {e}",
            )
        except Exception as e:
            logger.error(f"[ACTION ERROR] Unexpected error executing {action.action_type.value}: {e}", exc_info=True)
            return Result.fail(
                status=ResultStatus.INTERNAL_ERROR,
                code=ErrorCodes.INTERNAL_ERROR,
                message=f"Internal execution failure: {e}",
            )
