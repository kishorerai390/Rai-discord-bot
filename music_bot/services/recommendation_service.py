"""
Smart Music Recommendations Engine for Neko Songs.
Supports 8 distinct exploration and contextual modes powered by track metadata.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import discord

from music_bot.database.models import QueuedTrack
from music_bot.services.resolver_service import AudioResolver
from music_bot.services.session_service import GuildMusicSession

logger = logging.getLogger("RaiMusic.Recommendations")

RECOMMENDATION_MODES: Dict[str, Dict[str, str]] = {
    "similar_tracks": {
        "label": "Similar Tracks",
        "query_suffix": "similar songs",
        "description": "Finds songs that sound similar to the current track",
    },
    "similar_artists": {
        "label": "Similar Artists",
        "query_suffix": "songs by similar artists",
        "description": "Discovers related artists with matching styles",
    },
    "genre": {
        "label": "Same Genre",
        "query_suffix": "genre mix",
        "description": "Explores more tracks within the same musical genre",
    },
    "discover": {
        "label": "Discover Something New",
        "query_suffix": "indie fresh releases",
        "description": "Branch out with fresh, curated discoveries",
    },
    "chill": {
        "label": "Chill & Relax",
        "query_suffix": "lofi chill relax beats",
        "description": "Mellow, downtempo tracks perfect for unwinding",
    },
    "gaming": {
        "label": "Gaming Focus",
        "query_suffix": "synthwave gaming electro hype",
        "description": "High-energy tracks crafted for competitive sessions",
    },
    "party": {
        "label": "Party Vibes",
        "query_suffix": "party dance hits",
        "description": "Upbeat club and party rhythms",
    },
    "night": {
        "label": "Night Listening",
        "query_suffix": "midnight slow vibes",
        "description": "Late-night ambient and contemplative sounds",
    },
}


class MusicRecommendationService:
    """Coordinates metadata queries and contextual track searches."""

    @classmethod
    async def get_mode_recommendations(
        cls, session: GuildMusicSession, mode: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Fetch candidates based on selected mode and current session history."""
        mode_info = RECOMMENDATION_MODES.get(mode, RECOMMENDATION_MODES["similar_tracks"])

        current_track = session.current_track
        if not current_track and session.history:
            current_track = session.history[-1]

        if mode in ("similar_tracks", "similar_artists", "genre") and current_track:
            artist = current_track.artist if current_track.artist != "Unknown Artist" else ""
            query = f"{artist} {current_track.title} {mode_info['query_suffix']}".strip()
        elif current_track and mode in ("chill", "gaming", "party", "night"):
            query = f"{current_track.artist} {mode_info['query_suffix']}".strip()
        else:
            query = f"{mode_info['label']} {mode_info['query_suffix']}"

        try:
            return await AudioResolver.search(query, limit=limit)
        except Exception as e:
            logger.warning(f"Recommendation search failed for query '{query}': {e}")
            return []
