"""
Apple Music and iTunes Search API Service for MusicMaid.
Compliant catalog discovery and metadata parsing for Apple Music & iTunes links.

Rules:
1. Do NOT attempt to decrypt, rip, or bypass Apple Music FairPlay DRM streams.
2. Extracts track/album/artist metadata and preview URLs using Apple's official iTunes Search/Lookup API.
3. Provides official Apple Music links and album artwork.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from music_bot.services.network_security import validate_safe_url

logger = logging.getLogger("MusicMaid.AppleMusic")

# Regex pattern for Apple Music and iTunes links
# Examples:
# https://music.apple.com/us/album/yellow/1440854486?i=1440854492
# https://music.apple.com/us/album/parachutes/1440854486
# https://music.apple.com/in/song/kesariya/1634790065
APPLE_MUSIC_REGEX = re.compile(
    r"https?://(?:music|itunes)\.apple\.com/(?:(?P<country>[a-z]{2})/)?(?P<type>album|song|artist)/(?P<slug>[^/]+)/(?P<id>\d+)(?:\?i=(?P<track_id>\d+))?",
    re.IGNORECASE,
)


@dataclass
class AppleMusicTrack:
    id: str
    title: str
    artist: str
    album: Optional[str] = None
    duration_seconds: int = 0
    url: str = ""
    thumbnail_url: Optional[str] = None
    preview_url: Optional[str] = None
    source: str = "apple_music"

    @property
    def search_query(self) -> str:
        if self.artist and self.artist.lower() != "unknown artist":
            return f"{self.title} {self.artist}"
        return self.title

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration": self.duration_seconds,
            "url": self.url,
            "thumbnail": self.thumbnail_url,
            "preview_url": self.preview_url,
            "source": self.source,
            "search_query": self.search_query,
        }


class AppleMusicService:
    """Provides Apple Music metadata lookup and URL resolution via the iTunes Search API."""

    _metadata_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}

    @classmethod
    def is_apple_music_url(cls, url: str) -> bool:
        if not url or not isinstance(url, str):
            return False
        return bool(APPLE_MUSIC_REGEX.search(url))

    @classmethod
    async def resolve_url(cls, url: str) -> Optional[Dict[str, Any]]:
        """Resolve an Apple Music track or album URL into catalog metadata."""
        match = APPLE_MUSIC_REGEX.search(url)
        if not match:
            return None

        country = match.group("country") or "us"
        link_type = (match.group("type") or "").lower()
        target_id = match.group("track_id") or match.group("id")

        if not target_id:
            return None

        cache_key = f"apple:{country}:{target_id}"
        now = asyncio.get_running_loop().time()
        if cache_key in cls._metadata_cache:
            data, exp = cls._metadata_cache[cache_key]
            if now < exp:
                return data

        lookup_url = f"https://itunes.apple.com/lookup?id={target_id}&country={country}"
        is_safe, err, _ = validate_safe_url(lookup_url)
        if not is_safe:
            logger.warning(f"[AppleMusic] Target URL failed security validation: {err}")
            return None

        def _fetch_lookup() -> Optional[Dict[str, Any]]:
            req = urllib.request.Request(
                lookup_url,
                headers={"User-Agent": "MusicMaid/2.7 (Discord Bot; Lossless Audio Engine)"},
            )
            try:
                with urllib.request.urlopen(req, timeout=6.0) as resp:
                    if resp.status == 200:
                        raw = resp.read().decode("utf-8")
                        return json.loads(raw)
            except Exception as e:
                logger.warning(f"[AppleMusic] Lookup error for id={target_id}: {e}")
                return None
            return None

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _fetch_lookup)
        if not result or not result.get("results"):
            return None

        first = result["results"][0]
        title = first.get("trackName") or first.get("collectionName") or "Unknown Apple Music Item"
        artist = first.get("artistName") or "Unknown Artist"
        album = first.get("collectionName")
        duration_ms = first.get("trackTimeMillis") or 0
        duration = int(duration_ms // 1000)
        artwork = first.get("artworkUrl100") or first.get("artworkUrl60")
        if artwork and "100x100bb" in artwork:
            artwork = artwork.replace("100x100bb", "600x600bb")

        preview = first.get("previewUrl")
        item_url = first.get("trackViewUrl") or first.get("collectionViewUrl") or url

        track = AppleMusicTrack(
            id=str(target_id),
            title=title,
            artist=artist,
            album=album,
            duration_seconds=duration,
            url=item_url,
            thumbnail_url=artwork,
            preview_url=preview,
        )

        d = track.to_dict()
        cls._metadata_cache[cache_key] = (d, now + 3600.0)  # 1 hour cache
        return d
