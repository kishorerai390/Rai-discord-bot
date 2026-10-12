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
from music_bot.services.resolver_service import FFMPEG_OPTIONS, AudioResolver
from music_bot.services.session_service import GuildMusicSession, LoopMode, PlaybackState, SessionManager

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
    """Audio source wrapper ensuring verified first frame is preserved and delivered without frame loss."""

    def __init__(self, original: discord.AudioSource, first_frame: bytes):
        self.original = original
        self.first_frame: Optional[bytes] = first_frame

    def read(self) -> bytes:
        if self.first_frame is not None:
            frame = self.first_frame
            self.first_frame = None
            return frame
        return self.original.read()

    def is_opus(self) -> bool:
        return self.original.is_opus()

    def cleanup(self) -> None:
        self.original.cleanup()


class MusicPlayerService:
    """High-level audio playback and queue transition coordinator."""

    @classmethod
    async def start_playback(
        cls, bot: RaiMusicBot, session: GuildMusicSession, track: QueuedTrack
    ) -> bool:
        """Start playing track on session's voice client."""
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
            # Create FFmpeg audio source
            ffmpeg_opts = dict(FFMPEG_OPTIONS)
            if session.audio_filter:
                ffmpeg_opts["options"] = f"-vn {session.audio_filter}"
            audio_source = discord.FFmpegPCMAudio(track.stream_url, **ffmpeg_opts)
            volume_transformer = discord.PCMVolumeTransformer(
                audio_source, volume=norm_vol
            )

            # Validate that audio source actually produces valid PCM audio frames
            loop = asyncio.get_running_loop()
            first_frame: Optional[bytes] = None
            try:
                first_frame = await asyncio.wait_for(
                    loop.run_in_executor(None, volume_transformer.read),
                    timeout=3.5,
                )
            except Exception as read_err:
                logger.warning(f"Initial frame read failed for '{track.title}': {read_err}")
                first_frame = b""

            if not first_frame:
                logger.warning(f"Audio source produced empty audio for '{track.title}' (stream URL may be stale/expired). Attempting fresh re-resolution...")
                try:
                    volume_transformer.cleanup()
                except Exception:
                    pass

                fresh = await AudioResolver.resolve_track(track.url or track.title, track.requester_id, track.requester_name)
                if fresh and fresh.stream_url:
                    track.stream_url = fresh.stream_url
                    audio_source = discord.FFmpegPCMAudio(track.stream_url, **ffmpeg_opts)
                    volume_transformer = discord.PCMVolumeTransformer(audio_source, volume=norm_vol)
                    try:
                        first_frame = await asyncio.wait_for(
                            loop.run_in_executor(None, volume_transformer.read),
                            timeout=3.5,
                        )
                    except Exception:
                        first_frame = b""

                if not first_frame:
                    try:
                        volume_transformer.cleanup()
                    except Exception:
                        pass
                    session.state = PlaybackState.ERROR
                    session.last_error = f"Audio source produced no sound for '{track.title}'."
                    if session.text_channel:
                        try:
                            await session.text_channel.send(
                                embed=discord.Embed(
                                    title="❌ NO AUDIO STREAM",
                                    description=f"FFmpeg received no audio data for **{track.title}** (stream blocked or unavailable).\nSkipping to next track...",
                                    color=0xED4245,
                                )
                            )
                        except Exception:
                            pass
                    await cls.handle_track_finished(bot, session)
                    return False

            playable_source = ValidatedAudioSource(volume_transformer, first_frame)

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
                ):
                    return
                if session.playback_generation != current_generation:
                    logger.debug(f"Ignoring superseded playback callback (gen {current_generation} vs {session.playback_generation})")
                    return
                if error:
                    session.last_error = f"Audio playback error: {error}"
                    logger.error(f"Playback error in guild {session.guild_id}: {error}", exc_info=True)

                # Mid-song stream auto-recovery for premature stream failures
                elapsed = session.progress_seconds
                duration = track.duration if track else 0
                retries = getattr(track, "_retry_count", 0)
                if (
                    not getattr(session, "_is_skipping", False)
                    and error
                    and duration > 30
                    and elapsed < duration - 15
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

            session.voice_client.play(playable_source, after=after_playback)
            session.state = PlaybackState.PLAYING

            # Launch real-time progress bar updater loop (every 5 seconds)
            if session.progress_updater_task and not session.progress_updater_task.done():
                session.progress_updater_task.cancel()
            session.progress_updater_task = asyncio.create_task(cls._progress_updater_loop(session))

            # Auto-precache lyrics in background for instant /lyrics responses
            try:
                from music_bot.services.lyrics_service import LyricsService
                LyricsService.precache_lyrics(track.title, track.artist)
            except Exception:
                pass

            # Record playback to database history & persist active session (Feature 109)
            if bot.db:
                asyncio.create_task(
                    bot.db.record_history(
                        session.guild_id,
                        track.title,
                        track.url,
                        track.artist,
                        track.requester_id,
                    )
                )
                vc_id = session.voice_client.channel.id if session.voice_client and session.voice_client.channel else None
                text_id = session.text_channel.id if session.text_channel else None
                asyncio.create_task(
                    bot.db.save_session(
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
                )

            # Deploy or update Now Playing embed panel in the designated text channel
            if session.text_channel:
                asyncio.create_task(cls.send_now_playing_panel(session))

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
            resume_before = f"-ss {start_seconds} {base_before}".strip()

            ffmpeg_opts = {"before_options": resume_before, "options": "-vn"}
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
                    timeout=3.5,
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
                            timeout=3.5,
                        )
                    except Exception:
                        first_frame = b""

            if not first_frame:
                logger.error(f"Failed to resume stream for '{track.title}': No audio data decoded.")
                session.state = PlaybackState.ERROR
                session.last_error = f"Audio source produced no sound for '{track.title}' during stream resume."
                await cls.handle_track_finished(bot, session)
                return False

            playable_source = ValidatedAudioSource(volume_transformer, first_frame)

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

        async with session.lock:
            if getattr(session, "_is_skipping", False):
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
                dj_settings = await bot.db.get_dj_settings(session.guild_id)
                if dj_settings.enabled or getattr(session, "dj_enabled", False) or session.autoplay:
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
        """Construct official Neko Songs Now Playing embed with progress bar and metadata."""
        track = session.current_track
        if not track:
            return discord.Embed(
                title="🎶 NOW PLAYING",
                description="*No music is currently playing in this server.*",
                color=0x0B0E14,
            )

        elapsed = session.elapsed_seconds
        total = track.duration or 0
        is_active_play = session.is_playing
        if total > 0:
            remaining = max(0, total - elapsed)
            end_ts = int(time.time() + remaining)
            time_suffix = f" • Ends <t:{end_ts}:R>" if is_active_play else ""
            progress_str = f"{format_duration(elapsed, is_position=True)} / {format_duration(total)} (-{format_duration(remaining)}){time_suffix}"
            progress_bar = create_progress_bar(elapsed, total)
        else:
            progress_str = f"{format_duration(elapsed, is_position=True)} / 🔴 LIVE"
            progress_bar = "🔘──────────────"

        is_server_muted = False
        if session.voice_client and session.voice_client.guild and session.voice_client.guild.me:
            me = session.voice_client.guild.me
            if me.voice and getattr(me.voice, "mute", False):
                is_server_muted = True

        if session.is_playing:
            status_text = "🟢 Playing"
        elif session.is_paused or session.state == PlaybackState.PAUSED:
            status_text = "⏸️ Paused"
        elif session.state in (PlaybackState.LOADING, PlaybackState.SEARCHING, PlaybackState.RESOLVING):
            status_text = "⏳ Buffering"
        elif session.state == PlaybackState.RECOVERING:
            status_text = "🔄 Recovering"
        elif session.state == PlaybackState.ERROR:
            status_text = "❌ Error"
        else:
            status_text = "⏹️ Idle"

        if is_server_muted:
            status_text += " (⚠️ Server Muted)"

        requester_str = f"<@{track.requester_id}>" if track.requester_id else track.requester_name

        # Feature 94: Cyber Dialogue Morning & Evening Greeting Shifts
        utc_h = datetime.now(timezone.utc).hour
        if 5 <= utc_h < 12:
            time_badge = "Morning Vibes ☕"
        elif 12 <= utc_h < 18:
            time_badge = "Afternoon Groove 🎵"
        elif 18 <= utc_h < 23:
            time_badge = "Evening Gaming 🎮"
        else:
            time_badge = "Midnight Lounge 🌌"

        preset_name = session.eq_preset if session.eq_preset else "Flat"
        is_247_str = "Active 🛡️" if session.twenty_four_seven else "Off"
        is_autodj_on = getattr(session, "dj_enabled", False) or session.autoplay
        is_autodj_str = "ON 🎧" if is_autodj_on else "OFF"
        recovery_line = f"\n• **Recovery:** `{session.recovery_status}`" if getattr(session, "recovery_status", None) else ""
        error_line = f"\n• **Error:** `{session.last_error[:80]}`" if session.state == PlaybackState.ERROR and session.last_error else ""

        if session.queue:
            next_info_line = f"\n• **Next Track:** `{session.queue[0].title[:35]}` *(Manual Queue)*"
        elif is_autodj_on:
            next_info_line = "\n• **Next Track:** `Auto-DJ Recommendation` 🎧"
        else:
            next_info_line = ""

        embed_color = 0xED4245 if session.state == PlaybackState.ERROR else (0x00E5FF if session.is_playing else 0x9B59B6)

        embed = discord.Embed(
            title="🎶 NOW PLAYING",
            description=(
                f"*{time_badge}*\n\n"
                f"### [{track.title}]({track.url})\n"
                f"👤 **Artist:** `{track.artist}`\n\n"
                f"**Progress:**\n`{progress_bar}` `{progress_str}`\n\n"
                f"• **Requested by:** {requester_str}\n"
                f"• **Volume:** `{session.volume}%` • **Status:** {status_text}\n"
                f"• **Queue:** `{len(session.queue)} tracks` • **Loop:** `{session.loop_mode.value.title()}`\n"
                f"• **Filter:** `{preset_name}` • **Auto-DJ:** `{is_autodj_str}` • **24/7:** `{is_247_str}`"
                f"{next_info_line}{recovery_line}{error_line}"
            ),
            color=embed_color,
        )

        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        elif "Radio" in str(track.requester_name or ""):
            # Feature 110: Aesthetic Waveform Visualizer Cards for Radio Mode
            embed.set_thumbnail(url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOHF4ejVpOXp5amZvZXV6NGpsZnpxc2pqbDV0ZXh5ZGtsMWtvcTVrayZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/L2HWpS0y0Q3cI/giphy.gif")

        loop_badge = f"Loop: {session.loop_mode.value.title()}" if session.loop_mode != LoopMode.OFF else ""
        autoplay_badge = "Autoplay: ON" if session.autoplay else ""
        badges = [b for b in [loop_badge, autoplay_badge] if b]
        footer_text = f"Neko Songs • {(' | '.join(badges)) if badges else 'Cute & Futuristic Audio'}"
        embed.set_footer(text=footer_text)
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
                    dj_settings = await bot.db.get_dj_settings(session.guild_id) if bot and bot.db else None
                    if (dj_settings and dj_settings.enabled) or getattr(session, "dj_enabled", False) or session.autoplay:
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
        if not bot and hasattr(session.voice_client, "client"):
            bot = session.voice_client.client  # type: ignore
        if bot:
            success, _, _ = await cls.skip(bot, session)
            return success
        if session.voice_client.is_playing() or session.voice_client.is_paused():
            session.voice_client.stop()
            return True
        return False

    @classmethod
    async def send_now_playing_panel(cls, session: GuildMusicSession) -> None:
        """Send or update the single persistent interactive control panel in the text channel."""
        if not session.text_channel:
            return

        embed = cls.build_now_playing_embed(session)
        view = NowPlayingControlView(session)

        try:
            # 1. Update existing message if valid (avoids spamming new messages)
            if session.now_playing_message:
                try:
                    await session.now_playing_message.edit(embed=embed, view=view)
                    if session.is_playing:
                        if not session.progress_updater_task or session.progress_updater_task.done():
                            session.progress_updater_task = asyncio.create_task(cls._progress_updater_loop(session))
                    return
                except discord.NotFound:
                    session.now_playing_message = None
                except Exception:
                    pass

            # 2. Otherwise post new message and register as persistent panel
            msg = await session.text_channel.send(embed=embed, view=view)
            session.now_playing_message = msg
            if session.is_playing:
                if not session.progress_updater_task or session.progress_updater_task.done():
                    session.progress_updater_task = asyncio.create_task(cls._progress_updater_loop(session))
        except Exception as e:
            logger.warning(f"Could not deploy Now Playing panel in channel {session.text_channel.id}: {e}")


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


class NowPlayingControlView(discord.ui.View):

    def __init__(self, session: Optional[GuildMusicSession] = None):
        super().__init__(timeout=None)
        self.session = session
        if self.session:
            self._update_button_states()

    def _get_session(self, interaction: discord.Interaction) -> Optional[GuildMusicSession]:
        if self.session is not None and interaction.guild and self.session.guild_id == interaction.guild.id:
            return self.session
        if interaction.guild:
            from music_bot.services.session_service import SessionManager
            return SessionManager.get_instance().get_session_sync(interaction.guild.id)
        return self.session

    def _update_button_states(self, session: Optional[GuildMusicSession] = None):
        target = session or self.session
        if not target:
            return
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "music_btn_play_pause":
                    child.label = "Resume" if target.is_paused else "Pause"
                    child.emoji = "▶" if target.is_paused else "⏸"
                    child.style = discord.ButtonStyle.success if target.is_paused else discord.ButtonStyle.secondary

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

    # --- ROW 0: [⏮ Previous] [⏪ -10s] [⏸ Pause / Resume] [⏩ +10s] [⏭ Skip] ---
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

        prev_track = session.history.pop()
        if session.current_track:
            session.queue.appendleft(session.current_track)

        bot: RaiMusicBot = interaction.client  # type: ignore
        await MusicPlayerService.start_playback(bot, session, prev_track)
        try:
            await interaction.followup.send(f"⏮ Returned to **{prev_track.title}**.", ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(emoji="⏪", label="-10s", style=discord.ButtonStyle.secondary, custom_id="music_btn_rewind_10", row=0)
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

        if not session or not session.current_track or not (session.is_playing or session.is_paused or session.has_active_track):
            try:
                await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            except Exception:
                pass
            return

        bot: RaiMusicBot = interaction.client  # type: ignore
        cur_pos = session.progress_seconds
        target_pos = max(0, cur_pos - 10)
        await MusicPlayerService.seek(bot, session, target_pos)
        try:
            await interaction.followup.send(f"⏪ Rewound 10s (now at `{format_duration(target_pos, is_position=True)}`).", ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(emoji="⏸", label="Pause", style=discord.ButtonStyle.secondary, custom_id="music_btn_play_pause", row=0)
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

        if session.voice_client.is_playing():
            session.voice_client.pause()
            session.pause_time = time.time()
            session.state = PlaybackState.PAUSED
            action_text = "⏸ Playback paused."
        elif session.voice_client.is_paused():
            session.voice_client.resume()
            if session.pause_time > 0:
                session.paused_duration += time.time() - session.pause_time
                session.pause_time = 0.0
            session.state = PlaybackState.PLAYING
            action_text = "▶ Playback resumed."
            if not session.progress_updater_task or session.progress_updater_task.done():
                session.progress_updater_task = asyncio.create_task(MusicPlayerService._progress_updater_loop(session))
        elif session.state == PlaybackState.PAUSED and session.current_track:
            bot: RaiMusicBot = interaction.client  # type: ignore
            cur_pos = session.progress_seconds
            await MusicPlayerService.resume_track_stream(bot, session, session.current_track, cur_pos)
            action_text = "▶ Playback resumed."
        else:
            action_text = "⏹ No track active."

        self._update_button_states(session)
        if session.now_playing_message:
            try:
                await session.now_playing_message.edit(embed=MusicPlayerService.build_now_playing_embed(session), view=self)
            except Exception:
                pass
        try:
            await interaction.followup.send(action_text, ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(emoji="⏩", label="+10s", style=discord.ButtonStyle.secondary, custom_id="music_btn_forward_10", row=0)
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

        if not session or not session.current_track or not (session.is_playing or session.is_paused or session.has_active_track):
            try:
                await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            except Exception:
                pass
            return

        bot: RaiMusicBot = interaction.client  # type: ignore
        cur_pos = session.progress_seconds
        dur = session.current_track.duration or 0
        target_pos = min(dur - 1, cur_pos + 10) if dur > 0 else cur_pos + 10
        await MusicPlayerService.seek(bot, session, target_pos)
        try:
            await interaction.followup.send(f"⏩ Fast-forwarded 10s (now at `{format_duration(target_pos, is_position=True)}`).", ephemeral=True)
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

    # --- ROW 1: [📜 Queue] [🔀 Shuffle] [🔁 Loop] ---
    @discord.ui.button(emoji="📜", label="Queue", style=discord.ButtonStyle.secondary, custom_id="music_btn_queue", row=1)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        session = self._get_session(interaction)
        if not session:
            try:
                await interaction.followup.send("🐾 No active music session.", ephemeral=True)
            except Exception:
                pass
            return

        tracks = list(session.queue)
        if not tracks and not session.current_track:
            try:
                await interaction.followup.send("🐾 The music queue is currently empty.", ephemeral=True)
            except Exception:
                pass
            return

        embed = discord.Embed(
            title=f"📜 NEKO SONGS QUEUE ({len(tracks)} tracks)",
            color=0x00B0FF,
        )
        if session.current_track:
            embed.description = f"**Now Playing:** [{session.current_track.title}]({session.current_track.url})\n\n"
        else:
            embed.description = ""

        queue_preview = []
        for i, t in enumerate(tracks[:10], start=1):
            queue_preview.append(f"`{i}.` [{t.title}]({t.url}) (`{format_duration(t.duration)}`) • <@{t.requester_id}>")

        if queue_preview:
            embed.description += "\n".join(queue_preview)
            if len(tracks) > 10:
                embed.description += f"\n\n*... and {len(tracks) - 10} more tracks.*"
        else:
            embed.description += "*No upcoming tracks in queue.*"

        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
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
        if not session or len(session.queue) < 2:
            try:
                await interaction.followup.send("❌ Need at least 2 tracks in queue to shuffle.", ephemeral=True)
            except Exception:
                pass
            return

        tracks = list(session.queue)
        random.shuffle(tracks)
        from collections import deque
        session.queue = deque(tracks)
        try:
            await interaction.followup.send(f"🔀 Shuffled `{len(tracks)}` tracks in queue.", ephemeral=True)
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
        if not session:
            return

        if session.loop_mode == LoopMode.OFF:
            session.loop_mode = LoopMode.TRACK
            msg = "🔂 Track loop **ENABLED**."
        elif session.loop_mode == LoopMode.TRACK:
            session.loop_mode = LoopMode.QUEUE
            msg = "🔁 Queue loop **ENABLED**."
        else:
            session.loop_mode = LoopMode.OFF
            msg = "➡️ Loop **DISABLED**."

        await MusicPlayerService.send_now_playing_panel(session)
        try:
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

    # --- ROW 1 (Continued): [🔊 Volume] [❤️ Favorite] ---
    @discord.ui.button(emoji="🔊", label="Volume", style=discord.ButtonStyle.secondary, custom_id="music_btn_vol", row=1)
    async def volume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self._get_session(interaction)
        if not session:
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)
                await interaction.followup.send("❌ No active music session.", ephemeral=True)
            except Exception:
                pass
            return

        try:
            view = VolumeAdjustView(session)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"🔊 **Volume Adjustment** (Current: `{session.volume}%`):", view=view, ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"🔊 **Volume Adjustment** (Current: `{session.volume}%`):", view=view, ephemeral=True
                )
        except Exception:
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer(ephemeral=True)
                except Exception:
                    pass

    # --- ROW 2: [❤️ Favorite] [🎛️ Filter] [💬 Lyrics] ---
    @discord.ui.button(emoji="❤️", label="Favorite", style=discord.ButtonStyle.secondary, custom_id="music_btn_fav", row=2)
    async def favorite_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        session = self._get_session(interaction)
        if not session or not session.current_track:
            try:
                await interaction.followup.send("❌ No track currently playing to add to favorites.", ephemeral=True)
            except Exception:
                pass
            return

        bot: RaiMusicBot = interaction.client  # type: ignore
        success = await bot.db.add_favorite(interaction.user.id, session.current_track)
        try:
            if success:
                await interaction.followup.send(
                    f"❤️ Saved **{session.current_track.title}** to your favorites! View with `/music favorites`.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"❤️ **{session.current_track.title}** is already in your favorites!",
                    ephemeral=True,
                )
        except Exception:
            pass

    @discord.ui.button(emoji="🎛️", label="Filter", style=discord.ButtonStyle.secondary, custom_id="music_btn_filter", row=2)
    async def filter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self._get_session(interaction)
        if not session:
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)
                await interaction.followup.send("❌ No active music session.", ephemeral=True)
            except Exception:
                pass
            return

        try:
            view = AudioEqualizerView(session, bot=interaction.client)
            if not interaction.response.is_done():
                await interaction.response.send_message("🎛️ **Audio Equalizer Presets:**", view=view, ephemeral=True)
            else:
                await interaction.followup.send("🎛️ **Audio Equalizer Presets:**", view=view, ephemeral=True)
        except Exception:
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer(ephemeral=True)
                except Exception:
                    pass

    @discord.ui.button(emoji="💬", label="Lyrics", style=discord.ButtonStyle.secondary, custom_id="music_btn_lyrics", row=2)
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

        from music_bot.services.lyrics_service import LyricsService
        try:
            lyrics = await asyncio.wait_for(
                LyricsService.fetch_lyrics(session.current_track.title, session.current_track.artist),
                timeout=3.0,
            )
        except Exception:
            lyrics = None

        embed = discord.Embed(
            title=f"📜 Lyrics: {session.current_track.title}",
            description=lyrics[:4000] if lyrics else "😿 No lyrics found for this song.",
            color=0x00B0FF,
        )
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(emoji="⏹", label="Stop", style=discord.ButtonStyle.danger, custom_id="music_btn_stop", row=1)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. IMMEDIATELY defer interaction FIRST so Discord never times out!
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        session = self._get_session(interaction)
        if not session:
            try:
                await interaction.followup.send("⏹ No active playback session to stop.", ephemeral=True)
            except Exception:
                pass
            return

        can_interact, reason = self._check_user_voice(interaction, session)
        if not can_interact:
            try:
                await interaction.followup.send(reason, ephemeral=True)
            except Exception:
                pass
            return

        # 2. State cleanup & stop voice atomically
        session.is_intentional_stop = True
        session.state = PlaybackState.STOPPED
        session.queue.clear()
        if session.voice_client:
            session.voice_client.stop()
            try:
                await session.voice_client.disconnect()
            except Exception:
                pass

        if session.voice_client and session.voice_client.channel:
            vc_ch = session.voice_client.channel
            if hasattr(vc_ch, "set_status"):
                try:
                    await vc_ch.set_status(None, reason="Neko Songs Stopped")
                except Exception:
                    pass
            session.voice_client = None

        if session.now_playing_message:
            try:
                await session.now_playing_message.delete()
            except Exception:
                pass
            session.now_playing_message = None

        session.reset()

        bot_client = getattr(interaction, "client", None)
        if bot_client and getattr(bot_client, "db", None) and hasattr(bot_client.db, "delete_session"):
            coro = bot_client.db.delete_session(session.guild_id)
            if asyncio.iscoroutine(coro):
                asyncio.create_task(coro)

        try:
            await interaction.followup.send("⏹ Stopped music playback and disconnected. 🐾", ephemeral=True)
        except Exception:
            pass


# Module-level convenience function
build_now_playing_embed = MusicPlayerService.build_now_playing_embed


