"""
Thread-Safe Bounded Music Queue System for Rai.
Implements:
- Memory leak protection via bounded queue limits (max 200 tracks)
- Mutex lock protection (`asyncio.Lock`) for concurrent additions
- Track loop, Queue loop, History (previous track), and Shuffle
- Serializable state for graceful restart and crash recovery
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional
import discord

logger = logging.getLogger("Rai.MusicQueue")


class Track:
    """Represents a playable audio track with metadata."""

    def __init__(
        self,
        title: str,
        url: str,
        stream_url: str,
        duration: int,
        requester: discord.Member,
        artist: str = "Unknown Artist",
        thumbnail: Optional[str] = None,
    ):
        self.title = title
        self.url = url
        self.stream_url = stream_url
        self.duration = duration
        self.requester = requester
        self.artist = artist
        self.thumbnail = thumbnail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "stream_url": self.stream_url,
            "duration": self.duration,
            "artist": self.artist,
            "thumbnail": self.thumbnail,
            "requester_id": self.requester.id if hasattr(self.requester, "id") else 0,
            "requester_name": getattr(self.requester, "display_name", "Unknown"),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], requester: discord.Member) -> "Track":
        return cls(
            title=data.get("title", "Unknown Title"),
            url=data.get("url", ""),
            stream_url=data.get("stream_url", ""),
            duration=data.get("duration", 0),
            requester=requester,
            artist=data.get("artist", "Unknown Artist"),
            thumbnail=data.get("thumbnail"),
        )


class BoundedMusicQueue:
    """Thread-safe, memory-bounded audio queue."""

    def __init__(self, max_size: int = 200):
        self.max_size = max_size
        self._tracks: List[Track] = []
        self._history: List[Track] = []
        self.loop_mode: str = "off"  # "off", "track", "queue"
        self._lock = asyncio.Lock()

    def __len__(self) -> int:
        return len(self._tracks)

    @property
    def tracks(self) -> List[Track]:
        return list(self._tracks)

    @property
    def history(self) -> List[Track]:
        return list(self._history)

    async def add(self, track: Track) -> bool:
        """Adds a track to the queue if within bounds."""
        async with self._lock:
            if len(self._tracks) >= self.max_size:
                logger.warning(f"Queue capacity limit reached ({self.max_size}). Dropping overflow.")
                return False
            self._tracks.append(track)
            return True

    async def add_multiple(self, tracks: List[Track]) -> int:
        """Adds tracks up to maximum size limit."""
        async with self._lock:
            available_slots = max(0, self.max_size - len(self._tracks))
            to_add = tracks[:available_slots]
            self._tracks.extend(to_add)
            return len(to_add)

    async def pop_next(self, current: Optional[Track] = None) -> Optional[Track]:
        """Pops the next track respecting loop mode."""
        async with self._lock:
            if current:
                self._history.append(current)
                if len(self._history) > 25:
                    self._history.pop(0)

                if self.loop_mode == "track":
                    return current
                elif self.loop_mode == "queue":
                    self._tracks.append(current)

            if not self._tracks:
                return None
            return self._tracks.pop(0)

    async def pop_previous(self, current: Optional[Track] = None) -> Optional[Track]:
        """Pops and replays the previous track in history."""
        async with self._lock:
            if not self._history:
                return None
            prev = self._history.pop()
            if current:
                self._tracks.insert(0, current)
            return prev

    async def remove_at(self, index: int) -> Optional[Track]:
        """Removes a track at specific 1-indexed position."""
        async with self._lock:
            idx = index - 1
            if 0 <= idx < len(self._tracks):
                return self._tracks.pop(idx)
            return None

    async def shuffle(self) -> bool:
        async with self._lock:
            if len(self._tracks) < 2:
                return False
            random.shuffle(self._tracks)
            return True

    async def clear(self) -> None:
        async with self._lock:
            self._tracks.clear()

    def serialize_state(self) -> Dict[str, Any]:
        """Exports snapshot of queue for crash recovery."""
        return {
            "tracks": [t.to_dict() for t in self._tracks[:50]],
            "loop_mode": self.loop_mode,
        }
