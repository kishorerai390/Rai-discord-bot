"""
Audio Track Search and Stream Resolution Engine for Rai Music Bot.
Operates asynchronously with yt-dlp in a thread pool to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Dict, List, Optional
import yt_dlp

from music_bot.database.models import QueuedTrack

logger = logging.getLogger("RaiMusic.Resolver")

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "extractaudio": True,
    "audioformat": "mp3",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

_ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class AudioResolver:
    """Handles query searching, URL extraction, and stream link generation."""

    @classmethod
    async def search(cls, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search YouTube for tracks matching query and return raw candidates."""
        loop = asyncio.get_running_loop()
        search_query = f"ytsearch{limit}:{query}" if not query.startswith("http") else query

        try:
            data = await loop.run_in_executor(
                None, functools.partial(_ytdl.extract_info, search_query, download=False)
            )
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            raise e

        if not data:
            return []

        entries = data.get("entries") if "entries" in data else [data]
        results = []
        for entry in entries:
            if not entry:
                continue
            results.append({
                "title": entry.get("title", "Unknown Track"),
                "url": entry.get("webpage_url") or entry.get("url", ""),
                "duration": int(entry.get("duration", 0)),
                "artist": entry.get("uploader") or entry.get("channel", "Unknown Artist"),
                "thumbnail": entry.get("thumbnail"),
                "id": entry.get("id"),
            })
        return results

    @classmethod
    async def resolve_track(
        cls, query_or_url: str, requester_id: int, requester_name: str
    ) -> Optional[QueuedTrack]:
        """Resolve a query or direct link into a playable QueuedTrack with stream URL."""
        loop = asyncio.get_running_loop()
        target = query_or_url if query_or_url.startswith("http") else f"ytsearch1:{query_or_url}"

        try:
            data = await loop.run_in_executor(
                None, functools.partial(_ytdl.extract_info, target, download=False)
            )
        except Exception as e:
            logger.error(f"Track resolution failed for '{query_or_url}': {e}")
            raise e

        if not data:
            return None

        entry = data["entries"][0] if "entries" in data and data["entries"] else data
        if not entry:
            return None

        # Find best playable stream url
        stream_url = entry.get("url")
        if not stream_url and "formats" in entry:
            for fmt in entry["formats"]:
                if fmt.get("acodec") != "none" and fmt.get("url"):
                    stream_url = fmt["url"]
                    break

        if not stream_url:
            logger.warning(f"No playable audio stream found for {entry.get('title')}")
            return None

        return QueuedTrack(
            title=entry.get("title", "Unknown Title"),
            url=entry.get("webpage_url") or entry.get("url", ""),
            stream_url=stream_url,
            duration=int(entry.get("duration", 0)),
            requester_id=requester_id,
            requester_name=requester_name,
            artist=entry.get("uploader") or entry.get("channel", "Unknown Artist"),
            thumbnail=entry.get("thumbnail"),
        )
