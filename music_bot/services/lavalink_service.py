"""
Modular Lavalink Audio Service for MusicMaid (Conditional / Config-Flagged).
Enables offloading audio streaming to a dedicated Lavalink v4 node when LAVALINK_ENABLED=true.
Gracefully falls back to the native yt-dlp + FFmpeg engine if Lavalink is disabled, unavailable,
or if wavelink is not installed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from music_bot.config import (
    LAVALINK_ENABLED,
    LAVALINK_HOST,
    LAVALINK_PASSWORD,
    LAVALINK_PORT,
)

if TYPE_CHECKING:
    from music_bot.bot import RaiMusicBot
    from music_bot.services.session_service import GuildMusicSession

logger = logging.getLogger("RaiMusic.Lavalink")

try:
    import wavelink  # type: ignore
    WAVELINK_AVAILABLE = True
except ImportError:
    wavelink = None  # type: ignore
    WAVELINK_AVAILABLE = False


class LavalinkManager:
    """Manages optional connection to remote/external Lavalink audio nodes."""

    _initialized: bool = False
    _connected: bool = False
    _node: Any = None

    @classmethod
    def is_enabled(cls) -> bool:
        """True if LAVALINK_ENABLED=true in config and wavelink is available."""
        return bool(LAVALINK_ENABLED and WAVELINK_AVAILABLE)

    @classmethod
    def is_connected(cls) -> bool:
        """True if Lavalink node is active and connected."""
        return bool(cls._connected and cls._node is not None)

    @classmethod
    async def setup_node(cls, bot: RaiMusicBot) -> bool:
        """
        Connect to external Lavalink node if enabled.
        Returns True if connected successfully, False otherwise.
        """
        if not LAVALINK_ENABLED:
            logger.info("[Lavalink] LAVALINK_ENABLED=false. Native yt-dlp + FFmpeg engine active.")
            return False

        if not WAVELINK_AVAILABLE:
            logger.warning(
                "[Lavalink] LAVALINK_ENABLED=true but 'wavelink' is not installed in Python environment. "
                "Falling back to native yt-dlp + FFmpeg. Run `pip install wavelink` to enable Lavalink."
            )
            return False

        try:
            logger.info(f"[Lavalink] Attempting connection to Lavalink node at {LAVALINK_HOST}:{LAVALINK_PORT}...")
            node = wavelink.Node(
                uri=f"http://{LAVALINK_HOST}:{LAVALINK_PORT}",
                password=LAVALINK_PASSWORD,
            )
            await wavelink.Pool.connect(nodes=[node], client=bot, cache_capacity=100)
            cls._node = node
            cls._connected = True
            cls._initialized = True
            logger.info(f"[Lavalink] Successfully connected to Lavalink node ({LAVALINK_HOST}:{LAVALINK_PORT})! 🚀")
            return True
        except Exception as e:
            cls._connected = False
            logger.warning(
                f"[Lavalink] Connection failed to {LAVALINK_HOST}:{LAVALINK_PORT}: {e}. "
                f"Falling back safely to native yt-dlp + FFmpeg."
            )
            return False

    @classmethod
    async def resolve_tracks(cls, query: str) -> List[Any]:
        """Search and resolve tracks via Lavalink Node if connected."""
        if not cls.is_connected() or not wavelink:
            return []
        try:
            tracks: List[Any] = await wavelink.Playable.search(query)
            return tracks or []
        except Exception as e:
            logger.warning(f"[Lavalink] Search failed for '{query}': {e}")
            return []

    @classmethod
    def get_diagnostics(cls) -> Dict[str, Any]:
        """Diagnostic state of Lavalink service."""
        return {
            "enabled_by_config": bool(LAVALINK_ENABLED),
            "wavelink_installed": WAVELINK_AVAILABLE,
            "connected": cls._connected,
            "host": LAVALINK_HOST if LAVALINK_ENABLED else "N/A",
            "port": LAVALINK_PORT if LAVALINK_ENABLED else "N/A",
            "active_engine": "Lavalink" if cls.is_connected() else "Native yt-dlp + FFmpeg",
        }
