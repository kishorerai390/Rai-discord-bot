"""
Cross-Platform Playlist Importer Service for MusicMaid.
Imports playlists and albums from Spotify, YouTube, Apple Music, and SoundCloud
directly into the server or user's saved playlists.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional
import urllib.parse

from music_bot.database.models import QueuedTrack
from music_bot.services.resolver_service import AudioResolver

logger = logging.getLogger("MusicMaid.Importer")


@dataclass
class PlaylistImportResult:
    success: bool
    playlist_name: str
    platform: str
    track_count: int
    sample_tracks: List[str] = field(default_factory=list)
    tracks: List[QueuedTrack] = field(default_factory=list)
    error: Optional[str] = None


class PlaylistImporterService:
    """Imports playlists and albums from external platforms into MusicMaid."""

    @classmethod
    def detect_platform(cls, url: str) -> str:
        """Detect the source platform of a given playlist URL."""
        lowered = url.lower().strip()
        if "spotify.com" in lowered or lowered.startswith("spotify:"):
            return "Spotify"
        elif "youtube.com" in lowered or "youtu.be" in lowered:
            return "YouTube"
        elif "apple.com" in lowered:
            return "Apple Music"
        elif "soundcloud.com" in lowered:
            return "SoundCloud"
        return "Web Stream"

    @classmethod
    async def extract_tracks_from_url(
        cls, url: str, requester_id: int, requester_name: str, limit: int = 100
    ) -> tuple[str, List[QueuedTrack], str]:
        """
        Extract tracks and playlist name from a supported platform URL.
        Returns: (playlist_title, track_list, platform_name)
        """
        platform = cls.detect_platform(url)

        # 1. Spotify Playlist or Album
        if platform == "Spotify":
            col = await AudioResolver.resolve_spotify_collection(url, limit=limit)
            if col and col.get("tracks"):
                pl_title = col.get("title") or "Spotify Mix"
                tracks: List[QueuedTrack] = []
                for t in col["tracks"][:limit]:
                    q_title = t.get("name") or t.get("title") or "Unknown Track"
                    q_art = t.get("artist") or "Unknown Artist"
                    tracks.append(
                        QueuedTrack(
                            title=q_title,
                            url=t.get("url") or f"https://open.spotify.com/track/{t.get('id', '')}",
                            stream_url="",
                            duration=int(t.get("duration", 0)),
                            artist=q_art,
                            thumbnail=col.get("thumbnail"),
                            requester_id=requester_id,
                            requester_name=requester_name,
                        )
                    )
                return pl_title, tracks, platform

        # 2. YouTube Playlist or other generic playlists via yt-dlp flat extraction
        def _extract_flat_ytdlp() -> Optional[Dict[str, Any]]:
            try:
                import yt_dlp
                ydl_opts = {
                    "extract_flat": True,
                    "skip_download": True,
                    "quiet": True,
                    "no_warnings": True,
                    "ignoreerrors": True,
                    "playlistend": limit,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return info
            except Exception as yt_err:
                logger.warning(f"[Importer] yt-dlp extraction error for {url}: {yt_err}")
                return None

        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, _extract_flat_ytdlp)

        if info:
            entries = info.get("entries") or []
            if not entries and info.get("title"):
                # Single track fallback
                entries = [info]

            pl_title = info.get("title") or f"{platform} Import"
            tracks: List[QueuedTrack] = []
            for entry in entries[:limit]:
                if not entry:
                    continue
                t_title = entry.get("title") or "Untitled Track"
                t_url = entry.get("url")
                if not t_url and entry.get("id"):
                    t_url = f"https://www.youtube.com/watch?v={entry['id']}"
                if not t_url:
                    t_url = url

                t_dur = int(entry.get("duration") or 0)
                t_art = entry.get("uploader") or entry.get("artist") or "Various Artists"
                t_thumb = None
                if entry.get("thumbnails"):
                    t_thumb = entry["thumbnails"][-1].get("url")

                tracks.append(
                    QueuedTrack(
                        title=t_title,
                        url=t_url,
                        stream_url="",
                        duration=t_dur,
                        artist=t_art,
                        thumbnail=t_thumb,
                        requester_id=requester_id,
                        requester_name=requester_name,
                    )
                )

            if tracks:
                return pl_title, tracks, platform

        return "Imported Playlist", [], platform

    @classmethod
    async def import_playlist(
        cls,
        bot: Any,
        url: str,
        guild_id: int,
        user_id: int,
        user_name: str,
        custom_name: Optional[str] = None,
        limit: int = 100,
    ) -> PlaylistImportResult:
        """
        Extract tracks from an external URL and persist them into the user's saved playlists.
        """
        try:
            pl_title, tracks, platform = await cls.extract_tracks_from_url(
                url, requester_id=user_id, requester_name=user_name, limit=limit
            )

            if not tracks:
                return PlaylistImportResult(
                    success=False,
                    playlist_name=custom_name or "Unknown",
                    platform=platform,
                    track_count=0,
                    error=f"No playable tracks could be extracted from this {platform} URL.",
                )

            target_name = (custom_name or pl_title).strip()[:40]

            # Save to database
            if hasattr(bot, "db") and bot.db:
                # Remove if exists to allow updating/re-importing
                await bot.db.delete_playlist(guild_id, user_id, target_name)
                pl_id = await bot.db.create_playlist(guild_id, user_id, target_name)
                if pl_id:
                    for t in tracks:
                        await bot.db.add_playlist_track(pl_id, t)

            sample_titles = [f"{t.artist} — {t.title}" for t in tracks[:5]]

            return PlaylistImportResult(
                success=True,
                playlist_name=target_name,
                platform=platform,
                track_count=len(tracks),
                sample_tracks=sample_titles,
                tracks=tracks,
            )

        except Exception as e:
            logger.error(f"[Importer] Failed to import playlist from {url}: {e}", exc_info=True)
            return PlaylistImportResult(
                success=False,
                playlist_name=custom_name or "Import Error",
                platform=cls.detect_platform(url),
                track_count=0,
                error=str(e),
            )
