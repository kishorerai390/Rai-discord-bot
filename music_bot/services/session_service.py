"""
Guild Music Session & State Machine Engine for Rai Music Bot.
Provides absolute concurrency serialization and session isolation per guild.
"""

from __future__ import annotations

import asyncio
from collections import deque
from enum import Enum
import logging
import math
import random
import time
from typing import Any, Callable, Dict, List, Optional
import uuid
import discord

from music_bot.database.models import QueuedTrack

logger = logging.getLogger("RaiMusic.Session")


class PlaybackState(str, Enum):
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    SEARCHING = "SEARCHING"
    RESOLVING = "RESOLVING"
    LOADING = "LOADING"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    DISCONNECTED = "DISCONNECTED"
    RECOVERING = "RECOVERING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class LoopMode(str, Enum):
    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"


class GuildMusicSession:
    """Isolated session handling music playback for a single guild."""

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.session_id: str = f"sess_{uuid.uuid4().hex[:12]}"
        self.session_name: str = "Active Session"
        self.state: PlaybackState = PlaybackState.IDLE
        self.lock = asyncio.Lock()  # Per-guild operation serializer

        self.voice_client: Optional[discord.VoiceClient] = None
        self.text_channel: Optional[discord.TextChannel] = None

        self.current_track: Optional[QueuedTrack] = None
        self.queue: deque[QueuedTrack] = deque()
        self.history: List[QueuedTrack] = []

        self.volume: int = 80
        self.loop_mode: LoopMode = LoopMode.OFF
        self.autoplay: bool = False
        self.twenty_four_seven: bool = False
        self.dj_enabled: bool = False
        self.radio_station: Optional[str] = None
        self.eq_preset: str = "Flat"
        self.ducking_enabled: bool = True
        self.skip_votes: set[int] = set()

        self.track_start_time: float = 0.0
        self.pause_time: float = 0.0
        self.paused_duration: float = 0.0

        self.auto_leave_task: Optional[asyncio.Task] = None
        self.sleep_timer_task: Optional[asyncio.Task] = None
        self.sleep_timer_end: float = 0.0
        self.audio_filter: str = ""
        self.now_playing_message: Optional[discord.Message] = None
        self.progress_updater_task: Optional[asyncio.Task] = None
        self._is_seeking: bool = False
        self._is_reencoding: bool = False
        self._is_skipping: bool = False
        self.recent_skipped_urls: set[str] = set()
        self.playback_generation: int = 0
        self.is_intentional_stop: bool = False
        self.last_checkpoint_pos: int = 0
        self.last_checkpoint_time: float = 0.0
        self.recovery_attempts: int = 0
        self.recovery_status: Optional[str] = None

    @property
    def has_active_track(self) -> bool:
        """True if there is an active, paused, buffering, or recoverable track."""
        return self.current_track is not None and self.state in (
            PlaybackState.PLAYING,
            PlaybackState.PAUSED,
            PlaybackState.LOADING,
            PlaybackState.SEARCHING,
            PlaybackState.RESOLVING,
            PlaybackState.RECOVERING,
        )

    @property
    def is_playing(self) -> bool:
        return self.state == PlaybackState.PLAYING and self.voice_client is not None and self.voice_client.is_playing()

    @property
    def is_paused(self) -> bool:
        return self.state == PlaybackState.PAUSED or (self.voice_client is not None and self.voice_client.is_paused())

    @property
    def is_active(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_connected()

    @property
    def elapsed_seconds(self) -> int:
        """Calculate track playback elapsed time in seconds."""
        if self.track_start_time == 0.0:
            return 0
        if self.is_paused and self.pause_time > 0:
            current_elapsed = self.pause_time - self.track_start_time - self.paused_duration
        else:
            current_elapsed = time.time() - self.track_start_time - self.paused_duration
        return max(0, int(current_elapsed))

    @property
    def progress_seconds(self) -> int:
        """Alias for elapsed_seconds providing uniform interface for progress tracking."""
        return self.elapsed_seconds

    @progress_seconds.setter
    def progress_seconds(self, value: int) -> None:
        self.track_start_time = time.time() - max(0, value)
        self.paused_duration = 0.0

    def reset(self) -> None:
        """Reset player state without clearing queue/history."""
        if self.progress_updater_task and not self.progress_updater_task.done():
            self.progress_updater_task.cancel()
            self.progress_updater_task = None
        self.state = PlaybackState.IDLE
        self.current_track = None
        self.track_start_time = 0.0
        self.pause_time = 0.0
        self.paused_duration = 0.0
        self.skip_votes.clear()
        self.recovery_status = None
        self.is_intentional_stop = True


class SessionManager:
    """Singleton session registry managing independent sessions across guilds."""

    _instance: Optional[SessionManager] = None

    def __init__(self):
        self._sessions: Dict[int, GuildMusicSession] = {}
        self._global_lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> SessionManager:
        if cls._instance is None:
            cls._instance = SessionManager()
        return cls._instance

    async def get_session(self, guild_id: int) -> GuildMusicSession:
        """Retrieve existing session or instantiate a new one."""
        async with self._global_lock:
            if guild_id not in self._sessions:
                self._sessions[guild_id] = GuildMusicSession(guild_id)
            return self._sessions[guild_id]

    def get_session_sync(self, guild_id: int) -> GuildMusicSession:
        """Synchronously retrieve existing session or instantiate new session."""
        if guild_id not in self._sessions:
            self._sessions[guild_id] = GuildMusicSession(guild_id)
        return self._sessions[guild_id]

    def get_session_nowait(self, guild_id: int) -> GuildMusicSession:
        """Synchronously retrieve existing session or instantiate new session without blocking."""
        return self.get_session_sync(guild_id)

    async def remove_session(self, guild_id: int) -> None:
        """Remove and cleanup guild session."""
        async with self._global_lock:
            session = self._sessions.pop(guild_id, None)
            if session and session.auto_leave_task and not session.auto_leave_task.done():
                session.auto_leave_task.cancel()

    def get_active_sessions_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.is_active)

    def get_playing_sessions_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.is_playing)

    def get_all_sessions(self) -> List[GuildMusicSession]:
        return list(self._sessions.values())
