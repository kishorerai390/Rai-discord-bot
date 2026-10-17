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
from typing import Any, Dict, List, Optional, Tuple
import shutil
import aiosqlite

from music_bot.config import MUSIC_DATABASE_PATH
from music_bot.database.models import (
    MusicDJSettings,
    MusicFavorite,
    MusicGuildSettings,
    MusicHeartbeat,
    MusicPlaylist,
    PersistentMusicSession,
    QueuedTrack,
)

logger = logging.getLogger("RaiMusic.Database")


class MusicDatabase:
    """Async SQLite Database for the independent Music Bot."""

    def __init__(self, db_path: Path = MUSIC_DATABASE_PATH):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Returns True if database connection is established and alive."""
        return self._db is not None

    def backup_database(self, reason: str = "pre_migration", max_backups: int = 5) -> Optional[Path]:
        """Create a timestamped backup of music.db with bounded retention."""
        if not self.db_path.exists():
            return None
        backup_dir = self.db_path.parent / "backups" / "db"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"music_{timestamp}_{reason}.db"
        try:
            shutil.copy2(str(self.db_path), str(backup_file))
            logger.info(f"[Database] Created database backup: {backup_file.name}")

            # Retention pruning: keep only max_backups most recent
            existing = sorted(backup_dir.glob("music_*.db"), key=lambda p: p.stat().st_mtime)
            if len(existing) > max_backups:
                for old in existing[:-max_backups]:
                    try:
                        old.unlink()
                        logger.debug(f"[Database] Pruned old backup: {old.name}")
                    except Exception:
                        pass
            return backup_file
        except Exception as e:
            logger.warning(f"[Database] Failed to create backup: {e}")
            return None

    async def run_migrations(self) -> None:
        """Safe SQLite schema migration engine with automatic pre-migration backup & integrity verification."""
        if not self._db:
            return

        async with self._lock:
            await self._db.execute("PRAGMA journal_mode = WAL;")
            await self._db.execute("PRAGMA foreign_keys = ON;")

            cursor = await self._db.execute("PRAGMA user_version;")
            row = await cursor.fetchone()
            current_version = row[0] if row else 0

            TARGET_VERSION = 1
            if current_version < TARGET_VERSION:
                logger.info(f"[Database] Migrating database from v{current_version} to v{TARGET_VERSION}...")
                backup_path = self.backup_database(reason="migration_v1")

                try:
                    await self._db.execute("BEGIN IMMEDIATE TRANSACTION;")
                    await self._db.execute(f"PRAGMA user_version = {TARGET_VERSION};")
                    await self._db.commit()

                    cur_int = await self._db.execute("PRAGMA integrity_check;")
                    res_int = await cur_int.fetchone()
                    if res_int and res_int[0] == "ok":
                        logger.info(f"[Database] Migration to v{TARGET_VERSION} successful and verified.")
                    else:
                        raise RuntimeError(f"Integrity check failed: {res_int}")
                except Exception as mig_err:
                    logger.error(f"[Database] Migration failed: {mig_err}. Rolling back transaction...")
                    try:
                        await self._db.rollback()
                    except Exception:
                        pass
                    if backup_path and backup_path.exists():
                        logger.warning(f"[Database] Restoring database from pre-migration backup: {backup_path.name}")
                        await self._db.close()
                        shutil.copy2(str(backup_path), str(self.db_path))
                        self._db = await aiosqlite.connect(str(self.db_path))
                        self._db.row_factory = aiosqlite.Row
                    raise mig_err

    async def connect(self) -> None:
        """Establish connection and apply initial schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._init_schema()
        await self.run_migrations()
        logger.info(f"Music Bot database connected at {self.db_path}")

    @property
    def is_connected(self) -> bool:
        """True if SQLite connection handle is established."""
        return self._db is not None

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
                    quiet_mode INTEGER DEFAULT 0,
                    response_style TEXT DEFAULT 'normal',
                    vote_skip_threshold REAL DEFAULT 0.5,
                    dj_mode_enabled INTEGER DEFAULT 0,
                    twenty_four_seven_enabled INTEGER DEFAULT 0,
                    twenty_four_seven_channel_id INTEGER DEFAULT NULL,
                    prefix TEXT DEFAULT ',',
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
                    position_seconds INTEGER DEFAULT 0,
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

                CREATE TABLE IF NOT EXISTS music_favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    duration INTEGER NOT NULL DEFAULT 0,
                    artist TEXT,
                    thumbnail TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, url)
                );
                CREATE INDEX IF NOT EXISTS idx_music_favorites_user ON music_favorites(user_id);

                CREATE TABLE IF NOT EXISTS music_dj_settings (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 0,
                    auto_queue INTEGER DEFAULT 1,
                    recommendation_mode TEXT DEFAULT 'similar',
                    preferred_genres_json TEXT DEFAULT '[]',
                    explicit_allowed INTEGER DEFAULT 1,
                    repeat_avoidance_count INTEGER DEFAULT 15,
                    max_queue_size INTEGER DEFAULT 50,
                    recommendation_cooldown INTEGER DEFAULT 15,
                    updated_at TEXT NOT NULL
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

                CREATE TABLE IF NOT EXISTS persistent_music_sessions (
                    guild_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    session_name TEXT DEFAULT 'Default Session',
                    session_status TEXT NOT NULL DEFAULT 'SAVED',
                    current_track_json TEXT,
                    current_track_title TEXT,
                    stable_track_identifier TEXT,
                    source_provider TEXT DEFAULT 'youtube',
                    source_url TEXT,
                    track_duration INTEGER DEFAULT 0,
                    last_known_position INTEGER DEFAULT 0,
                    is_paused INTEGER DEFAULT 0,
                    queue_json TEXT DEFAULT '[]',
                    history_json TEXT DEFAULT '[]',
                    loop_mode TEXT DEFAULT 'off',
                    shuffle_enabled INTEGER DEFAULT 0,
                    volume INTEGER DEFAULT 80,
                    voice_channel_id INTEGER,
                    text_channel_id INTEGER,
                    created_by_user_id INTEGER,
                    created_by_user_name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_checkpoint TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    recovery_attempts INTEGER DEFAULT 0,
                    schema_version INTEGER DEFAULT 1,
                    is_pinned INTEGER DEFAULT 0,
                    recovery_mode TEXT DEFAULT 'MANUAL',
                    PRIMARY KEY (guild_id, session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_pers_sessions_guild ON persistent_music_sessions(guild_id);
                CREATE INDEX IF NOT EXISTS idx_pers_sessions_status ON persistent_music_sessions(session_status);
                CREATE INDEX IF NOT EXISTS idx_pers_sessions_expires ON persistent_music_sessions(expires_at);

                CREATE TABLE IF NOT EXISTS music_web_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT DEFAULT '{}',
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    result_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    processed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_music_web_actions_status ON music_web_actions(status);

                CREATE TABLE IF NOT EXISTS music_premium (
                    entity_id INTEGER PRIMARY KEY,
                    entity_type TEXT NOT NULL DEFAULT 'guild',
                    is_premium INTEGER DEFAULT 1,
                    tier TEXT DEFAULT 'premium',
                    activated_by INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS web_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    discord_user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    discriminator TEXT DEFAULT '0',
                    avatar TEXT,
                    access_token TEXT,
                    refresh_token TEXT,
                    expires_at TEXT,
                    user_data_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS music_user_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    plan TEXT NOT NULL DEFAULT 'free',
                    status TEXT NOT NULL DEFAULT 'active',
                    provider TEXT NOT NULL DEFAULT 'stripe',
                    provider_customer_id TEXT,
                    provider_subscription_id TEXT,
                    payment_reference TEXT,
                    currency TEXT DEFAULT 'usd',
                    amount INTEGER DEFAULT 0,
                    current_period_start TEXT,
                    current_period_end TEXT,
                    cancel_at_period_end INTEGER DEFAULT 0,
                    canceled_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sub_user ON music_user_subscriptions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sub_status ON music_user_subscriptions(status);

                CREATE TABLE IF NOT EXISTS payment_webhook_events (
                    event_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT,
                    status TEXT DEFAULT 'processed',
                    processed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS subscription_audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    details_json TEXT DEFAULT '{}',
                    ip_address TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_user ON subscription_audit_logs(user_id);
            """)
            await self._db.commit()

            # Ensure additional columns exist on older installations
            for col, col_type, default_val in [
                ("quiet_mode", "INTEGER", "0"),
                ("response_style", "TEXT", "'normal'"),
                ("vote_skip_threshold", "REAL", "0.5"),
                ("dj_mode_enabled", "INTEGER", "0"),
                ("twenty_four_seven_enabled", "INTEGER", "0"),
                ("twenty_four_seven_channel_id", "INTEGER", "NULL"),
                ("prefix", "TEXT", "','"),
                ("recovery_mode", "TEXT", "'MANUAL'"),
                ("session_retention_days", "INTEGER", "7"),
                ("checkpoint_interval", "INTEGER", "10"),
            ]:
                try:
                    await self._db.execute(
                        f"ALTER TABLE music_guild_settings ADD COLUMN {col} {col_type} DEFAULT {default_val}"
                    )
                    await self._db.commit()
                except Exception:
                    pass

            for col, col_type, default_val in [
                ("position_seconds", "INTEGER", "0"),
                ("queue_json", "TEXT", "'[]'"),
                ("history_json", "TEXT", "'[]'"),
            ]:
                try:
                    await self._db.execute(
                        f"ALTER TABLE music_sessions ADD COLUMN {col} {col_type} DEFAULT {default_val}"
                    )
                    await self._db.commit()
                except Exception:
                    pass

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
                        "INSERT INTO music_guild_settings (guild_id, prefix, updated_at) VALUES (?, ?, ?)",
                        (guild_id, ",", now),
                    )
                    await self._db.commit()
                    return MusicGuildSettings(guild_id=guild_id, prefix=",")

                allowed_ch = json.loads(row["allowed_channels_json"] or "[]")
                allowed_vc = json.loads(row["allowed_voice_channels_json"] or "[]")
                keys = row.keys()
                return MusicGuildSettings(
                    guild_id=row["guild_id"],
                    prefix=row["prefix"] if ("prefix" in keys and row["prefix"]) else ",",
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
                    quiet_mode=bool(row["quiet_mode"]) if "quiet_mode" in keys else False,
                    response_style=row["response_style"] if "response_style" in keys else "normal",
                    vote_skip_threshold=float(row["vote_skip_threshold"]) if "vote_skip_threshold" in keys else 0.5,
                    dj_mode_enabled=bool(row["dj_mode_enabled"]) if "dj_mode_enabled" in keys else False,
                    twenty_four_seven_enabled=bool(row["twenty_four_seven_enabled"]) if "twenty_four_seven_enabled" in keys else False,
                    twenty_four_seven_channel_id=row["twenty_four_seven_channel_id"] if "twenty_four_seven_channel_id" in keys else None,
                    recovery_mode=row["recovery_mode"] if "recovery_mode" in keys and row["recovery_mode"] else "MANUAL",
                    session_retention_days=int(row["session_retention_days"]) if "session_retention_days" in keys and row["session_retention_days"] is not None else 7,
                    checkpoint_interval=int(row["checkpoint_interval"]) if "checkpoint_interval" in keys and row["checkpoint_interval"] is not None else 10,
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
                    allowed_voice_channels_json, queue_limit, quiet_mode,
                    response_style, vote_skip_threshold, dj_mode_enabled,
                    twenty_four_seven_enabled, twenty_four_seven_channel_id, prefix,
                    recovery_mode, session_retention_days, checkpoint_interval, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    quiet_mode = excluded.quiet_mode,
                    response_style = excluded.response_style,
                    vote_skip_threshold = excluded.vote_skip_threshold,
                    dj_mode_enabled = excluded.dj_mode_enabled,
                    twenty_four_seven_enabled = excluded.twenty_four_seven_enabled,
                    twenty_four_seven_channel_id = excluded.twenty_four_seven_channel_id,
                    prefix = excluded.prefix,
                    recovery_mode = excluded.recovery_mode,
                    session_retention_days = excluded.session_retention_days,
                    checkpoint_interval = excluded.checkpoint_interval,
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
                1 if settings.quiet_mode else 0,
                settings.response_style,
                settings.vote_skip_threshold,
                1 if settings.dj_mode_enabled else 0,
                1 if settings.twenty_four_seven_enabled else 0,
                settings.twenty_four_seven_channel_id,
                settings.prefix or ",",
                getattr(settings, "recovery_mode", "MANUAL"),
                getattr(settings, "session_retention_days", 7),
                getattr(settings, "checkpoint_interval", 10),
                now,
            ))
            await self._db.commit()

    async def get_all_247_guilds(self) -> List[MusicGuildSettings]:
        """Fetch all guilds that have 24/7 mode enabled."""
        results = []
        async with self._lock:
            async with self._db.execute(
                "SELECT * FROM music_guild_settings WHERE twenty_four_seven_enabled = 1"
            ) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    keys = row.keys()
                    allowed_ch = json.loads(row["allowed_channels_json"] or "[]")
                    allowed_vc = json.loads(row["allowed_voice_channels_json"] or "[]")
                    results.append(
                        MusicGuildSettings(
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
                            quiet_mode=bool(row["quiet_mode"]) if "quiet_mode" in keys else False,
                            response_style=row["response_style"] if "response_style" in keys else "normal",
                            vote_skip_threshold=float(row["vote_skip_threshold"]) if "vote_skip_threshold" in keys else 0.5,
                            dj_mode_enabled=bool(row["dj_mode_enabled"]) if "dj_mode_enabled" in keys else False,
                            twenty_four_seven_enabled=bool(row["twenty_four_seven_enabled"]) if "twenty_four_seven_enabled" in keys else False,
                            twenty_four_seven_channel_id=row["twenty_four_seven_channel_id"] if "twenty_four_seven_channel_id" in keys else None,
                            updated_at=row["updated_at"],
                        )
                    )
        return results

    # =========================================================================
    # NEKO DJ SETTINGS
    # =========================================================================

    async def get_dj_settings(self, guild_id: int) -> MusicDJSettings:
        """Fetch guild Neko DJ settings."""
        async with self._lock:
            async with self._db.execute(
                "SELECT * FROM music_dj_settings WHERE guild_id = ?", (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return MusicDJSettings(guild_id=guild_id)
                genres = json.loads(row["preferred_genres_json"] or "[]")
                return MusicDJSettings(
                    guild_id=row["guild_id"],
                    enabled=bool(row["enabled"]),
                    auto_queue=bool(row["auto_queue"]),
                    recommendation_mode=row["recommendation_mode"],
                    preferred_genres=genres,
                    explicit_allowed=bool(row["explicit_allowed"]),
                    repeat_avoidance_count=row["repeat_avoidance_count"],
                    max_queue_size=row["max_queue_size"],
                    recommendation_cooldown=row["recommendation_cooldown"],
                    updated_at=row["updated_at"],
                )

    async def update_dj_settings(self, settings: MusicDJSettings) -> None:
        """Save Neko DJ settings."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            await self._db.execute("""
                INSERT INTO music_dj_settings (
                    guild_id, enabled, auto_queue, recommendation_mode,
                    preferred_genres_json, explicit_allowed, repeat_avoidance_count,
                    max_queue_size, recommendation_cooldown, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    auto_queue = excluded.auto_queue,
                    recommendation_mode = excluded.recommendation_mode,
                    preferred_genres_json = excluded.preferred_genres_json,
                    explicit_allowed = excluded.explicit_allowed,
                    repeat_avoidance_count = excluded.repeat_avoidance_count,
                    max_queue_size = excluded.max_queue_size,
                    recommendation_cooldown = excluded.recommendation_cooldown,
                    updated_at = excluded.updated_at
            """, (
                settings.guild_id,
                1 if settings.enabled else 0,
                1 if settings.auto_queue else 0,
                settings.recommendation_mode,
                json.dumps(settings.preferred_genres),
                1 if settings.explicit_allowed else 0,
                settings.repeat_avoidance_count,
                settings.max_queue_size,
                settings.recommendation_cooldown,
                now,
            ))
            await self._db.commit()

    # =========================================================================
    # FAVORITES SYSTEM
    # =========================================================================

    async def get_favorites(self, user_id: int) -> List[MusicFavorite]:
        """Fetch all favorite songs saved by a user."""
        async with self._lock:
            async with self._db.execute(
                "SELECT * FROM music_favorites WHERE user_id = ? ORDER BY id DESC", (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    MusicFavorite(
                        id=r["id"],
                        user_id=r["user_id"],
                        title=r["title"],
                        url=r["url"],
                        duration=r["duration"],
                        artist=r["artist"] or "Unknown Artist",
                        thumbnail=r["thumbnail"],
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]

    async def add_favorite(
        self,
        user_id: int,
        track: Optional[Any] = None,
        url: Optional[str] = None,
        duration: int = 0,
        artist: Optional[str] = None,
        thumbnail: Optional[str] = None,
        title: Optional[str] = None,
        **kwargs,
    ) -> bool:
        """Add a track to user's favorites list (supports QueuedTrack or direct parameters)."""
        if isinstance(track, QueuedTrack):
            fav_title = track.title
            fav_url = track.url
            fav_dur = track.duration or 0
            fav_art = track.artist or "Unknown Artist"
            fav_thumb = track.thumbnail
        elif title is not None:
            fav_title = title
            fav_url = url or ""
            fav_dur = duration
            fav_art = artist or "Unknown Artist"
            fav_thumb = thumbnail
        elif isinstance(track, str):
            fav_title = track
            fav_url = url or ""
            fav_dur = duration
            fav_art = artist or "Unknown Artist"
            fav_thumb = thumbnail
        else:
            fav_title = kwargs.get("title", "")
            fav_url = url or kwargs.get("url", "")
            fav_dur = duration or kwargs.get("duration", 0)
            fav_art = artist or kwargs.get("artist", "Unknown Artist")
            fav_thumb = thumbnail or kwargs.get("thumbnail")

        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            async with self._db.execute(
                "SELECT id FROM music_favorites WHERE user_id = ? AND url = ?",
                (user_id, fav_url)
            ) as cursor:
                if await cursor.fetchone():
                    return False

            try:
                await self._db.execute("""
                    INSERT INTO music_favorites (user_id, title, url, duration, artist, thumbnail, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, fav_title, fav_url, fav_dur, fav_art, fav_thumb, now))
                await self._db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False
            except Exception as e:
                logger.warning(f"Failed to add favorite for user {user_id}: {e}")
                return False

    async def remove_favorite(self, user_id: int, identifier: str) -> bool:
        """Remove a track from favorites by title or numeric ID."""
        async with self._lock:
            if identifier.isdigit():
                cursor = await self._db.execute(
                    "DELETE FROM music_favorites WHERE user_id = ? AND id = ?",
                    (user_id, int(identifier)),
                )
            else:
                cursor = await self._db.execute(
                    "DELETE FROM music_favorites WHERE user_id = ? AND (LOWER(title) LIKE ? OR url = ?)",
                    (user_id, f"%{identifier.lower()}%", identifier),
                )
            await self._db.commit()
            return cursor.rowcount > 0

    # =========================================================================
    # PLAYLIST CRUD
    # =========================================================================

    async def create_playlist(self, guild_id: int, user_id: int, name: str, is_server: bool = False) -> Optional[int]:
        """Create a new playlist."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            try:
                cursor = await self._db.execute("""
                    INSERT INTO music_playlists (guild_id, user_id, name, is_server, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (guild_id, user_id, name, 1 if is_server else 0, now))
                await self._db.commit()
                return cursor.lastrowid
            except Exception:
                return None

    async def delete_playlist(self, guild_id: int, user_id: int, name: str) -> bool:
        """Delete a playlist."""
        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM music_playlists WHERE guild_id = ? AND (user_id = ? OR is_server = 1) AND LOWER(name) = ?",
                (guild_id, user_id, name.lower()),
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def get_playlist(self, guild_id: int, name: str, user_id: Optional[int] = None) -> Optional[MusicPlaylist]:
        """Retrieve a playlist and all its tracks."""
        async with self._lock:
            query = """
                SELECT * FROM music_playlists
                WHERE guild_id = ? AND LOWER(name) = ?
            """
            params: list[Any] = [guild_id, name.lower()]
            if user_id is not None:
                query += " AND (user_id = ? OR is_server = 1)"
                params.append(user_id)

            async with self._db.execute(query, tuple(params)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                playlist_id = row["id"]

            async with self._db.execute(
                "SELECT * FROM music_playlist_tracks WHERE playlist_id = ? ORDER BY track_index ASC",
                (playlist_id,),
            ) as cursor:
                track_rows = await cursor.fetchall()
                tracks = [
                    QueuedTrack(
                        title=tr["title"],
                        url=tr["url"],
                        stream_url="",
                        duration=tr["duration"],
                        requester_id=row["user_id"],
                        requester_name="Playlist",
                        artist=tr["artist"] or "Unknown Artist",
                        thumbnail=tr["thumbnail"],
                    )
                    for tr in track_rows
                ]

            return MusicPlaylist(
                id=row["id"],
                guild_id=row["guild_id"],
                user_id=row["user_id"],
                name=row["name"],
                is_server=bool(row["is_server"]),
                created_at=row["created_at"],
                tracks=tracks,
            )

    async def get_playlists(self, guild_id: int, user_id: int) -> List[MusicPlaylist]:
        """List personal and server playlists available in this guild."""
        async with self._lock:
            async with self._db.execute("""
                SELECT p.*, COUNT(t.id) as track_count
                FROM music_playlists p
                LEFT JOIN music_playlist_tracks t ON p.id = t.playlist_id
                WHERE p.guild_id = ? AND (p.user_id = ? OR p.is_server = 1)
                GROUP BY p.id
                ORDER BY p.name ASC
            """, (guild_id, user_id)) as cursor:
                rows = await cursor.fetchall()
                return [
                    MusicPlaylist(
                        id=r["id"],
                        guild_id=r["guild_id"],
                        user_id=r["user_id"],
                        name=r["name"],
                        is_server=bool(r["is_server"]),
                        created_at=r["created_at"],
                        tracks=[],
                    )
                    for r in rows
                ]

    async def add_playlist_track(self, playlist_id: int, track: QueuedTrack) -> bool:
        """Append track to a playlist."""
        async with self._lock:
            async with self._db.execute(
                "SELECT COALESCE(MAX(track_index), 0) + 1 FROM music_playlist_tracks WHERE playlist_id = ?",
                (playlist_id,),
            ) as cursor:
                next_idx = (await cursor.fetchone())[0]

            await self._db.execute("""
                INSERT INTO music_playlist_tracks (playlist_id, track_index, title, url, duration, artist, thumbnail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (playlist_id, next_idx, track.title, track.url, track.duration, track.artist, track.thumbnail))
            await self._db.commit()
            return True

    async def remove_playlist_track(self, playlist_id: int, position: int) -> bool:
        """Remove track by position (1-indexed)."""
        async with self._lock:
            async with self._db.execute(
                "SELECT id FROM music_playlist_tracks WHERE playlist_id = ? ORDER BY track_index ASC LIMIT 1 OFFSET ?",
                (playlist_id, position - 1),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return False
                target_id = row[0]

            await self._db.execute("DELETE FROM music_playlist_tracks WHERE id = ?", (target_id,))
            await self._db.commit()
            return True

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

    async def get_latest_heartbeat(self) -> Optional[MusicHeartbeat]:
        """Read the latest heartbeat record across all bots."""
        async with self._lock:
            async with self._db.execute(
                "SELECT * FROM music_heartbeats ORDER BY last_heartbeat DESC LIMIT 1"
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
    # HISTORY & REAL STATS
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

    async def get_history(self, guild_id: int, limit: int = 15) -> List[Dict[str, Any]]:
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

    async def get_guild_stats(self, guild_id: int) -> Dict[str, Any]:
        """Fetch truthful aggregate statistics from playback history."""
        async with self._lock:
            # Total tracks played
            async with self._db.execute(
                "SELECT COUNT(*) FROM music_history WHERE guild_id = ?", (guild_id,)
            ) as c:
                total_played = (await c.fetchone())[0]

            # Top 3 most played songs
            async with self._db.execute("""
                SELECT title, COUNT(*) as cnt
                FROM music_history
                WHERE guild_id = ?
                GROUP BY title
                ORDER BY cnt DESC
                LIMIT 3
            """, (guild_id,)) as c:
                top_songs = [f"{r['title']} ({r['cnt']}x)" for r in await c.fetchall()]

            # Top 3 artists
            async with self._db.execute("""
                SELECT artist, COUNT(*) as cnt
                FROM music_history
                WHERE guild_id = ? AND artist IS NOT NULL AND artist != 'Unknown Artist'
                GROUP BY artist
                ORDER BY cnt DESC
                LIMIT 3
            """, (guild_id,)) as c:
                top_artists = [f"{r['artist']} ({r['cnt']}x)" for r in await c.fetchall()]

            return {
                "total_played": total_played,
                "top_songs": top_songs or ["None yet"],
                "top_artists": top_artists or ["None yet"],
            }

    # =========================================================================
    # SESSION PERSISTENCE & AUTO-RESUME (FEATURE 109)
    # =========================================================================

    async def save_session(
        self,
        guild_id: int,
        voice_channel_id: Optional[int],
        text_channel_id: Optional[int],
        state: str,
        volume: int = 80,
        loop_mode: str = "off",
        is_paused: bool = False,
        current_track: Optional[QueuedTrack] = None,
        started_at: Optional[str] = None,
        position_seconds: int = 0,
        queue: Optional[List[Any]] = None,
        history: Optional[List[Any]] = None,
    ) -> None:
        """Persist active session state for seamless recovery across restarts."""
        async with self._lock:
            track_json = json.dumps(current_track.to_dict()) if current_track else None
            queue_json = json.dumps([t.to_dict() if hasattr(t, "to_dict") else dict(t) for t in queue]) if queue else "[]"
            history_json = json.dumps([t.to_dict() if hasattr(t, "to_dict") else dict(t) for t in history]) if history else "[]"
            now_iso = datetime.now(timezone.utc).isoformat()
            await self._db.execute("""
                INSERT INTO music_sessions (
                    guild_id, voice_channel_id, text_channel_id, state, volume,
                    loop_mode, is_paused, current_track_json, position_seconds,
                    queue_json, history_json, started_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    voice_channel_id = excluded.voice_channel_id,
                    text_channel_id = excluded.text_channel_id,
                    state = excluded.state,
                    volume = excluded.volume,
                    loop_mode = excluded.loop_mode,
                    is_paused = excluded.is_paused,
                    current_track_json = excluded.current_track_json,
                    position_seconds = excluded.position_seconds,
                    queue_json = excluded.queue_json,
                    history_json = excluded.history_json,
                    started_at = COALESCE(excluded.started_at, music_sessions.started_at),
                    updated_at = excluded.updated_at
            """, (
                guild_id,
                voice_channel_id,
                text_channel_id,
                state,
                volume,
                loop_mode,
                1 if is_paused else 0,
                track_json,
                position_seconds,
                queue_json,
                history_json,
                started_at or now_iso,
                now_iso,
            ))
            await self._db.commit()

    async def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Retrieve all persisted active music sessions."""
        async with self._lock:
            async with self._db.execute("""
                SELECT * FROM music_sessions
                WHERE state IN ('PLAYING', 'PAUSED') AND current_track_json IS NOT NULL
            """) as cursor:
                rows = await cursor.fetchall()
                results = []
                for r in rows:
                    d = dict(r)
                    if d.get("current_track_json"):
                        try:
                            d["current_track"] = json.loads(d["current_track_json"])
                        except Exception:
                            d["current_track"] = None
                    if d.get("queue_json"):
                        try:
                            d["queue"] = json.loads(d["queue_json"])
                        except Exception:
                            d["queue"] = []
                    else:
                        d["queue"] = []
                    if d.get("history_json"):
                        try:
                            d["history"] = json.loads(d["history_json"])
                        except Exception:
                            d["history"] = []
                    else:
                        d["history"] = []
                    results.append(d)
                return results

    async def delete_session(self, guild_id: int) -> None:
        """Prune session row on complete stop / leave."""
        async with self._lock:
            await self._db.execute("DELETE FROM music_sessions WHERE guild_id = ?", (guild_id,))
            await self._db.commit()

    # =========================================================================
    # ADVANCED RYTHM-STYLE PERSISTENT SESSION MEMORY (PHASE 2 & 9)
    # =========================================================================

    async def save_persistent_session(self, session: PersistentMusicSession) -> None:
        """Upsert a comprehensive persistent music session record with exact queue & position."""
        now_iso = datetime.now(timezone.utc).isoformat()
        current_track_json = json.dumps(session.current_track.to_dict()) if session.current_track else None
        queue_json = json.dumps([t.to_dict() if hasattr(t, "to_dict") else dict(t) for t in session.queue])
        history_json = json.dumps([t.to_dict() if hasattr(t, "to_dict") else dict(t) for t in session.history])

        async with self._lock:
            await self._db.execute("""
                INSERT INTO persistent_music_sessions (
                    guild_id, session_id, session_name, session_status,
                    current_track_json, current_track_title, stable_track_identifier,
                    source_provider, source_url, track_duration, last_known_position,
                    is_paused, queue_json, history_json, loop_mode, shuffle_enabled,
                    volume, voice_channel_id, text_channel_id, created_by_user_id,
                    created_by_user_name, created_at, updated_at, last_checkpoint,
                    expires_at, recovery_attempts, schema_version, is_pinned, recovery_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, session_id) DO UPDATE SET
                    session_name = excluded.session_name,
                    session_status = excluded.session_status,
                    current_track_json = excluded.current_track_json,
                    current_track_title = excluded.current_track_title,
                    stable_track_identifier = excluded.stable_track_identifier,
                    source_provider = excluded.source_provider,
                    source_url = excluded.source_url,
                    track_duration = excluded.track_duration,
                    last_known_position = excluded.last_known_position,
                    is_paused = excluded.is_paused,
                    queue_json = excluded.queue_json,
                    history_json = excluded.history_json,
                    loop_mode = excluded.loop_mode,
                    shuffle_enabled = excluded.shuffle_enabled,
                    volume = excluded.volume,
                    voice_channel_id = excluded.voice_channel_id,
                    text_channel_id = excluded.text_channel_id,
                    updated_at = excluded.updated_at,
                    last_checkpoint = excluded.last_checkpoint,
                    expires_at = excluded.expires_at,
                    recovery_attempts = excluded.recovery_attempts,
                    is_pinned = excluded.is_pinned,
                    recovery_mode = excluded.recovery_mode
            """, (
                session.guild_id,
                session.session_id,
                session.session_name,
                session.session_status,
                current_track_json,
                session.current_track_title,
                session.stable_track_identifier,
                session.source_provider,
                session.source_url,
                session.track_duration,
                session.last_known_position,
                1 if session.is_paused else 0,
                queue_json,
                history_json,
                session.loop_mode,
                1 if session.shuffle_enabled else 0,
                session.volume,
                session.voice_channel_id,
                session.text_channel_id,
                session.created_by_user_id,
                session.created_by_user_name,
                session.created_at,
                now_iso,
                now_iso,
                session.expires_at,
                session.recovery_attempts,
                session.schema_version,
                1 if session.is_pinned else 0,
                session.recovery_mode,
            ))
            await self._db.commit()

    async def get_persistent_session(self, guild_id: int, session_id: Optional[str] = None) -> Optional[PersistentMusicSession]:
        """Fetch a specific session by ID or the latest active session for the guild."""
        async with self._lock:
            if session_id:
                query = "SELECT * FROM persistent_music_sessions WHERE guild_id = ? AND session_id = ? LIMIT 1"
                params = (guild_id, session_id)
            else:
                query = """
                    SELECT * FROM persistent_music_sessions
                    WHERE guild_id = ? AND session_status NOT IN ('EXPIRED', 'TERMINATED')
                    ORDER BY updated_at DESC LIMIT 1
                """
                params = (guild_id,)

            async with self._db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return self._row_to_persistent_session(dict(row))

    async def get_persistent_session_by_name(self, guild_id: int, name: str) -> Optional[PersistentMusicSession]:
        """Fetch a persistent session by custom name."""
        async with self._lock:
            query = """
                SELECT * FROM persistent_music_sessions
                WHERE guild_id = ? AND LOWER(session_name) = LOWER(?)
                ORDER BY updated_at DESC LIMIT 1
            """
            async with self._db.execute(query, (guild_id, name.strip())) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return self._row_to_persistent_session(dict(row))

    async def list_persistent_sessions(self, guild_id: int, limit: int = 25) -> List[PersistentMusicSession]:
        """List all saved/active sessions for a guild in reverse chronological order."""
        async with self._lock:
            query = """
                SELECT * FROM persistent_music_sessions
                WHERE guild_id = ? AND session_status NOT IN ('TERMINATED')
                ORDER BY is_pinned DESC, updated_at DESC LIMIT ?
            """
            async with self._db.execute(query, (guild_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_persistent_session(dict(r)) for r in rows]

    async def delete_persistent_session(self, guild_id: int, session_id: str) -> bool:
        """Mark or delete a persistent session record."""
        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM persistent_music_sessions WHERE guild_id = ? AND session_id = ?",
                (guild_id, session_id),
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def update_persistent_checkpoint(
        self,
        guild_id: int,
        session_id: str,
        last_known_position: int,
        is_paused: bool,
        status: str = "ACTIVE",
    ) -> None:
        """Efficiently update playback position and pause status without full serialization."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            await self._db.execute("""
                UPDATE persistent_music_sessions
                SET last_known_position = ?,
                    is_paused = ?,
                    session_status = ?,
                    last_checkpoint = ?,
                    updated_at = ?
                WHERE guild_id = ? AND session_id = ?
            """, (last_known_position, 1 if is_paused else 0, status, now_iso, now_iso, guild_id, session_id))
            await self._db.commit()

    async def get_all_eligible_auto_resume_sessions(self) -> List[PersistentMusicSession]:
        """Fetch all sessions eligible for automatic startup recovery."""
        async with self._lock:
            query = """
                SELECT s.* FROM persistent_music_sessions s
                JOIN music_guild_settings g ON s.guild_id = g.guild_id
                WHERE s.session_status IN ('ACTIVE', 'SAVED', 'PAUSED')
                  AND (g.recovery_mode = 'AUTO_RESUME' OR s.recovery_mode = 'AUTO_RESUME')
                  AND s.recovery_attempts < 3
                ORDER BY s.updated_at DESC
            """
            async with self._db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_persistent_session(dict(r)) for r in rows]

    async def cleanup_expired_persistent_sessions(self) -> int:
        """Purge sessions that have exceeded their retention expiration and are not pinned."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            cursor = await self._db.execute("""
                DELETE FROM persistent_music_sessions
                WHERE is_pinned = 0
                  AND expires_at < ?
                  AND session_status NOT IN ('ACTIVE', 'PLAYING')
            """, (now_iso,))
            await self._db.commit()
            return cursor.rowcount

    async def record_history(
        self,
        guild_id: int,
        title: str,
        url: str,
        artist: Optional[str] = None,
        requester_id: Optional[int] = None,
    ) -> None:
        """Record track playback event into music_history."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            await self._db.execute("""
                INSERT INTO music_history (guild_id, title, url, artist, requester_id, played_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (guild_id, title, url, artist or "Unknown Artist", requester_id, now_iso))
            await self._db.commit()

    async def get_guild_wrapped_stats(self, guild_id: int, days: int = 30) -> Dict[str, Any]:
        """Aggregate listening statistics for Server Music Wrapped."""
        async with self._lock:
            # Total tracks played
            async with self._db.execute(
                "SELECT COUNT(*) FROM music_history WHERE guild_id = ?", (guild_id,)
            ) as cur:
                total_tracks = (await cur.fetchone())[0]

            # Top tracks
            async with self._db.execute("""
                SELECT title, artist, COUNT(*) as play_count
                FROM music_history
                WHERE guild_id = ?
                GROUP BY title, artist
                ORDER BY play_count DESC
                LIMIT 5
            """, (guild_id,)) as cur:
                top_tracks = [dict(r) for r in await cur.fetchall()]

            # Top artists
            async with self._db.execute("""
                SELECT artist, COUNT(*) as play_count
                FROM music_history
                WHERE guild_id = ? AND artist != 'Unknown Artist'
                GROUP BY artist
                ORDER BY play_count DESC
                LIMIT 5
            """, (guild_id,)) as cur:
                top_artists = [dict(r) for r in await cur.fetchall()]

            # Top requesters
            async with self._db.execute("""
                SELECT requester_id, COUNT(*) as request_count
                FROM music_history
                WHERE guild_id = ? AND requester_id IS NOT NULL AND requester_id != 0
                GROUP BY requester_id
                ORDER BY request_count DESC
                LIMIT 5
            """, (guild_id,)) as cur:
                top_requesters = [dict(r) for r in await cur.fetchall()]

            return {
                "total_plays": total_tracks,
                "top_tracks": top_tracks,
                "top_artists": top_artists,
                "top_requesters": top_requesters,
            }


    async def get_user_favorites(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve user's favorite tracks ordered by most recently added."""
        async with self._lock:
            async with self._db.execute("""
                SELECT id, title, url, duration, artist, thumbnail, created_at
                FROM music_favorites
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (user_id, limit)) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    def _row_to_persistent_session(self, row: Dict[str, Any]) -> PersistentMusicSession:
        """Helper to deserialize database row into a structured PersistentMusicSession."""
        if row.get("current_track_json"):
            try:
                row["current_track"] = json.loads(row["current_track_json"])
            except Exception:
                row["current_track"] = None
        else:
            row["current_track"] = None

        if row.get("queue_json"):
            try:
                row["queue"] = json.loads(row["queue_json"])
            except Exception:
                row["queue"] = []
        else:
            row["queue"] = []

        if row.get("history_json"):
            try:
                row["history"] = json.loads(row["history_json"])
            except Exception:
                row["history"] = []
        else:
            row["history"] = []

        return PersistentMusicSession.from_dict(row)

    async def submit_web_action(
        self,
        guild_id: int,
        action: str,
        payload: Dict[str, Any],
        user_id: int,
    ) -> int:
        """Submit a user control action from the web platform for asynchronous bot execution."""
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            async with self._db.execute("""
                INSERT INTO music_web_actions (guild_id, action, payload_json, user_id, status, created_at)
                VALUES (?, ?, ?, ?, 'PENDING', ?)
            """, (guild_id, action.upper(), json.dumps(payload), user_id, now)) as cur:
                await self._db.commit()
                return cur.lastrowid

    async def fetch_pending_web_actions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch pending actions submitted from the web dashboard."""
        async with self._lock:
            async with self._db.execute("""
                SELECT id, guild_id, action, payload_json, user_id, status, created_at
                FROM music_web_actions
                WHERE status = 'PENDING'
                ORDER BY id ASC
                LIMIT ?
            """, (limit,)) as cur:
                rows = await cur.fetchall()
                results = []
                for r in rows:
                    d = dict(r)
                    try:
                        d["payload"] = json.loads(d["payload_json"])
                    except Exception:
                        d["payload"] = {}
                    results.append(d)
                return results

    async def mark_web_action_completed(self, action_id: int, result: Optional[Dict[str, Any]] = None) -> None:
        """Mark a web action as successfully processed."""
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            res_json = json.dumps(result or {"status": "ok"})
            await self._db.execute("""
                UPDATE music_web_actions
                SET status = 'PROCESSED', result_json = ?, processed_at = ?
                WHERE id = ?
            """, (res_json, now, action_id))
            await self._db.commit()

    async def mark_web_action_failed(self, action_id: int, error: str) -> None:
        """Mark a web action as failed with error details."""
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            res_json = json.dumps({"error": error})
            await self._db.execute("""
                UPDATE music_web_actions
                SET status = 'FAILED', result_json = ?, processed_at = ?
                WHERE id = ?
            """, (res_json, now, action_id))
            await self._db.commit()

    async def get_recent_history(self, guild_id: int, limit: int = 25) -> List[Dict[str, Any]]:
        """Fetch recent playback history for a guild."""
        async with self._lock:
            async with self._db.execute("""
                SELECT id, title, url, artist, requester_id, played_at
                FROM music_history
                WHERE guild_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (guild_id, limit)) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def is_premium(self, guild_id: int = 0, user_id: Optional[int] = None) -> bool:
        """Check if either the guild or the user has an active premium subscription."""
        async with self._lock:
            if not self._db:
                return False

            # 1. Check verified user subscription in payment system
            if user_id:
                now_iso = datetime.now(timezone.utc).isoformat()
                try:
                    async with self._db.execute(
                        """
                        SELECT 1 FROM music_user_subscriptions
                        WHERE user_id = ?
                          AND status = 'active'
                          AND (current_period_end IS NULL OR current_period_end >= ?)
                        LIMIT 1
                        """,
                        (user_id, now_iso),
                    ) as sub_cursor:
                        if await sub_cursor.fetchone():
                            return True
                except Exception:
                    pass

            # 2. Check direct guild/user license in music_premium
            query_ids = [guild_id]
            if user_id:
                query_ids.append(user_id)
            placeholders = ",".join("?" for _ in query_ids)
            async with self._db.execute(
                f"SELECT 1 FROM music_premium WHERE entity_id IN ({placeholders}) AND is_premium = 1 LIMIT 1",
                query_ids,
            ) as cursor:
                row = await cursor.fetchone()
                return row is not None

    async def get_premium_info(self, entity_id: int) -> Optional[Dict[str, Any]]:
        """Get premium record for a guild or user."""
        async with self._lock:
            if not self._db:
                return None
            async with self._db.execute(
                "SELECT * FROM music_premium WHERE entity_id = ?",
                (entity_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def set_premium(
        self,
        entity_id: int,
        entity_type: str = "guild",
        is_premium: bool = True,
        tier: str = "premium",
        activated_by: Optional[int] = None,
    ) -> None:
        """Set or revoke premium tier for a guild or user."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            if not self._db:
                return
            await self._db.execute("""
                INSERT INTO music_premium (entity_id, entity_type, is_premium, tier, activated_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    entity_type = excluded.entity_type,
                    is_premium = excluded.is_premium,
                    tier = excluded.tier,
                    activated_by = excluded.activated_by,
                    created_at = excluded.created_at
            """, (entity_id, entity_type, 1 if is_premium else 0, tier, activated_by, now))
            await self._db.commit()

    async def list_premiums(self) -> List[Dict[str, Any]]:
        """List all entities with active premium."""
        async with self._lock:
            if not self._db:
                return []
            async with self._db.execute(
                "SELECT * FROM music_premium WHERE is_premium = 1 ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    # ==========================================
    # WEB SESSIONS & AUTHENTICATION
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
        """Create or update a web authenticated session."""
        if not self._db:
            await self.connect()
        if not self._db:
            return

        now = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(user_data_dict or {})
        async with self._lock:
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
        """Retrieve web session by session ID."""
        if not self._db:
            await self.connect()
        if not self._db:
            return None

        async with self._db.execute("SELECT * FROM web_sessions WHERE session_id = ?", (session_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            columns = [c[0] for c in cur.description]
            res = dict(zip(columns, row))
            try:
                res["user_data"] = json.loads(res.get("user_data_json", "{}"))
            except Exception:
                res["user_data"] = {}
            return res

    async def delete_web_session(self, session_id: str) -> bool:
        """Remove a web session upon logout or invalidation."""
        if not self._db:
            await self.connect()
        if not self._db:
            return False

        async with self._lock:
            cur = await self._db.execute("DELETE FROM web_sessions WHERE session_id = ?", (session_id,))
            await self._db.commit()
            return (cur.rowcount or 0) > 0

    # =========================================================================
    # PREMIUM USER SUBSCRIPTIONS & PAYMENT WEBHOOKS
    # =========================================================================

    async def get_user_subscription(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve the verified subscription record for a Discord user."""
        if not self._db:
            await self.connect()
        if not self._db:
            return None

        async with self._db.execute(
            "SELECT * FROM music_user_subscriptions WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            columns = [c[0] for c in cur.description]
            return dict(zip(columns, row))

    async def upsert_user_subscription(
        self,
        user_id: int,
        plan: str,
        status: str,
        provider: str = "stripe",
        provider_customer_id: Optional[str] = None,
        provider_subscription_id: Optional[str] = None,
        payment_reference: Optional[str] = None,
        currency: str = "usd",
        amount: int = 0,
        current_period_start: Optional[str] = None,
        current_period_end: Optional[str] = None,
        cancel_at_period_end: bool = False,
        canceled_at: Optional[str] = None,
        **kwargs: Any,
    ) -> bool:
        """Create or update a user subscription record within an immediate transaction."""
        if not self._db:
            await self.connect()
        if not self._db:
            return False

        # Support aliases
        provider_customer_id = provider_customer_id or kwargs.get("customer_id")
        provider_subscription_id = provider_subscription_id or kwargs.get("subscription_id")
        payment_reference = payment_reference or kwargs.get("payment_ref")
        current_period_start = current_period_start or kwargs.get("start_date")
        current_period_end = current_period_end or kwargs.get("renewal_date")

        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO music_user_subscriptions (
                    user_id, plan, status, provider, provider_customer_id,
                    provider_subscription_id, payment_reference, currency, amount,
                    current_period_start, current_period_end, cancel_at_period_end,
                    canceled_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    plan = excluded.plan,
                    status = excluded.status,
                    provider = excluded.provider,
                    provider_customer_id = COALESCE(excluded.provider_customer_id, music_user_subscriptions.provider_customer_id),
                    provider_subscription_id = COALESCE(excluded.provider_subscription_id, music_user_subscriptions.provider_subscription_id),
                    payment_reference = COALESCE(excluded.payment_reference, music_user_subscriptions.payment_reference),
                    currency = excluded.currency,
                    amount = excluded.amount,
                    current_period_start = COALESCE(excluded.current_period_start, music_user_subscriptions.current_period_start),
                    current_period_end = COALESCE(excluded.current_period_end, music_user_subscriptions.current_period_end),
                    cancel_at_period_end = excluded.cancel_at_period_end,
                    canceled_at = excluded.canceled_at,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    plan,
                    status,
                    provider,
                    provider_customer_id,
                    provider_subscription_id,
                    payment_reference,
                    currency,
                    amount,
                    current_period_start or now,
                    current_period_end,
                    1 if cancel_at_period_end else 0,
                    canceled_at,
                    now,
                    now,
                ),
            )
            await self._db.commit()

        await self.record_subscription_audit(
            user_id=user_id,
            action="subscription_upserted",
            details={"plan": plan, "status": status, "provider": provider},
        )
        return True

    async def cancel_user_subscription(
        self,
        user_id: int,
        cancel_at_period_end: bool = True,
        reason: Optional[str] = None,
    ) -> bool:
        """Cancel subscription renewal or mark canceled."""
        if not self._db:
            await self.connect()
        if not self._db:
            return False

        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            if cancel_at_period_end:
                cur = await self._db.execute(
                    """
                    UPDATE music_user_subscriptions
                    SET cancel_at_period_end = 1, canceled_at = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (now, now, user_id),
                )
            else:
                cur = await self._db.execute(
                    """
                    UPDATE music_user_subscriptions
                    SET status = 'canceled', cancel_at_period_end = 1, canceled_at = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (now, now, user_id),
                )
            await self._db.commit()
            affected = (cur.rowcount or 0) > 0

        if affected:
            await self.record_subscription_audit(
                user_id=user_id,
                action="subscription_cancelled",
                details={"reason": reason or "user_cancelled", "cancel_at_period_end": cancel_at_period_end},
            )
        return affected

    async def is_webhook_event_processed(self, event_id: str) -> bool:
        """Idempotency check: returns True if webhook event has already been handled."""
        if not self._db:
            await self.connect()
        if not self._db:
            return False

        async with self._db.execute(
            "SELECT 1 FROM payment_webhook_events WHERE event_id = ? LIMIT 1",
            (event_id,),
        ) as cur:
            row = await cur.fetchone()
            return row is not None

    async def record_webhook_event(
        self,
        event_id: str,
        provider: str,
        event_type: str,
        payload_json: Optional[str] = None,
        status: str = "processed",
        **kwargs: Any,
    ) -> bool:
        """Record processed webhook event for idempotency guarantees."""
        if not self._db:
            await self.connect()
        if not self._db:
            return False

        final_payload = payload_json or kwargs.get("payload") or "{}"
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO payment_webhook_events (event_id, provider, event_type, payload_json, status, processed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    status = excluded.status,
                    processed_at = excluded.processed_at
                """,
                (event_id, provider, event_type, payload_json, status, now),
            )
            await self._db.commit()
            return True

    async def record_subscription_audit(
        self,
        user_id: int,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> bool:
        """Write immutable audit trail for all subscription status changes."""
        if not self._db:
            await self.connect()
        if not self._db:
            return False

        now = datetime.now(timezone.utc).isoformat()
        details_str = json.dumps(details or {})
        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO subscription_audit_logs (user_id, action, details_json, ip_address, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, action, details_str, ip_address, now),
            )
            await self._db.commit()
            return True

    async def get_subscription_audit_logs(
        self,
        user_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve recent audit events for subscriptions."""
        if not self._db:
            await self.connect()
        if not self._db:
            return []

        query = "SELECT * FROM subscription_audit_logs"
        params: List[Any] = []
        if user_id:
            query += " WHERE user_id = ?"
            params.append(user_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        async with self._db.execute(query, tuple(params)) as cur:
            rows = await cur.fetchall()
            columns = [c[0] for c in cur.description]
            result = []
            for r in rows:
                item = dict(zip(columns, r))
                try:
                    item["details"] = json.loads(item.get("details_json", "{}"))
                except Exception:
                    item["details"] = {}
                result.append(item)
            return result





