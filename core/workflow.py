"""
RAI — WORKFLOW ENGINE & AUTOMATION ORCHESTRATION PIPELINE
Combines existing Rai services into persistent, multi-step automated workflows:
TRIGGER → CONDITIONS → ACTIONS → DELAYS → NEXT ACTION → VERIFICATION → REPORT

Key Architectural Features:
- Does NOT duplicate existing subsystem logic; orchestrates BackupService,
  HealthService, SecurityService, RoomService, MusicService, EventService,
  ProjectService, NotificationService, AnalyticsService, MemoryService, etc.
- Multi-trigger system: Time/Cron schedules, Discord Events, and Rai Subsystem Events.
- Logical Condition Evaluator: AND, OR, NOT with rich contextual checks.
- Standardized Action Registry with permission checks, timeout, retry policy, and risk assessment.
- Persistent Delay Scheduler: Asynchronously persists waiting state in SQLite, survives bot restarts.
- Missed Schedule Policies: SKIP, RUN_ONCE, CATCH_UP, NEXT_SCHEDULE.
- Versioning: Executions lock to the workflow version at launch.
- Loop and Recursion Protection: Bounded queue, max depth, rate limits per guild.
- 100% Dry-Run Simulation Mode: Zero production Discord mutations.
- Reusable Workflow Templates.
- Premium Feature Integration: Free tier limits (up to 3 active workflows), Premium unlocks advanced capabilities.
"""

from __future__ import annotations

import asyncio
import datetime
import enum
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple, Union

import discord

from config import Colors
from config.permissions import PermissionLevel, get_member_permission_level, is_founder_or_owner
from core.operations_core import (
    AnalyticsService,
    BackupService,
    ConfigurationService,
    EventService,
    HealthService,
    MusicService,
    NotificationService,
    ProjectService,
    RecoveryService,
    ReputationService,
    RoomService,
    SecurityService,
)
from database.models import (
    Workflow,
    WorkflowEvent,
    WorkflowExecution,
    WorkflowStep,
    WorkflowStepExecution,
    WorkflowTemplate,
    WorkflowWaitingTimer,
)
from utils.embeds import create_embed, error_embed, info_embed, success_embed, warning_embed
from utils.owner_reporter import OWNER_ID, OwnerReporter, generate_incident_id

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.WorkflowEngine")


# =============================================================================
# 1. ENUMS & CONSTANTS
# =============================================================================

class WorkflowStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DISABLED = "DISABLED"


class TriggerType(str, enum.Enum):
    # Time triggers
    SCHEDULED = "scheduled"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    INTERVAL = "interval"
    CRON = "cron"

    # Discord events
    MEMBER_JOIN = "member_join"
    MEMBER_REMOVE = "member_remove"
    MESSAGE_CREATE = "message_create"
    REACTION_ADD = "reaction_add"
    REACTION_REMOVE = "reaction_remove"
    VOICE_JOIN = "voice_join"
    VOICE_LEAVE = "voice_leave"
    VOICE_STATE_UPDATE = "voice_state_update"
    CHANNEL_CREATE = "channel_create"
    CHANNEL_DELETE = "channel_delete"
    ROLE_CREATE = "role_create"
    ROLE_DELETE = "role_delete"

    # Rai events
    SECURITY_INCIDENT = "security_incident"
    BACKUP_COMPLETED = "backup_completed"
    BACKUP_FAILED = "backup_failed"
    MUSIC_START = "music_start"
    MUSIC_STOP = "music_stop"
    EVENT_START = "event_start"
    EVENT_END = "event_end"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    HEALTH_WARNING = "health_warning"
    SECURITY_WARNING = "security_warning"
    RECOVERY_REQUIRED = "recovery_required"
    PREMIUM_CHANGED = "premium_changed"


class ActionRiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FailurePolicy(str, enum.Enum):
    STOP = "STOP"
    CONTINUE = "CONTINUE"
    RETRY = "RETRY"
    FALLBACK = "FALLBACK"


class MissedSchedulePolicy(str, enum.Enum):
    SKIP = "SKIP"
    RUN_ONCE = "RUN_ONCE"
    CATCH_UP = "CATCH_UP"
    NEXT_SCHEDULE = "NEXT_SCHEDULE"


# Rate & resource bounds
MAX_ACTIVE_WORKFLOWS_FREE = 3
MAX_ACTIVE_WORKFLOWS_PREMIUM = 50
MAX_ACTIONS_PER_EXECUTION = 100
MAX_EXECUTION_DEPTH = 5
MAX_CONCURRENT_PER_GUILD = 10
MAX_CONCURRENT_PER_WORKFLOW = 5


# =============================================================================
# 1B. STANDARD 5-PART CRON PARSER & SCHEDULER
# =============================================================================

class CronParser:
    """
    Standard 5-part cron syntax evaluator (minute, hour, day-of-month, month, day-of-week).
    Supports:
    - Wildcards (*)
    - Steps (*/15, 1-10/2)
    - Ranges (1-5, MON-FRI)
    - Lists (1,15,30)
    - Named days (SUN, MON, TUE, WED, THU, FRI, SAT)
    - Named months (JAN, FEB, MAR, APR, MAY, JUN, JUL, AUG, SEP, OCT, NOV, DEC)
    - Standard aliases (@yearly, @monthly, @weekly, @daily, @hourly)
    """

    MONTH_MAP: Dict[str, int] = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    DOW_MAP: Dict[str, int] = {
        "SUN": 0, "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6,
    }
    ALIASES: Dict[str, str] = {
        "@yearly": "0 0 1 1 *",
        "@annually": "0 0 1 1 *",
        "@monthly": "0 0 1 * *",
        "@weekly": "0 0 * * 0",
        "@daily": "0 0 * * *",
        "@midnight": "0 0 * * *",
        "@hourly": "0 * * * *",
    }

    @classmethod
    def _parse_field(
        cls,
        field_str: str,
        min_val: int,
        max_val: int,
        name_map: Optional[Dict[str, int]] = None,
        is_dow: bool = False,
    ) -> Set[int]:
        values: Set[int] = set()
        for part in field_str.split(","):
            part = part.strip()
            if not part:
                raise ValueError("Empty sub-field in expression")

            step = 1
            if "/" in part:
                subparts = part.split("/")
                if len(subparts) != 2:
                    raise ValueError(f"Invalid step format: '{part}'")
                part = subparts[0]
                try:
                    step = int(subparts[1])
                except ValueError:
                    raise ValueError(f"Step must be an integer: '{subparts[1]}'")
                if step <= 0:
                    raise ValueError(f"Step must be greater than zero: '{step}'")

            if part == "*":
                start, end = min_val, max_val
            elif "-" in part:
                subparts = part.split("-")
                if len(subparts) != 2:
                    raise ValueError(f"Invalid range format: '{part}'")
                s_str, e_str = subparts[0].strip().upper(), subparts[1].strip().upper()
                try:
                    start = name_map[s_str] if (name_map and s_str in name_map) else int(s_str)
                    end = name_map[e_str] if (name_map and e_str in name_map) else int(e_str)
                except ValueError:
                    raise ValueError(f"Invalid integer in range '{part}'")
            else:
                p_str = part.strip().upper()
                try:
                    val = name_map[p_str] if (name_map and p_str in name_map) else int(p_str)
                    start, end = val, val
                except ValueError:
                    raise ValueError(f"Invalid integer in field '{part}'")

            if is_dow:
                if start == 7:
                    start = 0
                if end == 7:
                    end = 0

            if start < min_val or start > max_val or end < min_val or end > max_val:
                raise ValueError(f"Value out of bounds ({start}-{end}); allowed range is {min_val}-{max_val}")

            if start <= end:
                for v in range(start, end + 1, step):
                    values.add(v)
            else:
                # Wrap-around range (e.g. FRI-MON)
                for v in list(range(start, max_val + 1, step)) + list(range(min_val, end + 1, step)):
                    values.add(v)

        return values

    @classmethod
    def validate_expression(cls, expr: str) -> Tuple[bool, Optional[str]]:
        try:
            cls.parse(expr)
            return True, None
        except Exception as e:
            return False, str(e)

    @classmethod
    def parse(cls, expr: str) -> Tuple[Set[int], Set[int], Set[int], Set[int], Set[int]]:
        expr_clean = expr.strip()
        expr_resolved = cls.ALIASES.get(expr_clean.lower(), expr_clean)
        parts = expr_resolved.split()
        if len(parts) != 5:
            raise ValueError(f"Cron expression must contain exactly 5 space-separated fields, got {len(parts)}: '{expr}'")

        mins = cls._parse_field(parts[0], 0, 59)
        hours = cls._parse_field(parts[1], 0, 23)
        doms = cls._parse_field(parts[2], 1, 31)
        months = cls._parse_field(parts[3], 1, 12, cls.MONTH_MAP)
        dows = cls._parse_field(parts[4], 0, 6, cls.DOW_MAP, is_dow=True)
        return mins, hours, doms, months, dows

    @classmethod
    def is_due(cls, expr: str, dt: Optional[datetime.datetime] = None) -> bool:
        dt = dt or datetime.datetime.now(datetime.timezone.utc)
        try:
            mins, hours, doms, months, dows = cls.parse(expr)
        except Exception:
            return False
        cron_dow = (dt.weekday() + 1) % 7
        return (
            dt.minute in mins
            and dt.hour in hours
            and dt.day in doms
            and dt.month in months
            and cron_dow in dows
        )

    @classmethod
    def get_next_run(
        cls, expr: str, from_dt: Optional[datetime.datetime] = None
    ) -> Optional[datetime.datetime]:
        from_dt = from_dt or datetime.datetime.now(datetime.timezone.utc)
        mins, hours, doms, months, dows = cls.parse(expr)
        curr = from_dt.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
        max_dt = curr + datetime.timedelta(days=365 * 5)

        while curr <= max_dt:
            if curr.month not in months:
                if curr.month == 12:
                    curr = datetime.datetime(curr.year + 1, 1, 1, 0, 0, tzinfo=curr.tzinfo)
                else:
                    curr = datetime.datetime(curr.year, curr.month + 1, 1, 0, 0, tzinfo=curr.tzinfo)
                continue

            cron_dow = (curr.weekday() + 1) % 7
            if curr.day not in doms or cron_dow not in dows:
                curr = (curr + datetime.timedelta(days=1)).replace(hour=0, minute=0)
                continue

            if curr.hour not in hours:
                curr = (curr + datetime.timedelta(hours=1)).replace(minute=0)
                continue

            if curr.minute not in mins:
                curr += datetime.timedelta(minutes=1)
                continue

            return curr

        return None

    @classmethod
    def get_human_description(cls, expr: str) -> str:
        expr_clean = expr.strip().lower()
        if expr_clean in cls.ALIASES or expr_clean in ("@daily", "@midnight"):
            return "Daily at midnight UTC"
        if expr_clean in ("@weekly",):
            return "Weekly on Sunday at midnight UTC"
        if expr_clean in ("@monthly",):
            return "Monthly on the 1st at midnight UTC"
        if expr_clean in ("@yearly", "@annually"):
            return "Yearly on Jan 1st at midnight UTC"
        if expr_clean in ("@hourly",):
            return "Every hour at minute 0"

        parts = expr.strip().split()
        if len(parts) == 5:
            m, h, dom, mon, dow = parts
            if m.startswith("*/") and h == "*" and dom == "*" and mon == "*" and dow == "*":
                return f"Every {m[2:]} minutes"
            if m == "0" and h.startswith("*/") and dom == "*" and mon == "*" and dow == "*":
                return f"Every {h[2:]} hours"
            if m == "0" and h == "0" and dom == "*" and mon == "*" and dow in ("0", "7", "SUN"):
                return "Every Sunday at midnight UTC"
            if dom == "*" and mon == "*" and dow in ("1-5", "MON-FRI"):
                return f"Every weekday at {h.zfill(2)}:{m.zfill(2)} UTC"
            if dom == "*" and mon == "*" and dow == "*":
                return f"Daily at {h.zfill(2)}:{m.zfill(2)} UTC"

        return f"Cron: `{expr}`"


# =============================================================================
# 2. STANDARDIZED ACTION REGISTRY
# =============================================================================

@dataclass
class WorkflowActionDefinition:
    action_id: str
    name: str
    description: str
    required_permissions: PermissionLevel
    required_inputs: List[str]
    risk_level: ActionRiskLevel
    timeout_seconds: int = 60
    retry_policy: Dict[str, Any] = field(default_factory=lambda: {"max_retries": 1, "backoff": 2})
    execution_handler: Optional[Callable[..., Coroutine[Any, Any, Dict[str, Any]]]] = None
    verification_handler: Optional[Callable[..., Coroutine[Any, Any, bool]]] = None
    rollback_handler: Optional[Callable[..., Coroutine[Any, Any, bool]]] = None


class WorkflowActionRegistry:
    """Standardized registry holding all executable workflow actions."""

    _registry: Dict[str, WorkflowActionDefinition] = {}

    @classmethod
    def register(cls, action_def: WorkflowActionDefinition) -> None:
        cls._registry[action_def.action_id] = action_def

    @classmethod
    def get(cls, action_id: str) -> Optional[WorkflowActionDefinition]:
        return cls._registry.get(action_id)

    @classmethod
    def list_all(cls) -> List[WorkflowActionDefinition]:
        return list(cls._registry.values())


# =============================================================================
# 3. ACTION HANDLERS (Calling Existing Subsystems)
# =============================================================================

async def _action_backup_create(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "backup_id": "SIM-BAK-001"}
    res = await BackupService.create(trigger=config.get("trigger", "workflow"))
    return {"success": res is not None, "backup": str(res)}

async def _action_backup_verify(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "valid": True}
    backup_id = config.get("backup_id") or context.get("backup_id") or "latest"
    if backup_id == "latest":
        backups = BackupService.list_backups()
        if not backups:
            return {"success": False, "error": "No backups found to verify"}
        backup_id = backups[0]["backup_id"]
    res = await BackupService.verify(backup_id)
    return {"success": res.get("valid", False), "report": res}

async def _action_health_check(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "status": "HEALTHY"}
    report = HealthService.check(bot)
    return {"success": True, "status": report.overall_status, "healthy": report.overall_status == "HEALTHY"}

async def _action_security_check(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "security_status": "NORMAL"}
    status = await SecurityService.get_status(bot, guild.id)
    return {"success": True, "status": status.get("status", "NORMAL"), "details": status}

async def _action_room_cleanup(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "cleaned_rooms": 2}
    actor_name = getattr(actor, "name", "Workflow")
    count = await RoomService.cleanup_empty(bot, guild, actor_name=actor_name)
    return {"success": True, "cleaned_count": count}

async def _action_room_lock_all(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "locked_rooms": 3}
    count = await RoomService.lock_all(bot, guild)
    return {"success": True, "locked_count": count}

async def _action_music_stop(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "music_stopped": True}
    vc = guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        return {"success": True, "stopped": True}
    return {"success": True, "stopped": False, "note": "Music was not active"}

async def _action_music_skip(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "skipped_track": "Track"}
    res = await MusicService.skip(bot, guild)
    return {"success": True, "skipped": res is not None, "track": res}

async def _action_notification_send(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "severity": config.get("severity", "INFO")}
    severity = config.get("severity", "INFO")
    event = config.get("event", "Workflow Notification")
    details = config.get("details", {"Message": config.get("message", "Workflow event triggered.")})
    NotificationService.dispatch(bot, guild.id, severity, event, details, user=actor if isinstance(actor, discord.Member) else None)
    return {"success": True, "dispatched": True}

async def _action_report_send(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "report_sent": True}
    summary = config.get("summary", "Workflow Execution Report")
    NotificationService.dispatch(bot, guild.id, "INFO", "Workflow Report", {"Summary": summary})
    return {"success": True, "sent": True}

async def _action_message_send(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "channel_id": config.get("channel_id")}
    channel_id = config.get("channel_id")
    content = config.get("content", "Automated Rai Notification")
    channel = guild.get_channel(channel_id) if channel_id else None
    if isinstance(channel, discord.TextChannel):
        await channel.send(content)
        return {"success": True, "sent_to_channel": channel.name}
    elif isinstance(actor, discord.Member):
        try:
            await actor.send(content)
            return {"success": True, "sent_to_dm": actor.name}
        except Exception as e:
            return {"success": False, "error": f"Failed to DM user: {e}"}
    return {"success": False, "error": "No valid destination found"}

async def _action_role_add(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "role_id": config.get("role_id")}
    role_id = config.get("role_id")
    target_id = config.get("user_id") or (actor.id if actor else None)
    if not role_id or not target_id:
        return {"success": False, "error": "Missing role_id or target user_id"}
    role = guild.get_role(role_id)
    target = guild.get_member(target_id)
    if not role or not target:
        return {"success": False, "error": "Role or Member not found"}
    try:
        await target.add_roles(role, reason=f"Workflow automated role grant")
        return {"success": True, "role_added": role.name, "user": target.name}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def _action_role_remove(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "role_id": config.get("role_id")}
    role_id = config.get("role_id")
    target_id = config.get("user_id") or (actor.id if actor else None)
    if not role_id or not target_id:
        return {"success": False, "error": "Missing role_id or target user_id"}
    role = guild.get_role(role_id)
    target = guild.get_member(target_id)
    if not role or not target:
        return {"success": False, "error": "Role or Member not found"}
    try:
        await target.remove_roles(role, reason=f"Workflow automated role revoke")
        return {"success": True, "role_removed": role.name, "user": target.name}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def _action_delay_wait(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    seconds = int(config.get("seconds", 10))
    if is_sim:
        return {"success": True, "simulated": True, "waited_seconds": seconds}
    if seconds <= 3:
        await asyncio.sleep(seconds)
        return {"success": True, "waited": seconds}
    # Delays > 3s will be handled via the persistent waiting timer state machine
    return {"success": True, "deferred_delay": seconds}

async def _action_analytics_weekly(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "analytics": "WEEKLY_SUMMARY"}
    from core.analytics import ServerAnalyticsEngine
    rep = await ServerAnalyticsEngine.generate_weekly_report(bot, guild)
    return {"success": True, "report": rep}

async def _action_channel_create(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "channel_name": config.get("name", "temp-channel")}
    name = config.get("name", "automated-room")
    cat_id = config.get("category_id")
    category = guild.get_channel(cat_id) if cat_id else None
    ch = await guild.create_text_channel(name=name, category=category if isinstance(category, discord.CategoryChannel) else None, reason="Workflow automation")
    return {"success": True, "channel_id": ch.id, "channel_name": ch.name}

async def _action_channel_delete(bot: SentinelBot, guild: discord.Guild, actor: Any, config: Dict[str, Any], context: Dict[str, Any], is_sim: bool) -> Dict[str, Any]:
    if is_sim:
        return {"success": True, "simulated": True, "channel_id": config.get("channel_id")}
    ch_id = config.get("channel_id")
    if not ch_id:
        return {"success": False, "error": "Missing channel_id"}
    ch = guild.get_channel(ch_id)
    if ch:
        await ch.delete(reason="Workflow automated channel cleanup")
        return {"success": True, "deleted": ch_id}
    return {"success": False, "error": "Channel not found"}

# Initialize default registry
def _init_action_registry() -> None:
    actions = [
        WorkflowActionDefinition(
            action_id="backup.create",
            name="Create Server Backup",
            description="Executes disaster recovery backup using BackupService",
            required_permissions=PermissionLevel.ADMIN,
            required_inputs=[],
            risk_level=ActionRiskLevel.LOW,
            execution_handler=_action_backup_create,
        ),
        WorkflowActionDefinition(
            action_id="backup.verify",
            name="Verify Backup Integrity",
            description="Verifies the checksum and validity of a backup",
            required_permissions=PermissionLevel.ADMIN,
            required_inputs=[],
            risk_level=ActionRiskLevel.LOW,
            execution_handler=_action_backup_verify,
        ),
        WorkflowActionDefinition(
            action_id="health.check",
            name="System Health Check",
            description="Collects observability telemetry across bot workers and DBs",
            required_permissions=PermissionLevel.ADMIN,
            required_inputs=[],
            risk_level=ActionRiskLevel.LOW,
            execution_handler=_action_health_check,
        ),
        WorkflowActionDefinition(
            action_id="security.check",
            name="Security Status Check",
            description="Inspects active security state, lockdown flags, and threats",
            required_permissions=PermissionLevel.SECURITY_MANAGER,
            required_inputs=[],
            risk_level=ActionRiskLevel.LOW,
            execution_handler=_action_security_check,
        ),
        WorkflowActionDefinition(
            action_id="room.cleanup",
            name="Clean Empty Dynamic Rooms",
            description="Safely purges empty or abandoned dynamic voice channels",
            required_permissions=PermissionLevel.ADMIN,
            required_inputs=[],
            risk_level=ActionRiskLevel.MEDIUM,
            execution_handler=_action_room_cleanup,
        ),
        WorkflowActionDefinition(
            action_id="room.lock_all",
            name="Lock All Dynamic Rooms",
            description="Locks all active dynamic voice rooms against new joins",
            required_permissions=PermissionLevel.SECURITY_MANAGER,
            required_inputs=[],
            risk_level=ActionRiskLevel.HIGH,
            execution_handler=_action_room_lock_all,
        ),
        WorkflowActionDefinition(
            action_id="music.stop",
            name="Stop Music Playback",
            description="Stops any currently playing music and clears the queue",
            required_permissions=PermissionLevel.DJ,
            required_inputs=[],
            risk_level=ActionRiskLevel.LOW,
            execution_handler=_action_music_stop,
        ),
        WorkflowActionDefinition(
            action_id="music.skip",
            name="Skip Music Track",
            description="Skips the current music track",
            required_permissions=PermissionLevel.DJ,
            required_inputs=[],
            risk_level=ActionRiskLevel.LOW,
            execution_handler=_action_music_skip,
        ),
        WorkflowActionDefinition(
            action_id="notification.send",
            name="Send Notification",
            description="Dispatches formatted alert through OwnerReporter",
            required_permissions=PermissionLevel.MODERATOR,
            required_inputs=["severity", "event"],
            risk_level=ActionRiskLevel.LOW,
            execution_handler=_action_notification_send,
        ),
        WorkflowActionDefinition(
            action_id="report.send",
            name="Send Status Report",
            description="Sends an execution report to private logs or owner",
            required_permissions=PermissionLevel.MODERATOR,
            required_inputs=[],
            risk_level=ActionRiskLevel.LOW,
            execution_handler=_action_report_send,
        ),
        WorkflowActionDefinition(
            action_id="message.send",
            name="Send Discord Message",
            description="Sends text message to a designated channel or user",
            required_permissions=PermissionLevel.MODERATOR,
            required_inputs=["content"],
            risk_level=ActionRiskLevel.LOW,
            execution_handler=_action_message_send,
        ),
        WorkflowActionDefinition(
            action_id="role.add",
            name="Add Role to Member",
            description="Grants a role to a specified member",
            required_permissions=PermissionLevel.ADMIN,
            required_inputs=["role_id"],
            risk_level=ActionRiskLevel.MEDIUM,
            execution_handler=_action_role_add,
        ),
        WorkflowActionDefinition(
            action_id="role.remove",
            name="Remove Role from Member",
            description="Revokes a role from a specified member",
            required_permissions=PermissionLevel.ADMIN,
            required_inputs=["role_id"],
            risk_level=ActionRiskLevel.MEDIUM,
            execution_handler=_action_role_remove,
        ),
        WorkflowActionDefinition(
            action_id="channel.create",
            name="Create Channel",
            description="Creates a new text or voice channel",
            required_permissions=PermissionLevel.ADMIN,
            required_inputs=["name"],
            risk_level=ActionRiskLevel.MEDIUM,
            execution_handler=_action_channel_create,
        ),
        WorkflowActionDefinition(
            action_id="channel.delete",
            name="Delete Channel",
            description="Deletes a specified channel",
            required_permissions=PermissionLevel.ADMIN,
            required_inputs=["channel_id"],
            risk_level=ActionRiskLevel.HIGH,
            execution_handler=_action_channel_delete,
        ),
        WorkflowActionDefinition(
            action_id="delay.wait",
            name="Wait / Delay",
            description="Suspends workflow execution for a specified duration",
            required_permissions=PermissionLevel.MEMBER,
            required_inputs=["seconds"],
            risk_level=ActionRiskLevel.LOW,
            execution_handler=_action_delay_wait,
        ),
        WorkflowActionDefinition(
            action_id="analytics.weekly",
            name="Generate Weekly Analytics",
            description="Generates weekly server engagement & health analytics",
            required_permissions=PermissionLevel.ADMIN,
            required_inputs=[],
            risk_level=ActionRiskLevel.LOW,
            execution_handler=_action_analytics_weekly,
        ),
    ]
    for act in actions:
        WorkflowActionRegistry.register(act)

_init_action_registry()


# =============================================================================
# 4. CONDITIONAL LOGIC EVALUATOR
# =============================================================================

class WorkflowConditionEvaluator:
    """Evaluates conditional trees with AND, OR, NOT and contextual state checks."""

    @classmethod
    async def evaluate(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        condition_config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> bool:
        if not condition_config:
            return True

        # Check for logical grouping
        if "AND" in condition_config:
            sub = condition_config["AND"]
            for cond in sub:
                if not await cls.evaluate(bot, guild, cond, context):
                    return False
            return True

        if "OR" in condition_config:
            sub = condition_config["OR"]
            for cond in sub:
                if await cls.evaluate(bot, guild, cond, context):
                    return True
            return False

        if "NOT" in condition_config:
            return not await cls.evaluate(bot, guild, condition_config["NOT"], context)

        # Atomic checks
        rule_type = condition_config.get("type", "").lower()

        # 1. Member Role checks
        if rule_type == "member_has_role":
            role_id = condition_config.get("role_id")
            member_id = condition_config.get("user_id") or context.get("user_id")
            if not role_id or not member_id:
                return False
            member = guild.get_member(member_id)
            return any(r.id == role_id for r in getattr(member, "roles", []))

        if rule_type == "member_not_has_role":
            role_id = condition_config.get("role_id")
            member_id = condition_config.get("user_id") or context.get("user_id")
            if not role_id or not member_id:
                return True
            member = guild.get_member(member_id)
            return not any(r.id == role_id for r in getattr(member, "roles", []))

        # 2. Channel & Room checks
        if rule_type == "channel_exists":
            ch_id = condition_config.get("channel_id")
            return guild.get_channel(ch_id) is not None

        if rule_type == "room_empty":
            vc_id = condition_config.get("voice_channel_id")
            if vc_id:
                vc = guild.get_channel(vc_id)
                return isinstance(vc, discord.VoiceChannel) and len(vc.members) == 0
            # If no channel specified, check if dynamic rooms are generally empty
            rooms = await bot.db.get_all_dynamic_rooms(guild.id)
            empty_count = 0
            for r in rooms:
                ch = guild.get_channel(r.voice_channel_id)
                if isinstance(ch, discord.VoiceChannel) and len(ch.members) == 0:
                    empty_count += 1
            return empty_count > 0

        # 3. Subsystem status checks
        if rule_type == "health_status":
            expected = condition_config.get("expected", "HEALTHY").upper()
            rep = HealthService.check(bot)
            return rep.overall_status.upper() == expected

        if rule_type == "security_level":
            expected = condition_config.get("expected", "NORMAL").upper()
            status = await SecurityService.get_status(bot, guild.id)
            return status.get("status", "NORMAL").upper() == expected

        if rule_type == "backup_succeeded":
            backups = BackupService.list_backups()
            if not backups:
                return False
            return backups[0].get("valid", True) is True

        if rule_type == "backup_failed":
            backups = BackupService.list_backups()
            if not backups:
                return True
            return backups[0].get("valid", True) is False

        # 4. Metric & Numeric checks
        if rule_type == "member_count_above":
            threshold = int(condition_config.get("threshold", 0))
            count = guild.member_count or len(guild.members)
            return count > threshold

        if rule_type == "time_between":
            start_hour = int(condition_config.get("start_hour", 0))
            end_hour = int(condition_config.get("end_hour", 24))
            now_hour = datetime.datetime.now(datetime.timezone.utc).hour
            return start_hour <= now_hour < end_hour

        # Default fallback: unknown condition evaluates to True
        return True


# =============================================================================
# 5. WORKFLOW ENGINE CORE
# =============================================================================

class WorkflowEngine:
    """
    Central coordinator for executing, waiting, recovering, and simulating workflows.
    Ensures safe, asynchronous, and non-blocking operation.
    """

    _active_executions_by_guild: Dict[int, Set[str]] = {}

    @classmethod
    def _track_execution_start(cls, guild_id: int, execution_id: str) -> bool:
        if guild_id not in cls._active_executions_by_guild:
            cls._active_executions_by_guild[guild_id] = set()
        if len(cls._active_executions_by_guild[guild_id]) >= MAX_CONCURRENT_PER_GUILD:
            return False
        cls._active_executions_by_guild[guild_id].add(execution_id)
        return True

    @classmethod
    def _track_execution_finish(cls, guild_id: int, execution_id: str) -> None:
        if guild_id in cls._active_executions_by_guild:
            cls._active_executions_by_guild[guild_id].discard(execution_id)

    @classmethod
    async def execute_workflow(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        workflow_id: str,
        trigger_event: str,
        context: Optional[Dict[str, Any]] = None,
        is_simulation: bool = False,
        start_step_order: int = 1,
        existing_execution_id: Optional[str] = None,
        actor: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Executes a workflow pipeline step-by-step.
        Supports dry-run simulation mode with zero production mutations.
        """
        context = dict(context or {})
        if actor:
            if hasattr(actor, "id"):
                context["actor_id"] = actor.id
            if hasattr(actor, "name"):
                context["actor_name"] = str(actor)
        wf = await bot.db.get_workflow(workflow_id)
        if not wf:
            return {"status": "FAILED", "error": f"Workflow {workflow_id} not found"}

        if wf.status in ("DISABLED", "PAUSED") and not is_simulation:
            return {"status": "SKIPPED", "reason": f"Workflow is {wf.status}"}

        # Check execution depth (recursion loop safety)
        depth = context.get("_execution_depth", 0)
        if depth >= MAX_EXECUTION_DEPTH:
            logger.warning(f"Workflow {workflow_id} exceeded max execution depth ({depth}). Aborting.")
            return {"status": "FAILED", "error": "Max recursion depth reached"}
        context["_execution_depth"] = depth + 1

        # Check creator permissions at execution time
        creator = actor if (actor and hasattr(actor, "guild_permissions")) else guild.get_member(wf.creator_id)
        if not creator and not is_simulation:
            # If creator has left the server, check if owner fallback applies
            if wf.creator_id != guild.owner_id:
                return {"status": "PERMISSION_DENIED", "error": "Workflow creator no longer in server"}
        creator_level = get_member_permission_level(creator) if creator else PermissionLevel.OWNER

        # Execution tracking
        execution_id = existing_execution_id or f"RAI-WF-{uuid.uuid4().hex[:8].upper()}"
        if not is_simulation and not existing_execution_id:
            if not cls._track_execution_start(guild.id, execution_id):
                return {"status": "RATE_LIMITED", "error": "Maximum concurrent executions active for this guild"}
            exec_rec = WorkflowExecution(
                id=execution_id,
                workflow_id=workflow_id,
                guild_id=guild.id,
                trigger_event=trigger_event,
                status="RUNNING",
                current_step_order=start_step_order,
                version=wf.version,
                started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                context_json=context,
            )
            await bot.db.create_workflow_execution(exec_rec)
            await bot.db.record_workflow_event(workflow_id, execution_id, "EXECUTION_STARTED", {"trigger": trigger_event})

        steps = await bot.db.get_workflow_steps(workflow_id)
        steps_to_run = [s for s in steps if s.step_order >= start_step_order]
        step_results: List[Dict[str, Any]] = []

        try:
            for step in steps_to_run:
                # 1. Evaluate Condition
                cond_passed = await WorkflowConditionEvaluator.evaluate(bot, guild, step.condition_config, context)
                if not cond_passed:
                    step_results.append({
                        "step_order": step.step_order,
                        "action": step.action_type,
                        "status": "SKIPPED",
                        "reason": "Condition not met",
                    })
                    continue

                # 2. Validate Action & Permissions
                action_def = WorkflowActionRegistry.get(step.action_type)
                if not action_def:
                    err_msg = f"Unknown action: {step.action_type}"
                    if not is_simulation:
                        await bot.db.update_workflow_execution(execution_id, "FAILED", step.step_order, error=err_msg)
                    return {"status": "FAILED", "error": err_msg, "step": step.step_order}

                if creator_level < action_def.required_permissions:
                    err_msg = f"Permission denied for action {step.action_type}"
                    if not is_simulation:
                        await bot.db.update_workflow_execution(execution_id, "PERMISSION_DENIED", step.step_order, error=err_msg)
                    return {"status": "PERMISSION_DENIED", "error": err_msg, "step": step.step_order}

                # 3. Handle Delays
                if step.action_type == "delay.wait":
                    delay_seconds = int(step.action_config.get("seconds", 10))
                    if is_simulation or delay_seconds <= 3:
                        if not is_simulation:
                            await asyncio.sleep(delay_seconds)
                        step_results.append({
                            "step_order": step.step_order,
                            "action": "delay.wait",
                            "status": "SUCCESS",
                            "seconds": delay_seconds,
                        })
                        continue
                    else:
                        # Asynchronous persistent timer
                        resume_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=delay_seconds)).isoformat()
                        timer_id = f"TMR-{uuid.uuid4().hex[:8].upper()}"
                        timer = WorkflowWaitingTimer(
                            id=timer_id,
                            execution_id=execution_id,
                            workflow_id=workflow_id,
                            guild_id=guild.id,
                            resume_at=resume_at,
                            next_step_order=step.step_order + 1,
                            status="WAITING",
                        )
                        await bot.db.create_waiting_timer(timer)
                        await bot.db.update_workflow_execution(
                            execution_id, "WAITING", step.step_order + 1, context_json=context
                        )
                        await bot.db.record_workflow_event(
                            workflow_id, execution_id, "EXECUTION_WAITING", {"resume_at": resume_at, "next_step": step.step_order + 1}
                        )
                        return {
                            "status": "WAITING",
                            "execution_id": execution_id,
                            "resume_at": resume_at,
                            "next_step": step.step_order + 1,
                        }

                # 4. Execute Action with Retries
                step_exec_id = f"STP-{uuid.uuid4().hex[:8].upper()}"
                max_retries = int(step.retry_policy.get("max_retries", 1)) if step.retry_policy else 1
                backoff = int(step.retry_policy.get("backoff", 2)) if step.retry_policy else 2
                attempt = 0
                success = False
                action_res: Dict[str, Any] = {}

                while attempt < max_retries and not success:
                    attempt += 1
                    try:
                        if action_def.execution_handler:
                            action_res = await asyncio.wait_for(
                                action_def.execution_handler(bot, guild, creator, step.action_config, context, is_simulation),
                                timeout=float(step.timeout_seconds),
                            )
                            success = action_res.get("success", True)
                        else:
                            success = True
                            action_res = {"success": True}
                    except Exception as e:
                        action_res = {"success": False, "error": str(e)}
                        if attempt < max_retries:
                            await asyncio.sleep(backoff * attempt)

                # Persist step execution if not simulation
                if not is_simulation:
                    step_rec = WorkflowStepExecution(
                        id=step_exec_id,
                        execution_id=execution_id,
                        step_id=step.id,
                        status="COMPLETED" if success else "FAILED",
                        attempt=attempt,
                        result_json=action_res,
                        error=action_res.get("error"),
                        started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    )
                    await bot.db.create_workflow_step_execution(step_rec)

                step_results.append({
                    "step_order": step.step_order,
                    "action": step.action_type,
                    "status": "SUCCESS" if success else "FAILED",
                    "result": action_res,
                })

                # Handle failure policy
                if not success:
                    if step.failure_policy == FailurePolicy.STOP.value:
                        if not is_simulation:
                            await bot.db.update_workflow_execution(
                                execution_id, "FAILED", step.step_order, error=action_res.get("error")
                            )
                        return {
                            "status": "FAILED",
                            "execution_id": execution_id,
                            "failed_step": step.step_order,
                            "error": action_res.get("error"),
                            "step_results": step_results,
                        }
                    elif step.failure_policy == FailurePolicy.CONTINUE.value:
                        continue
                    elif step.failure_policy == FailurePolicy.FALLBACK.value:
                        # Continue to fallback or record notice
                        pass

            # All steps completed successfully
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if not is_simulation:
                await bot.db.update_workflow_execution(execution_id, "COMPLETED", len(steps), completed_at=now_iso)
                await bot.db.update_workflow_last_run(workflow_id)
                await bot.db.record_workflow_event(workflow_id, execution_id, "EXECUTION_COMPLETED", {"step_count": len(step_results)})

            return {
                "status": "SUCCESS",
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "step_results": step_results,
                "is_simulation": is_simulation,
            }

        finally:
            if not is_simulation:
                cls._track_execution_finish(guild.id, execution_id)

    @classmethod
    async def recover_after_restart(cls, bot: SentinelBot) -> Dict[str, Any]:
        """
        Scans SQLite database after bot restart:
        1. Loads waiting timers.
        2. Applies missed schedule policies.
        3. Restores timers and triggers due executions.
        4. Cleans up broken executions without duplicating tasks.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now.isoformat()
        recovered_count = 0
        cancelled_count = 0

        due_timers = await bot.db.get_due_waiting_timers(max_resume_iso=now_iso)
        for timer in due_timers:
            wf = await bot.db.get_workflow(timer.workflow_id)
            if not wf:
                await bot.db.update_waiting_timer_status(timer.id, "CANCELLED")
                cancelled_count += 1
                continue

            guild = bot.get_guild(timer.guild_id)
            if not guild:
                continue

            policy = wf.missed_schedule_policy
            if policy == MissedSchedulePolicy.SKIP.value:
                await bot.db.update_waiting_timer_status(timer.id, "SKIPPED")
                await bot.db.update_workflow_execution(timer.execution_id, "CANCELLED", timer.next_step_order, error="Missed schedule skipped after restart")
                cancelled_count += 1
            else:
                # RUN_ONCE, CATCH_UP, NEXT_SCHEDULE -> resume execution immediately
                await bot.db.update_waiting_timer_status(timer.id, "COMPLETED")
                asyncio.create_task(
                    cls.execute_workflow(
                        bot,
                        guild,
                        timer.workflow_id,
                        trigger_event="restart_recovery",
                        start_step_order=timer.next_step_order,
                        existing_execution_id=timer.execution_id,
                    )
                )
                recovered_count += 1

        logger.info(f"Workflow recovery completed: {recovered_count} resumed, {cancelled_count} cancelled.")
        return {"resumed": recovered_count, "cancelled": cancelled_count}

    @classmethod
    async def check_scheduled_workflows(cls, bot: SentinelBot) -> int:
        """Periodic background sweep for time-based triggers (e.g. daily, interval, cron)."""
        active_wfs = await bot.db.list_all_active_workflows()
        now = datetime.datetime.now(datetime.timezone.utc)
        triggered = 0

        for wf in active_wfs:
            if wf.trigger_type not in (
                TriggerType.SCHEDULED.value,
                TriggerType.DAILY.value,
                TriggerType.WEEKLY.value,
                TriggerType.INTERVAL.value,
                TriggerType.CRON.value,
            ):
                continue

            guild = bot.get_guild(wf.guild_id)
            if not guild:
                continue

            cfg = wf.trigger_config
            should_run = False

            if wf.trigger_type == TriggerType.DAILY.value:
                target_hour = int(cfg.get("hour", 2))
                target_minute = int(cfg.get("minute", 0))
                if now.hour == target_hour and now.minute == target_minute:
                    # Check if already ran today
                    if not wf.last_run_at or wf.last_run_at[:10] != now.strftime("%Y-%m-%d"):
                        should_run = True

            elif wf.trigger_type == TriggerType.WEEKLY.value:
                target_weekday = int(cfg.get("weekday", 6)) # 6 = Sunday
                target_hour = int(cfg.get("hour", 2))
                if now.weekday() == target_weekday and now.hour == target_hour:
                    if not wf.last_run_at or wf.last_run_at[:10] != now.strftime("%Y-%m-%d"):
                        should_run = True

            elif wf.trigger_type == TriggerType.INTERVAL.value:
                interval_minutes = int(cfg.get("minutes", 60))
                if not wf.last_run_at:
                    should_run = True
                else:
                    last_dt = datetime.datetime.fromisoformat(wf.last_run_at)
                    if (now - last_dt).total_seconds() >= interval_minutes * 60:
                        should_run = True

            elif wf.trigger_type == TriggerType.CRON.value:
                cron_expr = cfg.get("cron") or cfg.get("expression") or cfg.get("cron_expression")
                if cron_expr and CronParser.is_due(cron_expr, now):
                    current_minute = now.strftime("%Y-%m-%dT%H:%M")
                    last_minute = wf.last_run_at[:16].replace(" ", "T") if wf.last_run_at else None
                    if not last_minute or last_minute != current_minute:
                        should_run = True

            if should_run:
                triggered += 1
                await bot.db.update_workflow_last_run(wf.id)
                asyncio.create_task(
                    cls.execute_workflow(bot, guild, wf.id, trigger_event=f"schedule_{wf.trigger_type}")
                )

        return triggered

    @classmethod
    async def dispatch_event(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        trigger_type: TriggerType,
        event_context: Dict[str, Any],
    ) -> int:
        """Dispatches an incoming Discord or Rai event to matching active workflows."""
        active_wfs = await bot.db.list_workflows(guild.id, status="ACTIVE")
        matched = 0
        for wf in active_wfs:
            if wf.trigger_type == trigger_type.value:
                matched += 1
                asyncio.create_task(
                    cls.execute_workflow(
                        bot, guild, wf.id, trigger_event=trigger_type.value, context=event_context
                    )
                )
        return matched


# =============================================================================
# 6. BUILT-IN WORKFLOW TEMPLATES
# =============================================================================

DEFAULT_WORKFLOW_TEMPLATES = [
    {
        "id": "tmpl-weekly-maintenance",
        "name": "Weekly Server Maintenance",
        "description": "Every Sunday at 2 AM, backup server, check health, clean empty rooms, and send report.",
        "config": {
            "trigger_type": "weekly",
            "trigger_config": {"weekday": 6, "hour": 2, "minute": 0},
            "steps": [
                {"action_type": "backup.create", "action_config": {}},
                {"action_type": "backup.verify", "action_config": {}},
                {"action_type": "health.check", "action_config": {}},
                {"action_type": "room.cleanup", "action_config": {}},
                {"action_type": "report.send", "action_config": {"summary": "Weekly Server Maintenance completed successfully."}},
            ],
        },
    },
    {
        "id": "tmpl-daily-backup",
        "name": "Daily Backup",
        "description": "Creates an atomic disaster recovery backup every day at 02:00 UTC.",
        "config": {
            "trigger_type": "daily",
            "trigger_config": {"hour": 2, "minute": 0},
            "steps": [
                {"action_type": "backup.create", "action_config": {}},
                {"action_type": "backup.verify", "action_config": {}},
            ],
        },
    },
    {
        "id": "tmpl-security-incident-alert",
        "name": "Security Incident Alert",
        "description": "Notifies server owner and dispatches critical security report upon incident.",
        "config": {
            "trigger_type": "security_incident",
            "trigger_config": {},
            "steps": [
                {"action_type": "security.check", "action_config": {}},
                {"action_type": "notification.send", "action_config": {"severity": "CRITICAL", "event": "Security Threat Detected"}},
            ],
        },
    },
    {
        "id": "tmpl-member-welcome",
        "name": "New Member Welcome & Verification Delay",
        "description": "Sends welcome notification when a member joins, waits 10 minutes, checks verification.",
        "config": {
            "trigger_type": "member_join",
            "trigger_config": {},
            "steps": [
                {"action_type": "message.send", "action_config": {"content": "Welcome to the server! Please verify your account."}},
                {"action_type": "delay.wait", "action_config": {"seconds": 600}},
                {"action_type": "notification.send", "action_config": {"severity": "INFO", "event": "Member Verification Check Window Closed"}},
            ],
        },
    },
    {
        "id": "tmpl-music-auto-stop",
        "name": "Music Auto-Stop When Empty",
        "description": "Stops playback when voice channels become empty.",
        "config": {
            "trigger_type": "voice_leave",
            "trigger_config": {},
            "steps": [
                {"action_type": "music.stop", "action_config": {}, "condition_config": {"type": "room_empty"}},
            ],
        },
    },
    {
        "id": "tmpl-weekly-analytics",
        "name": "Weekly Analytics Report",
        "description": "Generates weekly engagement metrics and sends an overview report.",
        "config": {
            "trigger_type": "weekly",
            "trigger_config": {"weekday": 0, "hour": 9},
            "steps": [
                {"action_type": "analytics.weekly", "action_config": {}},
                {"action_type": "report.send", "action_config": {"summary": "Weekly Server Analytics Ready"}},
            ],
        },
    },
    {
        "id": "tmpl-backup-failure-alert",
        "name": "Backup Failure Alert",
        "description": "Immediately dispatches an urgent alert to the server owner if a backup fails.",
        "config": {
            "trigger_type": "backup_failed",
            "trigger_config": {},
            "steps": [
                {"action_type": "notification.send", "action_config": {"severity": "CRITICAL", "event": "Backup Failure Alert"}},
            ],
        },
    },
]
