"""
Independent Data Models for Rai Music Bot.
All models are strictly scoped by guild_id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class MusicGuildSettings:
    guild_id: int
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
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class QueuedTrack:
    title: str
    url: str
    stream_url: str
    duration: int
    requester_id: int
    requester_name: str
    artist: str = "Unknown Artist"
    thumbnail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "stream_url": self.stream_url,
            "duration": self.duration,
            "requester_id": self.requester_id,
            "requester_name": self.requester_name,
            "artist": self.artist,
            "thumbnail": self.thumbnail,
        }

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
        )


@dataclass
class MusicFavorite:
    id: int
    user_id: int
    title: str
    url: str
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

