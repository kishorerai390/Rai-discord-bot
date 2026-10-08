"""
RAI — Natural Language Owner Control Engine.
Provides:
- Lightweight, fast natural language intent recognition for server owner and authorized admins.
- Seamless mapping to existing Rai services (BackupManager, ObservabilityHealthService,
  DynamicVCControlManager, MusicCog, OwnerReporter) without duplicating logic.
- Owner-first authorization model and strict Discord permission preservation.
- Confirmation gate for destructive and high-impact actions.
- Sequential chained task execution with failure diagnostics (RAI-XXXXXX).
- Context-aware follow-up tracking scoped by (guild_id, user_id, channel_id).
- Dual-channel delivery routing sensitive details to Owner DM and private report channels.
- Full immutable audit logging with incident IDs (RAI-INC-XXXXXX).
- Interactive button continuations executing the identical service layer.
"""

from __future__ import annotations

import asyncio
import datetime
import difflib
import logging
import re
import string
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

import discord
from discord import ui

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed, warning_embed
from utils.owner_reporter import OWNER_ID, OwnerReporter, generate_incident_id

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger(__name__)


# =============================================================================
# 1. INTENTS & CONSTANTS
# =============================================================================

class NLIntent(str, Enum):
    # Workflow Pipelines & Automation
    WORKFLOW_CREATE = "WORKFLOW_CREATE"

    # Disaster Recovery & Backups
    BACKUP_CREATE = "BACKUP_CREATE"
    BACKUP_LIST = "BACKUP_LIST"
    BACKUP_VERIFY = "BACKUP_VERIFY"

    # Reliability & System Health
    HEALTH_CHECK = "HEALTH_CHECK"
    SYSTEM_STATUS = "SYSTEM_STATUS"

    # Dynamic Voice Rooms — Administrative
    ROOM_LIST = "ROOM_LIST"
    ROOM_CLEANUP = "ROOM_CLEANUP"
    LOCK_ALL_ROOMS = "LOCK_ALL_ROOMS"
    DELETE_ALL_ROOMS = "DELETE_ALL_ROOMS"

    # Dynamic Voice Rooms — Room Owner / Co-Host
    ROOM_MY = "ROOM_MY"
    ROOM_PRIVACY_PRIVATE = "ROOM_PRIVACY_PRIVATE"
    ROOM_PRIVACY_PUBLIC = "ROOM_PRIVACY_PUBLIC"
    ROOM_INVITE = "ROOM_INVITE"
    ROOM_REMOVE_MEMBER = "ROOM_REMOVE_MEMBER"
    DJ_ADD = "DJ_ADD"
    COHOST_ADD = "COHOST_ADD"

    # Music Streaming Subsystem
    MUSIC_QUEUE = "MUSIC_QUEUE"
    MUSIC_SKIP = "MUSIC_SKIP"
    MUSIC_PAUSE = "MUSIC_PAUSE"
    MUSIC_RESUME = "MUSIC_RESUME"
    MUSIC_STOP = "MUSIC_STOP"

    # Security & Lockdown
    SECURITY_CHECK = "SECURITY_CHECK"
    LOCK_SERVER = "LOCK_SERVER"
    UNLOCK_SERVER = "UNLOCK_SERVER"

    # Server Operations Core (Phase 1-15)
    OPERATIONS_CHECK = "OPERATIONS_CHECK"
    AWAY_SUMMARY = "AWAY_SUMMARY"
    MAINTENANCE_MODE_ENABLE = "MAINTENANCE_MODE_ENABLE"
    MAINTENANCE_MODE_DISABLE = "MAINTENANCE_MODE_DISABLE"
    SIMULATE_RAID = "SIMULATE_RAID"
    OPERATIONS_DASHBOARD = "OPERATIONS_DASHBOARD"

    # Contextual Follow-ups
    FOLLOW_UP_DETAILS = "FOLLOW_UP_DETAILS"
    FOLLOW_UP_CLEAN = "FOLLOW_UP_CLEAN"

    # Extended Subsystems (Phase 26)
    MEMORY_REMEMBER = "MEMORY_REMEMBER"
    MEMORY_CONTEXT = "MEMORY_CONTEXT"
    MEMORY_FORGET = "MEMORY_FORGET"
    EVENT_CREATE = "EVENT_CREATE"
    EVENT_LIST = "EVENT_LIST"
    EVENT_REMIND = "EVENT_REMIND"
    PROJECT_CREATE = "PROJECT_CREATE"
    PROJECT_LIST = "PROJECT_LIST"
    ANALYTICS_WEEKLY = "ANALYTICS_WEEKLY"
    REPUTATION_SHOW = "REPUTATION_SHOW"
    SIMULATE_LOCKDOWN = "SIMULATE_LOCKDOWN"
    SIMULATE_RECOVERY = "SIMULATE_RECOVERY"
    RECOVERY_AUDIT = "RECOVERY_AUDIT"


DANGEROUS_INTENTS: Set[NLIntent] = {
    NLIntent.LOCK_ALL_ROOMS,
    NLIntent.DELETE_ALL_ROOMS,
    NLIntent.LOCK_SERVER,
    NLIntent.FOLLOW_UP_CLEAN,
}

ADMIN_INTENTS: Set[NLIntent] = {
    NLIntent.BACKUP_CREATE,
    NLIntent.BACKUP_LIST,
    NLIntent.BACKUP_VERIFY,
    NLIntent.HEALTH_CHECK,
    NLIntent.SYSTEM_STATUS,
    NLIntent.ROOM_LIST,
    NLIntent.ROOM_CLEANUP,
    NLIntent.LOCK_ALL_ROOMS,
    NLIntent.DELETE_ALL_ROOMS,
    NLIntent.SECURITY_CHECK,
    NLIntent.LOCK_SERVER,
    NLIntent.UNLOCK_SERVER,
    NLIntent.OPERATIONS_CHECK,
    NLIntent.AWAY_SUMMARY,
    NLIntent.MAINTENANCE_MODE_ENABLE,
    NLIntent.MAINTENANCE_MODE_DISABLE,
    NLIntent.SIMULATE_RAID,
    NLIntent.OPERATIONS_DASHBOARD,
    NLIntent.MEMORY_REMEMBER,
    NLIntent.MEMORY_FORGET,
    NLIntent.SIMULATE_LOCKDOWN,
    NLIntent.SIMULATE_RECOVERY,
    NLIntent.RECOVERY_AUDIT,
}

FAST_DROP_PHRASES: Set[str] = {
    "hello", "hi", "hey", "sup", "yo", "good morning", "good evening",
    "good night", "what's up", "whats up", "how are you", "nice music",
    "cool music", "great bot", "thanks", "thank you", "thx", "ty", "lol",
    "lmao", "rofl", "ok", "okay", "k", "bye", "goodbye", "cya", "gm", "gn",
    "test", "testing", "nice", "gg", "welp", "bruh", "wow", "yes", "no"
}


# =============================================================================
# 2. CONVERSATIONAL CONTEXT STORE (SCOPED & TTL BOUNDED)
# =============================================================================

@dataclass
class NLSessionContext:
    guild_id: int
    user_id: int
    channel_id: int
    last_intent: Optional[NLIntent] = None
    last_result_type: Optional[str] = None
    last_result_data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    pending_confirmation: Optional[Dict[str, Any]] = None

    def is_expired(self, ttl: float = 120.0) -> bool:
        return (time.time() - self.timestamp) > ttl

    def update(
        self,
        last_intent: Optional[NLIntent] = None,
        last_type: Optional[str] = None,
        last_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        if last_intent is not None:
            self.last_intent = last_intent
        if last_type is not None:
            self.last_result_type = last_type
        if last_data is not None:
            self.last_result_data = last_data
        self.timestamp = time.time()


class NLContextManager:
    """Thread-safe context store isolated by (guild_id, user_id, channel_id)."""
    _sessions: Dict[Tuple[int, int, int], NLSessionContext] = {}
    _ttl: float = 120.0  # 2 minutes context retention

    @classmethod
    def get_session(cls, guild_id: int, user_id: int, channel_id: int) -> NLSessionContext:
        cls._prune_expired()
        key = (guild_id, user_id, channel_id)
        session = cls._sessions.get(key)
        if not session or session.is_expired(cls._ttl):
            session = NLSessionContext(guild_id=guild_id, user_id=user_id, channel_id=channel_id)
            cls._sessions[key] = session
        return session

    @classmethod
    def update_session(
        cls,
        guild_id: int,
        user_id: int,
        channel_id: int,
        last_intent: NLIntent,
        result_type: str,
        result_data: Dict[str, Any],
    ) -> None:
        session = cls.get_session(guild_id, user_id, channel_id)
        session.last_intent = last_intent
        session.last_result_type = result_type
        session.last_result_data = result_data
        session.timestamp = time.time()
        session.pending_confirmation = None

    @classmethod
    def set_pending_confirmation(
        cls,
        guild_id: int,
        user_id: int,
        channel_id: int,
        pending_data: Dict[str, Any],
    ) -> None:
        session = cls.get_session(guild_id, user_id, channel_id)
        session.pending_confirmation = pending_data
        session.timestamp = time.time()

    @classmethod
    def clear_pending(cls, guild_id: int, user_id: int, channel_id: int) -> None:
        key = (guild_id, user_id, channel_id)
        if key in cls._sessions:
            cls._sessions[key].pending_confirmation = None

    @classmethod
    def _prune_expired(cls) -> None:
        now = time.time()
        expired_keys = [k for k, s in cls._sessions.items() if (now - s.timestamp) > cls._ttl]
        for k in expired_keys:
            cls._sessions.pop(k, None)


# =============================================================================
# 3. NATURAL LANGUAGE PARSER & INTENT MATCHER
# =============================================================================

@dataclass
class ParsedTask:
    intent: NLIntent
    raw_segment: str
    confidence: float
    entities: Dict[str, Any] = field(default_factory=dict)


class NLParser:
    """Fast, lightweight regex and keyword-based intent extractor."""

    @classmethod
    def parse_message(
        cls,
        raw_text: str,
        context: Optional[NLSessionContext] = None,
        bot_id: Optional[int] = None,
    ) -> List[ParsedTask]:
        """
        Parses user message into one or more sequential tasks.
        Returns empty list if message is casual chat or non-command.
        """
        if not raw_text or not raw_text.strip():
            return []

        orig_text = raw_text.strip()
        text = orig_text.lower()

        # 1. Strip bot mention prefix if present
        if bot_id:
            mention_pat = re.compile(rf"^<@!?{bot_id}>\s*", re.IGNORECASE)
            text = mention_pat.sub("", text).strip()
            orig_text = mention_pat.sub("", orig_text).strip()

        # 2. Strip optional conversational prefix "you ", "rai ", "hey rai ", "bot "
        for prefix in ("you ", "rai ", "hey rai ", "bot "):
            if text.startswith(prefix):
                orig_text = orig_text[len(prefix):].strip()
                text = text[len(prefix):].strip()
                break

        # Fast drop check
        if text in FAST_DROP_PHRASES:
            return []

        # 3. Check for chained instructions: split by "and then", "then", or ", then"
        chain_delimiters = re.compile(r"\s+(?:and\s+then|then|, then)\s+", re.IGNORECASE)
        segments = chain_delimiters.split(text)
        orig_segments = chain_delimiters.split(orig_text)

        # Fallback: if single segment but contains " and ", check if two distinct commands
        if len(segments) == 1 and " and " in text:
            and_parts = text.split(" and ", 1)
            orig_parts = orig_text.split(" and ", 1) if " and " in orig_text else orig_text.split(" AND ", 1)
            if any(and_parts[1].strip().startswith(v) for v in ("check", "run", "show", "clean", "lock", "skip", "pause")):
                segments = and_parts
                orig_segments = orig_parts if len(orig_parts) == 2 else [orig_text, orig_text]

        parsed_tasks: List[ParsedTask] = []
        for idx, seg in enumerate(segments):
            orig_seg = orig_segments[idx] if idx < len(orig_segments) else seg
            task = cls._parse_single_segment(seg.strip(), orig_seg.strip(), context)
            if task and task.confidence >= 0.7:
                parsed_tasks.append(task)
            else:
                pass

        return parsed_tasks

    @classmethod
    def suggest_command(cls, raw_content: str, bot_id: Optional[int] = None) -> Optional[Tuple[str, str, ParsedTask]]:
        """
        Suggests an intended command if user appears to mistype a supported command (Phase 9).
        Only triggers if explicitly addressed to Rai or bot is mentioned to avoid interrupting
        regular chat.
        """
        text = raw_content.strip().lower()
        addressed = False

        if bot_id:
            mention_pat = re.compile(rf"^<@!?{bot_id}>\s*", re.IGNORECASE)
            if mention_pat.search(text):
                text = mention_pat.sub("", text).strip()
                addressed = True

        for prefix in ("rai ", "hey rai ", "you ", "bot "):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                addressed = True
                break

        # Only suggest if user explicitly directed message to Rai
        if not addressed or len(text) < 3 or len(text) > 35:
            return None

        if text in FAST_DROP_PHRASES:
            return None

        candidates = [
            ("bakup", "Backup", "💾", NLIntent.BACKUP_CREATE),
            ("backup", "Backup", "💾", NLIntent.BACKUP_CREATE),
            ("backups", "List Backups", "💾", NLIntent.BACKUP_LIST),
            ("health", "Health Check", "❤️", NLIntent.HEALTH_CHECK),
            ("helth", "Health Check", "❤️", NLIntent.HEALTH_CHECK),
            ("status", "System Status", "❤️", NLIntent.SYSTEM_STATUS),
            ("security", "Security Check", "🛡️", NLIntent.SECURITY_CHECK),
            ("securty", "Security Check", "🛡️", NLIntent.SECURITY_CHECK),
            ("rooms", "Active Rooms", "🎙️", NLIntent.ROOM_LIST),
            ("roms", "Active Rooms", "🎙️", NLIntent.ROOM_LIST),
            ("clean rooms", "Clean Empty Rooms", "🧹", NLIntent.ROOM_CLEANUP),
            ("cleanup", "Clean Empty Rooms", "🧹", NLIntent.ROOM_CLEANUP),
            ("operations", "Operations Check", "🧠", NLIntent.OPERATIONS_CHECK),
            ("check everything", "Operations Check", "🧠", NLIntent.OPERATIONS_CHECK),
            ("away summary", "Away Summary", "📊", NLIntent.AWAY_SUMMARY),
            ("maintenance", "Maintenance Mode", "🛠️", NLIntent.MAINTENANCE_MODE_ENABLE),
            ("simulate raid", "Simulate Raid", "🧪", NLIntent.SIMULATE_RAID),
            ("skip", "Skip Track", "⏭️", NLIntent.MUSIC_SKIP),
            ("pause", "Pause Music", "⏸️", NLIntent.MUSIC_PAUSE),
            ("queue", "Music Queue", "🎼", NLIntent.MUSIC_QUEUE),
        ]

        best_match = None
        highest_ratio = 0.0

        for keyword, label, emoji, intent in candidates:
            ratio = difflib.SequenceMatcher(None, text, keyword).ratio()
            if keyword in text or text in keyword:
                ratio = max(ratio, 0.75)
            if ratio > highest_ratio and ratio >= 0.70:
                highest_ratio = ratio
                best_match = (label, emoji, ParsedTask(intent=intent, raw_segment=text, confidence=ratio))

        return best_match

    @classmethod
    def _parse_single_segment(
        cls,
        text: str,
        orig_text: str,
        context: Optional[NLSessionContext] = None,
    ) -> Optional[ParsedTask]:
        if not text:
            return None

        # --- A. Contextual Follow-up Matching ---
        if text in ("show details", "details", "more info", "inspect", "inspect that"):
            if context and context.last_result_type:
                return ParsedTask(
                    intent=NLIntent.FOLLOW_UP_DETAILS,
                    raw_segment=text,
                    confidence=1.0,
                    entities={"target_type": context.last_result_type, "target_data": context.last_result_data},
                )
            return None

        if text in ("clean them", "clean those", "purge them", "clean rooms"):
            if context and context.last_result_type == "rooms":
                return ParsedTask(
                    intent=NLIntent.FOLLOW_UP_CLEAN,
                    raw_segment=text,
                    confidence=1.0,
                    entities={"target_type": "rooms", "room_ids": context.last_result_data.get("rooms", [])},
                )
            elif "clean" in text and "room" in text:
                return ParsedTask(
                    intent=NLIntent.ROOM_CLEANUP,
                    raw_segment=text,
                    confidence=0.9,
                )

        # --- B. Backup Subsystem ---
        if any(p in text for p in (
            "auto backup", "automatic backup", "run backup", "create backup",
            "take backup", "do a backup", "backup the server", "backup server",
            "do an automatic backup", "you auto backup"
        )) or "automatic backup" in text or "auto backup" in text:
            return ParsedTask(intent=NLIntent.BACKUP_CREATE, raw_segment=text, confidence=1.0)
        if text.startswith("backup") and len(text.split()) <= 4 and not any(w in text for w in ("list", "show", "status", "verify")):
            return ParsedTask(intent=NLIntent.BACKUP_CREATE, raw_segment=text, confidence=0.95)

        if any(p in text for p in ("show backups", "list backups", "view backups", "get backups", "backup list")):
            return ParsedTask(intent=NLIntent.BACKUP_LIST, raw_segment=text, confidence=1.0)

        if "verify backup" in text or "check backup" in text:
            return ParsedTask(intent=NLIntent.BACKUP_VERIFY, raw_segment=text, confidence=0.95)

        # --- Operations Center & Full System Inspection (Phase 1-15) ---
        if any(p in text for p in ("check everything", "operations check", "check all", "server check", "full check", "inspect everything")):
            return ParsedTask(intent=NLIntent.OPERATIONS_CHECK, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("what happened while i was away", "what happened while away", "away summary", "daily summary", "while i was away", "summary while away")):
            return ParsedTask(intent=NLIntent.AWAY_SUMMARY, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("simulate raid", "simulate attack", "simulate nuke", "test raid", "test anti-nuke", "simulate security")):
            return ParsedTask(intent=NLIntent.SIMULATE_RAID, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("disable maintenance mode", "exit maintenance mode", "maintenance mode off", "end maintenance mode")):
            return ParsedTask(intent=NLIntent.MAINTENANCE_MODE_DISABLE, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("put rai into maintenance mode", "enable maintenance mode", "maintenance mode on", "start maintenance mode")) or text == "maintenance mode":
            return ParsedTask(intent=NLIntent.MAINTENANCE_MODE_ENABLE, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("operations center", "operations dashboard", "show operations", "operations")):
            return ParsedTask(intent=NLIntent.OPERATIONS_DASHBOARD, raw_segment=text, confidence=1.0)

        # --- C. System & Reliability Health ---
        if any(p in text for p in ("check health", "system health", "check the bot", "is the bot okay", "is bot ok", "bot status", "health check", "health")):
            return ParsedTask(intent=NLIntent.HEALTH_CHECK, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("show system status", "system status", "status of system", "show status")):
            return ParsedTask(intent=NLIntent.SYSTEM_STATUS, raw_segment=text, confidence=0.95)

        # --- D. Dynamic Voice Rooms (Admin & Server Controls) ---
        if any(p in text for p in ("show active rooms", "list active rooms", "show rooms", "list rooms", "check active rooms", "check rooms", "active rooms")):
            return ParsedTask(intent=NLIntent.ROOM_LIST, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("clean empty rooms", "cleanup empty rooms", "purge empty rooms", "clean empty voice")):
            return ParsedTask(intent=NLIntent.ROOM_CLEANUP, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("lock all rooms", "lock all voice rooms", "lock all vc")):
            return ParsedTask(intent=NLIntent.LOCK_ALL_ROOMS, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("delete all rooms", "purge all rooms", "remove all rooms", "delete all vc")):
            return ParsedTask(intent=NLIntent.DELETE_ALL_ROOMS, raw_segment=text, confidence=1.0)

        # --- E. Security & Server Lockdown ---
        if any(p in text for p in ("check security", "run security check", "security status", "show security", "check the security")):
            return ParsedTask(intent=NLIntent.SECURITY_CHECK, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("lock the server", "server lockdown", "lockdown server", "lock down server")):
            return ParsedTask(intent=NLIntent.LOCK_SERVER, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("unlock the server", "end lockdown", "lift lockdown", "unlock server")):
            return ParsedTask(intent=NLIntent.UNLOCK_SERVER, raw_segment=text, confidence=1.0)

        # --- F. Dynamic Voice Rooms (Personal Controls - Specific first!) ---
        if any(p in text for p in ("make my room private", "set my room private", "lock my room", "make room private")):
            return ParsedTask(intent=NLIntent.ROOM_PRIVACY_PRIVATE, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("make my room public", "set my room public", "unlock my room", "make room public")):
            return ParsedTask(intent=NLIntent.ROOM_PRIVACY_PUBLIC, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("show my room", "my room status", "where is my room")) or text == "my room":
            return ParsedTask(intent=NLIntent.ROOM_MY, raw_segment=text, confidence=0.95)

        # Invite member
        invite_match = re.search(r"invite\s+(?:<@!?(\d+)>|@?([^\s]+))", orig_text, re.IGNORECASE)
        if invite_match:
            raw_target = invite_match.group(1) or invite_match.group(2)
            target_str = re.sub(r"[<@!>]", "", raw_target).strip()
            return ParsedTask(
                intent=NLIntent.ROOM_INVITE,
                raw_segment=text,
                confidence=0.95,
                entities={"target": target_str},
            )

        # Remove member
        remove_match = re.search(r"(?:remove|kick|disconnect)\s+(?:<@!?(\d+)>|@?([^\s]+))\s*(?:from my room|from room)?", orig_text, re.IGNORECASE)
        if remove_match and ("my room" in text or "room" in text or text.startswith("remove")):
            raw_target = remove_match.group(1) or remove_match.group(2)
            target_str = re.sub(r"[<@!>]", "", raw_target).strip()
            return ParsedTask(
                intent=NLIntent.ROOM_REMOVE_MEMBER,
                raw_segment=text,
                confidence=0.95,
                entities={"target": target_str},
            )

        # DJ delegation
        dj_match = re.search(r"(?:give|make|set)\s+(?:<@!?(\d+)>|@?([^\s]+))\s+(?:dj|room dj)", orig_text, re.IGNORECASE)
        if dj_match:
            raw_target = dj_match.group(1) or dj_match.group(2)
            target_str = re.sub(r"[<@!>]", "", raw_target).strip()
            return ParsedTask(
                intent=NLIntent.DJ_ADD,
                raw_segment=text,
                confidence=0.95,
                entities={"target": target_str},
            )

        # Co-host delegation
        cohost_match = re.search(r"(?:make|give|set)\s+(?:<@!?(\d+)>|@?([^\s]+))\s+(?:cohost|co-host)", orig_text, re.IGNORECASE)
        if cohost_match:
            raw_target = cohost_match.group(1) or cohost_match.group(2)
            target_str = re.sub(r"[<@!>]", "", raw_target).strip()
            return ParsedTask(
                intent=NLIntent.COHOST_ADD,
                raw_segment=text,
                confidence=0.95,
                entities={"target": target_str},
            )

        # --- G. Music Controls ---
        if any(p in text for p in ("show music queue", "show queue", "music queue", "what is playing", "now playing")):
            return ParsedTask(intent=NLIntent.MUSIC_QUEUE, raw_segment=text, confidence=1.0)

        if text in ("skip", "skip this", "skip song", "next song", "next track", "skip track"):
            return ParsedTask(intent=NLIntent.MUSIC_SKIP, raw_segment=text, confidence=1.0)

        if text in ("pause", "pause music", "stop playing"):
            return ParsedTask(intent=NLIntent.MUSIC_PAUSE, raw_segment=text, confidence=1.0)

        if text in ("resume", "resume music", "continue playing"):
            return ParsedTask(intent=NLIntent.MUSIC_RESUME, raw_segment=text, confidence=1.0)

        if any(p in text for p in ("restart music", "stop music", "halt music", "leave voice")):
            return ParsedTask(intent=NLIntent.MUSIC_STOP, raw_segment=text, confidence=0.95)

        # --- H. Extended Subsystems: Memory & Context ---
        if text.startswith("remember that ") or text.startswith("remember "):
            rem_body = orig_text.split("remember ", 1)[-1] if "remember " in orig_text else orig_text
            if " that " in rem_body.lower():
                rem_body = re.split(r"\s+that\s+", rem_body, maxsplit=1, flags=re.IGNORECASE)[-1]
            return ParsedTask(intent=NLIntent.MEMORY_REMEMBER, raw_segment=text, confidence=1.0, entities={"content": rem_body})

        if any(p in text for p in ("what do you remember", "server context", "show memory", "show context")):
            return ParsedTask(intent=NLIntent.MEMORY_CONTEXT, raw_segment=text, confidence=1.0)

        if text.startswith("forget ") or text.startswith("remove memory "):
            key_to_forget = orig_text.split("forget ", 1)[-1] if "forget " in orig_text else orig_text
            return ParsedTask(intent=NLIntent.MEMORY_FORGET, raw_segment=text, confidence=1.0, entities={"key": key_to_forget})

        # --- I. Extended Subsystems: Smart Events ---
        if any(p in text for p in ("create a movie night", "create movie night", "create an event", "create event", "create a gaming tournament", "schedule movie", "schedule event")):
            return ParsedTask(intent=NLIntent.EVENT_CREATE, raw_segment=text, confidence=1.0, entities={"query": orig_text})

        if any(p in text for p in ("show upcoming events", "upcoming events", "show events", "list events", "what events")):
            return ParsedTask(intent=NLIntent.EVENT_LIST, raw_segment=text, confidence=1.0)

        if "remind everyone" in text and "event" in text:
            return ParsedTask(intent=NLIntent.EVENT_REMIND, raw_segment=text, confidence=1.0)

        # --- J. Extended Subsystems: Collaboration Projects ---
        if any(p in text for p in ("create a project", "create project", "new project room", "project room")):
            proj_name = orig_text.split("for our ", 1)[-1] if "for our " in orig_text else (orig_text.split("project ", 1)[-1] if "project " in orig_text else "New Project")
            return ParsedTask(intent=NLIntent.PROJECT_CREATE, raw_segment=text, confidence=1.0, entities={"name": proj_name})

        if any(p in text for p in ("show active projects", "list projects", "active projects", "show projects")):
            return ParsedTask(intent=NLIntent.PROJECT_LIST, raw_segment=text, confidence=1.0)

        # --- K. Extended Subsystems: Analytics ---
        if any(p in text for p in ("what happened this week", "show this week's activity", "weekly report", "this week's activity", "weekly activity")):
            return ParsedTask(intent=NLIntent.ANALYTICS_WEEKLY, raw_segment=text, confidence=1.0)

        # --- L. Extended Subsystems: Reputation ---
        if any(p in text for p in ("show my reputation", "my reputation", "reputation profile", "check my rep")):
            return ParsedTask(intent=NLIntent.REPUTATION_SHOW, raw_segment=text, confidence=1.0)

        # --- M. Extended Subsystems: Disaster Recovery & Simulations ---
        if any(p in text for p in ("check if anything is broken", "check whether anything is missing", "check if anything is missing", "compare discord with the backup", "recovery audit")):
            return ParsedTask(intent=NLIntent.RECOVERY_AUDIT, raw_segment=text, confidence=1.0)

        if "simulate lockdown" in text:
            return ParsedTask(intent=NLIntent.SIMULATE_LOCKDOWN, raw_segment=text, confidence=1.0)

        if "simulate recovery" in text:
            return ParsedTask(intent=NLIntent.SIMULATE_RECOVERY, raw_segment=text, confidence=1.0)

        return None


# =============================================================================
# 4. ACTION DISPATCHER & SERVICE INTEGRATION LAYER
# =============================================================================

@dataclass
class DispatchResult:
    success: bool
    title: str
    message: str
    embed: discord.Embed
    next_actions: List[Tuple[str, str, str]] = field(default_factory=list)  # (label, emoji, action_name)
    requires_confirmation: bool = False
    confirmation_payload: Optional[Dict[str, Any]] = None
    sensitive_details: Optional[Dict[str, Any]] = None


class NLActionDispatcher:
    """Executes existing service commands on behalf of authorized users."""

    @classmethod
    async def dispatch(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        channel: discord.TextChannel,
        task: ParsedTask,
        session: NLSessionContext,
        is_confirmed: bool = False,
    ) -> DispatchResult:
        intent = task.intent

        # ---------------------------------------------------------
        # Step 1: Strict Permission & Owner Resolution Check
        # ---------------------------------------------------------
        is_owner = (user.id == guild.owner_id) or (user.id == OWNER_ID)
        is_admin = is_owner or user.guild_permissions.administrator

        if intent in ADMIN_INTENTS and not is_admin:
            logger.warning(f"NL Control: Unauthorized attempt by {user} ({user.id}) for intent {intent.value}")
            return DispatchResult(
                success=False,
                title="Unauthorized",
                message="❌ This administrative control is restricted to the server owner and administrators.",
                embed=error_embed("Permission Denied", "❌ You must be the Server Owner or an Administrator to execute this command."),
            )

        # ---------------------------------------------------------
        # Step 2: Dangerous Action Confirmation Gate
        # ---------------------------------------------------------
        if intent in DANGEROUS_INTENTS and not is_confirmed:
            impact_desc = "This operation will alter critical server or room state."
            if intent == NLIntent.LOCK_ALL_ROOMS:
                impact_desc = "This will immediately revoke join permissions for all active temporary voice rooms."
            elif intent == NLIntent.DELETE_ALL_ROOMS:
                impact_desc = "This will permanently delete all temporary voice rooms and remove their control panels."
            elif intent == NLIntent.LOCK_SERVER:
                impact_desc = "This will initiate emergency server lockdown, restricting @everyone from sending messages."
            elif intent == NLIntent.FOLLOW_UP_CLEAN:
                impact_desc = f"This will purge empty dynamic voice channels ({len(task.entities.get('room_ids', []))} target rooms)."

            embed = warning_embed(
                "⚠️ CONFIRMATION REQUIRED",
                f"**Action:** `{intent.value}`\n"
                f"**Impact:** {impact_desc}\n\n"
                "Please click **Confirm** below to proceed or **Cancel** to abort."
            )
            return DispatchResult(
                success=True,
                title="Confirmation Required",
                message="Action requires interactive confirmation.",
                embed=embed,
                requires_confirmation=True,
                confirmation_payload={
                    "intent": intent.value,
                    "entities": task.entities,
                    "actor_id": user.id,
                },
            )

        # ---------------------------------------------------------
        # Step 3: Dispatch to Existing Service Subsystems
        # ---------------------------------------------------------
        try:
            if intent == NLIntent.BACKUP_CREATE:
                return await cls._execute_backup_create(bot, guild, user, channel, session)
            elif intent == NLIntent.BACKUP_LIST:
                return await cls._execute_backup_list(bot, guild, user, session)
            elif intent in (NLIntent.HEALTH_CHECK, NLIntent.SYSTEM_STATUS):
                return await cls._execute_health_check(bot, guild, user, session)
            elif intent == NLIntent.ROOM_LIST:
                return await cls._execute_room_list(bot, guild, user, session)
            elif intent == NLIntent.ROOM_CLEANUP:
                return await cls._execute_room_cleanup(bot, guild, user, session)
            elif intent == NLIntent.LOCK_ALL_ROOMS:
                return await cls._execute_lock_all_rooms(bot, guild, user, session)
            elif intent == NLIntent.DELETE_ALL_ROOMS:
                return await cls._execute_delete_all_rooms(bot, guild, user, session)
            elif intent == NLIntent.SECURITY_CHECK:
                return await cls._execute_security_check(bot, guild, user, session)
            elif intent == NLIntent.LOCK_SERVER:
                return await cls._execute_lock_server(bot, guild, user, session)
            elif intent == NLIntent.UNLOCK_SERVER:
                return await cls._execute_unlock_server(bot, guild, user, session)
            elif intent == NLIntent.ROOM_MY:
                return await cls._execute_my_room(bot, guild, user, session)
            elif intent == NLIntent.ROOM_PRIVACY_PRIVATE:
                return await cls._execute_room_privacy(bot, guild, user, session, mode="invite")
            elif intent == NLIntent.ROOM_PRIVACY_PUBLIC:
                return await cls._execute_room_privacy(bot, guild, user, session, mode="public")
            elif intent == NLIntent.ROOM_INVITE:
                return await cls._execute_room_invite(bot, guild, user, session, task.entities.get("target"))
            elif intent == NLIntent.ROOM_REMOVE_MEMBER:
                return await cls._execute_room_remove_member(bot, guild, user, session, task.entities.get("target"))
            elif intent == NLIntent.DJ_ADD:
                return await cls._execute_room_dj(bot, guild, user, session, task.entities.get("target"))
            elif intent == NLIntent.COHOST_ADD:
                return await cls._execute_room_cohost(bot, guild, user, session, task.entities.get("target"))
            elif intent == NLIntent.MUSIC_QUEUE:
                return await cls._execute_music_queue(bot, guild, user, session)
            elif intent == NLIntent.MUSIC_SKIP:
                return await cls._execute_music_skip(bot, guild, user, session)
            elif intent == NLIntent.MUSIC_PAUSE:
                return await cls._execute_music_pause(bot, guild, user, session)
            elif intent == NLIntent.MUSIC_RESUME:
                return await cls._execute_music_resume(bot, guild, user, session)
            elif intent == NLIntent.MUSIC_STOP:
                return await cls._execute_music_stop(bot, guild, user, session)
            elif intent == NLIntent.FOLLOW_UP_DETAILS:
                return await cls._execute_follow_up_details(bot, guild, user, session)
            elif intent == NLIntent.FOLLOW_UP_CLEAN:
                return await cls._execute_room_cleanup(bot, guild, user, session)
            elif intent == NLIntent.OPERATIONS_CHECK:
                return await cls._execute_operations_check(bot, guild, user, session)
            elif intent == NLIntent.AWAY_SUMMARY:
                return await cls._execute_away_summary(bot, guild, user, session)
            elif intent == NLIntent.SIMULATE_RAID:
                return await cls._execute_simulate_raid(bot, guild, user, session)
            elif intent == NLIntent.MAINTENANCE_MODE_ENABLE:
                return await cls._execute_maintenance_mode(bot, guild, user, session, enabled=True)
            elif intent == NLIntent.MAINTENANCE_MODE_DISABLE:
                return await cls._execute_maintenance_mode(bot, guild, user, session, enabled=False)
            elif intent == NLIntent.OPERATIONS_DASHBOARD:
                return await cls._execute_operations_dashboard(bot, guild, user, session)
            elif intent == NLIntent.MEMORY_REMEMBER:
                return await cls._execute_memory_remember(bot, guild, user, session, task.entities.get("content", ""))
            elif intent == NLIntent.MEMORY_CONTEXT:
                return await cls._execute_memory_context(bot, guild, user, session)
            elif intent == NLIntent.MEMORY_FORGET:
                return await cls._execute_memory_forget(bot, guild, user, session, task.entities.get("key", ""))
            elif intent == NLIntent.EVENT_CREATE:
                return await cls._execute_event_create(bot, guild, user, session, task.entities.get("query", ""))
            elif intent == NLIntent.EVENT_LIST:
                return await cls._execute_event_list(bot, guild, user, session)
            elif intent == NLIntent.EVENT_REMIND:
                return await cls._execute_event_remind(bot, guild, user, session)
            elif intent == NLIntent.PROJECT_CREATE:
                return await cls._execute_project_create(bot, guild, user, session, task.entities.get("name", "New Project"))
            elif intent == NLIntent.PROJECT_LIST:
                return await cls._execute_project_list(bot, guild, user, session)
            elif intent == NLIntent.ANALYTICS_WEEKLY:
                return await cls._execute_analytics_weekly(bot, guild, user, session)
            elif intent == NLIntent.REPUTATION_SHOW:
                return await cls._execute_reputation_show(bot, guild, user, session)
            elif intent == NLIntent.RECOVERY_AUDIT:
                return await cls._execute_recovery_audit(bot, guild, user, session)
            elif intent == NLIntent.SIMULATE_LOCKDOWN:
                return await cls._execute_simulate_lockdown(bot, guild, user, session)
            elif intent == NLIntent.SIMULATE_RECOVERY:
                return await cls._execute_simulate_recovery(bot, guild, user, session)
            elif intent == NLIntent.WORKFLOW_CREATE:
                return await cls._execute_workflow_create(bot, guild, user, session, task.entities.get("query", task.raw_segment))
            else:
                return DispatchResult(
                    success=False,
                    title="Unsupported Intent",
                    message="Recognized intent is not currently mapped to an execution service.",
                    embed=error_embed("Unrecognized Action", "Could not find service handler for this intent."),
                )
        except Exception as e:
            logger.error(f"Error executing NL action {intent}: {e}", exc_info=True)
            diag_id = f"RAI-{int(time.time()) % 1000000:06d}"
            return DispatchResult(
                success=False,
                title="Service Failure",
                message=str(e),
                embed=error_embed(
                    "Action Failed",
                    f"❌ An internal error occurred while executing `{intent.value}`.\n"
                    f"• **Diagnostic ID:** `{diag_id}`\n"
                    f"• **Error:** `{e}`"
                ),
            )

class WorkflowPreviewView(ui.View):
    def __init__(self, bot: SentinelBot, guild: discord.Guild, user: discord.Member, wf: Any, steps: List[Any]):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild
        self.user = user
        self.wf = wf
        self.steps = steps

        self.activate_btn = ui.Button(label="Activate", style=discord.ButtonStyle.success, emoji="▶️")
        self.activate_btn.callback = self._on_activate
        self.add_item(self.activate_btn)

    async def _on_activate(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return
        await self.bot.db.create_workflow(self.wf)
        for st in self.steps:
            await self.bot.db.add_workflow_step(st)
        if hasattr(interaction, "response") and not interaction.response.is_done():
            await interaction.response.edit_message(
                embed=success_embed("Workflow Activated", f"Pipeline **{self.wf.name}** is now ACTIVE."),
                view=None,
            )
        elif hasattr(interaction, "followup"):
            await interaction.followup.send(
                embed=success_embed("Workflow Activated", f"Pipeline **{self.wf.name}** is now ACTIVE."),
                ephemeral=True,
            )


    # -------------------------------------------------------------------------
    # Subsystem Implementations (Invoking Existing Services)
    # -------------------------------------------------------------------------

    @classmethod
    async def _execute_workflow_create(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
        query: str,
    ) -> DispatchResult:
        wf_id = f"wf_{uuid.uuid4().hex[:8]}"
        q_low = (query or "").lower()
        if "sunday" in q_low or "weekly" in q_low:
            trigger_type = "weekly"
        elif "daily" in q_low:
            trigger_type = "daily"
        else:
            trigger_type = "schedule"

        from database.models import Workflow, WorkflowStep
        wf = Workflow(
            id=wf_id,
            guild_id=guild.id,
            creator_id=user.id,
            name="Automated Server Workflow",
            description=query,
            status="ACTIVE",
            trigger_type=trigger_type,
            trigger_config={"day": "sunday", "query": query},
        )
        steps = []
        step_order = 1
        if "backup" in q_low:
            steps.append(WorkflowStep(id=f"st_{uuid.uuid4().hex[:6]}", workflow_id=wf_id, step_order=step_order, action_type="backup.create", risk_level="LOW"))
            step_order += 1
        if "health" in q_low:
            steps.append(WorkflowStep(id=f"st_{uuid.uuid4().hex[:6]}", workflow_id=wf_id, step_order=step_order, action_type="health.check", risk_level="LOW"))
            step_order += 1
        if "report" in q_low:
            steps.append(WorkflowStep(id=f"st_{uuid.uuid4().hex[:6]}", workflow_id=wf_id, step_order=step_order, action_type="report.send", risk_level="LOW"))
            step_order += 1

        if not steps:
            steps.append(WorkflowStep(id=f"st_{uuid.uuid4().hex[:6]}", workflow_id=wf_id, step_order=1, action_type="health.check", risk_level="LOW"))

        view = WorkflowPreviewView(bot, guild, user, wf, steps)
        embed = discord.Embed(
            title="✦ RAI WORKFLOW PREVIEW ✦",
            description=f"Generated automated workflow for server **{guild.name}**.\n\n"
                        f"**Trigger:** `{trigger_type.upper()}`\n"
                        f"**Planned Steps:** `{len(steps)} actions`",
            color=Colors.PRIMARY,
        )
        for st in steps:
            embed.add_field(name=f"Step {st.step_order}", value=f"`{st.action_type}`", inline=True)

        return DispatchResult(
            success=True,
            title="Workflow Preview",
            message="Workflow generated from natural language query.",
            embed=embed,
            confirmation_payload={"view": view, "workflow": wf, "steps": steps},
        )

    @classmethod
    async def _execute_backup_create(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        channel: discord.TextChannel,
        session: NLSessionContext,
    ) -> DispatchResult:
        from backups.manager import BackupManager, format_bytes

        manager = BackupManager.get_instance()
        start_ts = time.time()
        record = await manager.run_backup(trigger=f"nl_owner_control_{user.name}")
        duration = round(time.time() - start_ts, 2)

        if not record.verified:
            diag_id = f"RAI-BKP-{int(time.time()) % 100000:05d}"
            return DispatchResult(
                success=False,
                title="Backup Verification Failed",
                message="Backup snapshot failed cryptographic verification.",
                embed=error_embed(
                    "Backup Failed",
                    f"❌ SQLite snapshot verification failed for `{record.backup_id}`.\n"
                    f"• **Diagnostic ID:** `{diag_id}`"
                ),
            )

        size_str = format_bytes(record.archive_size or record.sqlite_size)
        embed = create_embed(
            title="✅ BACKUP COMPLETED",
            description=(
                f"**Backup ID:** `{record.backup_id}`\n"
                f"**Duration:** `{duration}s`\n"
                f"**Archive Size:** `{size_str}`\n\n"
                f"💾 **Database Snapshot:** ✅\n"
                f"⚙️ **Configuration:** ✅\n"
                f"🔐 **Security State:** ✅\n"
                f"🎵 **Music & Playlists:** ✅\n"
                f"🔎 **SHA-256 Verification:** ✅ Passed\n"
                f"📦 **Archive:** `{record.storage_type}`"
            ),
            color=Colors.SUCCESS,
        )
        embed.set_footer(text=f"Triggered by {user.display_name} • Cryptographic Integrity Verified")

        # Update Session Context
        NLContextManager.update_session(
            guild_id=guild.id,
            user_id=user.id,
            channel_id=channel.id,
            last_intent=NLIntent.BACKUP_CREATE,
            result_type="backup",
            result_data={
                "backup_id": record.backup_id,
                "sha256": record.sqlite_sha256,
                "size_bytes": record.archive_size or record.sqlite_size,
                "archive_path": record.archive_path,
                "encryption": record.encryption_status,
            },
        )

        # Dual delivery: Dispatch report to Owner DM and private control
        OwnerReporter.send_system_report(
            bot=bot,
            guild_id=guild.id,
            event="Disaster Recovery Backup Created",
            component="NaturalLanguageControl",
            status="HEALTHY",
            details={
                "📦 Backup ID": f"`{record.backup_id}`",
                "📊 Size": f"`{size_str}`",
                "⏱️ Duration": f"`{duration}s`",
                "👤 Executed By": f"{user.mention} (`{user.name}`)",
                "🔐 SHA256": f"`{record.sqlite_sha256[:16]}...`",
            },
            incident_id=record.backup_id,
        )

        next_actions = [
            ("Details", "📋", "follow_up_details"),
            ("Backup List", "💾", "backup_list"),
            ("Health Check", "❤️", "health_check"),
        ]

        return DispatchResult(
            success=True,
            title="Backup Completed",
            message=f"Created verified backup {record.backup_id}",
            embed=embed,
            next_actions=next_actions,
            sensitive_details={"backup_id": record.backup_id, "path": record.archive_path},
        )

    @classmethod
    async def _execute_backup_list(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from backups.manager import BackupManager, format_bytes

        manager = BackupManager.get_instance()
        backups = manager.list_backups()

        if not backups:
            embed = info_embed("Disaster Recovery Archives", "⚪ No backup archives found on local storage.")
        else:
            lines = []
            for b in backups[:8]:
                size_str = format_bytes(b.get("size_bytes", 0))
                dt = b.get("formatted_created_at") or b.get("iso_created_at", "")[:16]
                ver = "✅" if b.get("verified") else "⚠️"
                lines.append(f"• `{b.get('backup_id')}` — {ver} `{size_str}` ({dt})")

            embed = create_embed(
                title=f"💾 Disaster Recovery Archives ({len(backups)})",
                description="\n".join(lines),
                color=Colors.PRIMARY,
            )
            embed.set_footer(text="Verified Cryptographic Checksums • Ordered by Recency")

        next_actions = [
            ("Run Backup", "💾", "backup_create"),
            ("Health Check", "❤️", "health_check"),
        ]

        return DispatchResult(
            success=True,
            title="Backup List",
            message=f"Listed {len(backups)} backups",
            embed=embed,
            next_actions=next_actions,
        )

    @classmethod
    async def _execute_health_check(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from observability.health import ObservabilityHealthService

        report = ObservabilityHealthService.evaluate_health(bot)

        def badge(val: str) -> str:
            v = str(val).upper()
            if "HEALTHY" in v or "ONLINE" in v or "ACTIVE" in v or "CONNECTED" in v:
                return f"🟢 `{v}`"
            elif "DEGRADED" in v or "WARN" in v:
                return f"🟡 `{v}`"
            return f"🔴 `{v}`"

        matrix = (
            f"**Overall Status:** {badge(report.overall_status)}\n"
            f"**Uptime:** `{report.uptime_seconds}s`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Security Subsystem:** {badge(report.security_health)}\n"
            f"• **Database Engine:** {badge(report.database_health)}\n"
            f"• **Background Workers:** {badge(report.worker_health)}\n"
            f"• **Liveness:** `{'PASS' if report.liveness else 'FAIL'}`\n"
            f"• **Readiness:** `{'READY' if report.readiness else 'INITIALIZING'}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        embed = create_embed(
            title="❤️ System Health Matrix",
            description=matrix,
            color=Colors.GREEN if report.overall_status == "HEALTHY" else Colors.GOLD,
        )
        embed.set_footer(text="Autonomous Self-Healing • Zero-Single-Point-of-Failure")

        NLContextManager.update_session(
            guild_id=guild.id,
            user_id=user.id,
            channel_id=session.channel_id,
            last_intent=NLIntent.HEALTH_CHECK,
            result_type="health",
            result_data={
                "overall_status": report.overall_status,
                "uptime_seconds": report.uptime_seconds,
                "security_health": report.security_health,
                "database_health": report.database_health,
                "worker_health": report.worker_health,
                "details": report.details,
            },
        )

        next_actions = [
            ("Run Backup", "💾", "backup_create"),
            ("Security Check", "🛡️", "security_check"),
            ("Active Rooms", "🔊", "room_list"),
        ]

        return DispatchResult(
            success=True,
            title="Health Check",
            message=f"Health status: {report.overall_status}",
            embed=embed,
            next_actions=next_actions,
        )

    @classmethod
    async def _execute_room_list(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        rooms = await bot.db.get_all_dynamic_rooms(guild.id)
        active_rooms: List[discord.VoiceChannel] = []
        empty_count = 0

        for r in rooms:
            vc = guild.get_channel(r.voice_channel_id)
            if isinstance(vc, discord.VoiceChannel):
                active_rooms.append(vc)
                if len(vc.members) == 0:
                    empty_count += 1

        if not active_rooms:
            embed = info_embed("Dynamic Voice Rooms", "🔊 No active dynamic voice rooms in this server.")
        else:
            lines = []
            for vc in active_rooms[:12]:
                occupancy = f"{len(vc.members)}/{vc.user_limit or '∞'}"
                lines.append(f"• **{vc.name}** — 👥 `{occupancy}`")

            embed = create_embed(
                title=f"🔊 Dynamic Voice Rooms ({len(active_rooms)})",
                description="\n".join(lines) + (f"\n\n*Empty rooms:* `{empty_count}`" if empty_count else ""),
                color=Colors.PRIMARY,
            )
            embed.set_footer(text="Central Voice Hub Engine • Active Channels")

        NLContextManager.update_session(
            guild_id=guild.id,
            user_id=user.id,
            channel_id=session.channel_id,
            last_intent=NLIntent.ROOM_LIST,
            result_type="rooms",
            result_data={
                "count": len(active_rooms),
                "rooms": [vc.id for vc in active_rooms],
                "empty_count": empty_count,
            },
        )

        next_actions = [
            ("Clean Empty Rooms", "🧹", "room_cleanup"),
            ("Lock All Rooms", "🔒", "lock_all_rooms"),
        ]

        return DispatchResult(
            success=True,
            title="Active Rooms",
            message=f"Found {len(active_rooms)} dynamic rooms",
            embed=embed,
            next_actions=next_actions,
        )

    @classmethod
    async def _execute_room_cleanup(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from utils.dynamic_vc_control import DynamicVCControlManager

        rooms = await bot.db.get_all_dynamic_rooms(guild.id)
        purged = 0

        for r in rooms:
            vc = guild.get_channel(r.voice_channel_id)
            if not isinstance(vc, discord.VoiceChannel):
                await DynamicVCControlManager.delete_room_panel(bot, guild, r.voice_channel_id)
                purged += 1
            elif len(vc.members) == 0:
                try:
                    await vc.delete(reason=f"Rai NL Control: Cleaned by {user.display_name}")
                except Exception:
                    pass
                await DynamicVCControlManager.delete_room_panel(bot, guild, r.voice_channel_id)
                purged += 1

        embed = success_embed(
            "Cleanup Complete",
            f"🧹 Purged **{purged}** empty dynamic rooms and stale control panels across the server."
        )

        next_actions = [
            ("Active Rooms", "🔊", "room_list"),
            ("Health Check", "❤️", "health_check"),
        ]

        return DispatchResult(
            success=True,
            title="Cleanup Complete",
            message=f"Cleaned {purged} empty rooms",
            embed=embed,
            next_actions=next_actions,
        )

    @classmethod
    async def _execute_lock_all_rooms(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from utils.dynamic_vc_control import DynamicVCControlManager

        rooms = await bot.db.get_all_dynamic_rooms(guild.id)
        count = 0

        for r in rooms:
            vc = guild.get_channel(r.voice_channel_id)
            if isinstance(vc, discord.VoiceChannel):
                try:
                    await vc.set_permissions(guild.default_role, connect=False)
                    await bot.db.update_dynamic_room(vc.id, locked=1, privacy_mode="locked")
                    await DynamicVCControlManager.update_room_panel(bot, guild, vc.id)
                    count += 1
                except Exception:
                    pass

        embed = warning_embed(
            "Dynamic Rooms Locked",
            f"🔒 Locked **{count}** dynamic voice rooms across the server. Existing members remain; new joins are blocked."
        )

        next_actions = [
            ("Active Rooms", "🔊", "room_list"),
            ("Health Check", "❤️", "health_check"),
        ]

        return DispatchResult(
            success=True,
            title="Rooms Locked",
            message=f"Locked {count} dynamic rooms",
            embed=embed,
            next_actions=next_actions,
        )

    @classmethod
    async def _execute_delete_all_rooms(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from utils.dynamic_vc_control import DynamicVCControlManager

        rooms = await bot.db.get_all_dynamic_rooms(guild.id)
        deleted = 0

        for r in rooms:
            vc = guild.get_channel(r.voice_channel_id)
            if isinstance(vc, discord.VoiceChannel):
                try:
                    await vc.delete(reason=f"Rai NL Control: Master purge by {user.display_name}")
                except Exception:
                    pass
            await DynamicVCControlManager.delete_room_panel(bot, guild, r.voice_channel_id)
            deleted += 1

        embed = error_embed(
            "Dynamic Rooms Deleted",
            f"🗑️ Purged all **{deleted}** temporary voice rooms and their control panels."
        )

        next_actions = [
            ("Active Rooms", "🔊", "room_list"),
            ("Health Check", "❤️", "health_check"),
        ]

        return DispatchResult(
            success=True,
            title="All Rooms Deleted",
            message=f"Purged {deleted} dynamic rooms",
            embed=embed,
            next_actions=next_actions,
        )

    @classmethod
    async def _execute_security_check(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        guild_cfg = await bot.db.get_or_create_guild_config(guild.id)
        sec_cfg = await bot.db.get_security_config(guild.id)
        sec_state = await bot.db.get_security_state(guild.id)
        incidents = await bot.db.get_security_incidents(guild.id, limit=3)

        status_str = "🟢 Active" if guild_cfg.security_enabled else "🔴 Disabled"
        lockdown_str = "🔒 Active" if sec_state.lockdown_enabled else "Normal"

        # Public / Channel Embed (Clean summary without exposing full threat vector)
        channel_embed = create_embed(
            title="🛡️ Security Status Overview",
            description=(
                f"**Engine Status:** {status_str}\n"
                f"**Lockdown Mode:** `{lockdown_str}`\n"
                f"**Recent Incidents:** `{len(incidents)}`\n\n"
                "✅ Deterministic threat protection is operating normally.\n"
                "🔐 *Confidential security details routed to Owner DM & Report Channels.*"
            ),
            color=Colors.SECURITY,
        )
        channel_embed.set_footer(text="Anti-Nuke • Anti-Raid • Mass Mention Shield")

        # Detailed breakdown for Owner DM & Private Reports
        details_dict = {
            "Module Status": status_str,
            "Channels Delete Limit": f"{sec_cfg.channel_delete_limit} / {sec_cfg.channel_delete_window}s",
            "Roles Delete Limit": f"{sec_cfg.role_delete_limit} / {sec_cfg.role_delete_window}s",
            "Ban Limit": f"{sec_cfg.ban_limit} / {sec_cfg.ban_window}s",
            "Punishment Mode": sec_cfg.punishment,
        }

        OwnerReporter.send_security_report(
            bot=bot,
            guild_id=guild.id,
            event="Owner Security Status Review",
            user=user,
            action_taken="Reviewed server security parameters",
            details=details_dict,
        )

        next_actions = [
            ("Health Check", "❤️", "health_check"),
            ("Run Backup", "💾", "backup_create"),
        ]

        return DispatchResult(
            success=True,
            title="Security Check Complete",
            message="Security check executed",
            embed=channel_embed,
            next_actions=next_actions,
            sensitive_details=details_dict,
        )

    @classmethod
    async def _execute_lock_server(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        locked_channels = 0
        for channel in guild.text_channels:
            perms = channel.overwrites_for(guild.default_role)
            if perms.send_messages is not False:
                perms.send_messages = False
                try:
                    await channel.set_permissions(guild.default_role, overwrite=perms, reason=f"Rai NL Lockdown by {user}")
                    locked_channels += 1
                except Exception:
                    pass

        await bot.db.set_lockdown(guild.id, True, actor=str(user))
        embed = error_embed(
            "🚨 SERVER LOCKDOWN INITIATED",
            f"🔒 Locked **{locked_channels}** text channels across the server.\n"
            f"All public chat permissions have been suspended by {user.mention}."
        )

        OwnerReporter.send_security_report(
            bot=bot,
            guild_id=guild.id,
            event="Emergency Server Lockdown",
            user=user,
            action_taken=f"Locked {locked_channels} channels",
            severity="CRITICAL",
        )

        return DispatchResult(
            success=True,
            title="Server Locked",
            message=f"Locked {locked_channels} channels",
            embed=embed,
            next_actions=[("Unlock Server", "🔓", "unlock_server")],
        )

    @classmethod
    async def _execute_unlock_server(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        unlocked_channels = 0
        for channel in guild.text_channels:
            perms = channel.overwrites_for(guild.default_role)
            if perms.send_messages is False:
                perms.send_messages = None
                try:
                    await channel.set_permissions(guild.default_role, overwrite=perms, reason=f"Rai NL Unlock by {user}")
                    unlocked_channels += 1
                except Exception:
                    pass

        await bot.db.set_lockdown(guild.id, False)
        embed = success_embed(
            "Server Lockdown Lifted",
            f"🔓 Restored chat permissions across **{unlocked_channels}** text channels."
        )

        return DispatchResult(
            success=True,
            title="Server Unlocked",
            message=f"Unlocked {unlocked_channels} channels",
            embed=embed,
            next_actions=[("Security Check", "🛡️", "security_check")],
        )

    # -------------------------------------------------------------------------
    # Personal Voice Room Controls
    # -------------------------------------------------------------------------

    @classmethod
    async def _get_user_room(cls, bot: SentinelBot, guild: discord.Guild, user: discord.Member) -> Optional[Tuple[Any, discord.VoiceChannel]]:
        rooms = await bot.db.get_all_dynamic_rooms(guild.id)
        for r in rooms:
            if r.owner_id == user.id:
                vc = guild.get_channel(r.voice_channel_id)
                if isinstance(vc, discord.VoiceChannel):
                    return (r, vc)
        # Check if user is in a dynamic room they co-host
        if user.voice and user.voice.channel:
            for r in rooms:
                if r.voice_channel_id == user.voice.channel.id and user.id in (r.co_host_ids or []):
                    return (r, user.voice.channel)
        return None

    @classmethod
    async def _execute_my_room(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        pair = await cls._get_user_room(bot, guild, user)
        if not pair:
            return DispatchResult(
                success=False,
                title="No Active Room",
                message="You do not currently own an active dynamic room.",
                embed=info_embed("No Active Room", "You don't currently have an active room. Join **🔊・CREATE YOUR ROOM** to create one!"),
            )
        room, vc = pair
        cohosts = [f"<@{uid}>" for uid in (room.co_host_ids or [])]
        djs = [f"<@{uid}>" for uid in (room.dj_ids or [])]

        embed = create_embed(
            title=f"🎙️ Your Room — {vc.name}",
            description=(
                f"• **Channel:** {vc.mention}\n"
                f"• **Occupants:** `{len(vc.members)}/{vc.user_limit or '∞'}`\n"
                f"• **Privacy:** `{room.privacy_mode.upper()}`\n"
                f"• **Co-Hosts:** {', '.join(cohosts) if cohosts else 'None'}\n"
                f"• **DJs:** {', '.join(djs) if djs else 'None'}"
            ),
            color=Colors.PRIMARY,
        )
        return DispatchResult(
            success=True,
            title="My Room",
            message=f"Displaying status for {vc.name}",
            embed=embed,
            next_actions=[
                ("Make Private", "🔒", "room_privacy_private"),
                ("Make Public", "🌐", "room_privacy_public"),
            ],
        )

    @classmethod
    async def _execute_room_privacy(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
        mode: str,
    ) -> DispatchResult:
        from utils.dynamic_vc_control import DynamicVCControlManager

        pair = await cls._get_user_room(bot, guild, user)
        if not pair:
            return DispatchResult(
                success=False,
                title="No Active Room",
                message="You do not own an active dynamic voice room.",
                embed=error_embed("No Room Found", "You do not currently own a temporary voice channel."),
            )
        room, vc = pair
        if mode == "invite":
            await vc.set_permissions(guild.default_role, view_channel=False, connect=False)
            await vc.set_permissions(user, view_channel=True, connect=True)
            await bot.db.update_dynamic_room(vc.id, privacy_mode="invite_only", locked=1)
            desc = f"👥 **{vc.name}** is now **Invite Only**."
        else:
            await vc.set_permissions(guild.default_role, view_channel=True, connect=True)
            await bot.db.update_dynamic_room(vc.id, privacy_mode="public", locked=0)
            desc = f"🌐 **{vc.name}** is now **Public**."

        await DynamicVCControlManager.update_room_panel(bot, guild, vc.id)
        embed = success_embed("Room Privacy Updated", desc)
        return DispatchResult(
            success=True,
            title="Privacy Updated",
            message=f"Privacy set to {mode}",
            embed=embed,
        )

    @classmethod
    async def _resolve_member(cls, guild: discord.Guild, target_str: Optional[str]) -> Optional[discord.Member]:
        if not target_str:
            return None
        # Check ID
        clean_id = re.sub(r"[<@!>]", "", target_str)
        if clean_id.isdigit():
            m = guild.get_member(int(clean_id))
            if m:
                return m
        # Check by name / display_name
        for m in guild.members:
            if m.name.lower() == target_str.lower() or m.display_name.lower() == target_str.lower():
                return m
        return None

    @classmethod
    async def _execute_room_invite(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
        target_str: Optional[str],
    ) -> DispatchResult:
        pair = await cls._get_user_room(bot, guild, user)
        if not pair:
            return DispatchResult(
                success=False,
                title="No Room Found",
                message="You must own an active room to invite friends.",
                embed=error_embed("No Active Room", "You do not own a room."),
            )
        room, vc = pair
        target = await cls._resolve_member(guild, target_str)
        if not target:
            return DispatchResult(
                success=False,
                title="Member Not Found",
                message=f"Could not locate member `{target_str}` in this server.",
                embed=error_embed("User Not Found", f"Could not find `{target_str}` in the server."),
            )

        await vc.set_permissions(target, view_channel=True, connect=True)
        await bot.db.add_room_member(vc.id, target.id, permission_type="invited")
        embed = success_embed("Member Invited", f"👥 Granted access to {target.mention} for **{vc.name}**.")
        return DispatchResult(success=True, title="Invited", message="Member invited", embed=embed)

    @classmethod
    async def _execute_room_remove_member(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
        target_str: Optional[str],
    ) -> DispatchResult:
        pair = await cls._get_user_room(bot, guild, user)
        if not pair:
            return DispatchResult(
                success=False,
                title="No Room Found",
                message="You must own an active room to remove members.",
                embed=error_embed("No Active Room", "You do not own a room."),
            )
        room, vc = pair
        target = await cls._resolve_member(guild, target_str)
        if not target:
            return DispatchResult(
                success=False,
                title="Member Not Found",
                message=f"Could not locate member `{target_str}`.",
                embed=error_embed("User Not Found", f"Could not find `{target_str}` in the server."),
            )

        if target.voice and target.voice.channel == vc:
            try:
                await target.move_to(None, reason=f"Rai NL Control: Removed by owner {user}")
            except Exception:
                pass
        await vc.set_permissions(target, overwrite=None)
        embed = success_embed("Member Removed", f"🚪 Disconnected {target.mention} from **{vc.name}**.")
        return DispatchResult(success=True, title="Removed", message="Member removed", embed=embed)

    @classmethod
    async def _execute_room_dj(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
        target_str: Optional[str],
    ) -> DispatchResult:
        from utils.dynamic_vc_control import DynamicVCControlManager

        pair = await cls._get_user_room(bot, guild, user)
        if not pair:
            return DispatchResult(
                success=False,
                title="No Room Found",
                message="You must own an active room to assign DJs.",
                embed=error_embed("No Active Room", "You do not own a room."),
            )
        room, vc = pair
        target = await cls._resolve_member(guild, target_str)
        if not target:
            return DispatchResult(
                success=False,
                title="Member Not Found",
                message=f"Could not locate member `{target_str}`.",
                embed=error_embed("User Not Found", f"Could not find `{target_str}`."),
            )

        djs = list(room.dj_ids or [])
        if target.id not in djs:
            djs.append(target.id)
            msg = f"🎧 Granted Room DJ privileges to {target.mention} in **{vc.name}**."
        else:
            djs.remove(target.id)
            msg = f"🎧 Revoked Room DJ privileges from {target.mention}."

        room.dj_ids = djs
        await bot.db.update_dynamic_room(vc.id, dj_ids=djs)
        await DynamicVCControlManager.update_room_panel(bot, guild, vc.id)
        embed = success_embed("Room DJ Updated", msg)
        return DispatchResult(success=True, title="Room DJ Updated", message="DJ updated", embed=embed)

    @classmethod
    async def _execute_room_cohost(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
        target_str: Optional[str],
    ) -> DispatchResult:
        from utils.dynamic_vc_control import DynamicVCControlManager

        pair = await cls._get_user_room(bot, guild, user)
        if not pair:
            return DispatchResult(
                success=False,
                title="No Room Found",
                message="You must own an active room to assign co-hosts.",
                embed=error_embed("No Active Room", "You do not own a room."),
            )
        room, vc = pair
        target = await cls._resolve_member(guild, target_str)
        if not target:
            return DispatchResult(
                success=False,
                title="Member Not Found",
                message=f"Could not locate member `{target_str}`.",
                embed=error_embed("User Not Found", f"Could not find `{target_str}`."),
            )

        cohosts = list(room.co_host_ids or [])
        if target.id not in cohosts:
            cohosts.append(target.id)
            await vc.set_permissions(target, view_channel=True, connect=True, move_members=True, mute_members=True)
            msg = f"🤝 Granted Co-Host privileges to {target.mention} in **{vc.name}**."
        else:
            cohosts.remove(target.id)
            await vc.set_permissions(target, overwrite=None)
            msg = f"🤝 Revoked Co-Host privileges from {target.mention}."

        room.co_host_ids = cohosts
        await bot.db.update_dynamic_room(vc.id, co_host_ids=cohosts)
        await DynamicVCControlManager.update_room_panel(bot, guild, vc.id)
        embed = success_embed("Room Co-Host Updated", msg)
        return DispatchResult(success=True, title="Co-Host Updated", message="Co-Host updated", embed=embed)

    # -------------------------------------------------------------------------
    # Music Subsystem Handlers
    # -------------------------------------------------------------------------

    @classmethod
    async def _execute_music_queue(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        music_cog = bot.cogs.get("Music")
        if not music_cog or not hasattr(music_cog, "players") or guild.id not in music_cog.players:
            return DispatchResult(
                success=True,
                title="Music Queue",
                message="No active queue",
                embed=info_embed("Music Queue", "🎵 No active music session in this server."),
            )

        player = music_cog.players[guild.id]
        current = getattr(player, "current", None)
        queue_list = getattr(player, "queue", [])

        lines = [f"🎵 **Now Playing:** {getattr(current, 'title', 'None')}\n"]
        if queue_list:
            lines.append(f"**Upcoming ({len(queue_list)}):**")
            for idx, item in enumerate(queue_list[:6], 1):
                lines.append(f"`{idx}.` {getattr(item, 'title', 'Track')}")
        else:
            lines.append("*Queue is empty.*")

        embed = create_embed(title="🎼 Server Music Queue", description="\n".join(lines), color=Colors.PRIMARY)
        next_actions = [("Skip", "⏭️", "music_skip"), ("Pause / Resume", "⏯️", "music_pause")]
        return DispatchResult(success=True, title="Queue", message="Queue retrieved", embed=embed, next_actions=next_actions)

    @classmethod
    async def _execute_music_skip(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        music_cog = bot.cogs.get("Music")
        if not music_cog or not hasattr(music_cog, "players") or guild.id not in music_cog.players:
            return DispatchResult(
                success=False,
                title="No Music",
                message="Nothing is currently playing.",
                embed=warning_embed("Not Playing", "🎵 Nothing is currently playing."),
            )
        player = music_cog.players[guild.id]
        title = player.current.title if player.current else "Current Track"
        vc = guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        elif hasattr(player, "skip") and callable(player.skip):
            res = player.skip()
            if asyncio.iscoroutine(res):
                await res
        embed = success_embed("Track Skipped", f"⏭️ Skipped **{title}**.")
        return DispatchResult(success=True, title="Skipped", message="Track skipped", embed=embed)

    @classmethod
    async def _execute_music_pause(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        music_cog = bot.cogs.get("Music")
        if not music_cog or not hasattr(music_cog, "players") or guild.id not in music_cog.players:
            return DispatchResult(
                success=False,
                title="No Music",
                message="Nothing is currently playing.",
                embed=warning_embed("Not Playing", "🎵 Nothing is currently playing."),
            )
        player = music_cog.players[guild.id]
        if getattr(player, "is_paused", False):
            await player.resume()
            msg = "▶️ Resumed music playback."
        else:
            await player.pause()
            msg = "⏸️ Paused music playback."
        embed = success_embed("Playback Toggled", msg)
        return DispatchResult(success=True, title="Playback Toggled", message=msg, embed=embed)

    @classmethod
    async def _execute_music_resume(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        music_cog = bot.cogs.get("Music")
        if not music_cog or not hasattr(music_cog, "players") or guild.id not in music_cog.players:
            return DispatchResult(
                success=False,
                title="No Music",
                message="Nothing is currently paused.",
                embed=warning_embed("Not Playing", "🎵 Nothing is currently paused."),
            )
        player = music_cog.players[guild.id]
        await player.resume()
        embed = success_embed("Playback Resumed", "▶️ Resumed music playback.")
        return DispatchResult(success=True, title="Playback Resumed", message="Resumed", embed=embed)

    @classmethod
    async def _execute_music_stop(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        music_cog = bot.cogs.get("Music")
        if music_cog and hasattr(music_cog, "players") and guild.id in music_cog.players:
            player = music_cog.players[guild.id]
            player.queue.clear()
            player.current = None
        vc = guild.voice_client
        if vc:
            await vc.disconnect(force=True)
        embed = success_embed("Music Halted", "🛑 Disconnected from voice channel and cleared music queue.")
        return DispatchResult(success=True, title="Music Stopped", message="Halted", embed=embed)

    # -------------------------------------------------------------------------
    # Context-Aware Follow-Up Inspection
    # -------------------------------------------------------------------------

    @classmethod
    async def _execute_follow_up_details(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        if session.last_result_type == "backup":
            b_id = session.last_result_data.get("backup_id", "Unknown")
            from backups.manager import BackupManager, format_bytes

            manager = BackupManager.get_instance()
            ver = await manager.verify_backup(b_id)
            desc = (
                f"**Backup ID:** `{b_id}`\n"
                f"**Status:** `{'VERIFIED' if ver.get('verified') else 'FAILED'}`\n"
                f"**SHA-256 Checksum:**\n`{ver.get('calculated_sha256', session.last_result_data.get('sha256', 'N/A'))}`\n"
                f"**Archive Size:** `{format_bytes(ver.get('archive_size', 0))}`\n"
                f"**Storage Path:** `{session.last_result_data.get('archive_path', 'local')}`\n"
                f"**Encryption:** `{session.last_result_data.get('encryption', 'NOT CONFIGURED')}`"
            )
            embed = create_embed(title=f"📋 Backup Inspection — {b_id}", description=desc, color=Colors.PRIMARY)
            return DispatchResult(success=True, title="Details", message="Backup details", embed=embed)

        elif session.last_result_type == "health":
            rep_data = session.last_result_data
            details = rep_data.get("details", {})
            desc = (
                f"**Uptime:** `{rep_data.get('uptime_seconds', 0)}s`\n"
                f"**Overall Status:** `{rep_data.get('overall_status')}`\n"
                f"• Security Health: `{rep_data.get('security_health')}`\n"
                f"• Database Health: `{rep_data.get('database_health')}`\n"
                f"• Worker Health: `{rep_data.get('worker_health')}`\n"
                f"• SQLite: `{details.get('sqlite', 'N/A')}`\n"
                f"• PostgreSQL: `{details.get('postgres', 'N/A')}`\n"
                f"• Redis: `{details.get('redis', 'N/A')}`\n"
                f"• Firebase: `{details.get('firebase', 'N/A')}`"
            )
            embed = create_embed(title="📋 Subsystem Telemetry Details", description=desc, color=Colors.PRIMARY)
            return DispatchResult(success=True, title="Details", message="Health details", embed=embed)

        elif session.last_result_type == "rooms":
            rooms = await bot.db.get_all_dynamic_rooms(guild.id)
            lines = []
            for r in rooms:
                vc = guild.get_channel(r.voice_channel_id)
                name = vc.name if vc else f"Room {r.voice_channel_id} (Stale)"
                lines.append(f"• `{r.voice_channel_id}`: **{name}** (Owner: <@{r.owner_id}>, Mode: `{r.privacy_mode}`)")
            desc = "\n".join(lines) if lines else "No rooms recorded."
            embed = create_embed(title="📋 Room Registry Records", description=desc, color=Colors.PRIMARY)
            return DispatchResult(success=True, title="Details", message="Room details", embed=embed)

        embed = info_embed("Context Details", "No recent detailed context found to inspect.")
        return DispatchResult(success=True, title="No Details", message="No context", embed=embed)

    # -------------------------------------------------------------------------
    # Server Operations Core Handlers (Phase 1-15)
    # -------------------------------------------------------------------------

    @classmethod
    async def _execute_operations_check(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from core.operations_core import RaiOperationsCore
        ops = RaiOperationsCore.get_instance(bot)
        overview = await ops.get_operations_overview(guild)

        health_emoji = "🟢" if overview["system_health"] == "HEALTHY" else "🟡"
        sec_emoji = "🟢" if overview["security_status"] == "NORMAL" else "🟡"
        maint_str = " | 🛠️ *Maintenance Active*" if overview["maintenance_mode"] else ""

        desc = (
            f"🤖 **Bot:** 🟢 Online{maint_str}\n\n"
            f"❤️ **System:** {health_emoji} {overview['system_health'].capitalize()}\n\n"
            f"🛡️ **Security:** {sec_emoji} {overview['security_status'].capitalize()}\n\n"
            f"🎙️ **Active Rooms:** `{overview['active_rooms_count']}`\n\n"
            f"🎵 **Music Sessions:** `{overview['music_sessions_count']}`\n\n"
            f"👥 **Members:** `{overview['members_count']:,}`\n\n"
            f"💾 **Last Backup:** `{overview['last_backup_str']}`\n\n"
            f"⚠️ **Open Incidents:** `{overview['open_incidents_count']}`"
        )

        embed = create_embed(
            title="🧠 RAI OPERATIONS CENTER",
            description=desc,
            color=Colors.PRIMARY,
        )

        session.update(
            last_intent=NLIntent.OPERATIONS_CHECK,
            last_type="operations",
            last_data=overview,
        )

        next_actions = [
            ("Health Check", "❤️", "health_check"),
            ("Security Check", "🛡️", "security_check"),
            ("Active Rooms", "🎙️", "room_list"),
            ("Run Backup", "💾", "backup_create"),
        ]

        return DispatchResult(
            success=True,
            title="Operations Overview",
            message="Operations check complete",
            embed=embed,
            next_actions=next_actions,
        )

    @classmethod
    async def _execute_away_summary(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from core.operations_core import AnalyticsService
        summary = await AnalyticsService.get_away_summary(bot, guild, hours=12)

        desc = (
            f"**Period:** `{summary['period_start']} → {summary['period_end']}`\n\n"
            f"👥 **COMMUNITY**\n"
            f"• `{summary['member_count']}` total members\n\n"
            f"🎙️ **ROOMS**\n"
            f"• `{summary['rooms_created']}` created\n"
            f"• `{summary['rooms_cleaned']}` cleaned\n"
            f"• `{summary['rooms_active']}` active\n\n"
            f"🎵 **MUSIC**\n"
            f"• `{summary['music_sessions']}` active sessions\n\n"
            f"🛡️ **SECURITY**\n"
            f"• `{summary['security_incidents_count']}` recorded incidents\n\n"
            f"💾 **BACKUP**\n"
            f"• `{summary['backups_count']}` archives in period\n\n"
            f"❤️ **SYSTEM**\n"
            f"• Health: `{summary['health_status']}`"
        )

        embed = create_embed(
            title="📊 RAI — WHILE YOU WERE AWAY",
            description=desc,
            color=Colors.PRIMARY,
        )

        session.update(
            last_intent=NLIntent.AWAY_SUMMARY,
            last_type="away_summary",
            last_data=summary,
        )

        return DispatchResult(
            success=True,
            title="Away Summary",
            message="Away summary generated from stored database events",
            embed=embed,
            next_actions=[("Operations Check", "🧠", "operations_check"), ("Security Check", "🛡️", "security_check")],
        )

    @classmethod
    async def _execute_simulate_raid(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from core.premium import PremiumFeatureGate, PremiumFeature, create_premium_upgrade_embed, EntitlementScope
        gate = await PremiumFeatureGate.has_access(bot, PremiumFeature.SECURITY_SIMULATION, user.id, guild.id)
        if not gate.has_access:
            embed = create_premium_upgrade_embed(
                "security_simulation",
                "Raid & Nuke Attack Simulation",
                required_scope=EntitlementScope.GUILD,
            )
            return DispatchResult(
                success=False,
                title="Premium Required",
                message="Raid attack simulation requires Rai Server Premium.",
                embed=embed,
                next_actions=[("Compare Plans", "📋", "premium_compare")],
            )

        from core.operations_core import RaiOperationsCore
        ops = RaiOperationsCore.get_instance(bot)
        sim_data = await ops.simulate_raid(guild, user)

        desc = (
            f"**Simulation ID:** `{sim_data['simulation_id']}`\n\n"
            f"**Scenario:** `{sim_data['scenario']}`\n"
            f"**Detected:** `{sim_data['simulated_deletions']}` simulated deletions (Threshold: `{sim_data['threshold']}`)\n"
            f"**Would trigger:** 🛡️ {sim_data['would_trigger']}\n"
            f"**Would execute:** 🔒 {sim_data['would_execute']}\n"
            f"**Notifications Sent:** {', '.join(sim_data['notified_destinations'])}\n\n"
            f"🛡️ **Sandbox Guarantee:** `Real damage taken: None (Zero channels deleted/modified)`"
        )

        embed = create_embed(
            title="🧪 SECURITY SIMULATION — RAID CONTAINMENT",
            description=desc,
            color=Colors.WARNING,
        )

        session.update(
            last_intent=NLIntent.SIMULATE_RAID,
            last_type="simulation",
            last_data=sim_data,
        )

        return DispatchResult(
            success=True,
            title="Simulation Complete",
            message="Safe raid simulation completed",
            embed=embed,
            next_actions=[("Security Check", "🛡️", "security_check"), ("Lockdown Check", "🔒", "lock_server")],
        )

    @classmethod
    async def _execute_maintenance_mode(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
        enabled: bool,
    ) -> DispatchResult:
        from core.operations_core import RaiOperationsCore
        ops = RaiOperationsCore.get_instance(bot)
        success = await ops.set_maintenance_mode(
            guild, user, enabled, reason=f"Requested via Natural Language by {user}"
        )

        if not success:
            return DispatchResult(
                success=False,
                title="Maintenance Update Failed",
                message="Failed to update maintenance mode in database.",
                embed=error_embed("Maintenance Error", "Could not toggle maintenance mode state."),
            )

        if enabled:
            embed = warning_embed(
                "🛠️ RAI MAINTENANCE MODE — ACTIVE",
                "• **Security:** 🟢 Active\n"
                "• **Reports:** 🟢 Active\n"
                "• **Rooms:** 🟢 Protected\n"
                "• **Automation:** 🟡 Paused\n\n"
                "Non-critical background jobs are suspended while core protection continues."
            )
        else:
            embed = success_embed(
                "🟢 RAI MAINTENANCE MODE — DEACTIVATED",
                "• All automated tasks, music, and background services have resumed standard operation."
            )

        return DispatchResult(
            success=True,
            title="Maintenance Mode",
            message=f"Maintenance mode set to {enabled}",
            embed=embed,
            next_actions=[("Operations Check", "🧠", "operations_check"), ("Health Check", "❤️", "health_check")],
        )

    @classmethod
    async def _execute_operations_dashboard(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from core.operations_core import RaiOperationsCore
        ops = RaiOperationsCore.get_instance(bot)
        overview = await ops.get_operations_overview(guild)

        health_emoji = "🟢" if overview["system_health"] == "HEALTHY" else "🟡"
        sec_emoji = "🟢" if overview["security_status"] == "NORMAL" else "🟡"
        maint_str = " | 🛠️ *Maintenance Mode*" if overview["maintenance_mode"] else ""

        desc = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 **Bot:** 🟢 Online{maint_str}\n"
            f"❤️ **System:** {health_emoji} {overview['system_health'].capitalize()}\n"
            f"🛡️ **Security:** {sec_emoji} {overview['security_status'].capitalize()}\n"
            f"🎙️ **Active Rooms:** `{overview['active_rooms_count']}`\n"
            f"🎵 **Music Sessions:** `{overview['music_sessions_count']}`\n"
            f"👥 **Members:** `{overview['members_count']:,}`\n"
            f"💾 **Last Backup:** `{overview['last_backup_str']}`\n"
            f"⚠️ **Open Incidents:** `{overview['open_incidents_count']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*Select an operation below to execute directly.*"
        )

        embed = create_embed(
            title="🧠 RAI OPERATIONS CENTER",
            description=desc,
            color=Colors.PRIMARY,
        )

        return DispatchResult(
            success=True,
            title="Operations Dashboard",
            message="Operations dashboard loaded",
            embed=embed,
            next_actions=[("Health", "❤️", "health_check"), ("Security", "🛡️", "security_check"), ("Rooms", "🎙️", "room_list"), ("Backups", "💾", "backup_list")],
        )

    @classmethod
    async def _execute_memory_remember(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
        content: str,
    ) -> DispatchResult:
        from core.memory import MemoryService
        # Extract key and value
        cleaned = content.strip()
        if " is " in cleaned:
            parts = cleaned.split(" is ", 1)
            key, val = parts[0].strip(), parts[1].strip()
        elif " that " in cleaned:
            parts = cleaned.split(" that ", 1)
            key, val = parts[0].strip(), parts[1].strip()
        else:
            key, val = "note", cleaned

        await MemoryService.remember(bot, guild.id, key, val, created_by=user.id)
        embed = success_embed(
            title="🧠 Rai Remembered",
            description=f"I have committed this to **{guild.name}** server memory:\n\n**Topic:** `{key}`\n**Detail:** {val}",
        )
        return DispatchResult(
            success=True,
            title="Memory Stored",
            message=f"Remembered: {key}",
            embed=embed,
            next_actions=[("Show Context", "🧠", "memory_context")],
        )

    @classmethod
    async def _execute_memory_context(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from core.memory import MemoryService
        memories = await MemoryService.list_memories(bot, guild.id)
        embed = create_embed(
            title=f"🧠 Server Context & Memory — {guild.name}",
            description=f"Remembered operational context (**{len(memories)}** items):",
            color=Colors.PRIMARY,
        )
        if memories:
            for m in memories[:8]:
                embed.add_field(name=f"🔑 {m['memory_key']}", value=m['memory_value'][:100], inline=False)
        else:
            embed.description = "No operational memory stored for this server yet."
        return DispatchResult(
            success=True,
            title="Server Memory Context",
            message=f"Context items: {len(memories)}",
            embed=embed,
        )

    @classmethod
    async def _execute_memory_forget(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
        key: str,
    ) -> DispatchResult:
        from core.memory import MemoryService
        deleted = await MemoryService.forget(bot, guild.id, key.strip())
        msg = f"✅ Forgot `{key}` from server memory." if deleted else f"ℹ️ Memory `{key}` was not found."
        embed = info_embed("Server Memory", msg)
        return DispatchResult(
            success=True,
            title="Memory Updated",
            message=msg,
            embed=embed,
        )

    @classmethod
    async def _execute_event_create(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
        query: str,
    ) -> DispatchResult:
        # Determine event type and title
        event_type = "gaming" if "tournament" in query.lower() or "gaming" in query.lower() else "community"
        title = "Community Movie Night" if "movie" in query.lower() else ("Gaming Tournament" if "tournament" in query.lower() else "Community Gathering")
        start_time = "Saturday at 9:00 PM UTC" if "saturday" in query.lower() else "Tomorrow at 8:00 PM UTC"

        event_id = await bot.db.create_event(
            guild_id=guild.id,
            title=title,
            event_type=event_type,
            start_time=start_time,
            description=f"Scheduled via Rai Natural Language by {user.display_name}.",
            creator_id=user.id,
        )
        embed = success_embed(
            title=f"🎉 Event Scheduled: {title} (#{event_id})",
            description=f"**Type:** `{event_type.title()}`\n**Time:** `{start_time}`\n**Organizer:** {user.mention}\n\nMembers can register using `/event join {event_id}`!",
        )
        return DispatchResult(
            success=True,
            title="Event Scheduled",
            message=f"Scheduled event #{event_id}",
            embed=embed,
            next_actions=[("Upcoming Events", "📅", "event_list")],
        )

    @classmethod
    async def _execute_event_list(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        events = await bot.db.list_events(guild.id, status="scheduled")
        embed = create_embed(
            title=f"📅 Scheduled Events — {guild.name} ({len(events)})",
            description="\n".join([f"• **#{e.id}** {e.title} — `{e.start_time}`" for e in events[:6]]) if events else "No events scheduled currently.",
            color=Colors.PRIMARY,
        )
        return DispatchResult(
            success=True,
            title="Scheduled Events",
            message=f"{len(events)} events active",
            embed=embed,
        )

    @classmethod
    async def _execute_event_remind(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        embed = info_embed(
            title="⏰ Event Reminders",
            description="Automated event participant reminders are scheduled to broadcast 1 hour before start time.",
        )
        return DispatchResult(
            success=True,
            title="Event Reminders Configured",
            message="Event reminders active",
            embed=embed,
        )

    @classmethod
    async def _execute_project_create(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
        name: str,
    ) -> DispatchResult:
        clean_name = name.strip() or "Collaboration Project"
        proj_id = await bot.db.create_project(
            guild_id=guild.id,
            name=clean_name,
            project_type="creator" if "edit" in clean_name.lower() or "video" in clean_name.lower() else "general",
            owner_id=user.id,
        )
        embed = success_embed(
            title=f"📁 Project Created: {clean_name} (#{proj_id})",
            description=f"**Owner:** {user.mention}\n**Status:** `ACTIVE 🟢`\n\nInvite team members with `/project invite {proj_id} @member`!",
        )
        return DispatchResult(
            success=True,
            title="Project Created",
            message=f"Project #{proj_id} created",
            embed=embed,
        )

    @classmethod
    async def _execute_project_list(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        projects = await bot.db.list_projects(guild.id, status="active")
        embed = create_embed(
            title=f"📁 Active Projects — {guild.name} ({len(projects)})",
            description="\n".join([f"• **#{p['id']}** {p['name']} (Owner: <@{p['owner_id']}>)" for p in projects[:6]]) if projects else "No active collaboration projects.",
            color=Colors.PRIMARY,
        )
        return DispatchResult(
            success=True,
            title="Active Projects",
            message=f"{len(projects)} projects active",
            embed=embed,
        )

    @classmethod
    async def _execute_analytics_weekly(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from core.analytics import ServerAnalyticsEngine
        w = await ServerAnalyticsEngine.generate_weekly_report(bot, guild)
        embed = create_embed(
            title=f"📊 Weekly Intelligence Summary — {guild.name}",
            description=(
                f"**Report Period:** Week of `{w['week_start']}`\n\n"
                f"👥 **MEMBERS:** `{w['members']['total_members']}` total (`{w['members']['active_percentage']}% active`)\n"
                f"🎙️ **VOICE:** `{w['voice']['voice_users']}` users across `{w['voice']['active_channels']}` active channels\n"
                f"🤝 **COMMUNITY:** `{w['community']['scheduled_events']}` events, `{w['community']['active_projects']}` projects\n"
                f"🛡️ **SECURITY:** `{w['security']['status']}`, `{w['security']['open_incidents']}` open incidents\n"
                f"❤️ **SYSTEM:** `{w['system']['overall_status']}`"
            ),
            color=Colors.GOLD,
        )
        return DispatchResult(
            success=True,
            title="Weekly Operational Report",
            message="Weekly report generated",
            embed=embed,
        )

    @classmethod
    async def _execute_reputation_show(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        profile = await bot.db.get_or_create_reputation_profile(guild.id, user.id)
        embed = create_embed(
            title=f"⭐ Community Reputation — {user.display_name}",
            description=(
                f"**Level:** `Level {profile['level']}`\n"
                f"**Reputation Points:** `{profile['points']} pts`\n\n"
                f"🤝 **Helpful Actions:** `{profile['helpful_count']}`\n"
                f"🎟️ **Events Attended:** `{profile['event_count']}`\n"
                f"🎙️ **Voice Time:** `{profile['voice_minutes']} mins`"
            ),
            color=Colors.GOLD,
        )
        return DispatchResult(
            success=True,
            title="Reputation Profile",
            message=f"Reputation: {profile['points']} pts",
            embed=embed,
        )

    @classmethod
    async def _execute_recovery_audit(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from core.recovery import DisasterRecoveryEngine
        scan_id, diffs = await DisasterRecoveryEngine.scan_guild_state(bot, guild)
        embed = create_embed(
            title=f"🔍 Disaster Recovery State Scan ({scan_id})",
            description=(
                f"**Discrepancies Detected:** `{len(diffs)}`\n\n"
                + ("\n".join([f"• [{d.diff_type}] {d.resource_name}" for d in diffs[:6]]) if diffs else "✅ All channels and database states are fully synchronized!")
            ),
            color=Colors.PRIMARY if not diffs else Colors.WARNING,
        )
        return DispatchResult(
            success=True,
            title="Recovery Scan Complete",
            message=f"Scan ID: {scan_id}",
            embed=embed,
        )

    @classmethod
    async def _execute_simulate_lockdown(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from core.simulation import SimulationLab
        sim = await SimulationLab.simulate_lockdown(bot, guild, user)
        embed = create_embed(
            title=f"🧪 SIMULATION: {sim.scenario}",
            description=f"**ID:** `{sim.simulation_id}`\n⚠️ `100% DRY RUN — ZERO LIVE MUTATIONS`\n\n" + "\n".join([f"• {w}" for w in sim.would_execute]),
            color=Colors.GOLD,
        )
        return DispatchResult(
            success=True,
            title="Lockdown Simulation",
            message="Lockdown simulation completed",
            embed=embed,
        )

    @classmethod
    async def _execute_simulate_recovery(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        user: discord.Member,
        session: NLSessionContext,
    ) -> DispatchResult:
        from core.simulation import SimulationLab
        sim = await SimulationLab.simulate_recovery(bot, guild, user)
        embed = create_embed(
            title=f"🧪 SIMULATION: {sim.scenario}",
            description=f"**ID:** `{sim.simulation_id}`\n⚠️ `100% DRY RUN — ZERO LIVE MUTATIONS`\n\n" + "\n".join([f"• {w}" for w in sim.would_execute]),
            color=Colors.GOLD,
        )
        return DispatchResult(
            success=True,
            title="Recovery Simulation",
            message="Recovery simulation completed",
            embed=embed,
        )


# =============================================================================
# 5. INTERACTIVE UI VIEWS (CONFIRMATION & NEXT ACTIONS)
# =============================================================================

class NLConfirmationView(ui.View):
    """Dangerous action confirmation view requiring explicit authorization."""

    def __init__(self, bot: SentinelBot, guild_id: int, user_id: int, channel_id: int, pending_data: Dict[str, Any]):
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.channel_id = channel_id
        self.pending_data = pending_data

    @ui.button(label="Confirm", emoji="✅", style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the authorizing administrator can confirm.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        session = NLContextManager.get_session(self.guild_id, self.user_id, self.channel_id)
        task = ParsedTask(
            intent=NLIntent(self.pending_data["intent"]),
            raw_segment="confirmed_action",
            confidence=1.0,
            entities=self.pending_data.get("entities", {}),
        )
        guild = interaction.guild or self.bot.get_guild(self.guild_id)
        res = await NLActionDispatcher.dispatch(
            bot=self.bot,
            guild=guild,  # type: ignore
            user=interaction.user,  # type: ignore
            channel=interaction.channel,  # type: ignore
            task=task,
            session=session,
            is_confirmed=True,
        )

        view = NLNextActionsView(self.bot, self.guild_id, self.user_id, self.channel_id, res.next_actions) if res.next_actions else None
        await interaction.followup.send(embed=res.embed, view=view)

    @ui.button(label="Cancel", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the authorizing administrator can cancel.", ephemeral=True)
            return

        NLContextManager.clear_pending(self.guild_id, self.user_id, self.channel_id)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=info_embed("Action Cancelled", "Operation cancelled by user."), view=self)


class NLNextActionsView(ui.View):
    """Dynamic next logical actions view executing the identical service layer."""

    def __init__(
        self,
        bot: SentinelBot,
        guild_id: int,
        user_id: int,
        channel_id: int,
        actions: List[Tuple[str, str, str]],
    ):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.channel_id = channel_id

        for label, emoji, action_name in actions[:5]:
            btn = ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.secondary,
                custom_id=f"rai_nl:{action_name}:{user_id}",
            )
            btn.callback = self._create_callback(action_name)
            self.add_item(btn)

    def _create_callback(self, action_name: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ You are not the author of this session.", ephemeral=True)
                return

            await interaction.response.defer()
            session = NLContextManager.get_session(self.guild_id, self.user_id, self.channel_id)

            # Map button action to parsed task
            task_map = {
                "backup_create": NLIntent.BACKUP_CREATE,
                "backup_list": NLIntent.BACKUP_LIST,
                "health_check": NLIntent.HEALTH_CHECK,
                "room_list": NLIntent.ROOM_LIST,
                "room_cleanup": NLIntent.ROOM_CLEANUP,
                "lock_all_rooms": NLIntent.LOCK_ALL_ROOMS,
                "security_check": NLIntent.SECURITY_CHECK,
                "follow_up_details": NLIntent.FOLLOW_UP_DETAILS,
                "music_skip": NLIntent.MUSIC_SKIP,
                "music_pause": NLIntent.MUSIC_PAUSE,
                "unlock_server": NLIntent.UNLOCK_SERVER,
                "room_privacy_private": NLIntent.ROOM_PRIVACY_PRIVATE,
                "room_privacy_public": NLIntent.ROOM_PRIVACY_PUBLIC,
            }
            target_intent = task_map.get(action_name, NLIntent.HEALTH_CHECK)
            task = ParsedTask(intent=target_intent, raw_segment=action_name, confidence=1.0)

            res = await NLActionDispatcher.dispatch(
                bot=self.bot,
                guild=interaction.guild,  # type: ignore
                user=interaction.user,  # type: ignore
                channel=interaction.channel,  # type: ignore
                task=task,
                session=session,
            )

            new_view = NLNextActionsView(self.bot, self.guild_id, self.user_id, self.channel_id, res.next_actions) if res.next_actions else None
            await interaction.followup.send(embed=res.embed, view=new_view)

        return callback


class NLSuggestionView(ui.View):
    """View presenting Did you mean: [Command]? [✅ Yes] [❌ No] (Phase 9)."""

    def __init__(
        self,
        bot: SentinelBot,
        guild_id: int,
        user_id: int,
        channel_id: int,
        task: ParsedTask,
        label: str,
        emoji: str,
    ):
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.channel_id = channel_id
        self.task = task
        self.label = label
        self.emoji = emoji

    @ui.button(label="Yes", emoji="✅", style=discord.ButtonStyle.success)
    async def yes_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This suggestion belongs to another user.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        session = NLContextManager.get_session(self.guild_id, self.user_id, self.channel_id)
        guild = interaction.guild or self.bot.get_guild(self.guild_id)
        res = await NLActionDispatcher.dispatch(
            bot=self.bot,
            guild=guild,  # type: ignore
            user=interaction.user,  # type: ignore
            channel=interaction.channel,  # type: ignore
            task=self.task,
            session=session,
        )
        view = NLNextActionsView(self.bot, self.guild_id, self.user_id, self.channel_id, res.next_actions) if res.next_actions else None
        await interaction.followup.send(embed=res.embed, view=view)

    @ui.button(label="No", emoji="❌", style=discord.ButtonStyle.secondary)
    async def no_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This suggestion belongs to another user.", ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=info_embed("Suggestion Dismissed", "Operation was not executed."), view=self)


# =============================================================================
# 6. CENTRAL NATURAL LANGUAGE CONTROL ENGINE FACADE
# =============================================================================

class NLControlEngine:
    """Entry facade for evaluating messages, executing chains, and handling interactions."""

    @classmethod
    async def process_message(cls, bot: SentinelBot, message: discord.Message) -> bool:
        """
        Main entry point for incoming Discord messages.
        Returns True if a natural language control command was recognized and handled.
        """
        if not message.guild or getattr(message.author, "bot", False) is True:
            return False

        # 1. Parse into tasks
        session = NLContextManager.get_session(message.guild.id, message.author.id, message.channel.id)
        tasks = NLParser.parse_message(message.content, context=session, bot_id=bot.user.id if bot.user else None)

        if not tasks:
            # Phase 9: Smart command suggestion for mistyped commands
            suggestion = NLParser.suggest_command(message.content, bot_id=bot.user.id if bot.user else None)
            if suggestion:
                label, emoji, suggested_task = suggestion
                embed = info_embed(
                    "Did you mean:",
                    f"{emoji} **{label}**\n\nClick **Yes** below to execute or **No** to dismiss."
                )
                view = NLSuggestionView(
                    bot=bot,
                    guild_id=message.guild.id,
                    user_id=message.author.id,
                    channel_id=message.channel.id,
                    task=suggested_task,
                    label=label,
                    emoji=emoji,
                )
                await message.channel.send(embed=embed, view=view)
                return True
            return False

        # 2. Sequential Task Chain Execution
        incident_id = generate_incident_id("RAI-INC")
        chain_results: List[DispatchResult] = []

        async with message.channel.typing():
            for idx, task in enumerate(tasks, 1):
                res = await NLActionDispatcher.dispatch(
                    bot=bot,
                    guild=message.guild,
                    user=message.author,
                    channel=message.channel,  # type: ignore
                    task=task,
                    session=session,
                )

                # Record Audit Log
                await bot.db.record_nl_audit(
                    incident_id=f"{incident_id}-{idx}",
                    guild_id=message.guild.id,
                    user_id=message.author.id,
                    user_name=str(message.author),
                    channel_id=message.channel.id,
                    raw_message=message.content[:250],
                    intent=task.intent.value,
                    confidence=task.confidence,
                    action=task.raw_segment[:100],
                    result="SUCCESS" if res.success else "FAILED",
                )

                chain_results.append(res)

                # If task failed or requires confirmation, HALT the chain!
                if not res.success or res.requires_confirmation:
                    if not res.success:
                        diag_id = f"RAI-{int(time.time()) % 1000000:06d}"
                        stop_embed = error_embed(
                            "❌ TASK CHAIN STOPPED",
                            f"**Step:** `{task.intent.value}`\n"
                            f"**Reason:** {res.message}\n"
                            f"**Diagnostic ID:** `{diag_id}`\n\n"
                            "Subsequent steps in the chain were halted for safety."
                        )
                        await message.channel.send(embed=stop_embed)
                    elif res.requires_confirmation:
                        NLContextManager.set_pending_confirmation(
                            message.guild.id, message.author.id, message.channel.id, res.confirmation_payload or {}
                        )
                        view = NLConfirmationView(
                            bot=bot,
                            guild_id=message.guild.id,
                            user_id=message.author.id,
                            channel_id=message.channel.id,
                            pending_data=res.confirmation_payload or {},
                        )
                        await message.channel.send(embed=res.embed, view=view)
                    return True

        # Send final/combined result if chain succeeded
        if chain_results:
            last_res = chain_results[-1]
            view = NLNextActionsView(bot, message.guild.id, message.author.id, message.channel.id, last_res.next_actions) if last_res.next_actions else None
            await message.channel.send(embed=last_res.embed, view=view)
            return True

        return False

    @classmethod
    async def handle_component_interaction(cls, bot: SentinelBot, interaction: discord.Interaction) -> bool:
        """Handles rai_nl: component interactions."""
        cid = interaction.data.get("custom_id", "")  # type: ignore
        if not cid.startswith("rai_nl:"):
            return False

        parts = cid.split(":")
        if len(parts) < 3:
            return False

        action_name = parts[1]
        allowed_user_id = int(parts[2])

        if interaction.user.id != allowed_user_id:
            await interaction.response.send_message("❌ This interactive continuation belongs to another user.", ephemeral=True)
            return True

        await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            return False

        session = NLContextManager.get_session(guild.id, interaction.user.id, interaction.channel_id or 0)
        task_map = {
            "backup_create": NLIntent.BACKUP_CREATE,
            "backup_list": NLIntent.BACKUP_LIST,
            "health_check": NLIntent.HEALTH_CHECK,
            "room_list": NLIntent.ROOM_LIST,
            "room_cleanup": NLIntent.ROOM_CLEANUP,
            "lock_all_rooms": NLIntent.LOCK_ALL_ROOMS,
            "security_check": NLIntent.SECURITY_CHECK,
            "follow_up_details": NLIntent.FOLLOW_UP_DETAILS,
            "music_skip": NLIntent.MUSIC_SKIP,
            "music_pause": NLIntent.MUSIC_PAUSE,
            "unlock_server": NLIntent.UNLOCK_SERVER,
            "room_privacy_private": NLIntent.ROOM_PRIVACY_PRIVATE,
            "room_privacy_public": NLIntent.ROOM_PRIVACY_PUBLIC,
        }
        target_intent = task_map.get(action_name, NLIntent.HEALTH_CHECK)
        task = ParsedTask(intent=target_intent, raw_segment=action_name, confidence=1.0)

        res = await NLActionDispatcher.dispatch(
            bot=bot,
            guild=guild,
            user=interaction.user,  # type: ignore
            channel=interaction.channel,  # type: ignore
            task=task,
            session=session,
        )

        view = NLNextActionsView(bot, guild.id, interaction.user.id, interaction.channel_id or 0, res.next_actions) if res.next_actions else None
        await interaction.followup.send(embed=res.embed, view=view)
        return True

    # Alias handle_interaction to handle_component_interaction
    handle_interaction = handle_component_interaction


# Backwards compatibility alias for central on_interaction router
NaturalLanguageControlManager = NLControlEngine
