"""
Audius and Jamendo Legal Catalog & Audio Provider Services for MusicMaid.

1. Audius:
   - Uses Audius Discovery Node REST API (v1).
   - Allows searching public tracks and streaming authorized community/independent music.
   - Streams live 320kbps MP3s from Audius discovery/content nodes.

2. Jamendo:
   - Uses Jamendo v3.0 REST API for CC/licensed music catalog.
   - Searches tracks and streams authorized audio.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from music_bot.services.network_security import validate_safe_url

logger = logging.getLogger("MusicMaid.AlternativeProviders")

AUDIUS_APP_NAME = os.getenv("AUDIUS_APP_NAME", "MusicMaidBot")
AUDIUS_DISCOVERY_NODE = os.getenv("AUDIUS_DISCOVERY_NODE", "https://api.audius.co")

JAMENDO_CLIENT_ID = os.getenv("JAMENDO_CLIENT_ID", "56d30c95")  # Default open developer key or configurable


class AudiusProviderService:
    """Audius independent music search and stream resolution service."""

    _search_cache: Dict[str, Tuple[List[Dict[str, Any]], float]] = {}

    @classmethod
    async def search(cls, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search Audius catalog for tracks matching query."""
        if not query or not query.strip():
            return []

        cache_key = f"audius:{limit}:{query.strip().lower()}"
        now = asyncio.get_running_loop().time()
        if cache_key in cls._search_cache:
            data, exp = cls._search_cache[cache_key]
            if now < exp:
                return data

        encoded_q = urllib.parse.quote(query.strip())
        req_url = f"{AUDIUS_DISCOVERY_NODE}/v1/tracks/search?query={encoded_q}&app_name={urllib.parse.quote(AUDIUS_APP_NAME)}"

        is_safe, err, _ = validate_safe_url(req_url)
        if not is_safe:
            logger.warning(f"[Audius] Request URL rejected by security validator: {err}")
            return []

        def _fetch() -> Optional[Dict[str, Any]]:
            req = urllib.request.Request(
                req_url,
                headers={"User-Agent": "MusicMaid/2.7 (Discord Bot; Lossless Audio Engine)"},
            )
            try:
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status == 200:
                        raw = resp.read().decode("utf-8")
                        return json.loads(raw)
            except Exception as e:
                logger.debug(f"[Audius] Search error for query '{query}': {e}")
                return None
            return None

        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, _fetch)
        if not res or not res.get("data"):
            return []

        tracks: List[Dict[str, Any]] = []
        for item in res["data"][:limit]:
            if not item:
                continue
            track_id = item.get("id")
            if not track_id:
                continue

            user_obj = item.get("user") or {}
            artist = user_obj.get("name") or user_obj.get("handle") or "Unknown Artist"
            title = item.get("title") or "Unknown Track"
            dur = int(item.get("duration") or 0)
            thumb = None
            art_obj = item.get("artwork") or {}
            if isinstance(art_obj, dict):
                thumb = art_obj.get("480x480") or art_obj.get("150x150")

            web_url = f"https://audius.co{item.get('permalink')}" if item.get("permalink") else f"https://audius.co/tracks/{track_id}"
            stream_url = f"{AUDIUS_DISCOVERY_NODE}/v1/tracks/{track_id}/stream?app_name={urllib.parse.quote(AUDIUS_APP_NAME)}"

            tracks.append({
                "id": str(track_id),
                "title": title,
                "artist": artist,
                "duration": dur,
                "url": web_url,
                "stream_url": stream_url,
                "thumbnail": thumb,
                "provider": "audius",
            })

        cls._search_cache[cache_key] = (tracks, now + 1800.0)
        return tracks


class JamendoProviderService:
    """Jamendo licensed catalog search and audio streaming service."""

    _search_cache: Dict[str, Tuple[List[Dict[str, Any]], float]] = {}

    @classmethod
    async def search(cls, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search Jamendo catalog for CC/licensed tracks matching query."""
        if not query or not query.strip():
            return []

        cache_key = f"jamendo:{limit}:{query.strip().lower()}"
        now = asyncio.get_running_loop().time()
        if cache_key in cls._search_cache:
            data, exp = cls._search_cache[cache_key]
            if now < exp:
                return data

        encoded_q = urllib.parse.quote(query.strip())
        client_id = JAMENDO_CLIENT_ID or "56d30c95"
        req_url = (
            f"https://api.jamendo.com/v3.0/tracks/?client_id={urllib.parse.quote(client_id)}"
            f"&format=json&search={encoded_q}&limit={limit}&audioformat=mp32"
        )

        is_safe, err, _ = validate_safe_url(req_url)
        if not is_safe:
            logger.warning(f"[Jamendo] Request URL rejected by security validator: {err}")
            return []

        def _fetch() -> Optional[Dict[str, Any]]:
            req = urllib.request.Request(
                req_url,
                headers={"User-Agent": "MusicMaid/2.7 (Discord Bot; Lossless Audio Engine)"},
            )
            try:
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status == 200:
                        raw = resp.read().decode("utf-8")
                        return json.loads(raw)
            except Exception as e:
                logger.debug(f"[Jamendo] Search error for query '{query}': {e}")
                return None
            return None

        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, _fetch)
        if not res or not res.get("results"):
            return []

        tracks: List[Dict[str, Any]] = []
        for item in res["results"][:limit]:
            if not item:
                continue
            track_id = item.get("id")
            stream_url = item.get("audio")
            if not track_id or not stream_url:
                continue

            title = item.get("name") or "Unknown Track"
            artist = item.get("artist_name") or "Jamendo Artist"
            dur = int(item.get("duration") or 0)
            thumb = item.get("image") or item.get("album_image")
            web_url = item.get("shareurl") or f"https://www.jamendo.com/track/{track_id}"

            tracks.append({
                "id": str(track_id),
                "title": title,
                "artist": artist,
                "duration": dur,
                "url": web_url,
                "stream_url": stream_url,
                "thumbnail": thumb,
                "provider": "jamendo",
            })

        cls._search_cache[cache_key] = (tracks, now + 1800.0)
        return tracks
