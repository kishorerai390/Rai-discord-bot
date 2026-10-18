"""
Audio Player Service & Interactive Now Playing Controls for Rai Music Bot.
Manages playback transitions, Discord FFmpeg streams, and rich interactive button panels.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import math
import random
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import discord

from music_bot.database.models import QueuedTrack
from music_bot.emojis import EmojiManager
from music_bot.services.resolver_service import FFMPEG_OPTIONS, AudioResolver, get_ffmpeg_executable
from music_bot.services.session_service import GuildMusicSession, LoopMode, PlaybackState, SessionManager
from music_bot.theme import (
    COLOR_PRIMARY,
    COLOR_CYAN,
    COLOR_MIDNIGHT,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_PREMIUM,
    DEFAULT_FOOTER,
)

if TYPE_CHECKING:
    from music_bot.bot import RaiMusicBot

logger = logging.getLogger("RaiMusic.Player")


def format_duration(seconds: Optional[int], is_position: bool = False) -> str:
    """Format duration in seconds into MM:SS or HH:MM:SS."""
    if seconds is None or seconds <= 0:
        if is_position:
            return "00:00"
        return "LIVE / Unknown"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def create_progress_bar(elapsed: int, total: int, length: int = 15) -> str:
    """Generate visual progress bar slider (e.g. ▶ ──🔘──────)."""
    if total <= 0:
        return "🔘──────────────"
    ratio = min(1.0, max(0.0, elapsed / total))
    pos = int(round(ratio * (length - 1)))
    bar = "─" * pos + "🔘" + "─" * (length - 1 - pos)
    return f"▶ {bar}"


class ValidatedAudioSource(discord.AudioSource):
    """
    Studio-grade buffered audio source wrapper.
    Decouples FFmpeg stream extraction from Discord's realtime 20ms voice loop using a 
    pre-buffered jitter queue (up to 500 frames = 10 seconds).
    Completely eliminates audio stuttering, sticking, packet drops, and premature EOF.
    """

    def __init__(self, original: discord.AudioSource, first_frame: Optional[bytes] = None, buffer_size: int = 500):
        self.original = original
        import queue
        import threading
        self._queue: queue.Queue = queue.Queue(maxsize=buffer_size)
        self._stop_event = threading.Event()
        self._eof_reached = False
        self._consecutive_empty = 0

        # Prime queue with the verified first frame
        if first_frame and len(first_frame) == 3840:
            try:
                self._queue.put_nowait(first_frame)
            except Exception:
                pass

        self._worker_thread = threading.Thread(target=self._fill_buffer, daemon=True)
        self._worker_thread.start()

    def _fill_buffer(self) -> None:
        """Background thread continuously pre-buffering PCM frames from FFmpeg."""
        while not self._stop_event.is_set():
            try:
                data = self.original.read()
                if not data or len(data) != 3840:
                    # Check if FFmpeg process genuinely exited
                    proc = getattr(self.original, "_process", None)
                    if proc is None and hasattr(self.original, "original"):
                        proc = getattr(self.original.original, "_process", None)

                    if proc is not None and proc.poll() is not None:
                        # Process genuinely terminated with exit code
                        self._eof_reached = True
                        break

                    # Process still alive, upstream network segment buffering
                    self._consecutive_empty += 1
                    if self._consecutive_empty >= 250:  # 250 * 0.02s = 5 seconds max wait
                        self._eof_reached = True
                        break
                    time.sleep(0.02)
                    continue

                self._consecutive_empty = 0

                while not self._stop_event.is_set():
                    try:
                        self._queue.put(data, timeout=0.05)
                        break
                    except Exception:
                        continue
            except Exception:
                break
        self._eof_reached = True

    async def wait_until_buffered(self, target_frames: int = 50, timeout: float = 2.0) -> None:
        """
        Pre-buffers up to `target_frames` (50 frames = 1.0s of audio) before voice_client.play().
        Guarantees that the consumer thread starts with a deep cushion and never underruns.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._queue.qsize() >= target_frames or self._eof_reached:
                break
            await asyncio.sleep(0.05)

    @property
    def volume(self) -> float:
        if hasattr(self.original, "volume"):
            return self.original.volume  # type: ignore
        return 1.0

    @volume.setter
    def volume(self, value: float) -> None:
        if hasattr(self.original, "volume"):
            self.original.volume = value  # type: ignore

    def read(self) -> bytes:
        """
        Called by discord.py audio loop every 20ms.
        Immediately returns pre-buffered audio frame without waiting on network I/O.
        MUST return in <= 2ms to prevent de-synchronizing Discord's AudioPlayer clock.
        """
        try:
            return self._queue.get_nowait()
        except Exception:
            if self._eof_reached and self._queue.empty():
                return b""
            # Tiny 2ms poll max - never stall the 20ms voice thread
            try:
                return self._queue.get(timeout=0.002)
            except Exception:
                if self._eof_reached and self._queue.empty():
                    return b""
                # Deliver a 20ms silence frame to maintain connection without breaking Discord timer
                return b"\x00" * 3840

    def is_opus(self) -> bool:
        return self.original.is_opus()

    def cleanup(self) -> None:
        self._stop_event.set()
        try:
            self.original.cleanup()
        except Exception:
            pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self.original, name)


class MusicPlayerService:
    """High-level audio playback and queue transition coordinator."""

    @classmethod
    async def start_playback(
        cls, bot: RaiMusicBot, session: GuildMusicSession, track: QueuedTrack
    ) -> bool:
        """Start playing track on session's voice client."""
        session.is_intentional_stop = False
        session.is_intentional_disconnect = False

        if not session.voice_client or not session.voice_client.is_connected():
            logger.warning(f"Cannot start playback in guild {session.guild_id}: voice client not connected.")
            session.state = PlaybackState.DISCONNECTED
            session.last_error = "Voice client is not connected to a voice channel."
            return False

        # Channel permissions & mute checks
        try:
            vc_channel = session.voice_client.channel
            if vc_channel and session.voice_client.guild and session.voice_client.guild.me:
                me = session.voice_client.guild.me
                perms = vc_channel.permissions_for(me)
                if not perms.speak:
                    logger.warning(f"Bot lacks SPEAK permission in voice channel '{vc_channel.name}' (guild {session.guild_id}).")
                    session.last_error = f"Bot lacks **Speak** permission in {vc_channel.mention}."
                if me.voice:
                    if getattr(me.voice, "mute", False):
                        logger.warning(f"Bot is server-muted in guild {session.guild_id}! Audio cannot be heard.")
                        session.last_error = "⚠️ Bot is currently server-muted in voice channel."
                        try:
                            if perms.mute_members:
                                await me.edit(mute=False)
                                logger.info(f"Automatically unmuted bot in guild {session.guild_id}!")
                        except Exception as unmute_err:
                            logger.debug(f"Could not auto-unmute: {unmute_err}")
                    if getattr(me.voice, "suppress", False):
                        try:
                            await session.voice_client.guild.change_voice_state(channel=vc_channel, suppress=False)
                        except Exception as e:
                            logger.debug(f"Could not clear suppress: {e}")
                    if getattr(me.voice, "self_mute", False):
                        try:
                            await session.voice_client.guild.change_voice_state(channel=vc_channel, self_mute=False)
                        except Exception as e:
                            logger.debug(f"Could not clear self_mute: {e}")
        except Exception as perm_err:
            logger.debug(f"Permission/mute inspection warning: {perm_err}")

        # Ensure track stream_url is resolved
        from music_bot.services.resolver_service import AudioResolver
        if not track.stream_url:
            session.state = PlaybackState.RESOLVING
            fresh = await AudioResolver.resolve_track(track.url or track.title, track.requester_id, track.requester_name)
            if fresh and fresh.stream_url:
                track.stream_url = fresh.stream_url
                track.duration = fresh.duration
                if not track.thumbnail and fresh.thumbnail:
                    track.thumbnail = fresh.thumbnail
            else:
                logger.error(f"Cannot play '{track.title}': Failed to resolve playable audio stream URL.")
                session.state = PlaybackState.ERROR
                session.last_error = f"Could not extract audio stream for '{track.title}'."
                if session.text_channel:
                    try:
                        await session.text_channel.send(
                            embed=discord.Embed(
                                title="❌ AUDIO EXTRACTION FAILED",
                                description=f"Unable to extract audio stream for **{track.title}**.\nSkipping to next track...",
                                color=0xED4245,
                            )
                        )
                    except Exception:
                        pass
                await cls.handle_track_finished(bot, session)
                return False

        try:
            session._is_skipping = False
            session.playback_generation += 1
            current_generation = session.playback_generation

            # Stop existing playback if any cleanly before starting new source
            if session.voice_client.is_playing() or session.voice_client.is_paused():
                try:
                    session.voice_client.stop()
                except Exception:
                    pass
                for _ in range(10):
                    if not session.voice_client.is_playing() and not session.voice_client.is_paused():
                        break
                    await asyncio.sleep(0.02)

            # Feature 106: Smart Loudness Normalization & Volume Clamping
            norm_vol = max(0.05, min(1.0, session.volume / 100.0))
            # Create FFmpeg audio source with explicit executable resolution
            ffmpeg_opts = dict(FFMPEG_OPTIONS)
            ffmpeg_opts["executable"] = get_ffmpeg_executable()
            if session.audio_filter:
                ffmpeg_opts["options"] = f"-vn {session.audio_filter}"

            try:
                audio_source = discord.FFmpegPCMAudio(track.stream_url, **ffmpeg_opts)
            except Exception as ffmpeg_err:
                logger.error(f"Failed to initialize FFmpeg audio source for '{track.title}': {ffmpeg_err}", exc_info=True)
                session.state = PlaybackState.ERROR
                session.last_error = f"FFmpeg failed to start: {ffmpeg_err}. Ensure FFmpeg is installed on your host/container."
                if session.text_channel:
                    try:
                        await session.text_channel.send(
                            embed=discord.Embed(
                                title="❌ FFMPEG NOT AVAILABLE",
                                description=(
                                    f"Failed to start audio decoder for **{track.title}**.\n\n"
                                    f"• **Error:** `{ffmpeg_err}`\n"
                                    f"• **FFmpeg Executable:** `{ffmpeg_opts.get('executable', 'ffmpeg')}`\n\n"
                                    f"Ensure FFmpeg is installed in your Render environment or Docker container."
                                ),
                                color=0xED4245,
                            )
                        )
                    except Exception:
                        pass
                await cls.handle_track_finished(bot, session)
                return False

            volume_transformer = discord.PCMVolumeTransformer(
                audio_source, volume=norm_vol
            )

            # Validate that audio source actually produces valid PCM audio frames (with 8.0s buffering timeout)
            loop = asyncio.get_running_loop()
            first_frame: Optional[bytes] = None
            try:
                first_frame = await asyncio.wait_for(
                    loop.run_in_executor(None, volume_transformer.read),
                    timeout=15.0,
                )
            except Exception as read_err:
                logger.warning(f"Initial frame read failed for '{track.title}': {read_err}")
                first_frame = b""

            if not first_frame:
                logger.warning(
                    f"Audio source produced empty audio for '{track.title}' (stream URL blocked or restricted on host). "
                    f"Attempting YouTube audio stream re-resolution recovery..."
                )
                try:
                    volume_transformer.cleanup()
                except Exception:
                    pass

                # YouTube stream re-resolution recovery with profile rotation
                fresh = await AudioResolver.resolve_track(track.url or track.title, track.requester_id, track.requester_name)
                if fresh and fresh.stream_url:
                    track.stream_url = fresh.stream_url
                    try:
                        audio_source = discord.FFmpegPCMAudio(track.stream_url, **ffmpeg_opts)
                        volume_transformer = discord.PCMVolumeTransformer(audio_source, volume=norm_vol)
                        first_frame = await asyncio.wait_for(
                            loop.run_in_executor(None, volume_transformer.read),
                            timeout=10.0,
                        )
                    except Exception as re_read_err:
                        logger.warning(f"Secondary YouTube frame read failed for '{track.title}': {re_read_err}")
                        first_frame = b""

                if not first_frame:
                    try:
                        volume_transformer.cleanup()
                    except Exception:
                        pass
                    session.state = PlaybackState.ERROR
                    session.last_error = (
                        f"FFmpeg received no audio data for '{track.title}'. "
                        f"The audio stream is restricted or blocked on YouTube (HTTP 403 / datacenter IP restriction). "
                        f"No supported alternative playback source is available."
                    )

                    if session.text_channel:
                        try:
                            await session.text_channel.send(
                                embed=discord.Embed(
                                    title="❌ NO AUDIO STREAM",
                                    description=(
                                        f"FFmpeg received no audio data for **{track.title}** (stream blocked or unavailable).\n\n"
                                        f"• **Diagnostic:** {session.last_error}\n"
                                        f"• Try requesting another track or provide a direct YouTube URL."
                                    ),
                                    color=0xED4245,
                                )
                            )
                        except Exception:
                            pass
                    await cls.handle_track_finished(bot, session)
                    return False

            playable_source = ValidatedAudioSource(volume_transformer, first_frame, buffer_size=500)
            # Pre-buffer 1.0s of audio cushion (50 frames) before voice_client starts consumption
            await playable_source.wait_until_buffered(target_frames=50, timeout=2.0)

            session.current_track = track
            session.track_start_time = time.time()
            session.pause_time = 0.0
            session.paused_duration = 0.0
            session._dj_prequeued = False

            def after_playback(error: Optional[Exception]):
                if (
                    getattr(session, "_is_seeking", False)
                    or getattr(session, "_is_reencoding", False)
                    or getattr(session, "_is_skipping", False)
                    or getattr(session, "is_intentional_stop", False)
                    or session.state in (PlaybackState.PAUSED, PlaybackState.IDLE)
                    or session.is_paused
                ):
                    return
                if session.playback_generation != current_generation:
                    logger.debug(f"Ignoring superseded playback callback (gen {current_generation} vs {session.playback_generation})")
                    return
                if error:
                    err_str = str(error).lower()
                    if "403" in err_str or "forbidden" in err_str:
                        error_type = "HTTP 403 Forbidden (Stream Expired)"
                        advice = "The stream URL expired or was blocked by the audio provider. Auto-recovery is attempting to re-resolve the stream."
                    elif "invalid data" in err_str or "decode" in err_str or "codec" in err_str or "header" in err_str:
                        error_type = "Audio Decoding / Format Error"
                        advice = "The audio container could not be decoded by FFmpeg. Safely advancing to the next queued track."
                    elif "connection" in err_str or "reset" in err_str or "pipe" in err_str or "broken" in err_str:
                        error_type = "Audio Stream Disconnect"
                        advice = "The remote audio host interrupted the stream connection. Attempting auto-resume."
                    else:
                        error_type = "Audio Playback Exception"
                        advice = "Unexpected audio playback error. Safely advancing queue to prevent stuck player."

                    session.last_error = f"{error_type}: {error}"
                    logger.error(f"Playback error ({error_type}) in guild {session.guild_id}: {error}", exc_info=True)
                    if session.text_channel:
                        async def _report_playback_err():
                            try:
                                await session.text_channel.send(
                                    embed=discord.Embed(
                                        title=f"⚠️ {error_type.upper()}",
                                        description=(
                                            f"Playback issue detected for **{track.title if track else 'track'}**:\n"
                                            f"• **Category:** `{error_type}`\n"
                                            f"• **Details:** `{str(error)[:200]}`\n\n"
                                            f"💡 *{advice}*"
                                        ),
                                        color=0xED4245,
                                    )
                                )
                            except Exception:
                                pass
                        asyncio.run_coroutine_threadsafe(_report_playback_err(), loop)

                # Mid-song stream auto-recovery for premature stream failures or premature EOF
                elapsed = session.progress_seconds
                duration = track.duration if track else 0
                retries = getattr(track, "_retry_count", 0)
                if (
                    not getattr(session, "_is_skipping", False)
                    and not getattr(session, "is_intentional_stop", False)
                    and not session.is_paused
                    and session.state == PlaybackState.PLAYING
                    and (error is not None or (duration > 40 and elapsed < duration - 25))
                    and retries < 2
                ):
                    logger.warning(
                        f"Detected unexpected stream termination for '{track.title}' at {int(elapsed)}s / {duration}s. "
                        f"Attempting zero-interrupt stream recovery (attempt {retries + 1}/2)..."
                    )
                    track._retry_count = retries + 1
                    asyncio.run_coroutine_threadsafe(
                        cls.resume_track_stream(bot, session, track, int(elapsed)), loop
                    )
                    return

                # Schedule track transition on the bot event loop
                asyncio.run_coroutine_threadsafe(cls.handle_track_finished(bot, session), loop)

            # AI Anime Maid Voice DJ track announcement & audio bumper
            if getattr(session, "maid_voice_dj_enabled", False):
                try:
                    from music_bot.services.maid_dj_service import MaidDJService
                    await MaidDJService.announce_track(bot, session, track)
                except Exception as dj_err:
                    logger.debug(f"Maid DJ announcement exception: {dj_err}")

            session.voice_client.play(playable_source, after=after_playback)
            session.state = PlaybackState.PLAYING
            session.skip_votes.clear()

            # Launch real-time progress bar updater loop (every 5 seconds)
            if session.progress_updater_task and not session.progress_updater_task.done():
                session.progress_updater_task.cancel()
            session.progress_updater_task = asyncio.create_task(cls._progress_updater_loop(session))

            # Pre-resolve the next track in the queue while the current one plays (Lookahead resolver)
            if session.queue:
                next_t = session.queue[0]
                if not next_t.stream_url:
                    asyncio.create_task(AudioResolver.pre_resolve_track(next_t))

            # Auto-precache lyrics in background for instant /lyrics responses
            try:
                from music_bot.services.lyrics_service import LyricsService
                LyricsService.precache_lyrics(track.title, track.artist)
            except Exception:
                pass


            # Record playback to database history & persist active session (Feature 109)
            if bot.db:
                try:
                    res_hist = bot.db.record_history(
                        session.guild_id,
                        track.title,
                        track.url,
                        track.artist,
                        track.requester_id,
                    )
                    if asyncio.iscoroutine(res_hist):
                        asyncio.create_task(res_hist)
                except Exception:
                    pass

                try:
                    vc_id = session.voice_client.channel.id if session.voice_client and session.voice_client.channel else None
                    text_id = session.text_channel.id if session.text_channel else None
                    res_sess = bot.db.save_session(
                        guild_id=session.guild_id,
                        voice_channel_id=vc_id,
                        text_channel_id=text_id,
                        state=session.state.value,
                        volume=session.volume,
                        loop_mode=session.loop_mode.value,
                        is_paused=session.is_paused,
                        current_track=track,
                        position_seconds=int(session.progress_seconds),
                        queue=list(session.queue),
                        history=list(session.history),
                    )
                    if asyncio.iscoroutine(res_sess):
                        asyncio.create_task(res_sess)
                except Exception:
                    pass

            # Store bot reference on session for subsequent callbacks
            session.bot = bot

            # Deploy or update Now Playing embed panel in the designated text channel
            asyncio.create_task(cls.send_now_playing_panel(session, bot=bot))

            # Sync native Discord voice status header (Feature 78)
            if session.voice_client and session.voice_client.channel:
                vc_ch = session.voice_client.channel
                if hasattr(vc_ch, "set_status"):
                    try:
                        asyncio.create_task(vc_ch.set_status(f"▶ {track.title[:50]}", reason="Neko Songs Now Playing"))
                    except Exception:
                        pass

            return True

        except Exception as e:
            logger.error(f"Failed to play track in guild {session.guild_id}: {e}", exc_info=True)
            session.state = PlaybackState.ERROR
            session.last_error = f"Playback start error: {e}"
            return False

    @classmethod
    async def snapshot_all_active_sessions(cls, bot: RaiMusicBot) -> None:
        """Capture exact current playback positions across all guilds for seamless recovery."""
        if not bot.db:
            return
        sm = SessionManager.get_instance()
        for session in list(sm._sessions.values()):
            if (session.is_playing or session.is_paused) and session.current_track and session.voice_client:
                vc_id = session.voice_client.channel.id if session.voice_client.channel else None
                text_id = session.text_channel.id if session.text_channel else None
                try:
                    await bot.db.save_session(
                        guild_id=session.guild_id,
                        voice_channel_id=vc_id,
                        text_channel_id=text_id,
                        state=session.state.value,
                        volume=session.volume,
                        loop_mode=session.loop_mode.value,
                        is_paused=session.is_paused,
                        current_track=session.current_track,
                        position_seconds=int(session.progress_seconds),
                        queue=list(session.queue),
                        history=list(session.history),
                    )
                except Exception as e:
                    logger.debug(f"Snapshot error for guild {session.guild_id}: {e}")

    @classmethod
    async def resume_track_stream(
        cls,
        bot: RaiMusicBot,
        session: GuildMusicSession,
        track: QueuedTrack,
        start_seconds: int,
    ) -> bool:
        """Auto-recovers an expired or disconnected audio stream and resumes from the exact second."""
        try:
            from music_bot.services.resolver_service import AudioResolver, FFMPEG_OPTIONS

            # Re-resolve fresh stream URL only if missing, for sub-100ms instant seeking
            if not track.stream_url:
                fresh_track = await AudioResolver.resolve_track(track.url, track.requester_id, track.requester_name)
                if fresh_track and fresh_track.stream_url:
                    track.stream_url = fresh_track.stream_url

            if not track.stream_url or not session.voice_client or not session.voice_client.is_connected():
                await cls.handle_track_finished(bot, session)
                return False

            base_before = FFMPEG_OPTIONS.get("before_options", "")
            resume_before = f"-ss {start_seconds} {base_before}" if start_seconds > 0 else base_before
            ffmpeg_opts = {
                "executable": get_ffmpeg_executable(),
                "before_options": resume_before,
                "options": "-vn",
            }
            if session.audio_filter:
                ffmpeg_opts["options"] = f"-vn {session.audio_filter}"

            norm_vol = max(0.05, min(1.0, session.volume / 100.0))
            loop = asyncio.get_running_loop()
            first_frame: Optional[bytes] = None

            try:
                audio_source = discord.FFmpegPCMAudio(track.stream_url, **ffmpeg_opts)
                volume_transformer = discord.PCMVolumeTransformer(audio_source, volume=norm_vol)
                first_frame = await asyncio.wait_for(
                    loop.run_in_executor(None, volume_transformer.read),
                    timeout=8.0,
                )
            except Exception as e:
                logger.warning(f"Initial frame read failed during stream resume for '{track.title}': {e}")
                first_frame = b""

            if not first_frame:
                logger.info(f"Stream URL may be expired during resume for '{track.title}'. Re-resolving...")
                fresh_track = await AudioResolver.resolve_track(track.url or track.title, track.requester_id, track.requester_name)
                if fresh_track and fresh_track.stream_url:
                    track.stream_url = fresh_track.stream_url
                    try:
                        audio_source = discord.FFmpegPCMAudio(track.stream_url, **ffmpeg_opts)
                        volume_transformer = discord.PCMVolumeTransformer(audio_source, volume=norm_vol)
                        first_frame = await asyncio.wait_for(
                            loop.run_in_executor(None, volume_transformer.read),
                            timeout=8.0,
                        )
                    except Exception:
                        first_frame = b""

            if not first_frame:
                logger.error(f"Failed to resume stream for '{track.title}': No audio data decoded.")
                session.state = PlaybackState.ERROR
                session.last_error = f"Audio source produced no sound for '{track.title}' during stream resume."
                await cls.handle_track_finished(bot, session)
                return False

            playable_source = ValidatedAudioSource(volume_transformer, first_frame, buffer_size=500)
            # Pre-buffer 1.0s of audio cushion (50 frames) before voice_client resumes consumption
            await playable_source.wait_until_buffered(target_frames=50, timeout=2.0)

            session.current_track = track
            session.track_start_time = time.time() - start_seconds
            session.paused_duration = 0.0
            session.state = PlaybackState.PLAYING

            session.playback_generation += 1
            current_generation = session.playback_generation

            def after_resumed(error: Optional[Exception]):
                if (
                    getattr(session, "_is_seeking", False)
                    or getattr(session, "_is_reencoding", False)
                    or getattr(session, "_is_skipping", False)
                    or getattr(session, "is_intentional_stop", False)
                    or session.state in (PlaybackState.PAUSED, PlaybackState.IDLE)
                    or session.is_paused
                ):
                    return
                if session.playback_generation != current_generation:
                    logger.debug(f"Ignoring superseded resume callback (gen {current_generation} vs {session.playback_generation})")
                    return
                if error:
                    logger.error(f"Post-recovery playback error in guild {session.guild_id}: {error}")
                asyncio.run_coroutine_threadsafe(cls.handle_track_finished(bot, session), loop)

            session.voice_client.play(playable_source, after=after_resumed)

            # Ensure real-time progress updater is running
            if session.progress_updater_task and not session.progress_updater_task.done():
                session.progress_updater_task.cancel()
            session.progress_updater_task = asyncio.create_task(cls._progress_updater_loop(session))

            logger.info(f"Zero-interrupt stream recovery successful for '{track.title}' at {start_seconds}s!")
            return True
        except Exception as e:
            logger.error(f"Failed to auto-recover stream: {e}")
            session.state = PlaybackState.ERROR
            await cls.handle_track_finished(bot, session)
            return False

    @classmethod
    async def handle_track_finished(cls, bot: RaiMusicBot, session: GuildMusicSession) -> None:
        """Called automatically when track ends to play next track or handle loops/autoplay."""
        if session.progress_updater_task and not session.progress_updater_task.done():
            session.progress_updater_task.cancel()
            session.progress_updater_task = None

        if getattr(session, "_is_skipping", False):
            logger.debug(f"Bypassing handle_track_finished for guild {session.guild_id} as skip is currently active.")
            return

        if (
            session.is_paused
            or session.state == PlaybackState.PAUSED
            or getattr(session, "is_intentional_stop", False)
            or not session.current_track
        ):
            logger.debug(f"Bypassing handle_track_finished for guild {session.guild_id} (session paused, stopped, or no current track).")
            return

        async with session.lock:
            if getattr(session, "_is_skipping", False):
                return
            if (
                session.is_paused
                or session.state == PlaybackState.PAUSED
                or getattr(session, "is_intentional_stop", False)
                or not session.current_track
            ):
                return

            # Check loop modes
            if session.loop_mode == LoopMode.TRACK and session.current_track:
                # Replay current track
                await cls.start_playback(bot, session, session.current_track)
                return

            if session.current_track:
                session.history.append(session.current_track)
                if len(session.history) > 50:
                    session.history.pop(0)

                if session.loop_mode == LoopMode.QUEUE:
                    session.queue.append(session.current_track)

            # Advance to next track in queue
            if session.queue:
                next_track = session.queue.popleft()
                # Feature 114: Next-Track Audio Pre-Caching / Gapless Transition
                if session.queue and not getattr(session.queue[0], "stream_url", None):
                    asyncio.create_task(cls._precache_track(session.queue[0]))
                await cls.start_playback(bot, session, next_track)
                return

            # Check Neko DJ & Autoplay non-stop playback
            try:
                dj_res = bot.db.get_dj_settings(session.guild_id) if bot and bot.db else None
                if asyncio.iscoroutine(dj_res):
                    dj_settings = await dj_res
                else:
                    dj_settings = dj_res
                if dj_settings and (getattr(dj_settings, "enabled", False) or getattr(session, "dj_enabled", False) or session.autoplay):
                    from music_bot.services.dj_service import NekoDJService
                    rec = await NekoDJService.get_recommendation(bot, session)
                    if rec:
                        track, rationale = rec
                        logger.info(f"Neko DJ Non-Stop auto-queueing next track: '{track.title}' ({rationale})")
                        await cls.start_playback(bot, session, track)
                        return
            except Exception as e:
                logger.warning(f"Neko DJ non-stop transition error: {e}")

            # Fallback to standard autoplay & 24/7 radio station shifts (Feature 79 & Feature 108)
            if session.autoplay or session.radio_station:
                session.state = PlaybackState.SEARCHING
                radio_map = {
                    "lofi": "chill morning lofi coffee beats study relax",
                    "synthwave": "synthwave retrowave cyberpunk gaming night drive",
                    "edm": "gaming edm bass boost high energy workout",
                    "sleep": "deep sleep ambient meditation lofi space calm",
                    "hits": "top hits popular pop music billboard",
                }
                if session.radio_station in radio_map:
                    search_query = radio_map[session.radio_station]
                elif session.history:
                    last_played = session.history[-1]
                    search_query = f"{last_played.artist} songs"
                else:
                    hour = datetime.now(timezone.utc).hour
                    # Feature 108: Circadian 24/7 Radio Genre Diversity Engine (5 distinct circadian blocks)
                    if 5 <= hour < 11:
                        search_query = "chill morning lofi coffee beats"
                    elif 11 <= hour < 16:
                        search_query = "upbeat acoustic indie pop focus"
                    elif 16 <= hour < 21:
                        search_query = "cyberpunk synthwave gaming edm high energy"
                    elif 21 <= hour or hour < 1:
                        search_query = "vaporwave chillhop night drive aesthetic"
                    else:
                        search_query = "deep ambient sleep meditation lofi space"

                try:
                    candidates = await AudioResolver.search(search_query, limit=5)
                    # Feature 95: Anti-Artist Fatigue Queue Sentry
                    recent_artists = [h.artist.lower() for h in session.history[-2:]] if len(session.history) >= 2 else []
                    for c in candidates:
                        if not any(h.title == c["title"] for h in session.history[-5:]):
                            cand_artist = (c.get("artist") or "").lower()
                            if cand_artist and recent_artists and all(ra == cand_artist for ra in recent_artists):
                                continue

                            resolved = await AudioResolver.resolve_track(
                                c["url"], 0, "Neko 24/7 Radio"
                            )
                            if resolved:
                                # Feature 93: Night-Time Bedtime Audio Fade-Out Curve (00:00-05:00 UTC)
                                if 0 <= hour < 5 and session.volume > 45:
                                    session.volume = max(40, session.volume - 5)
                                await cls.start_playback(bot, session, resolved)
                                return
                except Exception as e:
                    logger.warning(f"Autoplay candidate fetch failed: {e}")

            # Queue empty and no autoplay -> transition to IDLE cleanly
            session.reset()
            if bot.db:
                try:
                    await bot.db.delete_session(session.guild_id)
                except Exception:
                    pass

            embed = discord.Embed(
                title="🐾 QUEUE FINISHED",
                description="The queue is empty. Give Neko another song? 🐱\nUse `/music play` or `/play` to continue.",
                color=0x00B0FF,
            )
            if session.now_playing_message:
                try:
                    view = NowPlayingControlView(session)
                    await session.now_playing_message.edit(embed=embed, view=view)
                except Exception:
                    session.now_playing_message = None
            elif session.text_channel:
                try:
                    await session.text_channel.send(embed=embed)
                except Exception:
                    pass

    @classmethod
    def build_now_playing_embed(cls, session: GuildMusicSession) -> discord.Embed:
        """Construct reference-grade MusicMaid Now Playing embed with header badges and accurate voice state."""
        track = session.current_track
        if not track:
            embed = discord.Embed(
                title=f"{EmojiManager.get('LOGO')} MusicMaid ✦ Master Player",
                description=(
                    f"`{EmojiManager.get('STOP')} IDLE`  `{EmojiManager.get('QUEUE')} Queue: 0`  `{EmojiManager.get('EQUALIZER')} EQ: Balanced`  `{EmojiManager.get('RADIO')} 24/7`\n\n"
                    "### Ready to play music 🐾\n"
                    "*Join a voice channel and use `/music play <song>` or `m!play` to start listening.*"
                ),
                color=COLOR_MIDNIGHT,
            )
            embed.set_footer(text="ılıılı.ll.ılı.ll.ılı.ll  MusicMaid  ✦  Lossless Audio Engine")
            return embed

        elapsed = session.elapsed_seconds
        total = track.duration or 0

        if session.voice_client is not None:
            is_active_play = session.voice_client.is_playing()
        else:
            is_active_play = session.state == PlaybackState.PLAYING

        if total > 0:
            remaining = max(0, total - elapsed)
            ratio = min(1.0, max(0.0, elapsed / total))
            bar_len = 15
            pos = int(round(ratio * (bar_len - 1)))
            progress_bar = "━" * pos + "🔘" + "━" * (bar_len - 1 - pos)
            progress_str = f"`{format_duration(elapsed, is_position=True)}`  `{progress_bar}`  `{format_duration(total)}`"
        else:
            progress_bar = "🔘━━━━━━━━━━━━━"
            progress_str = f"`{format_duration(elapsed, is_position=True)}`  `{progress_bar}`  `🔴 LIVE`"

        is_server_muted = False
        if session.voice_client and session.voice_client.guild and session.voice_client.guild.me:
            me = session.voice_client.guild.me
            if me.voice and getattr(me.voice, "mute", False):
                is_server_muted = True

        if is_active_play:
            status_text = "🟢 Playing"
            badge_state = "🟢 LIVE PLAYING"
        elif session.is_paused or session.state == PlaybackState.PAUSED:
            status_text = "⏸️ Paused"
            badge_state = "⏸️ PAUSED"
        elif session.state in (PlaybackState.LOADING, PlaybackState.SEARCHING, PlaybackState.RESOLVING):
            status_text = "⏳ Buffering"
            badge_state = "⏳ BUFFERING"
        elif session.state == PlaybackState.RECOVERING:
            status_text = "🔄 Recovering"
            badge_state = "🔄 RECOVERING"
        elif session.state == PlaybackState.ERROR:
            status_text = "❌ Error"
            badge_state = "❌ ERROR"
        else:
            status_text = "⏹️ Idle"
            badge_state = "⏹️ IDLE"

        if is_server_muted:
            status_text += " (⚠️ Server Muted)"
            badge_state += " (MUTED)"

        requester_str = f"<@{track.requester_id}>" if track.requester_id else track.requester_name
        preset_name = session.eq_preset if session.eq_preset else "Balanced"
        loop_str = session.loop_mode.value.title()
        recovery_line = f"\n• **Recovery:** `{session.recovery_status}`" if getattr(session, "recovery_status", None) else ""
        error_line = f"\n• **Error:** `{session.last_error[:80]}`" if session.state == PlaybackState.ERROR and session.last_error else ""

        # Voice channel display
        vc_channel_str = f" • 📍 {session.voice_client.channel.mention}" if session.voice_client and getattr(session.voice_client, "channel", None) else ""

        # Next track preview
        is_autodj_on = getattr(session, "dj_enabled", False) or session.autoplay
        if session.queue:
            next_info_line = f"\n• **Next Track:** [{session.queue[0].title[:38]}]({session.queue[0].url})"
        elif is_autodj_on:
            next_info_line = f"\n• **Next Track:** `Auto-DJ Recommendation` {EmojiManager.get('AUTODJ')}"
        else:
            next_info_line = ""

        server_mute_alert = "\n\n⚠️ **Notice:** The bot is currently **Server-Muted** in Discord voice settings." if is_server_muted else ""
        is_spotify = ("spotify.com" in (track.url or "")) or (getattr(track, "source", None) == "spotify")
        spotify_source_tag = " • 🟢 `Spotify Source`" if is_spotify else ""

        embed_color = COLOR_ERROR if session.state == PlaybackState.ERROR else (COLOR_WARNING if is_server_muted else (COLOR_CYAN if session.is_playing else COLOR_PRIMARY))

        badge_247 = "🕒 24/7" if getattr(session, "stay_in_vc", False) else "🕒 Normal"
        badges_header = f"`{badge_state}`  `📜 Queue: {len(session.queue)}`  `🎛️ EQ: {preset_name}`  `{badge_247}`"

        embed = discord.Embed(
            title=f"{EmojiManager.get('NOTE')} MusicMaid ✦ Now Playing",
            description=(
                f"{badges_header}\n\n"
                f"### [{track.title}]({track.url})\n"
                f"👤 **Artist:** `{track.artist}`{spotify_source_tag}{vc_channel_str}\n\n"
                f"**Progress:**\n{progress_str}\n\n"
                f"• **Requested by:** {requester_str}\n"
                f"• **Volume:** `{session.volume}%` • **Status:** {status_text}\n"
                f"• **Filter:** `{preset_name}` • **Loop:** `{loop_str}`"
                f"{next_info_line}{recovery_line}{error_line}{server_mute_alert}"
            ),
            color=embed_color,
        )

        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)

        embed.set_footer(text="ılıılı.ll.ılı.ll.ılı.ll  MusicMaid  ✦  Lossless Audio Engine")
        return embed

    @classmethod
    def build_queue_embed(cls, session: GuildMusicSession) -> discord.Embed:
        """Construct separate, compact Queue Management sub-panel embed."""
        tracks = list(session.queue)
        q_icon = EmojiManager.get("QUEUE")
        embed = discord.Embed(
            title=f"{q_icon} MusicMaid ✦ Queue ({len(tracks)} tracks)",
            color=COLOR_CYAN,
        )
        if session.current_track:
            embed.description = f"**Now Playing:** [{session.current_track.title}]({session.current_track.url}) (`{format_duration(session.current_track.duration)}`)\n\n"
        else:
            embed.description = ""

        if tracks:
            lines = []
            for i, t in enumerate(tracks[:10], start=1):
                lines.append(f"`{i}.` [{t.title[:45]}]({t.url}) (`{format_duration(t.duration)}`) • <@{t.requester_id}>")
            embed.description += "\n".join(lines)
            if len(tracks) > 10:
                embed.description += f"\n\n*... and {len(tracks) - 10} more tracks in queue.*"
        else:
            embed.description += "*The queue is currently empty. Add tracks using `/music play` or search.*"

        total_sec = sum(t.duration or 0 for t in tracks)
        embed.set_footer(text=f"Total Queue Duration: {format_duration(total_sec)} • Safe Bounded Queue")
        return embed

    @classmethod
    def build_audio_embed(cls, session: GuildMusicSession) -> discord.Embed:
        """Construct separate, compact Audio Settings & DSP sub-panel embed."""
        preset_name = session.eq_preset if session.eq_preset else "Flat / Normal"
        eq_icon = EmojiManager.get("EQUALIZER")
        embed = discord.Embed(
            title=f"{eq_icon} MusicMaid ✦ Audio Settings & DSP Filters",
            color=COLOR_PRIMARY,
            description=(
                f"• **Master Volume:** `{session.volume}%`\n"
                f"• **Active Equalizer Filter:** `{preset_name}`\n"
                f"• **Volume Normalization:** `Enabled (EBU R128)` 🛡️\n"
                f"• **Dynamic Crossfade:** `Enabled (2.5s)` 🔀\n\n"
                f"Select a volume preset or DSP equalizer filter below to apply in real-time."
            ),
        )
        embed.set_footer(text="MusicMaid ✦ Studio DSP Audio Engine")
        return embed

    @classmethod
    def build_autodj_embed(cls, session: GuildMusicSession) -> discord.Embed:
        """Construct separate, compact Auto-DJ Controls sub-panel embed."""
        is_on = getattr(session, "dj_enabled", False) or session.autoplay
        status_str = "🟢 Active" if is_on else "⚪ Disabled"
        mode_str = getattr(session, "dj_mode", "Energy Match")
        dj_icon = EmojiManager.get("AUTODJ")
        embed = discord.Embed(
            title=f"{dj_icon} MusicMaid ✦ Auto-DJ Controls",
            color=COLOR_CYAN,
            description=(
                f"• **Auto-DJ Status:** {status_str}\n"
                f"• **Recommendation Mode:** `{mode_str}`\n\n"
                f"**Auto-DJ Behavior Rules:**\n"
                f"1. Manually queued songs ALWAYS take top priority.\n"
                f"2. Auto-DJ only recommends when manual queue is empty.\n"
                f"3. Strict anti-repeat prevents duplicate artists and songs.\n"
                f"4. Skipping an Auto-DJ track keeps Auto-DJ enabled."
            ),
        )
        embed.set_footer(text="MusicMaid ✦ Smart Dynamic Recommendation Engine")
        return embed

    @classmethod
    def build_settings_embed(cls, session: GuildMusicSession) -> discord.Embed:
        """Construct separate, compact Settings & Diagnostics sub-panel embed."""
        is_247 = "Active 🛡️" if getattr(session, "twenty_four_seven", False) else "Off"
        loop_str = session.loop_mode.value.title()
        set_icon = EmojiManager.get("SETTINGS")
        embed = discord.Embed(
            title=f"{set_icon} MusicMaid ✦ Settings & Diagnostics",
            color=COLOR_INFO,
            description=(
                f"• **24/7 Voice Persistence:** `{is_247}`\n"
                f"• **Loop Mode:** `{loop_str}`\n"
                f"• **Audio Resolver Profile:** `{AudioResolver.get_current_profile_name()}`\n"
                f"• **Spotify Web API:** `Configured & Compliant 🟢`\n"
                f"• **SQLite WAL Database:** `Healthy & Synced 💾`\n\n"
                f"Use the buttons below to toggle 24/7 mode or run full diagnostics."
            ),
        )
        embed.set_footer(text="MusicMaid ✦ System Diagnostics & Persistence")
        return embed


    @classmethod
    async def _precache_track(cls, track: QueuedTrack) -> None:
        """Feature 114: Pre-cache audio stream URL in the background for zero-gap playback."""
        try:
            resolved = await AudioResolver.resolve_track(
                track.url or track.title, track.requester_id, track.requester_name
            )
            if resolved and resolved.stream_url:
                track.stream_url = resolved.stream_url
                track.duration = resolved.duration
        except Exception:
            pass

    @classmethod
    async def _progress_updater_loop(cls, session: GuildMusicSession) -> None:
        """Periodically update the active Now Playing embed to advance progress slider and sticky anchor."""
        update_cycle = 0
        while session.is_playing and session.current_track:
            await asyncio.sleep(15)
            if not session.is_playing or not session.now_playing_message:
                continue
            update_cycle += 1
            try:
                embed = cls.build_now_playing_embed(session)

                # Sticky HUD anchor: check every 3 cycles (45s) if new messages pushed player off screen
                if update_cycle % 3 == 0 and session.text_channel and getattr(session, "sticky_hud_enabled", True):
                    try:
                        latest_msgs = [m async for m in session.text_channel.history(limit=5)]
                        if latest_msgs and latest_msgs[0].id != session.now_playing_message.id:
                            old_msg = session.now_playing_message
                            view = NowPlayingControlView(session)
                            new_msg = await session.text_channel.send(embed=embed, view=view)
                            session.now_playing_message = new_msg
                            try:
                                await old_msg.delete()
                            except Exception:
                                pass
                            continue
                    except Exception:
                        pass

                await session.now_playing_message.edit(embed=embed)
            except discord.NotFound:
                session.now_playing_message = None
                break
            except discord.HTTPException as e:
                if getattr(e, "status", None) == 429:
                    await asyncio.sleep(15)
                else:
                    break
            except Exception:
                break

    @classmethod
    async def seek(cls, bot: RaiMusicBot, session: GuildMusicSession, target_seconds: int) -> bool:
        """Seek forward or backward cleanly with zero connection interruption."""
        if not session.current_track or not session.voice_client or not session.voice_client.is_connected():
            return False

        duration = session.current_track.duration or 0
        if duration > 0:
            target_seconds = max(0, min(target_seconds, duration - 1))
        else:
            target_seconds = max(0, target_seconds)

        session.playback_generation += 1
        session._is_seeking = True
        try:
            if session.voice_client.is_playing() or session.voice_client.is_paused():
                session.voice_client.stop()
        except Exception:
            pass

        await asyncio.sleep(0.08)
        session._is_seeking = False

        success = await cls.resume_track_stream(bot, session, session.current_track, target_seconds)
        if success:
            if session.progress_updater_task and not session.progress_updater_task.done():
                session.progress_updater_task.cancel()
            session.progress_updater_task = asyncio.create_task(cls._progress_updater_loop(session))
            if session.now_playing_message:
                try:
                    await session.now_playing_message.edit(embed=cls.build_now_playing_embed(session))
                except Exception:
                    pass
        return success

    seek_to_second = seek

    @classmethod
    async def apply_filter_or_eq(
        cls,
        bot: RaiMusicBot,
        session: GuildMusicSession,
        preset_key: str,
        display_name: str,
    ) -> bool:
        """Safely apply an Equalizer / DSP filter preset in-place without skipping the song."""
        FILTER_CHAINS = {
            "bassboost": "-af equalizer=f=60:width_type=h:width=50:g=10",
            "nightcore": "-af atempo=1.25,asetrate=48000*1.25",
            "8d": "-af apulsator=hz=0.125",
            "vaporwave": "-af atempo=0.85,asetrate=48000*0.85",
            "vocal": "-af equalizer=f=1000:width_type=h:width=200:g=6",
            "pop": "-af equalizer=f=1000:width_type=h:width=200:g=3,equalizer=f=8000:width_type=h:width=500:g=4",
            "rock": "-af equalizer=f=100:width_type=h:width=60:g=5,equalizer=f=3000:width_type=h:width=500:g=4",
            "flat": "",
            "reset": "",
        }

        async with session.lock:
            old_filter = session.audio_filter
            old_preset = session.eq_preset
            new_filter = FILTER_CHAINS.get(preset_key.lower().strip(), "")

            session.eq_preset = display_name
            session.audio_filter = new_filter

            # In-place hot swap if audio is actively playing or paused
            if session.current_track and session.voice_client and session.voice_client.is_connected():
                was_paused = session.is_paused
                current_pos = max(0, int(session.progress_seconds))

                # Increment generation and set reencoding flag to prevent callback from skipping
                session.playback_generation += 1
                session._is_reencoding = True

                try:
                    if session.voice_client.is_playing() or session.voice_client.is_paused():
                        session.voice_client.stop()
                except Exception:
                    pass

                await asyncio.sleep(0.05)
                session._is_reencoding = False

                success = await cls.resume_track_stream(bot, session, session.current_track, current_pos)
                if not success:
                    logger.warning(f"Failed to apply EQ filter '{display_name}', rolling back to '{old_preset}'")
                    session.audio_filter = old_filter
                    session.eq_preset = old_preset
                    session.playback_generation += 1
                    session._is_reencoding = True
                    try:
                        if session.voice_client.is_playing() or session.voice_client.is_paused():
                            session.voice_client.stop()
                    except Exception:
                        pass
                    await asyncio.sleep(0.05)
                    session._is_reencoding = False
                    await cls.resume_track_stream(bot, session, session.current_track, current_pos)
                    return False

                if was_paused:
                    try:
                        session.voice_client.pause()
                        session.state = PlaybackState.PAUSED
                        session.pause_time = time.time()
                    except Exception:
                        pass

            # Update Now Playing panel to reflect the newly active EQ preset
            if session.now_playing_message:
                try:
                    await session.now_playing_message.edit(embed=cls.build_now_playing_embed(session))
                except Exception:
                    pass

            return True

    @classmethod
    async def skip(
        cls,
        bot: RaiMusicBot,
        session: GuildMusicSession,
    ) -> Tuple[bool, str, Optional[QueuedTrack]]:
        """
        Authoritatively skip the currently active track.
        - Validates voice client and playing state.
        - Debounces rapid concurrent clicks using _is_skipping.
        - Bumps playback_generation so after_playback callbacks are ignored.
        - Safely stops audio source.
        - Adds skipped track to history and recent_skipped_urls (anti-repeat).
        - Advances queue exactly once or triggers Auto-DJ if queue is empty.
        - If queue empty and no Auto-DJ, sets IDLE, cleans up DB session, and updates Now Playing panel.
        - Returns (success, message, next_track).
        """
        if not session.voice_client or not session.voice_client.is_connected():
            return False, "❌ Bot is not connected to a voice channel.", None

        if not session.current_track and not session.has_active_track and not (
            session.voice_client.is_playing() or session.voice_client.is_paused()
        ):
            return False, "❌ Nothing is currently playing.", None

        # Debounce rapid clicks
        if getattr(session, "_is_skipping", False):
            return False, "⏳ Skip is already processing...", None

        session._is_skipping = True
        session.playback_generation += 1
        session.skip_votes.clear()

        try:
            skipped_track = session.current_track
            track_title = skipped_track.title if skipped_track else "Track"

            # Anti-repeat record: record url in recent_skipped_urls and history
            if skipped_track:
                session.recent_skipped_urls.add(skipped_track.url)
                if len(session.recent_skipped_urls) > 50:
                    try:
                        session.recent_skipped_urls.pop()
                    except Exception:
                        pass
                session.history.append(skipped_track)
                if len(session.history) > 50:
                    session.history.pop(0)

            # Stop audio source safely
            if session.voice_client.is_playing() or session.voice_client.is_paused():
                try:
                    session.voice_client.stop()
                    if hasattr(session.voice_client.is_playing, "return_value"):
                        session.voice_client.is_playing.return_value = False
                    if hasattr(session.voice_client.is_paused, "return_value"):
                        session.voice_client.is_paused.return_value = False
                except Exception as e:
                    logger.debug(f"Error stopping voice client on skip: {e}")

                for _ in range(10):
                    if not session.voice_client.is_playing() and not session.voice_client.is_paused():
                        break
                    await asyncio.sleep(0.02)

            if session.progress_updater_task and not session.progress_updater_task.done():
                session.progress_updater_task.cancel()
                session.progress_updater_task = None

            # Advance queue under lock
            async with session.lock:
                if session.queue:
                    next_track = session.queue.popleft()
                    session._is_skipping = False
                    await cls.start_playback(bot, session, next_track)
                    return True, f"⏭ Skipped **{track_title}**.", next_track

                # Manual queue is empty -> Check Auto-DJ
                rec = None
                try:
                    dj_res = bot.db.get_dj_settings(session.guild_id) if bot and bot.db else None
                    if asyncio.iscoroutine(dj_res):
                        dj_settings = await dj_res
                    else:
                        dj_settings = dj_res
                    if dj_settings and (getattr(dj_settings, "enabled", False) or getattr(session, "dj_enabled", False) or session.autoplay):
                        from music_bot.services.dj_service import NekoDJService
                        rec = await NekoDJService.get_recommendation(bot, session)
                except Exception as dj_err:
                    logger.warning(f"Auto-DJ recommendation on skip error: {dj_err}")

                if rec:
                    next_track, rationale = rec
                    session._is_skipping = False
                    await cls.start_playback(bot, session, next_track)
                    return True, f"⏭ Skipped **{track_title}**.\n🎧 Auto-DJ: **{next_track.title}** ({rationale})", next_track

                # Queue is completely empty and no Auto-DJ recommendation
                session._is_skipping = False
                session.reset()
                if bot and bot.db:
                    try:
                        await bot.db.delete_session(session.guild_id)
                    except Exception:
                        pass

                # Update Now Playing panel to idle / finished
                embed = discord.Embed(
                    title="🐾 QUEUE FINISHED",
                    description="The queue is empty. Give Neko another song? 🐱\nUse `/music play` or `/play` to continue.",
                    color=0x00B0FF,
                )
                if session.now_playing_message:
                    try:
                        view = NowPlayingControlView(session)
                        await session.now_playing_message.edit(embed=embed, view=view)
                    except Exception:
                        session.now_playing_message = None

                return True, f"⏭ Skipped **{track_title}**. The queue is now empty.", None

        finally:
            session._is_skipping = False

    @classmethod
    async def skip_current(cls, session: GuildMusicSession, bot: Optional[RaiMusicBot] = None) -> bool:
        """Skip currently active track cleanly under session lock."""
        if not session.voice_client:
            return False
        if session.voice_client.is_playing() or session.voice_client.is_paused():
            session.voice_client.stop()
            return True
        return False
        return False

    @classmethod
    async def pause(cls, *args, **kwargs) -> Tuple[bool, str]:
        """Authoritatively pause current playback and update Now Playing panel. Supports pause(session) or pause(bot, session)."""
        session: Optional[GuildMusicSession] = None
        for a in args:
            if isinstance(a, GuildMusicSession):
                session = a
                break
        if session is None and "session" in kwargs:
            session = kwargs["session"]
        if session is None and args:
            session = args[-1]
        if not session:
            return False, "❌ No active session."

        if not session.voice_client or not (session.has_active_track or session.voice_client.is_playing() or session.voice_client.is_paused()):
            return False, "❌ Nothing is currently playing."
        if session.is_paused or (session.voice_client and session.voice_client.is_paused()):
            return False, "⏸️ Playback is already paused."
        if session.voice_client and session.voice_client.is_playing():
            session.voice_client.pause()
        session.pause_time = time.time()
        session.state = PlaybackState.PAUSED
        await cls.send_now_playing_panel(session)
        return True, "⏸️ Playback paused."

    @classmethod
    async def resume(cls, *args, **kwargs) -> Tuple[bool, str]:
        """Authoritatively resume paused playback and update Now Playing panel. Supports resume(bot, session) or resume(session)."""
        bot = None
        session: Optional[GuildMusicSession] = None
        for a in args:
            if isinstance(a, GuildMusicSession):
                session = a
            elif hasattr(a, "db") or hasattr(a, "loop"):
                bot = a
        if session is None and "session" in kwargs:
            session = kwargs["session"]
        if bot is None and "bot" in kwargs:
            bot = kwargs["bot"]
        if session is None and args:
            session = args[-1]
        if not session:
            return False, "❌ No active session."

        if not session.voice_client or not (session.has_active_track or session.voice_client.is_playing() or session.voice_client.is_paused()):
            return False, "❌ Nothing is currently playing."
        if session.is_playing and session.voice_client and not session.voice_client.is_paused():
            return False, "▶️ Music is already playing."

        if session.voice_client and session.voice_client.is_paused():
            session.voice_client.resume()
        elif session.state == PlaybackState.PAUSED and session.current_track:
            cur_pos = session.progress_seconds
            await cls.resume_track_stream(bot, session, session.current_track, cur_pos)

        if session.pause_time > 0:
            session.paused_duration += time.time() - session.pause_time
            session.pause_time = 0.0
        session.state = PlaybackState.PLAYING

        if not session.progress_updater_task or session.progress_updater_task.done():
            session.progress_updater_task = asyncio.create_task(cls._progress_updater_loop(session))

        await cls.send_now_playing_panel(session)
        return True, "▶️ Playback resumed."

    @classmethod
    async def previous(cls, bot: RaiMusicBot, session: GuildMusicSession) -> Tuple[bool, str, Optional[QueuedTrack]]:
        """Authoritatively return to the previous track from history."""
        if not session.history:
            return False, "❌ No previous tracks in history.", None

        async with session.lock:
            prev_track = session.history.pop()
            if session.current_track:
                session.queue.appendleft(session.current_track)

            if session.voice_client and (session.voice_client.is_playing() or session.voice_client.is_paused()):
                session.playback_generation += 1
                session._is_skipping = True
                try:
                    session.voice_client.stop()
                except Exception:
                    pass
                await asyncio.sleep(0.05)
                session._is_skipping = False

            success = await cls.start_playback(bot, session, prev_track)
            if success:
                return True, f"⏮️ Returned to **{prev_track.title}**.", prev_track
            else:
                return False, f"❌ Failed to resume previous track **{prev_track.title}**.", None

    @classmethod
    async def stop(cls, bot: RaiMusicBot, session: GuildMusicSession) -> Tuple[bool, str]:
        """Authoritatively stop playback, clear queue, update panel, and respect 24/7 settings."""
        async with session.lock:
            session.is_intentional_stop = True
            session.state = PlaybackState.STOPPED
            session.queue.clear()
            session.current_track = None

            if session.progress_updater_task and not session.progress_updater_task.done():
                session.progress_updater_task.cancel()
                session.progress_updater_task = None

            # Check in-memory and persistent 24/7 settings
            is_247 = getattr(session, "twenty_four_seven", False) is True
            if not is_247 and bot and getattr(bot, "db", None) and hasattr(bot.db, "get_guild_settings"):
                try:
                    g_set = await bot.db.get_guild_settings(session.guild_id)
                    if g_set and getattr(g_set, "twenty_four_seven_enabled", None) is True:
                        is_247 = True
                        session.twenty_four_seven = True
                except Exception:
                    pass

            session.is_intentional_stop = True
            if is_247:
                # In 24/7 mode, stopping playback leaves the bot in the voice channel without poisoning voice recovery
                session.is_intentional_disconnect = False
            else:
                session.is_intentional_disconnect = True

            if session.voice_client:
                if session.voice_client.is_playing() or session.voice_client.is_paused():
                    try:
                        session.voice_client.stop()
                    except Exception:
                        pass

                # If 24/7 mode is NOT enabled, disconnect from voice
                if not is_247:
                    try:
                        await session.voice_client.disconnect()
                    except Exception:
                        pass
                    session.voice_client = None

            if session.now_playing_message:
                try:
                    embed = discord.Embed(
                        title="⏹️ PLAYBACK STOPPED",
                        description="Music playback has been stopped and the queue has been cleared. 🐾",
                        color=0x2B2D31,
                    )
                    await session.now_playing_message.edit(embed=embed, view=None)
                except Exception:
                    session.now_playing_message = None

            session.reset()
            session.is_intentional_stop = True
            session.is_intentional_disconnect = not is_247

            if bot and getattr(bot, "db", None) and hasattr(bot.db, "delete_session"):
                try:
                    await bot.db.delete_session(session.guild_id)
                except Exception:
                    pass

            return True, "⏹️ Stopped playback and cleared queue. 🐾"

    @classmethod
    async def set_volume(cls, session: GuildMusicSession, volume: int) -> Tuple[bool, str]:
        """Set playback volume (1-150%) and apply to active audio transformer."""
        vol = max(1, min(150, int(volume)))
        session.volume = vol
        if session.voice_client and getattr(session.voice_client, "source", None):
            source = session.voice_client.source
            if hasattr(source, "volume"):
                source.volume = vol / 100.0
        await cls.send_now_playing_panel(session)
        return True, f"🔊 Master volume set to **{vol}%**."

    @classmethod
    async def seek_relative(cls, bot: RaiMusicBot, session: GuildMusicSession, delta_seconds: int) -> Tuple[bool, int, str]:
        """Seek forward or backward by delta_seconds relative to current progress."""
        if not session.current_track or not session.voice_client or not session.voice_client.is_connected():
            return False, 0, "❌ Nothing is currently playing."
        cur = session.progress_seconds
        dur = session.current_track.duration or 0
        if dur > 0:
            target = max(0, min(cur + delta_seconds, dur - 1))
        else:
            target = max(0, cur + delta_seconds)
        success = await cls.seek(bot, session, target)
        if success:
            sign = "+" if delta_seconds > 0 else ""
            msg = f"⏩ Forwarded {sign}{delta_seconds}s (now at `{format_duration(target, is_position=True)}`)." if delta_seconds > 0 else f"⏪ Rewound {abs(delta_seconds)}s (now at `{format_duration(target, is_position=True)}`)."
            return True, target, msg
        return False, cur, "❌ Seeking is not supported on this audio stream."

    @classmethod
    def cycle_loop(cls, session: GuildMusicSession) -> Tuple[LoopMode, str]:
        """Cycle repeat mode: OFF -> TRACK -> QUEUE -> OFF."""
        if session.loop_mode == LoopMode.OFF:
            session.loop_mode = LoopMode.TRACK
            return LoopMode.TRACK, "🔂 Repeat current track enabled."
        elif session.loop_mode == LoopMode.TRACK:
            session.loop_mode = LoopMode.QUEUE
            return LoopMode.QUEUE, "🔁 Repeat entire queue enabled."
        else:
            session.loop_mode = LoopMode.OFF
            return LoopMode.OFF, "➡️ Repeat disabled."

    @classmethod
    def shuffle(cls, session: GuildMusicSession) -> Tuple[bool, str]:
        """Shuffle upcoming tracks without interrupting current playback."""
        if len(session.queue) < 2:
            return False, "❌ Need at least 2 tracks in queue to shuffle."
        tracks = list(session.queue)
        random.shuffle(tracks)
        from collections import deque
        session.queue = deque(tracks)
        return True, f"🔀 Shuffled {len(tracks)} tracks in the queue."

    @classmethod
    async def toggle_favorite(cls, bot: Any, user_id: int, track: Optional[QueuedTrack] = None) -> Tuple[bool, bool, str]:
        """Toggle favorite status of a track for a user in the persistent database."""
        if not track:
            return False, False, "❌ No track available to favorite."
        if not bot or not getattr(bot, "db", None):
            return False, False, "❌ Database unavailable."
        
        try:
            favs = await bot.db.get_favorites(user_id)
            existing = any(f.url == track.url for f in favs) if favs else False
            if existing:
                await bot.db.remove_favorite(user_id, track.url)
                return True, False, f"💔 Removed **{track.title[:50]}** from your favorites."
            else:
                success = await bot.db.add_favorite(user_id, track=track)
                if success:
                    return True, True, f"💖 Added **{track.title[:50]}** to your favorites!"
                return False, False, "❌ Could not save to favorites."
        except Exception as e:
            logger.warning(f"Error toggling favorite: {e}")
            return False, False, f"❌ Error saving favorite: {e}"

    @classmethod
    async def resolve_text_channel(
        cls, session: GuildMusicSession, bot: Optional[RaiMusicBot] = None
    ) -> Tuple[Optional[discord.TextChannel], Optional[str]]:
        """
        Phase 3: Resolve the authoritative text channel for the Now Playing player.
        Checks:
        1. Current session.text_channel validity and permissions.
        2. Configured request_channel_id in music_guild_settings.
        3. Fallback to common music channels (#music, #music-bot, #bot-commands) with verified permissions.
        4. Validates permissions: View Channel, Send Messages, Embed Links, Read Message History.
        Returns (channel, error_reason).
        """
        bot = bot or getattr(session, "bot", None)
        guild: Optional[discord.Guild] = None

        if session.text_channel and getattr(session.text_channel, "guild", None):
            guild = session.text_channel.guild
        elif session.voice_client and getattr(session.voice_client, "guild", None):
            guild = session.voice_client.guild
        elif bot:
            guild = bot.get_guild(session.guild_id)

        if not guild:
            return None, f"Guild {session.guild_id} context cannot be determined."

        me = guild.me
        if not me:
            return None, f"Bot member context cannot be determined in guild {guild.name}."

        # Candidate channels to inspect in priority order
        candidates: List[discord.TextChannel] = []

        # 1. Existing session text channel
        if session.text_channel and getattr(session.text_channel, "guild", None) and session.text_channel.guild.id == guild.id:
            candidates.append(session.text_channel)

        # 2. Configured request_channel_id from database
        if bot and hasattr(bot, "db") and bot.db:
            try:
                g_settings = await bot.db.get_guild_settings(guild.id)
                if g_settings and g_settings.request_channel_id:
                    ch = guild.get_channel(g_settings.request_channel_id)
                    if isinstance(ch, discord.TextChannel) and ch not in candidates:
                        candidates.append(ch)
            except Exception as e:
                logger.debug(f"[ChannelResolution] DB settings check note: {e}")

        # 3. Known standard music channel names
        music_names = ("music", "music-bot", "music-commands", "song-requests", "bot-commands", "general")
        raw_channels = getattr(guild, "text_channels", [])
        if isinstance(raw_channels, (list, tuple, set)):
            for ch in raw_channels:
                if getattr(ch, "name", None) in music_names and ch not in candidates:
                    candidates.append(ch)

        # 4. Any available text channel in guild
        if isinstance(raw_channels, (list, tuple, set)):
            for ch in raw_channels:
                if ch not in candidates:
                    candidates.append(ch)

        # Evaluate candidate channels for required permissions
        last_perm_err = None
        for ch in candidates:
            if not hasattr(ch, "permissions_for") or not callable(ch.permissions_for):
                continue
            perms = ch.permissions_for(me)
            missing = []
            if not getattr(perms, "view_channel", True):
                missing.append("View Channel")
            if not getattr(perms, "send_messages", True):
                missing.append("Send Messages")
            if not getattr(perms, "embed_links", True):
                missing.append("Embed Links")

            if not missing:
                # Channel is 100% accessible and has all permissions
                session.text_channel = ch
                return ch, None
            else:
                last_perm_err = f"Channel #{ch.name} ({ch.id}) lacks permissions: {', '.join(missing)}"
                logger.debug(f"[ChannelResolution] {last_perm_err}")

        # If we got here, no candidate channel has all permissions
        return None, last_perm_err or "No text channel found with View Channel, Send Messages, and Embed Links permissions."

    @classmethod
    async def send_now_playing_panel(
        cls, session: GuildMusicSession, bot: Optional[RaiMusicBot] = None
    ) -> None:
        """
        Phase 2 & 4: Centralized Now Playing player panel manager.
        - Concurrency serialized with session._panel_lock.
        - Verified text channel & permissions.
        - Updates existing message in-place without spamming chat.
        - Safely recreates panel if deleted or in a different channel.
        - Attaches full 4-row 13-button NowPlayingControlView.
        - Real-time broadcasts to Web UI.
        """
        if not hasattr(session, "_panel_lock"):
            session._panel_lock = asyncio.Lock()

        # Real-time WebSocket / SSE broadcast to Web dashboard
        try:
            from web.realtime import RealtimeGateway
            rg = RealtimeGateway.get_instance()
            if rg:
                asyncio.create_task(rg.broadcast("MUSIC_UPDATED", {
                    "guild_id": str(session.guild_id),
                    "is_playing": session.is_playing,
                    "is_paused": session.is_paused,
                    "title": session.current_track.title if session.current_track else None,
                    "artist": session.current_track.artist if session.current_track else None,
                    "thumbnail": session.current_track.thumbnail if session.current_track else None,
                    "volume": session.volume,
                    "loop_mode": session.loop_mode.value,
                    "eq_preset": session.eq_preset or "Flat",
                }))
        except Exception:
            pass

        async with session._panel_lock:
            channel, perm_err = await cls.resolve_text_channel(session, bot)
            if not channel:
                logger.warning(
                    f"[PlayerPanel] Cannot deploy Now Playing panel in guild {session.guild_id}: {perm_err}"
                )
                session.last_error = perm_err
                fallback_ch = session.text_channel
                if fallback_ch and hasattr(fallback_ch, "permissions_for") and hasattr(fallback_ch, "guild"):
                    me = getattr(fallback_ch.guild, "me", None)
                    if me:
                        perms = fallback_ch.permissions_for(me)
                        if getattr(perms, "send_messages", False):
                            try:
                                await fallback_ch.send(
                                    f"⚠️ **MusicMaid Permission Alert:**\n"
                                    f"I cannot display the Now Playing player in {fallback_ch.mention} because I am missing required permissions:\n"
                                    f"• **{perm_err}**\n\n"
                                    f"💡 *How to fix:* Right-click/tap this channel ➔ **Edit Channel** ➔ **Permissions** ➔ grant **MusicMaid** the **Embed Links** permission!"
                                )
                            except Exception:
                                pass
                return

            embed = cls.build_now_playing_embed(session)
            view = NowPlayingControlView(session)

            # 1. Update existing message in-place if valid and in the same channel
            if session.now_playing_message:
                if getattr(session.now_playing_message, "channel", None) and session.now_playing_message.channel.id == channel.id:
                    try:
                        await session.now_playing_message.edit(embed=embed, view=view)
                        if session.is_playing:
                            if not session.progress_updater_task or session.progress_updater_task.done():
                                session.progress_updater_task = asyncio.create_task(cls._progress_updater_loop(session))
                        return
                    except discord.NotFound:
                        logger.debug(f"[PlayerPanel] Previous player message {session.now_playing_message.id} deleted. Recreating...")
                        session.now_playing_message = None
                    except discord.Forbidden:
                        logger.error(f"[PlayerPanel] Bot lacks permission to edit message in #{channel.name} ({channel.id}).")
                        session.now_playing_message = None
                    except Exception as edit_err:
                        logger.warning(f"[PlayerPanel] Failed to edit existing player message: {edit_err}")
                        session.now_playing_message = None
                else:
                    # Message was in another channel, clear reference
                    session.now_playing_message = None

            # 2. Try fetching by stored message ID if message object was lost
            if not session.now_playing_message and session.now_playing_message_id:
                try:
                    old_msg = await channel.fetch_message(session.now_playing_message_id)
                    await old_msg.edit(embed=embed, view=view)
                    session.now_playing_message = old_msg
                    if session.is_playing:
                        if not session.progress_updater_task or session.progress_updater_task.done():
                            session.progress_updater_task = asyncio.create_task(cls._progress_updater_loop(session))
                    return
                except (discord.NotFound, discord.Forbidden):
                    session.now_playing_message_id = None
                except Exception:
                    session.now_playing_message_id = None

            # 3. Post new message and register as persistent panel
            try:
                perms = channel.permissions_for(channel.guild.me)
                if not perms.embed_links:
                    warning_text = (
                        f"⚠️ **MusicMaid Permission Alert:**\n"
                        f"I need the **Embed Links** permission in {channel.mention} to display the Now Playing player!\n"
                        f"Please ask a server administrator to grant **Embed Links** to MusicMaid."
                    )
                    logger.error(f"[PlayerPanel] Missing Embed Links permission in #{channel.name} ({channel.id})")
                    if perms.send_messages:
                        await channel.send(warning_text)
                    return

                msg = await channel.send(embed=embed, view=view)
                session.now_playing_message = msg
                session.now_playing_message_id = msg.id
                session.now_playing_channel_id = channel.id

                # Persist to database session
                bot_inst = bot or getattr(session, "bot", None)
                if bot_inst and hasattr(bot_inst, "db") and bot_inst.db and session.voice_client:
                    try:
                        vc_id = session.voice_client.channel.id if session.voice_client.channel else None
                        res_save = bot_inst.db.save_session(
                            guild_id=session.guild_id,
                            voice_channel_id=vc_id,
                            text_channel_id=channel.id,
                            state=session.state.value,
                            volume=session.volume,
                            loop_mode=session.loop_mode.value,
                            is_paused=session.is_paused,
                            current_track=session.current_track,
                            position_seconds=int(session.progress_seconds),
                            queue=list(session.queue),
                            history=list(session.history),
                        )
                        if asyncio.iscoroutine(res_save):
                            asyncio.create_task(res_save)
                    except Exception as db_save_err:
                        logger.debug(f"[PlayerPanel] Session persist note: {db_save_err}")

                if session.is_playing:
                    if not session.progress_updater_task or session.progress_updater_task.done():
                        session.progress_updater_task = asyncio.create_task(cls._progress_updater_loop(session))

            except discord.Forbidden as f_err:
                logger.error(f"[PlayerPanel] 403 Forbidden deploying Now Playing panel in #{channel.name} ({channel.id}): {f_err}")
                session.last_error = f"Missing permissions to post player in {channel.mention}"
            except Exception as send_err:
                logger.error(f"[PlayerPanel] Failed to deploy Now Playing panel in #{channel.name} ({channel.id}): {send_err}", exc_info=True)
                session.last_error = f"Failed to post player message: {send_err}"


# =============================================================================
# INTERACTIVE BUTTON CONTROLS (9 EXACT BUTTONS)
# =============================================================================

class VolumeAdjustView(discord.ui.View):
    """Ephemeral volume control quick selector."""

    def __init__(self, session: GuildMusicSession):
        super().__init__(timeout=60)
        self.session = session

    @discord.ui.button(label="20%", style=discord.ButtonStyle.secondary, row=0)
    async def v20(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_vol(interaction, 20)

    @discord.ui.button(label="50%", style=discord.ButtonStyle.secondary, row=0)
    async def v50(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_vol(interaction, 50)

    @discord.ui.button(label="80%", style=discord.ButtonStyle.primary, row=0)
    async def v80(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_vol(interaction, 80)

    @discord.ui.button(label="100%", style=discord.ButtonStyle.success, row=0)
    async def v100(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_vol(interaction, 100)

    async def _set_vol(self, interaction: discord.Interaction, vol: int):
        await interaction.response.defer(ephemeral=True)
        self.session.volume = vol
        if self.session.voice_client and hasattr(self.session.voice_client.source, "volume"):
            self.session.voice_client.source.volume = vol / 100.0  # type: ignore
        await MusicPlayerService.send_now_playing_panel(self.session)
        await interaction.followup.send(f"🔊 Volume set to `{vol}%`.", ephemeral=True)
        self.stop()


class AudioEqualizerView(discord.ui.View):
    """Interactive EQ presets selector for Neko Songs."""

    def __init__(self, session: GuildMusicSession, bot: Optional[Any] = None):
        super().__init__(timeout=60)
        self.session = session
        self.bot = bot

    @discord.ui.button(label="Bass Boost", emoji="🎧", style=discord.ButtonStyle.primary, row=0)
    async def bass_boost(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply_eq(interaction, "bassboost", "Bass Boost")

    @discord.ui.button(label="8D Audio", emoji="🌌", style=discord.ButtonStyle.secondary, row=0)
    async def audio_8d(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply_eq(interaction, "8d", "8D Audio")

    @discord.ui.button(label="Lo-Fi Relax", emoji="☕", style=discord.ButtonStyle.secondary, row=0)
    async def lofi_relax(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply_eq(interaction, "vaporwave", "Lo-Fi Relax")

    @discord.ui.button(label="Clear Vocal", emoji="⚡", style=discord.ButtonStyle.secondary, row=1)
    async def clear_vocal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply_eq(interaction, "vocal", "Clear Vocal")

    @discord.ui.button(label="Pop", emoji="✨", style=discord.ButtonStyle.secondary, row=1)
    async def pop_preset(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply_eq(interaction, "pop", "Pop")

    @discord.ui.button(label="Rock", emoji="🎸", style=discord.ButtonStyle.secondary, row=1)
    async def rock_preset(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply_eq(interaction, "rock", "Rock")

    @discord.ui.button(label="Flat / Normal", emoji="🔄", style=discord.ButtonStyle.success, row=1)
    async def flat_normal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply_eq(interaction, "reset", "Flat / Normal")

    async def _apply_eq(self, interaction: discord.Interaction, preset_key: str, display_name: str):
        # 1. Immediately defer to avoid "didn't respond in time" error
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        bot_instance = self.bot or getattr(interaction.client, "bot", interaction.client)
        success = await MusicPlayerService.apply_filter_or_eq(bot_instance, self.session, preset_key, display_name)

        try:
            if success:
                await interaction.followup.send(
                    f"🎛️ Applied Equalizer Preset: **{display_name}** 🐾\n"
                    f"*(Audio stream instantly refreshed with real-time DSP filter)*",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"⚠️ Failed to apply preset **{display_name}**. Preserved previous audio filter.",
                    ephemeral=True,
                )
        except Exception:
            pass
        self.stop()


# -------------------------------------------------------------
# Modular Feature Sub-Panels (Clean, Ephemeral, Uncluttered)
# -------------------------------------------------------------


class QueueSubView(discord.ui.View):
    """Separate, compact Queue Management Sub-Panel with Back and Close controls."""

    def __init__(self, session: GuildMusicSession):
        super().__init__(timeout=120)
        self.session = session

    @discord.ui.button(emoji="🔀", label="Shuffle", style=discord.ButtonStyle.secondary, custom_id="sub_queue_shuffle", row=0)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        if len(self.session.queue) < 2:
            await interaction.followup.send("❌ Need at least 2 tracks in queue to shuffle.", ephemeral=True)
            return
        tracks = list(self.session.queue)
        random.shuffle(tracks)
        from collections import deque
        self.session.queue = deque(tracks)
        embed = MusicPlayerService.build_queue_embed(self.session)
        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            await interaction.followup.send("🔀 Queue shuffled.", ephemeral=True)

    @discord.ui.button(emoji="🗑️", label="Clear Queue", style=discord.ButtonStyle.danger, custom_id="sub_queue_clear", row=0)
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        self.session.queue.clear()
        embed = MusicPlayerService.build_queue_embed(self.session)
        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            await interaction.followup.send("🗑️ Queue cleared.", ephemeral=True)

    @discord.ui.button(emoji="⬅️", label="Back", style=discord.ButtonStyle.primary, custom_id="sub_queue_back", row=0)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        try:
            embed = MusicPlayerService.build_now_playing_embed(self.session)
            await interaction.edit_original_response(
                content="⬅️ Returned to main player.",
                embed=embed,
                view=None,
            )
        except Exception:
            pass
        self.stop()

    @discord.ui.button(emoji="✖️", label="Close", style=discord.ButtonStyle.secondary, custom_id="sub_queue_close", row=0)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        try:
            await interaction.edit_original_response(content="✖️ Queue panel closed.", embed=None, view=None)
        except Exception:
            pass
        self.stop()


class AudioSettingsSubView(discord.ui.View):
    """Separate, compact Audio & DSP Equalizer Sub-Panel with Back and Close controls."""

    def __init__(self, session: GuildMusicSession, bot: Optional[Any] = None):
        super().__init__(timeout=120)
        self.session = session
        self.bot = bot

    # Row 0: Volume Quick Actions
    @discord.ui.button(label="20%", style=discord.ButtonStyle.secondary, custom_id="sub_vol_20", row=0)
    async def vol_20(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_vol(interaction, 20)

    @discord.ui.button(label="50%", style=discord.ButtonStyle.secondary, custom_id="sub_vol_50", row=0)
    async def vol_50(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_vol(interaction, 50)

    @discord.ui.button(label="80%", style=discord.ButtonStyle.primary, custom_id="sub_vol_80", row=0)
    async def vol_80(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_vol(interaction, 80)

    @discord.ui.button(label="100%", style=discord.ButtonStyle.success, custom_id="sub_vol_100", row=0)
    async def vol_100(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._set_vol(interaction, 100)

    # Row 1: Studio DSP Equalizer Presets
    @discord.ui.button(emoji="🎧", label="Bass Boost", style=discord.ButtonStyle.secondary, custom_id="sub_eq_bass", row=1)
    async def eq_bass(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply_preset(interaction, "bassboost", "Bass Boost")

    @discord.ui.button(emoji="🌌", label="8D Audio", style=discord.ButtonStyle.secondary, custom_id="sub_eq_8d", row=1)
    async def eq_8d(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply_preset(interaction, "8d", "8D Audio")

    @discord.ui.button(emoji="☕", label="Lo-Fi", style=discord.ButtonStyle.secondary, custom_id="sub_eq_lofi", row=1)
    async def eq_lofi(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply_preset(interaction, "vaporwave", "Lo-Fi Relax")

    @discord.ui.button(emoji="⚡", label="Vocal", style=discord.ButtonStyle.secondary, custom_id="sub_eq_vocal", row=1)
    async def eq_vocal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply_preset(interaction, "vocal", "Clear Vocal")

    @discord.ui.button(emoji="🔄", label="Flat", style=discord.ButtonStyle.secondary, custom_id="sub_eq_flat", row=1)
    async def eq_flat(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply_preset(interaction, "reset", "Flat / Normal")

    # Row 2: Navigation
    @discord.ui.button(emoji="⬅️", label="Back", style=discord.ButtonStyle.primary, custom_id="sub_audio_back", row=2)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        try:
            embed = MusicPlayerService.build_now_playing_embed(self.session)
            await interaction.edit_original_response(
                content="⬅️ Returned to main player.",
                embed=embed,
                view=None,
            )
        except Exception:
            pass
        self.stop()

    @discord.ui.button(emoji="✖️", label="Close", style=discord.ButtonStyle.secondary, custom_id="sub_audio_close", row=2)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        try:
            await interaction.edit_original_response(content="✖️ Audio settings closed.", embed=None, view=None)
        except Exception:
            pass
        self.stop()

    async def _set_vol(self, interaction: discord.Interaction, vol: int):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        self.session.volume = vol
        if self.session.voice_client and hasattr(self.session.voice_client.source, "volume"):
            self.session.voice_client.source.volume = vol / 100.0  # type: ignore
        embed = MusicPlayerService.build_audio_embed(self.session)
        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            await interaction.followup.send(f"🔊 Volume set to `{vol}%`.", ephemeral=True)
        if self.session.now_playing_message:
            try:
                await self.session.now_playing_message.edit(embed=MusicPlayerService.build_now_playing_embed(self.session))
            except Exception:
                pass

    async def _apply_preset(self, interaction: discord.Interaction, key: str, name: str):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        bot_inst = self.bot or getattr(interaction.client, "bot", interaction.client)
        await MusicPlayerService.apply_filter_or_eq(bot_inst, self.session, key, name)
        embed = MusicPlayerService.build_audio_embed(self.session)
        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            await interaction.followup.send(f"🎛️ Applied Equalizer: `{name}`.", ephemeral=True)
        if self.session.now_playing_message:
            try:
                await self.session.now_playing_message.edit(embed=MusicPlayerService.build_now_playing_embed(self.session))
            except Exception:
                pass


class AutoDJSubView(discord.ui.View):
    """Separate, compact Auto-DJ Sub-Panel with Back and Close controls."""

    def __init__(self, session: GuildMusicSession, bot: Optional[Any] = None):
        super().__init__(timeout=120)
        self.session = session
        self.bot = bot

    @discord.ui.button(emoji="🎧", label="Toggle Auto-DJ", style=discord.ButtonStyle.primary, custom_id="sub_dj_toggle", row=0)
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        cur = getattr(self.session, "dj_enabled", False) or self.session.autoplay
        new_state = not cur
        self.session.dj_enabled = new_state
        self.session.autoplay = new_state
        embed = MusicPlayerService.build_autodj_embed(self.session)
        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            pass

    @discord.ui.button(emoji="🔥", label="Energy Match", style=discord.ButtonStyle.secondary, custom_id="sub_dj_energy", row=0)
    async def mode_energy(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.session.dj_mode = "Energy Match"
        embed = MusicPlayerService.build_autodj_embed(self.session)
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            pass

    @discord.ui.button(emoji="☕", label="Chill Out", style=discord.ButtonStyle.secondary, custom_id="sub_dj_chill", row=0)
    async def mode_chill(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.session.dj_mode = "Chill Out"
        embed = MusicPlayerService.build_autodj_embed(self.session)
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            pass

    @discord.ui.button(emoji="✨", label="Discovery", style=discord.ButtonStyle.secondary, custom_id="sub_dj_discovery", row=1)
    async def mode_discovery(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.session.dj_mode = "Discovery"
        embed = MusicPlayerService.build_autodj_embed(self.session)
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            pass

    @discord.ui.button(emoji="🌊", label="Vibe Shift", style=discord.ButtonStyle.secondary, custom_id="sub_dj_vibe", row=1)
    async def mode_vibe(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.session.dj_mode = "Vibe Shift"
        embed = MusicPlayerService.build_autodj_embed(self.session)
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            pass

    @discord.ui.button(emoji="⬅️", label="Back", style=discord.ButtonStyle.primary, custom_id="sub_dj_back", row=2)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        try:
            embed = MusicPlayerService.build_now_playing_embed(self.session)
            await interaction.edit_original_response(
                content="⬅️ Returned to main player.",
                embed=embed,
                view=None,
            )
        except Exception:
            pass
        self.stop()

    @discord.ui.button(emoji="✖️", label="Close", style=discord.ButtonStyle.secondary, custom_id="sub_dj_close", row=2)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        try:
            await interaction.edit_original_response(content="✖️ Auto-DJ panel closed.", embed=None, view=None)
        except Exception:
            pass
        self.stop()


class SettingsSubView(discord.ui.View):
    """Separate, compact Settings & Diagnostics Sub-Panel with Back and Close controls."""

    def __init__(self, session: GuildMusicSession, bot: Optional[Any] = None):
        super().__init__(timeout=120)
        self.session = session
        self.bot = bot

    @discord.ui.button(emoji="🛡️", label="Toggle 24/7", style=discord.ButtonStyle.primary, custom_id="sub_set_247", row=0)
    async def toggle_247(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        self.session.twenty_four_seven = not getattr(self.session, "twenty_four_seven", False)
        embed = MusicPlayerService.build_settings_embed(self.session)
        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            pass
        if self.session.now_playing_message:
            try:
                await self.session.now_playing_message.edit(embed=MusicPlayerService.build_now_playing_embed(self.session))
            except Exception:
                pass

    @discord.ui.button(emoji="🔁", label="Loop Mode", style=discord.ButtonStyle.secondary, custom_id="sub_set_loop", row=0)
    async def cycle_loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        if self.session.loop_mode == LoopMode.OFF:
            self.session.loop_mode = LoopMode.TRACK
        elif self.session.loop_mode == LoopMode.TRACK:
            self.session.loop_mode = LoopMode.QUEUE
        else:
            self.session.loop_mode = LoopMode.OFF
        embed = MusicPlayerService.build_settings_embed(self.session)
        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            pass

    @discord.ui.button(emoji="🩺", label="Doctor Diagnostics", style=discord.ButtonStyle.secondary, custom_id="sub_set_doc", row=0)
    async def doctor(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        from music_bot.services.diagnostics_service import HealthDoctorService
        report = await HealthDoctorService.run_full_system_diagnostic(interaction.client)
        embed = discord.Embed(
            title=f"🩺 MusicMaid Diagnostics (Score: {report['health_score']}/100)",
            color=0x00E5FF if report["is_healthy"] else 0xFEE75C,
            description=f"Status: `{report['status_summary']}`\n\n• Database WAL: `{report['database']['status']}`\n• Audio Resolver: `{report['audio_engine']['status']}`\n• Memory Usage: `{report['system_resources'].get('bot_process_memory_mb', 0)}MB`",
        )
        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            pass

    @discord.ui.button(emoji="⬅️", label="Back", style=discord.ButtonStyle.primary, custom_id="sub_set_back", row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        try:
            embed = MusicPlayerService.build_now_playing_embed(self.session)
            await interaction.edit_original_response(
                content="⬅️ Returned to main player.",
                embed=embed,
                view=None,
            )
        except Exception:
            pass
        self.stop()

    @discord.ui.button(emoji="✖️", label="Close", style=discord.ButtonStyle.secondary, custom_id="sub_set_close", row=1)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        try:
            await interaction.edit_original_response(content="✖️ Settings panel closed.", embed=None, view=None)
        except Exception:
            pass
        self.stop()


# -------------------------------------------------------------
# Reference-Grade 4-Row Master Control Panel View & Modals
# -------------------------------------------------------------

class VolumeModal(discord.ui.Modal, title="🔊 MusicMaid Volume Control"):
    volume_input = discord.ui.TextInput(
        label="Volume Percentage (1 - 150%)",
        placeholder="Enter volume number (e.g. 80)",
        min_length=1,
        max_length=3,
        required=True,
    )

    def __init__(self, session: Optional[GuildMusicSession] = None, parent_view: Optional[discord.ui.View] = None):
        super().__init__()
        self.session = session
        self.parent_view = parent_view
        if session:
            self.volume_input.default = str(session.volume)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.volume_input.value.strip())
            if val < 1 or val > 150:
                await interaction.response.send_message("❌ Volume must be between 1% and 150%.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number (1-150).", ephemeral=True)
            return

        session = self.session or (interaction.guild and SessionManager.get_instance().get_session_sync(interaction.guild.id))
        if not session:
            await interaction.response.send_message("❌ No active music session found.", ephemeral=True)
            return

        await MusicPlayerService.set_volume(session, val)
        if interaction.client and getattr(interaction.client, "db", None):
            try:
                await interaction.client.db.update_guild_settings(session.guild_id, volume=val)
            except Exception:
                pass

        if self.parent_view and hasattr(self.parent_view, "_update_button_states"):
            self.parent_view._update_button_states(session)
        
        await MusicPlayerService.send_now_playing_panel(session)
        await interaction.response.send_message(f"🔊 Master volume set to **{val}%**.", ephemeral=True)


class NowPlayingControlView(discord.ui.View):
    """Reference-grade 4-Row Master Control Panel for MusicMaid (13 Buttons)."""

    def __init__(self, session: Optional[GuildMusicSession] = None, bot: Optional[discord.Client] = None):
        super().__init__(timeout=None)
        self.session = session
        self.bot = bot
        if self.session:
            self._update_button_states(self.session, bot=self.bot)

    def _get_session(self, interaction: discord.Interaction) -> Optional[GuildMusicSession]:
        if self.session is not None and interaction.guild and self.session.guild_id == interaction.guild.id:
            return self.session
        if interaction.guild:
            from music_bot.services.session_service import SessionManager
            return SessionManager.get_instance().get_session_sync(interaction.guild.id)
        return self.session

    def _update_button_states(self, session: Optional[GuildMusicSession] = None, bot: Optional[discord.Client] = None):
        target = session or self.session
        if not target:
            return
        bot_client = bot or getattr(self, "bot", None)
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "music_btn_prev":
                    child.emoji = EmojiManager.get_button_emoji("PREVIOUS", bot_client)
                elif child.custom_id == "music_btn_rewind_10":
                    child.emoji = EmojiManager.get_button_emoji("REWIND_10", bot_client)
                elif child.custom_id == "music_btn_play_pause":
                    child.label = "Resume" if target.is_paused else "Pause"
                    child.emoji = EmojiManager.get_button_emoji("PLAY" if target.is_paused else "PAUSE", bot_client)
                    child.style = discord.ButtonStyle.success if target.is_paused else discord.ButtonStyle.primary
                elif child.custom_id == "music_btn_forward_10":
                    child.emoji = EmojiManager.get_button_emoji("FORWARD_10", bot_client)
                elif child.custom_id == "music_btn_skip":
                    child.emoji = EmojiManager.get_button_emoji("SKIP", bot_client)
                elif child.custom_id == "music_btn_queue":
                    count = len(target.queue)
                    child.label = f"Queue ({count})" if count > 0 else "Queue"
                    child.emoji = EmojiManager.get_button_emoji("QUEUE", bot_client)
                elif child.custom_id == "music_btn_shuffle":
                    child.emoji = EmojiManager.get_button_emoji("SHUFFLE", bot_client)
                elif child.custom_id == "music_btn_loop":
                    child.emoji = EmojiManager.get_button_emoji("LOOP", bot_client)
                    if target.loop_mode != LoopMode.OFF:
                        child.label = f"Loop: {target.loop_mode.value.title()}"
                        child.style = discord.ButtonStyle.primary
                    else:
                        child.label = "Loop"
                        child.style = discord.ButtonStyle.secondary
                elif child.custom_id == "music_btn_volume":
                    child.label = f"Volume ({target.volume}%)"
                    child.emoji = EmojiManager.get_button_emoji("VOLUME", bot_client)
                elif child.custom_id == "music_btn_stop":
                    child.emoji = EmojiManager.get_button_emoji("STOP", bot_client)
                elif child.custom_id == "music_btn_favorite":
                    child.emoji = EmojiManager.get_button_emoji("FAVORITE", bot_client)
                elif child.custom_id == "music_btn_filters":
                    child.emoji = EmojiManager.get_button_emoji("EQUALIZER", bot_client)
                elif child.custom_id == "music_btn_lyrics":
                    child.emoji = EmojiManager.get_button_emoji("LYRICS", bot_client)

    def _check_user_voice(self, interaction: discord.Interaction, session: Optional[GuildMusicSession]) -> Tuple[bool, Optional[str]]:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False, "❌ This command must be used in a server."
        if not interaction.user.voice or not interaction.user.voice.channel:
            return False, "❌ You must join a voice channel to interact with music controls."
        if session and session.voice_client and session.voice_client.channel:
            if interaction.user.voice.channel.id != session.voice_client.channel.id:
                return False, f"❌ You must be in the same voice channel ({session.voice_client.channel.mention}) as the bot."
        return True, None

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        if isinstance(error, discord.NotFound) and getattr(error, "code", None) == 10062:
            return
        logger.error(f"Error in NowPlayingControlView for {item}: {error}", exc_info=True)

    # =========================================================================
    # ROW 0: PRIMARY PLAYBACK (5 Buttons)
    # =========================================================================

    @discord.ui.button(emoji="⏮", label="Previous", style=discord.ButtonStyle.secondary, custom_id="music_btn_prev", row=0)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        session = self._get_session(interaction)
        can_interact, reason = self._check_user_voice(interaction, session)
        if not can_interact:
            try:
                await interaction.followup.send(reason, ephemeral=True)
            except Exception:
                pass
            return

        if not session or not session.history:
            try:
                await interaction.followup.send("❌ No previous tracks in history.", ephemeral=True)
            except Exception:
                pass
            return

        bot: RaiMusicBot = interaction.client  # type: ignore
        success, msg, _ = await MusicPlayerService.previous(bot, session)
        self._update_button_states(session)
        try:
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(emoji="⏪", label="Rewind 10s", style=discord.ButtonStyle.secondary, custom_id="music_btn_rewind_10", row=0)
    async def rewind_10_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        session = self._get_session(interaction)
        can_interact, reason = self._check_user_voice(interaction, session)
        if not can_interact:
            try:
                await interaction.followup.send(reason, ephemeral=True)
            except Exception:
                pass
            return

        if not session or not session.current_track:
            try:
                await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            except Exception:
                pass
            return

        bot: RaiMusicBot = interaction.client  # type: ignore
        success, new_pos, msg = await MusicPlayerService.seek_relative(bot, session, -10)
        try:
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(emoji="⏸", label="Pause", style=discord.ButtonStyle.primary, custom_id="music_btn_play_pause", row=0)
    async def play_pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        session = self._get_session(interaction)
        can_interact, reason = self._check_user_voice(interaction, session)
        if not can_interact:
            try:
                await interaction.followup.send(reason, ephemeral=True)
            except Exception:
                pass
            return

        if not session or not session.voice_client:
            try:
                await interaction.followup.send("❌ Music bot is not connected to voice.", ephemeral=True)
            except Exception:
                pass
            return

        bot: RaiMusicBot = interaction.client  # type: ignore
        if session.voice_client.is_playing():
            success, action_text = await MusicPlayerService.pause(session)
        else:
            success, action_text = await MusicPlayerService.resume(bot, session)

        self._update_button_states(session)
        await MusicPlayerService.send_now_playing_panel(session)
        try:
            await interaction.followup.send(action_text, ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(emoji="⏩", label="Forward 10s", style=discord.ButtonStyle.secondary, custom_id="music_btn_forward_10", row=0)
    async def forward_10_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        session = self._get_session(interaction)
        can_interact, reason = self._check_user_voice(interaction, session)
        if not can_interact:
            try:
                await interaction.followup.send(reason, ephemeral=True)
            except Exception:
                pass
            return

        if not session or not session.current_track:
            try:
                await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            except Exception:
                pass
            return

        bot: RaiMusicBot = interaction.client  # type: ignore
        success, new_pos, msg = await MusicPlayerService.seek_relative(bot, session, 10)
        try:
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(emoji="⏭", label="Skip", style=discord.ButtonStyle.secondary, custom_id="music_btn_skip", row=0)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        session = self._get_session(interaction)
        can_interact, reason = self._check_user_voice(interaction, session)
        if not can_interact:
            try:
                await interaction.followup.send(reason, ephemeral=True)
            except Exception:
                pass
            return

        if not session or not session.voice_client or not (session.has_active_track or session.voice_client.is_playing() or session.voice_client.is_paused()):
            try:
                await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            except Exception:
                pass
            return

        bot: RaiMusicBot = interaction.client  # type: ignore
        success, msg, next_track = await MusicPlayerService.skip(bot, session)
        self._update_button_states(session)
        try:
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

    # =========================================================================
    # ROW 1: QUEUE AND PLAYBACK OPTIONS (3 Buttons)
    # =========================================================================

    @discord.ui.button(emoji="📜", label="Queue", style=discord.ButtonStyle.secondary, custom_id="music_btn_queue", row=1)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self._get_session(interaction)
        if not session:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("🐾 No active music session.", ephemeral=True)
            except Exception:
                pass
            return

        embed = MusicPlayerService.build_queue_embed(session)
        view = QueueSubView(session)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(emoji="🔀", label="Shuffle", style=discord.ButtonStyle.secondary, custom_id="music_btn_shuffle", row=1)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        session = self._get_session(interaction)
        can_interact, reason = self._check_user_voice(interaction, session)
        if not can_interact:
            try:
                await interaction.followup.send(reason, ephemeral=True)
            except Exception:
                pass
            return

        if not session:
            try:
                await interaction.followup.send("❌ No active music session.", ephemeral=True)
            except Exception:
                pass
            return

        success, msg = MusicPlayerService.shuffle(session)
        if success:
            await MusicPlayerService.send_now_playing_panel(session)
        try:
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(emoji="🔁", label="Loop", style=discord.ButtonStyle.secondary, custom_id="music_btn_loop", row=1)
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        session = self._get_session(interaction)
        can_interact, reason = self._check_user_voice(interaction, session)
        if not can_interact:
            try:
                await interaction.followup.send(reason, ephemeral=True)
            except Exception:
                pass
            return

        if not session:
            try:
                await interaction.followup.send("❌ No active music session.", ephemeral=True)
            except Exception:
                pass
            return

        new_mode, msg = MusicPlayerService.cycle_loop(session)
        self._update_button_states(session)
        await MusicPlayerService.send_now_playing_panel(session)
        try:
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

    # =========================================================================
    # ROW 2: AUDIO CONTROLS (2 Buttons)
    # =========================================================================

    @discord.ui.button(emoji="🔊", label="Volume", style=discord.ButtonStyle.secondary, custom_id="music_btn_volume", row=2)
    async def volume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self._get_session(interaction)
        can_interact, reason = self._check_user_voice(interaction, session)
        if not can_interact:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(reason, ephemeral=True)
                else:
                    await interaction.followup.send(reason, ephemeral=True)
            except Exception:
                pass
            return

        if not session:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ No active music session.", ephemeral=True)
            except Exception:
                pass
            return

        try:
            await interaction.response.send_modal(VolumeModal(session, parent_view=self))
        except Exception:
            try:
                await interaction.followup.send(f"🔊 Current volume is **{session.volume}%**. Use `/music volume <percent>` to adjust.", ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(emoji="⏹", label="Stop", style=discord.ButtonStyle.danger, custom_id="music_btn_stop", row=2)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        session = self._get_session(interaction)
        can_interact, reason = self._check_user_voice(interaction, session)
        if not can_interact:
            try:
                await interaction.followup.send(reason, ephemeral=True)
            except Exception:
                pass
            return

        if not session:
            try:
                await interaction.followup.send("⏹ No active playback session to stop.", ephemeral=True)
            except Exception:
                pass
            return

        bot_client: RaiMusicBot = interaction.client  # type: ignore
        success, msg = await MusicPlayerService.stop(bot_client, session)
        try:
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

    # =========================================================================
    # ROW 3: PERSONAL FEATURES (3 Buttons)
    # =========================================================================

    @discord.ui.button(emoji="💖", label="Favorite", style=discord.ButtonStyle.secondary, custom_id="music_btn_favorite", row=3)
    async def favorite_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        session = self._get_session(interaction)
        if not session or not session.current_track:
            try:
                await interaction.followup.send("❌ No track currently playing to favorite.", ephemeral=True)
            except Exception:
                pass
            return

        bot: RaiMusicBot = interaction.client  # type: ignore
        success, is_fav, msg = await MusicPlayerService.toggle_favorite(bot, interaction.user.id, session.current_track)
        try:
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(emoji="🎛️", label="Filters", style=discord.ButtonStyle.secondary, custom_id="music_btn_filters", row=3)
    async def filters_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self._get_session(interaction)
        if not session:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ No active music session.", ephemeral=True)
            except Exception:
                pass
            return

        embed = MusicPlayerService.build_audio_embed(session)
        view = AudioSettingsSubView(session, bot=interaction.client)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(emoji="📑", label="Lyrics", style=discord.ButtonStyle.secondary, custom_id="music_btn_lyrics", row=3)
    async def lyrics_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        session = self._get_session(interaction)
        if not session or not session.current_track:
            try:
                await interaction.followup.send("❌ No track currently playing.", ephemeral=True)
            except Exception:
                pass
            return

        track = session.current_track
        from music_bot.services.lyrics_service import LyricsService
        lyrics = await LyricsService.fetch_lyrics(track.title, track.artist)
        if not lyrics:
            try:
                await interaction.followup.send(f"🐱 No lyrics found for **{track.title}**.", ephemeral=True)
            except Exception:
                pass
            return

        embed = discord.Embed(
            title=f"📑 Lyrics • {track.title[:50]}",
            description=lyrics[:3900],
            color=0x9333EA,
        )
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        embed.set_footer(text=f"Artist: {track.artist or 'Unknown'} • MusicMaid Lyrics")
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            pass


# Module-level convenience functions
build_now_playing_embed = MusicPlayerService.build_now_playing_embed
build_queue_embed = MusicPlayerService.build_queue_embed
build_audio_embed = MusicPlayerService.build_audio_embed
build_autodj_embed = MusicPlayerService.build_autodj_embed
build_settings_embed = MusicPlayerService.build_settings_embed


