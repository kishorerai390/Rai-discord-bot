"""
Async SQLite Database Manager for the Discord Bot.
Enforces foreign keys, WAL mode, transactions, and parameterization.
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid
import aiosqlite

from config import DATABASE_PATH
from database.migrations import run_migrations, backup_database
from database.models import (
    GuildConfig,
    SecurityConfig,
    SecurityIncident,
    SecurityState,
    ModerationWarning,
    WelcomeConfig,
    LoggingConfig,
    TicketConfig,
    TicketRecord,
    AutoModConfig,
    SuggestionConfig,
    SuggestionRecord,
    RaidConfig,
    RaidIncident,
    RaidEvent,
    VoiceGuardConfig,
    VoiceIncident,
    AutomationConfig,
    CommunityEvent,
    HiddenVoiceConfig,
    GamingLFG,
    OwnerReportsConfig,
    MemberInvites,
    StreamTracker,
    UserEconomy,
    MusicConfig,
    MusicPlaylist,
    WatchEvent,
    ReportDeliveryRecord,
    MemberVotes,
    ReportDestination,
    GuildRole,
    RoleAuditLog,
    HiddenVoiceRoom,
    CreatorShowcase,
    ReportEventRecord,
    ReportPermissionState,
    MusicAnalytics,
    InteractiveIncident,
    IncidentActionAudit,
    SubsystemHealthRecord,
    DynamicRoom,
    RoomMember,
    TempVoiceConfig,
    ServerStatsConfig,
    RoomTemplate,
    RoomKnockRequest,
    AutopilotConfig,
    AutopilotAction,
    SecurityBaseline,
    GuildChannelConfig,
    InteractionRecord,
    ChannelAccessConfig,
    ChannelAccessState,
    VerificationConfig,
)

logger = logging.getLogger(__name__)


def utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: Optional[Any] = None):
        if isinstance(db_path, str) and db_path != ":memory:":
            self.db_path = Path(db_path)
        else:
            self.db_path = db_path if db_path is not None else DATABASE_PATH
        self._db: Optional[aiosqlite.Connection] = None

    @property
    def is_connected(self) -> bool:
        return self._db is not None

    async def connect(self) -> None:
        """Connect to SQLite database, configure PRAGMAs and run migrations."""
        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row

        # Essential safety pragmas
        await self._db.execute("PRAGMA foreign_keys = ON;")
        await self._db.execute("PRAGMA journal_mode = WAL;")
        await self._db.execute("PRAGMA synchronous = NORMAL;")
        await self._db.execute("PRAGMA busy_timeout = 5000;")
        await self._db.commit()

        # Run schema migrations
        await run_migrations(self._db)

        # Dynamic rooms & autopilot tables
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS dynamic_rooms (
                guild_id INTEGER NOT NULL,
                voice_channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                room_type TEXT DEFAULT 'public',
                privacy_mode TEXT DEFAULT 'public',
                user_limit INTEGER DEFAULT 0,
                locked INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                control_message_id INTEGER,
                control_channel_id INTEGER,
                cleanup_status TEXT DEFAULT 'active',
                empty_since TEXT,
                cleanup_due_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        for col_def in [
            "ALTER TABLE dynamic_rooms ADD COLUMN cleanup_status TEXT DEFAULT 'active'",
            "ALTER TABLE dynamic_rooms ADD COLUMN empty_since TEXT",
            "ALTER TABLE dynamic_rooms ADD COLUMN cleanup_due_at TEXT",
            "ALTER TABLE dynamic_rooms ADD COLUMN updated_at TEXT",
        ]:
            try:
                await self._db.execute(col_def)
            except Exception:
                pass
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS room_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voice_channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                permission_type TEXT DEFAULT 'view',
                added_at TEXT NOT NULL
            );
            """
        )
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS autopilot_configs (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                dry_run INTEGER DEFAULT 0,
                max_safety_level TEXT DEFAULT 'HIGH',
                alert_channel_id INTEGER,
                ticket_management INTEGER DEFAULT 1,
                auto_safe_mode INTEGER DEFAULT 1,
                updated_at TEXT NOT NULL
            );
            """
        )
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS security_baselines (
                guild_id INTEGER PRIMARY KEY,
                joins_per_hour REAL DEFAULT 0.0,
                messages_per_min REAL DEFAULT 0.0,
                voice_users REAL DEFAULT 0.0,
                sample_count INTEGER DEFAULT 0,
                avg_joins_per_hour REAL DEFAULT 0.0,
                avg_messages_per_min REAL DEFAULT 0.0,
                updated_at TEXT NOT NULL
            );
            """
        )
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS autopilot_actions (
                id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                module TEXT NOT NULL,
                trigger TEXT NOT NULL,
                reason TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                target_id INTEGER,
                target_type TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                role_key TEXT NOT NULL,
                discord_role_id INTEGER NOT NULL,
                role_name TEXT NOT NULL,
                role_type TEXT NOT NULL,
                managed_by_rai INTEGER NOT NULL DEFAULT 1,
                enabled INTEGER NOT NULL DEFAULT 1,
                position INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (guild_id, role_key),
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """
        )
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS role_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER,
                role_id INTEGER,
                role_key TEXT,
                action TEXT NOT NULL,
                reason TEXT,
                trigger TEXT,
                executor TEXT,
                success INTEGER NOT NULL DEFAULT 1,
                error TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """
        )
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS subsystem_health (
                subsystem TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                last_check TEXT NOT NULL,
                failure_count INTEGER DEFAULT 0,
                details TEXT
            );
            """
        )
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS verification_configs (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                role_id INTEGER,
                channel_id INTEGER,
                verified_role_id INTEGER,
                community_role_id INTEGER,
                verify_channel_id INTEGER,
                welcome_channel_id INTEGER,
                min_account_age_hours INTEGER NOT NULL DEFAULT 0,
                require_2fa INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT ''
            );
            """
        )
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS verification_records (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                account_age_hours REAL DEFAULT 0,
                verified_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );
            """
        )
        await self._db.commit()

    async def update_subsystem_health(self, subsystem: str, status: str, details: str = "") -> None:
        now_str = utcnow_iso()
        await self._db.execute(
            """
            INSERT INTO subsystem_health (subsystem, status, last_check, failure_count, details)
            VALUES (?, ?, ?, 0, ?)
            ON CONFLICT(subsystem) DO UPDATE SET
                status = excluded.status,
                last_check = excluded.last_check,
                details = excluded.details
            """,
            (subsystem, status, now_str, details),
        )
        await self._db.commit()

    async def get_all_subsystem_health(self) -> List[SubsystemHealthRecord]:
        async with self._db.execute("SELECT subsystem, status, details, last_check FROM subsystem_health") as cursor:
            rows = await cursor.fetchall()
            return [
                SubsystemHealthRecord(
                    subsystem=row["subsystem"],
                    status=row["status"],
                    details=row["details"] or "",
                    updated_at=row["last_check"] or "",
                )
                for row in rows
            ]

    # --- DYNAMIC ROOMS CRUD ---

    def _row_to_dynamic_room(self, row: Any) -> DynamicRoom:
        keys = row.keys()
        co_host_ids = None
        if "co_host_ids" in keys and row["co_host_ids"]:
            try:
                co_host_ids = json.loads(row["co_host_ids"])
            except Exception:
                co_host_ids = []
        dj_ids = None
        if "dj_ids" in keys and row["dj_ids"]:
            try:
                dj_ids = json.loads(row["dj_ids"])
            except Exception:
                dj_ids = []

        return DynamicRoom(
            guild_id=row["guild_id"],
            voice_channel_id=row["voice_channel_id"],
            owner_id=row["owner_id"],
            room_type=row["room_type"],
            privacy_mode=row["privacy_mode"],
            user_limit=row["user_limit"],
            locked=bool(row["locked"]),
            status=row["status"],
            control_message_id=row["control_message_id"],
            control_channel_id=row["control_channel_id"],
            cleanup_status=row["cleanup_status"] if "cleanup_status" in keys else "active",
            empty_since=row["empty_since"] if "empty_since" in keys else None,
            cleanup_due_at=row["cleanup_due_at"] if "cleanup_due_at" in keys else None,
            last_empty_at=row["last_empty_at"] if "last_empty_at" in keys else None,
            protected_until=row["protected_until"] if "protected_until" in keys else None,
            last_voice_activity=row["last_voice_activity"] if "last_voice_activity" in keys else None,
            co_host_ids=co_host_ids,
            dj_ids=dj_ids,
            template_id=row["template_id"] if "template_id" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def create_dynamic_room(self, room: DynamicRoom) -> None:
        now_str = utcnow_iso()
        co_host_ids_str = json.dumps(room.co_host_ids) if room.co_host_ids is not None else None
        dj_ids_str = json.dumps(room.dj_ids) if room.dj_ids is not None else None
        await self._db.execute(
            """
            INSERT INTO dynamic_rooms (
                guild_id, voice_channel_id, owner_id, room_type, privacy_mode,
                user_limit, locked, status, control_message_id, control_channel_id,
                cleanup_status, empty_since, cleanup_due_at, last_empty_at, protected_until, last_voice_activity,
                co_host_ids, dj_ids, template_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(voice_channel_id) DO UPDATE SET
                guild_id = excluded.guild_id,
                owner_id = excluded.owner_id,
                room_type = excluded.room_type,
                privacy_mode = excluded.privacy_mode,
                user_limit = excluded.user_limit,
                locked = excluded.locked,
                status = excluded.status,
                control_message_id = excluded.control_message_id,
                control_channel_id = excluded.control_channel_id,
                cleanup_status = excluded.cleanup_status,
                empty_since = excluded.empty_since,
                cleanup_due_at = excluded.cleanup_due_at,
                last_empty_at = excluded.last_empty_at,
                protected_until = excluded.protected_until,
                last_voice_activity = excluded.last_voice_activity,
                co_host_ids = excluded.co_host_ids,
                dj_ids = excluded.dj_ids,
                template_id = excluded.template_id,
                updated_at = excluded.updated_at
            """,
            (
                room.guild_id, room.voice_channel_id, room.owner_id, room.room_type,
                room.privacy_mode, room.user_limit, 1 if room.locked else 0,
                room.status, room.control_message_id, room.control_channel_id,
                getattr(room, "cleanup_status", "active"),
                getattr(room, "empty_since", None),
                getattr(room, "cleanup_due_at", None),
                getattr(room, "last_empty_at", None),
                getattr(room, "protected_until", None),
                getattr(room, "last_voice_activity", None),
                co_host_ids_str,
                dj_ids_str,
                getattr(room, "template_id", None),
                room.created_at or now_str, room.updated_at or now_str
            ),
        )
        await self._db.commit()

    async def get_dynamic_room(self, voice_channel_id: int) -> Optional[DynamicRoom]:
        async with self._db.execute(
            "SELECT * FROM dynamic_rooms WHERE voice_channel_id = ?", (voice_channel_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_dynamic_room(row)

    async def get_all_dynamic_rooms(self, guild_id: Optional[int] = None) -> List[DynamicRoom]:
        query = "SELECT * FROM dynamic_rooms"
        params = ()
        if guild_id is not None:
            query += " WHERE guild_id = ?"
            params = (guild_id,)
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dynamic_room(row) for row in rows]

    async def get_dynamic_room_by_control_message(self, control_message_id: int) -> Optional[DynamicRoom]:
        async with self._db.execute(
            "SELECT * FROM dynamic_rooms WHERE control_message_id = ?", (control_message_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_dynamic_room(row)

    async def get_dynamic_room_by_owner(self, guild_id: int, owner_id: int) -> Optional[DynamicRoom]:
        async with self._db.execute(
            "SELECT * FROM dynamic_rooms WHERE guild_id = ? AND owner_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (guild_id, owner_id)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_dynamic_room(row)

    async def update_dynamic_room(self, voice_channel_id: int, **kwargs: Any) -> None:
        if not kwargs:
            return
        fields = []
        values = []
        for k, v in kwargs.items():
            if k == "locked":
                v = 1 if v else 0
            elif k in ("co_host_ids", "dj_ids") and isinstance(v, list):
                v = json.dumps(v)
            fields.append(f"{k} = ?")
            values.append(v)
        fields.append("updated_at = ?")
        values.append(utcnow_iso())
        values.append(voice_channel_id)
        query = f"UPDATE dynamic_rooms SET {', '.join(fields)} WHERE voice_channel_id = ?"
        await self._db.execute(query, tuple(values))
        await self._db.commit()

    async def delete_dynamic_room(self, voice_channel_id: int) -> None:
        await self._db.execute("DELETE FROM dynamic_rooms WHERE voice_channel_id = ?", (voice_channel_id,))
        await self._db.execute("DELETE FROM room_members WHERE voice_channel_id = ?", (voice_channel_id,))
        await self._db.commit()

    async def get_all_temp_voice_channels(self, guild_id: Optional[int] = None) -> List[DynamicRoom]:
        return await self.get_all_dynamic_rooms(guild_id)

    async def create_temp_voice_channel(self, channel_id: int, guild_id: int, owner_id: int) -> None:
        now_str = utcnow_iso()
        room = DynamicRoom(
            guild_id=guild_id,
            voice_channel_id=channel_id,
            owner_id=owner_id,
            room_type="public",
            privacy_mode="public",
            created_at=now_str,
            status="active",
        )
        await self.create_dynamic_room(room)

    async def get_temp_voice_channel(self, channel_id: int) -> Optional[DynamicRoom]:
        return await self.get_dynamic_room(channel_id)

    async def delete_temp_voice_channel(self, channel_id: int) -> None:
        await self.delete_dynamic_room(channel_id)

    async def add_room_member(self, voice_channel_id: int, user_id: int, permission_type: str = "view") -> None:
        now_str = utcnow_iso()
        await self._db.execute(
            "INSERT INTO room_members (voice_channel_id, user_id, permission_type, added_at) VALUES (?, ?, ?, ?)",
            (voice_channel_id, user_id, permission_type, now_str)
        )
        await self._db.commit()

    async def remove_room_member(self, voice_channel_id: int, user_id: int) -> None:
        await self._db.execute(
            "DELETE FROM room_members WHERE voice_channel_id = ? AND user_id = ?",
            (voice_channel_id, user_id)
        )
        await self._db.commit()

    async def get_room_members(self, voice_channel_id: int) -> List[RoomMember]:
        async with self._db.execute(
            "SELECT * FROM room_members WHERE voice_channel_id = ?", (voice_channel_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                RoomMember(
                    id=row["id"],
                    room_channel_id=row["voice_channel_id"],
                    member_id=row["user_id"],
                    permission_type=row["permission_type"],
                    added_at=row["added_at"],
                )
                for row in rows
            ]

    # --- ROOM TEMPLATES, EVENTS, & KNOCK REQUESTS ---

    async def save_room_template(self, guild_id: int, user_id: int, template_name: str, settings: str) -> None:
        now_str = utcnow_iso()
        await self._db.execute(
            """
            INSERT INTO room_templates (guild_id, user_id, template_name, settings, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, template_name, settings, now_str)
        )
        await self._db.commit()

    async def get_room_templates(self, guild_id: int, user_id: int) -> List[RoomTemplate]:
        async with self._db.execute(
            "SELECT * FROM room_templates WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
            (guild_id, user_id)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                RoomTemplate(
                    guild_id=row["guild_id"],
                    user_id=row["user_id"],
                    template_name=row["template_name"],
                    settings=row["settings"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    async def record_room_event(self, room_id: int, event_type: str, actor_id: int, metadata: str = "") -> None:
        now_str = utcnow_iso()
        await self._db.execute(
            """
            INSERT INTO room_events (room_id, event_type, actor_id, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (room_id, event_type, actor_id, metadata, now_str)
        )
        await self._db.commit()

    async def create_room_knock_request(
        self, room_id: int, user_id: int, expires_in_seconds: int = 120
    ) -> RoomKnockRequest:
        now = datetime.datetime.now(datetime.timezone.utc)
        now_str = now.isoformat()
        expires_at_str = (now + datetime.timedelta(seconds=expires_in_seconds)).isoformat()
        cursor = await self._db.execute(
            """
            INSERT INTO room_knock_requests (room_id, user_id, status, expires_at, created_at)
            VALUES (?, ?, 'pending', ?, ?)
            """,
            (room_id, user_id, expires_at_str, now_str)
        )
        req_id = cursor.lastrowid
        await self._db.commit()
        return RoomKnockRequest(
            id=req_id,
            room_id=room_id,
            user_id=user_id,
            status="pending",
            expires_at=expires_at_str,
            created_at=now_str
        )

    async def get_room_knock_request(self, request_id: int) -> Optional[RoomKnockRequest]:
        async with self._db.execute(
            "SELECT * FROM room_knock_requests WHERE id = ?", (request_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return RoomKnockRequest(
                id=row["id"],
                room_id=row["room_id"],
                user_id=row["user_id"],
                status=row["status"],
                expires_at=row["expires_at"],
                created_at=row["created_at"]
            )

    async def get_pending_knock_request(self, room_id: int, user_id: int) -> Optional[RoomKnockRequest]:
        now_str = utcnow_iso()
        async with self._db.execute(
            """
            SELECT * FROM room_knock_requests
            WHERE room_id = ? AND user_id = ? AND status = 'pending' AND expires_at > ?
            ORDER BY id DESC LIMIT 1
            """,
            (room_id, user_id, now_str)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return RoomKnockRequest(
                id=row["id"],
                room_id=row["room_id"],
                user_id=row["user_id"],
                status=row["status"],
                expires_at=row["expires_at"],
                created_at=row["created_at"]
            )

    async def update_room_knock_request_status(self, request_id: int, status: str) -> None:
        await self._db.execute(
            "UPDATE room_knock_requests SET status = ? WHERE id = ?",
            (status, request_id)
        )
        await self._db.commit()

    async def update_room_knock_request(self, request_id: int, status: str) -> None:
        await self.update_room_knock_request_status(request_id, status)

    # --- NATURAL LANGUAGE AUDIT CRUD ---

    async def record_nl_audit(
        self,
        incident_id: str,
        guild_id: int,
        user_id: int,
        user_name: str,
        channel_id: int,
        raw_message: str,
        intent: str,
        confidence: float,
        action: str,
        result: str,
    ) -> None:
        now_str = utcnow_iso()
        await self._db.execute(
            """
            INSERT INTO nl_audits (
                incident_id, guild_id, user_id, user_name, channel_id,
                raw_message, intent, confidence, action, result, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id, guild_id, user_id, user_name, channel_id,
                raw_message, intent, confidence, action, result, now_str
            )
        )
        await self._db.commit()

    async def get_recent_nl_audits(self, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        async with self._db.execute(
            """
            SELECT * FROM nl_audits
            WHERE guild_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (guild_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # --- AUTOPILOT CRUD ---

    async def get_or_create_autopilot_config(self, guild_id: int) -> AutopilotConfig:
        async with self._db.execute(
            "SELECT * FROM autopilot_configs WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return AutopilotConfig(
                    guild_id=row["guild_id"],
                    enabled=bool(row["enabled"]),
                    dry_run=bool(row["dry_run"]),
                    max_safety_level=row["max_safety_level"],
                    alert_channel_id=row["alert_channel_id"],
                    ticket_management=bool(row["ticket_management"]),
                    auto_safe_mode=bool(row["auto_safe_mode"]),
                    updated_at=row["updated_at"],
                )
        now_str = utcnow_iso()
        cfg = AutopilotConfig(guild_id=guild_id, updated_at=now_str)
        await self._db.execute(
            """
            INSERT INTO autopilot_configs (
                guild_id, enabled, dry_run, max_safety_level, alert_channel_id,
                ticket_management, auto_safe_mode, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, 1, 0, "HIGH", None, 1, 1, now_str)
        )
        await self._db.commit()
        return cfg

    async def update_autopilot_config(self, guild_id: int, **kwargs: Any) -> None:
        if not kwargs:
            return
        fields = []
        values = []
        for k, v in kwargs.items():
            if isinstance(v, bool):
                v = 1 if v else 0
            fields.append(f"{k} = ?")
            values.append(v)
        fields.append("updated_at = ?")
        values.append(utcnow_iso())
        values.append(guild_id)
        query = f"UPDATE autopilot_configs SET {', '.join(fields)} WHERE guild_id = ?"
        await self._db.execute(query, tuple(values))
        await self._db.commit()

    async def get_or_create_security_baseline(self, guild_id: int) -> SecurityBaseline:
        async with self._db.execute(
            "SELECT * FROM security_baselines WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                sb = SecurityBaseline(
                    guild_id=row["guild_id"],
                    joins_per_hour=row["joins_per_hour"],
                    messages_per_min=row["messages_per_min"],
                    voice_users=row["voice_users"],
                    updated_at=row["updated_at"],
                )
                sb.sample_count = row["sample_count"]
                sb.avg_joins_per_hour = row["avg_joins_per_hour"]
                sb.avg_messages_per_min = row["avg_messages_per_min"]
                return sb
        now_str = utcnow_iso()
        sb = SecurityBaseline(guild_id=guild_id, updated_at=now_str)
        sb.sample_count = 0
        sb.avg_joins_per_hour = 0.0
        sb.avg_messages_per_min = 0.0
        await self._db.execute(
            """
            INSERT INTO security_baselines (
                guild_id, joins_per_hour, messages_per_min, voice_users,
                sample_count, avg_joins_per_hour, avg_messages_per_min, updated_at
            ) VALUES (?, 0.0, 0.0, 0.0, 0, 0.0, 0.0, ?)
            """,
            (guild_id, now_str)
        )
        await self._db.commit()
        return sb

    async def update_security_baseline(self, guild_id: int, **kwargs: Any) -> None:
        if not kwargs:
            return
        fields = []
        values = []
        for k, v in kwargs.items():
            fields.append(f"{k} = ?")
            values.append(v)
        fields.append("updated_at = ?")
        values.append(utcnow_iso())
        values.append(guild_id)
        query = f"UPDATE security_baselines SET {', '.join(fields)} WHERE guild_id = ?"
        await self._db.execute(query, tuple(values))
        await self._db.commit()

    async def log_autopilot_action(
        self,
        guild_id: int,
        module: str,
        trigger: str,
        reason: str,
        risk_level: str,
        action: str,
        result: str,
        target_id: Optional[int] = None,
        target_type: Optional[str] = None,
        details: Optional[str] = None,
    ) -> str:
        action_id = f"AP-{uuid.uuid4().hex[:8].upper()}"
        now_str = utcnow_iso()
        if not self._db:
            return action_id

        async with self._db.execute("PRAGMA table_info(autopilot_actions)") as cursor:
            cols = {row[1] for row in await cursor.fetchall()}

        col_names = []
        vals = []
        if "action_id" in cols:
            col_names.append("action_id")
            vals.append(action_id)
        if "id" in cols:
            col_names.append("id")
            vals.append(action_id)

        col_names.extend(["guild_id", "module", "trigger", "reason", "risk_level", "action", "result"])
        vals.extend([guild_id, module, trigger, reason, risk_level, action, result])

        if "target_id" in cols:
            col_names.append("target_id")
            vals.append(target_id)
        if "target_type" in cols:
            col_names.append("target_type")
            vals.append(target_type)
        if "details" in cols:
            col_names.append("details")
            vals.append(details)

        if "timestamp" in cols:
            col_names.append("timestamp")
            vals.append(now_str)
        if "created_at" in cols:
            col_names.append("created_at")
            vals.append(now_str)

        placeholders = ", ".join("?" for _ in col_names)
        sql = f"INSERT INTO autopilot_actions ({', '.join(col_names)}) VALUES ({placeholders})"
        await self._db.execute(sql, tuple(vals))
        await self._db.commit()
        return action_id

    async def get_recent_autopilot_actions(self, guild_id: int, limit: int = 10) -> List[AutopilotAction]:
        """Fetch recent autopilot actions for a guild."""
        if not self._db:
            return []
        async with self._db.execute("PRAGMA table_info(autopilot_actions)") as cursor:
            cols = {row[1] for row in await cursor.fetchall()}
        order_col = "timestamp" if "timestamp" in cols else "created_at"
        async with self._db.execute(
            f"SELECT * FROM autopilot_actions WHERE guild_id = ? ORDER BY {order_col} DESC LIMIT ?",
            (guild_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                row_dict = dict(r)
                act_id = row_dict.get("id") or row_dict.get("action_id") or ""
                c_at = row_dict.get("created_at") or row_dict.get("timestamp") or ""
                results.append(
                    AutopilotAction(
                        id=act_id,
                        guild_id=row_dict["guild_id"],
                        module=row_dict["module"],
                        trigger=row_dict["trigger"],
                        reason=row_dict["reason"],
                        risk_level=row_dict["risk_level"],
                        action=row_dict["action"],
                        result=row_dict["result"],
                        target_id=row_dict.get("target_id"),
                        target_type=row_dict.get("target_type"),
                        details=row_dict.get("details"),
                        created_at=c_at,
                    )
                )
            return results


    # ==========================================
    # COMMUNITY PLATFORM EXPANSION METHODS
    # ==========================================

    async def get_or_create_gaming_profile(self, guild_id: int, user_id: int) -> dict:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        async with self._db.execute(
            "SELECT * FROM community_gaming_profiles WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)

        await self._db.execute(
            """
            INSERT OR IGNORE INTO community_gaming_profiles (user_id, guild_id, updated_at)
            VALUES (?, ?, ?)
            """,
            (user_id, guild_id, now_iso),
        )
        await self._db.commit()
        return {
            "user_id": user_id,
            "guild_id": guild_id,
            "games": "",
            "rank": "",
            "preferred_modes": "",
            "play_times": "",
            "mic_available": 1,
            "is_visible": 1,
            "updated_at": now_iso,
        }

    async def update_gaming_profile(self, guild_id: int, user_id: int, **kwargs: Any) -> None:
        await self.get_or_create_gaming_profile(guild_id, user_id)
        if not kwargs:
            return
        kwargs["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        set_clauses = [f"{k} = ?" for k in kwargs.keys()]
        params = list(kwargs.values()) + [guild_id, user_id]
        await self._db.execute(
            f"UPDATE community_gaming_profiles SET {', '.join(set_clauses)} WHERE guild_id = ? AND user_id = ?",
            params,
        )
        await self._db.commit()

    async def get_or_create_user_profile(self, guild_id: int, user_id: int) -> dict:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        async with self._db.execute(
            "SELECT * FROM community_user_profiles WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)

        await self._db.execute(
            """
            INSERT OR IGNORE INTO community_user_profiles (user_id, guild_id, updated_at)
            VALUES (?, ?, ?)
            """,
            (user_id, guild_id, now_iso),
        )
        await self._db.commit()
        return {
            "user_id": user_id,
            "guild_id": guild_id,
            "skills": "",
            "interests": "",
            "bio": "",
            "is_visible": 1,
            "updated_at": now_iso,
        }

    async def update_user_profile(self, guild_id: int, user_id: int, **kwargs: Any) -> None:
        await self.get_or_create_user_profile(guild_id, user_id)
        if not kwargs:
            return
        kwargs["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        set_clauses = [f"{k} = ?" for k in kwargs.keys()]
        params = list(kwargs.values()) + [guild_id, user_id]
        await self._db.execute(
            f"UPDATE community_user_profiles SET {', '.join(set_clauses)} WHERE guild_id = ? AND user_id = ?",
            params,
        )
        await self._db.commit()

    async def create_community_resource(
        self, guild_id: int, user_id: int, title: str, description: str, category: str, link: str
    ) -> int:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor = await self._db.execute(
            """
            INSERT INTO community_resources (guild_id, user_id, title, description, category, link, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'APPROVED', ?)
            """,
            (guild_id, user_id, title, description, category, link, now_iso),
        )
        await self._db.commit()
        return cursor.lastrowid or 0

    async def list_community_resources(self, guild_id: int, category: Optional[str] = None) -> List[dict]:
        if category:
            query = "SELECT * FROM community_resources WHERE guild_id = ? AND category = ? ORDER BY id DESC"
            params = (guild_id, category)
        else:
            query = "SELECT * FROM community_resources WHERE guild_id = ? ORDER BY id DESC LIMIT 25"
            params = (guild_id,)
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def list_resources(self, guild_id: int, category: Optional[str] = None, limit: int = 50) -> List[dict]:
        return await self.list_community_resources(guild_id, category=category)

    async def delete_community_resource(self, resource_id: int, guild_id: int, user_id: int, is_admin: bool = False) -> bool:
        if is_admin:
            cursor = await self._db.execute(
                "DELETE FROM community_resources WHERE id = ? AND guild_id = ?",
                (resource_id, guild_id),
            )
        else:
            cursor = await self._db.execute(
                "DELETE FROM community_resources WHERE id = ? AND guild_id = ? AND user_id = ?",
                (resource_id, guild_id, user_id),
            )
        await self._db.commit()
        return (cursor.rowcount or 0) > 0

    async def create_collaboration_request(
        self, guild_id: int, requester_id: int, target_id: int, skill: str, note: Optional[str]
    ) -> int:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor = await self._db.execute(
            """
            INSERT INTO community_collaborations (guild_id, requester_id, target_id, skill, note, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (guild_id, requester_id, target_id, skill, note or "", now_iso),
        )
        await self._db.commit()
        return cursor.lastrowid or 0

    async def list_collaborations(self, guild_id: int, user_id: int) -> List[dict]:
        async with self._db.execute(
            "SELECT * FROM community_collaborations WHERE guild_id = ? AND (requester_id = ? OR target_id = ?) ORDER BY id DESC LIMIT 10",
            (guild_id, user_id, user_id),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def update_collaboration_status(self, collab_id: int, status: str) -> bool:
        cursor = await self._db.execute(
            "UPDATE community_collaborations SET status = ? WHERE id = ?",
            (status, collab_id),
        )
        await self._db.commit()
        return (cursor.rowcount or 0) > 0

    async def get_or_create_notification_prefs(self, guild_id: int, user_id: int) -> dict:
        async with self._db.execute(
            "SELECT * FROM community_notification_prefs WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)

        await self._db.execute(
            """
            INSERT OR IGNORE INTO community_notification_prefs (user_id, guild_id)
            VALUES (?, ?)
            """,
            (user_id, guild_id),
        )
        await self._db.commit()
        return {
            "user_id": user_id,
            "guild_id": guild_id,
            "music_events": 1,
            "gaming_events": 1,
            "creator_events": 1,
            "community_events": 1,
            "idea_updates": 1,
            "reminders": 1,
        }

    async def update_notification_prefs(self, guild_id: int, user_id: int, **kwargs: Any) -> None:
        await self.get_or_create_notification_prefs(guild_id, user_id)
        if not kwargs:
            return
        set_clauses = [f"{k} = ?" for k in kwargs.keys()]
        params = list(kwargs.values()) + [guild_id, user_id]
        await self._db.execute(
            f"UPDATE community_notification_prefs SET {', '.join(set_clauses)} WHERE guild_id = ? AND user_id = ?",
            params,
        )
        await self._db.commit()

    async def get_or_create_module_settings(self, guild_id: int) -> dict:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        async with self._db.execute(
            "SELECT * FROM community_module_settings WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)

        await self._db.execute(
            """
            INSERT OR IGNORE INTO community_module_settings (guild_id, updated_at)
            VALUES (?, ?)
            """,
            (guild_id, now_iso),
        )
        await self._db.commit()
        return {
            "guild_id": guild_id,
            "music_enabled": 1,
            "dynamic_rooms_enabled": 1,
            "gaming_enabled": 1,
            "creator_enabled": 1,
            "events_enabled": 1,
            "reputation_enabled": 1,
            "resources_enabled": 1,
            "collaboration_enabled": 1,
            "updated_at": now_iso,
        }

    async def update_module_settings(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_or_create_module_settings(guild_id)
        if not kwargs:
            return
        kwargs["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        set_clauses = [f"{k} = ?" for k in kwargs.keys()]
        params = list(kwargs.values()) + [guild_id]
        await self._db.execute(
            f"UPDATE community_module_settings SET {', '.join(set_clauses)} WHERE guild_id = ?",
            params,
        )
        await self._db.commit()

    # ==========================================
    # 9. WEB PLATFORM & SESSIONS
    # ==========================================

    async def create_web_session(
        self,
        session_id: str,
        user_id: int,
        discord_user_id: int,
        username: str,
        discriminator: str = "0",
        avatar: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        expires_at: str = "",
        user_data_dict: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        data_json = json.dumps(user_data_dict or {})
        await self._db.execute(
            """
            INSERT INTO web_sessions (
                session_id, user_id, discord_user_id, username, discriminator,
                avatar, access_token, refresh_token, expires_at, user_data_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at,
                user_data_json = excluded.user_data_json
            """,
            (session_id, user_id, discord_user_id, username, discriminator, avatar, access_token, refresh_token, expires_at, data_json, now),
        )
        await self._db.commit()

    async def get_web_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        async with self._db.execute("SELECT * FROM web_sessions WHERE session_id = ?", (session_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res["user_data"] = json.loads(res.get("user_data_json", "{}"))
            except Exception:
                res["user_data"] = {}
            return res

    async def delete_web_session(self, session_id: str) -> bool:
        cur = await self._db.execute("DELETE FROM web_sessions WHERE session_id = ?", (session_id,))
        await self._db.commit()
        return (cur.rowcount or 0) > 0

    # ==========================================
    # 10. PROJECTS & TASKS
    # ==========================================

    async def create_project(
        self,
        guild_id: int,
        name: str,
        project_type: str,
        owner_id: int,
        category_id: Optional[int] = None,
        chat_channel_id: Optional[int] = None,
        voice_channel_id: Optional[int] = None,
    ) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = await self._db.execute(
            """
            INSERT INTO projects (guild_id, name, project_type, owner_id, status, category_id, chat_channel_id, voice_channel_id, created_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (guild_id, name, project_type, owner_id, category_id, chat_channel_id, voice_channel_id, now),
        )
        await self._db.commit()
        return cur.lastrowid or 0

    async def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        async with self._db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def list_projects(self, guild_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            query = "SELECT * FROM projects WHERE guild_id = ? AND status = ? ORDER BY id DESC"
            params = (guild_id, status)
        else:
            query = "SELECT * FROM projects WHERE guild_id = ? ORDER BY id DESC"
            params = (guild_id,)
        async with self._db.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def list_project_members(self, project_id: int) -> List[Dict[str, Any]]:
        proj = await self.get_project(project_id)
        if not proj:
            return []
        members = [{"user_id": proj["owner_id"], "role": "Founder"}]
        async with self._db.execute(
            "SELECT DISTINCT assignee_id FROM project_tasks WHERE project_id = ? AND assignee_id IS NOT NULL",
            (project_id,),
        ) as cur:
            rows = await cur.fetchall()
            for r in rows:
                if r[0] and r[0] != proj["owner_id"]:
                    members.append({"user_id": r[0], "role": "Contributor"})
        return members

    async def create_project_task(
        self,
        project_id: int,
        title: str,
        description: Optional[str] = None,
        status: str = "TODO",
        assignee_id: Optional[int] = None,
        priority: str = "NORMAL",
        due_date: Optional[str] = None,
    ) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = await self._db.execute(
            """
            INSERT INTO project_tasks (project_id, title, description, status, assignee_id, priority, due_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, title.strip(), description or "", status.upper(), assignee_id, priority.upper(), due_date, now, now),
        )
        await self._db.commit()
        return cur.lastrowid or 0

    async def list_project_tasks(self, project_id: int) -> List[Dict[str, Any]]:
        async with self._db.execute(
            "SELECT * FROM project_tasks WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def update_project_task_status(self, task_id: int, status: str) -> bool:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = await self._db.execute(
            "UPDATE project_tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status.upper(), now, task_id),
        )
        await self._db.commit()
        return (cur.rowcount or 0) > 0

    async def delete_project_task(self, task_id: int) -> bool:
        cur = await self._db.execute("DELETE FROM project_tasks WHERE id = ?", (task_id,))
        await self._db.commit()
        return (cur.rowcount or 0) > 0

    # ==========================================
    # 11. CREATOR PORTFOLIOS
    # ==========================================

    async def create_creator_portfolio(
        self,
        user_id: int,
        title: str,
        description: str,
        category: str,
        media_url: Optional[str] = None,
        tools_used: Optional[str] = None,
        tags: Optional[str] = None,
        external_links: Optional[str] = None,
        is_featured: bool = False,
    ) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = await self._db.execute(
            """
            INSERT INTO creator_portfolios (
                user_id, title, description, category, media_url, tools_used, tags, external_links, is_featured, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, title.strip(), description.strip(), category, media_url or "", tools_used or "", tags or "", external_links or "", 1 if is_featured else 0, now),
        )
        await self._db.commit()
        return cur.lastrowid or 0

    async def list_creator_portfolios(self, category: Optional[str] = None, user_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        clauses = []
        params = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM creator_portfolios {where} ORDER BY is_featured DESC, id DESC LIMIT ?"
        params.append(limit)
        async with self._db.execute(query, tuple(params)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_creator_portfolio(self, portfolio_id: int) -> Optional[Dict[str, Any]]:
        async with self._db.execute("SELECT * FROM creator_portfolios WHERE id = ?", (portfolio_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def delete_creator_portfolio(self, portfolio_id: int, user_id: int, is_admin: bool = False) -> bool:
        if is_admin:
            cur = await self._db.execute("DELETE FROM creator_portfolios WHERE id = ?", (portfolio_id,))
        else:
            cur = await self._db.execute("DELETE FROM creator_portfolios WHERE id = ? AND user_id = ?", (portfolio_id, user_id))
        await self._db.commit()
        return (cur.rowcount or 0) > 0

    # ==========================================
    # 12. COMMUNITY IDEAS & VOTING
    # ==========================================

    async def create_community_idea(
        self,
        guild_id: int,
        user_id: int,
        author_name: str,
        title: str,
        description: str,
        category: str = "Community",
        tags: str = "",
    ) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = await self._db.execute(
            """
            INSERT INTO community_ideas (guild_id, user_id, author_name, title, description, category, tags, status, votes_count, comments_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW', 1, 0, ?, ?)
            """,
            (guild_id, user_id, author_name, title.strip(), description.strip(), category, tags, now, now),
        )
        idea_id = cur.lastrowid or 0
        # Auto upvote by creator
        await self._db.execute(
            "INSERT INTO idea_votes (idea_id, user_id, direction, created_at) VALUES (?, ?, 1, ?)",
            (idea_id, user_id, now),
        )
        await self._db.commit()
        return idea_id

    async def list_community_ideas(self, guild_id: Optional[int] = None, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        clauses = []
        params = []
        if guild_id:
            clauses.append("guild_id = ?")
            params.append(guild_id)
        if status:
            clauses.append("status = ?")
            params.append(status.upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM community_ideas {where} ORDER BY votes_count DESC, id DESC LIMIT ?"
        params.append(limit)
        async with self._db.execute(query, tuple(params)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_community_idea(self, idea_id: int) -> Optional[Dict[str, Any]]:
        async with self._db.execute("SELECT * FROM community_ideas WHERE id = ?", (idea_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def vote_community_idea(self, idea_id: int, user_id: int, direction: int) -> Dict[str, Any]:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        dir_val = 1 if direction > 0 else -1
        async with self._db.execute("SELECT direction FROM idea_votes WHERE idea_id = ? AND user_id = ?", (idea_id, user_id)) as cur:
            prev = await cur.fetchone()

        if prev:
            if prev[0] == dir_val:
                # Remove vote
                await self._db.execute("DELETE FROM idea_votes WHERE idea_id = ? AND user_id = ?", (idea_id, user_id))
                delta = -dir_val
            else:
                # Flip vote
                await self._db.execute("UPDATE idea_votes SET direction = ?, created_at = ? WHERE idea_id = ? AND user_id = ?", (dir_val, now, idea_id, user_id))
                delta = dir_val * 2
        else:
            await self._db.execute("INSERT INTO idea_votes (idea_id, user_id, direction, created_at) VALUES (?, ?, ?, ?)", (idea_id, user_id, dir_val, now))
            delta = dir_val

        await self._db.execute("UPDATE community_ideas SET votes_count = votes_count + ?, updated_at = ? WHERE id = ?", (delta, now, idea_id))
        await self._db.commit()

        idea = await self.get_community_idea(idea_id)
        return idea or {}

    async def add_idea_comment(self, idea_id: int, user_id: int, author_name: str, content: str) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = await self._db.execute(
            "INSERT INTO idea_comments (idea_id, user_id, author_name, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (idea_id, user_id, author_name, content.strip(), now),
        )
        await self._db.execute("UPDATE community_ideas SET comments_count = comments_count + 1, updated_at = ? WHERE id = ?", (now, idea_id))
        await self._db.commit()
        return cur.lastrowid or 0

    async def list_idea_comments(self, idea_id: int) -> List[Dict[str, Any]]:
        async with self._db.execute("SELECT * FROM idea_comments WHERE idea_id = ? ORDER BY id ASC", (idea_id,)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def update_idea_status(self, idea_id: int, status: str) -> bool:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = await self._db.execute("UPDATE community_ideas SET status = ?, updated_at = ? WHERE id = ?", (status.upper(), now, idea_id))
        await self._db.commit()
        return (cur.rowcount or 0) > 0

    # ==========================================
    # 13. NOTIFICATIONS
    # ==========================================

    async def create_community_notification(
        self,
        user_id: int,
        guild_id: int,
        notification_type: str,
        title: str,
        message: str,
        link: Optional[str] = None,
        priority: str = "NORMAL",
    ) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = await self._db.execute(
            """
            INSERT INTO community_notifications (user_id, guild_id, notification_type, title, message, link, is_read, priority, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (user_id, guild_id, notification_type, title, message, link or "", priority.upper(), now),
        )
        await self._db.commit()
        return cur.lastrowid or 0

    async def list_community_notifications(self, user_id: int, limit: int = 30, unread_only: bool = False) -> List[Dict[str, Any]]:
        where = "WHERE user_id = ?"
        params: List[Any] = [user_id]
        if unread_only:
            where += " AND is_read = 0"
        query = f"SELECT * FROM community_notifications {where} ORDER BY id DESC LIMIT ?"
        params.append(limit)
        async with self._db.execute(query, tuple(params)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def mark_notification_read(self, notification_id: int, user_id: int) -> bool:
        cur = await self._db.execute(
            "UPDATE community_notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
            (notification_id, user_id),
        )
        await self._db.commit()
        return (cur.rowcount or 0) > 0

    async def mark_all_notifications_read(self, user_id: int) -> int:
        cur = await self._db.execute(
            "UPDATE community_notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0",
            (user_id,),
        )
        await self._db.commit()
        return cur.rowcount or 0

    async def count_unread_notifications(self, user_id: int) -> int:
        async with self._db.execute("SELECT COUNT(*) FROM community_notifications WHERE user_id = ? AND is_read = 0", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

    async def create_community_event(
        self,
        title: str,
        description: str,
        start_time: str,
        end_time: Optional[str] = None,
        location: str = "Discord Voice",
        creator_id: int = 0,
        guild_id: int = 0,
        event_type: str = "General",
        status: str = "scheduled",
        **kwargs: Any,
    ) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = await self._db.execute(
            """INSERT INTO events (guild_id, title, event_type, start_time, description, creator_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (guild_id, title, event_type, start_time, description, creator_id, status, now),
        )
        await self._db.execute(
            """INSERT INTO community_events (guild_id, title, description, event_type, start_time, end_time, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (guild_id, title, description, event_type, start_time, end_time or "", status, now),
        )
        await self._db.commit()
        return cur.lastrowid or 0

    # ==========================================
    # 14. WIKI & KNOWLEDGE
    # ==========================================

    async def get_or_create_wiki_article(
        self,
        slug: str,
        title: str,
        category: str,
        content: str,
        author_id: int = 0,
    ) -> Dict[str, Any]:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = await self._db.execute(
            """
            INSERT INTO wiki_articles (slug, title, category, content, author_id, is_published, version, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, 1, ?)
            ON CONFLICT(slug) DO UPDATE SET
                title = excluded.title,
                category = excluded.category,
                content = excluded.content,
                version = wiki_articles.version + 1,
                updated_at = excluded.updated_at
            """,
            (slug.strip().lower(), title.strip(), category.strip(), content.strip(), author_id, now),
        )
        await self._db.commit()
        article = await self.get_wiki_article(slug)
        return article or {}

    async def list_wiki_articles(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        if category:
            query = "SELECT * FROM wiki_articles WHERE category = ? AND is_published = 1 ORDER BY title ASC"
            params = (category,)
        else:
            query = "SELECT * FROM wiki_articles WHERE is_published = 1 ORDER BY category ASC, title ASC"
            params = ()
        async with self._db.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_wiki_article(self, slug: str) -> Optional[Dict[str, Any]]:
        async with self._db.execute("SELECT * FROM wiki_articles WHERE slug = ?", (slug.strip().lower(),)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    # ==========================================
    # 15. ACHIEVEMENTS
    # ==========================================

    async def award_community_achievement(
        self, user_id: int, badge_id: str, title: str, description: str, icon: str = "🏆"
    ) -> bool:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            await self._db.execute(
                """
                INSERT INTO community_achievements (user_id, badge_id, title, description, icon, unlocked_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, badge_id) DO NOTHING
                """,
                (user_id, badge_id, title, description, icon, now),
            )
            await self._db.commit()
            return True
        except Exception:
            return False

    async def list_community_achievements(self, user_id: int) -> List[Dict[str, Any]]:
        async with self._db.execute(
            "SELECT * FROM community_achievements WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ==========================================
    # 16. SYNC OUTBOX & AUDIT LOGS
    # ==========================================

    async def enqueue_sync_event(
        self,
        event_id: str,
        event_type: str,
        entity_id: str,
        payload_dict: Dict[str, Any],
        source: str = "web",
    ) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        payload_json = json.dumps(payload_dict)
        cur = await self._db.execute(
            """
            INSERT INTO sync_outbox (event_id, event_type, entity_id, source, payload_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
            ON CONFLICT(event_id) DO NOTHING
            """,
            (event_id, event_type, entity_id, source, payload_json, now),
        )
        await self._db.commit()
        return cur.lastrowid or 0

    async def fetch_pending_sync_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        async with self._db.execute(
            "SELECT * FROM sync_outbox WHERE status = 'PENDING' AND retry_count < 5 ORDER BY id ASC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            res = []
            for r in rows:
                item = dict(r)
                try:
                    item["payload"] = json.loads(item.get("payload_json", "{}"))
                except Exception:
                    item["payload"] = {}
                res.append(item)
            return res

    async def mark_sync_event_processed(self, event_id: str) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await self._db.execute(
            "UPDATE sync_outbox SET status = 'PROCESSED', processed_at = ? WHERE event_id = ?",
            (now, event_id),
        )
        await self._db.commit()

    async def mark_sync_event_failed(self, event_id: str, error_msg: str) -> None:
        await self._db.execute(
            "UPDATE sync_outbox SET status = 'FAILED', retry_count = retry_count + 1, last_error = ? WHERE event_id = ?",
            (error_msg[:500], event_id),
        )
        await self._db.commit()

    async def log_community_audit(
        self,
        actor_id: int,
        actor_name: str,
        action: str,
        target_type: str,
        target_id: Optional[str] = None,
        details_dict: Optional[Dict[str, Any]] = None,
    ) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = await self._db.execute(
            """
            INSERT INTO community_audit_logs (actor_id, actor_name, action, target_type, target_id, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (actor_id, actor_name, action, target_type, target_id or "", json.dumps(details_dict or {}), now),
        )
        await self._db.commit()
        return cur.lastrowid or 0

    async def list_community_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        async with self._db.execute(
            "SELECT * FROM community_audit_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            res = []
            for r in rows:
                item = dict(r)
                try:
                    item["details"] = json.loads(item.get("details_json", "{}"))
                except Exception:
                    item["details"] = {}
                res.append(item)
            return res


    # ==========================================
    # TEMPORARY / DYNAMIC VOICE CONFIG
    # ==========================================

    async def get_temp_voice_config(self, guild_id: int) -> TempVoiceConfig:
        await self.get_or_create_guild_config(guild_id)
        if not self._db:
            return TempVoiceConfig(guild_id=guild_id)
        async with self._db.execute(
            "SELECT * FROM temp_voice_configs WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            now = utcnow_iso()
            await self._db.execute(
                """
                INSERT OR IGNORE INTO temp_voice_configs (
                    guild_id, enabled, hub_channel_id, category_id, default_user_limit,
                    name_format, updated_at
                ) VALUES (?, 0, NULL, NULL, 0, '🎙️ {username}''s Room', ?)
                """,
                (guild_id, now),
            )
            await self._db.commit()
            return TempVoiceConfig(guild_id=guild_id, updated_at=now)

        return TempVoiceConfig(
            guild_id=row["guild_id"],
            enabled=bool(row["enabled"]),
            hub_channel_id=row["hub_channel_id"],
            category_id=row["category_id"],
            default_user_limit=row["default_user_limit"],
            name_format=row["name_format"] or "🎙️ {username}'s Room",
            updated_at=row["updated_at"] or "",
        )

    async def update_temp_voice_config(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_temp_voice_config(guild_id)
        if not self._db:
            return
        valid = {"enabled", "hub_channel_id", "category_id", "default_user_limit", "name_format"}
        updates = {k: (int(v) if isinstance(v, bool) else v) for k, v in kwargs.items() if k in valid}
        if not updates:
            return
        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]
        sql = f"UPDATE temp_voice_configs SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    # ==========================================
    # SERVER STATS COUNTER CONFIG
    # ==========================================

    async def get_or_create_server_stats_config(self, guild_id: int) -> ServerStatsConfig:
        await self.get_or_create_guild_config(guild_id)
        if not self._db:
            return ServerStatsConfig(guild_id=guild_id)
        async with self._db.execute(
            "SELECT * FROM server_stats_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            now = utcnow_iso()
            await self._db.execute(
                """
                INSERT OR IGNORE INTO server_stats_config (
                    guild_id, enabled, category_id, all_members_channel_id,
                    members_channel_id, bots_channel_id, updated_at
                ) VALUES (?, 0, NULL, NULL, NULL, NULL, ?)
                """,
                (guild_id, now),
            )
            await self._db.commit()
            return ServerStatsConfig(guild_id=guild_id, enabled=False, updated_at=now)

        return ServerStatsConfig(
            guild_id=row["guild_id"],
            enabled=bool(row["enabled"]),
            category_id=row["category_id"],
            all_members_channel_id=row["all_members_channel_id"],
            members_channel_id=row["members_channel_id"],
            bots_channel_id=row["bots_channel_id"],
            updated_at=row["updated_at"],
        )

    async def update_server_stats_config(
        self,
        guild_id: int,
        enabled: Optional[int] = None,
        category_id: Optional[int] = None,
        all_members_channel_id: Optional[int] = None,
        members_channel_id: Optional[int] = None,
        bots_channel_id: Optional[int] = None,
    ) -> None:
        await self.get_or_create_server_stats_config(guild_id)
        if not self._db:
            return
        fields = []
        values = []
        if enabled is not None:
            fields.append("enabled = ?")
            values.append(int(enabled))
        if category_id is not None:
            fields.append("category_id = ?")
            values.append(category_id)
        if all_members_channel_id is not None:
            fields.append("all_members_channel_id = ?")
            values.append(all_members_channel_id)
        if members_channel_id is not None:
            fields.append("members_channel_id = ?")
            values.append(members_channel_id)
        if bots_channel_id is not None:
            fields.append("bots_channel_id = ?")
            values.append(bots_channel_id)

        fields.append("updated_at = ?")
        values.append(utcnow_iso())
        values.append(guild_id)

        query = f"UPDATE server_stats_config SET {', '.join(fields)} WHERE guild_id = ?"
        await self._db.execute(query, tuple(values))
        await self._db.commit()


    # ==========================================
    # HIDDEN VOICE ROOMS
    # ==========================================

    async def get_hidden_voice_config(self, guild_id: int) -> HiddenVoiceConfig:
        await self.get_or_create_guild_config(guild_id)
        if not self._db:
            return HiddenVoiceConfig(guild_id=guild_id)
        async with self._db.execute(
            "SELECT * FROM hidden_voice_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            now = utcnow_iso()
            await self._db.execute(
                """
                INSERT OR IGNORE INTO hidden_voice_config (
                    guild_id, enabled, max_rooms_per_user, max_users_per_room,
                    empty_grace_period, allow_invited_members, allow_ownership_transfer,
                    staff_can_view_hidden_rooms, automatic_cleanup, automatic_owner_transfer,
                    room_name_format, updated_at
                ) VALUES (?, 1, 1, 99, 60, 1, 1, 0, 1, 0, '🔒・{username}-private', ?)
                """,
                (guild_id, now),
            )
            await self._db.commit()
            return HiddenVoiceConfig(guild_id=guild_id, updated_at=now)

        return HiddenVoiceConfig(
            guild_id=row["guild_id"],
            enabled=bool(row["enabled"]),
            category_id=row["category_id"],
            entry_channel_id=row["entry_channel_id"],
            max_rooms_per_user=row["max_rooms_per_user"],
            max_users_per_room=row["max_users_per_room"],
            empty_grace_period=row["empty_grace_period"],
            allow_invited_members=bool(row["allow_invited_members"]),
            allow_ownership_transfer=bool(row["allow_ownership_transfer"]),
            staff_can_view_hidden_rooms=bool(row["staff_can_view_hidden_rooms"]),
            automatic_cleanup=bool(row["automatic_cleanup"]),
            automatic_owner_transfer=bool(row["automatic_owner_transfer"]),
            room_name_format=row["room_name_format"] or "🔒・{username}-private",
            updated_at=row["updated_at"] or "",
        )

    async def update_hidden_voice_config(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_hidden_voice_config(guild_id)
        if not self._db:
            return
        valid = {
            "enabled", "category_id", "entry_channel_id", "max_rooms_per_user",
            "max_users_per_room", "empty_grace_period", "allow_invited_members",
            "allow_ownership_transfer", "staff_can_view_hidden_rooms",
            "automatic_cleanup", "automatic_owner_transfer", "room_name_format"
        }
        updates = {k: (int(v) if isinstance(v, bool) else v) for k, v in kwargs.items() if k in valid}
        if not updates:
            return

        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]

        sql = f"UPDATE hidden_voice_config SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    async def create_hidden_voice_room(
        self, channel_id: int, guild_id: int, owner_id: int, name: str, user_limit: int = 0
    ) -> None:
        await self.get_or_create_guild_config(guild_id)
        if not self._db:
            return
        now = utcnow_iso()
        await self._db.execute(
            """
            INSERT OR REPLACE INTO hidden_voice_rooms (
                channel_id, guild_id, owner_id, created_at, last_activity,
                invited_members, room_status, user_limit, is_locked, is_hidden, name
            ) VALUES (?, ?, ?, ?, ?, '[]', 'active', ?, 0, 1, ?)
            """,
            (channel_id, guild_id, owner_id, now, now, user_limit, name),
        )
        await self._db.commit()

    async def get_hidden_voice_room(self, channel_id: int) -> Optional[HiddenVoiceRoom]:
        if not self._db:
            return None
        async with self._db.execute(
            "SELECT * FROM hidden_voice_rooms WHERE channel_id = ?", (channel_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            invited = []
            try:
                invited = json.loads(row["invited_members"] or "[]")
            except Exception:
                invited = []
            return HiddenVoiceRoom(
                channel_id=row["channel_id"],
                guild_id=row["guild_id"],
                owner_id=row["owner_id"],
                created_at=row["created_at"],
                last_activity=row["last_activity"],
                invited_members=invited,
                room_status=row["room_status"] or "active",
                user_limit=row["user_limit"] or 0,
                is_locked=bool(row["is_locked"]),
                is_hidden=bool(row["is_hidden"]),
                name=row["name"] or "",
                grace_period_until=row["grace_period_until"],
                transferred_from=row["transferred_from"],
            )

    async def get_hidden_voice_rooms_by_owner(self, guild_id: int, owner_id: int) -> List[HiddenVoiceRoom]:
        if not self._db:
            return []
        async with self._db.execute(
            "SELECT * FROM hidden_voice_rooms WHERE guild_id = ? AND owner_id = ?",
            (guild_id, owner_id),
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                invited = []
                try:
                    invited = json.loads(row["invited_members"] or "[]")
                except Exception:
                    invited = []
                results.append(
                    HiddenVoiceRoom(
                        channel_id=row["channel_id"],
                        guild_id=row["guild_id"],
                        owner_id=row["owner_id"],
                        created_at=row["created_at"],
                        last_activity=row["last_activity"],
                        invited_members=invited,
                        room_status=row["room_status"] or "active",
                        user_limit=row["user_limit"] or 0,
                        is_locked=bool(row["is_locked"]),
                        is_hidden=bool(row["is_hidden"]),
                        name=row["name"] or "",
                        grace_period_until=row["grace_period_until"],
                        transferred_from=row["transferred_from"],
                    )
                )
            return results

    async def record_permission_failure(
        self,
        incident_id: str,
        guild_id: int,
        action: str,
        failure_type: str,
        reason: str,
        subsystem: str = "Core",
        channel_id: Optional[int] = None,
        target_id: Optional[int] = None,
        required_permission: Optional[str] = None,
        fallback_used: bool = False,
    ) -> Optional[int]:
        """Records a permission failure incident into SQLite with failure isolation."""
        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cursor = await self._db.execute(
                """
                INSERT INTO permission_failures (
                    incident_id, guild_id, channel_id, target_id, action,
                    failure_type, required_permission, subsystem, reason,
                    fallback_used, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    guild_id,
                    channel_id,
                    target_id,
                    action,
                    failure_type,
                    required_permission,
                    subsystem,
                    reason,
                    1 if fallback_used else 0,
                    now_iso,
                ),
            )
            await self._db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.warning(f"Could not record permission failure in DB (incident {incident_id}): {e}")
            return None

    async def get_recent_permission_failures(
        self, guild_id: int, limit: int = 10
    ) -> List[PermissionFailureRecord]:
        """Fetch recent permission failure incidents for a guild."""
        try:
            async with self._db.execute(
                """
                SELECT * FROM permission_failures
                WHERE guild_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (guild_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                results = []
                for r in rows:
                    results.append(
                        PermissionFailureRecord(
                            id=r["id"],
                            incident_id=r["incident_id"],
                            guild_id=r["guild_id"],
                            channel_id=r["channel_id"],
                            target_id=r["target_id"],
                            action=r["action"],
                            failure_type=r["failure_type"],
                            required_permission=r["required_permission"],
                            subsystem=r["subsystem"],
                            reason=r["reason"],
                            fallback_used=bool(r["fallback_used"]),
                            created_at=r["created_at"],
                        )
                    )
                return results
        except Exception as e:
            logger.warning(f"Could not fetch permission failures from DB for guild {guild_id}: {e}")
            return []

    async def get_all_hidden_voice_rooms(self, guild_id: Optional[int] = None) -> List[HiddenVoiceRoom]:
        if not self._db:
            return []
        query = "SELECT * FROM hidden_voice_rooms"
        params = ()
        if guild_id:
            query += " WHERE guild_id = ?"
            params = (guild_id,)
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                invited = []
                try:
                    invited = json.loads(row["invited_members"] or "[]")
                except Exception:
                    invited = []
                results.append(
                    HiddenVoiceRoom(
                        channel_id=row["channel_id"],
                        guild_id=row["guild_id"],
                        owner_id=row["owner_id"],
                        created_at=row["created_at"],
                        last_activity=row["last_activity"],
                        invited_members=invited,
                        room_status=row["room_status"] or "active",
                        user_limit=row["user_limit"] or 0,
                        is_locked=bool(row["is_locked"]),
                        is_hidden=bool(row["is_hidden"]),
                        name=row["name"] or "",
                        grace_period_until=row["grace_period_until"],
                        transferred_from=row["transferred_from"],
                    )
                )
            return results

    async def update_hidden_voice_room(self, channel_id: int, **kwargs: Any) -> None:
        if not self._db:
            return
        valid = {
            "owner_id", "last_activity", "invited_members", "room_status",
            "user_limit", "is_locked", "is_hidden", "name", "grace_period_until",
            "transferred_from"
        }
        updates: Dict[str, Any] = {}
        for k, v in kwargs.items():
            if k not in valid:
                continue
            if k == "invited_members" and isinstance(v, list):
                updates[k] = json.dumps(v)
            elif isinstance(v, bool):
                updates[k] = 1 if v else 0
            else:
                updates[k] = v

        if not updates:
            return

        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [channel_id]
        sql = f"UPDATE hidden_voice_rooms SET {', '.join(set_clauses)} WHERE channel_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    async def delete_hidden_voice_room(self, channel_id: int) -> None:
        if not self._db:
            return
        await self._db.execute("DELETE FROM hidden_voice_rooms WHERE channel_id = ?", (channel_id,))
        await self._db.commit()

    # ==========================================
    # MUSIC CONFIG & PLAYLISTS
    # ==========================================

    async def get_music_config(self, guild_id: int) -> MusicConfig:
        await self.get_or_create_guild_config(guild_id)
        if not self._db:
            return MusicConfig(guild_id=guild_id)
        async with self._db.execute(
            "SELECT * FROM music_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            now = utcnow_iso()
            await self._db.execute(
                """
                INSERT OR IGNORE INTO music_config (
                    guild_id, default_volume, autoplay_enabled, inactivity_timeout, updated_at
                ) VALUES (?, 50, 0, 180, ?)
                """,
                (guild_id, now),
            )
            await self._db.commit()
            return MusicConfig(guild_id=guild_id, updated_at=now)

        return MusicConfig(
            guild_id=row["guild_id"],
            dj_role_id=row["dj_role_id"],
            request_channel_id=row["request_channel_id"],
            default_volume=row["default_volume"],
            autoplay_enabled=bool(row["autoplay_enabled"]),
            inactivity_timeout=row["inactivity_timeout"],
            updated_at=row["updated_at"] or "",
        )

    async def update_music_config(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_music_config(guild_id)
        if not self._db:
            return
        valid = {"dj_role_id", "request_channel_id", "default_volume", "autoplay_enabled", "inactivity_timeout"}
        updates = {k: (int(v) if isinstance(v, bool) else v) for k, v in kwargs.items() if k in valid}
        if not updates:
            return

        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]
        sql = f"UPDATE music_config SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    async def create_music_playlist(
        self, guild_id: int, user_id: int, name: str, tracks: List[Dict[str, Any]], is_guild: bool = False
    ) -> int:
        await self.get_or_create_guild_config(guild_id)
        if not self._db:
            return 0
        now = utcnow_iso()
        tracks_json = json.dumps(tracks)
        async with self._db.execute(
            """
            INSERT INTO music_playlists (guild_id, user_id, name, tracks_json, is_guild_playlist, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id, name) DO UPDATE SET
                tracks_json = excluded.tracks_json,
                updated_at = excluded.updated_at
            RETURNING id;
            """,
            (guild_id, user_id, name, tracks_json, 1 if is_guild else 0, now, now),
        ) as cursor:
            row = await cursor.fetchone()
            await self._db.commit()
            return row[0] if row else 0

    async def get_music_playlist(self, guild_id: int, user_id: int, name: str) -> Optional[MusicPlaylist]:
        if not self._db:
            return None
        async with self._db.execute(
            "SELECT * FROM music_playlists WHERE guild_id = ? AND user_id = ? AND name = ?",
            (guild_id, user_id, name),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            tracks = []
            try:
                tracks = json.loads(row["tracks_json"] or "[]")
            except Exception:
                tracks = []
            return MusicPlaylist(
                id=row["id"],
                guild_id=row["guild_id"],
                user_id=row["user_id"],
                name=row["name"],
                tracks=tracks,
                is_guild_playlist=bool(row["is_guild_playlist"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def list_music_playlists(self, guild_id: int, user_id: int) -> List[MusicPlaylist]:
        if not self._db:
            return []
        async with self._db.execute(
            "SELECT * FROM music_playlists WHERE guild_id = ? AND (user_id = ? OR is_guild_playlist = 1) ORDER BY name ASC",
            (guild_id, user_id),
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                tracks = []
                try:
                    tracks = json.loads(row["tracks_json"] or "[]")
                except Exception:
                    tracks = []
                results.append(
                    MusicPlaylist(
                        id=row["id"],
                        guild_id=row["guild_id"],
                        user_id=row["user_id"],
                        name=row["name"],
                        tracks=tracks,
                        is_guild_playlist=bool(row["is_guild_playlist"]),
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                )
            return results

    async def update_music_playlist_tracks(self, playlist_id: int, tracks: List[Dict[str, Any]]) -> None:
        if not self._db:
            return
        now = utcnow_iso()
        await self._db.execute(
            "UPDATE music_playlists SET tracks_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(tracks), now, playlist_id),
        )
        await self._db.commit()

    async def delete_music_playlist(self, guild_id: int, user_id: int, name: str) -> bool:
        if not self._db:
            return False
        cursor = await self._db.execute(
            "DELETE FROM music_playlists WHERE guild_id = ? AND user_id = ? AND name = ?",
            (guild_id, user_id, name),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def run_retention_cleanup(
        self,
        command_metric_retention_days: int = 30,
        workflow_event_retention_days: int = 30,
        room_event_retention_days: int = 14,
        non_critical_incident_retention_days: int = 90,
    ) -> Dict[str, int]:
        """
        Executes bounded, policy-driven data retention cleanups:
        - Old command metrics older than configured threshold (default 30 days)
        - Old workflow events older than configured threshold (default 30 days)
        - Old room events older than configured threshold (default 14 days)
        - Old resolved non-critical incidents older than configured threshold (default 90 days)
          CRITICAL security records (severity 'critical' or 'emergency') are preserved according to policy.
        """
        counts: Dict[str, int] = {
            "command_metrics": 0,
            "workflow_events": 0,
            "room_events": 0,
            "non_critical_incidents": 0,
            "expired_cooldowns": 0,
        }
        if not self._db:
            return counts

        now_dt = datetime.datetime.now(datetime.timezone.utc)
        now_ts = now_dt.timestamp()

        # 1. Command metrics
        cutoff_cmd = now_dt - datetime.timedelta(days=command_metric_retention_days)
        cursor = await self._db.execute(
            "DELETE FROM command_metrics WHERE timestamp <= ?",
            (cutoff_cmd.isoformat(),),
        )
        counts["command_metrics"] = cursor.rowcount

        # 2. Workflow events
        cutoff_wf = now_dt - datetime.timedelta(days=workflow_event_retention_days)
        cursor = await self._db.execute(
            "DELETE FROM workflow_events WHERE created_at <= ?",
            (cutoff_wf.isoformat(),),
        )
        counts["workflow_events"] = cursor.rowcount

        # 3. Room events
        cutoff_room = now_ts - (room_event_retention_days * 86400)
        cutoff_room_iso = (now_dt - datetime.timedelta(days=room_event_retention_days)).isoformat()
        cursor = await self._db.execute(
            "DELETE FROM room_events WHERE timestamp <= ? OR timestamp <= ?",
            (str(cutoff_room), cutoff_room_iso),
        )
        counts["room_events"] = cursor.rowcount

        # 4. Old non-critical incidents (severity NOT IN ('critical', 'emergency'))
        cutoff_inc = now_dt - datetime.timedelta(days=non_critical_incident_retention_days)
        cursor = await self._db.execute(
            """
            DELETE FROM security_incidents
            WHERE timestamp <= ? AND severity NOT IN ('critical', 'emergency')
            """,
            (cutoff_inc.isoformat(),),
        )
        counts["non_critical_incidents"] = cursor.rowcount

        # 5. Expired persistent cooldowns
        cursor = await self._db.execute(
            "DELETE FROM persistent_cooldowns WHERE expires_at <= ?",
            (now_dt.isoformat(),),
        )
        counts["expired_cooldowns"] = cursor.rowcount

        await self._db.commit()
        logger.info(f"Retention policy cleanup executed: {counts}")
        return counts

    async def rename_music_playlist(self, guild_id: int, user_id: int, old_name: str, new_name: str) -> bool:
        if not self._db:
            return False
        now = utcnow_iso()
        cursor = await self._db.execute(
            "UPDATE music_playlists SET name = ?, updated_at = ? WHERE guild_id = ? AND user_id = ? AND name = ?",
            (new_name, now, guild_id, user_id, old_name),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    # ==========================================
    # COMMUNITY EVENTS
    # ==========================================

    async def create_event(
        self, guild_id: int, title: str, event_type: str, start_time: str, description: str, creator_id: int, channel_id: Optional[int] = None
    ) -> int:
        await self.get_or_create_guild_config(guild_id)
        if not self._db:
            return 0
        now = utcnow_iso()
        async with self._db.execute(
            """
            INSERT INTO events (guild_id, title, event_type, start_time, description, creator_id, channel_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'scheduled', ?)
            RETURNING id;
            """,
            (guild_id, title, event_type, start_time, description, creator_id, channel_id, now),
        ) as cursor:
            row = await cursor.fetchone()
            await self._db.commit()
            return row[0] if row else 0

    async def get_event(self, event_id: int) -> Optional[CommunityEvent]:
        if not self._db:
            return None
        async with self._db.execute("SELECT * FROM events WHERE id = ?", (event_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return CommunityEvent(
                id=row["id"],
                guild_id=row["guild_id"],
                title=row["title"],
                event_type=row["event_type"],
                start_time=row["start_time"],
                description=row["description"],
                creator_id=row["creator_id"],
                channel_id=row["channel_id"],
                status=row["status"],
                created_at=row["created_at"],
            )

    async def list_events(self, guild_id: int, status: str = "scheduled") -> List[CommunityEvent]:
        if not self._db:
            return []
        async with self._db.execute(
            "SELECT * FROM events WHERE guild_id = ? AND status = ? ORDER BY start_time ASC",
            (guild_id, status),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                CommunityEvent(
                    id=row["id"],
                    guild_id=row["guild_id"],
                    title=row["title"],
                    event_type=row["event_type"],
                    start_time=row["start_time"],
                    description=row["description"],
                    creator_id=row["creator_id"],
                    channel_id=row["channel_id"],
                    status=row["status"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    async def update_event_status(self, event_id: int, status: str) -> None:
        if not self._db:
            return
        await self._db.execute("UPDATE events SET status = ? WHERE id = ?", (status, event_id))
        await self._db.commit()

    async def add_event_participant(self, event_id: int, user_id: int) -> bool:
        if not self._db:
            return False
        now = utcnow_iso()
        try:
            await self._db.execute(
                "INSERT INTO event_participants (event_id, user_id, joined_at) VALUES (?, ?, ?)",
                (event_id, user_id, now),
            )
            await self._db.commit()
            return True
        except Exception:
            return False

    async def remove_event_participant(self, event_id: int, user_id: int) -> bool:
        if not self._db:
            return False
        cursor = await self._db.execute(
            "DELETE FROM event_participants WHERE event_id = ? AND user_id = ?",
            (event_id, user_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def list_event_participants(self, event_id: int) -> List[int]:
        if not self._db:
            return []
        async with self._db.execute(
            "SELECT user_id FROM event_participants WHERE event_id = ?", (event_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    # ==========================================
    # GAMING LFG
    # ==========================================

    async def create_gaming_lfg(
        self, guild_id: int, user_id: int, game: str, role: Optional[str] = None,
        note: Optional[str] = None, max_players: int = 4, channel_id: Optional[int] = None, message_id: Optional[int] = None
    ) -> int:
        await self.get_or_create_guild_config(guild_id)
        if not self._db:
            return 0
        now = utcnow_iso()
        async with self._db.execute(
            """
            INSERT INTO gaming_lfg (guild_id, user_id, game, role, note, max_players, current_players_json, channel_id, message_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            RETURNING id;
            """,
            (guild_id, user_id, game, role, note, max_players, json.dumps([user_id]), channel_id, message_id, now),
        ) as cursor:
            row = await cursor.fetchone()
            await self._db.commit()
            return row[0] if row else 0

    async def get_gaming_lfg(self, lfg_id: int) -> Optional[GamingLFG]:
        if not self._db:
            return None
        async with self._db.execute("SELECT * FROM gaming_lfg WHERE id = ?", (lfg_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            players = []
            try:
                players = json.loads(row["current_players_json"] or "[]")
            except Exception:
                players = []
            return GamingLFG(
                id=row["id"],
                guild_id=row["guild_id"],
                user_id=row["user_id"],
                game=row["game"],
                role=row["role"],
                note=row["note"],
                max_players=row["max_players"],
                current_players=players,
                message_id=row["message_id"],
                channel_id=row["channel_id"],
                status=row["status"],
                created_at=row["created_at"],
            )

    async def update_gaming_lfg_players(self, lfg_id: int, players: List[int], status: str = "open") -> None:
        if not self._db:
            return
        await self._db.execute(
            "UPDATE gaming_lfg SET current_players_json = ?, status = ? WHERE id = ?",
            (json.dumps(players), status, lfg_id),
        )
        await self._db.commit()

    async def list_active_gaming_lfg(self, guild_id: int) -> List[GamingLFG]:
        if not self._db:
            return []
        async with self._db.execute(
            "SELECT * FROM gaming_lfg WHERE guild_id = ? AND status = 'open' ORDER BY id DESC LIMIT 10",
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                try:
                    players = json.loads(row["current_players_json"] or "[]")
                except Exception:
                    players = []
                results.append(
                    GamingLFG(
                        id=row["id"],
                        guild_id=row["guild_id"],
                        user_id=row["user_id"],
                        game=row["game"],
                        role=row["role"],
                        note=row["note"],
                        max_players=row["max_players"],
                        current_players=players,
                        message_id=row["message_id"],
                        channel_id=row["channel_id"],
                        status=row["status"],
                        created_at=row["created_at"],
                    )
                )
            return results

    # ==========================================
    # CREATOR SHOWCASES
    # ==========================================

    async def create_creator_showcase(
        self, guild_id: int, user_id: int, title: str, media_url: str,
        software: Optional[str] = None, description: Optional[str] = None, message_id: Optional[int] = None
    ) -> int:
        await self.get_or_create_guild_config(guild_id)
        if not self._db:
            return 0
        now = utcnow_iso()
        async with self._db.execute(
            """
            INSERT INTO creator_showcases (guild_id, user_id, title, media_url, software, description, upvotes, message_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            RETURNING id;
            """,
            (guild_id, user_id, title, media_url, software, description, message_id, now),
        ) as cursor:
            row = await cursor.fetchone()
            await self._db.commit()
            return row[0] if row else 0

    async def upvote_creator_showcase(self, showcase_id: int) -> int:
        if not self._db:
            return 0
        await self._db.execute("UPDATE creator_showcases SET upvotes = upvotes + 1 WHERE id = ?", (showcase_id,))
        await self._db.commit()
        async with self._db.execute("SELECT upvotes FROM creator_showcases WHERE id = ?", (showcase_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def list_creator_showcases(self, guild_id: int, limit: int = 10) -> List[CreatorShowcase]:
        if not self._db:
            return []
        async with self._db.execute(
            "SELECT * FROM creator_showcases WHERE guild_id = ? ORDER BY upvotes DESC, id DESC LIMIT ?",
            (guild_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                CreatorShowcase(
                    id=row["id"],
                    guild_id=row["guild_id"],
                    user_id=row["user_id"],
                    title=row["title"],
                    media_url=row["media_url"],
                    software=row["software"],
                    description=row["description"],
                    upvotes=row["upvotes"],
                    message_id=row["message_id"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    # ==========================================
    # WATCH EVENTS
    # ==========================================

    async def create_watch_event(
        self, guild_id: int, title: str, platform: Optional[str], start_time: str, host_id: int, voice_channel_id: Optional[int] = None
    ) -> int:
        await self.get_or_create_guild_config(guild_id)
        if not self._db:
            return 0
        now = utcnow_iso()
        async with self._db.execute(
            """
            INSERT INTO watch_events (guild_id, title, platform, start_time, host_id, voice_channel_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?)
            RETURNING id;
            """,
            (guild_id, title, platform, start_time, host_id, voice_channel_id, now),
        ) as cursor:
            row = await cursor.fetchone()
            await self._db.commit()
            return row[0] if row else 0

    async def list_watch_events(self, guild_id: int) -> List[WatchEvent]:
        if not self._db:
            return []
        async with self._db.execute(
            "SELECT * FROM watch_events WHERE guild_id = ? AND status = 'scheduled' ORDER BY start_time ASC",
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                WatchEvent(
                    id=row["id"],
                    guild_id=row["guild_id"],
                    title=row["title"],
                    platform=row["platform"],
                    start_time=row["start_time"],
                    host_id=row["host_id"],
                    voice_channel_id=row["voice_channel_id"],
                    status=row["status"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    async def update_watch_event_status(self, event_id: int, status: str) -> None:
        if not self._db:
            return
        await self._db.execute("UPDATE watch_events SET status = ? WHERE id = ?", (status, event_id))
        await self._db.commit()

    # ==========================================
    # MUSIC ANALYTICS
    # ==========================================

    async def record_music_play(self, guild_id: int, duration_seconds: int, user_id: int) -> None:
        await self.get_or_create_guild_config(guild_id)
        if not self._db:
            return
        now = utcnow_iso()
        async with self._db.execute(
            "SELECT unique_listeners_json FROM music_analytics WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        listeners = set()
        if row and row["unique_listeners_json"]:
            try:
                listeners = set(json.loads(row["unique_listeners_json"]))
            except Exception:
                listeners = set()
        listeners.add(user_id)

        await self._db.execute(
            """
            INSERT INTO music_analytics (guild_id, tracks_played, total_playtime_seconds, unique_listeners_json, updated_at)
            VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                tracks_played = tracks_played + 1,
                total_playtime_seconds = total_playtime_seconds + excluded.total_playtime_seconds,
                unique_listeners_json = excluded.unique_listeners_json,
                updated_at = excluded.updated_at;
            """,
            (guild_id, duration_seconds, json.dumps(list(listeners)), now),
        )
        await self._db.commit()

    async def get_music_analytics(self, guild_id: int) -> MusicAnalytics:
        if not self._db:
            return MusicAnalytics(guild_id=guild_id)
        async with self._db.execute(
            "SELECT * FROM music_analytics WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return MusicAnalytics(guild_id=guild_id)
            listeners = []
            try:
                listeners = json.loads(row["unique_listeners_json"] or "[]")
            except Exception:
                listeners = []
            return MusicAnalytics(
                guild_id=row["guild_id"],
                tracks_played=row["tracks_played"],
                total_playtime_seconds=row["total_playtime_seconds"],
                unique_listeners=listeners,
                updated_at=row["updated_at"] or "",
            )

    async def get_or_create_user_economy(self, guild_id: int, user_id: int) -> UserEconomy:
        """Fetch or initialize a user's economy profile."""
        await self.get_or_create_guild_config(guild_id)
        now = utcnow_iso()
        async with self._db.execute(
            "SELECT * FROM user_economy WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                purchased_roles = []
                try:
                    purchased_roles = json.loads(row["purchased_roles"] or "[]")
                except Exception:
                    purchased_roles = []
                return UserEconomy(
                    user_id=row["user_id"],
                    guild_id=row["guild_id"],
                    coins=row["coins"],
                    bank=row["bank"],
                    daily_streak=row["daily_streak"],
                    last_daily=row["last_daily"],
                    xp=row["xp"],
                    level=row["level"],
                    purchased_roles=purchased_roles,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

        # Create new profile with 100 starting bonus
        await self._db.execute(
            """
            INSERT OR IGNORE INTO user_economy 
            (user_id, guild_id, coins, bank, daily_streak, last_daily, xp, level, purchased_roles, created_at, updated_at)
            VALUES (?, ?, 100, 0, 0, NULL, 0, 1, '[]', ?, ?)
            """,
            (user_id, guild_id, now, now),
        )
        await self._db.commit()

        return UserEconomy(
            user_id=user_id,
            guild_id=guild_id,
            coins=100,
            bank=0,
            daily_streak=0,
            last_daily=None,
            xp=0,
            level=1,
            purchased_roles=[],
            created_at=now,
            updated_at=now,
        )

    async def update_user_economy(self, guild_id: int, user_id: int, **kwargs) -> UserEconomy:
        """Update fields for a user's economy record."""
        await self.get_or_create_user_economy(guild_id, user_id)
        now = utcnow_iso()
        fields = []
        values = []
        for k, v in kwargs.items():
            if k == "purchased_roles" and isinstance(v, (list, set)):
                v = json.dumps(list(v))
            fields.append(f"{k} = ?")
            values.append(v)
        fields.append("updated_at = ?")
        values.append(now)
        values.extend([guild_id, user_id])

        sql = f"UPDATE user_economy SET {', '.join(fields)} WHERE guild_id = ? AND user_id = ?"
        await self._db.execute(sql, tuple(values))
        await self._db.commit()
        return await self.get_or_create_user_economy(guild_id, user_id)

    async def add_user_coins(self, guild_id: int, user_id: int, amount: int) -> UserEconomy:
        """Safely credit or debit coins."""
        profile = await self.get_or_create_user_economy(guild_id, user_id)
        new_coins = max(0, profile.coins + amount)
        return await self.update_user_economy(guild_id, user_id, coins=new_coins)

    async def get_top_economy_users(self, guild_id: int, limit: int = 10, order_by: str = "coins") -> List[UserEconomy]:
        """Fetch top ranked users by coins or level."""
        col = "level" if order_by == "level" else "coins"
        async with self._db.execute(
            f"SELECT * FROM user_economy WHERE guild_id = ? ORDER BY {col} DESC LIMIT ?",
            (guild_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                purchased = []
                try:
                    purchased = json.loads(row["purchased_roles"] or "[]")
                except Exception:
                    purchased = []
                results.append(
                    UserEconomy(
                        user_id=row["user_id"],
                        guild_id=row["guild_id"],
                        coins=row["coins"],
                        bank=row["bank"],
                        daily_streak=row["daily_streak"],
                        last_daily=row["last_daily"],
                        xp=row["xp"],
                        level=row["level"],
                        purchased_roles=purchased,
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                )
            return results

    async def record_matchmaker_history(
        self,
        guild_id: int,
        game: str,
        mode: str,
        player_ids: List[int],
        voice_channel_id: Optional[int] = None,
    ) -> int:
        """Log a completed matchmaking session."""
        now = utcnow_iso()
        cursor = await self._db.execute(
            """
            INSERT INTO matchmaker_history (guild_id, game, mode, player_ids_json, voice_channel_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, game, mode, json.dumps(player_ids), voice_channel_id, now),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_or_create_owner_reports_config(self, guild_id: int) -> OwnerReportsConfig:
        """Fetch or initialize private owner reports category and channel mapping."""
        await self.get_or_create_guild_config(guild_id)
        now = utcnow_iso()
        async with self._db.execute(
            "SELECT * FROM owner_reports_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                row_keys = row.keys() if hasattr(row, "keys") else []
                startup_rep = bool(row["startup_reports_enabled"]) if "startup_reports_enabled" in row_keys else False
                success_rep = bool(row["success_reports_enabled"]) if "success_reports_enabled" in row_keys else False
                return OwnerReportsConfig(
                    guild_id=row["guild_id"],
                    category_id=row["category_id"],
                    security_report_id=row["security_report_id"],
                    mod_report_id=row["mod_report_id"],
                    music_report_id=row["music_report_id"],
                    room_report_id=row["room_report_id"],
                    bot_report_id=row["bot_report_id"],
                    system_report_id=row["system_report_id"],
                    auto_repair=bool(row["auto_repair"]),
                    startup_reports_enabled=startup_rep,
                    success_reports_enabled=success_rep,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

        async with self._db.execute("PRAGMA table_info(owner_reports_config)") as c:
            cols = [r[1] for r in await c.fetchall()]

        if "startup_reports_enabled" in cols and "success_reports_enabled" in cols:
            await self._db.execute(
                """
                INSERT OR IGNORE INTO owner_reports_config
                (guild_id, category_id, security_report_id, mod_report_id, music_report_id, room_report_id, bot_report_id, system_report_id, auto_repair, startup_reports_enabled, success_reports_enabled, created_at, updated_at)
                VALUES (?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 1, 0, 0, ?, ?)
                """,
                (guild_id, now, now),
            )
        elif "startup_reports_enabled" in cols:
            await self._db.execute(
                """
                INSERT OR IGNORE INTO owner_reports_config
                (guild_id, category_id, security_report_id, mod_report_id, music_report_id, room_report_id, bot_report_id, system_report_id, auto_repair, startup_reports_enabled, created_at, updated_at)
                VALUES (?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 1, 0, ?, ?)
                """,
                (guild_id, now, now),
            )
        else:
            await self._db.execute(
                """
                INSERT OR IGNORE INTO owner_reports_config
                (guild_id, category_id, security_report_id, mod_report_id, music_report_id, room_report_id, bot_report_id, system_report_id, auto_repair, created_at, updated_at)
                VALUES (?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 1, ?, ?)
                """,
                (guild_id, now, now),
            )
        await self._db.commit()

        return OwnerReportsConfig(
            guild_id=guild_id,
            category_id=None,
            security_report_id=None,
            mod_report_id=None,
            music_report_id=None,
            room_report_id=None,
            bot_report_id=None,
            system_report_id=None,
            auto_repair=True,
            startup_reports_enabled=False,
            success_reports_enabled=False,
            created_at=now,
            updated_at=now,
        )

    async def update_owner_reports_config(self, guild_id: int, **kwargs) -> OwnerReportsConfig:
        """Update owner report channel IDs, auto repair state, startup or success reports toggle."""
        await self.get_or_create_owner_reports_config(guild_id)
        now = utcnow_iso()
        fields = []
        values = []
        for k, v in kwargs.items():
            fields.append(f"{k} = ?")
            values.append(v)
        fields.append("updated_at = ?")
        values.append(now)
        values.append(guild_id)

        sql = f"UPDATE owner_reports_config SET {', '.join(fields)} WHERE guild_id = ?"
        await self._db.execute(sql, tuple(values))
        await self._db.commit()
        return await self.get_or_create_owner_reports_config(guild_id)

    async def get_owner_reports_config(self, guild_id: int) -> Optional[OwnerReportsConfig]:
        """Get owner report configuration if exists."""
        if not self._db:
            return None
        async with self._db.execute(
            "SELECT * FROM owner_reports_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            row_keys = row.keys() if hasattr(row, "keys") else []
            startup_rep = bool(row["startup_reports_enabled"]) if "startup_reports_enabled" in row_keys else False
            success_rep = bool(row["success_reports_enabled"]) if "success_reports_enabled" in row_keys else False
            return OwnerReportsConfig(
                guild_id=row["guild_id"],
                category_id=row["category_id"],
                security_report_id=row["security_report_id"],
                mod_report_id=row["mod_report_id"],
                music_report_id=row["music_report_id"],
                room_report_id=row["room_report_id"],
                bot_report_id=row["bot_report_id"],
                system_report_id=row["system_report_id"],
                auto_repair=bool(row["auto_repair"]),
                startup_reports_enabled=startup_rep,
                success_reports_enabled=success_rep,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    # ==========================================
    # REPORT SYSTEM (DESTINATIONS, PERMISSIONS, EVENTS, DELIVERY)
    # ==========================================

    async def get_report_destinations(self, guild_id: int) -> List[ReportDestination]:
        """Fetch all configured report destinations for a guild."""
        if not self._db:
            return []
        async with self._db.execute(
            "SELECT * FROM report_destinations WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                ReportDestination(
                    guild_id=r["guild_id"],
                    report_type=r["report_type"],
                    channel_id=r["channel_id"],
                    enabled=bool(r["enabled"]),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    async def get_report_destination(self, guild_id: int, report_type: str) -> Optional[ReportDestination]:
        """Fetch specific report destination for a guild and report type."""
        if not self._db:
            return None
        async with self._db.execute(
            "SELECT * FROM report_destinations WHERE guild_id = ? AND report_type = ?",
            (guild_id, report_type),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return ReportDestination(
                guild_id=row["guild_id"],
                report_type=row["report_type"],
                channel_id=row["channel_id"],
                enabled=bool(row["enabled"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def set_report_destination(
        self, guild_id: int, report_type: str, channel_id: int, enabled: bool = True
    ) -> ReportDestination:
        """Create or update a report destination mapping."""
        now = utcnow_iso()
        await self._db.execute(
            """
            INSERT INTO report_destinations (guild_id, report_type, channel_id, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, report_type) DO UPDATE SET
                channel_id = excluded.channel_id,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (guild_id, report_type, channel_id, int(enabled), now, now),
        )
        await self._db.commit()
        return ReportDestination(
            guild_id=guild_id,
            report_type=report_type,
            channel_id=channel_id,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )

    async def set_report_destination_enabled(self, guild_id: int, report_type: str, enabled: bool) -> None:
        """Enable or disable a specific report type destination."""
        now = utcnow_iso()
        await self._db.execute(
            "UPDATE report_destinations SET enabled = ?, updated_at = ? WHERE guild_id = ? AND report_type = ?",
            (int(enabled), now, guild_id, report_type),
        )
        await self._db.commit()

    async def delete_report_destination(self, guild_id: int, report_type: str) -> None:
        """Remove a report destination."""
        await self._db.execute(
            "DELETE FROM report_destinations WHERE guild_id = ? AND report_type = ?",
            (guild_id, report_type),
        )
        await self._db.commit()

    async def get_report_permission_state(
        self, guild_id: int, channel_id: int, report_type: str
    ) -> Optional[ReportPermissionState]:
        """Fetch permission state for a channel and report type."""
        if not self._db:
            return None
        async with self._db.execute(
            "SELECT * FROM report_permission_state WHERE guild_id = ? AND channel_id = ? AND report_type = ?",
            (guild_id, channel_id, report_type),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return ReportPermissionState(
                guild_id=row["guild_id"],
                channel_id=row["channel_id"],
                report_type=row["report_type"],
                status=row["status"],
                last_checked_at=row["last_checked_at"],
                last_warning_at=row["last_warning_at"],
                last_error=row["last_error"],
                warning_message_id=row["warning_message_id"],
                retry_after=float(row["retry_after"] or 0.0),
            )

    async def list_report_permission_states(self, guild_id: int) -> List[ReportPermissionState]:
        """Fetch all permission states for a guild."""
        if not self._db:
            return []
        async with self._db.execute(
            "SELECT * FROM report_permission_state WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                ReportPermissionState(
                    guild_id=r["guild_id"],
                    channel_id=r["channel_id"],
                    report_type=r["report_type"],
                    status=r["status"],
                    last_checked_at=r["last_checked_at"],
                    last_warning_at=r["last_warning_at"],
                    last_error=r["last_error"],
                    warning_message_id=r["warning_message_id"],
                    retry_after=float(r["retry_after"] or 0.0),
                )
                for r in rows
            ]

    async def update_report_permission_state(
        self,
        guild_id: int,
        channel_id: int,
        report_type: str,
        status: str,
        last_error: Optional[str] = None,
        warning_message_id: Optional[int] = None,
        retry_after: float = 0.0,
        record_warning: bool = False,
    ) -> ReportPermissionState:
        """Insert or update report permission state."""
        now = utcnow_iso()
        async with self._db.execute(
            "SELECT last_warning_at, warning_message_id FROM report_permission_state WHERE guild_id = ? AND channel_id = ? AND report_type = ?",
            (guild_id, channel_id, report_type),
        ) as cursor:
            row = await cursor.fetchone()

        last_warn = row["last_warning_at"] if row else None
        prev_msg_id = row["warning_message_id"] if row else None
        if record_warning:
            last_warn = now
        effective_msg_id = warning_message_id if warning_message_id is not None else prev_msg_id

        await self._db.execute(
            """
            INSERT INTO report_permission_state (
                guild_id, channel_id, report_type, status, last_checked_at, last_warning_at,
                last_error, warning_message_id, retry_after
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, channel_id, report_type) DO UPDATE SET
                status = excluded.status,
                last_checked_at = excluded.last_checked_at,
                last_warning_at = COALESCE(excluded.last_warning_at, report_permission_state.last_warning_at),
                last_error = excluded.last_error,
                warning_message_id = COALESCE(excluded.warning_message_id, report_permission_state.warning_message_id),
                retry_after = excluded.retry_after
            """,
            (guild_id, channel_id, report_type, status, now, last_warn, last_error, effective_msg_id, retry_after),
        )
        await self._db.commit()
        return ReportPermissionState(
            guild_id=guild_id,
            channel_id=channel_id,
            report_type=report_type,
            status=status,
            last_checked_at=now,
            last_warning_at=last_warn,
            last_error=last_error,
            warning_message_id=effective_msg_id,
            retry_after=retry_after,
        )

    async def get_report_event(self, event_id: str) -> Optional[ReportEventRecord]:
        """Fetch report event record by ID."""
        if not self._db:
            return None
        async with self._db.execute(
            "SELECT * FROM report_events WHERE event_id = ?", (event_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return ReportEventRecord(
                event_id=row["event_id"],
                guild_id=row["guild_id"],
                report_type=row["report_type"],
                severity=row["severity"],
                fingerprint=row["fingerprint"],
                message=row["message"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                occurrences=row["occurrences"],
                status=row["status"],
            )

    async def find_active_report_event_by_fingerprint(
        self, guild_id: int, report_type: str, fingerprint: str
    ) -> Optional[ReportEventRecord]:
        """Find an open/detected report event with identical fingerprint."""
        if not self._db:
            return None
        async with self._db.execute(
            """
            SELECT * FROM report_events
            WHERE guild_id = ? AND report_type = ? AND fingerprint = ? AND status IN ('DETECTED', 'VERIFIED', 'OPEN', 'UPDATED')
            ORDER BY rowid DESC LIMIT 1
            """,
            (guild_id, report_type, fingerprint),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return ReportEventRecord(
                event_id=row["event_id"],
                guild_id=row["guild_id"],
                report_type=row["report_type"],
                severity=row["severity"],
                fingerprint=row["fingerprint"],
                message=row["message"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                occurrences=row["occurrences"],
                status=row["status"],
            )

    async def get_or_create_report_event(
        self,
        event_id: str,
        guild_id: int,
        report_type: str,
        severity: str,
        fingerprint: str,
        message: str,
    ) -> Tuple[ReportEventRecord, bool]:
        """Fetch active matching event or create new event. Returns (record, created)."""
        existing = await self.find_active_report_event_by_fingerprint(guild_id, report_type, fingerprint)
        if existing:
            return existing, False

        now = utcnow_iso()
        await self._db.execute(
            """
            INSERT INTO report_events (event_id, guild_id, report_type, severity, fingerprint, message, first_seen, last_seen, occurrences, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'OPEN')
            """,
            (event_id, guild_id, report_type, severity, fingerprint, message, now, now),
        )
        await self._db.commit()
        return (
            ReportEventRecord(
                event_id=event_id,
                guild_id=guild_id,
                report_type=report_type,
                severity=severity,
                fingerprint=fingerprint,
                message=message,
                first_seen=now,
                last_seen=now,
                occurrences=1,
                status="OPEN",
            ),
            True,
        )

    async def update_report_event_occurrence(self, event_id: str, status: str = "UPDATED") -> Optional[ReportEventRecord]:
        """Increment occurrence counter and bump last_seen timestamp."""
        now = utcnow_iso()
        await self._db.execute(
            """
            UPDATE report_events
            SET occurrences = occurrences + 1, last_seen = ?, status = ?
            WHERE event_id = ?
            """,
            (now, status, event_id),
        )
        await self._db.commit()
        return await self.get_report_event(event_id)

    async def update_report_event_status(self, event_id: str, status: str) -> None:
        """Update lifecycle status of a report event (e.g. RECOVERED, CLOSED)."""
        now = utcnow_iso()
        await self._db.execute(
            "UPDATE report_events SET status = ?, last_seen = ? WHERE event_id = ?",
            (status, now, event_id),
        )
        await self._db.commit()

    async def record_report_delivery(
        self,
        event_id: str,
        channel_id: int,
        message_id: Optional[int],
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Record report message delivery status."""
        now = utcnow_iso()
        await self._db.execute(
            """
            INSERT INTO report_delivery (event_id, channel_id, message_id, status, attempts, last_attempt_at, error)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(event_id, channel_id) DO UPDATE SET
                message_id = COALESCE(excluded.message_id, report_delivery.message_id),
                status = excluded.status,
                attempts = report_delivery.attempts + 1,
                last_attempt_at = excluded.last_attempt_at,
                error = excluded.error
            """,
            (event_id, channel_id, message_id, status, now, error),
        )
        await self._db.commit()

    async def get_report_delivery(self, event_id: str, channel_id: int) -> Optional[ReportDeliveryRecord]:
        """Fetch delivery record for an event and channel."""
        if not self._db:
            return None
        async with self._db.execute(
            "SELECT * FROM report_delivery WHERE event_id = ? AND channel_id = ?",
            (event_id, channel_id),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return ReportDeliveryRecord(
                event_id=row["event_id"],
                channel_id=row["channel_id"],
                message_id=row["message_id"],
                status=row["status"],
                attempts=row["attempts"],
                last_attempt_at=row["last_attempt_at"],
                error=row["error"],
            )

    # ==========================================
    # STREAM TRACKERS (TWITCH / YOUTUBE / KICK)
    # ==========================================

    async def add_stream_tracker(
        self,
        guild_id: int,
        platform: str,
        channel_name: str,
        alert_channel_id: int,
        custom_role_id: Optional[int] = None,
    ) -> int:
        """Add a streamer to radar."""
        now = utcnow_iso()
        async with self._db.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO stream_trackers (guild_id, platform, channel_name, alert_channel_id, custom_role_id, last_status, created_at)
                VALUES (?, ?, ?, ?, ?, 'offline', ?)
                """,
                (guild_id, platform.lower().strip(), channel_name.strip(), alert_channel_id, custom_role_id, now),
            )
            await self._db.commit()
            return cur.lastrowid

    async def remove_stream_tracker(self, guild_id: int, channel_name: str) -> bool:
        """Remove a streamer from radar."""
        async with self._db.cursor() as cur:
            await cur.execute(
                "DELETE FROM stream_trackers WHERE guild_id = ? AND LOWER(channel_name) = LOWER(?)",
                (guild_id, channel_name.strip()),
            )
            await self._db.commit()
            return cur.rowcount > 0

    async def get_stream_trackers(self, guild_id: int) -> List[StreamTracker]:
        """Fetch all tracked streamers for a guild."""
        async with self._db.execute(
            "SELECT * FROM stream_trackers WHERE guild_id = ? ORDER BY id ASC",
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                StreamTracker(
                    id=row["id"],
                    guild_id=row["guild_id"],
                    platform=row["platform"],
                    channel_name=row["channel_name"],
                    alert_channel_id=row["alert_channel_id"],
                    custom_role_id=row["custom_role_id"],
                    last_status=row["last_status"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    async def get_all_stream_trackers(self) -> List[StreamTracker]:
        """Fetch all tracked streamers across all guilds for background poll."""
        if not self._db:
            return []
        async with self._db.execute("SELECT * FROM stream_trackers ORDER BY id ASC") as cursor:
            rows = await cursor.fetchall()
            return [
                StreamTracker(
                    id=row["id"],
                    guild_id=row["guild_id"],
                    platform=row["platform"],
                    channel_name=row["channel_name"],
                    alert_channel_id=row["alert_channel_id"],
                    custom_role_id=row["custom_role_id"],
                    last_status=row["last_status"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    async def update_stream_tracker_status(self, tracker_id: int, status: str) -> None:
        """Update stream status (e.g. 'live' or 'offline')."""
        await self._db.execute(
            "UPDATE stream_trackers SET last_status = ? WHERE id = ?",
            (status, tracker_id),
        )
        await self._db.commit()

    # ==========================================
    # MEMBER INVITES TRACKING
    # ==========================================

    async def get_member_invites(self, guild_id: int, inviter_id: int) -> MemberInvites:
        """Get invite counts for a user in a guild."""
        async with self._db.execute(
            "SELECT * FROM member_invites WHERE guild_id = ? AND inviter_id = ?",
            (guild_id, inviter_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return MemberInvites(
                    guild_id=row["guild_id"],
                    inviter_id=row["inviter_id"],
                    regular=row["regular"],
                    leaves=row["leaves"],
                    fake=row["fake"],
                    bonus=row["bonus"],
                )
        return MemberInvites(guild_id=guild_id, inviter_id=inviter_id)

    async def increment_member_invites(
        self,
        guild_id: int,
        inviter_id: int,
        regular: int = 0,
        leaves: int = 0,
        fake: int = 0,
        bonus: int = 0,
    ) -> MemberInvites:
        """Increment or adjust invite statistics."""
        await self._db.execute(
            """
            INSERT INTO member_invites (guild_id, inviter_id, regular, leaves, fake, bonus)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, inviter_id) DO UPDATE SET
                regular = MAX(0, regular + excluded.regular),
                leaves = MAX(0, leaves + excluded.leaves),
                fake = MAX(0, fake + excluded.fake),
                bonus = MAX(0, bonus + excluded.bonus)
            """,
            (guild_id, inviter_id, regular, leaves, fake, bonus),
        )
        await self._db.commit()
        return await self.get_member_invites(guild_id, inviter_id)

    async def get_top_inviters(self, guild_id: int, limit: int = 10) -> List[Tuple[int, int]]:
        """Get top inviters sorted by effective invites."""
        async with self._db.execute(
            """
            SELECT inviter_id, (regular + bonus - leaves - fake) AS total_invites
            FROM member_invites
            WHERE guild_id = ?
            ORDER BY total_invites DESC
            LIMIT ?
            """,
            (guild_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [(row[0], max(0, row[1])) for row in rows]

    # ==========================================
    # TOP.GG VOTING & REWARDS
    # ==========================================

    async def record_vote(self, user_id: int, guild_id: int) -> int:
        """Record a vote and return new total."""
        now = utcnow_iso()
        await self._db.execute(
            """
            INSERT INTO member_votes (user_id, guild_id, total_votes, last_voted)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET
                total_votes = total_votes + 1,
                last_voted = excluded.last_voted
            """,
            (user_id, guild_id, now),
        )
        await self._db.commit()
        votes = await self.get_member_votes(user_id, guild_id)
        return votes.total_votes

    async def get_member_votes(self, user_id: int, guild_id: int) -> MemberVotes:
        """Fetch member vote details."""
        async with self._db.execute(
            "SELECT * FROM member_votes WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return MemberVotes(
                    user_id=row["user_id"],
                    guild_id=row["guild_id"],
                    total_votes=row["total_votes"],
                    last_voted=row["last_voted"],
                )
        return MemberVotes(user_id=user_id, guild_id=guild_id)




        # Run schema migrations
        await run_migrations(self._db)
        logger.info(f"Connected to database at {self.db_path}")

    async def close(self) -> None:
        """Cleanly close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("Database connection closed")

    async def check_integrity(self) -> Tuple[bool, List[str]]:
        """Verify foreign keys and database integrity."""
        errors: List[str] = []
        if not self._db:
            return False, ["Database is not connected"]

        async with self._db.execute("PRAGMA foreign_key_check;") as cursor:
            fk_rows = await cursor.fetchall()
            if fk_rows:
                errors.append(f"Foreign key violations found: {len(fk_rows)}")

        async with self._db.execute("PRAGMA integrity_check;") as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                if row[0] != "ok":
                    errors.append(f"Integrity issue: {row[0]}")

        return len(errors) == 0, errors

    # ==========================================
    # GUILD CONFIGURATION
    # ==========================================

    async def get_or_create_guild_config(self, guild_id: int) -> GuildConfig:
        """Ensure all configuration tables have defaults for the guild and return GuildConfig."""
        now = utcnow_iso()
        async with self._db.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            async with self._db.cursor() as cur:
                # 1. guild_config
                await cur.execute(
                    """
                    INSERT INTO guild_config (
                        guild_id, security_enabled, automod_enabled, welcome_enabled,
                        autorole_enabled, tickets_enabled, music_enabled, emergency_stop,
                        created_at, updated_at
                    ) VALUES (?, 1, 0, 0, 0, 0, 1, 0, ?, ?)
                    ON CONFLICT(guild_id) DO NOTHING;
                    """,
                    (guild_id, now, now),
                )
                # 2. security_config
                await cur.execute(
                    """
                    INSERT INTO security_config (guild_id, updated_at)
                    VALUES (?, ?)
                    ON CONFLICT(guild_id) DO NOTHING;
                    """,
                    (guild_id, now),
                )
                # 3. security_state
                await cur.execute(
                    """
                    INSERT INTO security_state (guild_id, updated_at)
                    VALUES (?, ?)
                    ON CONFLICT(guild_id) DO NOTHING;
                    """,
                    (guild_id, now),
                )
                # 4. welcome_config
                await cur.execute(
                    """
                    INSERT INTO welcome_config (guild_id, updated_at)
                    VALUES (?, ?)
                    ON CONFLICT(guild_id) DO NOTHING;
                    """,
                    (guild_id, now),
                )
                # 5. logging_config
                await cur.execute(
                    """
                    INSERT INTO logging_config (guild_id, updated_at)
                    VALUES (?, ?)
                    ON CONFLICT(guild_id) DO NOTHING;
                    """,
                    (guild_id, now),
                )
                # 6. ticket_config
                await cur.execute(
                    """
                    INSERT INTO ticket_config (guild_id, updated_at)
                    VALUES (?, ?)
                    ON CONFLICT(guild_id) DO NOTHING;
                    """,
                    (guild_id, now),
                )
                # 7. automod_config
                await cur.execute(
                    """
                    INSERT INTO automod_config (guild_id, updated_at)
                    VALUES (?, ?)
                    ON CONFLICT(guild_id) DO NOTHING;
                    """,
                    (guild_id, now),
                )
                # 8. suggestion_config
                await cur.execute(
                    """
                    INSERT INTO suggestion_config (guild_id, created_at, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id) DO NOTHING;
                    """,
                    (guild_id, now, now),
                )
                # 9. raid_config
                await cur.execute(
                    """
                    INSERT INTO raid_config (guild_id, updated_at)
                    VALUES (?, ?)
                    ON CONFLICT(guild_id) DO NOTHING;
                    """,
                    (guild_id, now),
                )
                # 10. voiceguard_config
                await cur.execute(
                    """
                    INSERT INTO voiceguard_config (guild_id, updated_at)
                    VALUES (?, ?)
                    ON CONFLICT(guild_id) DO NOTHING;
                    """,
                    (guild_id, now),
                )
                # 11. automation_config
                await cur.execute(
                    """
                    INSERT INTO automation_config (guild_id, updated_at)
                    VALUES (?, ?)
                    ON CONFLICT(guild_id) DO NOTHING;
                    """,
                    (guild_id, now),
                )
                await self._db.commit()

            async with self._db.execute(
                "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()

        return GuildConfig(
            guild_id=row["guild_id"],
            security_enabled=bool(row["security_enabled"]),
            automod_enabled=bool(row["automod_enabled"]),
            welcome_enabled=bool(row["welcome_enabled"]),
            autorole_enabled=bool(row["autorole_enabled"]),
            tickets_enabled=bool(row["tickets_enabled"]),
            music_enabled=bool(row["music_enabled"]),
            emergency_stop=bool(row["emergency_stop"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def update_guild_config(self, guild_id: int, **kwargs: Any) -> None:
        """Update fields in guild_config."""
        await self.get_or_create_guild_config(guild_id)
        valid_fields = {
            "security_enabled", "automod_enabled", "welcome_enabled",
            "autorole_enabled", "tickets_enabled", "music_enabled", "emergency_stop"
        }
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}
        if not updates:
            return

        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]

        sql = f"UPDATE guild_config SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    # ==========================================
    # SECURITY CONFIG & STATE
    # ==========================================

    async def get_security_config(self, guild_id: int) -> SecurityConfig:
        await self.get_or_create_guild_config(guild_id)
        async with self._db.execute(
            "SELECT * FROM security_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return SecurityConfig(guild_id=guild_id)

        return SecurityConfig(
            guild_id=row["guild_id"],
            channel_delete_limit=row["channel_delete_limit"],
            channel_delete_window=row["channel_delete_window"],
            channel_create_limit=row["channel_create_limit"],
            channel_create_window=row["channel_create_window"],
            role_delete_limit=row["role_delete_limit"],
            role_delete_window=row["role_delete_window"],
            role_create_limit=row["role_create_limit"],
            role_create_window=row["role_create_window"],
            ban_limit=row["ban_limit"],
            ban_window=row["ban_window"],
            kick_limit=row["kick_limit"],
            kick_window=row["kick_window"],
            webhook_limit=row["webhook_limit"],
            webhook_window=row["webhook_window"],
            punishment=row["punishment"],
            updated_at=row["updated_at"],
        )

    async def update_security_config(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_or_create_guild_config(guild_id)
        valid_fields = {
            "channel_delete_limit", "channel_delete_window",
            "channel_create_limit", "channel_create_window",
            "role_delete_limit", "role_delete_window",
            "role_create_limit", "role_create_window",
            "ban_limit", "ban_window",
            "kick_limit", "kick_window",
            "webhook_limit", "webhook_window",
            "punishment"
        }
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}
        if not updates:
            return

        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]

        sql = f"UPDATE security_config SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    async def get_security_state(self, guild_id: int) -> SecurityState:
        await self.get_or_create_guild_config(guild_id)
        async with self._db.execute(
            "SELECT * FROM security_state WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return SecurityState(guild_id=guild_id)

        return SecurityState(
            guild_id=row["guild_id"],
            emergency_stop=bool(row["emergency_stop"]),
            lockdown_enabled=bool(row["lockdown_enabled"]),
            lockdown_started_at=row["lockdown_started_at"],
            emergency_started_at=row["emergency_started_at"],
            changed_by=row["changed_by"],
            updated_at=row["updated_at"],
        )

    async def set_emergency_stop(self, guild_id: int, enabled: bool, changed_by: Optional[int] = None) -> None:
        now = utcnow_iso()
        await self.get_or_create_guild_config(guild_id)
        await self._db.execute(
            """
            UPDATE security_state
            SET emergency_stop = ?,
                emergency_started_at = CASE WHEN ? = 1 THEN ? ELSE NULL END,
                changed_by = ?,
                updated_at = ?
            WHERE guild_id = ?
            """,
            (int(enabled), int(enabled), now, changed_by, now, guild_id),
        )
        await self._db.execute(
            "UPDATE guild_config SET emergency_stop = ?, updated_at = ? WHERE guild_id = ?",
            (int(enabled), now, guild_id),
        )
        await self._db.commit()

    # ==========================================
    # GUILD ROLES & ROLE AUDIT LOGS
    # ==========================================

    async def save_guild_role(
        self,
        guild_id: int,
        role_key: str,
        discord_role_id: int,
        role_name: str,
        role_type: str,
        managed_by_rai: bool = True,
        enabled: bool = True,
        position: int = 0,
    ) -> GuildRole:
        """Insert or update a managed guild role mapping."""
        now = utcnow_iso()
        await self.get_or_create_guild_config(guild_id)
        await self._db.execute(
            """
            INSERT INTO guild_roles (
                guild_id, role_key, discord_role_id, role_name, role_type,
                managed_by_rai, enabled, position, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, role_key) DO UPDATE SET
                discord_role_id = excluded.discord_role_id,
                role_name = excluded.role_name,
                role_type = excluded.role_type,
                managed_by_rai = excluded.managed_by_rai,
                enabled = excluded.enabled,
                position = excluded.position,
                updated_at = excluded.updated_at
            """,
            (
                guild_id,
                role_key,
                discord_role_id,
                role_name,
                role_type,
                1 if managed_by_rai else 0,
                1 if enabled else 0,
                position,
                now,
                now,
            ),
        )
        await self._db.commit()
        return await self.get_guild_role(guild_id, role_key)

    async def get_guild_role(self, guild_id: int, role_key: str) -> Optional[GuildRole]:
        """Fetch a guild role by its unique role_key."""
        async with self._db.execute(
            "SELECT * FROM guild_roles WHERE guild_id = ? AND role_key = ?",
            (guild_id, role_key),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return GuildRole(
                id=row["id"],
                guild_id=row["guild_id"],
                role_key=row["role_key"],
                discord_role_id=row["discord_role_id"],
                role_name=row["role_name"],
                role_type=row["role_type"],
                managed_by_rai=bool(row["managed_by_rai"]),
                enabled=bool(row["enabled"]),
                position=row["position"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def get_guild_role_by_id(self, guild_id: int, discord_role_id: int) -> Optional[GuildRole]:
        """Fetch a guild role by Discord role ID."""
        async with self._db.execute(
            "SELECT * FROM guild_roles WHERE guild_id = ? AND discord_role_id = ?",
            (guild_id, discord_role_id),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return GuildRole(
                id=row["id"],
                guild_id=row["guild_id"],
                role_key=row["role_key"],
                discord_role_id=row["discord_role_id"],
                role_name=row["role_name"],
                role_type=row["role_type"],
                managed_by_rai=bool(row["managed_by_rai"]),
                enabled=bool(row["enabled"]),
                position=row["position"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def get_all_guild_roles(self, guild_id: int) -> List[GuildRole]:
        """Fetch all configured roles for a guild."""
        async with self._db.execute(
            "SELECT * FROM guild_roles WHERE guild_id = ? ORDER BY position DESC, role_type ASC",
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                GuildRole(
                    id=r["id"],
                    guild_id=r["guild_id"],
                    role_key=r["role_key"],
                    discord_role_id=r["discord_role_id"],
                    role_name=r["role_name"],
                    role_type=r["role_type"],
                    managed_by_rai=bool(r["managed_by_rai"]),
                    enabled=bool(r["enabled"]),
                    position=r["position"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    async def delete_guild_role(self, guild_id: int, role_key: str) -> bool:
        """Delete a guild role record by role_key."""
        async with self._db.execute(
            "DELETE FROM guild_roles WHERE guild_id = ? AND role_key = ?",
            (guild_id, role_key),
        ) as cursor:
            await self._db.commit()
            return cursor.rowcount > 0

    async def delete_guild_role_by_id(self, guild_id: int, discord_role_id: int) -> bool:
        """Delete a guild role record by Discord role ID."""
        async with self._db.execute(
            "DELETE FROM guild_roles WHERE guild_id = ? AND discord_role_id = ?",
            (guild_id, discord_role_id),
        ) as cursor:
            await self._db.commit()
            return cursor.rowcount > 0

    async def log_role_audit(
        self,
        guild_id: int,
        user_id: Optional[int],
        role_id: int,
        role_key: str,
        action: str,
        reason: Optional[str] = None,
        trigger: Optional[str] = None,
        executor: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Log an automatic or manual role change audit entry."""
        now = utcnow_iso()
        await self.get_or_create_guild_config(guild_id)
        await self._db.execute(
            """
            INSERT INTO role_audit_logs (
                guild_id, user_id, role_id, role_key, action, reason, trigger, executor, success, error, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                user_id,
                role_id,
                role_key,
                action,
                reason,
                trigger,
                executor,
                1 if success else 0,
                error,
                now,
            ),
        )
        await self._db.commit()

    async def get_recent_role_audits(self, guild_id: int, limit: int = 25) -> List[RoleAuditLog]:
        """Fetch recent role audit logs for a guild."""
        async with self._db.execute(
            "SELECT * FROM role_audit_logs WHERE guild_id = ? ORDER BY timestamp DESC LIMIT ?",
            (guild_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                RoleAuditLog(
                    id=r["id"],
                    guild_id=r["guild_id"],
                    user_id=r["user_id"],
                    role_id=r["role_id"],
                    role_key=r["role_key"],
                    action=r["action"],
                    reason=r["reason"],
                    trigger=r["trigger"],
                    executor=r["executor"],
                    success=bool(r["success"]),
                    error=r["error"],
                    timestamp=r["timestamp"],
                )
                for r in rows
            ]

    # ==========================================
    # MENTION NOTIFICATIONS
    # ==========================================

    async def _ensure_mention_tables(self) -> None:
        if not hasattr(self, "_mention_tables_checked") or not self._mention_tables_checked:
            if not self._db:
                return
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS user_mention_notifications (
                    user_id INTEGER PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1
                );
            """)
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS guild_mention_notifications (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1
                );
            """)
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS founder_activity_alerts (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    recipient_id INTEGER
                );
            """)
            await self._db.commit()
            self._mention_tables_checked = True

    async def get_user_mention_notification(self, user_id: int) -> bool:
        """Returns True if the user has mention notifications enabled (default: True)."""
        await self._ensure_mention_tables()
        if not self._db:
            return True
        async with self._db.execute(
            "SELECT enabled FROM user_mention_notifications WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is not None:
                return bool(row["enabled"])
            return True

    async def set_user_mention_notification(self, user_id: int, enabled: bool) -> None:
        """Sets the user's mention notification preference."""
        await self._ensure_mention_tables()
        if not self._db:
            return
        await self._db.execute(
            """
            INSERT INTO user_mention_notifications (user_id, enabled)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET enabled = excluded.enabled;
            """,
            (user_id, 1 if enabled else 0),
        )
        await self._db.commit()

    async def get_guild_mention_notification(self, guild_id: int) -> bool:
        """Returns True if mention notifications are enabled for the guild (default: True)."""
        await self._ensure_mention_tables()
        if not self._db:
            return True
        async with self._db.execute(
            "SELECT enabled FROM guild_mention_notifications WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is not None:
                return bool(row["enabled"])
            return True

    async def set_guild_mention_notification(self, guild_id: int, enabled: bool) -> None:
        """Sets the guild's mention notification preference."""
        await self._ensure_mention_tables()
        if not self._db:
            return
        await self._db.execute(
            """
            INSERT INTO guild_mention_notifications (guild_id, enabled)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET enabled = excluded.enabled;
            """,
            (guild_id, 1 if enabled else 0),
        )
        await self._db.commit()

    # ==========================================
    # FOUNDER ACTIVITY NOTIFICATIONS
    # ==========================================

    async def get_founder_activity_dm(self, guild_id: int) -> bool:
        """Returns True if founder activity DM alerts are enabled (default: False)."""
        await self._ensure_mention_tables()
        if not self._db:
            return False
        async with self._db.execute(
            "SELECT enabled FROM founder_activity_alerts WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is not None:
                return bool(row["enabled"])
            return False

    async def set_founder_activity_dm(self, guild_id: int, enabled: bool) -> None:
        """Sets founder activity DM alerts preference."""
        await self._ensure_mention_tables()
        if not self._db:
            return
        await self._db.execute(
            """
            INSERT INTO founder_activity_alerts (guild_id, enabled)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET enabled = excluded.enabled;
            """,
            (guild_id, 1 if enabled else 0),
        )
        await self._db.commit()

    async def get_founder_dm_recipient(self, guild_id: int) -> Optional[int]:
        """Gets custom recipient user ID for founder activity alerts if configured."""
        await self._ensure_mention_tables()
        if not self._db:
            return None
        async with self._db.execute(
            "SELECT recipient_id FROM founder_activity_alerts WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is not None and row["recipient_id"]:
                return int(row["recipient_id"])
            return None

    async def set_founder_dm_recipient(self, guild_id: int, user_id: Optional[int]) -> None:
        """Sets custom recipient user ID for founder activity alerts."""
        await self._ensure_mention_tables()
        if not self._db:
            return
        await self._db.execute(
            """
            INSERT INTO founder_activity_alerts (guild_id, enabled, recipient_id)
            VALUES (?, 1, ?)
            ON CONFLICT(guild_id) DO UPDATE SET recipient_id = excluded.recipient_id;
            """,
            (guild_id, user_id),
        )
        await self._db.commit()




    async def set_lockdown(self, guild_id: int, enabled: bool, changed_by: Optional[int] = None) -> None:
        now = utcnow_iso()
        await self.get_or_create_guild_config(guild_id)
        await self._db.execute(
            """
            UPDATE security_state
            SET lockdown_enabled = ?,
                lockdown_started_at = CASE WHEN ? = 1 THEN ? ELSE NULL END,
                changed_by = ?,
                updated_at = ?
            WHERE guild_id = ?
            """,
            (int(enabled), int(enabled), now, changed_by, now, guild_id),
        )
        await self._db.commit()

    # ==========================================
    # WHITELIST
    # ==========================================

    async def add_whitelist(self, guild_id: int, target_id: int, target_type: str, added_by: int) -> bool:
        await self.get_or_create_guild_config(guild_id)
        now = utcnow_iso()
        try:
            await self._db.execute(
                """
                INSERT INTO security_whitelist (guild_id, target_id, target_type, added_by, added_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, target_id, target_type) DO NOTHING
                """,
                (guild_id, target_id, target_type, added_by, now),
            )
            await self._db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add whitelist: {e}")
            return False

    async def remove_whitelist(self, guild_id: int, target_id: int, target_type: str) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM security_whitelist WHERE guild_id = ? AND target_id = ? AND target_type = ?",
            (guild_id, target_id, target_type),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def get_whitelist(self, guild_id: int) -> List[Dict[str, Any]]:
        async with self._db.execute(
            "SELECT target_id, target_type, added_by, added_at FROM security_whitelist WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def is_whitelisted(self, guild_id: int, user_id: int, role_ids: Optional[List[int]] = None) -> bool:
        """Check if user or any of their roles are on the security whitelist."""
        # Check user
        async with self._db.execute(
            "SELECT 1 FROM security_whitelist WHERE guild_id = ? AND target_id = ? AND target_type = 'user'",
            (guild_id, user_id),
        ) as cursor:
            if await cursor.fetchone():
                return True

        # Check roles
        if role_ids:
            placeholders = ",".join("?" for _ in role_ids)
            sql = f"SELECT 1 FROM security_whitelist WHERE guild_id = ? AND target_type = 'role' AND target_id IN ({placeholders})"
            async with self._db.execute(sql, [guild_id] + role_ids) as cursor:
                if await cursor.fetchone():
                    return True

        return False

    # ==========================================
    # SECURITY INCIDENTS
    # ==========================================

    async def record_security_incident(self, incident: SecurityIncident) -> None:
        await self.get_or_create_guild_config(incident.guild_id)
        await self._db.execute(
            """
            INSERT INTO security_incidents (
                event_id, guild_id, timestamp, event_type, executor_id, executor_name,
                target_id, target_name, action, detected_count, threshold, audit_log_id,
                reason, automated_action, result, severity, audit_verified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident.event_id,
                incident.guild_id,
                incident.timestamp,
                incident.event_type,
                incident.executor_id,
                incident.executor_name,
                incident.target_id,
                incident.target_name,
                incident.action,
                incident.detected_count,
                incident.threshold,
                incident.audit_log_id,
                incident.reason,
                incident.automated_action,
                incident.result,
                incident.severity,
                int(incident.audit_verified),
            ),
        )
        await self._db.commit()

    async def get_security_incidents(
        self,
        guild_id: int,
        limit: int = 10,
        event_type: Optional[str] = None,
        executor_id: Optional[int] = None,
        severity: Optional[str] = None,
    ) -> List[SecurityIncident]:
        conditions = ["guild_id = ?"]
        params: List[Any] = [guild_id]

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if executor_id:
            conditions.append("executor_id = ?")
            params.append(executor_id)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)

        sql = f"""
            SELECT * FROM security_incidents
            WHERE {' AND '.join(conditions)}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)

        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [
                SecurityIncident(
                    event_id=row["event_id"],
                    guild_id=row["guild_id"],
                    timestamp=row["timestamp"],
                    event_type=row["event_type"],
                    executor_id=row["executor_id"],
                    executor_name=row["executor_name"],
                    target_id=row["target_id"],
                    target_name=row["target_name"],
                    action=row["action"],
                    detected_count=row["detected_count"],
                    threshold=row["threshold"],
                    audit_log_id=row["audit_log_id"],
                    reason=row["reason"],
                    automated_action=row["automated_action"],
                    result=row["result"],
                    severity=row["severity"],
                    audit_verified=bool(row["audit_verified"]),
                )
                for row in rows
            ]

    # ==========================================
    # VIOLATION HISTORY
    # ==========================================

    async def record_violation(self, guild_id: int, executor_id: int, event_type: str) -> int:
        """Increment or insert violation record and return new violation count."""
        await self.get_or_create_guild_config(guild_id)
        now = utcnow_iso()
        async with self._db.execute(
            """
            SELECT id, violation_count FROM violation_history
            WHERE guild_id = ? AND executor_id = ? AND event_type = ?
            """,
            (guild_id, executor_id, event_type),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            new_count = row["violation_count"] + 1
            await self._db.execute(
                """
                UPDATE violation_history
                SET violation_count = ?, last_violation_at = ?
                WHERE id = ?
                """,
                (new_count, now, row["id"]),
            )
            await self._db.commit()
            return new_count
        else:
            await self._db.execute(
                """
                INSERT INTO violation_history (
                    guild_id, executor_id, event_type, violation_count, first_violation_at, last_violation_at
                ) VALUES (?, ?, ?, 1, ?, ?)
                """,
                (guild_id, executor_id, event_type, now, now),
            )
            await self._db.commit()
            return 1

    async def get_violation_count(self, guild_id: int, executor_id: int, event_type: str) -> int:
        async with self._db.execute(
            "SELECT violation_count FROM violation_history WHERE guild_id = ? AND executor_id = ? AND event_type = ?",
            (guild_id, executor_id, event_type),
        ) as cursor:
            row = await cursor.fetchone()
            return row["violation_count"] if row else 0

    # ==========================================
    # PERSISTENT COOLDOWNS
    # ==========================================

    async def set_persistent_cooldown(
        self, guild_id: int, user_id: Optional[int], action: str, expires_at: str
    ) -> None:
        await self.get_or_create_guild_config(guild_id)
        now = utcnow_iso()
        await self._db.execute(
            """
            INSERT INTO persistent_cooldowns (guild_id, user_id, action, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id, action) DO UPDATE SET
                expires_at = excluded.expires_at,
                created_at = excluded.created_at
            """,
            (guild_id, user_id or 0, action, expires_at, now),
        )
        await self._db.commit()

    async def get_persistent_cooldown(
        self, guild_id: int, user_id: Optional[int], action: str
    ) -> Optional[str]:
        async with self._db.execute(
            "SELECT expires_at FROM persistent_cooldowns WHERE guild_id = ? AND user_id = ? AND action = ?",
            (guild_id, user_id or 0, action),
        ) as cursor:
            row = await cursor.fetchone()
            return row["expires_at"] if row else None

    async def delete_persistent_cooldown(
        self, guild_id: int, user_id: Optional[int], action: str
    ) -> None:
        await self._db.execute(
            "DELETE FROM persistent_cooldowns WHERE guild_id = ? AND user_id = ? AND action = ?",
            (guild_id, user_id or 0, action),
        )
        await self._db.commit()

    # ==========================================
    # MODERATION WARNINGS
    # ==========================================

    async def add_warning(
        self, guild_id: int, user_id: int, moderator_id: int, reason: str, expires_at: Optional[str] = None
    ) -> int:
        await self.get_or_create_guild_config(guild_id)
        now = utcnow_iso()
        cursor = await self._db.execute(
            """
            INSERT INTO moderation_warnings (guild_id, user_id, moderator_id, reason, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, moderator_id, reason, now, expires_at),
        )
        await self._db.commit()
        return cursor.lastrowid or 0

    async def get_warnings(self, guild_id: int, user_id: int) -> List[ModerationWarning]:
        async with self._db.execute(
            """
            SELECT * FROM moderation_warnings
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at DESC
            """,
            (guild_id, user_id),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                ModerationWarning(
                    id=row["id"],
                    guild_id=row["guild_id"],
                    user_id=row["user_id"],
                    moderator_id=row["moderator_id"],
                    reason=row["reason"],
                    created_at=row["created_at"],
                    expires_at=row["expires_at"],
                )
                for row in rows
            ]

    async def delete_warning(self, warning_id: int, guild_id: int) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM moderation_warnings WHERE id = ? AND guild_id = ?",
            (warning_id, guild_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def clear_warnings(self, guild_id: int, user_id: int) -> int:
        cursor = await self._db.execute(
            "DELETE FROM moderation_warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self._db.commit()
        return cursor.rowcount

    # ==========================================
    # WELCOME CONFIG
    # ==========================================

    async def get_welcome_config(self, guild_id: int) -> WelcomeConfig:
        await self.get_or_create_guild_config(guild_id)
        async with self._db.execute(
            "SELECT * FROM welcome_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return WelcomeConfig(guild_id=guild_id)

        return WelcomeConfig(
            guild_id=row["guild_id"],
            welcome_channel_id=row["welcome_channel_id"],
            goodbye_channel_id=row["goodbye_channel_id"],
            welcome_message=row["welcome_message"],
            goodbye_message=row["goodbye_message"],
            autorole_id=row["autorole_id"],
            dm_enabled=bool(row["dm_enabled"]),
            embed_enabled=bool(row["embed_enabled"]),
            updated_at=row["updated_at"],
        )

    async def update_welcome_config(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_or_create_guild_config(guild_id)
        valid = {
            "welcome_channel_id", "goodbye_channel_id", "welcome_message",
            "goodbye_message", "autorole_id", "dm_enabled", "embed_enabled"
        }
        updates = {k: v for k, v in kwargs.items() if k in valid}
        if not updates:
            return

        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]

        sql = f"UPDATE welcome_config SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    # ==========================================
    # LOGGING CONFIG
    # ==========================================

    async def get_logging_config(self, guild_id: int) -> LoggingConfig:
        await self.get_or_create_guild_config(guild_id)
        async with self._db.execute(
            "SELECT * FROM logging_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return LoggingConfig(guild_id=guild_id)

        return LoggingConfig(
            guild_id=row["guild_id"],
            general_channel_id=row["general_channel_id"],
            moderation_channel_id=row["moderation_channel_id"],
            security_channel_id=row["security_channel_id"],
            automod_channel_id=row["automod_channel_id"],
            member_channel_id=row["member_channel_id"],
            message_channel_id=row["message_channel_id"],
            voice_channel_id=row["voice_channel_id"],
            updated_at=row["updated_at"],
        )

    async def update_logging_config(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_or_create_guild_config(guild_id)
        valid = {
            "general_channel_id", "moderation_channel_id", "security_channel_id",
            "automod_channel_id", "member_channel_id", "message_channel_id", "voice_channel_id"
        }
        updates = {k: v for k, v in kwargs.items() if k in valid}
        if not updates:
            return

        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]

        sql = f"UPDATE logging_config SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    # ==========================================
    # TICKET CONFIG & TICKETS
    # ==========================================

    async def get_ticket_config(self, guild_id: int) -> TicketConfig:
        await self.get_or_create_guild_config(guild_id)
        async with self._db.execute(
            "SELECT * FROM ticket_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return TicketConfig(guild_id=guild_id)

        return TicketConfig(
            guild_id=row["guild_id"],
            category_id=row["category_id"],
            log_channel_id=row["log_channel_id"],
            support_role_id=row["support_role_id"],
            transcript_enabled=bool(row["transcript_enabled"]),
            updated_at=row["updated_at"],
        )

    async def update_ticket_config(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_or_create_guild_config(guild_id)
        valid = {"category_id", "log_channel_id", "support_role_id", "transcript_enabled"}
        updates = {k: v for k, v in kwargs.items() if k in valid}
        if not updates:
            return

        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]

        sql = f"UPDATE ticket_config SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    async def create_ticket(self, guild_id: int, channel_id: int, creator_id: int) -> int:
        await self.get_or_create_guild_config(guild_id)
        now = utcnow_iso()
        cursor = await self._db.execute(
            """
            INSERT INTO tickets (guild_id, channel_id, creator_id, status, created_at)
            VALUES (?, ?, ?, 'open', ?)
            """,
            (guild_id, channel_id, creator_id, now),
        )
        await self._db.commit()
        return cursor.lastrowid or 0

    async def get_ticket_by_channel(self, channel_id: int) -> Optional[TicketRecord]:
        async with self._db.execute(
            "SELECT * FROM tickets WHERE channel_id = ?", (channel_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return TicketRecord(
                ticket_id=row["ticket_id"],
                guild_id=row["guild_id"],
                channel_id=row["channel_id"],
                creator_id=row["creator_id"],
                status=row["status"],
                created_at=row["created_at"],
                closed_at=row["closed_at"],
                closed_by=row["closed_by"],
            )

    async def get_open_tickets(self, guild_id: int) -> List[TicketRecord]:
        """Fetch all open tickets for a guild."""
        async with self._db.execute(
            "SELECT * FROM tickets WHERE guild_id = ? AND status = 'open'", (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                TicketRecord(
                    ticket_id=row["ticket_id"],
                    guild_id=row["guild_id"],
                    channel_id=row["channel_id"],
                    creator_id=row["creator_id"],
                    status=row["status"],
                    created_at=row["created_at"],
                    closed_at=row["closed_at"],
                    closed_by=row["closed_by"],
                )
                for row in rows
            ]

    async def close_ticket(self, channel_id: int, closed_by: Optional[int] = None) -> bool:
        now = utcnow_iso()
        cursor = await self._db.execute(
            "UPDATE tickets SET status = 'closed', closed_at = ?, closed_by = ? WHERE (channel_id = ? OR ticket_id = ?) AND status = 'open'",
            (now, closed_by, channel_id, channel_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    # ==========================================
    # AUTOMOD CONFIG
    # ==========================================

    async def get_automod_config(self, guild_id: int) -> AutoModConfig:
        await self.get_or_create_guild_config(guild_id)
        async with self._db.execute(
            "SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return AutoModConfig(guild_id=guild_id)

        return AutoModConfig(
            guild_id=row["guild_id"],
            spam_detection=bool(row["spam_detection"]),
            spam_limit=row["spam_limit"],
            spam_window=row["spam_window"],
            mention_limit=row["mention_limit"],
            repeated_limit=row["repeated_limit"],
            banned_words_enabled=bool(row["banned_words_enabled"]),
            invite_links_block=bool(row["invite_links_block"]),
            suspicious_links_block=bool(row["suspicious_links_block"]),
            excessive_emojis_block=bool(row["excessive_emojis_block"]),
            emoji_limit=row["emoji_limit"],
            excessive_caps_block=bool(row["excessive_caps_block"]),
            caps_percentage=row["caps_percentage"],
            action=row["action"],
            banned_words=row["banned_words"] or "",
            updated_at=row["updated_at"],
        )

    async def update_automod_config(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_or_create_guild_config(guild_id)
        valid = {
            "spam_detection", "spam_limit", "spam_window", "mention_limit",
            "repeated_limit", "banned_words_enabled", "invite_links_block",
            "suspicious_links_block", "excessive_emojis_block", "emoji_limit",
            "excessive_caps_block", "caps_percentage", "action", "banned_words"
        }
        updates = {k: v for k, v in kwargs.items() if k in valid}
        if not updates:
            return

        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]

        sql = f"UPDATE automod_config SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    # ==========================================
    # SUGGESTION CONFIG & RECORDS
    # ==========================================

    async def get_suggestion_config(self, guild_id: int) -> SuggestionConfig:
        await self.get_or_create_guild_config(guild_id)
        async with self._db.execute(
            "SELECT * FROM suggestion_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return SuggestionConfig(guild_id=guild_id)

        return SuggestionConfig(
            guild_id=row["guild_id"],
            suggestion_channel_id=row["suggestion_channel_id"],
            review_channel_id=row["review_channel_id"],
            staff_role_id=row["staff_role_id"],
            voting_enabled=bool(row["voting_enabled"]),
            discussion_enabled=bool(row["discussion_enabled"]),
            cooldown_seconds=row["cooldown_seconds"],
            minimum_length=row["minimum_length"],
            maximum_length=row["maximum_length"],
            show_rejection_reason=bool(row["show_rejection_reason"]),
            notifications_enabled=bool(row["notifications_enabled"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    async def update_suggestion_config(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_or_create_guild_config(guild_id)
        valid = {
            "suggestion_channel_id", "review_channel_id", "staff_role_id",
            "voting_enabled", "discussion_enabled", "cooldown_seconds",
            "minimum_length", "maximum_length", "show_rejection_reason",
            "notifications_enabled"
        }
        updates = {k: v for k, v in kwargs.items() if k in valid}
        if not updates:
            return

        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]

        sql = f"UPDATE suggestion_config SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    async def create_suggestion(
        self, guild_id: int, channel_id: int, message_id: int, author_id: int, content: str
    ) -> int:
        now = utcnow_iso()
        cursor = await self._db.execute(
            """
            INSERT INTO suggestions (
                guild_id, channel_id, message_id, author_id, content,
                status, upvotes, downvotes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', 0, 0, ?, ?)
            """,
            (guild_id, channel_id, message_id, author_id, content, now, now),
        )
        await self._db.commit()
        return cursor.lastrowid or 0

    async def get_suggestion(self, suggestion_id: int) -> Optional[SuggestionRecord]:
        async with self._db.execute(
            "SELECT * FROM suggestions WHERE suggestion_id = ?", (suggestion_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return SuggestionRecord(
                suggestion_id=row["suggestion_id"],
                guild_id=row["guild_id"],
                channel_id=row["channel_id"],
                message_id=row["message_id"],
                author_id=row["author_id"],
                content=row["content"],
                status=row["status"],
                reason=row["reason"],
                upvotes=row["upvotes"],
                downvotes=row["downvotes"],
                thread_id=row["thread_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                reviewed_by=row["reviewed_by"],
                reviewed_at=row["reviewed_at"],
            )

    async def update_suggestion_status(
        self, suggestion_id: int, status: str, reviewed_by: int, reason: Optional[str] = None
    ) -> bool:
        now = utcnow_iso()
        cursor = await self._db.execute(
            """
            UPDATE suggestions
            SET status = ?, reviewed_by = ?, reviewed_at = ?, reason = ?, updated_at = ?
            WHERE suggestion_id = ?
            """,
            (status, reviewed_by, now, reason, now, suggestion_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def update_suggestion_thread(self, suggestion_id: int, thread_id: int) -> None:
        await self._db.execute(
            "UPDATE suggestions SET thread_id = ? WHERE suggestion_id = ?",
            (thread_id, suggestion_id),
        )
        await self._db.commit()

    async def delete_suggestion(self, suggestion_id: int) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM suggestions WHERE suggestion_id = ?", (suggestion_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def cast_vote(
        self, guild_id: int, suggestion_id: int, user_id: int, vote_type: str
    ) -> Tuple[int, int, str]:
        """
        Atomic vote casting with unique per-user enforcement.
        Returns (upvotes, downvotes, action: 'added' | 'switched' | 'removed').
        """
        now = utcnow_iso()
        action_taken = "added"

        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT vote_type FROM suggestion_votes WHERE guild_id = ? AND suggestion_id = ? AND user_id = ?",
                (guild_id, suggestion_id, user_id),
            )
            existing = await cur.fetchone()

            if existing:
                if existing["vote_type"] == vote_type:
                    # User clicked same vote -> Remove vote
                    await cur.execute(
                        "DELETE FROM suggestion_votes WHERE guild_id = ? AND suggestion_id = ? AND user_id = ?",
                        (guild_id, suggestion_id, user_id),
                    )
                    action_taken = "removed"
                else:
                    # User switched vote
                    await cur.execute(
                        "UPDATE suggestion_votes SET vote_type = ?, updated_at = ? WHERE guild_id = ? AND suggestion_id = ? AND user_id = ?",
                        (vote_type, now, guild_id, suggestion_id, user_id),
                    )
                    action_taken = "switched"
            else:
                # New vote
                await cur.execute(
                    """
                    INSERT INTO suggestion_votes (guild_id, suggestion_id, user_id, vote_type, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (guild_id, suggestion_id, user_id, vote_type, now, now),
                )
                action_taken = "added"

            # Recalculate upvotes and downvotes atomically
            await cur.execute(
                "SELECT COUNT(*) FROM suggestion_votes WHERE suggestion_id = ? AND vote_type = 'upvote'",
                (suggestion_id,),
            )
            upvotes = (await cur.fetchone())[0]

            await cur.execute(
                "SELECT COUNT(*) FROM suggestion_votes WHERE suggestion_id = ? AND vote_type = 'downvote'",
                (suggestion_id,),
            )
            downvotes = (await cur.fetchone())[0]

            await cur.execute(
                "UPDATE suggestions SET upvotes = ?, downvotes = ?, updated_at = ? WHERE suggestion_id = ?",
                (upvotes, downvotes, now, suggestion_id),
            )
            await self._db.commit()

        return upvotes, downvotes, action_taken

    async def get_vote_counts(self, suggestion_id: int) -> Tuple[int, int]:
        async with self._db.execute(
            "SELECT upvotes, downvotes FROM suggestions WHERE suggestion_id = ?",
            (suggestion_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return 0, 0
            return row["upvotes"], row["downvotes"]

    # ==========================================
    # RAID CONFIG & INCIDENTS
    # ==========================================

    async def get_raid_config(self, guild_id: int) -> RaidConfig:
        await self.get_or_create_guild_config(guild_id)
        async with self._db.execute(
            "SELECT * FROM raid_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return RaidConfig(guild_id=guild_id)

        return RaidConfig(
            guild_id=row["guild_id"],
            enabled=bool(row["enabled"]),
            baseline_enabled=bool(row["baseline_enabled"]),
            join_threshold=row["join_threshold"],
            join_multiplier=row["join_multiplier"],
            account_age_threshold_hours=row["account_age_threshold_hours"],
            risk_threshold_elevated=row["risk_threshold_elevated"],
            risk_threshold_suspicious=row["risk_threshold_suspicious"],
            risk_threshold_high=row["risk_threshold_high"],
            risk_threshold_critical=row["risk_threshold_critical"],
            observation_window_seconds=row["observation_window_seconds"],
            quiet_period_seconds=row["quiet_period_seconds"],
            alert_cooldown_seconds=row["alert_cooldown_seconds"],
            auto_containment=bool(row["auto_containment"]),
            safe_mode_enabled=bool(row["safe_mode_enabled"]),
            updated_at=row["updated_at"] or "",
        )

    async def update_raid_config(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_or_create_guild_config(guild_id)
        valid = {
            "enabled", "baseline_enabled", "join_threshold", "join_multiplier",
            "account_age_threshold_hours", "risk_threshold_elevated", "risk_threshold_suspicious",
            "risk_threshold_high", "risk_threshold_critical", "observation_window_seconds",
            "quiet_period_seconds", "alert_cooldown_seconds", "auto_containment", "safe_mode_enabled"
        }
        updates = {k: v for k, v in kwargs.items() if k in valid}
        if not updates:
            return

        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]

        sql = f"UPDATE raid_config SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    async def create_raid_incident(
        self, guild_id: int, incident_id: str, risk_level: str, initial_score: int
    ) -> int:
        now = utcnow_iso()
        cursor = await self._db.execute(
            """
            INSERT INTO raid_incidents (
                guild_id, incident_id, started_at, status, risk_level, current_score, maximum_score
            ) VALUES (?, ?, ?, 'OPEN', ?, ?, ?)
            """,
            (guild_id, incident_id, now, risk_level, initial_score, initial_score),
        )
        await self._db.commit()
        return cursor.lastrowid or 0

    async def get_active_raid_incident(self, guild_id: int) -> Optional[RaidIncident]:
        async with self._db.execute(
            "SELECT * FROM raid_incidents WHERE guild_id = ? AND status IN ('OPEN', 'MONITORING', 'ESCALATED') ORDER BY started_at DESC LIMIT 1",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return RaidIncident(
                id=row["id"],
                guild_id=row["guild_id"],
                incident_id=row["incident_id"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                status=row["status"],
                risk_level=row["risk_level"],
                current_score=row["current_score"],
                maximum_score=row["maximum_score"],
                resolved_at=row["resolved_at"],
                resolved_by=row["resolved_by"],
            )

    async def update_raid_incident_score(
        self, incident_id: str, current_score: int, risk_level: str
    ) -> None:
        await self._db.execute(
            """
            UPDATE raid_incidents
            SET current_score = ?,
                maximum_score = MAX(maximum_score, ?),
                risk_level = ?
            WHERE incident_id = ?
            """,
            (current_score, current_score, risk_level, incident_id),
        )
        await self._db.commit()

    async def resolve_raid_incident(
        self, incident_id: str, resolved_by: Optional[int] = None, status: str = "RESOLVED"
    ) -> None:
        now = utcnow_iso()
        await self._db.execute(
            """
            UPDATE raid_incidents
            SET status = ?, ended_at = ?, resolved_at = ?, resolved_by = ?
            WHERE incident_id = ?
            """,
            (status, now, now, resolved_by, incident_id),
        )
        await self._db.commit()

    async def record_raid_event(
        self, incident_id: str, guild_id: int, event_type: str, user_id: Optional[int], channel_id: Optional[int], metadata: str = ""
    ) -> None:
        now = utcnow_iso()
        await self._db.execute(
            """
            INSERT INTO raid_events (incident_id, guild_id, event_type, user_id, channel_id, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (incident_id, guild_id, event_type, user_id, channel_id, now, metadata),
        )
        await self._db.commit()

    # ==========================================
    # VOICEGUARD
    # ==========================================

    async def get_voiceguard_config(self, guild_id: int) -> VoiceGuardConfig:
        await self.get_or_create_guild_config(guild_id)
        async with self._db.execute(
            "SELECT * FROM voiceguard_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return VoiceGuardConfig(guild_id=guild_id)

        return VoiceGuardConfig(
            guild_id=row["guild_id"],
            enabled=bool(row["enabled"]),
            default_threshold=row["default_threshold"],
            extreme_threshold=row["extreme_threshold"],
            minimum_duration_ms=row["minimum_duration_ms"],
            warning_limit=row["warning_limit"],
            violation_decay_seconds=row["violation_decay_seconds"],
            alert_cooldown_seconds=row["alert_cooldown_seconds"],
            automatic_action=row["automatic_action"] or "warn",
            updated_at=row["updated_at"] or "",
        )

    async def update_voiceguard_config(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_or_create_guild_config(guild_id)
        valid = {
            "enabled", "default_threshold", "extreme_threshold", "minimum_duration_ms",
            "warning_limit", "violation_decay_seconds", "alert_cooldown_seconds", "automatic_action"
        }
        updates = {k: v for k, v in kwargs.items() if k in valid}
        if not updates:
            return

        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]

        sql = f"UPDATE voiceguard_config SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    async def record_voice_incident(
        self, guild_id: int, user_id: int, channel_id: int, peak: float, avg: float, score: int, severity: str, action: str
    ) -> int:
        now = utcnow_iso()
        cursor = await self._db.execute(
            """
            INSERT INTO voice_incidents (
                guild_id, user_id, channel_id, started_at, peak_level, average_level,
                risk_score, severity, action_taken
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, channel_id, now, peak, avg, score, severity, action),
        )
        await self._db.commit()
        return cursor.lastrowid or 0

    # ==========================================
    # AUTOMATION CONFIG
    # ==========================================

    async def get_automation_config(self, guild_id: int) -> AutomationConfig:
        await self.get_or_create_guild_config(guild_id)
        async with self._db.execute(
            "SELECT * FROM automation_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return AutomationConfig(guild_id=guild_id)

        return AutomationConfig(
            guild_id=row["guild_id"],
            security_monitor=bool(row["security_monitor"]),
            raid_detection=bool(row["raid_detection"]),
            automod=bool(row["automod"]),
            voiceguard=bool(row["voiceguard"]),
            welcome=bool(row["welcome"]),
            autorole=bool(row["autorole"]),
            logging=bool(row["logging"]),
            ticket_automation=bool(row["ticket_automation"]),
            suggestion_automation=bool(row["suggestion_automation"]),
            database_maintenance=bool(row["database_maintenance"]),
            health_monitor=bool(row["health_monitor"]),
            updated_at=row["updated_at"] or "",
        )

    async def update_automation_config(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_or_create_guild_config(guild_id)
        valid = {
            "security_monitor", "raid_detection", "automod", "voiceguard",
            "welcome", "autorole", "logging", "ticket_automation",
            "suggestion_automation", "database_maintenance", "health_monitor"
        }
        updates = {k: v for k, v in kwargs.items() if k in valid}
        if not updates:
            return

        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]

        sql = f"UPDATE automation_config SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    # ==========================================
    # CLEANUP / RETENTION
    # ==========================================

    async def cleanup_expired_data(self, violation_retention_seconds: int = 86400) -> Dict[str, int]:
        """
        Cleanup temporary expired data:
        - Expired persistent cooldowns
        - Violations older than retention window
        """
        counts = {"cooldowns": 0, "violations": 0}
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now_dt.isoformat()

        # Expired persistent cooldowns
        cursor = await self._db.execute(
            "DELETE FROM persistent_cooldowns WHERE expires_at <= ?", (now_iso,)
        )
        counts["cooldowns"] = cursor.rowcount

        # Violation history older than retention window
        cutoff_iso = (now_dt - datetime.timedelta(seconds=violation_retention_seconds)).isoformat()
        cursor = await self._db.execute(
            "DELETE FROM violation_history WHERE last_violation_at <= ?", (cutoff_iso,)
        )
        counts["violations"] = cursor.rowcount

        await self._db.commit()
        return counts

    # ---------------------------------------------------------------------------
    # Interactive Incidents
    # ---------------------------------------------------------------------------

    async def create_interactive_incident(self, incident: InteractiveIncident) -> None:
        """Insert or replace an interactive incident."""
        if not self._db:
            return
        if incident.guild_id:
            try:
                await self.get_or_create_guild_config(incident.guild_id)
            except Exception:
                pass
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS interactive_incidents (
                incident_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                report_type TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id INTEGER,
                actor_name TEXT,
                target_id INTEGER,
                target_name TEXT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                action_taken TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                severity TEXT NOT NULL DEFAULT 'HIGH',
                details_json TEXT,
                dm_message_id INTEGER,
                dm_channel_id INTEGER,
                channel_message_id INTEGER,
                report_channel_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            )
            """
        )
        sql = """
            INSERT OR REPLACE INTO interactive_incidents (
                incident_id, guild_id, report_type, event_type, actor_id, actor_name,
                target_id, target_name, title, description, action_taken, status,
                severity, details_json, dm_message_id, dm_channel_id,
                channel_message_id, report_channel_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = utcnow_iso()
        await self._db.execute(
            sql,
            (
                incident.incident_id,
                incident.guild_id,
                incident.report_type,
                incident.event_type,
                incident.actor_id,
                incident.actor_name,
                incident.target_id,
                incident.target_name,
                incident.title,
                incident.description,
                incident.action_taken,
                incident.status,
                incident.severity,
                incident.details_json,
                incident.dm_message_id,
                incident.dm_channel_id,
                incident.channel_message_id,
                incident.report_channel_id,
                incident.created_at or now,
                incident.updated_at or now,
            ),
        )
        await self._db.commit()

    async def get_interactive_incident(self, incident_id: str) -> Optional[InteractiveIncident]:
        """Fetch an interactive incident by ID."""
        if not self._db:
            return None
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS interactive_incidents (
                incident_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                report_type TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id INTEGER,
                actor_name TEXT,
                target_id INTEGER,
                target_name TEXT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                action_taken TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                severity TEXT NOT NULL DEFAULT 'HIGH',
                details_json TEXT,
                dm_message_id INTEGER,
                dm_channel_id INTEGER,
                channel_message_id INTEGER,
                report_channel_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            )
            """
        )
        async with self._db.execute(
            "SELECT * FROM interactive_incidents WHERE incident_id = ?", (incident_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return InteractiveIncident(
                incident_id=row["incident_id"],
                guild_id=row["guild_id"],
                report_type=row["report_type"],
                event_type=row["event_type"],
                actor_id=row["actor_id"],
                actor_name=row["actor_name"],
                target_id=row["target_id"],
                target_name=row["target_name"],
                title=row["title"],
                description=row["description"],
                action_taken=row["action_taken"],
                status=row["status"],
                severity=row["severity"],
                details_json=row["details_json"] or "{}",
                dm_message_id=row["dm_message_id"],
                dm_channel_id=row["dm_channel_id"],
                channel_message_id=row["channel_message_id"],
                report_channel_id=row["report_channel_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def update_interactive_incident_messages(
        self,
        incident_id: str,
        dm_message_id: Optional[int] = None,
        dm_channel_id: Optional[int] = None,
        channel_message_id: Optional[int] = None,
        report_channel_id: Optional[int] = None,
    ) -> None:
        """Update tracked message IDs for an incident."""
        if not self._db:
            return
        fields = ["updated_at = ?"]
        params: List[Any] = [utcnow_iso()]
        if dm_message_id is not None:
            fields.append("dm_message_id = ?")
            params.append(dm_message_id)
        if dm_channel_id is not None:
            fields.append("dm_channel_id = ?")
            params.append(dm_channel_id)
        if channel_message_id is not None:
            fields.append("channel_message_id = ?")
            params.append(channel_message_id)
        if report_channel_id is not None:
            fields.append("report_channel_id = ?")
            params.append(report_channel_id)

        params.append(incident_id)
        sql = f"UPDATE interactive_incidents SET {', '.join(fields)} WHERE incident_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    async def update_interactive_incident_status(
        self,
        incident_id: str,
        status: str,
        action_taken: Optional[str] = None,
    ) -> None:
        """Update state and action note of an interactive incident."""
        if not self._db:
            return
        fields = ["status = ?", "updated_at = ?"]
        params: List[Any] = [status, utcnow_iso()]
        if action_taken is not None:
            fields.append("action_taken = ?")
            params.append(action_taken)
        params.append(incident_id)
        sql = f"UPDATE interactive_incidents SET {', '.join(fields)} WHERE incident_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    async def get_active_interactive_incidents_for_guild(self, guild_id: int) -> List[InteractiveIncident]:
        """Fetch all non-resolved incidents for a guild."""
        if not self._db:
            return []
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS interactive_incidents (
                incident_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                report_type TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id INTEGER,
                actor_name TEXT,
                target_id INTEGER,
                target_name TEXT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                action_taken TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                severity TEXT NOT NULL DEFAULT 'HIGH',
                details_json TEXT,
                dm_message_id INTEGER,
                dm_channel_id INTEGER,
                channel_message_id INTEGER,
                report_channel_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            )
            """
        )
        async with self._db.execute(
            "SELECT * FROM interactive_incidents WHERE guild_id = ? AND status != 'RESOLVED' ORDER BY created_at DESC",
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                InteractiveIncident(
                    incident_id=r["incident_id"],
                    guild_id=r["guild_id"],
                    report_type=r["report_type"],
                    event_type=r["event_type"],
                    actor_id=r["actor_id"],
                    actor_name=r["actor_name"],
                    target_id=r["target_id"],
                    target_name=r["target_name"],
                    title=r["title"],
                    description=r["description"],
                    action_taken=r["action_taken"],
                    status=r["status"],
                    severity=r["severity"],
                    details_json=r["details_json"] or "{}",
                    dm_message_id=r["dm_message_id"],
                    dm_channel_id=r["dm_channel_id"],
                    channel_message_id=r["channel_message_id"],
                    report_channel_id=r["report_channel_id"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    async def record_incident_action(
        self,
        incident_id: str,
        actor_id: int,
        action: str,
        result: str,
        target_id: Optional[int] = None,
        failure_reason: Optional[str] = None,
    ) -> None:
        """Audit an action performed against an incident."""
        if not self._db:
            return
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS incident_action_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                actor_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_id INTEGER,
                timestamp TEXT NOT NULL,
                result TEXT NOT NULL,
                failure_reason TEXT,
                FOREIGN KEY (incident_id) REFERENCES interactive_incidents(incident_id) ON DELETE CASCADE
            )
            """
        )
        sql = """
            INSERT INTO incident_action_audit (incident_id, actor_id, action, target_id, timestamp, result, failure_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        now = utcnow_iso()
        act_id = getattr(actor_id, "id", actor_id)
        try:
            act_id = int(act_id)
        except Exception:
            act_id = 0

        tgt_id = getattr(target_id, "id", target_id)
        if tgt_id is not None:
            try:
                tgt_id = int(tgt_id)
            except Exception:
                tgt_id = None

        await self._db.execute(sql, (incident_id, act_id, str(action), tgt_id, now, str(result), str(failure_reason) if failure_reason else None))
        await self._db.commit()

    async def get_incident_actions(self, incident_id: str) -> List[IncidentActionAudit]:
        """Fetch audit trail of actions taken on an incident."""
        if not self._db:
            return []
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS incident_action_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                actor_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_id INTEGER,
                timestamp TEXT NOT NULL,
                result TEXT NOT NULL,
                failure_reason TEXT,
                FOREIGN KEY (incident_id) REFERENCES interactive_incidents(incident_id) ON DELETE CASCADE
            )
            """
        )
        async with self._db.execute(
            "SELECT * FROM incident_action_audit WHERE incident_id = ? ORDER BY id ASC",
            (incident_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                IncidentActionAudit(
                    id=r["id"],
                    incident_id=r["incident_id"],
                    actor_id=r["actor_id"],
                    action=r["action"],
                    result=r["result"],
                    target_id=r["target_id"],
                    details=r["failure_reason"],
                    created_at=r["timestamp"],
                    timestamp=r["timestamp"],
                )
                for r in rows
            ]

    # ---------------------------------------------------------------------------
    # Guild Channel Config (Canonical 17-Channel Purpose System)
    # ---------------------------------------------------------------------------

    async def get_guild_channel_config(self, guild_id: int) -> Optional[GuildChannelConfig]:
        """Fetch the canonical channel assignment configuration for a guild."""
        if not self._db:
            return None
        sql = "SELECT * FROM guild_channel_configs WHERE guild_id = ?"
        async with self._db.execute(sql, (guild_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return GuildChannelConfig(
                guild_id=row["guild_id"],
                security_alerts_channel_id=row["security_alerts_channel_id"],
                anti_nuke_channel_id=row["anti_nuke_channel_id"],
                lockdown_control_channel_id=row["lockdown_control_channel_id"],
                security_log_channel_id=row["security_log_channel_id"],
                audit_monitor_channel_id=row["audit_monitor_channel_id"],
                security_report_channel_id=row["security_report_channel_id"],
                moderation_report_channel_id=row["moderation_report_channel_id"],
                music_report_channel_id=row["music_report_channel_id"],
                room_report_channel_id=row["room_report_channel_id"],
                bot_report_channel_id=row["bot_report_channel_id"],
                system_report_channel_id=row["system_report_channel_id"],
                admin_control_channel_id=row["admin_control_channel_id"],
                server_dashboard_channel_id=row["server_dashboard_channel_id"],
                bot_config_channel_id=row["bot_config_channel_id"],
                automation_control_channel_id=row["automation_control_channel_id"],
                backup_control_channel_id=row["backup_control_channel_id"],
                system_health_channel_id=row["system_health_channel_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def set_guild_channel_config(self, guild_id: int, **kwargs) -> GuildChannelConfig:
        """Insert or replace the full canonical channel assignment configuration for a guild."""
        if not self._db:
            return GuildChannelConfig(guild_id=guild_id)
        now = utcnow_iso()
        existing = await self.get_guild_channel_config(guild_id)
        created_at = existing.created_at if existing else now

        fields = [
            "security_alerts_channel_id", "anti_nuke_channel_id", "lockdown_control_channel_id",
            "security_log_channel_id", "audit_monitor_channel_id",
            "security_report_channel_id", "moderation_report_channel_id", "music_report_channel_id",
            "room_report_channel_id", "bot_report_channel_id", "system_report_channel_id",
            "admin_control_channel_id", "server_dashboard_channel_id", "bot_config_channel_id",
            "automation_control_channel_id", "backup_control_channel_id", "system_health_channel_id",
        ]
        values = [guild_id]
        for f in fields:
            if f in kwargs:
                values.append(kwargs[f])
            elif existing:
                values.append(getattr(existing, f, None))
            else:
                values.append(None)
        values.extend([created_at, now])

        cols = ["guild_id"] + fields + ["created_at", "updated_at"]
        placeholders = ", ".join(["?"] * len(cols))
        sql = f"INSERT OR REPLACE INTO guild_channel_configs ({', '.join(cols)}) VALUES ({placeholders})"
        await self._db.execute(sql, tuple(values))
        await self._db.commit()

        cfg = await self.get_guild_channel_config(guild_id)
        return cfg or GuildChannelConfig(guild_id=guild_id, created_at=created_at, updated_at=now)

    async def update_guild_channel_config(self, guild_id: int, **kwargs) -> Optional[GuildChannelConfig]:
        """Update specific channel fields in the canonical channel assignment configuration."""
        if not self._db or not kwargs:
            return await self.get_guild_channel_config(guild_id)

        existing = await self.get_guild_channel_config(guild_id)
        if not existing:
            return await self.set_guild_channel_config(guild_id, **kwargs)

        now = utcnow_iso()
        set_clauses = []
        params = []
        for k, v in kwargs.items():
            set_clauses.append(f"{k} = ?")
            params.append(v)
        set_clauses.append("updated_at = ?")
        params.append(now)
        params.append(guild_id)

        sql = f"UPDATE guild_channel_configs SET {', '.join(set_clauses)} WHERE guild_id = ?"
        await self._db.execute(sql, tuple(params))
        await self._db.commit()
        return await self.get_guild_channel_config(guild_id)

    # ---------------------------------------------------------------------------
    # Interaction Telemetry & Latency Records
    # ---------------------------------------------------------------------------

    async def save_interaction_record(self, record: InteractionRecord) -> None:
        """Persist an interaction execution telemetry record."""
        if not self._db:
            return
        sql = """
            INSERT OR REPLACE INTO interaction_records (
                request_id, guild_id, user_id, interaction_id, interaction_type,
                command_name, module, received_at, ack_at, completed_at,
                ack_latency_ms, duration_ms, status, error_code, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = utcnow_iso()
        await self._db.execute(
            sql,
            (
                record.request_id,
                record.guild_id,
                record.user_id,
                record.interaction_id,
                record.interaction_type,
                record.command_name,
                record.module or "general",
                record.received_at,
                record.ack_at,
                record.completed_at,
                record.ack_latency_ms,
                record.duration_ms,
                record.status,
                record.error_code,
                record.created_at or now,
            ),
        )
        await self._db.commit()

    async def get_interaction_metrics(
        self, guild_id: Optional[int] = None, limit: int = 200
    ) -> Dict[str, Any]:
        """Fetch aggregated interaction latency and reliability metrics."""
        if not self._db:
            return {
                "total": 0,
                "avg_ack_latency_ms": 0.0,
                "slow_count": 0,
                "failed_count": 0,
                "success_count": 0,
            }

        where = "WHERE guild_id = ?" if guild_id else ""
        params = (guild_id, limit) if guild_id else (limit,)
        sql = f"""
            SELECT ack_latency_ms, duration_ms, status
            FROM interaction_records
            {where}
            ORDER BY received_at DESC
            LIMIT ?
        """
        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            if not rows:
                return {
                    "total": 0,
                    "avg_ack_latency_ms": 0.0,
                    "slow_count": 0,
                    "failed_count": 0,
                    "success_count": 0,
                }

            total = len(rows)
            ack_latencies = [r["ack_latency_ms"] for r in rows if r["ack_latency_ms"] is not None]
            avg_ack = round(sum(ack_latencies) / len(ack_latencies), 1) if ack_latencies else 0.0
            slow = sum(1 for r in rows if (r["duration_ms"] or 0) > 3000.0)
            failed = sum(1 for r in rows if r["status"] == "FAILED")
            success = sum(1 for r in rows if r["status"] == "COMPLETED")

            return {
                "total": total,
                "avg_ack_latency_ms": avg_ack,
                "slow_count": slow,
                "failed_count": failed,
                "success_count": success,
            }

    # ---------------------------------------------------------------------------
    # Channel Access Config
    # ---------------------------------------------------------------------------

    async def get_channel_access_config(self, guild_id: int) -> ChannelAccessConfig:
        """Fetch or create default channel access config."""
        if not self._db:
            return ChannelAccessConfig(guild_id=guild_id)
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_access_config (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                empty_channels_only INTEGER NOT NULL DEFAULT 1,
                include_text INTEGER NOT NULL DEFAULT 1,
                include_announcement INTEGER NOT NULL DEFAULT 1,
                include_forum INTEGER NOT NULL DEFAULT 1,
                include_voice INTEGER NOT NULL DEFAULT 0,
                include_stage INTEGER NOT NULL DEFAULT 0,
                include_private INTEGER NOT NULL DEFAULT 0,
                auto_update INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        async with self._db.execute(
            "SELECT * FROM channel_access_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return ChannelAccessConfig(
                    guild_id=row["guild_id"],
                    enabled=bool(row["enabled"]),
                    empty_channels_only=bool(row["empty_channels_only"]),
                    include_text=bool(row["include_text"]),
                    include_announcement=bool(row["include_announcement"]),
                    include_forum=bool(row["include_forum"]),
                    include_voice=bool(row["include_voice"]),
                    include_stage=bool(row["include_stage"]),
                    include_private=bool(row["include_private"]),
                    auto_update=bool(row["auto_update"]),
                    updated_at=row["updated_at"] or "",
                )
        cfg = ChannelAccessConfig(guild_id=guild_id)
        await self.update_channel_access_config(cfg)
        return cfg

    async def update_channel_access_config(self, config: ChannelAccessConfig) -> None:
        """Persist channel access config."""
        if not self._db:
            return
        now_str = config.updated_at or utcnow_iso()
        async with self._db.execute("PRAGMA table_info(channel_access_config)") as cursor:
            cols = {row[1] for row in await cursor.fetchall()}

        if "created_at" in cols:
            await self._db.execute(
                """
                INSERT OR REPLACE INTO channel_access_config (
                    guild_id, enabled, empty_channels_only, include_text, include_announcement,
                    include_forum, include_voice, include_stage, include_private, auto_update, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config.guild_id,
                    int(config.enabled),
                    int(config.empty_channels_only),
                    int(config.include_text),
                    int(config.include_announcement),
                    int(config.include_forum),
                    int(config.include_voice),
                    int(config.include_stage),
                    int(config.include_private),
                    int(config.auto_update),
                    now_str,
                    now_str,
                ),
            )
        else:
            await self._db.execute(
                """
                INSERT OR REPLACE INTO channel_access_config (
                    guild_id, enabled, empty_channels_only, include_text, include_announcement,
                    include_forum, include_voice, include_stage, include_private, auto_update, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config.guild_id,
                    int(config.enabled),
                    int(config.empty_channels_only),
                    int(config.include_text),
                    int(config.include_announcement),
                    int(config.include_forum),
                    int(config.include_voice),
                    int(config.include_stage),
                    int(config.include_private),
                    int(config.auto_update),
                    now_str,
                ),
            )
        await self._db.commit()

    async def record_channel_access_state(self, state: ChannelAccessState) -> None:
        """Persist channel access inspection/modification state."""
        if not self._db:
            return
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_access_state (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                channel_type TEXT NOT NULL,
                last_checked TEXT NOT NULL,
                access_status TEXT NOT NULL,
                last_updated TEXT,
                error_code TEXT,
                PRIMARY KEY (guild_id, channel_id)
            )
            """
        )
        await self._db.execute(
            """
            INSERT OR REPLACE INTO channel_access_state (
                guild_id, channel_id, channel_type, last_checked, access_status, last_updated, error_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.guild_id,
                state.channel_id,
                state.channel_type,
                state.last_checked,
                state.access_status,
                state.last_updated,
                state.error_code,
            ),
        )
        await self._db.commit()

    async def get_channel_access_state(self, guild_id: int, channel_id: int) -> Optional[ChannelAccessState]:
        """Fetch channel access state by guild and channel."""
        if not self._db:
            return None
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_access_state (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                channel_type TEXT NOT NULL,
                last_checked TEXT NOT NULL,
                access_status TEXT NOT NULL,
                last_updated TEXT,
                error_code TEXT,
                PRIMARY KEY (guild_id, channel_id)
            )
            """
        )
        async with self._db.execute(
            "SELECT * FROM channel_access_state WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return ChannelAccessState(
                    guild_id=row["guild_id"],
                    channel_id=row["channel_id"],
                    channel_type=row["channel_type"],
                    last_checked=row["last_checked"],
                    access_status=row["access_status"],
                    last_updated=row["last_updated"],
                    error_code=row["error_code"],
                )
            return None

    # ---------------------------------------------------------------------------
    # Self-Healing Logs
    # ---------------------------------------------------------------------------

    async def log_self_healing_record(
        self,
        recovery_id: str,
        error_id: str,
        component: str,
        failure_type: str,
        action_taken: str,
        attempt_number: int,
        result: str,
        duration_ms: float,
    ) -> None:
        """Persist self-healing event in SQLite."""
        if not self._db:
            return
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS self_healing_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recovery_id TEXT,
                error_id TEXT,
                component TEXT,
                failure_type TEXT,
                action_taken TEXT,
                attempt_number INTEGER,
                result TEXT,
                duration_ms REAL,
                created_at TEXT NOT NULL
            )
            """
        )
        await self._db.execute(
            """
            INSERT INTO self_healing_logs (
                recovery_id, error_id, component, failure_type,
                action_taken, attempt_number, result, duration_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recovery_id,
                error_id,
                component,
                failure_type,
                action_taken,
                attempt_number,
                result,
                duration_ms,
                utcnow_iso(),
            ),
        )
        await self._db.commit()

    # ==========================================
    # VERIFICATION SYSTEM
    # ==========================================

    async def get_verification_config(self, guild_id: int) -> VerificationConfig:
        if not self._db:
            return VerificationConfig(guild_id=guild_id)
        async with self._db.execute(
            "SELECT * FROM verification_configs WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            now = utcnow_iso()
            await self._db.execute(
                """
                INSERT OR IGNORE INTO verification_configs (
                    guild_id, enabled, role_id, channel_id, min_account_age_hours, updated_at
                ) VALUES (?, 0, NULL, NULL, 0, ?)
                """,
                (guild_id, now),
            )
            await self._db.commit()
            return VerificationConfig(guild_id=guild_id, updated_at=now)

        return VerificationConfig(
            guild_id=row["guild_id"],
            enabled=bool(row["enabled"]),
            role_id=row["role_id"],
            channel_id=row["channel_id"],
            verified_role_id=row["verified_role_id"] or row["role_id"],
            community_role_id=row["community_role_id"],
            verify_channel_id=row["verify_channel_id"] or row["channel_id"],
            welcome_channel_id=row["welcome_channel_id"],
            min_account_age_hours=row["min_account_age_hours"],
            require_2fa=bool(row["require_2fa"]),
            updated_at=row["updated_at"] or "",
        )

    async def update_verification_config(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_verification_config(guild_id)
        if not self._db:
            return
        valid = {
            "enabled", "role_id", "channel_id", "verified_role_id",
            "community_role_id", "verify_channel_id", "welcome_channel_id",
            "min_account_age_hours", "require_2fa"
        }
        updates = {k: (int(v) if isinstance(v, bool) else v) for k, v in kwargs.items() if k in valid}
        if "role_id" in updates and "verified_role_id" not in updates:
            updates["verified_role_id"] = updates["role_id"]
        if "channel_id" in updates and "verify_channel_id" not in updates:
            updates["verify_channel_id"] = updates["channel_id"]
        if not updates:
            return
        updates["updated_at"] = utcnow_iso()
        set_clauses = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [guild_id]
        await self._db.execute(
            f"UPDATE verification_configs SET {', '.join(set_clauses)} WHERE guild_id = ?",
            params,
        )
        await self._db.commit()

    async def is_user_verified(self, guild_id: int, user_id: int) -> bool:
        if not self._db:
            return False
        async with self._db.execute(
            "SELECT 1 FROM verification_records WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            return (await cursor.fetchone()) is not None

    async def record_verification(self, guild_id: int, user_id: int, account_age_hours: float = 0.0) -> None:
        if not self._db:
            return
        now = utcnow_iso()
        await self._db.execute(
            """
            INSERT OR REPLACE INTO verification_records (
                guild_id, user_id, account_age_hours, verified_at
            ) VALUES (?, ?, ?, ?)
            """,
            (guild_id, user_id, account_age_hours, now),
        )
        await self._db.commit()


