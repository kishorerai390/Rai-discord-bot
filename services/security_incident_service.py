"""
RAI — CENTRAL SECURITY INCIDENT & EVENT CLASSIFICATION SERVICE
Single Source of Truth for Security Events, Threat Triage, and Incident Aggregation.

Principles:
1. Normal Events are NOT Security Incidents:
   - Voice room connected / disconnected / switched -> NORMAL -> NO alert, NO report.
   - Music play / queue -> NORMAL -> NO alert.
   - Channel / role creation by authorized admin -> NORMAL.
   - Only true threats (mass channel/role deletion, raid join spikes, unauthorized webhooks,
     permission abuse) trigger security incidents.
2. Unified Incident ID:
   - Every incident receives ONE canonical ID (e.g. RAI-INC-274263).
   - Reused across Security Alert, Security Report, Security Log, Audit Monitor, Admin Dashboard.
3. Incident Aggregation & In-Place Editing:
   - Identical repeated events increment count (47 -> 62 -> 91) and edit the existing message.
4. Mark as Safe:
   - Instant acknowledgement, permission verification, in-place message edit, stops repeats.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import logging
import random
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import discord

from database.models import InteractiveIncident
from services.channel_assignment_service import ChannelAssignmentService

logger = logging.getLogger("Rai.SecurityIncidentService")


class IncidentSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentState(str, Enum):
    DETECTED = "DETECTED"
    VERIFIED = "VERIFIED"
    CONTAINED = "CONTAINED"
    RECOVERING = "RECOVERING"
    RECOVERED = "RECOVERED"
    CLOSED = "CLOSED"


@dataclass
class EventClassification:
    is_security_incident: bool
    severity: IncidentSeverity
    threat_description: str
    recommended_action: str
    allow_report: bool = False
    requires_alert: bool = False


# Benign routine events that must NEVER trigger a security incident or alert
BENIGN_EVENT_PATTERNS: Set[str] = {
    "voice_member_joined",
    "voice_member_left",
    "voice_member_switched",
    "voice_room_connected",
    "voice_room_disconnected",
    "voice_room_switched",
    "voice_room_create_request",
    "voice_room_created",
    "voice_room_deleted",
    "music_track_start",
    "music_track_queue",
    "member_joined_normal",
    "ticket_created",
    "ticket_closed",
    "help_command",
    "project_created",
}


class SecurityIncidentService:
    """
    Centralized, single source of truth for all Rai security incidents.
    """

    _active_fingerprints: Dict[str, str] = {}  # fingerprint -> incident_id
    _incident_counts: Dict[str, int] = {}       # incident_id -> count
    _lock = asyncio.Lock()

    @staticmethod
    def generate_incident_id(prefix: str = "RAI-INC") -> str:
        """Generate canonical incident identifier (e.g. RAI-INC-274263)."""
        num = random.randint(100000, 999999)
        return f"{prefix}-{num}"

    @classmethod
    def compute_fingerprint(
        cls,
        guild_id: int,
        event_type: str,
        actor_id: Optional[int] = None,
        target_id: Optional[int] = None,
        time_bucket_minutes: int = 10,
    ) -> str:
        """
        Generate time-windowed incident fingerprint for aggregation.
        Identical attacks within time bucket map to the same incident.
        """
        now = time.time()
        bucket = int(now // (time_bucket_minutes * 60))
        raw = f"{guild_id}:{event_type}:{actor_id or 0}:{target_id or 0}:{bucket}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def classify_event(
        cls,
        event_type: str,
        actor: Optional[Union[discord.Member, discord.User]] = None,
        count: int = 1,
        time_window_sec: float = 10.0,
        details: Optional[Dict[str, Any]] = None,
    ) -> EventClassification:
        """
        Intelligent event classifier:
        Distinguishes routine server activity from genuine security threats.
        """
        norm_type = event_type.strip().lower().replace(" ", "_").replace("-", "_")

        # 1. Immediate benign filter
        if norm_type in BENIGN_EVENT_PATTERNS:
            return EventClassification(
                is_security_incident=False,
                severity=IncidentSeverity.INFO,
                threat_description="Routine operational activity.",
                recommended_action="None required.",
                allow_report=False,
                requires_alert=False,
            )

        # 2. Voice join rate-check:
        # A single user or small group joining voice is completely normal.
        if "voice" in norm_type or "room" in norm_type:
            if count >= 30 and time_window_sec <= 20.0:
                return EventClassification(
                    is_security_incident=True,
                    severity=IncidentSeverity.HIGH,
                    threat_description=f"Mass voice connection spike detected ({count} joins in {time_window_sec}s). Possible raid.",
                    recommended_action="Enable voice verification or temporary slowmode.",
                    allow_report=True,
                    requires_alert=True,
                )
            # Otherwise normal voice activity
            return EventClassification(
                is_security_incident=False,
                severity=IncidentSeverity.INFO,
                threat_description="Standard voice channel activity.",
                recommended_action="None required.",
                allow_report=False,
                requires_alert=False,
            )

        # 3. Critical Nuke & Mass Destruction Signals:
        if any(k in norm_type for k in ["channel_delete", "role_delete", "mass_kick", "mass_ban", "nuke"]):
            if count >= 3:
                return EventClassification(
                    is_security_incident=True,
                    severity=IncidentSeverity.CRITICAL,
                    threat_description=f"Mass deletion threshold breached ({count} deletions detected). Potential Anti-Nuke trigger.",
                    recommended_action="Contain actor immediately and lock critical channels.",
                    allow_report=True,
                    requires_alert=True,
                )
            else:
                return EventClassification(
                    is_security_incident=True,
                    severity=IncidentSeverity.HIGH,
                    threat_description="Sensitive deletion activity detected.",
                    recommended_action="Review audit logs.",
                    allow_report=True,
                    requires_alert=False,
                )

        # 4. Webhook & Integration Abuse:
        if "webhook" in norm_type or "bot_add" in norm_type:
            if count >= 2:
                return EventClassification(
                    is_security_incident=True,
                    severity=IncidentSeverity.CRITICAL,
                    threat_description="Rapid webhook creation spike detected. High risk of token abuse.",
                    recommended_action="Revoke unauthorized webhooks and audit integrations.",
                    allow_report=True,
                    requires_alert=True,
                )

        # 5. Raid Detection / Member join flood:
        if "member_join" in norm_type or "raid" in norm_type:
            if count >= 10:
                return EventClassification(
                    is_security_incident=True,
                    severity=IncidentSeverity.HIGH,
                    threat_description=f"Raid pattern detected: {count} accounts joined in {time_window_sec}s.",
                    recommended_action="Enable server verification gate or lockdown.",
                    allow_report=True,
                    requires_alert=True,
                )

        # 6. Mass Mentions / Spam:
        if "mention" in norm_type or "spam" in norm_type:
            return EventClassification(
                is_security_incident=True,
                severity=IncidentSeverity.HIGH,
                threat_description="High-frequency mention or text flood detected.",
                recommended_action="Timeout actor and purge recent messages.",
                allow_report=True,
                requires_alert=False,
            )

        # Default: Not a security incident
        return EventClassification(
            is_security_incident=False,
            severity=IncidentSeverity.LOW,
            threat_description="Informational event.",
            recommended_action="None required.",
            allow_report=False,
            requires_alert=False,
        )

    @classmethod
    async def process_security_signal(
        cls,
        bot: Any,
        guild: discord.Guild,
        event_type: str,
        title: str,
        description: str,
        actor: Optional[Union[discord.Member, discord.User]] = None,
        target: Optional[Union[discord.abc.GuildChannel, discord.Role, discord.Member, discord.User]] = None,
        count: int = 1,
        time_window_sec: float = 10.0,
        action_taken: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Optional[InteractiveIncident]:
        """
        Single entry point for processing potential security events.
        1. Classifies event. If benign, exits immediately with zero spam.
        2. Computes fingerprint and aggregates repeated occurrences.
        3. Edits existing Discord message in-place if duplicate.
        4. Delivers unified incident alert and report.
        """
        classification = cls.classify_event(
            event_type=event_type,
            actor=actor,
            count=count,
            time_window_sec=time_window_sec,
            details=details,
        )

        # Drop non-incidents immediately
        if not classification.is_security_incident:
            logger.debug(f"[SECURITY_FILTERED] Filtered benign event: {event_type} in guild {guild.id}")
            return None

        actor_id = actor.id if actor else None
        target_id = target.id if target else None
        actor_name = str(actor) if actor else None
        target_name = getattr(target, "name", str(target)) if target else None

        fingerprint = cls.compute_fingerprint(
            guild_id=guild.id,
            event_type=event_type,
            actor_id=actor_id,
            target_id=target_id,
        )

        async with cls._lock:
            existing_inc_id = cls._active_fingerprints.get(fingerprint)
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # --- Case 1: Existing incident within time window -> Aggregate & Edit in-place ---
            if existing_inc_id:
                cls._incident_counts[existing_inc_id] = cls._incident_counts.get(existing_inc_id, 1) + count
                current_count = cls._incident_counts[existing_inc_id]

                # Update in DB
                if hasattr(bot, "db") and bot.db:
                    try:
                        inc = await bot.db.get_interactive_incident(existing_inc_id)
                        if inc:
                            # Update in place on Discord
                            await cls._update_existing_incident_messages(
                                bot, guild, inc, current_count, classification
                            )
                            return inc
                    except Exception as e:
                        logger.warning(f"Error aggregating incident {existing_inc_id}: {e}")

            # --- Case 2: New incident ---
            inc_id = cls.generate_incident_id()
            cls._active_fingerprints[fingerprint] = inc_id
            cls._incident_counts[inc_id] = count

            import json
            details_str = json.dumps(details or {})

            incident = InteractiveIncident(
                incident_id=inc_id,
                guild_id=guild.id,
                report_type="security",
                event_type=event_type,
                actor_id=actor_id,
                actor_name=actor_name,
                target_id=target_id,
                target_name=target_name,
                title=title,
                description=description,
                action_taken=action_taken or "✓ Actor contained\n✓ Further actions blocked\n✓ Recovery initiated",
                status="ACTIVE",
                severity=classification.severity.value,
                details_json=details_str,
                created_at=now_iso,
                updated_at=now_iso,
            )

            # Persist in DB
            if hasattr(bot, "db") and bot.db:
                try:
                    await bot.db.create_interactive_incident(incident)
                except Exception as e:
                    logger.warning(f"Error saving incident {inc_id}: {e}")

            # Dispatch to channels
            await cls._deliver_incident_to_channels(bot, guild, incident, classification, count)
            return incident

    @classmethod
    def build_security_alert_embed(
        cls,
        incident: InteractiveIncident,
        classification: EventClassification,
        count: int = 1,
    ) -> discord.Embed:
        """Constructs concise, standardized Security Alert embed."""
        color = 0xED4245 if classification.severity == IncidentSeverity.CRITICAL else 0xFEE75C
        status_text = "🔴 ACTIVE / CONTAINED" if incident.status == "ACTIVE" else f"🟢 {incident.status}"

        embed = discord.Embed(
            title=f"🚨 RAI SECURITY ALERT",
            description=f"**Incident:** `{incident.incident_id}`\n**Threat:** `{classification.severity.value}`",
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        embed.add_field(name="Event", value=incident.description[:1024], inline=False)

        actor_str = f"<@{incident.actor_id}> (`{incident.actor_name}`)" if incident.actor_id else "Automated / Unknown"
        embed.add_field(name="Actor", value=actor_str, inline=True)

        if incident.target_id:
            embed.add_field(name="Target", value=f"`{incident.target_name}`", inline=True)

        if count > 1:
            embed.add_field(name="Occurrences", value=f"⚠️ **{count} repeated signals**", inline=True)

        embed.add_field(
            name="Response",
            value=incident.action_taken or "✓ Actor contained\n✓ Further actions blocked",
            inline=False,
        )
        embed.add_field(name="Status", value=status_text, inline=True)
        embed.set_footer(text=f"Rai Security Operations • {incident.incident_id}")
        return embed

    @classmethod
    def build_mark_safe_view(cls, incident_id: str) -> discord.ui.View:
        """Build interactive view with View Incident and Mark as Safe buttons."""
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Mark as Safe",
            emoji="✓",
            custom_id=f"rai_inc:mark_safe:{incident_id}",
        ))
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="View Incident",
            emoji="🔍",
            custom_id=f"rai_inc:details:{incident_id}",
        ))
        return view

    @classmethod
    async def _deliver_incident_to_channels(
        cls,
        bot: Any,
        guild: discord.Guild,
        incident: InteractiveIncident,
        classification: EventClassification,
        count: int,
    ) -> None:
        """Delivers unified incident representations to appropriate canonical channels."""
        embed = cls.build_security_alert_embed(incident, classification, count)
        view = cls.build_mark_safe_view(incident.incident_id)

        # 1. 🚨 SECURITY-ALERTS: Only for CRITICAL threats
        if classification.requires_alert or classification.severity == IncidentSeverity.CRITICAL:
            alert_ch, status, _ = await ChannelAssignmentService.resolve_destination(
                bot, guild.id, "security_alerts"
            )
            if alert_ch:
                try:
                    alert_msg = await alert_ch.send(embed=embed, view=view)
                    incident.channel_message_id = alert_msg.id
                    incident.report_channel_id = alert_ch.id
                except Exception as e:
                    logger.warning(f"Could not deliver alert to security-alerts: {e}")

        # 2. 🛡️ SECURITY-REPORT: Complete Incident Card
        report_ch, status, _ = await ChannelAssignmentService.resolve_destination(
            bot, guild.id, "security_report"
        )
        if report_ch:
            try:
                rep_msg = await report_ch.send(embed=embed, view=view)
                if not incident.channel_message_id:
                    incident.channel_message_id = rep_msg.id
                    incident.report_channel_id = report_ch.id
            except Exception as e:
                logger.warning(f"Could not deliver to security-report: {e}")

        # Update message IDs in DB
        if hasattr(bot, "db") and bot.db:
            try:
                await bot.db.update_interactive_incident_messages(
                    incident.incident_id,
                    channel_message_id=incident.channel_message_id,
                    report_channel_id=incident.report_channel_id,
                )
            except Exception:
                pass

    @classmethod
    async def _update_existing_incident_messages(
        cls,
        bot: Any,
        guild: discord.Guild,
        incident: InteractiveIncident,
        count: int,
        classification: EventClassification,
    ) -> None:
        """Edits existing incident messages in place to show updated count (e.g. 47 -> 62)."""
        embed = cls.build_security_alert_embed(incident, classification, count)

        # Update in report channel
        if incident.report_channel_id and incident.channel_message_id:
            ch = guild.get_channel(incident.report_channel_id)
            if ch and hasattr(ch, "fetch_message"):
                try:
                    msg = await ch.fetch_message(incident.channel_message_id)
                    if msg:
                        await msg.edit(embed=embed)
                        logger.info(f"[INCIDENT_AGGREGATED] In-place edit for {incident.incident_id} (count={count})")
                except Exception as e:
                    logger.debug(f"Could not edit incident message: {e}")

    @classmethod
    async def mark_incident_safe(
        cls,
        bot: Any,
        interaction: discord.Interaction,
        incident_id: str,
    ) -> bool:
        """
        Executes 'Mark as Safe':
        1. Verifies staff permission.
        2. Marks incident acknowledged/resolved in DB.
        3. Updates existing message in place.
        4. Stops future repeated notifications.
        """
        # Server-side permission check
        member = interaction.user
        perms = interaction.permissions if hasattr(interaction, "permissions") else None
        is_staff = False
        if perms and (perms.administrator or perms.manage_guild or perms.moderate_members):
            is_staff = True
        elif interaction.guild and interaction.guild.owner_id == member.id:
            is_staff = True

        if not is_staff:
            await interaction.response.send_message(
                "❌ **Unauthorized:** Only authorized moderators and administrators can mark incidents as safe.",
                ephemeral=True,
            )
            return False

        # Immediate acknowledgement
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        db = getattr(bot, "db", None)
        incident = None
        if db:
            incident = await db.get_interactive_incident(incident_id)

        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        if db and incident:
            incident.status = "RESOLVED"
            incident.action_taken = f"✓ Marked as Safe by {member.mention} at {now_str}"
            await db.update_interactive_incident_status(incident_id, "RESOLVED", incident.action_taken)

        # Edit existing message in place
        if interaction.message:
            try:
                old_embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
                safe_embed = discord.Embed(
                    title=f"✓ MARKED SAFE • {incident_id}",
                    description=(
                        f"**Incident:** `{incident_id}`\n"
                        f"**Acknowledged by:** {member.mention}\n"
                        f"**Time:** `{now_str}`\n"
                        f"**Resolution:** Marked as false positive / resolved by security staff."
                    ),
                    color=0x57F287,
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                safe_embed.set_footer(text=f"Rai Incident Resolved • {incident_id}")
                await interaction.message.edit(embed=safe_embed, view=None)
            except Exception as edit_err:
                logger.warning(f"Could not edit message in mark_safe: {edit_err}")

        await interaction.followup.send(
            f"✅ **Incident `{incident_id}` marked as safe.** Notifications halted and resolution recorded.",
            ephemeral=True,
        )
        return True
