"""
SoundCloud Music Provider for RAI.
Serves as secondary search engine and direct resolver for soundcloud.com tracks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import discord
import yt_dlp

from music.provider import (
    MusicProvider,
    ProviderHealthState,
    QueryType,
    ResolvedTrack,
    TrackCandidate,
)

logger = logging.getLogger("Rai.SoundCloudProvider")

BASE_SC_OPTIONS: Dict[str, Any] = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "quiet": True,
    "no_warnings": True,
}


class SoundCloudMusicProvider(MusicProvider):
    """SoundCloud search and playback resolver."""

    def __init__(self):
        self._name = "SoundCloud"
        self._search_ytdl = yt_dlp.YoutubeDL({
            **BASE_SC_OPTIONS,
            "extract_flat": "in_playlist",
        })
        self._resolve_ytdl = yt_dlp.YoutubeDL(BASE_SC_OPTIONS)

    @property
    def name(self) -> str:
        return self._name

    def supports(self, query: str, query_type: QueryType) -> bool:
        clean = query.strip()
        parsed = urlparse(clean)
        if "soundcloud.com" in parsed.netloc.lower():
            return True
        # If query explicitly targets soundcloud via prefix
        if clean.lower().startswith("scsearch:"):
            return True
        return False

    async def search(self, query: str, limit: int = 5, requester: Optional[discord.Member] = None) -> List[TrackCandidate]:
        loop = asyncio.get_running_loop()
        clean = query.strip()
        if not clean.lower().startswith("scsearch:"):
            search_query = f"scsearch{limit}:{clean}"
        else:
            search_query = clean

        def _do_search():
            return self._search_ytdl.extract_info(search_query, download=False)

        try:
            data = await asyncio.wait_for(loop.run_in_executor(None, _do_search), timeout=10.0)
        except Exception as exc:
            logger.error(f"SoundCloud search error for query '{query}': {exc}")
            return []

        if not data:
            return []

        entries = data.get("entries") or []
        candidates: List[TrackCandidate] = []
        for entry in entries:
            if not entry:
                continue
            title = entry.get("title") or "Unknown Title"
            webpage_url = entry.get("url") or entry.get("webpage_url") or ""
            duration = int(entry.get("duration") or 0)
            artist = entry.get("uploader") or "SoundCloud Artist"
            thumbnail = entry.get("thumbnail")

            candidates.append(
                TrackCandidate(
                    title=title,
                    url=webpage_url,
                    duration=duration,
                    artist=artist,
                    thumbnail=thumbnail,
                    provider_name=self.name,
                    extractor_id=entry.get("id"),
                    requester=requester,
                )
            )
        return candidates

    async def get_metadata(self, url: str, requester: Optional[discord.Member] = None) -> Optional[TrackCandidate]:
        loop = asyncio.get_running_loop()

        def _do_meta():
            return self._search_ytdl.extract_info(url, download=False)

        try:
            data = await asyncio.wait_for(loop.run_in_executor(None, _do_meta), timeout=10.0)
        except Exception as exc:
            logger.error(f"SoundCloud metadata error for URL '{url}': {exc}")
            return None

        if not data:
            return None

        return TrackCandidate(
            title=data.get("title", "Unknown Title"),
            url=data.get("webpage_url", url),
            duration=int(data.get("duration") or 0),
            artist=data.get("uploader", "SoundCloud Artist"),
            thumbnail=data.get("thumbnail"),
            provider_name=self.name,
            extractor_id=data.get("id"),
            requester=requester,
        )

    async def resolve(self, candidate_or_url: Union[str, TrackCandidate], requester: Optional[discord.Member] = None) -> Optional[ResolvedTrack]:
        loop = asyncio.get_running_loop()
        if isinstance(candidate_or_url, TrackCandidate):
            target_url = candidate_or_url.url
            candidate = candidate_or_url
        else:
            target_url = candidate_or_url
            candidate = None

        def _do_resolve():
            return self._resolve_ytdl.extract_info(target_url, download=False)

        try:
            data = await asyncio.wait_for(loop.run_in_executor(None, _do_resolve), timeout=12.0)
        except Exception as exc:
            logger.error(f"SoundCloud resolution error for '{target_url}': {exc}")
            return None

        if not data:
            return None

        stream_url = data.get("url") or ""
        if not stream_url:
            formats = data.get("formats") or []
            for fmt in reversed(formats):
                if fmt.get("url"):
                    stream_url = fmt["url"]
                    break

        if not stream_url:
            return None

        if not candidate:
            candidate = TrackCandidate(
                title=data.get("title", "Unknown Title"),
                url=data.get("webpage_url", target_url),
                duration=int(data.get("duration") or 0),
                artist=data.get("uploader", "SoundCloud Artist"),
                thumbnail=data.get("thumbnail"),
                provider_name=self.name,
                extractor_id=data.get("id"),
                requester=requester,
            )

        return ResolvedTrack(
            candidate=candidate,
            stream_url=stream_url,
            is_playable=True,
        )

    async def health_check(self) -> Tuple[ProviderHealthState, str]:
        try:
            results = await self.search("lofi", limit=1)
            if results and len(results) > 0:
                return ProviderHealthState.HEALTHY, "SoundCloud search operational"
            return ProviderHealthState.DEGRADED, "SoundCloud returned empty results"
        except Exception as exc:
            return ProviderHealthState.OFFLINE, f"SoundCloud error: {exc}"
