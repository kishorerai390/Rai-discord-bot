"""
RAI Music Queue Service.
Manages thread-safe bounded track queue, history preservation, repeat modes, and shuffle.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional

import discord

from music.provider import ResolvedTrack

logger = logging.getLogger("Rai.MusicQueueService")


class MusicQueueService:
    """Thread-safe bounded audio track queue and history manager."""

    def __init__(self, max_size: int = 200):
        self.max_size = max_size
        self._tracks: List[ResolvedTrack] = []
        self._history: List[ResolvedTrack] = []
        self.loop_mode: str = "off"  # "off", "track", "queue"
        self._lock = asyncio.Lock()

    def __len__(self) -> int:
        return len(self._tracks)

    @property
    def tracks(self) -> List[ResolvedTrack]:
        return list(self._tracks)

    @property
    def history(self) -> List[ResolvedTrack]:
        return list(self._history)

    async def add(self, track: ResolvedTrack) -> bool:
        """Adds a verified playable track to the queue if within bounds."""
        if not track.stream_url:
            logger.warning(f"Refusing to enqueue track without playable stream: {track.title}")
            return False

        async with self._lock:
            if len(self._tracks) >= self.max_size:
                logger.warning(f"Queue capacity limit reached ({self.max_size}). Dropping overflow track.")
                return False
            self._tracks.append(track)
            return True

    async def add_multiple(self, tracks: List[ResolvedTrack]) -> int:
        """Enqueues verified tracks up to max limit."""
        valid_tracks = [t for t in tracks if t.stream_url]
        async with self._lock:
            available_slots = max(0, self.max_size - len(self._tracks))
            to_add = valid_tracks[:available_slots]
            self._tracks.extend(to_add)
            return len(to_add)

    async def pop_next(self, current: Optional[ResolvedTrack] = None) -> Optional[ResolvedTrack]:
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

    async def pop_previous(self, current: Optional[ResolvedTrack] = None) -> Optional[ResolvedTrack]:
        """Replays the previous track in history."""
        async with self._lock:
            if not self._history:
                return None
            prev = self._history.pop()
            if current:
                self._tracks.insert(0, current)
            return prev

    async def remove_at(self, index: int) -> Optional[ResolvedTrack]:
        """Removes a track at specific 1-indexed position."""
        async with self._lock:
            idx = index - 1
            if 0 <= idx < len(self._tracks):
                return self._tracks.pop(idx)
            return None

    async def shuffle(self) -> bool:
        """Shuffles remaining tracks in the queue."""
        async with self._lock:
            if len(self._tracks) < 2:
                return False
            random.shuffle(self._tracks)
            return True

    async def clear(self) -> None:
        """Clears all upcoming tracks."""
        async with self._lock:
            self._tracks.clear()
