"""
Mass User Mention Spam Protection Engine for 『RΛI』.
Protects Discord servers from malicious actors spamming member IDs across channels.

Features:
- Parsed Discord mentions + raw mention regex extraction (<@123456>, <@!123456>)
- Multi-tier sliding window rate limits (LOW/SUSPICIOUS, HIGH_RISK, CRITICAL)
- Cross-channel tracking: tracks attack moving from Channel A -> B -> C -> D
- Duplicate content detection (hashing mention bodies)
- Coordinated multi-user raid detection
- Automatic targeted message purge (attacker's messages only within time window)
- Explicit structured return types across all detection, moderation, and cleanup pipelines
- Safe staff notification (no @everyone or mass pings)
- Full isolation from music and other subsystems
- Persistent incident logging in SQLite with memory fallback
"""

from __future__ import annotations

import asyncio
import collections
import datetime
import enum
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

import discord

from config.settings import Colors, Branding
from core.results import (
    Result,
    ResultStatus,
    ResultError,
    ErrorCodes,
    DeleteMessageData,
    ModerationData,
    PermissionCheckData,
    OperationSummary,
    DatabaseResultData,
)
from database.models import MentionSpamConfig, MentionSpamIncident
from utils.embeds import (
    create_embed,
    security_alert_embed,
    DEFAULT_BRAND,
    DEFAULT_FOOTER,
)
from utils.permissions import is_founder_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger("Rai.MentionSpam")

# Regex to detect unparsed or raw Discord mention tokens: <@123456789...> or <@!123456789...>
USER_MENTION_REGEX = re.compile(r"<@!?(\d{15,21})>")


# ==========================================
# TYPED DETECTION AND PIPELINE MODELS
# ==========================================

class DetectionStatus(str, enum.Enum):
    """Explicit detection outcome states for mention spam inspection."""
    NO_THREAT = "NO_THREAT"
    SUSPICIOUS = "SUSPICIOUS"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL = "CRITICAL"
    IGNORED = "IGNORED"
    INVALID = "INVALID"
    ERROR = "ERROR"


@dataclass(frozen=True)
class DetectionResult:
    """Diagnostic data returned by threat detection evaluation."""
    status: DetectionStatus
    mention_count: int
    message_count: int
    channels_affected: int
    incident_id: Optional[str] = None
    reason: Optional[str] = None
    targets: Set[int] = field(default_factory=set)
    stats: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MentionSpamResult:
    """Overall structured pipeline result covering detection, containment, and cleanup."""
    detected: bool
    severity: str
    mentions: int
    messages: int
    channels: int
    action_status: ResultStatus
    cleanup_status: ResultStatus
    incident_id: Optional[str]
    detection: Optional[DetectionResult] = None
    delete_result: Optional[Result[DeleteMessageData]] = None
    restriction_result: Optional[Result[ModerationData]] = None
    cleanup_result: Optional[Result[OperationSummary]] = None
    db_result: Optional[Result[DatabaseResultData]] = None
    is_coordinated: bool = False
    action_summary: str = ""

    def __bool__(self) -> bool:
        """Enables backward-compatible boolean evaluation (True if threat detected & handled)."""
        return self.detected


@dataclass
class MentionEvent:
    timestamp: float
    channel_id: int
    mention_count: int
    targets: Set[int]
    content_hash: str
    message_id: int


class UserMentionTracker:
    """Tracks sliding window mention activity for an individual user across the server."""

    def __init__(self, max_history: int = 100):
        self.events: collections.deque[MentionEvent] = collections.deque(maxlen=max_history)

    def record_event(
        self,
        channel_id: int,
        mention_count: int,
        targets: Set[int],
        content_hash: str,
        message_id: int,
    ) -> None:
        self.events.append(
            MentionEvent(
                timestamp=time.time(),
                channel_id=channel_id,
                mention_count=mention_count,
                targets=targets,
                content_hash=content_hash,
                message_id=message_id,
            )
        )

    def get_window_stats(self, window_seconds: float, current_hash: str) -> Dict[str, Any]:
        now = time.time()
        recent = [e for e in self.events if now - e.timestamp <= window_seconds]
        if not recent:
            return {
                "total_mentions": 0,
                "message_count": 0,
                "channels_affected": [],
                "unique_targets": 0,
                "repeat_count": 0,
                "duration_seconds": 0.0,
                "first_seen": now,
                "last_seen": now,
            }

        channels = list(set(e.channel_id for e in recent))
        all_targets: Set[int] = set()
        for e in recent:
            all_targets.update(e.targets)

        repeat_count = sum(1 for e in recent if e.content_hash == current_hash)
        duration = max(0.1, recent[-1].timestamp - recent[0].timestamp)

        return {
            "total_mentions": sum(e.mention_count for e in recent),
            "message_count": len(recent),
            "channels_affected": channels,
            "unique_targets": len(all_targets),
            "repeat_count": repeat_count,
            "duration_seconds": round(duration, 1),
            "first_seen": recent[0].timestamp,
            "last_seen": recent[-1].timestamp,
        }


class MentionSpamEngine:
    """
    Central Mass User Mention Spam Protection Coordinator.
    Monitors, contains, and mitigates multi-user and cross-channel mention floods.
    Returns typed, invariant-enforcing Result containers across all operations.
    """

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # Trackers: (guild_id, user_id) -> UserMentionTracker
        self._user_trackers: Dict[Tuple[int, int], UserMentionTracker] = {}
        # Guild correlation for multi-user coordinated spam: guild_id -> deque of (timestamp, user_id, channel_id)
        self._guild_correlation: Dict[int, collections.deque[Tuple[float, int, int]]] = collections.defaultdict(
            lambda: collections.deque(maxlen=200)
        )
        self._lock = asyncio.Lock()
        self._last_cleanup = time.time()

    def _cleanup_expired_trackers(self, ttl_seconds: float = 120.0) -> None:
        """Periodic cleanup to protect memory bounds on large servers."""
        now = time.time()
        if now - self._last_cleanup < 60.0:
            return
        self._last_cleanup = now

        expired = []
        for (g_id, u_id), tracker in self._user_trackers.items():
            if not tracker.events or (now - tracker.events[-1].timestamp > ttl_seconds):
                expired.append((g_id, u_id))
        for key in expired:
            self._user_trackers.pop(key, None)

    @staticmethod
    def extract_mentions(message: discord.Message) -> Set[int]:
        """Extracts unique member target IDs from both parsed mentions and raw regex tokens."""
        targets: Set[int] = set()
        # 1. Parsed Discord mentions
        if message.mentions:
            for m in message.mentions:
                if m.id != message.author.id:
                    targets.add(m.id)

        # 2. Raw regex tokens (<@123456...> or <@!123456...>)
        raw_matches = USER_MENTION_REGEX.findall(message.content or "")
        for match in raw_matches:
            try:
                uid = int(match)
                if uid != message.author.id:
                    targets.add(uid)
            except ValueError:
                logger.debug(f"Ignoring non-integer mention token: {match}")

        return targets

    @staticmethod
    def compute_mention_hash(content: str) -> str:
        """Generates hash of normalized message mentions to identify repeated spam."""
        tokens = USER_MENTION_REGEX.findall(content or "")
        normalized = " ".join(sorted(tokens))
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    async def is_exempt(self, member: discord.Member, config: MentionSpamConfig) -> bool:
        """Determines if the member is exempt from mention spam enforcement."""
        if not member or member.bot:
            return True
        if is_founder_or_owner(member):
            return True
        if not config.staff_exempt:
            return False

        # Check Discord administrative / moderation permissions
        perms = member.guild_permissions
        if perms.administrator or perms.manage_guild or perms.moderate_members:
            return True

        # Check Whitelist in DB
        try:
            is_wl = await self.bot.db.is_whitelisted(member.guild.id, member.id)
            if is_wl:
                return True
        except Exception as e:
            logger.debug(f"Whitelist query exception ignored during exemption check: {e}")

        return False

    # ==========================================
    # MODERATION OPERATION PRIMITIVES
    # ==========================================

    async def delete_message_safe(
        self,
        message: discord.Message,
        incident_id: Optional[str] = None,
    ) -> Result[DeleteMessageData]:
        """
        Safely attempts message deletion with typed result reporting.
        Distinguishes SUCCESS, PERMISSION_DENIED, MESSAGE_NOT_FOUND, RATE_LIMITED, DISCORD_ERROR.
        """
        try:
            await message.delete()
            return Result.ok(
                data=DeleteMessageData(message_id=message.id, channel_id=message.channel.id, deleted=True),
                incident_id=incident_id,
            )
        except discord.NotFound:
            return Result.not_found(
                message="Target message was already deleted or not found.",
                code=ErrorCodes.MESSAGE_NOT_FOUND,
                incident_id=incident_id,
                data=DeleteMessageData(message_id=message.id, channel_id=message.channel.id, deleted=False),
            )
        except discord.Forbidden:
            logger.warning(f"Missing Manage Messages permission in #{getattr(message.channel, 'name', message.channel.id)}")
            return Result.permission_denied(
                code=ErrorCodes.MISSING_MANAGE_MESSAGES,
                message="RAI lacks Manage Messages permission.",
                incident_id=incident_id,
                data=DeleteMessageData(message_id=message.id, channel_id=message.channel.id, deleted=False),
            )
        except discord.HTTPException as e:
            if getattr(e, "status", None) == 429:
                return Result.rate_limited(
                    message=f"Discord rate limit reached deleting message: {e}",
                    code=ErrorCodes.DISCORD_RATE_LIMIT,
                    incident_id=incident_id,
                    data=DeleteMessageData(message_id=message.id, channel_id=message.channel.id, deleted=False),
                )
            return Result.discord_error(
                message=f"Discord API error deleting message: {e}",
                code=ErrorCodes.DISCORD_API_ERROR,
                incident_id=incident_id,
                data=DeleteMessageData(message_id=message.id, channel_id=message.channel.id, deleted=False),
            )
        except Exception as e:
            logger.error(f"Unexpected error deleting message: {e}", exc_info=True)
            return Result.internal_error(
                message=f"Unexpected error deleting message: {e}",
                incident_id=incident_id,
                data=DeleteMessageData(message_id=message.id, channel_id=message.channel.id, deleted=False),
            )

    async def apply_restriction_safe(
        self,
        author: discord.Member,
        duration_seconds: int,
        severity: str,
        incident_id: Optional[str] = None,
    ) -> Result[ModerationData]:
        """
        Safely applies communication restriction (timeout) with role hierarchy inspection.
        Distinguishes SUCCESS, PERMISSION_DENIED, ROLE_HIERARCHY_BLOCKED, INVALID_DURATION, MEMBER_NOT_FOUND.
        """
        if not author:
            return Result.not_found(
                message="Target member not found.",
                code=ErrorCodes.MEMBER_NOT_FOUND,
                incident_id=incident_id,
            )

        if duration_seconds <= 0:
            return Result.fail(
                status=ResultStatus.INVALID,
                code=ErrorCodes.INVALID_DURATION,
                message="Timeout duration must be a positive integer.",
                incident_id=incident_id,
                data=ModerationData(target_id=author.id, action="timeout", duration_seconds=duration_seconds),
            )

        guild = author.guild
        bot_member = guild.me

        # 1. Role hierarchy check
        try:
            author_pos = getattr(getattr(author, "top_role", None), "position", 0)
            bot_pos = getattr(getattr(bot_member, "top_role", None), "position", 0)
            if not isinstance(author_pos, (int, float)):
                author_pos = 0
            if not isinstance(bot_pos, (int, float)):
                bot_pos = 0

            if (author_pos >= bot_pos and author.id != bot_member.id) or author.id == guild.owner_id:
                return Result.role_hierarchy_blocked(
                    message="Target role is higher than or equal to bot's highest role, or target is server owner.",
                    code=ErrorCodes.ROLE_HIERARCHY_BLOCKED,
                    incident_id=incident_id,
                    data=ModerationData(target_id=author.id, action="timeout", duration_seconds=duration_seconds),
                )
        except Exception as e:
            logger.debug(f"Role hierarchy inspection error note: {e}")

        # 2. Execute timeout
        try:
            until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
            await author.timeout(until, reason=f"『RΛI』 Mass User Mention Spam ({severity})")
            return Result.ok(
                data=ModerationData(
                    target_id=author.id,
                    action="timeout",
                    duration_seconds=duration_seconds,
                    reason=f"Mass User Mention Spam ({severity})",
                ),
                incident_id=incident_id,
            )
        except discord.Forbidden:
            return Result.permission_denied(
                code=ErrorCodes.MISSING_MODERATE_MEMBERS,
                message="RAI lacks Moderate Members permission to apply timeout.",
                incident_id=incident_id,
                data=ModerationData(target_id=author.id, action="timeout", duration_seconds=duration_seconds),
            )
        except discord.NotFound:
            return Result.not_found(
                message="Member not found in guild when applying timeout.",
                code=ErrorCodes.MEMBER_NOT_FOUND,
                incident_id=incident_id,
                data=ModerationData(target_id=author.id, action="timeout", duration_seconds=duration_seconds),
            )
        except discord.HTTPException as e:
            if getattr(e, "status", None) == 429:
                return Result.rate_limited(
                    message=f"Discord rate limit reached applying timeout: {e}",
                    code=ErrorCodes.DISCORD_RATE_LIMIT,
                    incident_id=incident_id,
                    data=ModerationData(target_id=author.id, action="timeout", duration_seconds=duration_seconds),
                )
            return Result.discord_error(
                message=f"Discord API error applying timeout: {e}",
                code=ErrorCodes.DISCORD_API_ERROR,
                incident_id=incident_id,
                data=ModerationData(target_id=author.id, action="timeout", duration_seconds=duration_seconds),
            )
        except Exception as e:
            logger.error(f"Unexpected error applying timeout: {e}", exc_info=True)
            return Result.internal_error(
                message=f"Unexpected error applying timeout: {e}",
                incident_id=incident_id,
                data=ModerationData(target_id=author.id, action="timeout", duration_seconds=duration_seconds),
            )

    async def cleanup_channel_messages_safe(
        self,
        guild: discord.Guild,
        author_id: int,
        channels: List[int],
        purge_window_seconds: int,
        incident_id: Optional[str] = None,
    ) -> Result[OperationSummary]:
        """
        Safely purges offending attacker messages across affected channels within the purge window.
        Returns aggregate OperationSummary indicating succeeded, failed, and permission_denied counts.
        """
        purge_cutoff = time.time() - purge_window_seconds
        total_attempted = len(channels)
        total_deleted = 0
        failed = 0
        permission_denied = 0

        for ch_id in channels:
            channel = guild.get_channel(ch_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                failed += 1
                continue

            try:
                def is_attacker_spam(m: discord.Message) -> bool:
                    return m.author.id == author_id and m.created_at.timestamp() >= purge_cutoff

                deleted = await channel.purge(limit=50, check=is_attacker_spam)
                total_deleted += len(deleted)
            except discord.Forbidden:
                permission_denied += 1
            except Exception as e:
                logger.debug(f"Channel purge error in #{channel.name}: {e}")
                failed += 1

        summary = OperationSummary(
            attempted=total_attempted,
            succeeded=total_deleted,
            failed=failed,
            skipped=0,
            permission_denied=permission_denied,
        )

        if permission_denied == total_attempted and total_attempted > 0:
            return Result.permission_denied(
                code=ErrorCodes.MISSING_MANAGE_MESSAGES,
                message="Purge failed: lacking Manage Messages permission across affected channels.",
                incident_id=incident_id,
                data=summary,
            )
        elif summary.is_partial or failed > 0 or permission_denied > 0:
            return Result.partial(
                code="PARTIAL_PURGE",
                message=f"Purged {total_deleted} messages across channels with {failed} failures and {permission_denied} permission blocks.",
                incident_id=incident_id,
                data=summary,
            )
        else:
            return Result.ok(data=summary, incident_id=incident_id)

    async def save_incident_safe(
        self,
        guild_id: int,
        author: discord.Member,
        incident_id: str,
        severity: str,
        stats: Dict[str, Any],
        first_channel_id: int,
        action_summary: str,
    ) -> Result[DatabaseResultData]:
        """
        Saves incident details to SQLite database.
        If database fails, returns DATABASE_ERROR while preserving in-memory security isolation.
        """
        first_seen_iso = datetime.datetime.fromtimestamp(stats["first_seen"], datetime.timezone.utc).isoformat()
        last_seen_iso = datetime.datetime.fromtimestamp(stats["last_seen"], datetime.timezone.utc).isoformat()
        user_name = f"{author.name}#{author.discriminator}" if author.discriminator != "0" else author.name

        try:
            await self.bot.db.create_mention_spam_incident(
                incident_id=incident_id,
                guild_id=guild_id,
                user_id=author.id,
                user_name=user_name,
                first_channel_id=first_channel_id,
                channels_affected=stats["channels_affected"],
                messages_count=stats["message_count"],
                mentions_count=stats["total_mentions"],
                unique_targets_count=stats["unique_targets"],
                first_seen=first_seen_iso,
                last_seen=last_seen_iso,
                severity=severity,
                action_taken=action_summary,
                incident_status="RESOLVED",
            )
            return Result.ok(
                data=DatabaseResultData(
                    operation="create_mention_spam_incident",
                    incident_id=incident_id,
                    affected_rows=1,
                    success=True,
                    table="mention_spam_incidents",
                ),
                incident_id=incident_id,
            )
        except Exception as e:
            logger.error(f"Failed to record mention spam incident in DB: {e}")
            return Result.database_error(
                message=f"SQLite database error recording incident: {e}",
                code=ErrorCodes.DATABASE_ERROR,
                retryable=True,
                incident_id=incident_id,
                data=DatabaseResultData(
                    operation="create_mention_spam_incident",
                    incident_id=incident_id,
                    affected_rows=0,
                    success=False,
                    table="mention_spam_incidents",
                ),
            )

    # ==========================================
    # DETECTION & PIPELINE COORDINATOR
    # ==========================================

    async def detect_threat(
        self,
        message: discord.Message,
        cfg: Optional[MentionSpamConfig] = None,
    ) -> Result[DetectionResult]:
        """
        Evaluates message against mention thresholds and sliding window statistics.
        Returns explicit DetectionResult with status: NO_THREAT, SUSPICIOUS, HIGH_RISK, CRITICAL, IGNORED, INVALID, or ERROR.
        """
        if not message or not message.guild or not isinstance(message.author, discord.Member):
            return Result.fail(
                status=ResultStatus.INVALID,
                code=ErrorCodes.INVALID,
                message="Message does not originate from a valid guild member.",
                data=DetectionResult(
                    status=DetectionStatus.INVALID,
                    mention_count=0,
                    message_count=0,
                    channels_affected=0,
                    reason="Invalid guild or author",
                ),
            )

        if message.author.bot:
            return Result.skipped(
                reason="Author is a bot account.",
                code=ErrorCodes.IGNORED,
                data=DetectionResult(
                    status=DetectionStatus.IGNORED,
                    mention_count=0,
                    message_count=0,
                    channels_affected=0,
                    reason="Bot account",
                ),
            )

        guild = message.guild
        author = message.author

        # Extract mentions
        targets = self.extract_mentions(message)
        mention_count = len(targets)

        # Fast exit for zero mentions if user has no recent activity
        tracker_key = (guild.id, author.id)
        tracker = self._user_trackers.get(tracker_key)
        if mention_count == 0 and not tracker:
            return Result.ok(
                data=DetectionResult(
                    status=DetectionStatus.NO_THREAT,
                    mention_count=0,
                    message_count=0,
                    channels_affected=0,
                    reason="Zero mentions present",
                    targets=targets,
                )
            )

        # Load guild config if not provided
        if cfg is None:
            try:
                cfg = await self.bot.db.get_or_create_mention_spam_config(guild.id)
            except Exception as e:
                logger.warning(f"Failed to load mention spam config for guild {guild.id}: {e}")
                cfg = MentionSpamConfig(guild_id=guild.id)

        if not cfg.enabled:
            return Result.skipped(
                reason="Mention spam protection is disabled for this guild.",
                code=ErrorCodes.IGNORED,
                data=DetectionResult(
                    status=DetectionStatus.IGNORED,
                    mention_count=mention_count,
                    message_count=0,
                    channels_affected=0,
                    reason="Disabled in configuration",
                ),
            )

        # Exemption check
        if await self.is_exempt(author, cfg):
            return Result.skipped(
                reason="Member is exempt from mention spam enforcement.",
                code=ErrorCodes.EXEMPT,
                data=DetectionResult(
                    status=DetectionStatus.IGNORED,
                    mention_count=mention_count,
                    message_count=0,
                    channels_affected=0,
                    reason="Exempt staff or founder",
                ),
            )

        now = time.time()
        content_hash = self.compute_mention_hash(message.content)

        # Update tracker
        if not tracker:
            tracker = UserMentionTracker()
            self._user_trackers[tracker_key] = tracker

        tracker.record_event(
            channel_id=message.channel.id,
            mention_count=mention_count,
            targets=targets,
            content_hash=content_hash,
            message_id=message.id,
        )
        self._cleanup_expired_trackers()

        # Update guild correlation for multi-user coordination
        if mention_count >= cfg.warning_threshold:
            self._guild_correlation[guild.id].append((now, author.id, message.channel.id))

        stats = tracker.get_window_stats(cfg.window_seconds, current_hash=content_hash)
        total_mentions = stats["total_mentions"]
        channels_count = len(stats["channels_affected"])
        repeat_count = stats["repeat_count"]

        # 1. CRITICAL THRESHOLD:
        if (
            mention_count >= cfg.critical_threshold
            or total_mentions >= int(cfg.critical_threshold * 1.5)
            or (channels_count >= cfg.cross_channel_threshold and total_mentions >= cfg.high_threshold)
        ):
            return Result.ok(
                data=DetectionResult(
                    status=DetectionStatus.CRITICAL,
                    mention_count=total_mentions,
                    message_count=stats["message_count"],
                    channels_affected=channels_count,
                    reason="Critical mention burst or cross-channel flood",
                    targets=targets,
                    stats=stats,
                )
            )

        # 2. HIGH THRESHOLD:
        elif (
            mention_count >= cfg.high_threshold
            or total_mentions >= cfg.high_threshold
            or repeat_count >= cfg.repeat_message_threshold
        ):
            return Result.ok(
                data=DetectionResult(
                    status=DetectionStatus.HIGH_RISK,
                    mention_count=total_mentions,
                    message_count=stats["message_count"],
                    channels_affected=channels_count,
                    reason="High mention threshold or repeated spam text",
                    targets=targets,
                    stats=stats,
                )
            )

        # 3. SUSPICIOUS / WARNING THRESHOLD:
        elif mention_count >= cfg.warning_threshold:
            return Result.ok(
                data=DetectionResult(
                    status=DetectionStatus.SUSPICIOUS,
                    mention_count=total_mentions,
                    message_count=stats["message_count"],
                    channels_affected=channels_count,
                    reason="Warning mention threshold exceeded",
                    targets=targets,
                    stats=stats,
                )
            )

        # Normal message
        return Result.ok(
            data=DetectionResult(
                status=DetectionStatus.NO_THREAT,
                mention_count=total_mentions,
                message_count=stats["message_count"],
                channels_affected=channels_count,
                reason="Mention counts within safe thresholds",
                targets=targets,
                stats=stats,
            )
        )

    async def inspect_message(self, message: discord.Message) -> Result[MentionSpamResult]:
        """
        Inspects message for mass user mentions across channels.
        Returns a structured Result[MentionSpamResult] with complete operational diagnostics.
        Never swallows exceptions or terminates the calling worker.
        """
        try:
            if not message or not message.guild or not isinstance(message.author, discord.Member):
                return Result.fail(
                    status=ResultStatus.INVALID,
                    code=ErrorCodes.INVALID,
                    message="Message does not originate from a valid guild member.",
                    data=MentionSpamResult(
                        detected=False,
                        severity="INVALID",
                        mentions=0,
                        messages=0,
                        channels=0,
                        action_status=ResultStatus.INVALID,
                        cleanup_status=ResultStatus.SKIPPED,
                        incident_id=None,
                        detection=DetectionResult(
                            status=DetectionStatus.INVALID,
                            mention_count=0,
                            message_count=0,
                            channels_affected=0,
                            reason="Invalid guild or author",
                        ),
                    ),
                )

            guild = message.guild
            author = message.author

            # Load config
            try:
                cfg = await self.bot.db.get_or_create_mention_spam_config(guild.id)
            except Exception as e:
                logger.warning(f"Failed to load mention spam config for guild {guild.id}: {e}")
                cfg = MentionSpamConfig(guild_id=guild.id)

            # Perform detection
            detection_res = await self.detect_threat(message, cfg)

            if not detection_res.success:
                # Detection returned a non-success state (SKIPPED or INVALID)
                det_data = detection_res.data or DetectionResult(
                    status=DetectionStatus.IGNORED,
                    mention_count=0,
                    message_count=0,
                    channels_affected=0,
                )
                return Result.skipped(
                    reason=detection_res.error.message if detection_res.error else "Inspection skipped",
                    code=detection_res.error.code if detection_res.error else ErrorCodes.IGNORED,
                    data=MentionSpamResult(
                        detected=False,
                        severity=det_data.status.value,
                        mentions=det_data.mention_count,
                        messages=det_data.message_count,
                        channels=det_data.channels_affected,
                        action_status=ResultStatus.SKIPPED,
                        cleanup_status=ResultStatus.SKIPPED,
                        incident_id=None,
                        detection=det_data,
                    ),
                )

            det_data = detection_res.data
            if det_data.status == DetectionStatus.NO_THREAT:
                return Result.ok(
                    data=MentionSpamResult(
                        detected=False,
                        severity="NO_THREAT",
                        mentions=det_data.mention_count,
                        messages=det_data.message_count,
                        channels=det_data.channels_affected,
                        action_status=ResultStatus.SKIPPED,
                        cleanup_status=ResultStatus.SKIPPED,
                        incident_id=None,
                        detection=det_data,
                    )
                )

            # Threat detected: Map detection severity to configuration actions
            severity_str: str = "LOW"
            action_type = cfg.action_low

            if det_data.status == DetectionStatus.CRITICAL:
                severity_str = "CRITICAL"
                action_type = cfg.action_critical
            elif det_data.status == DetectionStatus.HIGH_RISK:
                severity_str = "HIGH"
                action_type = cfg.action_high

            # Execute Mitigation Pipeline
            return await self._mitigate_attack(
                message=message,
                author=author,
                guild=guild,
                cfg=cfg,
                severity=severity_str,
                action_type=action_type,
                stats=det_data.stats,
                det_result=det_data,
            )

        except Exception as e:
            logger.error(f"Internal error in mention spam inspector: {e}", exc_info=True)
            return Result.internal_error(
                message=f"Internal inspection error: {e}",
                code=ErrorCodes.INTERNAL_ERROR,
                data=MentionSpamResult(
                    detected=False,
                    severity="ERROR",
                    mentions=0,
                    messages=0,
                    channels=0,
                    action_status=ResultStatus.INTERNAL_ERROR,
                    cleanup_status=ResultStatus.SKIPPED,
                    incident_id=None,
                    detection=DetectionResult(
                        status=DetectionStatus.ERROR,
                        mention_count=0,
                        message_count=0,
                        channels_affected=0,
                        reason=str(e),
                    ),
                ),
            )

    async def _mitigate_attack(
        self,
        message: discord.Message,
        author: discord.Member,
        guild: discord.Guild,
        cfg: MentionSpamConfig,
        severity: str,
        action_type: str,
        stats: Dict[str, Any],
        det_result: DetectionResult,
    ) -> Result[MentionSpamResult]:
        """
        Executes multi-step containment, message cleanup, timeout, and incident logging.
        Evaluates partial success and returns comprehensive Result[MentionSpamResult].
        """
        incident_id = f"MS-{int(time.time()) % 100000:05d}"
        action_items: List[str] = []

        # Non-blocking publish to SecuritySignalBus
        try:
            from security.signals import SecuritySignal, SecuritySignalBus, SignalEventType, SignalSeverity, SignalSource
            bus = SecuritySignalBus.get_instance()
            sig_sev = SignalSeverity.CRITICAL.value if severity == "CRITICAL" else (
                SignalSeverity.HIGH.value if severity == "HIGH" else SignalSeverity.MEDIUM.value
            )
            evt_type = SignalEventType.MASS_MENTION.value if stats.get("total_mentions", 0) >= 10 else SignalEventType.REPEATED_MENTION_SPAM.value
            bus.publish(
                SecuritySignal(
                    guild_id=guild.id,
                    event_type=evt_type,
                    source=SignalSource.MENTION_SPAM.value,
                    severity=sig_sev,
                    confidence=0.95,
                    actor_id=author.id,
                    actor_name=str(author),
                    channel_id=message.channel.id,
                    channel_name=getattr(message.channel, "name", None),
                    evidence={
                        "total_mentions": stats.get("total_mentions", 0),
                        "channels_affected": len(stats.get("channels_affected", [])),
                        "message_count": stats.get("message_count", 0),
                        "repeat_count": stats.get("repeat_count", 0),
                    },
                    incident_id=incident_id,
                )
            )
        except Exception as bus_err:
            logger.debug(f"Failed to publish signal to SecuritySignalBus: {bus_err}")

        # 1. Delete triggering message
        delete_res = await self.delete_message_safe(message, incident_id=incident_id)
        if delete_res.success:
            action_items.append("Message deleted")
        else:
            action_items.append(f"Delete failed ({delete_res.status.value})")

        # 2. Communication Restriction / Timeout
        restrict_res: Optional[Result[ModerationData]] = None
        timeout_duration = 0
        if severity == "CRITICAL" or action_type in ("timeout", "timeout_and_purge"):
            timeout_duration = (
                cfg.timeout_duration_critical if severity == "CRITICAL" else cfg.timeout_duration_high
            )

        if timeout_duration > 0:
            restrict_res = await self.apply_restriction_safe(
                author=author,
                duration_seconds=timeout_duration,
                severity=severity,
                incident_id=incident_id,
            )
            if restrict_res.success:
                hours = timeout_duration // 3600
                action_items.append(f"Restricted ({hours}h)" if hours else f"Restricted ({timeout_duration // 60}m)")
            else:
                action_items.append(f"Restriction skipped/failed ({restrict_res.status.value})")

        # 3. Targeted Cross-Channel Cleanup
        cleanup_res: Optional[Result[OperationSummary]] = None
        if severity == "CRITICAL" and "purge" in action_type:
            cleanup_res = await self.cleanup_channel_messages_safe(
                guild=guild,
                author_id=author.id,
                channels=stats["channels_affected"],
                purge_window_seconds=cfg.purge_window_seconds,
                incident_id=incident_id,
            )
            if cleanup_res.data and cleanup_res.data.succeeded > 0:
                action_items.append(f"Purged {cleanup_res.data.succeeded} messages")

        # 4. Check Coordinated Multi-User Correlation
        is_coordinated = False
        recent_guild_bursts = [
            b for b in self._guild_correlation[guild.id] if time.time() - b[0] <= 30.0
        ]
        distinct_attackers = set(b[1] for b in recent_guild_bursts)
        if len(distinct_attackers) >= 3:
            is_coordinated = True
            action_items.append(f"Coordinated raid alert ({len(distinct_attackers)} attackers)")

        full_action_summary = ", ".join(action_items) or "Flagged & logged"

        # 5. Persist Incident to Database (SQLite)
        db_res = await self.save_incident_safe(
            guild_id=guild.id,
            author=author,
            incident_id=incident_id,
            severity=severity,
            stats=stats,
            first_channel_id=message.channel.id,
            action_summary=full_action_summary,
        )

        # 6. Evaluate Overall Action Status (Supporting PARTIAL outcomes)
        action_status: ResultStatus = ResultStatus.SUCCESS
        if restrict_res is not None:
            # Both delete and restrict were attempted
            if delete_res.success and restrict_res.success:
                action_status = ResultStatus.SUCCESS
            elif delete_res.success and not restrict_res.success:
                action_status = ResultStatus.PARTIAL
            elif not delete_res.success and restrict_res.success:
                action_status = ResultStatus.PARTIAL
            elif (
                delete_res.status == ResultStatus.PERMISSION_DENIED
                and restrict_res.status == ResultStatus.PERMISSION_DENIED
            ):
                action_status = ResultStatus.PERMISSION_DENIED
            elif restrict_res.status == ResultStatus.ROLE_HIERARCHY_BLOCKED:
                action_status = ResultStatus.PARTIAL if delete_res.success else ResultStatus.ROLE_HIERARCHY_BLOCKED
            else:
                action_status = ResultStatus.FAILED
        else:
            # Only delete was attempted
            action_status = delete_res.status

        cleanup_status = cleanup_res.status if cleanup_res is not None else ResultStatus.SKIPPED

        # 7. Dispatch Security Alert
        await self._dispatch_security_log(
            guild=guild,
            author=author,
            severity=severity,
            stats=stats,
            action_str=full_action_summary,
            incident_id=incident_id,
            is_coordinated=is_coordinated,
            action_status=action_status,
            delete_res=delete_res,
            restrict_res=restrict_res,
            db_res=db_res,
        )

        pipeline_data = MentionSpamResult(
            detected=True,
            severity=severity,
            mentions=stats["total_mentions"],
            messages=stats["message_count"],
            channels=len(stats["channels_affected"]),
            action_status=action_status,
            cleanup_status=cleanup_status,
            incident_id=incident_id,
            detection=det_result,
            delete_result=delete_res,
            restriction_result=restrict_res,
            cleanup_result=cleanup_res,
            db_result=db_res,
            is_coordinated=is_coordinated,
            action_summary=full_action_summary,
        )

        # Construct final typed Result
        if action_status == ResultStatus.SUCCESS:
            return Result.ok(data=pipeline_data, incident_id=incident_id)
        elif action_status == ResultStatus.PARTIAL:
            err = (
                restrict_res.error
                if (restrict_res and not restrict_res.success and restrict_res.error)
                else delete_res.error
            )
            return Result.partial(
                code=err.code if err else "PARTIAL_SUCCESS",
                message=err.message if err else "Some containment operations succeeded while others failed.",
                data=pipeline_data,
                incident_id=incident_id,
                retryable=err.retryable if err else False,
            )
        elif action_status == ResultStatus.PERMISSION_DENIED:
            return Result.permission_denied(
                code=delete_res.error.code if delete_res.error else ErrorCodes.MISSING_MANAGE_MESSAGES,
                message=delete_res.error.message if delete_res.error else "RAI lacked permissions to contain mention spam.",
                incident_id=incident_id,
                data=pipeline_data,
            )
        elif action_status == ResultStatus.ROLE_HIERARCHY_BLOCKED:
            return Result.role_hierarchy_blocked(
                message="Target role is higher than or equal to bot's highest role.",
                code=ErrorCodes.ROLE_HIERARCHY_BLOCKED,
                incident_id=incident_id,
                data=pipeline_data,
            )
        else:
            return Result.fail(
                status=action_status,
                code=delete_res.error.code if delete_res.error else ErrorCodes.INTERNAL_ERROR,
                message=delete_res.error.message if delete_res.error else "Mitigation operations failed.",
                incident_id=incident_id,
                data=pipeline_data,
                retryable=delete_res.error.retryable if delete_res.error else False,
            )

    async def _dispatch_security_log(
        self,
        guild: discord.Guild,
        author: discord.Member,
        severity: str,
        stats: Dict[str, Any],
        action_str: str,
        incident_id: str,
        is_coordinated: bool = False,
        action_status: ResultStatus = ResultStatus.SUCCESS,
        delete_res: Optional[Result[DeleteMessageData]] = None,
        restrict_res: Optional[Result[ModerationData]] = None,
        db_res: Optional[Result[DatabaseResultData]] = None,
    ) -> None:
        """Dispatches structured security alert embed reporting explicit operation states."""
        color = Colors.ERROR if severity == "CRITICAL" else Colors.SECURITY
        title = f"{DEFAULT_BRAND} • MENTION SPAM DETECTED"
        if is_coordinated:
            title = f"{DEFAULT_BRAND} • COORDINATED MENTION RAID DETECTED"

        embed = create_embed(
            title=title,
            color=color,
            description=f"Mass individual-user mention spam detected and processed.",
        )
        embed.add_field(
            name="👤 Attacker",
            value=f"{author.display_name} (`{author.id}`)",
            inline=True,
        )
        embed.add_field(name="⚡ Severity", value=f"`{severity}`", inline=True)
        embed.add_field(name="🆔 Incident ID", value=f"`#{incident_id}`", inline=True)

        embed.add_field(name="💬 Messages", value=str(stats.get("message_count", 1)), inline=True)
        embed.add_field(name="📁 Channels", value=str(len(stats.get("channels_affected", []))), inline=True)
        embed.add_field(name="👥 User Mentions", value=str(stats.get("total_mentions", 0)), inline=True)

        # Operational diagnostics field breakdown
        delete_status_str = delete_res.status.value.upper() if delete_res else "N/A"
        restrict_status_str = restrict_res.status.value.upper() if restrict_res else "SKIPPED"
        db_status_str = db_res.status.value.upper() if db_res else "SKIPPED"

        ops_summary = (
            f"• Delete Message: `{delete_status_str}`\n"
            f"• Apply Restriction: `{restrict_status_str}`\n"
            f"• Database Persistence: `{db_status_str}`\n"
            f"• Overall Status: **`{action_status.value.upper()}`**"
        )
        embed.add_field(name="📋 Operation Diagnostics", value=ops_summary, inline=False)
        embed.add_field(name="🛡️ Action Taken", value=action_str, inline=False)

        embed.set_footer(text=DEFAULT_FOOTER)

        # Route to Server Security Log Channel (No @everyone pings)
        try:
            log_cfg = await self.bot.db.get_logging_config(guild.id)
            ch_id = log_cfg.security_channel_id or log_cfg.moderation_channel_id
            if ch_id:
                channel = guild.get_channel(ch_id)
                if channel and isinstance(channel, discord.TextChannel):
                    await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except Exception as e:
            logger.debug(f"Could not dispatch mention alert to log channel: {e}")

        # Also notify Owner Confidential Report without mass mentions
        try:
            from utils.owner_reporter import OwnerReporter
            OwnerReporter.send_security_report(
                self.bot,
                guild.id,
                event="Mass User Mention Spam",
                reason=f"Mentions: {stats.get('total_mentions', 0)} across {len(stats.get('channels_affected', []))} channels",
                action_taken=action_str,
                severity=severity,
                details={
                    "Attacker": f"{author} ({author.id})",
                    "Incident": incident_id,
                    "Channels": f"{len(stats.get('channels_affected', []))} affected",
                    "Overall": action_status.value,
                },
            )
        except Exception as e:
            logger.debug(f"OwnerReporter notice note: {e}")
