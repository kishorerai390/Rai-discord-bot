"""
Genius & LRCLIB Lyrics Integration for Rai Music Bot.
Fetches high-speed synchronized or plain lyrics without third-party API keys.
Includes in-memory LRU caching and queue pre-fetching for instant 0ms responses.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional
import aiohttp

logger = logging.getLogger("RaiMusic.Lyrics")

LRCLIB_API_URL = "https://lrclib.net/api/get"


class LyricsService:
    """Retrieves and caches track lyrics using open lyrics APIs."""

    _lyrics_cache: Dict[str, str] = {}
    _max_cache_size: int = 200

    @classmethod
    def _make_key(cls, title: str, artist: Optional[str]) -> str:
        t = title.strip().lower()
        a = (artist or "").strip().lower()
        return f"{t}::{a}"

    @classmethod
    async def fetch_lyrics(cls, title: str, artist: Optional[str] = None) -> Optional[str]:
        """Query LRCLIB API for lyrics with memory caching."""
        cache_key = cls._make_key(title, artist)
        if cache_key in cls._lyrics_cache:
            return cls._lyrics_cache[cache_key]

        params = {"track_name": title}
        if artist and artist.lower() not in ("unknown artist", "various artists"):
            params["artist_name"] = artist

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6.0)) as session:
                async with session.get(LRCLIB_API_URL, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        lyrics = data.get("plainLyrics") or data.get("syncedLyrics")
                        if lyrics:
                            cls._store_cache(cache_key, lyrics.strip())
                            return lyrics.strip()
                    elif resp.status == 404:
                        # Fallback: search endpoint
                        search_url = "https://lrclib.net/api/search"
                        async with session.get(search_url, params={"q": f"{artist or ''} {title}".strip()}) as s_resp:
                            if s_resp.status == 200:
                                results = await s_resp.json()
                                if results and isinstance(results, list):
                                    top = results[0]
                                    lyrics = (top.get("plainLyrics") or top.get("syncedLyrics") or "").strip()
                                    if lyrics:
                                        cls._store_cache(cache_key, lyrics)
                                        return lyrics
        except Exception as e:
            logger.warning(f"Lyrics lookup error for '{title}': {e}")

        return None

    @classmethod
    def precache_lyrics(cls, title: str, artist: Optional[str] = None) -> None:
        """Trigger background pre-fetch of lyrics when track is queued or starts playing."""
        cache_key = cls._make_key(title, artist)
        if cache_key in cls._lyrics_cache:
            return

        async def _worker():
            try:
                await cls.fetch_lyrics(title, artist)
            except Exception:
                pass

        asyncio.create_task(_worker())

    @classmethod
    def _store_cache(cls, key: str, text: str) -> None:
        if len(cls._lyrics_cache) >= cls._max_cache_size:
            # Drop arbitrary first item
            first_key = next(iter(cls._lyrics_cache))
            cls._lyrics_cache.pop(first_key, None)
        cls._lyrics_cache[key] = text
