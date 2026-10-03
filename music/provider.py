"""
RAI Music Provider Abstraction and Diagnostic Subsystem.
Defines interfaces, data models, error taxonomy, and diagnostic reporting
for music search, metadata resolution, and audio stream extraction.
"""

from __future__ import annotations

import abc
import dataclasses
import enum
import logging
import random
import string
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import discord

logger = logging.getLogger("Rai.MusicProvider")


def generate_music_diagnostic_id() -> str:
    """Generates unique diagnostic reference (e.g. RAI-MUSIC-7F21A9)."""
    chars = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"RAI-MUSIC-{chars}"


class QueryType(enum.Enum):
    SEARCH = "SEARCH"
    DIRECT_URL = "DIRECT_URL"
    UNKNOWN = "UNKNOWN"


class MusicErrorCode(enum.Enum):
    SUCCESS = "SUCCESS"
    SEARCH_FAILED = "SEARCH_FAILED"
    NO_RESULTS = "NO_RESULTS"
    METADATA_FAILED = "METADATA_FAILED"
    SOURCE_RESOLUTION_FAILED = "SOURCE_RESOLUTION_FAILED"
    UNSUPPORTED_URL = "UNSUPPORTED_URL"
    PROVIDER_BLOCKED = "PROVIDER_BLOCKED"
    NETWORK_ERROR = "NETWORK_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    VOICE_CONNECTION_FAILED = "VOICE_CONNECTION_FAILED"
    AUDIO_START_FAILED = "AUDIO_START_FAILED"


class ProviderHealthState(enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


@dataclasses.dataclass
class TrackCandidate:
    """Candidate track metadata returned by search or URL parser."""
    title: str
    url: str
    duration: int
    artist: str = "Unknown Artist"
    thumbnail: Optional[str] = None
    provider_name: str = "Unknown"
    extractor_id: Optional[str] = None
    requester: Optional[discord.Member] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "duration": self.duration,
            "artist": self.artist,
            "thumbnail": self.thumbnail,
            "provider_name": self.provider_name,
            "extractor_id": self.extractor_id,
            "requester_id": self.requester.id if self.requester else 0,
            "requester_name": getattr(self.requester, "display_name", "Unknown") if self.requester else "Unknown",
        }


@dataclasses.dataclass
class ResolvedTrack:
    """Fully resolved track with validated playable stream URL."""
    candidate: TrackCandidate
    stream_url: str
    is_playable: bool = True
    expiry: Optional[float] = None
    resolved_at: float = dataclasses.field(default_factory=time.time)

    @property
    def title(self) -> str:
        return self.candidate.title

    @property
    def url(self) -> str:
        return self.candidate.url

    @property
    def duration(self) -> int:
        return self.candidate.duration

    @property
    def artist(self) -> str:
        return self.candidate.artist

    @property
    def thumbnail(self) -> Optional[str]:
        return self.candidate.thumbnail

    @property
    def requester(self) -> Optional[discord.Member]:
        return self.candidate.requester

    def to_dict(self) -> Dict[str, Any]:
        d = self.candidate.to_dict()
        d["stream_url"] = self.stream_url
        d["is_playable"] = self.is_playable
        d["resolved_at"] = self.resolved_at
        return d


@dataclasses.dataclass
class MusicDiagnosticReport:
    """Structured internal diagnostic record for resolution and playback issues."""
    diagnostic_id: str
    music_request_id: str
    guild_id: int
    user_id: int
    voice_channel_id: Optional[int]
    query: str
    query_type: QueryType
    provider: str
    stage: str
    error_code: MusicErrorCode
    error_message: str
    timestamp: float = dataclasses.field(default_factory=time.time)

    def log_and_report(self, bot: Optional[Any] = None) -> None:
        """Logs structured diagnostic and notifies private Rai report system."""
        logger.warning(
            f"[{self.diagnostic_id}] Music Stage '{self.stage}' failed for guild {self.guild_id}: "
            f"Code={self.error_code.value} Provider={self.provider} Msg={self.error_message}"
        )
        if bot and hasattr(bot, "loop"):
            try:
                from utils.owner_reporter import OwnerReporter
                OwnerReporter.send_music_report(
                    bot=bot,
                    guild_id=self.guild_id,
                    event=f"Music Resolution Error ({self.error_code.value})",
                    reason=self.error_message[:200],
                    action_taken="Provided specific diagnostic to user; isolated audio player",
                    severity="WARNING",
                    details={
                        "Diagnostic ID": self.diagnostic_id,
                        "Stage": self.stage,
                        "Provider": self.provider,
                        "Query": self.query[:80],
                        "User ID": str(self.user_id),
                        "Channel ID": str(self.voice_channel_id or 0),
                    },
                )
            except Exception as exc:
                logger.debug(f"Could not forward diagnostic to OwnerReporter: {exc}")


@dataclasses.dataclass
class ResolutionResult:
    """Result of search or resolution pipeline."""
    is_success: bool
    track: Optional[ResolvedTrack] = None
    candidates: List[TrackCandidate] = dataclasses.field(default_factory=list)
    diagnostic: Optional[MusicDiagnosticReport] = None
    error_code: MusicErrorCode = MusicErrorCode.SUCCESS
    user_message: str = ""


class MusicProvider(abc.ABC):
    """Abstract interface for all music search and audio source providers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'YouTube', 'SoundCloud', 'DirectAudio')."""
        pass

    @abc.abstractmethod
    def supports(self, query: str, query_type: QueryType) -> bool:
        """Determines if this provider can handle the query or URL."""
        pass

    @abc.abstractmethod
    async def search(self, query: str, limit: int = 5, requester: Optional[discord.Member] = None) -> List[TrackCandidate]:
        """Performs multi-candidate search."""
        pass

    @abc.abstractmethod
    async def get_metadata(self, url: str, requester: Optional[discord.Member] = None) -> Optional[TrackCandidate]:
        """Fetches lightweight candidate metadata from a URL."""
        pass

    @abc.abstractmethod
    async def resolve(self, candidate_or_url: Union[str, TrackCandidate], requester: Optional[discord.Member] = None) -> Optional[ResolvedTrack]:
        """Resolves candidate or URL into verified playable audio stream."""
        pass

    @abc.abstractmethod
    async def health_check(self) -> Tuple[ProviderHealthState, str]:
        """Performs provider health check returning state and status message."""
        pass
