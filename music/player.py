"""
Rythm-Style Guild Audio Player with Mutex Protection and Error Isolation.
Guarantees thread-safe queue mutations, idle timeouts, and automatic error skipping.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional
import discord

from music.queue import BoundedMusicQueue, Track
from music.source import AudioSourceResolver
from music.isolation import MusicIsolationManager

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.GuildMusicPlayer")


class GuildMusicPlayer:
    """Manages audio playback, queue state, and voice connections for a single Guild."""

    def __init__(self, bot: SentinelBot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue = BoundedMusicQueue(max_size=200)
        self.current: Optional[Track] = None
        self.volume: float = 0.5
        self.autoplay: bool = False
        self.panel_message: Optional[discord.Message] = None
        self.inactivity_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    @property
    def voice_client(self) -> Optional[discord.VoiceClient]:
        return self.guild.voice_client

    def play_next(self, error: Optional[Exception] = None) -> None:
        """Called by discord.VoiceClient when audio stream finishes or encounters an error."""
        if error:
            logger.warning(f"Audio stream error in {self.guild.name}: {error}")
            try:
                from utils.owner_reporter import OwnerReporter
                OwnerReporter.send_music_report(
                    self.bot,
                    self.guild.id,
                    event="Playback Stream Error Recovered",
                    reason=str(error)[:150],
                    action_taken="Skipping to next track; player isolated",
                    severity="WARNING",
                    details={"Track": self.current.title if self.current else "Unknown"},
                )
            except Exception:
                pass

        if not self.voice_client or not self.voice_client.is_connected():
            return

        asyncio.run_coroutine_threadsafe(self._process_next(), self.bot.loop)

    @MusicIsolationManager.guard("process_next_track")
    async def _process_next(self) -> None:
        """Thread-safe queue advancement."""
        async with self._lock:
            next_track = await self.queue.pop_next(self.current)

            # Handle Autoplay if queue empty
            if not next_track and self.autoplay and self.current:
                try:
                    query = f"{self.current.artist} official audio"
                    candidates = await AudioSourceResolver.search_candidates(query, self.current.requester, limit=2)
                    for c in candidates:
                        if c.title != self.current.title:
                            next_track = c
                            break
                except Exception as e:
                    logger.debug(f"Autoplay resolution note: {e}")

            if not next_track:
                self.current = None
                self._schedule_inactivity(timeout=180)
                return

            self._cancel_inactivity()
            self.current = next_track

            try:
                source = AudioSourceResolver.create_audio_source(next_track.stream_url, volume=self.volume)
                self.voice_client.play(source, after=self.play_next)
                logger.info(f"Now playing in {self.guild.name}: {next_track.title}")
            except Exception as exc:
                logger.error(f"Failed to play source in {self.guild.name}: {exc}")
                # Recursively advance to next track safely without hanging
                self.play_next(error=exc)

    def _schedule_inactivity(self, timeout: int = 180) -> None:
        self._cancel_inactivity()
        self.inactivity_task = asyncio.create_task(self._inactivity_countdown(timeout))

    def _cancel_inactivity(self) -> None:
        if self.inactivity_task and not self.inactivity_task.done():
            self.inactivity_task.cancel()
        self.inactivity_task = None

    async def _inactivity_countdown(self, timeout: int) -> None:
        try:
            await asyncio.sleep(timeout)
            if self.voice_client and self.voice_client.is_connected() and not self.voice_client.is_playing():
                logger.info(f"Disconnecting idle voice client in {self.guild.name} (timeout: {timeout}s)")
                await self.voice_client.disconnect(force=True)
                await self.queue.clear()
                self.current = None
        except asyncio.CancelledError:
            pass
