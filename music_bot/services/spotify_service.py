"""
Spotify Integration Service for Raivora Music Maid.
Compliant integration using official Spotify Web API (Client Credentials Flow)
with robust fallback to open oEmbed metadata.

Strict Compliance Rules:
1. Do NOT extract, rip, decrypt, or bypass DRM on Spotify audio streams.
2. Clearly distinguish Spotify metadata access vs audio playable through the bot.
3. Provide direct, usable Spotify links and embeds for tracks, albums, and playlists.
4. Voice playback resolution uses public audio matching while preserving Spotify metadata.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import discord

from music_bot import config

logger = logging.getLogger("MusicMaid.Spotify")

# Regex patterns for Spotify web links and URI formats
SPOTIFY_URL_REGEX = re.compile(
    r"(?:https?://open\.spotify\.com/(?:intl-[a-zA-Z0-9_-]+/)?|spotify:)(track|album|playlist|artist)(?:/|:)([a-zA-Z0-9]+)",
    re.IGNORECASE,
)


class SpotifyItemType(str, Enum):
    TRACK = "track"
    ALBUM = "album"
    PLAYLIST = "playlist"
    ARTIST = "artist"
    UNKNOWN = "unknown"


@dataclass
class SpotifyTrack:
    id: str
    title: str
    artist: str
    album: Optional[str] = None
    duration_seconds: int = 0
    url: str = ""
    thumbnail_url: Optional[str] = None
    preview_url: Optional[str] = None
    is_playable: bool = True
    explicit: bool = False
    source: str = "spotify"

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
            "is_playable": self.is_playable,
            "explicit": self.explicit,
            "source": self.source,
            "search_query": self.search_query,
        }


@dataclass
class SpotifyCollection:
    type: SpotifyItemType
    id: str
    title: str
    author_or_artist: str
    thumbnail_url: Optional[str] = None
    url: str = ""
    total_tracks: int = 0
    tracks: List[SpotifyTrack] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "id": self.id,
            "title": self.title,
            "author_or_artist": self.author_or_artist,
            "thumbnail": self.thumbnail_url,
            "url": self.url,
            "total_tracks": self.total_tracks,
            "tracks": [t.to_dict() for t in self.tracks],
        }


class SpotifyService:
    """Authoritative Spotify Web API Client and Metadata Extractor."""

    _token_cache: Dict[str, Any] = {
        "access_token": None,
        "expires_at": 0.0,
    }
    _token_lock = asyncio.Lock()

    @classmethod
    def is_configured(cls) -> bool:
        """Check if official client credentials are present in environment."""
        return config.is_spotify_configured()

    @classmethod
    def match_spotify_link(cls, query: str) -> Optional[Tuple[SpotifyItemType, str]]:
        """
        Parses a Spotify URL or URI.
        Returns (item_type, item_id) or None.
        """
        if not query:
            return None
        match = SPOTIFY_URL_REGEX.search(query.strip())
        if not match:
            return None
        raw_type, item_id = match.group(1).lower(), match.group(2)
        try:
            return SpotifyItemType(raw_type), item_id
        except ValueError:
            return None

    @classmethod
    def get_canonical_url(cls, item_type: SpotifyItemType, item_id: str) -> str:
        return f"https://open.spotify.com/{item_type.value}/{item_id}"

    # ---------------------------------------------------------
    # Authentication & Token Management (Client Credentials)
    # ---------------------------------------------------------
    @classmethod
    async def _get_access_token(cls) -> Optional[str]:
        """Obtain or reuse cached Spotify Web API access token."""
        if not cls.is_configured():
            return None

        now = time.time()
        cached_token = cls._token_cache.get("access_token")
        expires_at = cls._token_cache.get("expires_at", 0.0)

        # Token still valid (with 60-second buffer)
        if cached_token and now < (expires_at - 60):
            return cached_token

        async with cls._token_lock:
            # Double-check inside lock
            cached_token = cls._token_cache.get("access_token")
            expires_at = cls._token_cache.get("expires_at", 0.0)
            if cached_token and now < (expires_at - 60):
                return cached_token

            client_id = config.SPOTIFY_CLIENT_ID
            client_secret = config.SPOTIFY_CLIENT_SECRET
            auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

            loop = asyncio.get_running_loop()

            def _request_token() -> Optional[Dict[str, Any]]:
                token_url = "https://accounts.spotify.com/api/token"
                data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
                req = urllib.request.Request(
                    token_url,
                    data=data,
                    headers={
                        "Authorization": f"Basic {auth_header}",
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": "MusicMaid/2.2 (DiscordBot)",
                    },
                )
                try:
                    with urllib.request.urlopen(req, timeout=8.0) as resp:
                        if resp.status == 200:
                            return json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as e:
                    logger.error(f"Spotify token request failed with HTTP {e.code}: {e.reason}")
                except Exception as e:
                    logger.error(f"Spotify token request error: {e}")
                return None

            token_data = await loop.run_in_executor(None, _request_token)
            if token_data and "access_token" in token_data:
                token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                cls._token_cache["access_token"] = token
                cls._token_cache["expires_at"] = time.time() + expires_in
                logger.info("[SpotifyService] Acquired fresh Spotify API access token.")
                return token

            return None

    # ---------------------------------------------------------
    # API Request Helper with Rate-Limit Handling (429 Backoff)
    # ---------------------------------------------------------
    @classmethod
    async def _api_get(cls, endpoint: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """Perform authenticated GET request to Spotify Web API with rate-limit backoff."""
        token = await cls._get_access_token()
        if not token:
            return None

        url = f"https://api.spotify.com/v1/{endpoint.lstrip('/')}"
        loop = asyncio.get_running_loop()

        for attempt in range(max_retries):
            def _do_get() -> Tuple[int, Optional[str], Optional[Dict[str, Any]]]:
                req = urllib.request.Request(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "User-Agent": "MusicMaid/2.2 (DiscordBot)",
                    },
                )
                try:
                    with urllib.request.urlopen(req, timeout=7.0) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            return 200, None, data
                        return resp.status, None, None
                except urllib.error.HTTPError as err:
                    retry_after = err.headers.get("Retry-After")
                    return err.code, retry_after, None
                except Exception as ex:
                    return 0, None, None

            status, retry_header, data = await loop.run_in_executor(None, _do_get)

            if status == 200 and data is not None:
                return data

            if status == 429:
                wait_time = float(retry_header) if retry_header and retry_header.isdigit() else (2.0 ** attempt)
                logger.warning(f"[SpotifyService] Rate limited (429). Backing off for {wait_time}s.")
                await asyncio.sleep(wait_time)
                continue

            if status == 401:
                # Invalidate cached token on unauthorized
                cls._token_cache["access_token"] = None
                cls._token_cache["expires_at"] = 0.0
                token = await cls._get_access_token()
                if not token:
                    return None
                continue

            logger.warning(f"[SpotifyService] API call failed with status {status} for {endpoint}")
            break

        return None

    # ---------------------------------------------------------
    @classmethod
    async def search_tracks(cls, query: str, limit: int = 6) -> List[SpotifyTrack]:
        """Search track metadata through the official Spotify Web API."""
        query = (query or "").strip()
        if not query or not cls.is_configured():
            return []
        params = urllib.parse.urlencode({"q": query, "type": "track", "limit": max(1, min(int(limit), 10))})
        data = await cls._api_get(f"search?{params}")
        if not data:
            return []
        tracks: List[SpotifyTrack] = []
        for item in data.get("tracks", {}).get("items", []):
            track_id = item.get("id")
            if not track_id:
                continue
            artists = ", ".join(a.get("name", "") for a in item.get("artists", [])) or "Unknown Artist"
            album = item.get("album", {})
            images = album.get("images", [])
            tracks.append(SpotifyTrack(
                id=track_id,
                title=item.get("name", "Unknown Title"),
                artist=artists,
                album=album.get("name"),
                duration_seconds=(item.get("duration_ms", 0) or 0) // 1000,
                url=item.get("external_urls", {}).get("spotify") or cls.get_canonical_url(SpotifyItemType.TRACK, track_id),
                thumbnail_url=images[0].get("url") if images else None,
                preview_url=item.get("preview_url"),
                is_playable=item.get("is_playable", True),
                explicit=item.get("explicit", False),
            ))
        return tracks

    # Public Track / Album / Playlist Resolution
    # ---------------------------------------------------------
    @classmethod
    async def get_track(cls, track_id: str) -> Optional[SpotifyTrack]:
        """Fetch track metadata via official Spotify Web API."""
        data = await cls._api_get(f"tracks/{track_id}")
        if not data:
            return None

        artists = ", ".join(a.get("name", "") for a in data.get("artists", [])) or "Unknown Artist"
        album_name = data.get("album", {}).get("name")
        images = data.get("album", {}).get("images", [])
        thumbnail_url = images[0]["url"] if images else None
        duration_ms = data.get("duration_ms", 0)
        external_url = data.get("external_urls", {}).get("spotify") or cls.get_canonical_url(SpotifyItemType.TRACK, track_id)

        return SpotifyTrack(
            id=track_id,
            title=data.get("name", "Unknown Title"),
            artist=artists,
            album=album_name,
            duration_seconds=duration_ms // 1000,
            url=external_url,
            thumbnail_url=thumbnail_url,
            preview_url=data.get("preview_url"),
            is_playable=data.get("is_playable", True),
            explicit=data.get("explicit", False),
        )

    @classmethod
    async def get_album(cls, album_id: str, limit: int = 100) -> Optional[SpotifyCollection]:
        """Fetch album metadata and its tracks via official Spotify Web API."""
        data = await cls._api_get(f"albums/{album_id}")
        if not data:
            return None

        title = data.get("name", "Unknown Album")
        artists = ", ".join(a.get("name", "") for a in data.get("artists", [])) or "Various Artists"
        images = data.get("images", [])
        thumbnail_url = images[0]["url"] if images else None
        external_url = data.get("external_urls", {}).get("spotify") or cls.get_canonical_url(SpotifyItemType.ALBUM, album_id)
        total = data.get("total_tracks", 0)

        tracks_data = data.get("tracks", {}).get("items", [])[:limit]
        tracks: List[SpotifyTrack] = []
        for t in tracks_data:
            t_artists = ", ".join(a.get("name", "") for a in t.get("artists", [])) or artists
            t_url = t.get("external_urls", {}).get("spotify") or cls.get_canonical_url(SpotifyItemType.TRACK, t.get("id", ""))
            tracks.append(
                SpotifyTrack(
                    id=t.get("id", ""),
                    title=t.get("name", "Unknown Track"),
                    artist=t_artists,
                    album=title,
                    duration_seconds=t.get("duration_ms", 0) // 1000,
                    url=t_url,
                    thumbnail_url=thumbnail_url,
                    preview_url=t.get("preview_url"),
                    is_playable=t.get("is_playable", True),
                    explicit=t.get("explicit", False),
                )
            )

        return SpotifyCollection(
            type=SpotifyItemType.ALBUM,
            id=album_id,
            title=title,
            author_or_artist=artists,
            thumbnail_url=thumbnail_url,
            url=external_url,
            total_tracks=total,
            tracks=tracks,
        )

    @classmethod
    async def get_playlist(cls, playlist_id: str, limit: int = 100) -> Optional[SpotifyCollection]:
        """Fetch playlist metadata and its tracks via official Spotify Web API."""
        data = await cls._api_get(f"playlists/{playlist_id}?fields=name,owner,images,external_urls,tracks.total,tracks.items(track(id,name,artists,album(name,images),duration_ms,external_urls,preview_url,is_playable,explicit))")
        if not data:
            return None

        title = data.get("name", "Unknown Playlist")
        owner = data.get("owner", {}).get("display_name", "Spotify User")
        images = data.get("images", [])
        thumbnail_url = images[0]["url"] if images else None
        external_url = data.get("external_urls", {}).get("spotify") or cls.get_canonical_url(SpotifyItemType.PLAYLIST, playlist_id)
        total = data.get("tracks", {}).get("total", 0)

        raw_items = data.get("tracks", {}).get("items", [])[:limit]
        tracks: List[SpotifyTrack] = []
        for item in raw_items:
            t = item.get("track")
            if not t or not t.get("id"):
                continue
            t_artists = ", ".join(a.get("name", "") for a in t.get("artists", [])) or "Unknown Artist"
            t_images = t.get("album", {}).get("images", [])
            t_thumb = t_images[0]["url"] if t_images else thumbnail_url
            t_url = t.get("external_urls", {}).get("spotify") or cls.get_canonical_url(SpotifyItemType.TRACK, t["id"])

            tracks.append(
                SpotifyTrack(
                    id=t["id"],
                    title=t.get("name", "Unknown Track"),
                    artist=t_artists,
                    album=t.get("album", {}).get("name"),
                    duration_seconds=t.get("duration_ms", 0) // 1000,
                    url=t_url,
                    thumbnail_url=t_thumb,
                    preview_url=t.get("preview_url"),
                    is_playable=t.get("is_playable", True),
                    explicit=t.get("explicit", False),
                )
            )

        return SpotifyCollection(
            type=SpotifyItemType.PLAYLIST,
            id=playlist_id,
            title=title,
            author_or_artist=owner,
            thumbnail_url=thumbnail_url,
            url=external_url,
            total_tracks=total,
            tracks=tracks,
        )

    # ---------------------------------------------------------
    # Graceful Open Fallback (oEmbed & Meta Scraper)
    # ---------------------------------------------------------
    @classmethod
    async def resolve_via_oembed(cls, spotify_url: str) -> Optional[SpotifyTrack]:
        """
        Public fallback when official API credentials are not set or during API errors.
        Extracts title, artist, and album thumbnail without requiring developer tokens.
        """
        clean_url = spotify_url.split("?")[0]
        parsed = cls.match_spotify_link(clean_url)
        track_id = parsed[1] if parsed else "spotify"

        loop = asyncio.get_running_loop()

        def _fetch() -> Optional[SpotifyTrack]:
            try:
                oembed_endpoint = f"https://open.spotify.com/oembed?url={clean_url}"
                req = urllib.request.Request(
                    oembed_endpoint,
                    headers={"User-Agent": "MusicMaid/2.2 (DiscordBot)"},
                )
                with urllib.request.urlopen(req, timeout=6.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                track_title = data.get("title", "").strip()
                thumbnail = data.get("thumbnail_url")
                artist = "Unknown Artist"

                # Extract artist from open.spotify.com page title if available
                page_req = urllib.request.Request(
                    clean_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                )
                try:
                    with urllib.request.urlopen(page_req, timeout=5.0) as page_resp:
                        html = page_resp.read().decode("utf-8", errors="ignore")
                        start_idx = html.find("<title>")
                        end_idx = html.find("</title>")
                        if start_idx != -1 and end_idx != -1:
                            page_title = html[start_idx + 7 : end_idx]
                            if " - song and lyrics by " in page_title:
                                parts = page_title.split(" - song and lyrics by ", 1)
                                if not track_title:
                                    track_title = parts[0].strip()
                                artist = parts[1].split(" | Spotify")[0].strip()
                            elif " - song by " in page_title:
                                parts = page_title.split(" - song by ", 1)
                                if not track_title:
                                    track_title = parts[0].strip()
                                artist = parts[1].split(" | Spotify")[0].strip()
                            elif " | Spotify" in page_title:
                                raw_title = page_title.replace(" | Spotify", "").strip()
                                if " - " in raw_title:
                                    pts = raw_title.split(" - ", 1)
                                    artist, track_title = pts[0].strip(), pts[1].strip()
                except Exception:
                    pass

                if track_title:
                    return SpotifyTrack(
                        id=track_id,
                        title=track_title,
                        artist=artist,
                        url=clean_url,
                        thumbnail_url=thumbnail,
                    )
            except Exception as e:
                logger.warning(f"[SpotifyService] oEmbed fallback error for {spotify_url}: {e}")
            return None

        return await loop.run_in_executor(None, _fetch)

    # ---------------------------------------------------------
    # Main Unified Resolver
    # ---------------------------------------------------------
    @classmethod
    async def resolve_url(
        cls, query_or_url: str
    ) -> Optional[Union[SpotifyTrack, SpotifyCollection]]:
        """
        Unified resolver for any Spotify link (track, album, playlist).
        Tries official Web API first; falls back gracefully to oEmbed for tracks.
        """
        parsed = cls.match_spotify_link(query_or_url)
        if not parsed:
            return None

        item_type, item_id = parsed

        # Strategy 1: Official Spotify API
        if cls.is_configured():
            try:
                if item_type == SpotifyItemType.TRACK:
                    res = await cls.get_track(item_id)
                    if res:
                        return res
                elif item_type == SpotifyItemType.ALBUM:
                    res = await cls.get_album(item_id)
                    if res:
                        return res
                elif item_type == SpotifyItemType.PLAYLIST:
                    res = await cls.get_playlist(item_id)
                    if res:
                        return res
            except Exception as e:
                logger.error(f"[SpotifyService] Official API failed for {item_type.value}/{item_id}: {e}")

        # Strategy 2: Graceful oEmbed fallback for single tracks
        if item_type == SpotifyItemType.TRACK or "open.spotify.com" in query_or_url:
            canonical = cls.get_canonical_url(item_type, item_id)
            fallback = await cls.resolve_via_oembed(canonical)
            if fallback:
                return fallback

        return None

    # ---------------------------------------------------------
    # Policy-Compliant Discord UI Embeds
    # ---------------------------------------------------------
    @classmethod
    def build_spotify_track_embed(cls, track: SpotifyTrack) -> discord.Embed:
        """Create a compliant Spotify metadata embed with green accent and attribution."""
        embed = discord.Embed(
            title=f"🟢 {track.title}",
            url=track.url,
            color=0x1DB954,  # Spotify Brand Green
            description=(
                f"👤 **Artist:** `{track.artist}`\n"
                f"💿 **Album:** `{track.album or 'Single'}`\n"
                f"⏱️ **Duration:** `{track.duration_seconds // 60}:{track.duration_seconds % 60:02d}`\n\n"
                f"🔗 [Listen on Spotify]({track.url})\n\n"
                f"🛡️ *Policy Notice: In strict compliance with Spotify Developer Terms, "
                f"Spotify audio is not ripped or bypassed. Voice playback utilizes public stream matching.*"
            ),
        )
        if track.thumbnail_url:
            embed.set_thumbnail(url=track.thumbnail_url)
        embed.set_footer(text="MusicMaid • Official Spotify Web API Metadata", icon_url="https://open.spotifycdn.com/cdn/images/favicon32.b64ecc03.png")
        return embed

    @classmethod
    def build_spotify_collection_embed(cls, collection: SpotifyCollection) -> discord.Embed:
        """Create a compliant collection preview embed."""
        type_label = "Album" if collection.type == SpotifyItemType.ALBUM else "Playlist"
        embed = discord.Embed(
            title=f"🟢 {collection.title} ({type_label})",
            url=collection.url,
            color=0x1DB954,
            description=(
                f"👤 **Creator/Artist:** `{collection.author_or_artist}`\n"
                f"🎶 **Total Tracks:** `{collection.total_tracks}` (Loaded `{len(collection.tracks)}`)\n\n"
                f"🔗 [Open on Spotify]({collection.url})\n\n"
                f"🛡️ *Policy Notice: Tracks will be matched with public audio sources for voice playback.*"
            ),
        )
        if collection.thumbnail_url:
            embed.set_thumbnail(url=collection.thumbnail_url)
        embed.set_footer(text="MusicMaid • Spotify Web API Integration")
        return embed

    @classmethod
    def build_spotify_unsupported_embed(cls, url: str, reason: str = "Audio extraction from Spotify is not supported.") -> discord.Embed:
        """Informative embed when a Spotify link cannot be directly played or matched."""
        clean_url = url.split("?")[0]
        embed = discord.Embed(
            title="🟢 Spotify Playback Notice",
            url=clean_url,
            color=0x1DB954,
            description=(
                f"**Requested Link:** [{clean_url}]({clean_url})\n\n"
                f"⚠️ **{reason}**\n\n"
                f"Spotify audio streams are protected by DRM and proprietary protocols. "
                f"In compliance with Spotify's Developer Terms of Service, MusicMaid does not rip, download, "
                f"or bypass encryption on Spotify audio streams.\n\n"
                f"👉 You can listen to this track directly in your Spotify application: [Open Spotify]({clean_url})"
            ),
        )
        embed.set_footer(text="MusicMaid • Spotify Developer Terms Compliant")
        return embed
