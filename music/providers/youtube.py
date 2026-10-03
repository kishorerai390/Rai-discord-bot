"""
Production YouTube Music Provider for RAI.
Supports iOS/Android player client fallback, URL normalization (watch, youtu.be, shorts),
fast multi-candidate search, and validated audio stream resolution.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qs, urlparse

import discord
import yt_dlp

from music.provider import (
    MusicErrorCode,
    MusicProvider,
    ProviderHealthState,
    QueryType,
    ResolvedTrack,
    TrackCandidate,
)

logger = logging.getLogger("Rai.YouTubeProvider")

# YouTube URL regexes
YOUTUBE_WATCH_REGEX = re.compile(r"^(?:https?://)?(?:www\.|m\.|music\.)?youtube\.com/watch.*", re.IGNORECASE)
YOUTUBE_SHORT_REGEX = re.compile(r"^(?:https?://)?(?:www\.|m\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})", re.IGNORECASE)
YOUTU_BE_REGEX = re.compile(r"^(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]{11})", re.IGNORECASE)
YOUTUBE_EMBED_REGEX = re.compile(r"^(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})", re.IGNORECASE)
VIDEO_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{11}$")

# Production yt-dlp configurations
BASE_YTDL_OPTIONS: Dict[str, Any] = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["ios", "android", "web", "mweb"]
        }
    },
}


class YouTubeMusicProvider(MusicProvider):
    """Production-grade YouTube music resolver with mobile player client fallback."""

    def __init__(self):
        self._name = "YouTube"
        self._search_ytdl = yt_dlp.YoutubeDL({
            **BASE_YTDL_OPTIONS,
            "extract_flat": "in_playlist",
        })
        self._resolve_ytdl = yt_dlp.YoutubeDL(BASE_YTDL_OPTIONS)

    @property
    def name(self) -> str:
        return self._name

    @classmethod
    def normalize_url(cls, raw_url: str) -> Optional[str]:
        """
        Normalizes any valid YouTube URL into canonical watch format.
        Strips tracking query parameters (e.g. ?si=..., &feature=...).
        """
        raw_url = raw_url.strip()
        parsed = urlparse(raw_url)
        video_id: Optional[str] = None

        # Case 1: youtu.be/<id>
        match_short = YOUTU_BE_REGEX.match(raw_url)
        if match_short:
            video_id = match_short.group(1)

        # Case 2: youtube.com/shorts/<id>
        if not video_id:
            match_shorts_path = YOUTUBE_SHORT_REGEX.match(raw_url)
            if match_shorts_path:
                video_id = match_shorts_path.group(1)

        # Case 3: youtube.com/embed/<id>
        if not video_id:
            match_embed = YOUTUBE_EMBED_REGEX.match(raw_url)
            if match_embed:
                video_id = match_embed.group(1)

        # Case 4: youtube.com/watch?v=<id>
        if not video_id and ("youtube.com" in parsed.netloc.lower() or "music.youtube.com" in parsed.netloc.lower()):
            qs = parse_qs(parsed.query)
            if "v" in qs and qs["v"]:
                candidate_id = qs["v"][0]
                if VIDEO_ID_REGEX.match(candidate_id):
                    video_id = candidate_id

        if video_id and VIDEO_ID_REGEX.match(video_id):
            return f"https://www.youtube.com/watch?v={video_id}"

        # If it was already a valid youtube URL that didn't match the standard regex, return as-is
        if "youtube.com" in parsed.netloc.lower() or "youtu.be" in parsed.netloc.lower():
            return raw_url

        return None

    def supports(self, query: str, query_type: QueryType) -> bool:
        """Determines if query or URL belongs to YouTube."""
        clean = query.strip()
        if query_type == QueryType.DIRECT_URL or clean.startswith("http://") or clean.startswith("https://"):
            return bool(self.normalize_url(clean))
        # Non-URL plain search queries are supported by YouTube provider by default
        return True

    async def search(self, query: str, limit: int = 5, requester: Optional[discord.Member] = None) -> List[TrackCandidate]:
        """
        Fast candidate search using in_playlist extraction.
        Returns candidates in ~1-2s without resolving heavy media streams.
        """
        loop = asyncio.get_running_loop()
        clean_query = query.strip()
        search_query = f"ytsearch{limit}:{clean_query}"

        def _do_search():
            return self._search_ytdl.extract_info(search_query, download=False)

        try:
            data = await asyncio.wait_for(loop.run_in_executor(None, _do_search), timeout=12.0)
        except Exception as exc:
            logger.error(f"YouTube search error for query '{query}': {exc}")
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
            if not webpage_url.startswith("http"):
                webpage_url = f"https://www.youtube.com/watch?v={webpage_url}"

            canonical_url = self.normalize_url(webpage_url) or webpage_url
            duration = int(entry.get("duration") or 0)
            artist = entry.get("uploader") or entry.get("channel") or entry.get("artist") or "Unknown Artist"
            thumbnail = entry.get("thumbnail") or (entry.get("thumbnails")[0]["url"] if entry.get("thumbnails") else None)

            candidates.append(
                TrackCandidate(
                    title=title,
                    url=canonical_url,
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
        """Fetches lightweight candidate metadata from a normalized YouTube URL."""
        loop = asyncio.get_running_loop()
        canonical_url = self.normalize_url(url) or url

        def _do_meta():
            return self._search_ytdl.extract_info(canonical_url, download=False)

        try:
            data = await asyncio.wait_for(loop.run_in_executor(None, _do_meta), timeout=20.0)
        except Exception as exc:
            logger.error(f"YouTube metadata error for URL '{url}': {exc}")
            return None

        if not data:
            return None

        if "entries" in data:
            entries = data.get("entries") or []
            if not entries:
                return None
            data = entries[0]

        title = data.get("title") or "Unknown Title"
        webpage_url = data.get("webpage_url") or canonical_url
        duration = int(data.get("duration") or 0)
        artist = data.get("uploader") or data.get("channel") or "Unknown Artist"
        thumbnail = data.get("thumbnail")

        return TrackCandidate(
            title=title,
            url=webpage_url,
            duration=duration,
            artist=artist,
            thumbnail=thumbnail,
            provider_name=self.name,
            extractor_id=data.get("id"),
            requester=requester,
        )

    async def resolve(self, candidate_or_url: Union[str, TrackCandidate], requester: Optional[discord.Member] = None) -> Optional[ResolvedTrack]:
        """
        Resolves candidate or URL into a fully validated playable audio stream URL.
        """
        loop = asyncio.get_running_loop()
        if isinstance(candidate_or_url, TrackCandidate):
            target_url = candidate_or_url.url
            candidate = candidate_or_url
        else:
            target_url = candidate_or_url
            candidate = None

        canonical_url = self.normalize_url(target_url) or target_url

        def _do_resolve():
            return self._resolve_ytdl.extract_info(canonical_url, download=False)

        try:
            data = await asyncio.wait_for(loop.run_in_executor(None, _do_resolve), timeout=25.0)
        except Exception as exc:
            logger.error(f"YouTube resolution failed for '{canonical_url}': {exc}")
            return None

        if not data:
            return None

        if "entries" in data:
            entries = data.get("entries") or []
            if not entries:
                return None
            data = entries[0]

        stream_url = data.get("url") or ""
        if not stream_url:
            # Check formats if direct url isn't top-level
            formats = data.get("formats") or []
            for fmt in reversed(formats):
                if fmt.get("acodec") != "none" and fmt.get("url"):
                    stream_url = fmt["url"]
                    break

        if not stream_url or not (stream_url.startswith("http://") or stream_url.startswith("https://")):
            logger.warning(f"YouTube resolution returned invalid stream URL for '{canonical_url}'")
            return None

        if not candidate:
            title = data.get("title") or "Unknown Title"
            webpage_url = data.get("webpage_url") or canonical_url
            duration = int(data.get("duration") or 0)
            artist = data.get("uploader") or data.get("channel") or "Unknown Artist"
            thumbnail = data.get("thumbnail")
            candidate = TrackCandidate(
                title=title,
                url=webpage_url,
                duration=duration,
                artist=artist,
                thumbnail=thumbnail,
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
        """Probes YouTube provider readiness with quick probe."""
        try:
            results = await self.search("kalyani", limit=1)
            if results and len(results) > 0:
                return ProviderHealthState.HEALTHY, "Search & extraction operational"
            return ProviderHealthState.DEGRADED, "Search returned empty results"
        except Exception as exc:
            return ProviderHealthState.OFFLINE, f"YouTube probe error: {exc}"
