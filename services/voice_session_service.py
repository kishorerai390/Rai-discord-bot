"""
RAI — VOICE SESSION SERVICE & VOICE SESSION MANAGER.
Coordinates voice connections, preventing collisions between Music playback and Soundboard audio.
Supports controlled state transitions: IDLE, MUSIC, SOUNDBOARD, MUSIC_WITH_EFFECTS, and clean pause/resume ducking.
Tracks connection states: DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING, DISCONNECTING, ERROR.
Ensures one voice connection per guild, safe reconnects, zombie connection elimination, and failure isolation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional, Set, Tuple

import discord

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.VoiceSessionService")


class AudioSessionMode(str, Enum):
    IDLE = "IDLE"
    MUSIC = "MUSIC"
    SOUNDBOARD = "SOUNDBOARD"
    MUSIC_WITH_EFFECTS = "MUSIC_WITH_EFFECTS"


class VoiceConnectionState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    DISCONNECTING = "DISCONNECTING"
    ERROR = "ERROR"


class GuildAudioSession:
    """Tracks state of audio and voice connection for a specific guild."""

    def __init__(self, guild_id: int):
        self.guild_id: int = guild_id
        self.voice_channel_id: Optional[int] = None
        self.connection: Optional[discord.VoiceClient] = None
        self._mode: AudioSessionMode = AudioSessionMode.IDLE
        self.connection_state: VoiceConnectionState = VoiceConnectionState.DISCONNECTED
        self.music_session: Optional[Any] = None
        self.soundboard_session: Optional[Any] = None
        self.active_users: Set[int] = set()
        self.last_activity: float = time.time()
        self.was_playing_music: bool = False
        self.active_sound_id: Optional[str] = None
        self.requester_id: Optional[int] = None
        self.lock = asyncio.Lock()

    @property
    def mode(self) -> AudioSessionMode:
        return self._mode

    @mode.setter
    def mode(self, val: AudioSessionMode) -> None:
        self._mode = val

    @property
    def current_mode(self) -> AudioSessionMode:
        return self._mode

    @current_mode.setter
    def current_mode(self, val: AudioSessionMode) -> None:
        self._mode = val


class VoiceSessionService:
    """
    Central coordinator for Discord voice connections.
    Enforces the single-voice-connection rule per guild while allowing clean
    coexistence between Music, Soundboard effects, and Dynamic VC rooms.
    """

    _instance: Optional[VoiceSessionService] = None

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._sessions: Dict[int, GuildAudioSession] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls, bot: Optional[SentinelBot] = None) -> VoiceSessionService:
        if cls._instance is None:
            if bot is None:
                raise RuntimeError("VoiceSessionService requires bot instance on initialization.")
            cls._instance = cls(bot)
        return cls._instance

    def get_session(self, guild_id: int) -> GuildAudioSession:
        if guild_id not in self._sessions:
            self._sessions[guild_id] = GuildAudioSession(guild_id)
        return self._sessions[guild_id]

    async def connect_channel(
        self, channel: discord.VoiceChannel, timeout: float = 10.0
    ) -> Tuple[bool, Optional[discord.VoiceClient], str]:
        """
        Safely connects to a voice channel, preventing race conditions or duplicate connections.
        """
        guild = channel.guild
        session = self.get_session(guild.id)
        async with session.lock:
            existing_vc = guild.voice_client
            if existing_vc and existing_vc.is_connected():
                if existing_vc.channel.id == channel.id:
                    session.connection = existing_vc
                    session.voice_channel_id = channel.id
                    session.connection_state = VoiceConnectionState.CONNECTED
                    return True, existing_vc, "Already connected to target channel."
                # Move to new channel cleanly
                try:
                    await existing_vc.move_to(channel)
                    session.connection = existing_vc
                    session.voice_channel_id = channel.id
                    session.connection_state = VoiceConnectionState.CONNECTED
                    return True, existing_vc, f"Moved to {channel.name}."
                except Exception as e:
                    logger.warning(f"Failed to move voice connection: {e}")
                    return False, None, f"Could not move to channel: {e}"

            session.connection_state = VoiceConnectionState.CONNECTING
            try:
                vc = await channel.connect(timeout=timeout, reconnect=True)
                session.connection = vc
                session.voice_channel_id = channel.id
                session.connection_state = VoiceConnectionState.CONNECTED
                session.last_activity = time.time()
                return True, vc, "Connected successfully."
            except Exception as e:
                session.connection_state = VoiceConnectionState.ERROR
                logger.error(f"Voice connection failure in guild {guild.id}: {e}")
                return False, None, f"Failed to connect to voice channel: {e}"

    async def disconnect(self, guild: discord.Guild, force: bool = False) -> bool:
        """
        Disconnects voice client cleanly and resets audio session state.
        Preserves Dynamic VC state.
        """
        session = self.get_session(guild.id)
        async with session.lock:
            vc = guild.voice_client
            if vc:
                try:
                    if vc.is_playing() and not force:
                        vc.stop()
                    await vc.disconnect(force=force)
                except Exception as e:
                    logger.warning(f"Error during voice disconnect: {e}")

            session.connection = None
            session.voice_channel_id = None
            session.connection_state = VoiceConnectionState.DISCONNECTED
            session.mode = AudioSessionMode.IDLE
            session.was_playing_music = False
            session.active_sound_id = None
            session.requester_id = None
            return True

    async def acquire_soundboard_session(
        self, guild: discord.Guild, sound_id: str, requester_id: int
    ) -> Tuple[bool, str]:
        """
        Coordinates acquiring voice access for a soundboard clip.
        If music is active, safely pauses it without clearing queue or corrupting player state.
        """
        session = self.get_session(guild.id)
        async with session.lock:
            vc = guild.voice_client
            if not vc or not vc.is_connected():
                return False, "Bot is not connected to a voice channel in this server."

            # Update session tracking
            session.connection = vc
            session.voice_channel_id = getattr(getattr(vc, "channel", None), "id", None)
            session.connection_state = VoiceConnectionState.CONNECTED
            session.last_activity = time.time()

            if vc.is_playing():
                if session.mode == AudioSessionMode.SOUNDBOARD:
                    return False, "A sound is already playing."
                # Music is playing -> pause cleanly
                try:
                    vc.pause()
                    session.was_playing_music = True
                    logger.info(f"Paused active music in {guild.name} ({guild.id}) for soundboard clip '{sound_id}'.")
                except Exception as e:
                    logger.warning(f"Could not pause music for soundboard: {e}")

            session.mode = AudioSessionMode.SOUNDBOARD
            session.active_sound_id = sound_id
            session.requester_id = requester_id
            return True, "Acquired"

    async def release_soundboard_session(self, guild: discord.Guild, sound_id: Optional[str] = None) -> None:
        """
        Releases voice access after soundboard playback completes or times out.
        If music was paused, safely resumes playback.
        """
        session = self.get_session(guild.id)
        async with session.lock:
            if session.mode != AudioSessionMode.SOUNDBOARD:
                return

            if sound_id and session.active_sound_id != sound_id:
                return

            session.active_sound_id = None
            session.requester_id = None
            session.last_activity = time.time()

            vc = guild.voice_client
            if session.was_playing_music:
                session.was_playing_music = False
                session.mode = AudioSessionMode.MUSIC
                if vc and vc.is_connected() and vc.is_paused():
                    try:
                        vc.resume()
                        logger.info(f"Resumed music in {guild.name} ({guild.id}) after soundboard clip.")
                    except Exception as e:
                        logger.warning(f"Could not resume music after soundboard: {e}")
            else:
                session.mode = AudioSessionMode.IDLE

    async def acquire_music_session(self, guild: discord.Guild, music_player: Any = None) -> Tuple[bool, str]:
        """Acquires the voice session for music playback."""
        session = self.get_session(guild.id)
        async with session.lock:
            vc = guild.voice_client
            if not vc or not vc.is_connected():
                return False, "Bot is not connected to a voice channel."

            session.connection = vc
            session.voice_channel_id = vc.channel.id if vc.channel else None
            session.connection_state = VoiceConnectionState.CONNECTED
            session.music_session = music_player
            session.mode = AudioSessionMode.MUSIC
            session.last_activity = time.time()
            return True, "Acquired"

    async def release_music_session(self, guild: discord.Guild) -> None:
        """Releases the music session state."""
        session = self.get_session(guild.id)
        async with session.lock:
            session.music_session = None
            if session.mode == AudioSessionMode.MUSIC:
                session.mode = AudioSessionMode.IDLE
            session.last_activity = time.time()

    async def handle_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """Tracks active users and cleans up stale sessions if the channel becomes empty."""
        guild = member.guild
        session = self.get_session(guild.id)
        vc = guild.voice_client

        if vc and vc.channel:
            human_members = {m.id for m in vc.channel.members if not m.bot}
            session.active_users = human_members
            session.last_activity = time.time()
            if not human_members and not member.bot:
                # Channel became empty of humans
                logger.info(f"[VOICE] Channel {vc.channel.name} in {guild.name} became empty.")

    def cleanup_stale_sessions(self) -> int:
        """Cleans up stale or zombie session objects where the voice client is disconnected."""
        cleaned = 0
        now = time.time()
        for gid, session in list(self._sessions.items()):
            if session.connection and not session.connection.is_connected():
                session.connection = None
                session.voice_channel_id = None
                session.connection_state = VoiceConnectionState.DISCONNECTED
                session.mode = AudioSessionMode.IDLE
                cleaned += 1
            elif session.mode == AudioSessionMode.IDLE and (now - session.last_activity > 3600):
                # Idle for over an hour
                pass
        return cleaned


# Central VoiceSessionManager alias
VoiceSessionManager = VoiceSessionService
