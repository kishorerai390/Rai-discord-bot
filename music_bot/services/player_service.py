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
            return False

        try:
            # Stop existing playback if any
            if session.voice_client.is_playing() or session.voice_client.is_paused():
                session.voice_client.stop()

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

            session.current_track = track
            session.track_start_time = time.time()
            session.pause_time = 0.0
            session.paused_duration = 0.0
            session._dj_prequeued = False
            session.state = PlaybackState.PLAYING

            loop = bot.loop

            def after_playback(error: Optional[Exception]):
                if getattr(session, "_is_seeking", False):
                    return
                if error:
                    logger.error(f"Playback error in guild {session.guild_id}: {error}")

                # Mid-song stream auto-recovery for premature stream failures
                elapsed = session.progress_seconds
                duration = track.duration if track else 0
                retries = getattr(track, "_retry_count", 0)
                if error and duration > 30 and elapsed < duration - 15 and retries < 2:
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

            session.voice_client.play(volume_transformer, after=after_playback)

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

            try:
                audio_source = discord.FFmpegPCMAudio(track.stream_url, **ffmpeg_opts)
            except Exception:
                fresh_track = await AudioResolver.resolve_track(track.url, track.requester_id, track.requester_name)
                if fresh_track and fresh_track.stream_url:
                    track.stream_url = fresh_track.stream_url
                audio_source = discord.FFmpegPCMAudio(track.stream_url, **ffmpeg_opts)
            volume_transformer = discord.PCMVolumeTransformer(audio_source, volume=session.volume / 100.0)

            session.current_track = track
            session.track_start_time = time.time() - start_seconds
            session.paused_duration = 0.0
            session.state = PlaybackState.PLAYING

            loop = bot.loop

            def after_resumed(error: Optional[Exception]):
                if getattr(session, "_is_seeking", False):
                    return
                if error:
                    logger.error(f"Post-recovery playback error in guild {session.guild_id}: {error}")
                asyncio.run_coroutine_threadsafe(cls.handle_track_finished(bot, session), loop)

            session.voice_client.play(volume_transformer, after=after_resumed)

            # Ensure real-time progress updater is running
            if session.progress_updater_task and not session.progress_updater_task.done():
                session.progress_updater_task.cancel()
            session.progress_updater_task = asyncio.create_task(cls._progress_updater_loop(session))

            logger.info(f"Zero-interrupt stream recovery successful for '{track.title}' at {start_seconds}s!")
            return True
        except Exception as e:
            logger.error(f"Failed to auto-recover stream: {e}")
            await cls.handle_track_finished(bot, session)
            return False

    @classmethod
    async def handle_track_finished(cls, bot: RaiMusicBot, session: GuildMusicSession) -> None:
        """Called automatically when track ends to play next track or handle loops/autoplay."""
        if session.progress_updater_task and not session.progress_updater_task.done():
            session.progress_updater_task.cancel()
            session.progress_updater_task = None

        async with session.lock:
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

            # Queue empty and no autoplay -> transition to IDLE
            session.reset()
            if session.text_channel:
                embed = discord.Embed(
                    title="🐾 QUEUE FINISHED",
                    description="The queue is empty. Give Neko another song? 🐱\nUse `/music play` or `/play` to continue.",
                    color=0x00B0FF,
                )
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
        is_active_play = session.state == PlaybackState.PLAYING or session.is_playing
        if total > 0:
            remaining = max(0, total - elapsed)
            end_ts = int(time.time() + remaining)
            time_suffix = f" • Ends <t:{end_ts}:R>" if is_active_play else ""
            progress_str = f"{format_duration(elapsed, is_position=True)} / {format_duration(total)}{time_suffix}"
            progress_bar = create_progress_bar(elapsed, total)
        else:
            progress_str = f"{format_duration(elapsed, is_position=True)} / 🔴 LIVE"
            progress_bar = "🔘──────────────"

        status_text = "🟢 Playing" if is_active_play else ("⏸️ Paused" if session.is_paused else "⏹️ Idle")
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

        embed = discord.Embed(
            title="🎶 NOW PLAYING",
            description=(
                f"*{time_badge}*\n\n"
                f"### [{track.title}]({track.url})\n"
                f"👤 **Artist:** `{track.artist}`\n\n"
                f"**Progress:**\n`{progress_bar}` `{progress_str}`\n\n"
                f"• **Requested by:** {requester_str}\n"
                f"• **Volume:** `{session.volume}%` • **Status:** {status_text}\n"
                f"• **Queue:** `{len(session.queue)} tracks` • **EQ:** `{preset_name}` • **24/7:** `{is_247_str}`"
            ),
            color=0x00E5FF if session.is_playing else 0x9B59B6,
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
            await asyncio.sleep(10)
            if not session.is_playing or not session.now_playing_message:
                continue
            update_cycle += 1
            try:
                embed = cls.build_now_playing_embed(session)

                # Sticky HUD anchor: check every 3 cycles (30s) if new messages pushed player off screen
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
                    await asyncio.sleep(10)
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

    @classmethod
    async def send_now_playing_panel(cls, session: GuildMusicSession) -> None:
        """Send or update the interactive control panel in the text channel."""
        if not session.text_channel:
            return

        embed = cls.build_now_playing_embed(session)
        view = NowPlayingControlView(session)

        try:
            # Always post as a fresh new message in the text channel (never edit previous message)
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

        filter_chains = {
            "bassboost": "-af equalizer=f=60:width_type=h:width=50:g=10",
            "nightcore": "-af atempo=1.25,asetrate=48000*1.25",
            "8d": "-af apulsator=hz=0.125",
            "vaporwave": "-af atempo=0.85,asetrate=48000*0.85",
            "vocal": "-af equalizer=f=1000:width_type=h:width=200:g=6",
            "reset": "",
        }

        self.session.eq_preset = display_name
        self.session.audio_filter = filter_chains.get(preset_key, "")

        # 2. If music is playing, seamlessly re-encode and seek to current position so it applies live!
        bot_instance = self.bot or getattr(interaction.client, "bot", interaction.client)
        if self.session.current_track and self.session.is_playing and bot_instance:
            import time
            current_pos = self.session.elapsed_seconds
            await MusicPlayerService.start_playback(bot_instance, self.session, self.session.current_track)
            self.session.paused_duration = 0.0
            self.session.track_start_time = time.time() - current_pos

        try:
            await interaction.followup.send(
                f"🎛️ Applied Equalizer Preset: **{display_name}** 🐾\n"
                f"*(Audio stream instantly refreshed with real-time DSP filter)*",
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
        if not session or not session.current_track or not session.is_playing:
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
        if not session or not session.current_track or not session.is_playing:
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
        if not session or not session.voice_client or not session.voice_client.is_playing():
            try:
                await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            except Exception:
                pass
            return

        track_title = session.current_track.title if session.current_track else "Track"
        session.voice_client.stop()  # Triggers after_playback -> handle_track_finished
        try:
            await interaction.followup.send(f"⏭ Skipped **{track_title}**.", ephemeral=True)
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

        # 2. State cleanup & stop voice
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
        if bot_client and getattr(bot_client, "db", None):
            asyncio.create_task(bot_client.db.delete_session(session.guild_id))

        try:
            await interaction.followup.send("⏹ Stopped music playback and disconnected. 🐾", ephemeral=True)
        except Exception:
            pass


# Module-level convenience function
build_now_playing_embed = MusicPlayerService.build_now_playing_embed


