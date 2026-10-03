"""
Direct Audio Stream Provider for RAI.
Handles raw media URLs (mp3, ogg, flac, aac, wav, m4a, m3u8) with HTTP pre-flight validation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Tuple, Union
from urllib.parse import urlparse

import aiohttp
import discord

from music.provider import (
    MusicProvider,
    ProviderHealthState,
    QueryType,
    ResolvedTrack,
    TrackCandidate,
)

logger = logging.getLogger("Rai.DirectAudioProvider")

SUPPORTED_AUDIO_EXTENSIONS = (
    ".mp3",
    ".ogg",
    ".wav",
    ".flac",
    ".aac",
    ".m4a",
    ".opus",
    ".m3u8",
)


class DirectAudioProvider(MusicProvider):
    """Direct HTTP/HTTPS audio file and live stream provider."""

    def __init__(self):
        self._name = "DirectAudio"

    @property
    def name(self) -> str:
        return self._name

    def supports(self, query: str, query_type: QueryType) -> bool:
        clean = query.strip().lower()
        if not (clean.startswith("http://") or clean.startswith("https://")):
            return False
        parsed = urlparse(clean)
        path = parsed.path.lower()
        return any(path.endswith(ext) for ext in SUPPORTED_AUDIO_EXTENSIONS)

    async def search(self, query: str, limit: int = 5, requester: Optional[discord.Member] = None) -> List[TrackCandidate]:
        # Direct audio does not perform textual catalog searches
        return []

    async def get_metadata(self, url: str, requester: Optional[discord.Member] = None) -> Optional[TrackCandidate]:
        clean_url = url.strip()
        parsed = urlparse(clean_url)
        filename = parsed.path.split("/")[-1] or "Direct Audio Stream"

        # Pre-flight check via HEAD request
        is_valid = False
        content_type = ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(clean_url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
                    if resp.status in (200, 206):
                        is_valid = True
                        content_type = resp.headers.get("Content-Type", "")
        except Exception:
            pass

        if not is_valid:
            # Try GET probe with range header
            try:
                headers = {"Range": "bytes=0-1024"}
                async with aiohttp.ClientSession() as session:
                    async with session.get(clean_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
                        if resp.status in (200, 206):
                            is_valid = True
            except Exception:
                pass

        if not is_valid:
            return None

        return TrackCandidate(
            title=filename,
            url=clean_url,
            duration=0,
            artist="Direct Audio Stream",
            thumbnail=None,
            provider_name=self.name,
            extractor_id=filename,
            requester=requester,
        )

    async def resolve(self, candidate_or_url: Union[str, TrackCandidate], requester: Optional[discord.Member] = None) -> Optional[ResolvedTrack]:
        if isinstance(candidate_or_url, TrackCandidate):
            url = candidate_or_url.url
            candidate = candidate_or_url
        else:
            url = candidate_or_url
            candidate = await self.get_metadata(url, requester=requester)

        if not candidate:
            return None

        return ResolvedTrack(
            candidate=candidate,
            stream_url=url,
            is_playable=True,
        )

    async def health_check(self) -> Tuple[ProviderHealthState, str]:
        return ProviderHealthState.HEALTHY, "Direct Audio stream parser ready"
