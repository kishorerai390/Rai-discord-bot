"""
RAI Music Search Service.
Coordinates multi-provider query classification, candidate search, URL routing, and fallback.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import discord

from music.provider import (
    MusicErrorCode,
    MusicProvider,
    QueryType,
    TrackCandidate,
)
from music.providers.direct import DirectAudioProvider
from music.providers.soundcloud import SoundCloudMusicProvider
from music.providers.youtube import YouTubeMusicProvider

logger = logging.getLogger("Rai.MusicSearchService")


class MusicSearchService:
    """Manages music search providers, query parsing, and fallback ranking."""

    _instance: Optional["MusicSearchService"] = None

    def __init__(self, providers: Optional[List[MusicProvider]] = None):
        self.providers: List[MusicProvider] = providers or [
            DirectAudioProvider(),
            YouTubeMusicProvider(),
            SoundCloudMusicProvider(),
        ]
        self._youtube_provider = next((p for p in self.providers if isinstance(p, YouTubeMusicProvider)), YouTubeMusicProvider())
        self._sc_provider = next((p for p in self.providers if isinstance(p, SoundCloudMusicProvider)), SoundCloudMusicProvider())

    @classmethod
    def get_instance(cls) -> "MusicSearchService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def classify_query(cls, raw_query: str) -> Tuple[QueryType, str]:
        """Classifies input into Direct URL or text Search query."""
        clean = raw_query.strip()
        parsed = urlparse(clean)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return QueryType.DIRECT_URL, clean
        return QueryType.SEARCH, clean

    def get_supported_provider(self, query: str, query_type: QueryType) -> Optional[MusicProvider]:
        """Finds the best provider supporting this query or URL."""
        for provider in self.providers:
            if provider.supports(query, query_type):
                return provider
        return None

    async def search_candidates(
        self,
        query: str,
        limit: int = 5,
        requester: Optional[discord.Member] = None,
        max_retries: int = 2,
    ) -> List[TrackCandidate]:
        """
        Retrieves search candidates from the primary provider with automatic fallback.
        """
        query_type, clean_query = self.classify_query(query)

        # Direct URL routing: return single candidate if supported
        if query_type == QueryType.DIRECT_URL:
            provider = self.get_supported_provider(clean_query, query_type)
            if not provider:
                return []
            candidate = await provider.get_metadata(clean_query, requester=requester)
            return [candidate] if candidate else []

        # Plain search query: Try YouTube first
        primary_provider = self._youtube_provider
        fallback_provider = self._sc_provider

        candidates: List[TrackCandidate] = []
        try:
            candidates = await primary_provider.search(clean_query, limit=limit, requester=requester)
        except Exception as exc:
            logger.warning(f"Primary search failed on {primary_provider.name} for '{clean_query}': {exc}")

        # If primary failed or returned nothing, fallback to SoundCloud
        if not candidates and fallback_provider:
            logger.info(f"Triggering fallback search on {fallback_provider.name} for '{clean_query}'")
            try:
                candidates = await fallback_provider.search(clean_query, limit=limit, requester=requester)
            except Exception as exc:
                logger.error(f"Fallback search failed on {fallback_provider.name} for '{clean_query}': {exc}")

        return candidates
