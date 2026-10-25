"""
Independent Data Models for Rai Music Bot.
All models are strictly scoped by guild_id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


@dataclass
class MusicGuildSettings:
    guild_id: int
    prefix: str = ","
    request_channel_id: Optional[int] = None
    dj_role_id: Optional[int] = None
    default_volume: int = 80
    autoplay_enabled: bool = False
    auto_leave_enabled: bool = True
    auto_leave_timeout: int = 300
    natural_requests_enabled: bool = True
    allowed_channels: List[int] = field(default_factory=list)
    allowed_voice_channels: List[int] = field(default_factory=list)
    queue_limit: int = 200
    quiet_mode: bool = False
    response_style: str = "normal"  # normal, minimal, cute
    vote_skip_threshold: float = 0.5  # 50% of listeners must vote
    dj_mode_enabled: bool = False
    twenty_four_seven_enabled: bool = False
    twenty_four_seven_channel_id: Optional[int] = None
    recovery_mode: str = "MANUAL"  # MANUAL, AUTO_RESUME, QUEUE_ONLY
    session_retention_days: int = 7
    checkpoint_interval: int = 10
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class QueuedTrack:
    title: str
    url: str
    duration: int = 0
    requester_id: int = 0
    requester_name: str = "Unknown"
    stream_url: str = ""
    artist: str = "Unknown Artist"
    thumbnail: Optional[str] = None
    http_headers: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "title": self.title,
            "url": self.url,
            "stream_url": self.stream_url,
            "duration": self.duration,
            "requester_id": self.requester_id,
            "requester_name": self.requester_name,
            "artist": self.artist,
            "thumbnail": self.thumbnail,
        }
        if self.http_headers:
            d["http_headers"] = self.http_headers
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> QueuedTrack:
        return cls(
            title=data.get("title", "Unknown"),
            url=data.get("url", ""),
            stream_url=data.get("stream_url", ""),
            duration=data.get("duration", 0),
            requester_id=data.get("requester_id", 0),
            requester_name=data.get("requester_name", "Unknown"),
            artist=data.get("artist", "Unknown Artist"),
            thumbnail=data.get("thumbnail"),
            http_headers=data.get("http_headers"),
        )


@dataclass
class MusicFavorite:
    user_id: int
    title: str
    url: str
    id: Optional[int] = None
    duration: int = 0
    artist: str = "Unknown Artist"
    thumbnail: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())



@dataclass
class MusicDJSettings:
    guild_id: int
    enabled: bool = False
    auto_queue: bool = True
    recommendation_mode: str = "similar"  # similar, discover, mood, genre
    preferred_genres: List[str] = field(default_factory=list)
    explicit_allowed: bool = True
    repeat_avoidance_count: int = 15
    max_queue_size: int = 50
    recommendation_cooldown: int = 15
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class MusicPlaylist:
    id: int
    guild_id: int
    user_id: int
    name: str
    is_server: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tracks: List[QueuedTrack] = field(default_factory=list)


@dataclass
class MusicHeartbeat:
    bot_id: int
    version: str
    status: str
    active_sessions: int
    playing_count: int
    last_heartbeat: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PersistentMusicSession:
    guild_id: int
    session_id: str
    session_name: str = "Default Session"
    session_status: str = "SAVED"  # ACTIVE, SAVED, PAUSED, RESTORED, EXPIRED, TERMINATED
    current_track: Optional[QueuedTrack] = None
    current_track_title: str = ""
    stable_track_identifier: str = ""
    source_provider: str = "youtube"
    source_url: str = ""
    track_duration: int = 0
    last_known_position: int = 0
    is_paused: bool = False
    queue: List[QueuedTrack] = field(default_factory=list)
    history: List[QueuedTrack] = field(default_factory=list)
    loop_mode: str = "off"
    shuffle_enabled: bool = False
    volume: int = 80
    voice_channel_id: Optional[int] = None
    text_channel_id: Optional[int] = None
    created_by_user_id: Optional[int] = None
    created_by_user_name: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_checkpoint: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(days=7)).isoformat())
    recovery_attempts: int = 0
    schema_version: int = 1
    is_pinned: bool = False
    recovery_mode: str = "MANUAL"  # MANUAL, AUTO_RESUME, QUEUE_ONLY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "guild_id": self.guild_id,
            "session_id": self.session_id,
            "session_name": self.session_name,
            "session_status": self.session_status,
            "current_track": self.current_track.to_dict() if self.current_track else None,
            "current_track_title": self.current_track_title,
            "stable_track_identifier": self.stable_track_identifier,
            "source_provider": self.source_provider,
            "source_url": self.source_url,
            "track_duration": self.track_duration,
            "last_known_position": self.last_known_position,
            "is_paused": self.is_paused,
            "queue": [t.to_dict() if hasattr(t, "to_dict") else dict(t) for t in self.queue],
            "history": [t.to_dict() if hasattr(t, "to_dict") else dict(t) for t in self.history],
            "loop_mode": self.loop_mode,
            "shuffle_enabled": self.shuffle_enabled,
            "volume": self.volume,
            "voice_channel_id": self.voice_channel_id,
            "text_channel_id": self.text_channel_id,
            "created_by_user_id": self.created_by_user_id,
            "created_by_user_name": self.created_by_user_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_checkpoint": self.last_checkpoint,
            "expires_at": self.expires_at,
            "recovery_attempts": self.recovery_attempts,
            "schema_version": self.schema_version,
            "is_pinned": self.is_pinned,
            "recovery_mode": self.recovery_mode,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PersistentMusicSession:
        current_track_raw = data.get("current_track")
        current_track = QueuedTrack.from_dict(current_track_raw) if current_track_raw else None
        queue_raw = data.get("queue") or []
        queue = [QueuedTrack.from_dict(t) if isinstance(t, dict) else t for t in queue_raw]
        history_raw = data.get("history") or []
        history = [QueuedTrack.from_dict(t) if isinstance(t, dict) else t for t in history_raw]

        return cls(
            guild_id=int(data["guild_id"]),
            session_id=str(data["session_id"]),
            session_name=data.get("session_name", "Default Session"),
            session_status=data.get("session_status", "SAVED"),
            current_track=current_track,
            current_track_title=data.get("current_track_title") or (current_track.title if current_track else ""),
            stable_track_identifier=data.get("stable_track_identifier") or (current_track.url if current_track else ""),
            source_provider=data.get("source_provider", "youtube"),
            source_url=data.get("source_url") or (current_track.url if current_track else ""),
            track_duration=int(data.get("track_duration") or (current_track.duration if current_track else 0)),
            last_known_position=int(data.get("last_known_position", 0)),
            is_paused=bool(data.get("is_paused", False)),
            queue=queue,
            history=history,
            loop_mode=data.get("loop_mode", "off"),
            shuffle_enabled=bool(data.get("shuffle_enabled", False)),
            volume=int(data.get("volume", 80)),
            voice_channel_id=data.get("voice_channel_id"),
            text_channel_id=data.get("text_channel_id"),
            created_by_user_id=data.get("created_by_user_id"),
            created_by_user_name=data.get("created_by_user_name"),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
            last_checkpoint=data.get("last_checkpoint") or datetime.now(timezone.utc).isoformat(),
            expires_at=data.get("expires_at") or (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            recovery_attempts=int(data.get("recovery_attempts", 0)),
            schema_version=int(data.get("schema_version", 1)),
            is_pinned=bool(data.get("is_pinned", False)),
            recovery_mode=data.get("recovery_mode", "MANUAL"),
        )


