"""
Genius & LRCLIB Lyrics Integration for Rai Music Bot.
Fetches high-speed synchronized or plain lyrics without third-party API keys.
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Optional
import aiohttp

logger = logging.getLogger("RaiMusic.Lyrics")

LRCLIB_API_URL = "https://lrclib.net/api/get"


class LyricsService:
    """Retrieves track lyrics using open lyrics APIs."""

    @classmethod
    async def fetch_lyrics(cls, title: str, artist: Optional[str] = None) -> Optional[str]:
        """Query LRCLIB API for lyrics."""
        params = {"track_name": title}
        if artist and artist.lower() not in ("unknown artist", "various artists"):
            params["artist_name"] = artist

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8.0)) as session:
                async with session.get(LRCLIB_API_URL, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        lyrics = data.get("plainLyrics") or data.get("syncedLyrics")
                        if lyrics:
                            return lyrics.strip()
                    elif resp.status == 404:
                        # Fallback: search endpoint
                        search_url = "https://lrclib.net/api/search"
                        async with session.get(search_url, params={"q": f"{artist or ''} {title}".strip()}) as s_resp:
                            if s_resp.status == 200:
                                results = await s_resp.json()
                                if results and isinstance(results, list):
                                    top = results[0]
                                    return (top.get("plainLyrics") or top.get("syncedLyrics") or "").strip()
        except Exception as e:
            logger.warning(f"Lyrics lookup error for '{title}': {e}")

        return None
