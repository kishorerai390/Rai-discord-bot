"""
RAI Music Player Service.
Manages audio stream playback through Discord VoiceClient, FFmpeg volume transformation,
connection reuse, and safe playback error recovery.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

import discord

from music.provider import (
    MusicErrorCode,
    ResolvedTrack,
    generate_music_diagnostic_id,
)
from music.queue_service import MusicQueueService

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.MusicPlayerService")

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class MusicPlayerService:
    """Controls voice client connection and audio playback pipeline for a guild."""

    def __init__(self, bot: SentinelBot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue = MusicQueueService(max_size=200)
        self.current: Optional[ResolvedTrack] = None
        self.volume: float = 0.5
        self.autoplay: bool = False
        self.inactivity_task: Optional[asyncio.Task] = None
        self.panel_message: Optional[discord.Message] = None
        self.text_channel: Optional[discord.abc.Messageable] = None
        self._lock = asyncio.Lock()

    @property
    def voice_client(self) -> Optional[discord.VoiceClient]:
        return self.guild.voice_client

    @property
    def is_playing(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_playing())

    @property
    def is_paused(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_paused())

    async def verify_and_connect_voice(
        self,
        user: discord.Member,
        target_channel: Optional[discord.VoiceChannel] = None,
    ) -> Tuple[bool, Optional[discord.VoiceClient], Optional[str], Optional[MusicErrorCode]]:
        """
        Validates voice permissions and connects or reuses existing connection without duplication.
        """
        vc_target = target_channel
        if not vc_target:
            if not user.voice or not user.voice.channel:
                return False, None, "❌ You must join a voice channel first.", MusicErrorCode.VOICE_CONNECTION_FAILED
            vc_target = user.voice.channel

        # Check bot permissions in target channel
        me = self.guild.me
        perms = vc_target.permissions_for(me)
        if not perms.view_channel:
            return False, None, "❌ Rai does not have permission to **View Channel** for this voice room.", MusicErrorCode.VOICE_CONNECTION_FAILED
        if not perms.connect:
            return False, None, "❌ Rai does not have permission to **Connect** to this voice room.", MusicErrorCode.VOICE_CONNECTION_FAILED
        if not perms.speak:
            return False, None, "❌ Rai does not have permission to **Speak** in this voice room.", MusicErrorCode.VOICE_CONNECTION_FAILED

        # Check existing connection for reuse
        current_vc = self.guild.voice_client
        if current_vc and current_vc.is_connected():
            if current_vc.channel.id != vc_target.id:
                try:
                    await current_vc.move_to(vc_target)
                    logger.info(f"Moved bot voice client to {vc_target.name} in {self.guild.name}")
                except Exception as exc:
                    return False, None, f"❌ Could not move bot to your voice channel: {exc}", MusicErrorCode.VOICE_CONNECTION_FAILED
            return True, current_vc, None, MusicErrorCode.SUCCESS

        # Connect to voice channel
        try:
            connected_vc = await vc_target.connect()
            logger.info(f"Connected bot voice client to {vc_target.name} in {self.guild.name}")
            return True, connected_vc, None, MusicErrorCode.SUCCESS
        except Exception as exc:
            logger.error(f"Failed to connect to voice channel {vc_target.id} in {self.guild.name}: {exc}")
            return False, None, f"❌ Failed to establish voice connection: {exc}", MusicErrorCode.VOICE_CONNECTION_FAILED

    def create_ffmpeg_source(self, stream_url: str) -> discord.AudioSource:
        """Creates FFmpeg audio source with volume transformation."""
        if not shutil.which("ffmpeg"):
            try:
                import static_ffmpeg
                static_ffmpeg.add_paths()
            except Exception:
                pass

        raw_source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
        return discord.PCMVolumeTransformer(raw_source, volume=self.volume)

    async def start_track(self, track: ResolvedTrack) -> bool:
        """Starts playback of a resolved track on the active voice client."""
        vc = self.voice_client
        if not vc or not vc.is_connected():
            logger.warning(f"Cannot start track in {self.guild.name}: Voice client not connected.")
            return False

        if not track.stream_url:
            logger.warning(f"Cannot start track in {self.guild.name}: Empty stream URL.")
            return False

        self._cancel_inactivity()
        self.current = track

        try:
            source = self.create_ffmpeg_source(track.stream_url)
            vc.play(source, after=self._on_track_end)
            logger.info(f"Started playback in {self.guild.name}: {track.title}")
            await self.update_panel()
            return True
        except Exception as exc:
            logger.error(f"Error starting audio playback for '{track.title}' in {self.guild.name}: {exc}")
            self.current = None
            self._on_track_end(error=exc)
            return False

    def _on_track_end(self, error: Optional[Exception] = None) -> None:
        """Callback invoked by Discord VoiceClient when stream finishes or fails."""
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

        asyncio.run_coroutine_threadsafe(self.process_next(), self.bot.loop)

    async def process_next(self) -> None:
        """Thread-safe queue advancement."""
        async with self._lock:
            next_track = await self.queue.pop_next(self.current)

            # Autoplay fallback if queue is empty
            if not next_track and self.autoplay and self.current:
                try:
                    from music.search_service import MusicSearchService
                    from music.resolver_service import MusicResolverService
                    search_service = MusicSearchService()
                    resolver = MusicResolverService(search_service)
                    candidates = await search_service.search_candidates(
                        f"{self.current.artist} official audio",
                        limit=3,
                        requester=self.current.requester,
                    )
                    for c in candidates:
                        if c.title != self.current.title:
                            res = await resolver.resolve_track(
                                c,
                                requester=self.current.requester or self.guild.me,
                                guild_id=self.guild.id,
                                bot=self.bot,
                            )
                            if res.is_success and res.track:
                                next_track = res.track
                                break
                except Exception as exc:
                    logger.debug(f"Autoplay resolution note: {exc}")

            if not next_track:
                self.current = None
                await self.update_panel()
                self._schedule_inactivity(timeout=180)
                return

            self._cancel_inactivity()
            self.current = next_track

            try:
                source = self.create_ffmpeg_source(next_track.stream_url)
                self.voice_client.play(source, after=self._on_track_end)
                logger.info(f"Advancing playback in {self.guild.name}: {next_track.title}")
                await self.update_panel()
            except Exception as exc:
                logger.error(f"Failed to play source in {self.guild.name}: {exc}")
                self._on_track_end(error=exc)

    async def pause(self) -> bool:
        vc = self.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await self.update_panel()
            return True
        return False

    async def resume(self) -> bool:
        vc = self.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await self.update_panel()
            return True
        return False

    async def skip(self) -> bool:
        vc = self.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            return True
        return False

    async def previous(self) -> Optional[ResolvedTrack]:
        prev = await self.queue.pop_previous(self.current)
        if prev:
            vc = self.voice_client
            if vc and (vc.is_playing() or vc.is_paused()):
                self.current = None
                vc.stop()
            await self.start_track(prev)
            return prev
        return None

    async def stop(self) -> None:
        await self.queue.clear()
        self.current = None
        vc = self.voice_client
        if vc:
            vc.stop()
        await self.update_panel()

    async def disconnect(self) -> None:
        await self.stop()
        vc = self.voice_client
        if vc and vc.is_connected():
            await vc.disconnect(force=True)

    async def update_panel(self) -> None:
        """Updates community Now Playing panel if configured."""
        music_cog = self.bot.get_cog("Music")
        if not music_cog:
            return

        if not self.current:
            if self.panel_message:
                try:
                    from utils.embeds import create_embed, Colors
                    embed = create_embed(
                        title="🎵 MUSIC PLAYER",
                        description="⏹️ Playback has ended. Use `/music play` to start listening.",
                        color=Colors.PRIMARY,
                    )
                    await self.panel_message.edit(embed=embed, view=None)
                except Exception:
                    pass
            return

        try:
            from cogs.music import MusicControlView
            embed = music_cog._create_now_playing_embed(self, self.current)
            view = MusicControlView(music_cog, self.guild)
            if self.panel_message:
                try:
                    await self.panel_message.edit(embed=embed, view=view)
                    return
                except Exception:
                    self.panel_message = None

            if self.text_channel:
                try:
                    self.panel_message = await self.text_channel.send(embed=embed, view=view)
                except Exception as pe:
                    logger.debug(f"Could not send public panel message: {pe}")
        except Exception as exc:
            logger.debug(f"Panel update suppressed: {exc}")

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
                logger.info(f"Auto-disconnecting idle voice client in {self.guild.name} (timeout {timeout}s)")
                await self.disconnect()
        except asyncio.CancelledError:
            pass
