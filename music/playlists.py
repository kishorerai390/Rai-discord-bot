"""
Saved Playlists and SQLite Storage Adapter for Rai Music.
Provides personal and guild playlist creation, queue import, and export.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from core.bot import SentinelBot
    from music.queue import Track

logger = logging.getLogger("Rai.Playlists")


class PlaylistManager:
    def __init__(self, bot: SentinelBot):
        self.bot = bot

    async def save_queue_as_playlist(
        self,
        guild_id: int,
        user_id: int,
        name: str,
        tracks: List[Track],
    ) -> bool:
        """Saves current queue to database."""
        tracks_data = [t.to_dict() for t in tracks]
        return await self.bot.db.create_music_playlist(
            guild_id=guild_id,
            user_id=user_id,
            name=name.strip()[:50],
            tracks=tracks_data,
        )

    async def get_playlist(self, guild_id: int, user_id: int, name: str):
        return await self.bot.db.get_music_playlist(guild_id, user_id, name.strip())

    async def list_playlists(self, guild_id: int, user_id: int):
        return await self.bot.db.list_music_playlists(guild_id, user_id)
