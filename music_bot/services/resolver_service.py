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

from pathlib import Path
import os

logger = logging.getLogger("RaiMusic.Resolver")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
COOKIE_PATHS = [
    BASE_DIR / "data" / "cookies.txt",
    BASE_DIR / "data" / "youtube_cookies.txt",
    BASE_DIR / "cookies.txt",
]
TOKENS_FILE = BASE_DIR / "data" / "tokens.json"


def _load_po_tokens_and_cookies() -> Dict[str, Any]:
    """Load PO-Token and visitor data pool from data/tokens.json for automated rotation."""
    if not TOKENS_FILE.exists():
        try:
            TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
            default_data = {
                "active_po_token": "",
                "visitor_data": "",
                "tokens": [],
                "cookies": [],
                "last_rotated": 0.0,
            }
            import json
            TOKENS_FILE.write_text(json.dumps(default_data, indent=2))
        except Exception:
            pass
        return {}
    try:
        import json
        return json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


import concurrent.futures
import shutil
import time

_audio_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="AudioResolver")


def _detect_js_runtimes() -> Dict[str, Any]:
    """Detect available JavaScript runtimes for yt-dlp EJS challenge solver."""
    node = shutil.which("node") or "C:\\Program Files\\nodejs\\node.exe"
    if node and (Path(node).exists() or shutil.which("node")):
        return {"node": {}}
    deno = shutil.which("deno")
    if deno:
        return {"deno": {}}
    quickjs = shutil.which("quickjs")
    if quickjs:
        return {"quickjs": {}}
    return {}



def get_ffmpeg_executable() -> str:
    """Resolve active FFmpeg binary path from system PATH or static-ffmpeg."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        found = shutil.which("ffmpeg")
        if found:
            return found
    except Exception:
        pass
    return "ffmpeg"


def _sync_environment_cookies() -> None:
    """Load YouTube cookies from environment variables if present on Render/Cloud hosts."""
    raw_cookies = os.environ.get("YOUTUBE_COOKIES") or os.environ.get("YOUTUBE_COOKIES_DATA")
    if not raw_cookies and os.environ.get("YOUTUBE_COOKIES_BASE64"):
        try:
            import base64
            raw_cookies = base64.b64decode(os.environ["YOUTUBE_COOKIES_BASE64"]).decode("utf-8")
        except Exception as e:
            logger.warning(f"Could not decode YOUTUBE_COOKIES_BASE64: {e}")

    if raw_cookies and raw_cookies.strip():
        target = BASE_DIR / "data" / "cookies.txt"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(raw_cookies.strip(), encoding="utf-8")
            logger.info(f"Loaded YouTube authentication cookies from environment variable into {target}")
        except Exception as e:
            logger.warning(f"Failed writing environment cookies to {target}: {e}")


# Sync cookies on import
_sync_environment_cookies()


def _build_ytdl_options(player_clients: Optional[List[str]] = None) -> Dict[str, Any]:
    # Default to Android and iOS player clients which have significantly higher success rates on datacenter IPs
    clients = player_clients or ["android", "ios", "mweb", "web_creator"]
    opts: Dict[str, Any] = {
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
        "default_search": "ytsearch",
        "source_address": "0.0.0.0",
        "socket_timeout": 8,
        "extractor_retries": 1,
        "remote_components": ["ejs:github"],
        "extractor_args": {
            "youtube": {
                "player_client": clients,
                "skip": ["translated_subs", "dash", "hls"],
            }
        },
    }

    if player_clients:
        opts["extractor_args"]["youtube"]["player_client"] = player_clients

    # Automatically attach JavaScript runtime for EJS signature solving
    js_runtimes = _detect_js_runtimes()
    if js_runtimes:
        opts["js_runtimes"] = js_runtimes

    # Feature: Inject active YouTube PO-Token / Visitor Data to prevent 403 & SABR blocks
    token_data = _load_po_tokens_and_cookies()
    po_token = token_data.get("active_po_token")
    visitor_data = token_data.get("visitor_data")
    if po_token:
        opts["extractor_args"]["youtube"]["po_token"] = [f"web+{po_token}", f"mweb+{po_token}"]
    if visitor_data:
        opts["extractor_args"]["youtube"]["visitor_data"] = [visitor_data]

    for cp in COOKIE_PATHS:
        if cp.exists() and cp.stat().st_size > 0:
            opts["cookiefile"] = str(cp)
            logger.info(f"Loaded YouTube authentication cookies from {cp}")
            break
    return opts


YTDL_OPTIONS = _build_ytdl_options()

FFMPEG_OPTIONS = {
    "executable": get_ffmpeg_executable(),
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -analyzeduration 0 -loglevel warning",
    "options": "-vn",
}

_ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class AudioResolver:
    """Handles query searching, URL extraction, and stream link generation with ultra-low latency."""

    _search_cache: Dict[str, List[Dict[str, Any]]] = {}
    PROFILE_PRESETS: List[List[str]] = [
        ["android", "ios"],
        ["ios", "mweb"],
        ["android", "mweb"],
        ["mweb", "web_creator"],
        ["ios", "web_creator"],
    ]
    _active_profile_index: int = 0

    @classmethod
    def get_current_profile_name(cls) -> str:
        idx = cls._active_profile_index % len(cls.PROFILE_PRESETS)
        return "+".join(cls.PROFILE_PRESETS[idx])

    @classmethod
    def rotate_client_profile(cls) -> str:
        """Rotates yt-dlp client profile in memory to bypass SABR / stream blocks with 0 downtime."""
        cls._active_profile_index = (cls._active_profile_index + 1) % len(cls.PROFILE_PRESETS)
        new_profile = cls.PROFILE_PRESETS[cls._active_profile_index]
        global _ytdl, YTDL_OPTIONS
        YTDL_OPTIONS = _build_ytdl_options(new_profile)
        _ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
        profile_name = "+".join(new_profile)
        logger.info(f"[CanaryEngine] Rotated yt-dlp client profile to: {profile_name}")
        return profile_name

    @classmethod
    async def probe_extractor_health(cls) -> Dict[str, Any]:
        """Canary Probe: Tests resolving a 5-second test audio clip. Rotates clients if issues detected."""
        import time
        start_t = time.time()
        test_target = "ytsearch1:lofi silence beats"
        loop = asyncio.get_running_loop()

        for attempt in range(len(cls.PROFILE_PRESETS)):
            try:
                data = await asyncio.wait_for(
                    loop.run_in_executor(
                        _audio_executor, functools.partial(_ytdl.extract_info, test_target, download=False)
                    ),
                    timeout=6.0,
                )
                entry = data["entries"][0] if "entries" in data and data["entries"] else data
                stream_url = entry.get("url") if entry else None
                if not stream_url and entry and "formats" in entry:
                    for fmt in entry["formats"]:
                        if fmt.get("acodec") != "none" and fmt.get("url"):
                            stream_url = fmt["url"]
                            break
                if stream_url:
                    latency = round((time.time() - start_t) * 1000, 2)
                    return {
                        "operational": True,
                        "profile": cls.get_current_profile_name(),
                        "latency_ms": latency,
                        "message": f"Healthy ({latency}ms latency)",
                    }
            except Exception as e:
                logger.warning(f"[CanaryProbe] Client profile '{cls.get_current_profile_name()}' probe failed: {e}. Auto-rotating...")
                cls.rotate_client_profile()

        return {
            "operational": False,
            "profile": cls.get_current_profile_name(),
            "message": "All extractor profiles encountered restrictions. YouTube may require PO-Token or yt-dlp update.",
        }

    @classmethod
    def rotate_po_token(cls) -> Tuple[bool, str]:
        """Rotates to next PO-Token in data/tokens.json if available."""
        token_data = _load_po_tokens_and_cookies()
        tokens = token_data.get("tokens", [])
        if not tokens:
            return False, "No secondary PO-Tokens configured in data/tokens.json."

        curr_token = token_data.get("active_po_token", "")
        try:
            curr_idx = tokens.index(curr_token) if curr_token in tokens else -1
            next_token = tokens[(curr_idx + 1) % len(tokens)]
        except Exception:
            next_token = tokens[0]

        token_data["active_po_token"] = next_token
        import time, json
        token_data["last_rotated"] = time.time()
        try:
            TOKENS_FILE.write_text(json.dumps(token_data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to write rotated token: {e}")

        # Rebuild options and YoutubeDL instance in memory
        global _ytdl, YTDL_OPTIONS
        YTDL_OPTIONS = _build_ytdl_options(cls.PROFILE_PRESETS[cls._active_profile_index])
        _ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
        msg = f"Successfully rotated to next PO-Token ({next_token[:8]}...)."
        logger.info(f"[TokenRotator] {msg}")
        return True, msg

    @classmethod
    def _parse_entry(cls, data: Any, requester_id: int, requester_name: str) -> Optional[QueuedTrack]:
        """Parse raw yt-dlp dictionary into a validated QueuedTrack, avoiding DRM-restricted formats."""
        if not data:
            return None
        entry = data["entries"][0] if "entries" in data and data["entries"] else data
        if not entry:
            return None

        # Find best playable stream url (filtering out DRM protected streams)
        stream_url = entry.get("url")
        if not stream_url and "formats" in entry:
            # 1. Best audio non-DRM format
            for fmt in entry["formats"]:
                if fmt.get("acodec") != "none" and fmt.get("url") and not fmt.get("has_drm"):
                    stream_url = fmt["url"]
                    break
            # 2. Any non-DRM format with URL
            if not stream_url:
                for fmt in entry["formats"]:
                    if fmt.get("url") and not fmt.get("has_drm"):
                        stream_url = fmt["url"]
                        break

        if not stream_url:
            return None

        return QueuedTrack(
            title=entry.get("title", "Unknown Title"),
            url=entry.get("webpage_url") or entry.get("url", ""),
            stream_url=stream_url,
            duration=int(entry.get("duration", 0) or 0),
            requester_id=requester_id,
            requester_name=requester_name,
            artist=entry.get("uploader") or entry.get("channel", "Unknown Artist"),
            thumbnail=entry.get("thumbnail"),
        )

    @classmethod
    async def search(cls, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search YouTube for tracks matching query with in-memory caching and SoundCloud fallback."""
        cache_key = f"{limit}:{query.strip().lower()}"
        if cache_key in cls._search_cache:
            return cls._search_cache[cache_key]

        loop = asyncio.get_running_loop()
        search_query = f"ytsearch{limit}:{query}" if not query.startswith("http") else query

        try:
            data = await asyncio.wait_for(
                loop.run_in_executor(
                    _audio_executor, functools.partial(_ytdl.extract_info, search_query, download=False)
                ),
                timeout=20.0,
            )
        except Exception as e:
            logger.warning(f"YouTube search failed for '{query}': {e}. Attempting SoundCloud fallback...")
            try:
                sc_query = f"scsearch{limit + 3}:{query}"
                sc_opts = _build_ytdl_options()
                sc_opts.update({"quiet": True, "noplaylist": True, "socket_timeout": 15})
                sc_ydl = yt_dlp.YoutubeDL(sc_opts)
                data = await asyncio.wait_for(
                    loop.run_in_executor(
                        _audio_executor, functools.partial(sc_ydl.extract_info, sc_query, download=False)
                    ),
                    timeout=20.0,
                )
            except Exception as sc_err:
                logger.error(f"SoundCloud search fallback also failed for '{query}': {sc_err}")
                return []

        if not data:
            return []

        entries = data.get("entries") if "entries" in data else [data]
        results = []
        for entry in entries:
            if not entry:
                continue
            # Skip entries tagged as DRM protected
            if entry.get("has_drm"):
                continue
            results.append({
                "title": entry.get("title", "Unknown Track"),
                "url": entry.get("webpage_url") or entry.get("url", ""),
                "duration": int(entry.get("duration", 0) or 0),
                "artist": entry.get("uploader") or entry.get("channel", "Unknown Artist"),
                "thumbnail": entry.get("thumbnail"),
                "id": entry.get("id"),
            })
            if len(results) >= limit:
                break

        cls._search_cache[cache_key] = results
        return results

    @classmethod
    async def resolve_spotify_metadata(cls, spotify_url: str) -> Optional[Dict[str, Any]]:
        """
        Extract title, artist, thumbnail, and metadata from Spotify URLs or URIs.
        Prioritizes official Spotify Web API (Client Credentials Flow) with automatic
        fallback to open oEmbed parser without requiring developer tokens.
        """
        from music_bot.services.spotify_service import SpotifyItemType, SpotifyService, SpotifyTrack, SpotifyCollection

        try:
            res = await SpotifyService.resolve_url(spotify_url)
            if res:
                if isinstance(res, SpotifyTrack):
                    return res.to_dict()
                elif isinstance(res, SpotifyCollection):
                    d = res.to_dict()
                    # Add single track search query from first item or title
                    first_track = res.tracks[0] if res.tracks else None
                    d["title"] = res.title
                    d["artist"] = res.author_or_artist
                    d["search_query"] = first_track.search_query if first_track else f"{res.title} {res.author_or_artist}"
                    return d
        except Exception as e:
            logger.warning(f"[Resolver] SpotifyService resolution error for '{spotify_url}': {e}")

        # Direct fallback to open oEmbed
        try:
            fb = await SpotifyService.resolve_via_oembed(spotify_url)
            if fb:
                return fb.to_dict()
        except Exception as fb_err:
            logger.warning(f"[Resolver] Fallback oEmbed failed for '{spotify_url}': {fb_err}")

        return None

    @classmethod
    async def resolve_spotify_collection(
        cls, spotify_url: str, limit: int = 100
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve Spotify albums or playlists into a collection with track metadata.
        """
        from music_bot.services.spotify_service import SpotifyItemType, SpotifyService, SpotifyCollection
        parsed = SpotifyService.match_spotify_link(spotify_url)
        if not parsed:
            return None
        item_type, item_id = parsed
        if item_type == SpotifyItemType.ALBUM:
            col = await SpotifyService.get_album(item_id, limit=limit)
            return col.to_dict() if col else None
        elif item_type == SpotifyItemType.PLAYLIST:
            col = await SpotifyService.get_playlist(item_id, limit=limit)
            return col.to_dict() if col else None
        return None

    @classmethod
    async def resolve_track(
        cls, query_or_url: str, requester_id: int, requester_name: str
    ) -> Optional[QueuedTrack]:
        """Resolve a query or direct link into a playable QueuedTrack with multi-source fallback."""
        start_t = time.time()
        loop = asyncio.get_running_loop()

        spotify_info = None
        cleaned_query = query_or_url
        is_spotify = "spotify.com" in query_or_url or query_or_url.startswith("spotify:")
        if is_spotify:
            spotify_info = await cls.resolve_spotify_metadata(query_or_url)
            if spotify_info:
                cleaned_query = spotify_info.get("search_query", query_or_url)
                logger.info(f"[Resolver] Resolved Spotify metadata: '{spotify_info.get('title')}' by '{spotify_info.get('artist')}'")
        elif "apple.com" in query_or_url:
            cleaned_query = query_or_url.split("/")[-1].split("?")[0].replace("-", " ")

        target = cleaned_query if (cleaned_query.startswith("http") and not is_spotify) else f"ytsearch1:{cleaned_query}"

        def _apply_metadata_enhancements(t: Optional[QueuedTrack]) -> Optional[QueuedTrack]:
            if t and spotify_info:
                if spotify_info.get("title"):
                    t.title = spotify_info["title"]
                if spotify_info.get("artist") and spotify_info["artist"] != "Unknown Artist":
                    t.artist = spotify_info["artist"]
                if spotify_info.get("thumbnail"):
                    t.thumbnail = spotify_info["thumbnail"]
                if spotify_info.get("url"):
                    t.url = spotify_info["url"]
                elif query_or_url.startswith("http"):
                    t.url = query_or_url
            return t

        # Strategy 1: Primary extraction with modern mobile/embedded client list
        cls.last_resolver_error = None
        try:
            data = await asyncio.wait_for(
                loop.run_in_executor(
                    _audio_executor, functools.partial(_ytdl.extract_info, target, download=False)
                ),
                timeout=12.0,
            )
            track = cls._parse_entry(data, requester_id, requester_name)
            if track:
                track = _apply_metadata_enhancements(track)
                dur = time.time() - start_t
                logger.info(f"[Resolver] Primary resolver resolved '{cleaned_query[:60]}' in {dur:.2f}s -> '{track.title}'")
                return track
        except Exception as yt_err:
            cls.last_resolver_error = str(yt_err)
            logger.warning(f"Primary resolver failed for '{cleaned_query}': {yt_err}. Trying secondary fallback...")

        # Strategy 2: Fallback with mobile/ios profile
        try:
            fallback_opts = _build_ytdl_options(["ios", "mweb"])
            fallback_ytdl = yt_dlp.YoutubeDL(fallback_opts)
            data = await asyncio.wait_for(
                loop.run_in_executor(
                    _audio_executor, functools.partial(fallback_ytdl.extract_info, target, download=False)
                ),
                timeout=10.0,
            )
            track = cls._parse_entry(data, requester_id, requester_name)
            if track:
                track = _apply_metadata_enhancements(track)
                dur = time.time() - start_t
                logger.info(f"[Resolver] Secondary profile resolved '{cleaned_query[:60]}' in {dur:.2f}s -> '{track.title}'")
                return track
        except Exception as fb_err:
            cls.last_resolver_error = str(fb_err)
            logger.warning(f"Secondary profile failed for '{cleaned_query}': {fb_err}")

        # Strategy 3: Multi-Source Failover to SoundCloud if it's a search query or Spotify link
        if not cleaned_query.startswith("http") or spotify_info is not None:
            try:
                sc_target = f"scsearch3:{cleaned_query}"
                logger.info(f"Failing over to SoundCloud for '{cleaned_query}'...")
                sc_opts = {
                    "format": "bestaudio/best",
                    "noplaylist": True,
                    "quiet": True,
                    "socket_timeout": 8,
                    "nocheckcertificate": True,
                }
                sc_ytdl = yt_dlp.YoutubeDL(sc_opts)
                data = await asyncio.wait_for(
                    loop.run_in_executor(
                        _audio_executor, functools.partial(sc_ytdl.extract_info, sc_target, download=False)
                    ),
                    timeout=10.0,
                )
                if data:
                    entries = data.get("entries") if "entries" in data else [data]
                    for entry in entries:
                        if not entry:
                            continue
                        track = cls._parse_entry(entry, requester_id, requester_name)
                        if track and track.stream_url:
                            track = _apply_metadata_enhancements(track)
                            dur = time.time() - start_t
                            logger.info(f"[Resolver] Successfully recovered track from SoundCloud in {dur:.2f}s: {track.title}")
                            return track
            except Exception as sc_err:
                cls.last_resolver_error = f"YouTube and SoundCloud both failed: {sc_err}"
                logger.error(f"SoundCloud fallback failed for '{cleaned_query}': {sc_err}")

        dur = time.time() - start_t
        logger.warning(f"[Resolver] Track resolution completely exhausted for '{cleaned_query}' in {dur:.2f}s")
        return None
