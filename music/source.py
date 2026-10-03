"""
Safe Audio Source and Extraction Engine for Rai.
Guarded by Circuit Breakers to prevent yt-dlp / FFmpeg hangs from starving the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any, Dict, List, Optional
import discord
import yt_dlp

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception:
    pass

from core.circuit_breaker import CircuitBreakerRegistry
from core.errors import CircuitBreakerOpenError, MusicPlaybackError
from music.queue import Track

logger = logging.getLogger("Rai.AudioSource")

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

_ytdl_instance = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class AudioSourceResolver:
    """Non-blocking audio metadata extraction with circuit breaker protection."""

    @classmethod
    async def resolve_track(cls, query: str, requester: discord.Member) -> Optional[Track]:
        """Resolves single track query or URL into Track object."""
        breaker = CircuitBreakerRegistry.get("music_audio_source")
        if not breaker.is_available:
            raise CircuitBreakerOpenError("YouTube/Audio Provider", breaker.get_remaining_open_time())

        loop = asyncio.get_running_loop()

        async def _extract():
            return await loop.run_in_executor(None, lambda: _ytdl_instance.extract_info(query, download=False))

        try:
            data = await breaker.call(_extract)
        except Exception as exc:
            logger.error(f"Failed to extract audio track for '{query}': {exc}")
            return None

        if not data:
            return None

        if "entries" in data:
            if not data["entries"]:
                return None
            data = data["entries"][0]

        return Track(
            title=data.get("title", "Unknown Title"),
            url=data.get("webpage_url", query),
            stream_url=data.get("url") or "",
            duration=data.get("duration", 0),
            requester=requester,
            artist=data.get("uploader", data.get("artist", "Unknown Artist")),
            thumbnail=data.get("thumbnail"),
        )

    @classmethod
    async def search_candidates(cls, query: str, requester: discord.Member, limit: int = 5) -> List[Track]:
        """Multi-candidate search for ambiguous queries."""
        breaker = CircuitBreakerRegistry.get("music_audio_source")
        if not breaker.is_available:
            raise CircuitBreakerOpenError("YouTube/Audio Provider", breaker.get_remaining_open_time())

        loop = asyncio.get_running_loop()
        search_query = f"ytsearch{limit}:{query}" if not query.startswith("http") else query

        async def _search():
            return await loop.run_in_executor(None, lambda: _ytdl_instance.extract_info(search_query, download=False))

        try:
            data = await breaker.call(_search)
        except Exception as exc:
            logger.error(f"Failed multi-track search for '{query}': {exc}")
            return []

        if not data:
            return []

        entries = data.get("entries") if "entries" in data else [data]
        results = []
        for entry in (entries or []):
            if not entry:
                continue
            results.append(
                Track(
                    title=entry.get("title", "Unknown Title"),
                    url=entry.get("webpage_url", query),
                    stream_url=entry.get("url") or "",
                    duration=entry.get("duration", 0),
                    requester=requester,
                    artist=entry.get("uploader", "Unknown Artist"),
                    thumbnail=entry.get("thumbnail"),
                )
            )
        return results

    @classmethod
    def create_audio_source(cls, stream_url: str, volume: float = 0.5) -> discord.AudioSource:
        """Instantiates FFmpeg PCM Volume Transformer."""
        # Ensure static ffmpeg on path
        if not shutil.which("ffmpeg"):
            try:
                import static_ffmpeg
                static_ffmpeg.add_paths()
            except Exception:
                pass

        return discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS),
            volume=volume,
        )
