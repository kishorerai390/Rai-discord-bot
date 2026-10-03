"""
RAI — SOUNDBOARD SERVICE & TIMEOUT MANAGER.
Provides:
- Playback state machine: IDLE, PLAYING, STOPPING, TIMED_OUT, COMPLETED, ERROR.
- Strict automatic sound timeout enforcement (default 8s, configurable 1-30s).
- Centralized SoundboardTimeoutManager linked to unified TimeoutManager.
- Dedicated SoundboardCooldownService: user cooldown (3-5s), sound cooldown (2-5s), guild cooldown.
- Dedicated SoundboardPermissionService: role/channel restrictions, DJ/Staff permissions.
- Full SoundboardPlaybackInstance state records (soundId, guildId, voiceChannelId, requesterId, startedAt, expiresAt, status, timerId).
- Safe coordination with VoiceSessionService (never corrupts or replaces Music).
- Standalone built-in audio synthesis for 100% offline self-healing reliability.
"""

from __future__ import annotations

import asyncio
import datetime
import math
import os
import shutil
import struct
import time
import wave
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

import discord

from services.timeout_manager import TimeoutManager, TimerType
from services.voice_session_service import VoiceSessionService

if TYPE_CHECKING:
    from core.bot import SentinelBot

import logging
logger = logging.getLogger("Rai.SoundboardService")

SOUNDBOARD_DIR = Path("assets/soundboard")


class SoundboardState(str, Enum):
    IDLE = "IDLE"
    PLAYING = "PLAYING"
    STOPPING = "STOPPING"
    TIMED_OUT = "TIMED_OUT"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


@dataclass
class SoundboardPlaybackInstance:
    sound_id: str
    guild_id: int
    voice_channel_id: int
    requester_id: int
    started_at: float
    expires_at: float
    status: SoundboardState = SoundboardState.PLAYING
    timer_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sound_id": self.sound_id,
            "guild_id": self.guild_id,
            "voice_channel_id": self.voice_channel_id,
            "requester_id": self.requester_id,
            "started_at": self.started_at,
            "expires_at": self.expires_at,
            "status": self.status.value,
            "timer_id": self.timer_id,
        }


class SoundboardTimeoutManager:
    """Centralized manager for playback timeout timers per guild, delegating to unified TimeoutManager."""

    def __init__(self):
        self._tasks: Dict[int, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self.unified_timeout = TimeoutManager.get_instance()

    async def register_timeout(
        self, guild_id: int, duration: float, callback, *args, **kwargs
    ) -> None:
        async with self._lock:
            # Cancel any existing timeout for this guild
            if guild_id in self._tasks and not self._tasks[guild_id].done():
                self._tasks[guild_id].cancel()

            timer_id = f"sb_guild_{guild_id}"
            await self.unified_timeout.create_timer(
                timer_id=timer_id,
                timer_type=TimerType.SOUNDBOARD_TIMEOUT,
                owner=guild_id,
                duration=duration,
                callback=callback,
                *args,
                **kwargs,
            )

            # Keep direct task reference for backward compatibility
            managed = self.unified_timeout.inspect_timer(timer_id)
            if managed and managed.task:
                self._tasks[guild_id] = managed.task

    async def cancel_timeout(self, guild_id: int) -> bool:
        async with self._lock:
            timer_id = f"sb_guild_{guild_id}"
            cancelled_unified = await self.unified_timeout.cancel_timer(timer_id)
            task = self._tasks.pop(guild_id, None)
            if task and not task.done():
                task.cancel()
                return True
            return cancelled_unified

    def clear_all(self) -> None:
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        self._tasks.clear()


class SoundboardCooldownService:
    """Manages anti-spam cooldowns per user, per sound, and per guild."""

    def __init__(self):
        self.user_cooldowns: Dict[Tuple[int, int], float] = {}   # (guild_id, user_id) -> expiry
        self.sound_cooldowns: Dict[Tuple[int, str], float] = {}  # (guild_id, sound_name) -> expiry
        self.guild_cooldowns: Dict[int, float] = {}               # guild_id -> expiry

    def check_user_cooldown(self, guild_id: int, user_id: int) -> Tuple[bool, float]:
        now = time.time()
        expiry = self.user_cooldowns.get((guild_id, user_id), 0.0)
        if now < expiry:
            return False, round(expiry - now, 1)
        return True, 0.0

    def check_sound_cooldown(self, guild_id: int, sound_name: str) -> Tuple[bool, float]:
        now = time.time()
        expiry = self.sound_cooldowns.get((guild_id, sound_name), 0.0)
        if now < expiry:
            return False, round(expiry - now, 1)
        return True, 0.0

    def check_guild_cooldown(self, guild_id: int) -> Tuple[bool, float]:
        now = time.time()
        expiry = self.guild_cooldowns.get(guild_id, 0.0)
        if now < expiry:
            return False, round(expiry - now, 1)
        return True, 0.0

    def apply_cooldowns(
        self, guild_id: int, user_id: int, sound_name: str, user_cd: float, sound_cd: float, guild_cd: float = 0.0
    ) -> None:
        now = time.time()
        if user_cd > 0:
            self.user_cooldowns[(guild_id, user_id)] = now + user_cd
        if sound_cd > 0:
            self.sound_cooldowns[(guild_id, sound_name)] = now + sound_cd
        if guild_cd > 0:
            self.guild_cooldowns[guild_id] = now + guild_cd

    def clear(self) -> None:
        self.user_cooldowns.clear()
        self.sound_cooldowns.clear()
        self.guild_cooldowns.clear()


class SoundboardPermissionService:
    """Enforces role, channel, and administrative restrictions on soundboard playback."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    def can_play_sound(
        self, member: Any, channel: Any, settings: Dict[str, Any]
    ) -> Tuple[bool, str]:
        # 1. Voice channel permission
        if hasattr(channel, "permissions_for") and callable(channel.permissions_for):
            try:
                perms = channel.permissions_for(member)
                if not getattr(perms, "connect", True) or not getattr(perms, "speak", True):
                    return False, "You do not have permission to connect and speak in this voice channel."
            except Exception:
                pass

        # 2. Disabled channel check
        restricted_channels = settings.get("restricted_channels", [])
        if getattr(channel, "id", None) in restricted_channels:
            return False, "Soundboard playback is restricted in this channel."

        # 3. Role restrictions if configured
        allowed_roles = settings.get("allowed_roles", [])
        if allowed_roles and hasattr(member, "roles"):
            member_role_ids = {r.id for r in member.roles}
            is_admin = getattr(getattr(member, "guild_permissions", None), "administrator", False)
            if not member_role_ids.intersection(allowed_roles) and not is_admin:
                return False, "You do not hold an authorized role to use the soundboard."

        return True, "OK"

    def can_manage_soundboard(self, member: discord.Member) -> bool:
        from utils.permissions import is_admin_or_owner
        return is_admin_or_owner(member)


class SoundboardService:
    _instance: Optional[SoundboardService] = None

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.timeout_manager = SoundboardTimeoutManager()
        self.cooldown_service = SoundboardCooldownService()
        self.permission_service = SoundboardPermissionService(bot)
        self.voice_session = VoiceSessionService.get_instance(bot)
        self.states: Dict[int, SoundboardState] = {}
        self.active_instances: Dict[int, SoundboardPlaybackInstance] = {}
        self.active_requesters: Dict[int, int] = {}
        self.active_sounds: Dict[int, str] = {}
        # Backward compatibility aliases for cooldown dictionaries
        self.user_cooldowns = self.cooldown_service.user_cooldowns
        self.sound_cooldowns = self.cooldown_service.sound_cooldowns
        self.server_settings: Dict[int, Dict[str, Any]] = {}
        self._ensure_built_in_sounds()

    @classmethod
    def get_instance(cls, bot: Optional[SentinelBot] = None) -> SoundboardService:
        if cls._instance is None:
            if bot is None:
                raise RuntimeError("SoundboardService requires bot instance on first access.")
            cls._instance = cls(bot)
        return cls._instance

    def _ensure_built_in_sounds(self) -> None:
        """Generates standard clean WAV audio assets if not present."""
        SOUNDBOARD_DIR.mkdir(parents=True, exist_ok=True)
        built_ins = {
            "airhorn": [(880, 0.15), (0, 0.05), (880, 0.15), (0, 0.05), (880, 0.4)],
            "bruh": [(150, 0.4), (110, 0.3)],
            "victory": [(523, 0.15), (659, 0.15), (784, 0.15), (1046, 0.5)],
            "defeat": [(440, 0.3), (415, 0.3), (392, 0.3), (370, 0.6)],
            "laugh": [(600, 0.1), (700, 0.1), (600, 0.1), (700, 0.1), (600, 0.2)],
            "beep": [(1000, 0.3)],
            "tada": [(440, 0.15), (554, 0.15), (659, 0.15), (880, 0.6)],
            "bell": [(1200, 0.8)],
            "fart": [(90, 0.4), (75, 0.3)],
            "applause": [(300, 0.05), (0, 0.05), (350, 0.05), (0, 0.05), (320, 0.05), (0, 0.05)],
        }

        for name, tones in built_ins.items():
            path = SOUNDBOARD_DIR / f"{name}.wav"
            if not path.exists():
                self._generate_wav(path, tones)

    @staticmethod
    def _generate_wav(path: Path, tones: List[Tuple[float, float]], sample_rate: int = 44100) -> None:
        """Synthesizes clean sine wave PCM audio with standard headers."""
        try:
            with wave.open(str(path), "wb") as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)

                data = bytearray()
                for freq, dur in tones:
                    total_samples = int(sample_rate * dur)
                    for i in range(total_samples):
                        if freq == 0:
                            sample_val = 0
                        else:
                            t = float(i) / sample_rate
                            sample_val = int(32767.0 * 0.6 * math.sin(2.0 * math.pi * freq * t))
                        data.extend(struct.pack("<h", max(-32768, min(32767, sample_val))))
                wav_file.writeframes(data)
        except Exception as e:
            logger.warning(f"Failed to generate built-in sound '{path.name}': {e}")

    def get_settings(self, guild_id: int) -> Dict[str, Any]:
        defaults = {
            "timeout": 8,            # Seconds (1-30)
            "user_cooldown": 3,      # Seconds
            "sound_cooldown": 5,     # Seconds
            "guild_cooldown": 0,     # Seconds
            "allow_overlapping": False,
            "max_concurrent": 1,
            "enabled": True,
            "volume_limit": 0.85,    # 0.1 - 1.0
            "restricted_channels": [],
            "allowed_roles": [],
        }
        if guild_id not in self.server_settings:
            self.server_settings[guild_id] = defaults
        return self.server_settings[guild_id]

    def update_settings(self, guild_id: int, **kwargs) -> Dict[str, Any]:
        cfg = self.get_settings(guild_id)
        for k, v in kwargs.items():
            if k == "timeout":
                cfg[k] = max(1, min(30, int(v)))
            elif k in ("user_cooldown", "sound_cooldown", "guild_cooldown"):
                cfg[k] = max(0, int(v))
            elif k == "allow_overlapping":
                cfg[k] = bool(v)
            elif k == "max_concurrent":
                cfg[k] = max(1, min(3, int(v)))
            elif k == "enabled":
                cfg[k] = bool(v)
            elif k == "volume_limit":
                cfg[k] = max(0.1, min(1.0, float(v)))
            elif k in ("restricted_channels", "allowed_roles"):
                cfg[k] = list(v)
        return cfg

    def list_available_sounds(self, guild_id: Optional[int] = None) -> List[str]:
        if not SOUNDBOARD_DIR.exists():
            return []
        sounds = []
        for file in SOUNDBOARD_DIR.iterdir():
            if file.suffix.lower() in (".wav", ".mp3"):
                sounds.append(file.stem.lower())
        return sorted(list(set(sounds)))

    def get_sound_path(self, sound_name: str) -> Optional[Path]:
        clean = sound_name.strip().lower()
        wav = SOUNDBOARD_DIR / f"{clean}.wav"
        if wav.exists():
            return wav
        mp3 = SOUNDBOARD_DIR / f"{clean}.mp3"
        if mp3.exists():
            return mp3
        return None

    def get_active_playback(self, guild_id: int) -> Optional[SoundboardPlaybackInstance]:
        return self.active_instances.get(guild_id)

    async def play_sound(
        self, interaction: discord.Interaction, sound_name: str
    ) -> Tuple[bool, str]:
        """
        Executes complete soundboard playback pipeline:
        1. Configuration check (enabled?)
        2. Audio asset resolution
        3. Voice channel membership check
        4. Permission checks (SoundboardPermissionService)
        5. Anti-spam Cooldown checks (SoundboardCooldownService)
        6. Voice connection via VoiceSessionService (never clashes with Music)
        7. Strict timeout scheduling
        8. PlaybackInstance recording
        """
        guild = interaction.guild
        user = interaction.user
        if not guild or user is None:
            return False, "❌ Soundboard commands can only be used in a Discord server."

        cfg = self.get_settings(guild.id)
        if not cfg.get("enabled", True):
            return False, "❌ Soundboard is currently disabled on this server."

        # 1. Resolve Audio File
        clean_sound = sound_name.strip().lower()
        sound_path = self.get_sound_path(clean_sound)
        if not sound_path:
            return False, f"❌ Sound clip '**{clean_sound}**' was not found. Use `/soundboard list` to view available clips."

        # 2. Verify Requester Voice State
        voice_state = getattr(user, "voice", None)
        target_vc = getattr(voice_state, "channel", None) if voice_state else None
        if not target_vc:
            return False, "❌ You must be connected to a voice channel to use the soundboard."

        # 3. Verify Permissions
        perm_ok, perm_msg = self.permission_service.can_play_sound(user, target_vc, cfg)
        if not perm_ok:
            return False, f"❌ {perm_msg}"

        # 4. Anti-Spam Cooldown Verification
        user_ok, user_rem = self.cooldown_service.check_user_cooldown(guild.id, user.id)
        if not user_ok:
            return False, f"⏳ You are on cooldown. Please wait **{user_rem}s** before playing another sound."

        sound_ok, sound_rem = self.cooldown_service.check_sound_cooldown(guild.id, clean_sound)
        if not sound_ok:
            return False, f"⏳ Sound '**{clean_sound}**' is on cooldown. Please wait **{sound_rem}s**."

        guild_ok, guild_rem = self.cooldown_service.check_guild_cooldown(guild.id)
        if not guild_ok:
            return False, f"⏳ Server soundboard cooldown active. Please wait **{guild_rem}s**."

        # 5. Overlapping & Concurrency Checks
        current_state = self.states.get(guild.id, SoundboardState.IDLE)
        if current_state == SoundboardState.PLAYING and not cfg.get("allow_overlapping", False):
            return False, "⚠️ A sound is already playing in this server. Please wait for it to finish or use `/soundboard stop`."

        # 6. Ensure Voice Connection
        vc = getattr(guild, "voice_client", None)
        if not vc:
            try:
                if hasattr(target_vc, "connect") and callable(target_vc.connect):
                    vc = await target_vc.connect(timeout=10.0, reconnect=True)
                else:
                    return False, "❌ Could not connect to your voice channel."
            except Exception as e:
                return False, f"❌ Could not connect to your voice channel: {e}"
        elif getattr(getattr(vc, "channel", None), "id", None) != getattr(target_vc, "id", None):
            try:
                if hasattr(vc, "move_to") and callable(vc.move_to):
                    await vc.move_to(target_vc)
            except Exception as e:
                return False, f"❌ Could not move to your voice channel: {e}"

        # 7. Coordinate with VoiceSessionService (pause music if playing)
        acquired, msg = await self.voice_session.acquire_soundboard_session(guild, clean_sound, user.id)
        if not acquired:
            return False, f"❌ {msg}"

        # 8. Start playback with strict timeout
        timeout_seconds = cfg.get("timeout", 8)
        now = time.time()
        expires_at = now + timeout_seconds
        timer_id = f"sb_guild_{guild.id}"

        # Record Playback Instance
        instance = SoundboardPlaybackInstance(
            sound_id=clean_sound,
            guild_id=guild.id,
            voice_channel_id=target_vc.id,
            requester_id=user.id,
            started_at=now,
            expires_at=expires_at,
            status=SoundboardState.PLAYING,
            timer_id=timer_id,
        )
        self.active_instances[guild.id] = instance
        self.states[guild.id] = SoundboardState.PLAYING
        self.active_requesters[guild.id] = user.id
        self.active_sounds[guild.id] = clean_sound

        # Apply cooldowns
        self.cooldown_service.apply_cooldowns(
            guild_id=guild.id,
            user_id=user.id,
            sound_name=clean_sound,
            user_cd=float(cfg.get("user_cooldown", 3)),
            sound_cd=float(cfg.get("sound_cooldown", 5)),
            guild_cd=float(cfg.get("guild_cooldown", 0)),
        )

        def _after_playback(error):
            asyncio.run_coroutine_threadsafe(
                self._handle_playback_finished(guild.id, clean_sound, error),
                self.bot.loop,
            )

        try:
            audio_source = discord.FFmpegPCMAudio(str(sound_path))
            volume_level = cfg.get("volume_limit", 0.85)
            volume_source = discord.PCMVolumeTransformer(audio_source, volume=volume_level)
            vc.play(volume_source, after=_after_playback)
        except Exception as e:
            await self.voice_session.release_soundboard_session(guild, clean_sound)
            self.states[guild.id] = SoundboardState.ERROR
            if guild.id in self.active_instances:
                self.active_instances[guild.id].status = SoundboardState.ERROR
            return False, f"❌ Failed to start audio playback: {e}"

        # 9. Register timeout with SoundboardTimeoutManager
        await self.timeout_manager.register_timeout(
            guild.id,
            duration=float(timeout_seconds),
            callback=self._handle_timeout,
            guild_id=guild.id,
            sound_name=clean_sound,
        )

        logger.info(f"Started soundboard '{clean_sound}' in guild {guild.id} (timeout: {timeout_seconds}s).")
        return True, f"🔊 Playing **{clean_sound}** (auto-timeout in {timeout_seconds}s)"

    async def _handle_timeout(self, guild_id: int, sound_name: str) -> None:
        """Called by SoundboardTimeoutManager when timeout is reached."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        if self.states.get(guild_id) != SoundboardState.PLAYING:
            return

        logger.info(f"Soundboard timeout reached for '{sound_name}' in guild {guild_id}. Stopping sound.")
        self.states[guild_id] = SoundboardState.TIMED_OUT
        if guild_id in self.active_instances:
            self.active_instances[guild_id].status = SoundboardState.TIMED_OUT

        vc = guild.voice_client
        if vc and vc.is_playing():
            try:
                vc.stop()
            except Exception as e:
                logger.warning(f"Error stopping voice client on timeout: {e}")

        await self._cleanup_guild_sound(guild_id, sound_name)

    async def _handle_playback_finished(self, guild_id: int, sound_name: str, error: Optional[Exception]) -> None:
        """Called when audio naturally finishes or stops."""
        if error:
            logger.error(f"Soundboard error in guild {guild_id}: {error}")
            self.states[guild_id] = SoundboardState.ERROR
            if guild_id in self.active_instances:
                self.active_instances[guild_id].status = SoundboardState.ERROR
        elif self.states.get(guild_id) != SoundboardState.TIMED_OUT:
            self.states[guild_id] = SoundboardState.COMPLETED
            if guild_id in self.active_instances:
                self.active_instances[guild_id].status = SoundboardState.COMPLETED

        await self.timeout_manager.cancel_timeout(guild_id)
        await self._cleanup_guild_sound(guild_id, sound_name)

    async def stop_sound(self, guild: discord.Guild, user: discord.Member, force: bool = False) -> Tuple[bool, str]:
        """Stops active sound for requester, DJ, or server staff."""
        guild_id = guild.id
        if self.states.get(guild_id) not in (SoundboardState.PLAYING, SoundboardState.STOPPING):
            return False, "ℹ️ No sound is currently playing in this server."

        requester_id = self.active_requesters.get(guild_id)
        from utils.permissions import is_admin_or_owner

        if not force and requester_id != user.id and not is_admin_or_owner(user):
            return False, "❌ Only the requester or server staff can stop this sound."

        self.states[guild_id] = SoundboardState.STOPPING
        if guild_id in self.active_instances:
            self.active_instances[guild_id].status = SoundboardState.STOPPING

        await self.timeout_manager.cancel_timeout(guild_id)

        vc = guild.voice_client
        if vc and vc.is_playing():
            try:
                vc.stop()
            except Exception:
                pass

        sound_name = self.active_sounds.get(guild_id, "")
        await self._cleanup_guild_sound(guild_id, sound_name)
        return True, "⏹️ Stopped soundboard playback."

    async def _cleanup_guild_sound(self, guild_id: int, sound_name: str) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild:
            await self.voice_session.release_soundboard_session(guild, sound_name)

        self.states[guild_id] = SoundboardState.IDLE
        self.active_requesters.pop(guild_id, None)
        self.active_sounds.pop(guild_id, None)
        self.active_instances.pop(guild_id, None)

    async def handle_user_left_vc(self, member: discord.Member, channel: discord.VoiceChannel) -> None:
        """Stops playback if the requester leaves the voice channel."""
        guild_id = member.guild.id
        if self.states.get(guild_id) == SoundboardState.PLAYING:
            if self.active_requesters.get(guild_id) == member.id:
                logger.info(f"Requester {member} left VC {channel.id}; stopping sound.")
                await self.stop_sound(member.guild, member, force=True)

    async def handle_empty_vc(self, channel: discord.VoiceChannel) -> None:
        """Stops playback if voice channel becomes empty."""
        guild_id = channel.guild.id
        if self.states.get(guild_id) == SoundboardState.PLAYING:
            logger.info(f"VC {channel.id} is empty; stopping soundboard.")
            await self.stop_sound(channel.guild, channel.guild.me, force=True)
