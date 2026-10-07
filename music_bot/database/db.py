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
import aiosqlite

from music_bot.config import MUSIC_DATABASE_PATH
from music_bot.database.models import (
    MusicDJSettings,
    MusicFavorite,
    MusicGuildSettings,
    MusicHeartbeat,
    MusicPlaylist,
    QueuedTrack,
)

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
                    quiet_mode INTEGER DEFAULT 0,
                    response_style TEXT DEFAULT 'normal',
                    vote_skip_threshold REAL DEFAULT 0.5,
                    dj_mode_enabled INTEGER DEFAULT 0,
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
            """)
            await self._db.commit()

            # Ensure additional columns exist on older installations
            for col, col_type, default_val in [
                ("quiet_mode", "INTEGER", "0"),
                ("response_style", "TEXT", "'normal'"),
                ("vote_skip_threshold", "REAL", "0.5"),
                ("dj_mode_enabled", "INTEGER", "0"),
            ]:
                try:
                    await self._db.execute(
                        f"ALTER TABLE music_guild_settings ADD COLUMN {col} {col_type} DEFAULT {default_val}"
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
                    quiet_mode=bool(row["quiet_mode"]) if "quiet_mode" in row.keys() else False,
                    response_style=row["response_style"] if "response_style" in row.keys() else "normal",
                    vote_skip_threshold=float(row["vote_skip_threshold"]) if "vote_skip_threshold" in row.keys() else 0.5,
                    dj_mode_enabled=bool(row["dj_mode_enabled"]) if "dj_mode_enabled" in row.keys() else False,
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
                    response_style, vote_skip_threshold, dj_mode_enabled, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                now,
            ))
            await self._db.commit()

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

    async def add_favorite(self, user_id: int, track: QueuedTrack) -> bool:
        """Add a track to user's favorites list."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            try:
                await self._db.execute("""
                    INSERT INTO music_favorites (user_id, title, url, duration, artist, thumbnail, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, track.title, track.url, track.duration, track.artist, track.thumbnail, now))
                await self._db.commit()
                return True
            except aiosqlite.IntegrityError:
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
