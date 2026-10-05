"""
Independent Database Connection and Schema Management for Rai Music Bot.
Operates on data/music.db with complete isolation from Main Rai tables.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiosqlite

from music_bot.config import MUSIC_DATABASE_PATH
from music_bot.database.models import MusicGuildSettings, MusicHeartbeat, QueuedTrack

logger = logging.getLogger("RaiMusic.Database")


class MusicDatabase:
    """Async SQLite Database for the independent Music Bot."""

    def __init__(self, db_path: Path = MUSIC_DATABASE_PATH):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Establish connection and apply initial schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._init_schema()
        logger.info(f"Music Bot database connected at {self.db_path}")

    async def close(self) -> None:
        """Cleanly close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("Music Bot database connection closed.")

    async def _init_schema(self) -> None:
        """Initialize dedicated Music tables."""
        async with self._lock:
            await self._db.executescript("""
                CREATE TABLE IF NOT EXISTS music_guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    request_channel_id INTEGER,
                    dj_role_id INTEGER,
                    default_volume INTEGER DEFAULT 80,
                    autoplay_enabled INTEGER DEFAULT 0,
                    auto_leave_enabled INTEGER DEFAULT 1,
                    auto_leave_timeout INTEGER DEFAULT 300,
                    natural_requests_enabled INTEGER DEFAULT 1,
                    allowed_channels_json TEXT DEFAULT '[]',
                    allowed_voice_channels_json TEXT DEFAULT '[]',
                    queue_limit INTEGER DEFAULT 200,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS music_sessions (
                    guild_id INTEGER PRIMARY KEY,
                    voice_channel_id INTEGER,
                    text_channel_id INTEGER,
                    state TEXT NOT NULL DEFAULT 'IDLE',
                    volume INTEGER DEFAULT 80,
                    loop_mode TEXT DEFAULT 'off',
                    is_paused INTEGER DEFAULT 0,
                    current_track_json TEXT,
                    started_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS music_queues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    track_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    stream_url TEXT NOT NULL,
                    duration INTEGER NOT NULL,
                    requester_id INTEGER NOT NULL,
                    requester_name TEXT NOT NULL,
                    artist TEXT,
                    thumbnail TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_music_queues_guild ON music_queues(guild_id);

                CREATE TABLE IF NOT EXISTS music_playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    is_server INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    UNIQUE(guild_id, user_id, name)
                );

                CREATE TABLE IF NOT EXISTS music_playlist_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id INTEGER NOT NULL,
                    track_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    duration INTEGER NOT NULL,
                    artist TEXT,
                    thumbnail TEXT,
                    FOREIGN KEY(playlist_id) REFERENCES music_playlists(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS music_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    artist TEXT,
                    requester_id INTEGER,
                    played_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_music_history_guild ON music_history(guild_id);

                CREATE TABLE IF NOT EXISTS music_heartbeats (
                    bot_id INTEGER PRIMARY KEY,
                    version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    active_sessions INTEGER DEFAULT 0,
                    playing_count INTEGER DEFAULT 0,
                    last_heartbeat TEXT NOT NULL
                );
            """)
            await self._db.commit()

    # =========================================================================
    # SETTINGS CRUD
    # =========================================================================

    async def get_guild_settings(self, guild_id: int) -> MusicGuildSettings:
        """Fetch guild music settings or return default."""
        async with self._lock:
            async with self._db.execute(
                "SELECT * FROM music_guild_settings WHERE guild_id = ?", (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    now = datetime.now(timezone.utc).isoformat()
                    await self._db.execute(
                        "INSERT INTO music_guild_settings (guild_id, updated_at) VALUES (?, ?)",
                        (guild_id, now),
                    )
                    await self._db.commit()
                    return MusicGuildSettings(guild_id=guild_id)

                allowed_ch = json.loads(row["allowed_channels_json"] or "[]")
                allowed_vc = json.loads(row["allowed_voice_channels_json"] or "[]")
                return MusicGuildSettings(
                    guild_id=row["guild_id"],
                    request_channel_id=row["request_channel_id"],
                    dj_role_id=row["dj_role_id"],
                    default_volume=row["default_volume"],
                    autoplay_enabled=bool(row["autoplay_enabled"]),
                    auto_leave_enabled=bool(row["auto_leave_enabled"]),
                    auto_leave_timeout=row["auto_leave_timeout"],
                    natural_requests_enabled=bool(row["natural_requests_enabled"]),
                    allowed_channels=allowed_ch,
                    allowed_voice_channels=allowed_vc,
                    queue_limit=row["queue_limit"],
                    updated_at=row["updated_at"],
                )

    async def update_guild_settings(self, settings: MusicGuildSettings) -> None:
        """Save updated guild music settings."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            await self._db.execute("""
                INSERT INTO music_guild_settings (
                    guild_id, request_channel_id, dj_role_id, default_volume,
                    autoplay_enabled, auto_leave_enabled, auto_leave_timeout,
                    natural_requests_enabled, allowed_channels_json,
                    allowed_voice_channels_json, queue_limit, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    request_channel_id = excluded.request_channel_id,
                    dj_role_id = excluded.dj_role_id,
                    default_volume = excluded.default_volume,
                    autoplay_enabled = excluded.autoplay_enabled,
                    auto_leave_enabled = excluded.auto_leave_enabled,
                    auto_leave_timeout = excluded.auto_leave_timeout,
                    natural_requests_enabled = excluded.natural_requests_enabled,
                    allowed_channels_json = excluded.allowed_channels_json,
                    allowed_voice_channels_json = excluded.allowed_voice_channels_json,
                    queue_limit = excluded.queue_limit,
                    updated_at = excluded.updated_at
            """, (
                settings.guild_id,
                settings.request_channel_id,
                settings.dj_role_id,
                settings.default_volume,
                1 if settings.autoplay_enabled else 0,
                1 if settings.auto_leave_enabled else 0,
                settings.auto_leave_timeout,
                1 if settings.natural_requests_enabled else 0,
                json.dumps(settings.allowed_channels),
                json.dumps(settings.allowed_voice_channels),
                settings.queue_limit,
                now,
            ))
            await self._db.commit()

    # =========================================================================
    # HEARTBEAT & INTER-PROCESS TELEMETRY
    # =========================================================================

    async def update_heartbeat(
        self, bot_id: int, version: str, status: str, active_sessions: int, playing_count: int
    ) -> None:
        """Write heartbeat record for external observers (Main Rai, API, Website)."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            await self._db.execute("""
                INSERT INTO music_heartbeats (
                    bot_id, version, status, active_sessions, playing_count, last_heartbeat
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(bot_id) DO UPDATE SET
                    version = excluded.version,
                    status = excluded.status,
                    active_sessions = excluded.active_sessions,
                    playing_count = excluded.playing_count,
                    last_heartbeat = excluded.last_heartbeat
            """, (bot_id, version, status, active_sessions, playing_count, now))
            await self._db.commit()

    async def get_heartbeat(self, bot_id: int) -> Optional[MusicHeartbeat]:
        """Read last heartbeat for status reporting."""
        async with self._lock:
            async with self._db.execute(
                "SELECT * FROM music_heartbeats WHERE bot_id = ?", (bot_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return MusicHeartbeat(
                    bot_id=row["bot_id"],
                    version=row["version"],
                    status=row["status"],
                    active_sessions=row["active_sessions"],
                    playing_count=row["playing_count"],
                    last_heartbeat=row["last_heartbeat"],
                )

    # =========================================================================
    # HISTORY RECORDING
    # =========================================================================

    async def record_history(
        self, guild_id: int, title: str, url: str, artist: str, requester_id: int
    ) -> None:
        """Record track to guild playback history."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            await self._db.execute("""
                INSERT INTO music_history (guild_id, title, url, artist, requester_id, played_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (guild_id, title, url, artist, requester_id, now))
            await self._db.commit()

    async def get_history(self, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent playback history."""
        async with self._lock:
            async with self._db.execute("""
                SELECT title, url, artist, requester_id, played_at
                FROM music_history
                WHERE guild_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (guild_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
