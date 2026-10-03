"""
Confidential Owner Reports Engine for RAI.
Provides:
- Non-blocking asynchronous dual report dispatching to:
  1. 📩 Server Owner DM
  2. 📋 The Corresponding Private Report Channel under '📋 | RAI REPORTS'
- Formats clean Discord embeds with event, user, timestamp, reason, action, severity, and incident ID.
- Independent failure isolation: Failure in DM does not prevent channel delivery, and vice-versa.
- Duplicate prevention with sliding window TTL caching.
- Dynamic current server owner resolution via guild.owner_id.
- Auto-repair verification: Automatically recreates deleted report channels or category with strict owner-only permissions.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import random
import string
import time
import unicodedata
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
import discord

from config import Colors

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

OWNER_ID = 1457380609641938981
BOT_ID = 1554732669072445532

SMALL_CAPS_MAP: Dict[str, str] = {
    "ᴀ": "a", "ʙ": "b", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ꜰ": "f", "ɢ": "g", "ʜ": "h",
    "ɪ": "i", "ᴊ": "j", "ᴋ": "k", "ʟ": "l", "ᴍ": "m", "ɴ": "n", "ᴏ": "o", "ᴘ": "p",
    "ǫ": "q", "ʀ": "r", "ꜱ": "s", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w", "x": "x",
    "ʏ": "y", "ᴢ": "z",
}


def normalize_channel_name(name: str) -> str:
    """Normalizes channel names across styled unicode, math script, and small caps."""
    s = "".join(SMALL_CAPS_MAP.get(c, c) for c in str(name))
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-zA-Z0-9]", "", s).lower()


def generate_incident_id(prefix: str = "RAI-INC") -> str:
    """Generates standardized incident identifier: RAI-INC-XXXXXX."""
    num = "".join(random.choices(string.digits, k=6))
    return f"{prefix}-{num}"


class ReportDeduplicator:
    """Prevents duplicate reports from flooding DM or report channels within a sliding window."""
    _seen: Dict[str, float] = {}
    _ttl: float = 12.0  # seconds

    @classmethod
    def is_duplicate(cls, key: str) -> bool:
        now = time.monotonic()
        # Evict expired entries
        cls._seen = {k: ts for k, ts in cls._seen.items() if now - ts < cls._ttl}
        if key in cls._seen:
            return True
        cls._seen[key] = now
        if len(cls._seen) > 300:
            for old_k, _ in sorted(cls._seen.items(), key=lambda x: x[1])[:100]:
                cls._seen.pop(old_k, None)
        return False

    @classmethod
    def reset(cls) -> None:
        cls._seen.clear()
        IncidentAggregator.reset()


@dataclass
class AggregatedIncidentSession:
    correlation_key: str
    guild_id: int
    channel_key: str
    incident_id: str
    event_title: str
    color: int
    user_str: Optional[str]
    user_obj: Optional[discord.User | discord.Member]
    reasons: List[str]
    actions: List[str]
    details: Dict[str, Any]
    severity: str
    occurrences: int = 1
    channels_affected: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    last_dispatched: float = 0.0
    dispatched: bool = False
    resolved: bool = False
    debounce_task: Optional[asyncio.Task] = None
    update_task: Optional[asyncio.Task] = None
    dm_msg: Optional[discord.Message] = None
    ch_msg: Optional[discord.Message] = None
    bot: Optional[Any] = None
    guild: Optional[discord.Guild] = None
    view: Optional[discord.ui.View] = None
    attach_actions: bool = True
    force_dm: bool = False


class IncidentAggregator:
    """
    Gathers, aggregates, and debounces continuous security and moderation incidents.
    Prevents notification floods by gathering all forensic details across an attack window
    and reporting as a single consolidated summary. If subsequent events occur after initial
    dispatch, updates the existing report message in-place without generating new messages.
    """
    _sessions: Dict[str, AggregatedIncidentSession] = {}
    _debounce_seconds: float = 3.5
    _max_aggregation_seconds: float = 10.0
    _active_window_seconds: float = 60.0
    _lock = asyncio.Lock()

    SEVERITY_ORDER = {
        "LOW": 1,
        "MEDIUM": 2,
        "HIGH": 3,
        "CRITICAL": 4,
        "EMERGENCY": 5,
    }

    @classmethod
    def reset(cls) -> None:
        """Resets all active aggregation sessions and cancels pending tasks."""
        for s in cls._sessions.values():
            if s.debounce_task and not s.debounce_task.done():
                s.debounce_task.cancel()
            if s.update_task and not s.update_task.done():
                s.update_task.cancel()
        cls._sessions.clear()

    @classmethod
    def mark_resolved(cls, incident_id: str) -> None:
        """Marks any active aggregation session corresponding to this incident as resolved."""
        for s in cls._sessions.values():
            if s.incident_id == incident_id:
                s.resolved = True
                if s.debounce_task and not s.debounce_task.done():
                    s.debounce_task.cancel()
                if s.update_task and not s.update_task.done():
                    s.update_task.cancel()

    @classmethod
    def _extract_correlation_key(
        cls,
        guild_id: int,
        channel_key: str,
        embed: discord.Embed,
        incident_id: Optional[str] = None,
    ) -> Tuple[str, str, Optional[str], Optional[str], Optional[str], str, Dict[str, Any]]:
        """Extracts normalized event, target token, reason, action, severity, details from embed."""
        event_title = embed.title or "Incident Alert"
        severity = "HIGH"
        user_str = None
        reason = None
        action_taken = None
        details: Dict[str, Any] = {}

        import re
        for f in getattr(embed, "fields", []):
            fn = f.name.lower()
            if "📌" in f.name or "event" in fn:
                event_title = f.value.replace("*", "").strip()
            elif "severity" in fn:
                severity = f.value.replace("`", "").strip().upper()
            elif "target" in fn or "user" in fn:
                user_str = f.value
            elif "reason" in fn or "trigger" in fn:
                reason = f.value
            elif "action taken" in fn or "result" in fn:
                action_taken = f.value
            elif "incident id" not in fn:
                details[f.name] = f.value

        # Extract target token for correlation
        target_token = "general"
        if user_str:
            m = re.search(r"ID:\s*`?(\d+)`?", user_str)
            if m:
                target_token = m.group(1)
            else:
                target_token = user_str[:25]
        elif "Attacker" in details:
            m = re.search(r"\((\d+)\)", str(details["Attacker"]))
            if m:
                target_token = m.group(1)
            else:
                target_token = str(details["Attacker"])[:25]
        elif "Target ID" in details:
            target_token = str(details["Target ID"])[:25]

        # Normalize event name into threat category
        norm_event = event_title.lower()
        for pfx in ("🚨", "🛡️", "security alert:", "moderation sanction:", "system event:"):
            norm_event = norm_event.replace(pfx, "").strip()

        if any(w in norm_event for w in ("mention", "mass mention")):
            cat = "mention_spam"
        elif any(w in norm_event for w in ("raid", "mass join")):
            cat = "raid"
        elif any(w in norm_event for w in ("nuke", "channel delete", "role delete", "webhook abuse")):
            cat = "nuke"
        elif any(w in norm_event for w in ("spam", "message spam")):
            cat = "spam"
        else:
            cat = norm_event[:30]

        if incident_id and not incident_id.startswith("RAI-INC-"):
            corr_key = f"{guild_id}:{channel_key}:{incident_id}"
        else:
            corr_key = f"{guild_id}:{channel_key}:{cat}:{target_token}"

        return corr_key, event_title, user_str, reason, action_taken, severity, details

    @classmethod
    async def aggregate_report(
        cls,
        bot: SentinelBot,
        guild_id: int,
        channel_key: str,
        embed: discord.Embed,
        incident_id: Optional[str] = None,
        guild: Optional[discord.Guild] = None,
        incident: Optional[Any] = None,
        view: Optional[discord.ui.View] = None,
        attach_actions: bool = True,
        force_dm: bool = False,
        dispatch_func: Optional[Any] = None,
    ) -> None:
        """
        Coordinates incident aggregation:
        - If new incident: starts debounce aggregation window to collect burst details.
        - If ongoing burst: aggregates occurrences, reasons, channels, actions, and details.
        - If already dispatched: updates the existing report message in-place without spamming.
        """
        now = time.time()
        # Clean up old sessions
        expired = [k for k, s in cls._sessions.items() if now - s.last_updated > cls._active_window_seconds]
        for k in expired:
            cls._sessions.pop(k, None)

        corr_key, event_title, user_str, reason, action_taken, severity, details = cls._extract_correlation_key(
            guild_id, channel_key, embed, incident_id
        )

        session = cls._sessions.get(corr_key)

        # Scenario 1: New Incident Session
        if session is None or (now - session.last_updated > cls._active_window_seconds):
            inc_id = incident_id or generate_incident_id()
            session = AggregatedIncidentSession(
                correlation_key=corr_key,
                guild_id=guild_id,
                channel_key=channel_key,
                incident_id=inc_id,
                event_title=event_title,
                color=embed.color or Colors.WARNING,
                user_str=user_str,
                user_obj=None,
                reasons=[reason] if reason else [],
                actions=[action_taken] if action_taken else [],
                details=dict(details),
                severity=severity,
                occurrences=1,
                created_at=now,
                last_updated=now,
                bot=bot,
                guild=guild,
                view=view,
                attach_actions=attach_actions,
                force_dm=force_dm,
                dispatched=False,
            )
            cls._extract_channels_into_session(session, reason, details)
            cls._sessions[corr_key] = session

            # Start debounce timer to gather full detail before reporting
            session.debounce_task = asyncio.create_task(
                cls._debounce_dispatcher(session, dispatch_func)
            )
            return

        # If marked resolved, do not resurrect or edit
        if session.resolved:
            return

        # Scenario 2: Incident actively bursting (before initial dispatch)
        if not session.dispatched:
            session.occurrences += 1
            session.last_updated = now

            if reason and reason not in session.reasons:
                session.reasons.append(reason)
            if action_taken and action_taken not in session.actions:
                session.actions.append(action_taken)

            if cls.SEVERITY_ORDER.get(severity, 0) > cls.SEVERITY_ORDER.get(session.severity, 0):
                session.severity = severity
                session.color = embed.color or session.color

            cls._merge_details(session, details)
            cls._extract_channels_into_session(session, reason, details)

            # Reset debounce timer if within max aggregation window
            if now - session.created_at < cls._max_aggregation_seconds:
                if session.debounce_task and not session.debounce_task.done():
                    session.debounce_task.cancel()
                session.debounce_task = asyncio.create_task(
                    cls._debounce_dispatcher(session, dispatch_func)
                )
            return

        # Scenario 3: Incident continued after initial dispatch (update in-place)
        session.occurrences += 1
        session.last_updated = now
        if reason and reason not in session.reasons:
            session.reasons.append(reason)
        if action_taken and action_taken not in session.actions:
            session.actions.append(action_taken)

        if cls.SEVERITY_ORDER.get(severity, 0) > cls.SEVERITY_ORDER.get(session.severity, 0):
            session.severity = severity
            session.color = embed.color or session.color

        cls._merge_details(session, details)
        cls._extract_channels_into_session(session, reason, details)

        # Debounced in-place update
        if session.update_task and not session.update_task.done():
            session.update_task.cancel()
        session.update_task = asyncio.create_task(
            cls._update_dispatched_report_debounced(session)
        )

    @classmethod
    def _extract_channels_into_session(
        cls,
        session: AggregatedIncidentSession,
        reason: Optional[str],
        details: Dict[str, Any],
    ) -> None:
        """Extracts channel mentions or names into session.channels_affected."""
        import re
        text_to_check = f"{reason or ''} {details.get('Channels', '')} {details.get('Channel', '')} {details.get('Channels Affected', '')}"
        ch_matches = re.findall(r"<#(\d+)>|#([a-zA-Z0-9_\-]+)", text_to_check)
        for num_id, ch_name in ch_matches:
            if num_id:
                session.channels_affected.add(f"<#{num_id}>")
            elif ch_name:
                session.channels_affected.add(f"#{ch_name}")

    @classmethod
    def _merge_details(cls, session: AggregatedIncidentSession, new_details: Dict[str, Any]) -> None:
        """Merges forensic detail fields, summing numeric counts where applicable."""
        for k, v in new_details.items():
            if k in ("Total Mentions", "Mentions", "Messages"):
                try:
                    curr_val = int(session.details.get(k, 0))
                    add_val = int(v)
                    session.details[k] = curr_val + add_val
                except Exception:
                    session.details[k] = v
            elif k not in session.details:
                session.details[k] = v

    @classmethod
    async def _debounce_dispatcher(
        cls,
        session: AggregatedIncidentSession,
        dispatch_func: Any,
    ) -> None:
        """Waits for debounce silence window, then builds and dispatches the consolidated report."""
        try:
            await asyncio.sleep(cls._debounce_seconds)
        except asyncio.CancelledError:
            return

        if session.resolved:
            return

        consolidated_embed = cls._build_consolidated_embed(session)

        try:
            if dispatch_func:
                await dispatch_func(
                    bot=session.bot,
                    guild_id=session.guild_id,
                    channel_key=session.channel_key,
                    embed=consolidated_embed,
                    incident_id=session.incident_id,
                    guild=session.guild,
                    bypass_dedup=True,
                    view=session.view,
                    attach_actions=session.attach_actions,
                    force_dm=session.force_dm,
                )
                session.dispatched = True
                session.last_dispatched = time.time()

                # Fetch dispatched messages for subsequent in-place updates
                msgs = OwnerReporter._last_dispatched_messages.get(session.incident_id)
                if msgs:
                    session.dm_msg, session.ch_msg = msgs
                logger.info(
                    f"[INCIDENT_AGGREGATOR] Consolidated report dispatched for {session.incident_id} "
                    f"({session.occurrences} events aggregated)"
                )
        except Exception as e:
            logger.error(f"[INCIDENT_AGGREGATOR_FAIL] Could not dispatch aggregated report: {e}", exc_info=True)

    @classmethod
    async def _update_dispatched_report_debounced(
        cls,
        session: AggregatedIncidentSession,
    ) -> None:
        """Updates the existing DM and Channel messages in-place with gathered details."""
        try:
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            return

        if session.resolved:
            return

        # Retrieve messages if not yet loaded
        if not session.dm_msg and not session.ch_msg:
            msgs = OwnerReporter._last_dispatched_messages.get(session.incident_id)
            if msgs:
                session.dm_msg, session.ch_msg = msgs

        # Fallback fetch from DB if needed
        if not session.dm_msg and not session.ch_msg and session.bot and hasattr(session.bot, "db"):
            try:
                rec = await session.bot.db.get_interactive_incident(session.incident_id)
                if rec:
                    if rec.dm_channel_id and rec.dm_message_id:
                        ch = session.bot.get_channel(rec.dm_channel_id)
                        if ch and hasattr(ch, "fetch_message"):
                            session.dm_msg = await ch.fetch_message(rec.dm_message_id)
                    if rec.report_channel_id and rec.channel_message_id:
                        ch = session.bot.get_channel(rec.report_channel_id)
                        if ch and hasattr(ch, "fetch_message"):
                            session.ch_msg = await ch.fetch_message(rec.channel_message_id)
            except Exception as e:
                logger.debug(f"Incident fetch for update note: {e}")

        updated_embed = cls._build_consolidated_embed(session)

        # Update DM message in-place
        if session.dm_msg and hasattr(session.dm_msg, "edit"):
            try:
                await session.dm_msg.edit(embed=updated_embed)
                logger.debug(f"[INCIDENT_UPDATE] Updated DM report {session.incident_id} in-place")
            except Exception as e:
                logger.debug(f"[INCIDENT_UPDATE_DM_FAIL] Could not edit DM message: {e}")

        # Update Channel message in-place
        if session.ch_msg and hasattr(session.ch_msg, "edit"):
            try:
                await session.ch_msg.edit(embed=updated_embed)
                logger.debug(f"[INCIDENT_UPDATE] Updated Channel report {session.incident_id} in-place")
            except Exception as e:
                logger.debug(f"[INCIDENT_UPDATE_CH_FAIL] Could not edit Channel message: {e}")

        # Update SQLite interactive incident record with aggregated details
        if session.bot and hasattr(session.bot, "db") and hasattr(session.bot.db, "update_interactive_incident_status"):
            try:
                full_note = ", ".join(session.actions) or "Mitigated"
                if session.occurrences > 1:
                    full_note += f" (Aggregated: {session.occurrences} events)"
                await session.bot.db.update_interactive_incident_status(session.incident_id, "ACTIVE", full_note)
            except Exception:
                pass

    @classmethod
    def _build_consolidated_embed(cls, session: AggregatedIncidentSession) -> discord.Embed:
        """Constructs rich consolidated Discord Embed containing all gathered incident details."""
        if session.occurrences > 1:
            title = f"🚨 Security Alert: {session.event_title} (Aggregated Summary)"
        else:
            title = f"🚨 Security Alert: {session.event_title}"

        embed = discord.Embed(
            title=title,
            color=session.color,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        event_val = f"**{session.event_title}**"
        if session.occurrences > 1:
            event_val += f"\n*(Aggregated: **{session.occurrences}** incident bursts gathered)*"
        embed.add_field(name="📌 Event / Action", value=event_val, inline=False)
        embed.add_field(name="🆔 Incident ID", value=f"`{session.incident_id}`", inline=True)
        embed.add_field(name="⚡ Severity", value=f"`{session.severity}`", inline=True)

        if session.user_str:
            embed.add_field(name="👤 Target / User", value=session.user_str, inline=True)

        # Consolidated reasons
        if session.reasons:
            if len(session.reasons) == 1:
                reason_text = session.reasons[0]
            else:
                reason_text = "\n".join([f"• {r}" for r in session.reasons[-5:]])
            embed.add_field(name="📝 Reason / Trigger (Consolidated)", value=reason_text[:1024], inline=False)

        # Consolidated actions taken
        if session.actions:
            if len(session.actions) == 1:
                action_text = session.actions[0]
            else:
                action_text = "\n".join([f"• {a}" for a in session.actions[-5:]])
            embed.add_field(name="🛡️ Action Taken / Result (Consolidated)", value=action_text[:1024], inline=False)

        # Aggregated Metrics
        if session.occurrences > 1:
            embed.add_field(name="📊 Incident Bursts", value=f"`{session.occurrences}` events gathered across window", inline=True)

        if session.channels_affected:
            channels_str = ", ".join(sorted(list(session.channels_affected))[:6])
            if len(session.channels_affected) > 6:
                channels_str += f" (+{len(session.channels_affected) - 6} more)"
            embed.add_field(name="📍 Channels Affected", value=channels_str[:1024], inline=True)

        # Other forensic details
        for k, v in session.details.items():
            if k not in ("Incident", "incident_id", "Channels", "Channel", "Channels Affected", "Target ID"):
                embed.add_field(name=k, value=str(v)[:1024], inline=True if len(str(v)) < 30 else False)

        footer_text = f"Confidential Owner Report • {session.incident_id} • RAI FAM💗"
        if session.occurrences > 1:
            footer_text += f" • {session.occurrences} events aggregated"
        embed.set_footer(text=footer_text)

        return embed


class OwnerReporter:
    """Asynchronous Confidential Dual Report Dispatcher."""
    _last_dispatched_messages: Dict[str, Tuple[Optional[discord.Message], Optional[discord.Message]]] = {}

    @staticmethod
    def _create_report_embed(
        title: str,
        color: int,
        event: str,
        user: Optional[discord.User | discord.Member] = None,
        reason: Optional[str] = None,
        action_taken: Optional[str] = None,
        severity: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        incident_id: Optional[str] = None,
    ) -> discord.Embed:
        inc_id = incident_id or (details.get("Incident") if details else None) or generate_incident_id()
        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="📌 Event / Action", value=f"**{event}**", inline=False)

        if inc_id:
            embed.add_field(name="🆔 Incident ID", value=f"`{inc_id}`", inline=True)

        if severity:
            embed.add_field(name="⚡ Severity", value=f"`{severity}`", inline=True)

        if user:
            embed.add_field(
                name="👤 Target / User",
                value=f"{user.mention} (`{user.name}` | ID: `{user.id}`)",
                inline=True,
            )

        if reason:
            embed.add_field(name="📝 Reason / Trigger", value=reason, inline=False)

        if action_taken:
            embed.add_field(name="🛡️ Action Taken / Result", value=action_taken, inline=False)

        if details:
            for k, v in details.items():
                if v and k not in ("Incident", "incident_id"):
                    embed.add_field(name=k, value=str(v)[:1024], inline=False)

        embed.set_footer(text=f"Confidential Owner Report • {inc_id} • RAI FAM💗")
        return embed

    REPORT_CHANNEL_KEYS = {
        "security_report_id": "security",
        "mod_report_id": "mod",
        "music_report_id": "music",
        "room_report_id": "room",
        "bot_report_id": "bot",
        "system_report_id": "system",
    }

    CHANNEL_TARGETS = {
        "system_report_id": ["system-report", "system_report", "system-health", "system-log"],
        "room_report_id": ["room-report", "room_report", "room-control", "voice-log"],
        "bot_report_id": ["bot-report", "bot_report", "bot-config", "bot-log", "admin-operations"],
        "music_report_id": ["music-report", "music_report", "music-control"],
        "mod_report_id": ["mod-report", "mod_report", "mod-log"],
        "security_report_id": ["security-report", "security_report", "security-alerts", "security-log", "alerts"],
    }

    @classmethod
    async def _dispatch_dual_report_async(
        cls,
        bot: SentinelBot,
        guild_id: int,
        channel_key: str,
        embed: discord.Embed,
        incident_id: Optional[str] = None,
        guild: Optional[discord.Guild] = None,
        bypass_dedup: bool = False,
        incident: Optional[Any] = None,
        view: Optional[discord.ui.View] = None,
        attach_actions: bool = False,
        force_dm: bool = False,
    ) -> Tuple[bool, bool]:
        """
        Asynchronously delivers the report to BOTH:
        1. 📩 Server Owner DM
        2. 📋 Corresponding Private Report Channel under '📋 | RAI REPORTS'

        Returns:
            Tuple[bool, bool]: (dm_success, channel_success)
        """
        # Deduplication check
        inc_tag = incident_id or (embed.footer.text if embed.footer else None) or embed.title or "report"
        dedup_key = f"{guild_id}:{channel_key}:{inc_tag}"
        if not bypass_dedup and ReportDeduplicator.is_duplicate(dedup_key):
            logger.debug(f"[REPORT_DEDUP] Duplicate report suppressed for guild {guild_id}, channel {channel_key}: {inc_tag}")
            return (True, True)

        guild_obj = guild
        if not guild_obj and hasattr(bot, "get_guild"):
            guild_obj = bot.get_guild(guild_id)
        if not guild_obj and hasattr(bot, "fetch_guild"):
            try:
                guild_obj = await bot.fetch_guild(guild_id)
            except Exception:
                guild_obj = None

        dm_success = False
        channel_success = False
        dm_msg = None
        ch_msg = None

        # Resolve interactive incident and action button views
        dm_view = view
        ch_view = view
        if (attach_actions or incident is not None) and incident_id:
            try:
                from utils.interactive_incidents import InteractiveIncidentManager
                from database.models import InteractiveIncident
                if not incident:
                    rep_type = cls.REPORT_CHANNEL_KEYS.get(channel_key, "security")
                    actor_id = None
                    actor_name = None
                    target_id = None
                    target_name = None
                    action_taken_val = None
                    severity_val = "HIGH"
                    event_title = embed.title or "Incident Alert"
                    description_val = "Incident alert logged."

                    import re
                    for f in getattr(embed, "fields", []):
                        fn = f.name.lower()
                        if "📌" in f.name or "event" in fn:
                            event_title = f.value.replace("*", "")
                        elif "severity" in fn:
                            severity_val = f.value.replace("`", "")
                        elif "target" in fn or "user" in fn:
                            match = re.search(r"ID:\s*`?(\d+)`?", f.value)
                            if match:
                                target_id = int(match.group(1))
                            name_match = re.search(r"`([^`]+)`", f.value)
                            if name_match:
                                target_name = name_match.group(1)
                        elif "actor" in fn or "executor" in fn or "moderator" in fn:
                            match = re.search(r"ID:\s*`?(\d+)`?", f.value)
                            if match:
                                actor_id = int(match.group(1))
                            name_match = re.search(r"`([^`]+)`", f.value)
                            if name_match:
                                actor_name = name_match.group(1)
                        elif "room id" in fn:
                            match = re.search(r"`?(\d+)`?", f.value)
                            if match:
                                target_id = int(match.group(1))
                        elif "reason" in fn or "trigger" in fn:
                            description_val = f.value
                        elif "action taken" in fn or "result" in fn:
                            action_taken_val = f.value

                    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    incident = InteractiveIncident(
                        incident_id=incident_id,
                        guild_id=guild_id,
                        report_type=rep_type,
                        event_type=event_title,
                        title=embed.title or f"{rep_type.upper()} Incident",
                        description=description_val,
                        actor_id=actor_id or target_id,
                        actor_name=actor_name or target_name,
                        target_id=target_id or actor_id,
                        target_name=target_name or actor_name,
                        action_taken=action_taken_val,
                        status="ACTIVE",
                        severity=severity_val,
                        created_at=now_iso,
                        updated_at=now_iso,
                    )

                if hasattr(bot, "db") and bot.db and hasattr(bot.db, "create_interactive_incident"):
                    await bot.db.create_interactive_incident(incident)

                if dm_view is None:
                    dm_view = InteractiveIncidentManager.build_incident_view(incident)
                if ch_view is None:
                    ch_view = InteractiveIncidentManager.build_incident_view(incident)
            except Exception as inc_err:
                logger.warning(f"Interactive incident init note: {inc_err}")

        # ==========================================
        # DESTINATION 1: 📋 PRIVATE SERVER REPORT CHANNEL
        # ==========================================
        channel = None
        try:
            cfg = None
            if hasattr(bot, "db") and bot.db and hasattr(bot.db, "get_owner_reports_config"):
                try:
                    cfg = await bot.db.get_owner_reports_config(guild_id)
                except Exception:
                    cfg = None

            ch_id = getattr(cfg, channel_key, None) if cfg else None

            if ch_id:
                if guild_obj:
                    channel = guild_obj.get_channel(ch_id)
                if not channel and hasattr(bot, "get_channel"):
                    channel = bot.get_channel(ch_id)
                if not channel and hasattr(bot, "fetch_channel"):
                    try:
                        channel = await bot.fetch_channel(ch_id)
                    except Exception:
                        channel = None

            # Fallback for existing or styled channels in guild
            if (not channel or not isinstance(channel, discord.TextChannel)) and guild_obj and hasattr(guild_obj, "text_channels") and guild_obj.text_channels:
                key_targets = cls.CHANNEL_TARGETS.get(channel_key, [])
                norm_key = channel_key.replace("_id", "").replace("_report", "")
                target_tokens = [norm_key] + [t.replace("-", "").replace("_", "") for t in key_targets]

                for ch in guild_obj.text_channels:
                    cname = getattr(ch, "name", "")
                    cnorm = normalize_channel_name(cname)
                    if any(t in cnorm for t in target_tokens):
                        channel = ch
                        if hasattr(bot, "db") and bot.db and hasattr(bot.db, "update_owner_reports_config"):
                            try:
                                await bot.db.update_owner_reports_config(guild_id, **{channel_key: ch.id})
                            except Exception:
                                pass
                        break

                # Legacy/general fallback
                if not channel or not isinstance(channel, discord.TextChannel):
                    for ch in guild_obj.text_channels:
                        cname = getattr(ch, "name", "").lower()
                        if any(target in cname for target in ("security-report", "security-log", "alerts", "mod-report", "mod-log", "bot-report", "bot-log", "room-report", "system-report", "general")):
                            channel = ch
                            break

            # Auto-repair / ensure channel if missing or deleted
            has_owner_setup = bool(cfg and (getattr(cfg, "category_id", None) or getattr(cfg, "security_report_id", None)))
            should_auto_repair = bool(getattr(cfg, "auto_repair", True) if cfg else True)
            if (not channel or not isinstance(channel, discord.TextChannel)) and should_auto_repair and guild_obj:
                try:
                    channel = await cls.repair_missing_channel(bot, guild_obj, channel_key)
                except Exception as rep_err:
                    logger.warning(f"Auto-repair attempt failed for {channel_key}: {rep_err}")

            if channel and hasattr(channel, "send"):
                send_kwargs = {"embed": embed}
                if ch_view is not None:
                    send_kwargs["view"] = ch_view
                ch_send_res = channel.send(**send_kwargs)
                if asyncio.iscoroutine(ch_send_res) or hasattr(ch_send_res, "__await__"):
                    ch_msg = await ch_send_res
                else:
                    ch_msg = ch_send_res
                channel_success = True
                ch_name = getattr(channel, "name", str(channel))
                ch_id_val = getattr(channel, "id", "unknown")
                logger.info(f"[OWNER_REPORT_CHANNEL_SUCCESS] Delivered report ({inc_tag}) to #{ch_name} ({ch_id_val})")
            else:
                logger.warning(f"[OWNER_REPORT_CHANNEL_UNAVAILABLE] Private report channel {channel_key} not resolved in guild {guild_id}")
        except (discord.Forbidden, discord.HTTPException) as ch_err:
            logger.warning(f"[OWNER_REPORT_CHANNEL_FAILED] Could not send to report channel {channel_key}: {ch_err}")
        except Exception as e:
            logger.error(f"[OWNER_REPORT_CHANNEL_ERROR] Unexpected error sending to report channel {channel_key}: {e}", exc_info=True)

        # ==========================================
        # DESTINATION 2: 📩 SERVER OWNER DM
        # ==========================================
        # Send to Owner DM if explicitly requested (force_dm) OR as safety fallback if server channel failed
        if force_dm or not channel_success:
            owner_id = None
            try:
                if guild_obj:
                    owner_id = getattr(guild_obj, "owner_id", None)
                if not owner_id and hasattr(bot, "db") and bot.db:
                    try:
                        owner_id = await bot.db.get_founder_dm_recipient(guild_id)
                    except Exception:
                        owner_id = None
                if not owner_id:
                    owner_id = OWNER_ID

                owner = bot.get_user(owner_id) if hasattr(bot, "get_user") else None
                if not owner and hasattr(bot, "fetch_user"):
                    try:
                        owner = await bot.fetch_user(owner_id)
                    except Exception:
                        owner = None

                is_bot = (getattr(owner, "bot", False) is True)
                if owner and not is_bot:
                    send_fn = getattr(owner, "send", None)
                    if send_fn:
                        send_kwargs = {"embed": embed}
                        if dm_view is not None:
                            send_kwargs["view"] = dm_view
                        res = send_fn(**send_kwargs)
                        if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                            dm_msg = await res
                        else:
                            dm_msg = res
                        dm_success = True
                        logger.info(f"[OWNER_REPORT_DM_SUCCESS] Delivered report ({inc_tag}) to owner {owner_id}")
                else:
                    logger.warning(f"[OWNER_REPORT_DM_UNREACHABLE] Owner user {owner_id} unreachable or is a bot.")
            except (discord.Forbidden, discord.HTTPException) as dm_err:
                logger.warning(f"[OWNER_REPORT_DM_FAILED] Could not DM current owner ({owner_id}): {dm_err}")
            except Exception as e:
                logger.error(f"[OWNER_REPORT_DM_ERROR] Unexpected error sending DM to owner ({owner_id}): {e}", exc_info=True)
        else:
            logger.debug(f"[OWNER_REPORT_DM_SUPPRESSED] Report delivered to server channel, suppressing DM ({inc_tag})")

        # DESTINATION 3: 🚨 SECURITY ALERTS (for security incidents)
        if channel_key == "security_report_id" and hasattr(bot, "db") and bot.db:
            try:
                p_cfg = None
                if hasattr(bot.db, "get_private_control_config"):
                    p_cfg = await bot.db.get_private_control_config(guild_id)
                alerts_ch_id = getattr(p_cfg, "security_alerts_id", None)
                if alerts_ch_id and alerts_ch_id != getattr(channel, "id", None):
                    alerts_ch = guild_obj.get_channel(alerts_ch_id) if guild_obj else None
                    if not alerts_ch and hasattr(bot, "get_channel"):
                        alerts_ch = bot.get_channel(alerts_ch_id)
                    if alerts_ch and hasattr(alerts_ch, "send"):
                        a_kwargs = {"embed": embed}
                        if ch_view is not None:
                            a_kwargs["view"] = ch_view
                        a_res = alerts_ch.send(**a_kwargs)
                        if asyncio.iscoroutine(a_res) or hasattr(a_res, "__await__"):
                            await a_res
                        logger.info(f"[SECURITY_ALERTS_SUCCESS] Mirrored incident ({inc_tag}) to #security-alerts ({alerts_ch_id})")
            except Exception as e:
                logger.debug(f"Note: Could not mirror to security-alerts: {e}")

        # Update database with message IDs for synchronization
        if incident and hasattr(bot, "db") and bot.db:
            raw_dm_id = getattr(dm_msg, "id", None) if dm_success and dm_msg else None
            dm_msg_id = raw_dm_id if isinstance(raw_dm_id, int) else None

            raw_dm_ch_id = getattr(getattr(dm_msg, "channel", None), "id", None) if dm_success and dm_msg else None
            dm_ch_id = raw_dm_ch_id if isinstance(raw_dm_ch_id, int) else None

            raw_ch_id = getattr(ch_msg, "id", None) if channel_success and ch_msg else None
            ch_msg_id = raw_ch_id if isinstance(raw_ch_id, int) else None

            raw_rep_ch_id = getattr(channel, "id", None) if channel_success and channel else None
            rep_ch_id = raw_rep_ch_id if isinstance(raw_rep_ch_id, int) else None

            incident.dm_message_id = dm_msg_id
            incident.dm_channel_id = dm_ch_id
            incident.channel_message_id = ch_msg_id
            incident.report_channel_id = rep_ch_id

            if hasattr(bot.db, "update_interactive_incident_messages"):
                try:
                    await bot.db.update_interactive_incident_messages(
                        incident_id=incident.incident_id,
                        dm_message_id=dm_msg_id,
                        dm_channel_id=dm_ch_id,
                        channel_message_id=ch_msg_id,
                        report_channel_id=rep_ch_id,
                    )
                except Exception as update_err:
                    logger.debug(f"Failed to record incident message IDs: {update_err}")

        # Record dispatched messages for potential subsequent in-place updates by IncidentAggregator
        eff_inc_id = incident_id or (incident.incident_id if incident else None)
        if eff_inc_id:
            cls._last_dispatched_messages[eff_inc_id] = (dm_msg, ch_msg)

        return (dm_success, channel_success)

    @classmethod
    async def _dispatch_async(
        cls,
        bot: SentinelBot,
        guild_id: int,
        channel_key: str,
        embed: discord.Embed,
        incident_id: Optional[str] = None,
        guild: Optional[discord.Guild] = None,
        bypass_dedup: bool = False,
        force_dm: bool = False,
    ) -> None:
        """Internal asynchronous delivery ensuring channel and optional DM receive the report."""
        await cls._dispatch_dual_report_async(
            bot, guild_id, channel_key, embed, incident_id, guild=guild, bypass_dedup=bypass_dedup, force_dm=force_dm
        )

    @classmethod
    def dispatch_report(
        cls,
        bot: SentinelBot,
        guild_id: int,
        channel_key: str,
        embed: discord.Embed,
        incident_id: Optional[str] = None,
        guild: Optional[discord.Guild] = None,
        bypass_dedup: bool = False,
        incident: Optional[Any] = None,
        view: Optional[discord.ui.View] = None,
        attach_actions: bool = True,
        force_dm: bool = False,
    ) -> None:
        """Public non-blocking entry point delivering to private report channel and optional owner DM."""
        if bypass_dedup:
            asyncio.create_task(
                cls._dispatch_dual_report_async(
                    bot,
                    guild_id,
                    channel_key,
                    embed,
                    incident_id=incident_id,
                    guild=guild,
                    bypass_dedup=bypass_dedup,
                    incident=incident,
                    view=view,
                    attach_actions=attach_actions,
                    force_dm=force_dm,
                )
            )
        else:
            asyncio.create_task(
                IncidentAggregator.aggregate_report(
                    bot=bot,
                    guild_id=guild_id,
                    channel_key=channel_key,
                    embed=embed,
                    incident_id=incident_id,
                    guild=guild,
                    incident=incident,
                    view=view,
                    attach_actions=attach_actions,
                    force_dm=force_dm,
                    dispatch_func=cls._dispatch_dual_report_async,
                )
            )

    @classmethod
    async def _report_to_owner_async(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        embed: discord.Embed,
        fallback_channel_key: str = "security_report_id",
        incident_id: Optional[str] = None,
        bypass_dedup: bool = True,
        attach_actions: bool = True,
    ) -> Tuple[bool, str]:
        """
        Dynamically notifies CURRENT server owner (guild.owner_id) AND private server report channel.
        Maintains complete failure isolation:
        - If DM fails -> still sends to report channel (fallback).
        - If channel delivery fails -> still sends DM.
        """
        dm_ok, ch_ok = await cls._dispatch_dual_report_async(
            bot=bot,
            guild_id=guild.id,
            channel_key=fallback_channel_key,
            embed=embed,
            incident_id=incident_id,
            guild=guild,
            bypass_dedup=bypass_dedup,
            attach_actions=attach_actions,
        )

        if dm_ok and ch_ok:
            return True, "Delivered via Direct Message and private report channel"
        elif dm_ok and not ch_ok:
            return True, "Delivered via Direct Message"
        elif not dm_ok and ch_ok:
            return True, "Delivered via channel fallback"
        else:
            return False, "Failed to deliver to owner DM and private report channel"

    @classmethod
    async def report_to_current_server_owner(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        embed: Optional[discord.Embed] = None,
        event_title: Optional[str] = None,
        incident_id: Optional[str] = None,
        severity: str = "HIGH",
        details: Optional[Dict[str, Any]] = None,
        fallback_channel_key: str = "security_report_id",
    ) -> Tuple[bool, str]:
        """Public entry point for dynamic current server owner dual reporting."""
        inc_id = incident_id or generate_incident_id()
        if embed is None:
            embed = cls._create_report_embed(
                title=f"🚨 {event_title or 'Security Alert'}",
                color=Colors.ERROR if severity in ("CRITICAL", "EMERGENCY") else Colors.WARNING,
                event=event_title or "Security Intelligence Event",
                severity=severity,
                reason=f"Automated incident alert {inc_id}",
                action_taken="Immediate mitigation and quarantine engaged",
                details=details or {},
                incident_id=inc_id,
            )
        return await cls._report_to_owner_async(bot, guild, embed, fallback_channel_key, incident_id=inc_id)

    @classmethod
    def dispatch_to_current_server_owner(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        embed: discord.Embed,
        fallback_channel_key: str = "security_report_id",
        incident_id: Optional[str] = None,
    ) -> None:
        """Public non-blocking entry point for dynamic current server owner dual reporting."""
        asyncio.create_task(cls._report_to_owner_async(bot, guild, embed, fallback_channel_key, incident_id))

    # ==========================================
    # SPECIALIZED REPORT ROUTERS
    # ==========================================

    @classmethod
    def send_security_report(
        cls,
        bot: SentinelBot,
        guild_id: int,
        event: str,
        user: Optional[discord.User | discord.Member] = None,
        reason: Optional[str] = None,
        action_taken: Optional[str] = None,
        severity: str = "HIGH",
        details: Optional[Dict[str, Any]] = None,
        incident_id: Optional[str] = None,
    ) -> None:
        """Route to 📩 Owner DM AND 📋 🚨・security-report."""
        color = Colors.ERROR if severity in ("HIGH", "CRITICAL", "EMERGENCY") else Colors.WARNING
        inc_id = incident_id or (details.get("Incident") if details else None) or generate_incident_id()
        embed = cls._create_report_embed(
            title=f"🚨 Security Alert: {event}",
            color=color,
            event=event,
            user=user,
            reason=reason,
            action_taken=action_taken,
            severity=severity,
            details=details,
            incident_id=inc_id,
        )
        cls.dispatch_report(bot, guild_id, "security_report_id", embed, incident_id=inc_id)

    @classmethod
    def send_mod_report(
        cls,
        bot: SentinelBot,
        guild_id: int,
        event: str,
        user: Optional[discord.User | discord.Member] = None,
        moderator: Optional[discord.User | discord.Member] = None,
        reason: Optional[str] = None,
        action_taken: Optional[str] = None,
        severity: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        incident_id: Optional[str] = None,
    ) -> None:
        """Route to 📩 Owner DM AND 📋 🛡️・mod-report."""
        all_details = dict(details or {})
        if moderator:
            all_details["👮 Moderator / Enforcer"] = f"{moderator.mention} (`{moderator.name}`)"
        inc_id = incident_id or (details.get("Incident") if details else None) or generate_incident_id()

        embed = cls._create_report_embed(
            title=f"🛡️ Moderation Sanction: {event}",
            color=Colors.PRIMARY,
            event=event,
            user=user,
            reason=reason,
            action_taken=action_taken,
            severity=severity,
            details=all_details,
            incident_id=inc_id,
        )
        cls.dispatch_report(bot, guild_id, "mod_report_id", embed, incident_id=inc_id)

    @classmethod
    def send_music_report(
        cls,
        bot: SentinelBot,
        guild_id: int,
        event: str,
        user: Optional[discord.User | discord.Member] = None,
        reason: Optional[str] = None,
        action_taken: Optional[str] = None,
        severity: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        incident_id: Optional[str] = None,
    ) -> None:
        """Route to 📩 Owner DM AND 📋 🎵・music-report."""
        inc_id = incident_id or (details.get("Incident") if details else None) or generate_incident_id()
        embed = cls._create_report_embed(
            title=f"🎵 Audio Telemetry: {event}",
            color=0x9B59B6,
            event=event,
            user=user,
            reason=reason,
            action_taken=action_taken,
            severity=severity,
            details=details,
            incident_id=inc_id,
        )
        cls.dispatch_report(bot, guild_id, "music_report_id", embed, incident_id=inc_id)

    @classmethod
    def send_room_report(
        cls,
        bot: SentinelBot,
        guild_id: int,
        event: str,
        user: Optional[discord.User | discord.Member] = None,
        action_taken: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        incident_id: Optional[str] = None,
    ) -> None:
        """Route to 📩 Owner DM AND 📋 🔐・room-report."""
        inc_id = incident_id or (details.get("Incident") if details else None) or generate_incident_id()
        embed = cls._create_report_embed(
            title=f"🔐 Voice Suite Lifecycle: {event}",
            color=0x1ABC9C,
            event=event,
            user=user,
            action_taken=action_taken,
            details=details,
            incident_id=inc_id,
        )
        cls.dispatch_report(bot, guild_id, "room_report_id", embed, incident_id=inc_id)

    @classmethod
    def send_bot_report(
        cls,
        bot: SentinelBot,
        guild_id: int,
        event: str,
        executor: Optional[discord.User | discord.Member] = None,
        action_taken: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        incident_id: Optional[str] = None,
    ) -> None:
        """Route to 📩 Owner DM AND 📋 🤖・bot-report."""
        all_details = dict(details or {})
        if executor:
            all_details["👤 Executed By"] = f"{executor.mention} (`{executor.name}`)"
        inc_id = incident_id or (details.get("Incident") if details else None) or generate_incident_id()

        embed = cls._create_report_embed(
            title=f"🤖 Bot Operation: {event}",
            color=0xF1C40F,
            event=event,
            user=executor,
            action_taken=action_taken,
            details=all_details,
            incident_id=inc_id,
        )
        cls.dispatch_report(bot, guild_id, "bot_report_id", embed, incident_id=inc_id)

    @classmethod
    def send_system_report(
        cls,
        bot: SentinelBot,
        guild_id: int,
        event: str,
        component: Optional[str] = None,
        status: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: Optional[str] = None,
        incident_id: Optional[str] = None,
    ) -> None:
        """Route to 📩 Owner DM AND 📋 ⚙️・system-report."""
        all_details = dict(details or {})
        if component:
            all_details["📦 Subsystem Component"] = f"`{component}`"
        if status:
            all_details["📊 Subsystem Status"] = f"**{status}**"

        color = Colors.ERROR if severity == "CRITICAL" else Colors.SUCCESS if status == "HEALTHY" else Colors.PRIMARY
        inc_id = incident_id or (details.get("Incident") if details else None) or generate_incident_id()

        embed = cls._create_report_embed(
            title=f"⚙️ System Infrastructure: {event}",
            color=color,
            event=event,
            severity=severity,
            details=all_details,
            incident_id=inc_id,
        )
        cls.dispatch_report(bot, guild_id, "system_report_id", embed, incident_id=inc_id)

    # ==========================================
    # PRIVATE CHANNEL SECURITY & AUTO-REPAIR
    # ==========================================

    @classmethod
    def _build_strict_overwrites(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
    ) -> Dict[Any, discord.PermissionOverwrite]:
        """
        Builds strict owner-only permission overwrites:
        - @everyone: No view, no send, no history
        - All server roles: No view, no send, no history
        - Current Server Owner: View, Send, History
        - Rai Bot: View, Send, History, Embed Links, Attach Files
        """
        overwrites: Dict[Any, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False,
                read_messages=False,
                send_messages=False,
                read_message_history=False,
            ),
        }

        # Deny every role in the server to protect against privilege escalation
        for r in getattr(guild, "roles", []):
            if r != guild.default_role:
                overwrites[r] = discord.PermissionOverwrite(
                    view_channel=False,
                    read_messages=False,
                    send_messages=False,
                    read_message_history=False,
                )

        # Dynamic Server Owner resolution
        owner_id = getattr(guild, "owner_id", None)
        owner_member = None
        if owner_id and hasattr(guild, "get_member"):
            owner_member = guild.get_member(owner_id)
        if not owner_member and hasattr(guild, "owner"):
            owner_member = guild.owner
        if not owner_member and hasattr(guild, "get_member"):
            owner_member = guild.get_member(OWNER_ID)

        if owner_member:
            overwrites[owner_member] = discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                send_messages=True,
                read_message_history=True,
            )

        # Rai Bot
        bot_user_id = bot.user.id if hasattr(bot, "user") and bot.user else BOT_ID
        bot_member = guild.get_member(bot_user_id) if hasattr(guild, "get_member") else None
        if not bot_member and hasattr(guild, "me"):
            bot_member = guild.me

        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                send_messages=True,
                read_message_history=True,
                embed_links=True,
                attach_files=True,
            )

        return overwrites

    @classmethod
    async def ensure_reports_category(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
    ) -> Optional[discord.CategoryChannel]:
        """Finds or creates the confidential '📋 | RAI REPORTS' category with strict owner-only permissions."""
        overwrites = cls._build_strict_overwrites(bot, guild)

        # Search existing categories
        category = None
        for cat in getattr(guild, "categories", []):
            cat_name = getattr(cat, "name", "").upper()
            if "RAI REPORTS" in cat_name or "📋 | RAI REPORTS" in cat_name:
                category = cat
                break

        if not category and hasattr(guild, "create_category"):
            try:
                cat_coro = guild.create_category(
                    name="📋 | RAI REPORTS",
                    overwrites=overwrites,
                    reason="Rai Autonomous Architecture: Created private confidential reports category",
                )
                if asyncio.iscoroutine(cat_coro) or hasattr(cat_coro, "__await__"):
                    category = await cat_coro
                else:
                    category = cat_coro
                logger.info(f"Created private report category in {guild.name} (ID: {getattr(category, 'id', 'unknown')})")
            except Exception as e:
                logger.error(f"Failed to create reports category in {guild.name}: {e}")
                return None

        # Ensure database is updated with category_id
        if category and hasattr(bot, "db") and bot.db and hasattr(bot.db, "update_owner_reports_config"):
            try:
                cid = getattr(category, "id", None)
                if cid:
                    await bot.db.update_owner_reports_config(guild.id, category_id=cid)
            except Exception:
                pass

        return category

    @classmethod
    async def repair_missing_channel(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        channel_key: str,
    ) -> Optional[discord.TextChannel]:
        """Automatically recreates any missing or deleted report channel with strict owner-only permissions."""
        logger.info(f"Auto-repairing missing report channel: {channel_key} in {guild.name}")
        category = await cls.ensure_reports_category(bot, guild)
        if not category or not isinstance(category, discord.CategoryChannel):
            return None

        channel_meta = {
            "security_report_id": (
                "🚨・security-report",
                "Private Owner Stream: Security incidents, anti-nuke, anti-raid, lockdowns, and threat alerts.",
            ),
            "mod_report_id": (
                "🛡️・mod-report",
                "Private Owner Stream: Bans, kicks, timeouts, warnings, and moderation actions.",
            ),
            "music_report_id": (
                "🎵・music-report",
                "Private Owner Stream: Music errors, playlist imports, playback and queue problems.",
            ),
            "room_report_id": (
                "🔐・room-report",
                "Private Owner Stream: Private VC creation/deletion, invites, locks, ownership transfers.",
            ),
            "bot_report_id": (
                "🤖・bot-report",
                "Private Owner Stream: Important bot actions and configuration changes.",
            ),
            "system_report_id": (
                "⚙️・system-report",
                "Private Owner Stream: Startup, shutdown, database, backups, health warnings, recovery.",
            ),
        }

        meta = channel_meta.get(channel_key)
        if not meta:
            return None
        target_name, topic = meta

        # Search existing channels under category
        target_norm = normalize_channel_name(target_name)
        for ch in getattr(category, "text_channels", []):
            if ch.name == target_name or normalize_channel_name(ch.name) == target_norm:
                if hasattr(bot, "db") and bot.db and hasattr(bot.db, "update_owner_reports_config"):
                    await bot.db.update_owner_reports_config(guild.id, **{channel_key: ch.id})
                return ch

        overwrites = cls._build_strict_overwrites(bot, guild)

        try:
            ch_coro = guild.create_text_channel(
                name=target_name,
                category=category,
                topic=topic,
                overwrites=overwrites,
                reason="Rai Autonomous Auto-Repair: Restored deleted confidential report channel",
            )
            if asyncio.iscoroutine(ch_coro) or hasattr(ch_coro, "__await__"):
                new_channel = await ch_coro
            else:
                new_channel = ch_coro

            if hasattr(bot, "db") and bot.db and hasattr(bot.db, "update_owner_reports_config"):
                chid = getattr(new_channel, "id", None)
                if chid:
                    await bot.db.update_owner_reports_config(guild.id, **{channel_key: chid})
            logger.info(f"Auto-repaired channel #{target_name} ({getattr(new_channel, 'id', 'unknown')}) in {guild.name}")
            return new_channel
        except Exception as e:
            logger.error(f"Failed to auto-repair channel {channel_key} in {guild.name}: {e}")
            return None


async def get_owner_report_channel(
    bot: SentinelBot,
    guild_id: int,
    category: str = "system",
) -> Optional[discord.TextChannel]:
    """Retrieve the Discord channel object for a report category (security, mod, music, room, bot, system)."""
    key_map = {
        "security": "security_report_id",
        "mod": "mod_report_id",
        "music": "music_report_id",
        "room": "room_report_id",
        "bot": "bot_report_id",
        "system": "system_report_id",
    }
    field = key_map.get(category.lower(), f"{category}_report_id")
    try:
        cfg = None
        if hasattr(bot, "db") and bot.db and hasattr(bot.db, "get_owner_reports_config"):
            cfg = await bot.db.get_owner_reports_config(guild_id)

        ch_id = getattr(cfg, field, None) if cfg else None
        guild = bot.get_guild(guild_id) if hasattr(bot, "get_guild") else None
        if not guild and hasattr(bot, "fetch_guild"):
            try:
                guild = await bot.fetch_guild(guild_id)
            except Exception:
                guild = None

        ch = None
        if ch_id:
            ch = guild.get_channel(ch_id) if guild else (bot.get_channel(ch_id) if hasattr(bot, "get_channel") else None)
            if not ch and hasattr(bot, "fetch_channel"):
                try:
                    ch = await bot.fetch_channel(ch_id)
                except Exception:
                    ch = None

        if not ch and (cfg is None or getattr(cfg, "auto_repair", True)) and guild:
            ch = await OwnerReporter.repair_missing_channel(bot, guild, field)
        return ch if isinstance(ch, discord.TextChannel) else None
    except Exception as e:
        logger.warning(f"Error fetching owner report channel {category}: {e}")
        return None


async def dispatch_owner_report(
    bot: SentinelBot,
    guild_id: int,
    category: str,
    title: str,
    description: str,
    color: int = Colors.PRIMARY,
    incident_id: Optional[str] = None,
) -> None:
    """Helper to dispatch quick report embed to BOTH Owner DM and corresponding private report channel."""
    inc_id = incident_id or generate_incident_id()
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.add_field(name="🆔 Incident ID", value=f"`{inc_id}`", inline=True)
    embed.set_footer(text=f"Confidential Owner Report • {inc_id} • RAI FAM💗")

    key_map = {
        "security": "security_report_id",
        "mod": "mod_report_id",
        "music": "music_report_id",
        "room": "room_report_id",
        "bot": "bot_report_id",
        "system": "system_report_id",
    }
    channel_key = key_map.get(category.lower(), "system_report_id")
    OwnerReporter.dispatch_report(bot, guild_id, channel_key, embed, incident_id=inc_id)
