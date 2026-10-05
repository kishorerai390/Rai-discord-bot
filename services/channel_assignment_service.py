"""
RAI — CANONICAL CHANNEL ASSIGNMENT & PURPOSE ROUTING SERVICE

Implements the guild-specific 17-channel purpose mapping system:
1. Discovers existing channels in the server without creating, deleting, renaming, or duplicating channels.
2. Resolves canonical destinations for all Rai security, reporting, and administrative events.
3. Performs least-privilege permission audits per channel (View, Send, Embed, History).
4. Tracks channel assignment health: CONNECTED, DEGRADED, MISSING, NO_PERMISSION, DISABLED.
5. Provides safe channel testing with automated verification and cleanup.
6. Handles missing or deleted channels gracefully without crashing or spamming.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import discord

from database.models import GuildChannelConfig

logger = logging.getLogger("Rai.ChannelAssignment")


class ChannelHealthStatus(str, Enum):
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    MISSING = "MISSING"
    NO_PERMISSION = "NO_PERMISSION"
    DISABLED = "DISABLED"


@dataclass
class ChannelPurposeDefinition:
    key: str
    config_field: str
    display_name: str
    category_group: str  # "SECURITY", "REPORTS", "ADMIN"
    description: str
    search_keywords: List[str]
    emoji: str
    requires_history: bool = True
    requires_embeds: bool = True


# The 17 Canonical Channel Purposes across 3 Primary Operational Categories
CANONICAL_CHANNELS: List[ChannelPurposeDefinition] = [
    # --- RAI SECURITY ---
    ChannelPurposeDefinition(
        key="security_alerts",
        config_field="security_alerts_channel_id",
        display_name="Security Alerts",
        category_group="SECURITY",
        description="Critical security events, mass destructive actions, raid alarms, and anti-nuke triggers.",
        search_keywords=["security-alerts", "security_alerts", "security-alert", "securityalert", "alerts"],
        emoji="🚨",
    ),
    ChannelPurposeDefinition(
        key="anti_nuke",
        config_field="anti_nuke_channel_id",
        display_name="Anti-Nuke",
        category_group="SECURITY",
        description="Anti-Nuke operational threshold events, role/channel spikes, and dangerous integrations.",
        search_keywords=["anti-nuke", "antinuke", "anti_nuke", "nuke-control", "nuke-defense"],
        emoji="🧱",
    ),
    ChannelPurposeDefinition(
        key="lockdown_control",
        config_field="lockdown_control_channel_id",
        display_name="Lockdown Control",
        category_group="SECURITY",
        description="Staff interactive control panel for emergency lockdown and security state overrides.",
        search_keywords=["lockdown-control", "lockdown", "emergency-control", "lockdown_control"],
        emoji="🔒",
    ),
    ChannelPurposeDefinition(
        key="security_log",
        config_field="security_log_channel_id",
        display_name="Security Log",
        category_group="SECURITY",
        description="Historical security logs: whitelist changes, quarantine, security policy changes, recovery.",
        search_keywords=["security-log", "security_log", "security-logs", "securitylog"],
        emoji="🛡️",
    ),
    ChannelPurposeDefinition(
        key="audit_monitor",
        config_field="audit_monitor_channel_id",
        display_name="Audit Monitor",
        category_group="SECURITY",
        description="Batched and deduplicated Discord audit trail (roles, channels, perms, webhooks, bot added).",
        search_keywords=["audit-monitor", "audit_monitor", "audit-log", "audit-feed", "audit"],
        emoji="🔍",
    ),

    # --- RAI REPORTS ---
    ChannelPurposeDefinition(
        key="security_report",
        config_field="security_report_channel_id",
        display_name="Security Report",
        category_group="REPORTS",
        description="Detailed incident cards for verified security occurrences, anti-raid, and permission abuse.",
        search_keywords=["security-report", "security_report", "sec-report", "securityreport"],
        emoji="🚨",
    ),
    ChannelPurposeDefinition(
        key="moderation_report",
        config_field="moderation_report_channel_id",
        display_name="Moderation Report",
        category_group="REPORTS",
        description="Staff moderation activity (warn, timeout, kick, ban, unban, purge, AutoMod actions).",
        search_keywords=["mod-report", "moderation-report", "mod_report", "mod-logs", "modreport"],
        emoji="🛡️",
    ),
    ChannelPurposeDefinition(
        key="music_report",
        config_field="music_report_channel_id",
        display_name="Music Report",
        category_group="REPORTS",
        description="Music operational failures and recovery only. Does not log routine track plays.",
        search_keywords=["music-report", "music_report", "audio-report", "musicreport"],
        emoji="🎵",
    ),
    ChannelPurposeDefinition(
        key="room_report",
        config_field="room_report_channel_id",
        display_name="Room Report",
        category_group="REPORTS",
        description="Dynamic Voice operational failures and recoveries only. Normal room joins generate no reports.",
        search_keywords=["room-report", "room_report", "voice-report", "vc-report", "roomreport"],
        emoji="🔐",
    ),
    ChannelPurposeDefinition(
        key="bot_report",
        config_field="bot_report_channel_id",
        display_name="Bot Report",
        category_group="REPORTS",
        description="Bot-level errors, unhandled exceptions, worker crashes, and Discord API degradation.",
        search_keywords=["bot-report", "bot_report", "client-report", "botreport"],
        emoji="🤖",
    ),
    ChannelPurposeDefinition(
        key="system_report",
        config_field="system_report_channel_id",
        display_name="System Report",
        category_group="REPORTS",
        description="Infrastructure-level events: database failures, database recoveries, API synchronization.",
        search_keywords=["system-report", "system_report", "infra-report", "sys-report", "systemreport"],
        emoji="⚙️",
    ),

    # --- RAI ADMIN ---
    ChannelPurposeDefinition(
        key="admin_control",
        config_field="admin_control_channel_id",
        display_name="Admin Control",
        category_group="ADMIN",
        description="Central staff control panel (Rai Status, Rai Doctor, Lockdown, Maintenance, Modules).",
        search_keywords=["admin-control", "admin_control", "staff-control", "command-center", "admincontrol"],
        emoji="👑",
    ),
    ChannelPurposeDefinition(
        key="server_dashboard",
        config_field="server_dashboard_channel_id",
        display_name="Server Dashboard",
        category_group="ADMIN",
        description="Real server operational metrics (members, active rooms, music sessions, incidents).",
        search_keywords=["server-dashboard", "server_dashboard", "dashboard", "server-stats"],
        emoji="📊",
    ),
    ChannelPurposeDefinition(
        key="bot_config",
        config_field="bot_config_channel_id",
        display_name="Bot Config",
        category_group="ADMIN",
        description="Configuration and feature-flag controls for Rai subsystems.",
        search_keywords=["bot-config", "bot_config", "settings", "configuration", "botconfig"],
        emoji="⚙️",
    ),
    ChannelPurposeDefinition(
        key="automation_control",
        config_field="automation_control_channel_id",
        display_name="Automation Control",
        category_group="ADMIN",
        description="Active automation workflows, schedules, and trigger status.",
        search_keywords=["automation-control", "automation_control", "automations", "workflow-control"],
        emoji="🤖",
    ),
    ChannelPurposeDefinition(
        key="backup_control",
        config_field="backup_control_channel_id",
        display_name="Backup Control",
        category_group="ADMIN",
        description="Interactive backup creation, inspection, and verified restore consoles.",
        search_keywords=["backup-control", "backup_control", "backups", "snapshots", "backupcontrol"],
        emoji="💾",
    ),
    ChannelPurposeDefinition(
        key="system_health",
        config_field="system_health_channel_id",
        display_name="System Health",
        category_group="ADMIN",
        description="Operational health matrix across Gateway, DB, Workers, Music, Voice, Security, and API.",
        search_keywords=["system-health", "system_health", "health-monitor", "health", "systemhealth"],
        emoji="💗",
    ),
]

PURPOSE_MAP: Dict[str, ChannelPurposeDefinition] = {p.key: p for p in CANONICAL_CHANNELS}
FIELD_TO_PURPOSE: Dict[str, ChannelPurposeDefinition] = {p.config_field: p for p in CANONICAL_CHANNELS}


@dataclass
class ChannelHealthReport:
    purpose: ChannelPurposeDefinition
    channel_id: Optional[int]
    channel_name: Optional[str]
    status: ChannelHealthStatus
    missing_permissions: List[str]
    details: str


@dataclass
class ChannelDiscoveryResult:
    matched: Dict[str, int]  # purpose_key -> channel_id
    ambiguous: Dict[str, List[int]]  # purpose_key -> list of matching channel_ids
    unmatched: List[str]  # list of purpose_keys that could not be auto-discovered


class ChannelAssignmentService:
    """
    Central service for guild-specific channel purpose mapping and health auditing.
    """

    _permission_warning_timestamps: Dict[Tuple[int, str], float] = {}

    @classmethod
    def normalize_channel_name(cls, name: str) -> str:
        """Strip emojis, special unicode decorators, and normalize to alphanumeric lower-case kebab."""
        clean = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE)
        clean = clean.strip().lower().replace(" ", "-").replace("_", "-")
        clean = re.sub(r"-+", "-", clean).strip("-")
        return clean

    @classmethod
    async def get_config(cls, bot: Any, guild_id: int) -> GuildChannelConfig:
        """Fetch or create default channel config for the guild."""
        if hasattr(bot, "db") and bot.db:
            try:
                cfg = await bot.db.get_guild_channel_config(guild_id)
                if cfg:
                    return cfg
            except Exception as e:
                logger.warning(f"Error fetching guild channel config: {e}")

        # Fallback to existing owner_reports_config if available
        initial_kwargs: Dict[str, Any] = {}
        if hasattr(bot, "db") and bot.db:
            try:
                old_cfg = await bot.db.get_owner_reports_config(guild_id)
                if old_cfg:
                    initial_kwargs["security_report_channel_id"] = getattr(old_cfg, "security_report_id", None)
                    initial_kwargs["moderation_report_channel_id"] = getattr(old_cfg, "mod_report_id", None)
                    initial_kwargs["music_report_channel_id"] = getattr(old_cfg, "music_report_id", None)
                    initial_kwargs["room_report_channel_id"] = getattr(old_cfg, "room_report_id", None)
                    initial_kwargs["bot_report_channel_id"] = getattr(old_cfg, "bot_report_id", None)
                    initial_kwargs["system_report_channel_id"] = getattr(old_cfg, "system_report_id", None)
            except Exception:
                pass

        if hasattr(bot, "db") and bot.db:
            try:
                return await bot.db.set_guild_channel_config(guild_id, **initial_kwargs)
            except Exception as e:
                logger.warning(f"Error initializing guild channel config: {e}")

        return GuildChannelConfig(guild_id=guild_id)

    @classmethod
    async def assign_channel(
        cls, bot: Any, guild_id: int, purpose_key: str, channel_id: Optional[int]
    ) -> Optional[GuildChannelConfig]:
        """Assign or unassign a specific purpose key to a Discord text channel."""
        purpose = PURPOSE_MAP.get(purpose_key)
        if not purpose:
            raise ValueError(f"Unknown channel purpose: {purpose_key}")

        if hasattr(bot, "db") and bot.db:
            update_data = {purpose.config_field: channel_id}
            cfg = await bot.db.update_guild_channel_config(guild_id, **update_data)
            return cfg
        return None

    @classmethod
    def discover_channels(cls, guild: discord.Guild) -> ChannelDiscoveryResult:
        """
        Inspect the existing guild text channels and find candidate assignments.
        DOES NOT create, delete, rename, or duplicate any channels.
        Detects ambiguous duplicates and requests explicit administrator choice.
        """
        text_channels = [
            c for c in guild.channels if isinstance(c, discord.TextChannel)
        ]

        matched: Dict[str, int] = {}
        ambiguous: Dict[str, List[int]] = {}
        unmatched: List[str] = []

        for purpose in CANONICAL_CHANNELS:
            candidates: List[discord.TextChannel] = []

            for ch in text_channels:
                norm_name = cls.normalize_channel_name(ch.name)
                # 1. Exact match on normalized keywords
                for kw in purpose.search_keywords:
                    norm_kw = cls.normalize_channel_name(kw)
                    if norm_name == norm_kw:
                        candidates.append(ch)
                        break

            # 2. If no exact match, check substring match
            if not candidates:
                for ch in text_channels:
                    norm_name = cls.normalize_channel_name(ch.name)
                    for kw in purpose.search_keywords:
                        norm_kw = cls.normalize_channel_name(kw)
                        if norm_kw in norm_name or norm_name in norm_kw:
                            if ch not in candidates:
                                candidates.append(ch)

            if len(candidates) == 1:
                matched[purpose.key] = candidates[0].id
            elif len(candidates) > 1:
                ambiguous[purpose.key] = [c.id for c in candidates]
            else:
                unmatched.append(purpose.key)

        return ChannelDiscoveryResult(
            matched=matched,
            ambiguous=ambiguous,
            unmatched=unmatched,
        )

    @classmethod
    async def auto_assign_discovered_channels(
        cls, bot: Any, guild: discord.Guild, overwrite_existing: bool = False
    ) -> Tuple[GuildChannelConfig, ChannelDiscoveryResult]:
        """
        Safely auto-populates unassigned channels from discovered single-matches.
        Never blindly overwrites ambiguous channels or already-configured channels unless requested.
        """
        cfg = await cls.get_config(bot, guild.id)
        discovery = cls.discover_channels(guild)

        updates: Dict[str, Any] = {}
        for purpose_key, ch_id in discovery.matched.items():
            purpose = PURPOSE_MAP[purpose_key]
            current_val = getattr(cfg, purpose.config_field, None)
            if current_val is None or overwrite_existing:
                updates[purpose.config_field] = ch_id

        if updates and hasattr(bot, "db") and bot.db:
            cfg = await bot.db.update_guild_channel_config(guild.id, **updates)

        return cfg, discovery

    @classmethod
    def check_permissions(
        cls, channel: discord.TextChannel
    ) -> Tuple[bool, List[str]]:
        """
        Verify that Rai has required least-privilege permissions in the given channel.
        Requires: View Channel, Send Messages, Embed Links, Read Message History.
        """
        guild = channel.guild
        me = getattr(guild, "me", None)
        if not me:
            return False, ["Bot Member Unavailable"]

        perms = channel.permissions_for(me)
        missing: List[str] = []

        if not perms.view_channel:
            missing.append("View Channel")
        if not perms.send_messages:
            missing.append("Send Messages")
        if not perms.embed_links:
            missing.append("Embed Links")
        if not perms.read_message_history:
            missing.append("Read Message History")

        return len(missing) == 0, missing

    @classmethod
    def evaluate_channel_health(
        cls, guild: discord.Guild, purpose_key: str, channel_id: Optional[int]
    ) -> ChannelHealthReport:
        """Compute the operational health of a given channel purpose."""
        purpose = PURPOSE_MAP[purpose_key]

        if not channel_id:
            return ChannelHealthReport(
                purpose=purpose,
                channel_id=None,
                channel_name=None,
                status=ChannelHealthStatus.DISABLED,
                missing_permissions=[],
                details="Channel assignment unconfigured.",
            )

        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return ChannelHealthReport(
                purpose=purpose,
                channel_id=channel_id,
                channel_name=None,
                status=ChannelHealthStatus.MISSING,
                missing_permissions=[],
                details="Configured channel no longer exists in the server.",
            )

        is_valid, missing = cls.check_permissions(channel)
        if not is_valid:
            return ChannelHealthReport(
                purpose=purpose,
                channel_id=channel_id,
                channel_name=channel.name,
                status=ChannelHealthStatus.NO_PERMISSION,
                missing_permissions=missing,
                details=f"Missing required permissions: {', '.join(missing)}",
            )

        return ChannelHealthReport(
            purpose=purpose,
            channel_id=channel_id,
            channel_name=channel.name,
            status=ChannelHealthStatus.CONNECTED,
            missing_permissions=[],
            details="Operational with all required permissions.",
        )

    @classmethod
    async def audit_all_channels(
        cls, bot: Any, guild: discord.Guild
    ) -> List[ChannelHealthReport]:
        """Runs a complete health evaluation for all 17 canonical purposes in a guild."""
        cfg = await cls.get_config(bot, guild.id)
        reports: List[ChannelHealthReport] = []

        for purpose in CANONICAL_CHANNELS:
            ch_id = getattr(cfg, purpose.config_field, None)
            health = cls.evaluate_channel_health(guild, purpose.key, ch_id)
            reports.append(health)

        return reports

    @classmethod
    async def resolve_destination(
        cls, bot: Any, guild_id: int, purpose_key: str
    ) -> Tuple[Optional[discord.TextChannel], ChannelHealthStatus, Optional[str]]:
        """
        Resolves the actual discord.TextChannel for an operational event.
        Returns: (channel, health_status, failure_reason)
        """
        cfg = await cls.get_config(bot, guild_id)
        purpose = PURPOSE_MAP.get(purpose_key)
        if not purpose:
            return None, ChannelHealthStatus.DISABLED, f"Unknown purpose: {purpose_key}"

        ch_id = getattr(cfg, purpose.config_field, None)
        if not ch_id:
            return None, ChannelHealthStatus.DISABLED, f"Purpose '{purpose.display_name}' is not configured"

        guild = bot.get_guild(guild_id) if hasattr(bot, "get_guild") else None
        if not guild:
            return None, ChannelHealthStatus.MISSING, "Guild not found"

        channel = guild.get_channel(ch_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return None, ChannelHealthStatus.MISSING, f"Assigned channel ID `{ch_id}` was deleted or is missing"

        is_valid, missing = cls.check_permissions(channel)
        if not is_valid:
            return None, ChannelHealthStatus.NO_PERMISSION, f"Missing permissions: {', '.join(missing)}"

        return channel, ChannelHealthStatus.CONNECTED, None

    @classmethod
    async def test_single_channel(
        cls, bot: Any, guild: discord.Guild, purpose_key: str
    ) -> Dict[str, Any]:
        """
        Dispatches a transient diagnostic test message to verify end-to-end delivery
        and immediately cleans it up.
        """
        channel, status, reason = await cls.resolve_destination(bot, guild.id, purpose_key)
        purpose = PURPOSE_MAP[purpose_key]

        if not channel:
            return {
                "purpose_key": purpose_key,
                "display_name": purpose.display_name,
                "status": status.value,
                "success": False,
                "error": reason,
            }

        embed = discord.Embed(
            title=f"🧪 Rai Channel Test • {purpose.display_name}",
            description=(
                f"**Purpose:** `{purpose_key}`\n"
                f"**Channel:** {channel.mention}\n"
                f"**Category:** {purpose.category_group}\n\n"
                "✓ **View Channel**\n"
                "✓ **Send Messages**\n"
                "✓ **Embed Links**\n"
                "✓ **Read Message History**\n\n"
                "🟢 Verification passed. This message will self-destruct in 8 seconds."
            ),
            color=0x57F287,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_footer(text="Rai Channel Diagnostics • Automated Self-Test")

        try:
            test_msg = await channel.send(embed=embed)
            # Safe async cleanup after delay
            asyncio.create_task(cls._cleanup_test_message(test_msg, delay=8.0))
            return {
                "purpose_key": purpose_key,
                "display_name": purpose.display_name,
                "status": ChannelHealthStatus.CONNECTED.value,
                "channel_id": channel.id,
                "channel_name": channel.name,
                "success": True,
                "error": None,
            }
        except Exception as e:
            return {
                "purpose_key": purpose_key,
                "display_name": purpose.display_name,
                "status": ChannelHealthStatus.NO_PERMISSION.value,
                "channel_id": channel.id,
                "channel_name": channel.name,
                "success": False,
                "error": str(e),
            }

    @classmethod
    async def _cleanup_test_message(cls, message: discord.Message, delay: float = 8.0) -> None:
        """Safely delete test message without throwing exceptions if already deleted."""
        try:
            await asyncio.sleep(delay)
            await message.delete()
        except Exception:
            pass
