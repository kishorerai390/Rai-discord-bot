"""
Unified Permission-Based Reporting Service for RAI.

Guarantees:
1. Permission verification prior to any report delivery.
2. Controlled, non-spammy permission requests with cooldowns and UI buttons.
3. Event-driven reporting (no periodic loop spam or continuous identical messages).
4. State-change reporting (only when previous_state != current_state).
5. Error deduplication via normalized fingerprinting and in-place message updates.
6. Cooldown enforcement per report type, with critical security bypass.
7. Optional success reporting (disabled by default to prevent spam).
8. Elimination of report loops and health loops.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import logging
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import discord
from discord.ui import Button, View

logger = logging.getLogger("rai.services.report_service")


class ReportStatus(str, Enum):
    SUCCESS = "SUCCESS"
    UPDATED = "UPDATED"
    SKIPPED = "SKIPPED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    DESTINATION_MISSING = "DESTINATION_MISSING"
    RATE_LIMITED = "RATE_LIMITED"
    DISABLED = "DISABLED"
    COOLDOWN = "COOLDOWN"
    ERROR = "ERROR"


class ReportSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    IMPORTANT = "IMPORTANT"
    CRITICAL = "CRITICAL"


class ReportType(str, Enum):
    SECURITY = "security"
    SYSTEM = "system"
    MUSIC = "music"
    ROOM = "room"
    BACKUP = "backup"
    BOT = "bot"
    HEALTH = "health"
    MOD = "mod"
    WORKFLOW = "workflow"


@dataclass
class ReportResult:
    status: ReportStatus
    message: str
    event_id: Optional[str] = None
    message_id: Optional[int] = None
    channel_id: Optional[int] = None
    occurrences: int = 1
    diagnostic_id: Optional[str] = None
    is_updated: bool = False


# Required channel permissions for report dispatch
REQUIRED_REPORT_PERMISSIONS: Dict[str, str] = {
    "view_channel": "View Channel",
    "send_messages": "Send Messages",
    "embed_links": "Embed Links",
    "read_message_history": "Read Message History",
}

# Cooldowns in seconds per report type
DEFAULT_REPORT_COOLDOWNS: Dict[str, float] = {
    ReportType.SECURITY.value: 0.0,      # Immediate for critical
    ReportType.SYSTEM.value: 300.0,      # 5 minutes
    ReportType.MUSIC.value: 300.0,       # 5 minutes
    ReportType.ROOM.value: 300.0,        # 5 minutes
    ReportType.BACKUP.value: 900.0,      # 15 minutes
    ReportType.BOT.value: 300.0,         # 5 minutes
    ReportType.HEALTH.value: 300.0,      # State-change only
    ReportType.MOD.value: 300.0,         # 5 minutes
    ReportType.WORKFLOW.value: 300.0,    # 5 minutes
}

# Cooldown between permission warnings (1 hour)
REPORT_PERMISSION_WARNING_COOLDOWN = 3600.0

# Global guild throttle: maximum report messages allowed in a 5-minute sliding window
MAX_REPORTS_PER_5_MINUTES = 10
RATE_LIMIT_WINDOW = 300.0


class ReportPermissionCheckView(View):
    """
    Interactive Discord UI view for checking and approving report permissions.
    """

    def __init__(self, guild_id: int, channel_id: int, report_type: str = "all"):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.report_type = report_type
        self.check_button = Button(
            label="Check Permissions",
            style=discord.ButtonStyle.primary,
            custom_id=f"rai_rep:check_perms:{guild_id}:{channel_id}",
            emoji="🔍",
        )
        self.check_button.callback = self.on_check_permissions
        self.add_item(self.check_button)

    async def on_check_permissions(self, interaction: discord.Interaction) -> None:
        """Handle button click to re-evaluate permissions."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This action can only be run in a server.", ephemeral=True)
            return

        bot = interaction.client
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ The configured report channel no longer exists.", ephemeral=True)
            return

        is_valid, missing = ReportService.check_channel_permissions(channel)
        if is_valid:
            if hasattr(bot, "db") and bot.db:
                await bot.db.update_report_permission_state(
                    guild_id=self.guild_id,
                    channel_id=self.channel_id,
                    report_type=self.report_type,
                    status="APPROVED",
                    last_error=None,
                )
            self.check_button.disabled = True
            self.check_button.label = "✓ Permissions Granted"
            self.check_button.style = discord.ButtonStyle.success
            try:
                await interaction.response.edit_message(view=self)
            except Exception:
                await interaction.response.send_message("✅ Permissions verified! Report delivery is now active.", ephemeral=True)
            else:
                await interaction.followup.send("✅ Permissions verified! Report delivery is now active.", ephemeral=True)
        else:
            missing_text = "\n".join(f"• {m}" for m in missing)
            await interaction.response.send_message(
                f"⚠️ Channel <#{self.channel_id}> is still missing required permissions:\n{missing_text}\n"
                "Please update the bot's permissions in channel settings and try again.",
                ephemeral=True,
            )


class ReportService:
    """
    Central, unified service controlling all report delivery across RAI.
    """

    _last_report_times: Dict[Tuple[int, str], float] = {}
    _guild_report_timestamps: Dict[int, List[float]] = defaultdict(list)
    _state_cache: Dict[Tuple[int, str], str] = {}
    _delivery_lock: Set[str] = set()

    @classmethod
    def check_channel_permissions(
        cls, channel: Any, requires_files: bool = False
    ) -> Tuple[bool, List[str]]:
        """
        Verify that Rai has the requisite Discord permissions in the target channel.
        """
        if not channel or not hasattr(channel, "guild") or not channel.guild:
            return False, ["Channel or Guild Unavailable"]

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
        if requires_files and not perms.attach_files:
            missing.append("Attach Files")

        return len(missing) == 0, missing

    @classmethod
    def compute_fingerprint(
        cls,
        guild_id: int,
        report_type: str,
        module: Optional[str],
        error_category: Optional[str],
        error_code: Optional[str],
        message: str,
    ) -> str:
        """
        Generate a stable normalized fingerprint for grouping identical incidents.
        Strips variable elements like memory addresses, IDs, and timestamps.
        """
        norm = re.sub(r"0x[0-9a-fA-F]+", "<HEX>", message)
        norm = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?\b", "<TIMESTAMP>", norm)
        norm = re.sub(r"\b\d{17,20}\b", "<DISCORD_ID>", norm)
        norm = norm.strip().lower()

        raw = f"{guild_id}:{report_type}:{module or 'core'}:{error_category or 'general'}:{error_code or 'none'}:{norm}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @classmethod
    async def get_destinations(cls, bot: Any, guild_id: int) -> List[Any]:
        """Fetch all configured report destinations for a guild."""
        if hasattr(bot, "db") and bot.db:
            try:
                return await bot.db.get_report_destinations(guild_id)
            except Exception as e:
                logger.warning(f"Error fetching report destinations: {e}")
        return []

    @classmethod
    async def remove_destination(cls, bot: Any, guild_id: int, channel_id: int) -> bool:
        """Remove all report destinations pointing to a deleted or invalid channel."""
        if hasattr(bot, "db") and bot.db:
            try:
                destinations = await bot.db.get_report_destinations(guild_id)
                for d in destinations:
                    if d.channel_id == channel_id:
                        await bot.db.delete_report_destination(guild_id, d.report_type)
                return True
            except Exception as e:
                logger.warning(f"Error removing report destination: {e}")
        return False

    @classmethod
    async def resolve_destination_channel(
        cls, bot: Any, guild_id: int, report_type: str
    ) -> Tuple[Optional[discord.TextChannel], Optional[str]]:
        """
        Resolve the destination Discord channel for a report type.
        Returns (channel, failure_reason).
        """
        channel_id: Optional[int] = None

        # 1. Check report_destinations table
        if hasattr(bot, "db") and bot.db:
            try:
                dest = await bot.db.get_report_destination(guild_id, report_type)
                if dest:
                    if not dest.enabled:
                        return None, "DISABLED"
                    channel_id = dest.channel_id
            except Exception as e:
                logger.warning(f"Error reading report_destinations: {e}")

        # 2. Fallback to owner_reports_config table
        if not channel_id and hasattr(bot, "db") and bot.db:
            try:
                cfg = await bot.db.get_owner_reports_config(guild_id)
                if cfg:
                    attr_map = {
                        ReportType.SECURITY.value: "security_report_id",
                        ReportType.MOD.value: "mod_report_id",
                        ReportType.MUSIC.value: "music_report_id",
                        ReportType.ROOM.value: "room_report_id",
                        ReportType.BOT.value: "bot_report_id",
                        ReportType.SYSTEM.value: "system_report_id",
                        ReportType.HEALTH.value: "system_report_id",
                        ReportType.BACKUP.value: "system_report_id",
                        ReportType.WORKFLOW.value: "system_report_id",
                    }
                    col_name = attr_map.get(report_type, "system_report_id")
                    channel_id = getattr(cfg, col_name, None)
            except Exception as e:
                logger.warning(f"Error reading owner_reports_config: {e}")

        if not channel_id:
            return None, "NO_DESTINATION_CONFIGURED"

        # 3. Resolve Discord Channel Object
        guild = bot.get_guild(guild_id) if hasattr(bot, "get_guild") else None
        channel = None
        if guild:
            channel = guild.get_channel(channel_id)
        if not channel and hasattr(bot, "get_channel"):
            channel = bot.get_channel(channel_id)
        if not channel and hasattr(bot, "fetch_channel"):
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception:
                channel = None

        if not channel or not (isinstance(channel, (discord.TextChannel, discord.Thread)) or hasattr(channel, "send")):
            return None, "DESTINATION_MISSING"

        return channel, None

    @classmethod
    async def send_permission_warning(
        cls,
        bot: Any,
        guild: discord.Guild,
        channel: discord.TextChannel,
        report_type: str,
        missing_perms: List[str],
    ) -> None:
        """
        Send a one-time, controlled permission warning without spamming.
        Enforces a 1-hour cooldown.
        """
        now = time.time()
        guild_id = guild.id
        channel_id = channel.id

        # Check existing permission state & cooldown in DB
        if hasattr(bot, "db") and bot.db:
            try:
                state = await bot.db.get_report_permission_state(guild_id, channel_id, report_type)
                if state and state.last_warning_at:
                    try:
                        last_ts = datetime.datetime.fromisoformat(state.last_warning_at).timestamp()
                        if (now - last_ts) < REPORT_PERMISSION_WARNING_COOLDOWN:
                            # Still on cooldown, update state without sending message
                            await bot.db.update_report_permission_state(
                                guild_id=guild_id,
                                channel_id=channel_id,
                                report_type=report_type,
                                status="PENDING",
                                last_error=f"Missing: {', '.join(missing_perms)}",
                                record_warning=False,
                            )
                            return
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Could not read permission state from DB: {e}")

        # Construct warning embed
        embed = discord.Embed(
            title="⚠️ Rai Report Permission Required",
            description=f"I need permission to post reports in <#{channel_id}>.",
            color=0xFEE75C,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        req_lines = []
        for perm_key, perm_label in REQUIRED_REPORT_PERMISSIONS.items():
            icon = "❌" if perm_label in missing_perms else "✓"
            req_lines.append(f"{icon} {perm_label}")
        embed.add_field(name="Required Permissions", value="\n".join(req_lines), inline=False)
        embed.set_footer(text="Please grant the required permissions in channel settings and press Check Permissions.")

        view = ReportPermissionCheckView(guild_id=guild_id, channel_id=channel_id, report_type=report_type)

        msg = None
        # Attempt delivery:
        # 1. Try sending into the target channel if Send Messages is available
        perms_me = channel.permissions_for(guild.me)
        if perms_me.send_messages and perms_me.embed_links:
            try:
                msg = await channel.send(embed=embed, view=view)
            except Exception:
                msg = None

        # 2. If target channel cannot receive messages, notify guild owner DM dynamically
        if not msg:
            owner_id = getattr(guild, "owner_id", None)
            if owner_id:
                try:
                    owner = guild.get_member(owner_id) or (await bot.fetch_user(owner_id) if hasattr(bot, "fetch_user") else None)
                    if owner and hasattr(owner, "send"):
                        msg = await owner.send(embed=embed, view=view)
                except Exception as dm_err:
                    logger.warning(f"Could not send permission warning DM to owner: {dm_err}")

        # Update permission state in DB with warning timestamp
        if hasattr(bot, "db") and bot.db:
            try:
                await bot.db.update_report_permission_state(
                    guild_id=guild_id,
                    channel_id=channel_id,
                    report_type=report_type,
                    status="PENDING",
                    last_error=f"Missing: {', '.join(missing_perms)}",
                    warning_message_id=msg.id if msg else None,
                    record_warning=True,
                )
            except Exception as db_err:
                logger.warning(f"Could not update permission state in DB: {db_err}")

    @classmethod
    async def report_state_change(
        cls,
        bot: Any,
        guild_id: int,
        component: str,
        current_state: str,
        report_type: str = ReportType.SYSTEM.value,
        details: Optional[str] = None,
        diagnostic_id: Optional[str] = None,
    ) -> Optional[ReportResult]:
        """
        Report only when state changes (previous_state != current_state).
        - HEALTHY -> DEGRADED/FAILED: Generates ONE failure report.
        - FAILED -> FAILED: Suppressed (no duplicate spam).
        - DEGRADED/FAILED -> HEALTHY: Generates ONE recovery report.
        """
        cache_key = (guild_id, component)
        previous_state = cls._state_cache.get(cache_key)

        # Baseline: initial healthy state does not generate unsolicited report
        if previous_state is None and current_state == "HEALTHY":
            cls._state_cache[cache_key] = current_state
            return None

        # No state change -> strictly no report
        if previous_state == current_state:
            return None

        # State transition detected
        cls._state_cache[cache_key] = current_state

        diag_id = diagnostic_id or f"RAI-STATE-{uuid.uuid4().hex[:6].upper()}"

        if current_state == "HEALTHY":
            # RECOVERY EVENT
            title = f"🟢 {component.title()} Recovered"
            desc = f"**Status:** {component.title()} has recovered to **HEALTHY**.\n"
            if details:
                desc += f"\n**Details:** {details}\n"
            desc += f"\n**Diagnostic ID:** `{diag_id}`"

            embed = discord.Embed(
                title=title,
                description=desc,
                color=0x57F287,  # Green
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            return await cls.report(
                bot=bot,
                guild_id=guild_id,
                report_type=report_type,
                severity=ReportSeverity.IMPORTANT,
                title=title,
                embed=embed,
                diagnostic_id=diag_id,
                module=component,
                force=True,  # Recovery reports are important
            )
        else:
            # FAILURE / DEGRADATION EVENT
            title = f"⚠️ {component.title()} State Change: {current_state}"
            desc = f"**Status:** {component.title()} changed state from `{previous_state or 'UNKNOWN'}` to `{current_state}`.\n"
            if details:
                desc += f"\n**Details:** {details}\n"
            desc += f"\n**Diagnostic ID:** `{diag_id}`"

            severity = ReportSeverity.CRITICAL if current_state == "FAILED" else ReportSeverity.WARNING
            embed = discord.Embed(
                title=title,
                description=desc,
                color=0xED4245 if current_state == "FAILED" else 0xFEE75C,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            return await cls.report(
                bot=bot,
                guild_id=guild_id,
                report_type=report_type,
                severity=severity,
                title=title,
                embed=embed,
                diagnostic_id=diag_id,
                module=component,
            )

    @classmethod
    async def report(
        cls,
        bot: Any,
        guild_id: int,
        report_type: str,
        severity: ReportSeverity = ReportSeverity.WARNING,
        title: Optional[str] = None,
        description: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
        view: Optional[View] = None,
        module: Optional[str] = None,
        error_category: Optional[str] = None,
        error_code: Optional[str] = None,
        is_success: bool = False,
        diagnostic_id: Optional[str] = None,
        force: bool = False,
        requires_files: bool = False,
    ) -> ReportResult:
        """
        Unified report entry point.
        All bot modules MUST route report delivery through this method.
        """
        # --- 1. Loop Breaker ---
        call_key = f"{guild_id}:{report_type}:{title or ''}"
        if call_key in cls._delivery_lock:
            logger.warning(f"[REPORT_LOOP_BLOCKED] Recursive report dispatch prevented: {call_key}")
            return ReportResult(status=ReportStatus.SKIPPED, message="Recursive report call prevented")
        cls._delivery_lock.add(call_key)

        try:
            return await cls._execute_report(
                bot=bot,
                guild_id=guild_id,
                report_type=report_type,
                severity=severity,
                title=title,
                description=description,
                embed=embed,
                view=view,
                module=module,
                error_category=error_category,
                error_code=error_code,
                is_success=is_success,
                diagnostic_id=diagnostic_id,
                force=force,
                requires_files=requires_files,
            )
        finally:
            cls._delivery_lock.discard(call_key)

    @classmethod
    async def _execute_report(
        cls,
        bot: Any,
        guild_id: int,
        report_type: str,
        severity: ReportSeverity,
        title: Optional[str],
        description: Optional[str],
        embed: Optional[discord.Embed],
        view: Optional[View],
        module: Optional[str],
        error_category: Optional[str],
        error_code: Optional[str],
        is_success: bool,
        diagnostic_id: Optional[str],
        force: bool,
        requires_files: bool,
    ) -> ReportResult:
        now = time.time()

        # --- 2. Success Reports Suppression ---
        # Success messages and INFO-level reports are suppressed unless success_reports_enabled is explicitly set
        if is_success or severity == ReportSeverity.INFO:
            success_enabled = False
            if hasattr(bot, "db") and bot.db:
                try:
                    cfg = await bot.db.get_owner_reports_config(guild_id)
                    success_enabled = getattr(cfg, "success_reports_enabled", False) if cfg else False
                except Exception:
                    success_enabled = False
            if not success_enabled and not force:
                logger.debug(f"[REPORT_SUPPRESSED] Success/INFO report skipped for guild {guild_id}")
                return ReportResult(status=ReportStatus.SKIPPED, message="Success/INFO reports disabled")

        # --- 3. Resolve Destination Channel ---
        channel, failure_reason = await cls.resolve_destination_channel(bot, guild_id, report_type)
        if not channel:
            if failure_reason == "DISABLED":
                return ReportResult(status=ReportStatus.DISABLED, message=f"Report type '{report_type}' is disabled")
            elif failure_reason == "DESTINATION_MISSING":
                # Create one controlled warning if configured destination channel is missing
                logger.warning(f"[DESTINATION_MISSING] Configured channel for {report_type} in guild {guild_id} not found")
                return ReportResult(status=ReportStatus.DESTINATION_MISSING, message="Report channel missing")
            else:
                return ReportResult(status=ReportStatus.SKIPPED, message=failure_reason or "Destination unavailable")

        # --- 4. Permission Verification ---
        is_valid, missing_perms = cls.check_channel_permissions(channel, requires_files=requires_files)
        if not is_valid:
            logger.warning(
                f"[REPORT_PERMISSION_DENIED] Missing {missing_perms} in #{channel.name} ({channel.id}) for {report_type}"
            )
            # Create controlled warning (cooldown enforced internally)
            await cls.send_permission_warning(bot, channel.guild, channel, report_type, missing_perms)
            return ReportResult(
                status=ReportStatus.PERMISSION_DENIED,
                message=f"Missing channel permissions: {', '.join(missing_perms)}",
                channel_id=channel.id,
            )

        # Mark permission state APPROVED if previously pending
        if hasattr(bot, "db") and bot.db:
            try:
                await bot.db.update_report_permission_state(
                    guild_id=guild_id,
                    channel_id=channel.id,
                    report_type=report_type,
                    status="APPROVED",
                    last_error=None,
                )
            except Exception:
                pass

        # --- 5. Global Rate Limiting per Guild ---
        window_start = now - RATE_LIMIT_WINDOW
        timestamps = cls._guild_report_timestamps[guild_id]
        cls._guild_report_timestamps[guild_id] = [ts for ts in timestamps if ts > window_start]

        if len(cls._guild_report_timestamps[guild_id]) >= MAX_REPORTS_PER_5_MINUTES and severity != ReportSeverity.CRITICAL and not force:
            logger.warning(f"[REPORT_RATE_LIMITED] Guild {guild_id} exceeded {MAX_REPORTS_PER_5_MINUTES} reports/5min")
            return ReportResult(status=ReportStatus.RATE_LIMITED, message="Guild report rate limit reached")

        # --- 6. Cooldown Enforcement per Report Type ---
        cooldown = DEFAULT_REPORT_COOLDOWNS.get(report_type, 300.0)
        last_sent = cls._last_report_times.get((guild_id, report_type), 0.0)

        # Critical severity bypasses cooldown
        if (now - last_sent) < cooldown and severity != ReportSeverity.CRITICAL and not force:
            logger.debug(f"[REPORT_COOLDOWN] Report type {report_type} on cooldown for guild {guild_id}")
            # Will be aggregated into existing report if matching fingerprint exists
            pass

        # --- 7. Deduplication & Error Fingerprinting ---
        diag_id = diagnostic_id or f"RAI-{uuid.uuid4().hex[:6].upper()}"
        event_message = description or title or (embed.description if embed else "")
        fingerprint = cls.compute_fingerprint(
            guild_id=guild_id,
            report_type=report_type,
            module=module,
            error_category=error_category,
            error_code=error_code,
            message=event_message,
        )

        event_record = None
        is_new_event = True
        if hasattr(bot, "db") and bot.db:
            try:
                event_record, is_new_event = await bot.db.get_or_create_report_event(
                    event_id=diag_id,
                    guild_id=guild_id,
                    report_type=report_type,
                    severity=severity.value,
                    fingerprint=fingerprint,
                    message=event_message[:500],
                )
            except Exception as e:
                logger.warning(f"Could not register report event in DB: {e}")

        # If identical event exists and was previously posted, update existing message in-place
        if not is_new_event and event_record:
            try:
                updated_rec = await bot.db.update_report_event_occurrence(event_record.event_id)
                occurrences = updated_rec.occurrences if updated_rec else (event_record.occurrences + 1)
                diag_id = event_record.event_id

                delivery = await bot.db.get_report_delivery(event_record.event_id, channel.id)
                if delivery and delivery.message_id:
                    try:
                        existing_msg = await channel.fetch_message(delivery.message_id)
                        if existing_msg:
                            updated_embed = existing_msg.embeds[0] if existing_msg.embeds else (embed or discord.Embed())
                            # Update or append occurrences field
                            field_updated = False
                            for i, f in enumerate(updated_embed.fields):
                                if f.name == "Occurrences" or "Occurrences" in f.name:
                                    updated_embed.set_field_at(
                                        i,
                                        name="⚠️ Occurrences",
                                        value=f"**{occurrences}** (First seen: <t:{int(datetime.datetime.fromisoformat(event_record.first_seen).timestamp())}:R>)",
                                        inline=True,
                                    )
                                    field_updated = True
                                    break
                            if not field_updated:
                                updated_embed.add_field(
                                    name="⚠️ Occurrences",
                                    value=f"**{occurrences}**",
                                    inline=True,
                                )

                            await existing_msg.edit(embed=updated_embed)
                            logger.info(f"[REPORT_UPDATED] In-place update for {diag_id} (count={occurrences}) in #{channel.name}")
                            return ReportResult(
                                status=ReportStatus.UPDATED,
                                message="Existing report updated in-place",
                                event_id=diag_id,
                                message_id=existing_msg.id,
                                channel_id=channel.id,
                                occurrences=occurrences,
                                diagnostic_id=diag_id,
                                is_updated=True,
                            )
                    except Exception as edit_err:
                        logger.warning(f"Could not edit existing report message {delivery.message_id}: {edit_err}")
            except Exception as e:
                logger.warning(f"Error handling duplicate event update: {e}")

        # --- 8. Build Message & Embed ---
        final_embed = embed
        if not final_embed:
            color = 0xED4245 if severity == ReportSeverity.CRITICAL else (0xFEE75C if severity == ReportSeverity.WARNING else 0x5865F2)
            final_embed = discord.Embed(
                title=title or f"📢 {report_type.title()} Report",
                description=description or "No details provided.",
                color=color,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            final_embed.set_footer(text=f"Diagnostic ID: {diag_id}")

        # Ensure Diagnostic ID is in footer if not present
        if final_embed.footer and final_embed.footer.text:
            if diag_id not in final_embed.footer.text:
                final_embed.set_footer(text=f"{final_embed.footer.text} • Diagnostic ID: {diag_id}")
        else:
            final_embed.set_footer(text=f"Diagnostic ID: {diag_id}")

        # --- 9. Deliver Message ---
        send_kwargs: Dict[str, Any] = {"embed": final_embed}
        if view is not None:
            send_kwargs["view"] = view

        try:
            sent_msg = await channel.send(**send_kwargs)
            cls._last_report_times[(guild_id, report_type)] = now
            cls._guild_report_timestamps[guild_id].append(now)

            if hasattr(bot, "db") and bot.db:
                try:
                    await bot.db.record_report_delivery(
                        event_id=diag_id,
                        channel_id=channel.id,
                        message_id=sent_msg.id,
                        status="DELIVERED",
                        error=None,
                    )
                except Exception as deliv_err:
                    logger.warning(f"Could not record report delivery in DB: {deliv_err}")

            logger.info(f"[REPORT_DELIVERED] Report ({diag_id}) sent to #{channel.name} in guild {guild_id}")
            return ReportResult(
                status=ReportStatus.SUCCESS,
                message="Report dispatched successfully",
                event_id=diag_id,
                message_id=sent_msg.id,
                channel_id=channel.id,
                occurrences=1,
                diagnostic_id=diag_id,
                is_updated=False,
            )
        except (discord.Forbidden, discord.HTTPException) as send_err:
            logger.error(f"[REPORT_SEND_FAILED] HTTP/Forbidden delivering report to #{channel.name}: {send_err}")
            if hasattr(bot, "db") and bot.db:
                try:
                    await bot.db.record_report_delivery(
                        event_id=diag_id,
                        channel_id=channel.id,
                        message_id=None,
                        status="FAILED",
                        error=str(send_err),
                    )
                except Exception:
                    pass
            return ReportResult(
                status=ReportStatus.ERROR,
                message=f"Discord delivery failed: {send_err}",
                event_id=diag_id,
                channel_id=channel.id,
                diagnostic_id=diag_id,
            )
        except Exception as e:
            logger.error(f"[REPORT_INTERNAL_ERROR] Unexpected error sending report: {e}", exc_info=True)
            return ReportResult(
                status=ReportStatus.ERROR,
                message=f"Internal report delivery error: {e}",
                event_id=diag_id,
                diagnostic_id=diag_id,
            )

    @classmethod
    def clear_cooldowns(cls, guild_id: Optional[int] = None) -> None:
        """Clear cached timestamps and cooldowns."""
        if guild_id is not None:
            keys_to_remove = [k for k in cls._last_report_times if k[0] == guild_id]
            for k in keys_to_remove:
                cls._last_report_times.pop(k, None)
            cls._guild_report_timestamps.pop(guild_id, None)
        else:
            cls._last_report_times.clear()
            cls._guild_report_timestamps.clear()
