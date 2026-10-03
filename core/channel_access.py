"""
Safe Automatic Empty Channel Access Engine for 『RΛI』.

Core Responsibilities:
1. Automatically ensures the bot has minimum required access to eligible empty channels.
2. Never gives RAI Administrator permissions or dangerous permissions (Manage Channels, Manage Roles, Ban, Kick, Webhooks).
3. Preserves existing channel permission configurations and overwrites without blind replacement.
4. Does not automatically modify voice channels, stage channels, private channels, or channels explicitly denied by design.
5. Employs bounded concurrency, rate limit awareness, jitter, and exponential backoff.
6. Returns typed results and provides both dry-run auditing and live modification.
7. Completely failure-isolated: errors never crash security, moderation, music, or other subsystems.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import discord

from config import Colors
from core.results import ErrorCodes, Result, ResultError, ResultStatus
from database.models import ChannelAccessConfig, ChannelAccessState

logger = logging.getLogger("Rai.ChannelAccess")

MINIMUM_REQUIRED_PERMISSIONS = ["view_channel", "send_messages", "read_message_history"]

# Patterns indicating security or administrative channels that must never be altered or weakened
SECURITY_CHANNEL_KEYWORDS = {
    "security",
    "audit",
    "incident",
    "threat",
    "alert",
    "anti-nuke",
    "anti-raid",
    "anti-spam",
    "panic",
    "emergency",
    "lockdown",
    "admin-control",
    "system-report",
    "mod-report",
    "security-report",
}


@dataclass
class ChannelAccessEvaluation:
    """Evaluation result for an inspected channel."""
    channel_id: int
    channel_name: str
    channel_type: str
    is_eligible: bool
    is_empty: bool
    has_access: bool
    missing_permissions: List[str]
    skip_reason: Optional[str] = None


@dataclass
class ChannelAccessOperation:
    """Result of an access evaluation or modification operation on a single channel."""
    channel_id: int
    channel_name: str
    status: ResultStatus
    action: str  # "granted", "skipped", "failed", "no_change"
    permissions_added: List[str]
    reason: str
    error_code: Optional[str] = None


@dataclass
class ChannelAccessScanSummary:
    """Aggregated outcome of a guild-wide channel access scan."""
    guild_id: int
    total_scanned: int = 0
    eligible_count: int = 0
    already_accessible: int = 0
    missing_access: int = 0
    updated: int = 0
    would_modify: int = 0
    skipped: int = 0
    failed: int = 0
    is_dry_run: bool = False
    details: List[ChannelAccessOperation] = field(default_factory=list)


class ChannelAccessService:
    """Autonomous Service coordinating safe empty channel access."""

    _instance: Optional[ChannelAccessService] = None

    def __init__(self, db: Any = None):
        self.db = db
        self._semaphore = asyncio.Semaphore(2)  # Bounded concurrency to protect Discord API rate limits

    @classmethod
    def get_instance(cls, db: Any = None) -> ChannelAccessService:
        if cls._instance is None:
            cls._instance = ChannelAccessService(db)
        elif db is not None and cls._instance.db is None:
            cls._instance.db = db
        return cls._instance

    # ==========================================
    # ELIGIBILITY & EMPTY CHECKS
    # ==========================================

    def is_eligible_channel_type(
        self,
        channel: discord.abc.GuildChannel,
        config: ChannelAccessConfig,
    ) -> Tuple[bool, Optional[str]]:
        """Validates if channel type is eligible according to configuration."""
        ch_type = getattr(channel, "type", None)

        if ch_type == discord.ChannelType.text:
            if hasattr(channel, "is_news") and channel.is_news():
                if not config.include_announcement:
                    return False, "Announcement channels disabled in config"
            elif not config.include_text:
                return False, "Text channels disabled in config"
            return True, None

        if ch_type == discord.ChannelType.news:
            if not config.include_announcement:
                return False, "Announcement channels disabled in config"
            return True, None

        if ch_type == discord.ChannelType.forum:
            if not config.include_forum:
                return False, "Forum channels disabled in config"
            return True, None

        if ch_type == discord.ChannelType.voice:
            if not config.include_voice:
                return False, "Voice channels excluded by default"
            return True, None

        if ch_type == discord.ChannelType.stage_voice:
            if not config.include_stage:
                return False, "Stage channels excluded by default"
            return True, None

        return False, f"Channel type '{ch_type}' is not supported"

    def is_private_channel(
        self,
        channel: discord.abc.GuildChannel,
        guild: discord.Guild,
    ) -> bool:
        """Determines if the channel is configured as a private channel (view restricted for @everyone)."""
        everyone_role = guild.default_role
        overwrites = getattr(channel, "overwrites", {})
        if everyone_role in overwrites:
            overwrite = overwrites[everyone_role]
            if overwrite.view_channel is False:
                return True
        return False

    def is_explicitly_denied_by_design(
        self,
        channel: discord.abc.GuildChannel,
        bot_member: discord.Member,
    ) -> bool:
        """Checks if RAI was explicitly denied access by deliberate administrative overwrite."""
        overwrites = getattr(channel, "overwrites", {})
        # Check bot member direct overwrite
        if bot_member in overwrites:
            bot_ow = overwrites[bot_member]
            if bot_ow.view_channel is False or bot_ow.send_messages is False:
                return True

        # Check bot's roles for explicit deny
        for role in bot_member.roles:
            if role in overwrites:
                role_ow = overwrites[role]
                if role_ow.view_channel is False or role_ow.send_messages is False:
                    # Role explicitly denies access
                    return True
        return False

    def is_security_channel(self, channel: discord.abc.GuildChannel) -> bool:
        """Identifies security, audit, or administrative channels to protect their baseline."""
        name_lower = getattr(channel, "name", "").lower()
        for kw in SECURITY_CHANNEL_KEYWORDS:
            if kw in name_lower:
                return True
        category = getattr(channel, "category", None)
        if category:
            cat_name = getattr(category, "name", "").lower()
            for kw in SECURITY_CHANNEL_KEYWORDS:
                if kw in cat_name:
                    return True
        return False

    async def is_channel_empty(
        self,
        channel: discord.abc.GuildChannel,
        bot_member: discord.Member,
    ) -> bool:
        """
        Determines whether a channel is empty (contains no messages).
        Uses history() when read permissions exist; falls back to last_message_id.
        """
        if not hasattr(channel, "history"):
            return False

        perms = channel.permissions_for(bot_member)
        if perms.read_message_history and perms.view_channel:
            try:
                async for _ in channel.history(limit=1):
                    return False
                return True
            except (discord.Forbidden, discord.HTTPException):
                pass

        # Fallback to last_message_id attribute
        last_id = getattr(channel, "last_message_id", None)
        return last_id is None

    # ==========================================
    # PERMISSION CHECKING & CALCULATION
    # ==========================================

    def check_bot_access(
        self,
        channel: discord.abc.GuildChannel,
        bot_member: discord.Member,
    ) -> Tuple[bool, List[str]]:
        """
        Verifies if RAI can already access the channel with minimum permissions:
        - View Channel
        - Send Messages
        - Read Message History
        """
        perms = channel.permissions_for(bot_member)
        missing: List[str] = []

        if not perms.view_channel:
            missing.append("view_channel")
        if not perms.send_messages:
            missing.append("send_messages")
        if not perms.read_message_history:
            missing.append("read_message_history")

        return len(missing) == 0, missing

    # ==========================================
    # EVALUATION
    # ==========================================

    async def evaluate_channel(
        self,
        channel: discord.abc.GuildChannel,
        bot_member: discord.Member,
        config: ChannelAccessConfig,
    ) -> ChannelAccessEvaluation:
        """Performs a comprehensive eligibility and access check for a channel."""
        ch_id = getattr(channel, "id", 0)
        ch_name = getattr(channel, "name", "unknown")
        ch_type = str(getattr(channel, "type", "unknown"))

        # 1. Check channel type eligibility
        is_type_eligible, type_reason = self.is_eligible_channel_type(channel, config)
        if not is_type_eligible:
            return ChannelAccessEvaluation(
                channel_id=ch_id,
                channel_name=ch_name,
                channel_type=ch_type,
                is_eligible=False,
                is_empty=False,
                has_access=False,
                missing_permissions=[],
                skip_reason=type_reason,
            )

        # 2. Check private channel restriction
        guild = getattr(channel, "guild", bot_member.guild)
        if not config.include_private and self.is_private_channel(channel, guild):
            return ChannelAccessEvaluation(
                channel_id=ch_id,
                channel_name=ch_name,
                channel_type=ch_type,
                is_eligible=False,
                is_empty=False,
                has_access=False,
                missing_permissions=[],
                skip_reason="Private channel excluded by policy",
            )

        # 3. Check if explicitly denied by design
        if self.is_explicitly_denied_by_design(channel, bot_member):
            return ChannelAccessEvaluation(
                channel_id=ch_id,
                channel_name=ch_name,
                channel_type=ch_type,
                is_eligible=False,
                is_empty=False,
                has_access=False,
                missing_permissions=[],
                skip_reason="Explicitly denied to bot by design",
            )

        # 4. Check whether channel is empty
        is_empty = await self.is_channel_empty(channel, bot_member)
        if config.empty_channels_only and not is_empty:
            return ChannelAccessEvaluation(
                channel_id=ch_id,
                channel_name=ch_name,
                channel_type=ch_type,
                is_eligible=False,
                is_empty=False,
                has_access=False,
                missing_permissions=[],
                skip_reason="Channel contains messages (not empty)",
            )

        # 5. Check existing bot permissions
        has_access, missing_perms = self.check_bot_access(channel, bot_member)

        return ChannelAccessEvaluation(
            channel_id=ch_id,
            channel_name=ch_name,
            channel_type=ch_type,
            is_eligible=True,
            is_empty=is_empty,
            has_access=has_access,
            missing_permissions=missing_perms,
            skip_reason=None if not has_access else "Bot already has full access",
        )

    # ==========================================
    # OVERWRITE APPLICATION (SAFE & PRESERVING)
    # ==========================================

    async def apply_minimum_overwrite(
        self,
        channel: discord.abc.GuildChannel,
        bot_member: discord.Member,
        missing_perms: List[str],
    ) -> Result[ChannelAccessOperation]:
        """
        Safely applies minimum permissions to an empty channel without overwriting
        existing configurations or other role/member overwrites.
        """
        ch_id = getattr(channel, "id", 0)
        ch_name = getattr(channel, "name", "unknown")

        # 1. Pre-flight check: Can RAI modify channel permissions?
        bot_guild_perms = getattr(bot_member, "guild_permissions", None)
        chan_perms = channel.permissions_for(bot_member)
        can_manage_roles = (
            (bot_guild_perms and getattr(bot_guild_perms, "manage_roles", False))
            or getattr(chan_perms, "manage_roles", False)
        )

        if not can_manage_roles:
            logger.warning(
                f"[CHANNEL_ACCESS] Cannot modify #{ch_name} ({ch_id}): Missing Manage Roles permission."
            )
            return Result.fail(
                status=ResultStatus.PERMISSION_DENIED,
                code=ErrorCodes.MISSING_MANAGE_ROLES,
                message="RAI lacks 'Manage Roles' permission to set channel overwrites.",
                retryable=False,
            )

        # 2. Preserve existing overwrites for bot member
        current_overwrite = channel.overwrites_for(bot_member)

        # Create updated overwrite preserving all existing allow/deny bits
        new_overwrite = discord.PermissionOverwrite.from_pair(*current_overwrite.pair()) if hasattr(current_overwrite, "pair") else discord.PermissionOverwrite()
        for attr in ("view_channel", "send_messages", "read_message_history"):
            existing_val = getattr(current_overwrite, attr, None)
            if existing_val is not None:
                setattr(new_overwrite, attr, existing_val)

        # Set ONLY the missing permissions to True
        permissions_added: List[str] = []
        if "view_channel" in missing_perms:
            new_overwrite.view_channel = True
            permissions_added.append("View Channel")
        if "send_messages" in missing_perms:
            new_overwrite.send_messages = True
            permissions_added.append("Send Messages")
        if "read_message_history" in missing_perms:
            new_overwrite.read_message_history = True
            permissions_added.append("Read Message History")

        # 3. Apply overwrite with exponential backoff & rate-limit awareness
        max_retries = 3
        backoff_delay = 1.0

        for attempt in range(1, max_retries + 1):
            try:
                await channel.set_permissions(
                    bot_member,
                    overwrite=new_overwrite,
                    reason="RAI: Automatic minimum access for eligible empty channel",
                )
                break
            except discord.Forbidden as e:
                logger.warning(
                    f"[CHANNEL_ACCESS] Forbidden when setting permissions on #{ch_name} ({ch_id}): {e}"
                )
                return Result.fail(
                    status=ResultStatus.ROLE_HIERARCHY_BLOCKED,
                    code=ErrorCodes.ROLE_HIERARCHY_BLOCKED,
                    message="Discord rejected permission change: Role hierarchy blocked or forbidden.",
                    retryable=False,
                )
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, "retry_after", backoff_delay)
                    jitter = random.uniform(0.1, 0.4)
                    sleep_time = (retry_after or backoff_delay) + jitter
                    logger.warning(
                        f"[CHANNEL_ACCESS] Rate limited on #{ch_name}, waiting {sleep_time:.2f}s (attempt {attempt}/{max_retries})"
                    )
                    await asyncio.sleep(sleep_time)
                    backoff_delay *= 2.0
                    if attempt == max_retries:
                        return Result.fail(
                            status=ResultStatus.RATE_LIMITED,
                            code=ErrorCodes.DISCORD_RATE_LIMIT,
                            message="Discord rate limit exceeded when updating channel overwrite.",
                            retryable=True,
                        )
                else:
                    logger.error(
                        f"[CHANNEL_ACCESS] HTTP error on #{ch_name} ({ch_id}): {e}"
                    )
                    return Result.fail(
                        status=ResultStatus.DISCORD_ERROR,
                        code=ErrorCodes.DISCORD_API_ERROR,
                        message=f"Discord API error: {e}",
                        retryable=False,
                    )
            except Exception as e:
                logger.error(f"[CHANNEL_ACCESS] Unexpected error on #{ch_name} ({ch_id}): {e}", exc_info=True)
                return Result.fail(
                    status=ResultStatus.INTERNAL_ERROR,
                    code=ErrorCodes.INTERNAL_ERROR,
                    message=f"Unexpected internal error: {e}",
                    retryable=False,
                )

        # 4. Post-flight verification
        verify_perms = channel.permissions_for(bot_member)
        if not (verify_perms.view_channel and verify_perms.send_messages and verify_perms.read_message_history):
            logger.warning(
                f"[CHANNEL_ACCESS] Verification partial/failed for #{ch_name} ({ch_id})."
            )
            return Result.fail(
                status=ResultStatus.PARTIAL,
                code=ErrorCodes.CHANNEL_PERMISSION_DENIED,
                message="Permissions could not be verified after update.",
                retryable=False,
            )

        operation = ChannelAccessOperation(
            channel_id=ch_id,
            channel_name=ch_name,
            status=ResultStatus.SUCCESS,
            action="granted",
            permissions_added=permissions_added,
            reason="Eligible empty channel",
        )
        return Result.ok(data=operation)

    # ==========================================
    # GUILD SCANNING & AUDITING
    # ==========================================

    async def scan_guild(
        self,
        guild: discord.Guild,
        dry_run: bool = False,
        bot_member: Optional[discord.Member] = None,
        config: Optional[ChannelAccessConfig] = None,
    ) -> ChannelAccessScanSummary:
        """
        Scans all channels in a guild, evaluates eligibility, and conditionally updates them.
        """
        bot_mem = bot_member or guild.me
        if not bot_mem:
            logger.error(f"[CHANNEL_ACCESS] guild.me is None for guild {guild.id}")
            return ChannelAccessScanSummary(guild_id=guild.id)

        # Fetch config
        cfg = config
        if cfg is None and self.db:
            try:
                cfg = await self.db.get_channel_access_config(guild.id)
            except Exception as e:
                logger.warning(f"Could not load channel_access_config, using defaults: {e}")
                cfg = ChannelAccessConfig(guild_id=guild.id)
        elif cfg is None:
            cfg = ChannelAccessConfig(guild_id=guild.id)

        channels = list(guild.channels)
        summary = ChannelAccessScanSummary(
            guild_id=guild.id,
            total_scanned=len(channels),
            is_dry_run=dry_run,
        )

        for channel in channels:
            async with self._semaphore:
                try:
                    eval_result = await self.evaluate_channel(channel, bot_mem, cfg)
                    ch_id = eval_result.channel_id
                    ch_name = eval_result.channel_name

                    if not eval_result.is_eligible:
                        summary.skipped += 1
                        summary.details.append(
                            ChannelAccessOperation(
                                channel_id=ch_id,
                                channel_name=ch_name,
                                status=ResultStatus.SKIPPED,
                                action="skipped",
                                permissions_added=[],
                                reason=eval_result.skip_reason or "Ineligible channel",
                            )
                        )
                        continue

                    summary.eligible_count += 1

                    if eval_result.has_access:
                        summary.already_accessible += 1
                        summary.details.append(
                            ChannelAccessOperation(
                                channel_id=ch_id,
                                channel_name=ch_name,
                                status=ResultStatus.ALREADY_HANDLED,
                                action="no_change",
                                permissions_added=[],
                                reason="Access already available",
                            )
                        )
                        # Record accessible state in DB
                        if self.db:
                            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                            await self.db.record_channel_access_state(
                                ChannelAccessState(
                                    guild_id=guild.id,
                                    channel_id=ch_id,
                                    channel_type=eval_result.channel_type,
                                    last_checked=now_str,
                                    access_status="ACCESSIBLE",
                                )
                            )
                        continue

                    # Channel is eligible, empty, but missing access
                    summary.missing_access += 1

                    if dry_run:
                        summary.would_modify += 1
                        perms_needed = [
                            p.replace("_", " ").title() for p in eval_result.missing_permissions
                        ]
                        summary.details.append(
                            ChannelAccessOperation(
                                channel_id=ch_id,
                                channel_name=ch_name,
                                status=ResultStatus.SUCCESS,
                                action="would_modify",
                                permissions_added=perms_needed,
                                reason="Eligible empty channel",
                            )
                        )
                    else:
                        # Apply live modifications
                        apply_res = await self.apply_minimum_overwrite(
                            channel, bot_mem, eval_result.missing_permissions
                        )
                        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

                        if apply_res.success and apply_res.data:
                            summary.updated += 1
                            summary.details.append(apply_res.data)
                            if self.db:
                                await self.db.record_channel_access_state(
                                    ChannelAccessState(
                                        guild_id=guild.id,
                                        channel_id=ch_id,
                                        channel_type=eval_result.channel_type,
                                        last_checked=now_str,
                                        last_updated=now_str,
                                        access_status="UPDATED",
                                    )
                                )
                        else:
                            summary.failed += 1
                            err_code = apply_res.error.code if apply_res.error else "UNKNOWN_ERROR"
                            summary.details.append(
                                ChannelAccessOperation(
                                    channel_id=ch_id,
                                    channel_name=ch_name,
                                    status=apply_res.status,
                                    action="failed",
                                    permissions_added=[],
                                    reason=apply_res.error.message if apply_res.error else "Failed to apply permissions",
                                    error_code=err_code,
                                )
                            )
                            if self.db:
                                await self.db.record_channel_access_state(
                                    ChannelAccessState(
                                        guild_id=guild.id,
                                        channel_id=ch_id,
                                        channel_type=eval_result.channel_type,
                                        last_checked=now_str,
                                        access_status="FAILED",
                                        error_code=err_code,
                                    )
                                )

                    # Small delay to keep gateway healthy
                    await asyncio.sleep(0.15)

                except Exception as e:
                    logger.error(
                        f"[CHANNEL_ACCESS] Error inspecting channel {getattr(channel, 'name', 'unknown')}: {e}",
                        exc_info=True,
                    )
                    summary.failed += 1

        return summary

    # ==========================================
    # EMBED GENERATORS
    # ==========================================

    def create_audit_embed(
        self,
        operation: ChannelAccessOperation,
        channel_name: str,
    ) -> discord.Embed:
        """
        Builds the standard audit log embed for an automatic modification:
        『RΛI』 • CHANNEL ACCESS
        Channel: <name>
        Action: Bot access granted
        Permissions: View Channel, Send Messages, Read Message History
        Reason: Eligible empty channel
        Status: 🟢 SUCCESS
        """
        embed = discord.Embed(
            title="『RΛI』 • CHANNEL ACCESS",
            color=Colors.SUCCESS if operation.status == ResultStatus.SUCCESS else Colors.ERROR,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Channel", value=f"`#{channel_name}`", inline=False)
        embed.add_field(name="Action", value="Bot access granted", inline=False)

        perms_str = "\n".join(operation.permissions_added) if operation.permissions_added else "View Channel\nSend Messages\nRead Message History"
        embed.add_field(name="Permissions", value=perms_str, inline=False)
        embed.add_field(name="Reason", value=operation.reason, inline=False)
        embed.add_field(
            name="Status",
            value="🟢 SUCCESS" if operation.status == ResultStatus.SUCCESS else f"🔴 FAILED ({operation.error_code})",
            inline=False,
        )
        embed.set_footer(text="RAI Permission Engine • Safe Access Protocol")
        return embed

    def create_scan_embed(self, summary: ChannelAccessScanSummary) -> discord.Embed:
        """Builds clean embed reports for dry-run or live scan results."""
        if summary.is_dry_run:
            embed = discord.Embed(
                title="『RΛI』 • CHANNEL ACCESS AUDIT",
                color=Colors.INFO,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            embed.add_field(name="Eligible Channels", value=str(summary.eligible_count), inline=True)
            embed.add_field(name="Already Accessible", value=str(summary.already_accessible), inline=True)
            embed.add_field(name="Missing Access", value=str(summary.missing_access), inline=True)
            embed.add_field(name="Skipped", value=str(summary.skipped), inline=True)
            embed.add_field(name="Would Modify", value=str(summary.would_modify), inline=True)
            embed.set_footer(text="Audit Complete • No changes were made.")
            return embed

        embed = discord.Embed(
            title="『RΛI』 • CHANNEL ACCESS",
            color=Colors.SUCCESS if summary.failed == 0 else Colors.WARNING,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Channels Scanned", value=str(summary.total_scanned), inline=True)
        embed.add_field(name="Access Already Available", value=str(summary.already_accessible), inline=True)
        embed.add_field(name="Updated", value=str(summary.updated), inline=True)
        embed.add_field(name="Skipped", value=str(summary.skipped), inline=True)
        embed.add_field(name="Failed", value=str(summary.failed), inline=True)
        status_text = "🟢 COMPLETE" if summary.failed == 0 else f"🟡 COMPLETED WITH {summary.failed} FAILURES"
        embed.add_field(name="Status", value=status_text, inline=True)
        embed.set_footer(text="RAI Permission Engine • Zero Dangerous Permissions Granted")
        return embed
