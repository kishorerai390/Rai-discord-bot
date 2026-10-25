"""
JukeBot Music Engine Integration for MusicMaid.
Ports JukeBot's (Dysta/JukeBot) StreamRequest extraction, audio stream parameters,
and curated radio station collections into MusicMaid.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Any, Dict, List, Optional
import yt_dlp

logger = logging.getLogger("RaiMusic.JukeBot")

# JukeBot Curated Radio Stations (from JukeBot radios.yaml)
JUKEBOT_RADIOS: Dict[str, List[str]] = {
    "lofi": [
        "https://www.youtube.com/watch?v=jfKfPfyJRdk",
        "https://www.youtube.com/watch?v=rUxyKA_-grg",
        "https://www.youtube.com/watch?v=HAZoLuME-PU",
        "https://www.youtube.com/watch?v=7NOSDKb0HlU",
    ],
    "jazz": [
        "https://www.youtube.com/watch?v=Dx5qFachd3A",
        "https://www.youtube.com/watch?v=fEvM-OUbaKs",
        "https://www.youtube.com/watch?v=g06AjrOlki0",
        "https://www.youtube.com/watch?v=DSGyEsJ17cI",
        "https://www.youtube.com/watch?v=c3IVTi6TlfE",
        "https://www.youtube.com/watch?v=_rMZt292mJc",
    ],
    "synthwave": [
        "https://www.youtube.com/playlist?list=PL9a7fFpVuuJCNx1VfUKlusNP-4TGBTuz5",
        "https://www.youtube.com/watch?v=Ss3DEK1rGuM",
        "https://www.youtube.com/watch?v=FvwJ_Fh5_uE",
        "https://www.youtube.com/watch?v=4xDzrJKXOOY",
    ],
    "phonk": [
        "https://www.youtube.com/watch?v=S6helKOW5P0",
        "https://www.youtube.com/watch?v=8v_kKMaq5po",
    ],
    "lounge": [
        "https://www.youtube.com/watch?v=fEvM-OUbaKs",
        "https://www.youtube.com/watch?v=Dx5qFachd3A",
        "https://www.youtube.com/watch?v=XQuR1OxYJt0",
        "https://www.youtube.com/watch?v=3XbEUv_MCj0",
    ],
    "rocknroll": [
        "https://www.youtube.com/watch?v=zdBGqWnpDRk",
        "https://www.youtube.com/playlist?list=PLZN_exA7d4RVmCQrG5VlWIjMOkMFZVVOc",
    ],
    "poprock": [
        "https://www.youtube.com/watch?v=EurKD84TFtA",
        "https://www.youtube.com/watch?v=uRImXboQnzE",
        "https://www.youtube.com/watch?v=Va-h6WZPUzQ",
    ],
    "workout": [
        "https://www.youtube.com/watch?v=qWf-FPFmVw0",
        "https://www.youtube.com/watch?v=fBnpWP4Fneg",
        "https://www.youtube.com/watch?v=bT408U-LOn8",
    ],
    "minecraft": [
        "https://www.youtube.com/watch?v=Pa_s7ogtokM",
        "https://www.youtube.com/watch?v=TsTtqGAxvWk",
        "https://www.youtube.com/watch?v=Dg0IjOzopYU",
        "https://www.youtube.com/watch?v=snphzO9UFJM",
        "https://www.youtube.com/watch?v=0KvlwMd3C4Y",
    ],
    "rap": [
        "https://www.youtube.com/watch?v=05689ErDUdM",
        "https://www.youtube.com/watch?v=0MOkLkTP-Jk",
    ],
    "chiptune": [
        "https://www.youtube.com/watch?v=KzFmtxFG9z4",
        "https://www.youtube.com/watch?v=VcQqVMQHYYU",
    ],
}


class JukeBotStreamRequest:
    """
    Port of JukeBot's StreamRequest.
    Uses JukeBot's specialized yt-dlp parameters designed for clean direct audio extraction
    with 0.0.0.0 source binding, certificate verification bypass, and low-latency socket timeout.
    """

    YTDL_OPTIONS: Dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
        "restrictfilenames": True,
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "logtostderr": False,
        "quiet": True,
        "no_warnings": True,
        "default_search": "auto",
        "source_address": "0.0.0.0",
        "socket_timeout": 8,
        "noplaylist": True,
        "cachedir": False,
    }

    # JukeBot FFmpeg audio player parameters
    FFMPEG_BEFORE_OPTIONS: str = (
        "-vn -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 3 -nostdin"
    )

    @classmethod
    async def extract_stream(
        cls,
        query_or_url: str,
        timeout: float = 12.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Extract stream information using JukeBot's extraction pipeline.
        Returns a dictionary containing stream_url, title, duration, uploader, etc.
        """
        loop = asyncio.get_running_loop()

        def _sync_extract() -> Optional[Dict[str, Any]]:
            try:
                with yt_dlp.YoutubeDL(params=cls.YTDL_OPTIONS) as ytdl:
                    data = ytdl.extract_info(url=query_or_url, download=False)
                    if not data:
                        return None
                    if "entries" in data:
                        entries = [e for e in data["entries"] if e]
                        return entries[0] if entries else None
                    return data
            except Exception as exc:
                logger.debug(f"[JukeBot] Stream extraction notice for '{query_or_url[:60]}': {exc}")
                return None

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _sync_extract),
                timeout=timeout,
            )
            if result and result.get("url"):
                return {
                    "stream_url": result["url"],
                    "title": result.get("title", "Unknown Title"),
                    "duration": round(result.get("duration") or 0),
                    "thumbnail": result.get("thumbnail"),
                    "uploader": result.get("channel") or result.get("uploader") or "Unknown Artist",
                    "url": result.get("webpage_url") or query_or_url,
                    "id": result.get("id"),
                }
            return None
        except asyncio.TimeoutError:
            logger.debug(f"[JukeBot] Stream extraction timed out after {timeout}s for '{query_or_url[:60]}'")
            return None
        except Exception as exc:
            logger.debug(f"[JukeBot] Stream extraction exception for '{query_or_url[:60]}': {exc}")
            return None

    @classmethod
    def get_random_radio_url(cls, station_name: str) -> Optional[str]:
        """Return a random stream URL for the requested radio station."""
        urls = JUKEBOT_RADIOS.get(station_name.lower())
        if urls:
            return random.choice(urls)
        return None

    @classmethod
    def list_radio_stations(cls) -> List[str]:
        """Return a list of available radio station names."""
        return list(JUKEBOT_RADIOS.keys())
