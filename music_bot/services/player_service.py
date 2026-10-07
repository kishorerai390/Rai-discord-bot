"""
Audio Player Service & Interactive Now Playing Controls for Rai Music Bot.
Manages playback transitions, Discord FFmpeg streams, and rich interactive button panels.
"""

from __future__ import annotations

import asyncio
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


def format_duration(seconds: int) -> str:
    """Format duration in seconds into MM:SS or HH:MM:SS."""
    if seconds <= 0:
        return "LIVE / Unknown"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def create_progress_bar(elapsed: int, total: int, length: int = 15) -> str:
    """Generate visual progress bar (e.g. ████████░░ 03:12 / 04:01)."""
    if total <= 0:
        return "🔘 LIVE STREAM"
    ratio = min(1.0, max(0.0, elapsed / total))
    filled = int(round(ratio * length))
    bar = "█" * filled + "░" * (length - filled)
    return f"{bar} {format_duration(elapsed)} / {format_duration(total)}"


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

            # Create FFmpeg audio source
            audio_source = discord.FFmpegPCMAudio(track.stream_url, **FFMPEG_OPTIONS)
            volume_transformer = discord.PCMVolumeTransformer(
                audio_source, volume=session.volume / 100.0
            )

            session.current_track = track
            session.track_start_time = time.time()
            session.pause_time = 0.0
            session.paused_duration = 0.0
            session.state = PlaybackState.PLAYING

            loop = bot.loop

            def after_playback(error: Optional[Exception]):
                if error:
                    logger.error(f"Playback error in guild {session.guild_id}: {error}")
                # Schedule track transition on the bot event loop
                asyncio.run_coroutine_threadsafe(cls.handle_track_finished(bot, session), loop)

            session.voice_client.play(volume_transformer, after=after_playback)

            # Record playback to database history
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

            # Deploy or update Now Playing embed panel in the designated text channel
            if session.text_channel:
                asyncio.create_task(cls.send_now_playing_panel(session))

            return True

        except Exception as e:
            logger.error(f"Failed to play track in guild {session.guild_id}: {e}", exc_info=True)
            session.state = PlaybackState.ERROR
            return False

    @classmethod
    async def handle_track_finished(cls, bot: RaiMusicBot, session: GuildMusicSession) -> None:
        """Called automatically when track ends to play next track or handle loops/autoplay."""
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
                await cls.start_playback(bot, session, next_track)
                return

            # Check Neko DJ & Autoplay if enabled
            if session.history:
                try:
                    dj_settings = await bot.db.get_dj_settings(session.guild_id)
                    if dj_settings.enabled:
                        from music_bot.services.dj_service import NekoDJService
                        rec = await NekoDJService.get_recommendation(bot, session)
                        if rec:
                            track, rationale = rec
                            if dj_settings.auto_queue:
                                logger.info(f"Neko DJ auto-queueing recommended track: '{track.title}'")
                                await cls.start_playback(bot, session, track)
                                return
                            else:
                                await NekoDJService.post_recommendation_card(bot, session)
                except Exception as e:
                    logger.warning(f"Neko DJ hook error: {e}")

            # Fallback to standard autoplay
            if session.autoplay and session.history:
                last_played = session.history[-1]
                logger.info(f"Queue exhausted. Autoplaying related track for '{last_played.title}'...")
                session.state = PlaybackState.SEARCHING
                try:
                    candidates = await AudioResolver.search(f"{last_played.artist} songs", limit=5)
                    for c in candidates:
                        if c["title"] != last_played.title and not any(h.title == c["title"] for h in session.history[-5:]):
                            resolved = await AudioResolver.resolve_track(
                                c["url"], 0, "Neko Autoplay"
                            )
                            if resolved:
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
                title="╭────────────────────────────╮\n       🎵 NEKO SONGS\n╰────────────────────────────╯",
                description="🐱 **NOW PLAYING**\n\n*No music is currently playing in this server.*",
                color=0x0B0E14,
            )

        elapsed = session.elapsed_seconds
        progress_str = f"{format_duration(elapsed)} / {format_duration(track.duration)}"
        progress_bar = create_progress_bar(elapsed, track.duration)

        status_text = "🟢 Playing" if session.is_playing else ("⏸️ Paused" if session.is_paused else "⏹️ Idle")
        requester_str = f"<@{track.requester_id}>" if track.requester_id else track.requester_name

        embed = discord.Embed(
            title="╭────────────────────────────╮\n       🎵 NEKO SONGS\n╰────────────────────────────╯",
            description=(
                f"🐱 **NOW PLAYING**\n\n"
                f"**{track.artist}** — **[{track.title}]({track.url})**\n\n"
                f"**Requested by:** {requester_str}\n\n"
                f"**Progress:**\n`{progress_bar}`\n`{progress_str}`\n\n"
                f"**Queue:**\n`{len(session.queue)} tracks`\n\n"
                f"**Volume:**\n`{session.volume}%`\n\n"
                f"**Playback:**\n{status_text}"
            ),
            color=0x00B0FF if session.is_playing else 0x9B59B6,
        )

        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)

        loop_badge = f"Loop: {session.loop_mode.value.title()}" if session.loop_mode != LoopMode.OFF else ""
        autoplay_badge = "Autoplay: ON" if session.autoplay else ""
        badges = [b for b in [loop_badge, autoplay_badge] if b]
        footer_text = f"Neko Songs • {(' | '.join(badges)) if badges else 'Cute & Futuristic Audio'}"
        embed.set_footer(text=footer_text)
        return embed

    @classmethod
    async def send_now_playing_panel(cls, session: GuildMusicSession) -> None:
        """Send or update the interactive control panel in the text channel."""
        if not session.text_channel:
            return

        embed = cls.build_now_playing_embed(session)
        view = NowPlayingControlView(session)

        try:
            if session.now_playing_message:
                try:
                    await session.now_playing_message.edit(embed=embed, view=view)
                    return
                except Exception:
                    session.now_playing_message = None

            msg = await session.text_channel.send(embed=embed, view=view)
            session.now_playing_message = msg
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


class NowPlayingControlView(discord.ui.View):
    """Interactive Discord UI buttons for Neko Songs Now Playing panel."""

    def __init__(self, session: GuildMusicSession):
        super().__init__(timeout=None)
        self.session = session
        self._update_button_states()

    def _update_button_states(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "music_btn_play_pause":
                    child.label = "Resume" if self.session.is_paused else "Pause"
                    child.emoji = "▶" if self.session.is_paused else "⏸"
                    child.style = discord.ButtonStyle.success if self.session.is_paused else discord.ButtonStyle.secondary

    # --- ROW 0: [⏮ Previous] [⏸ Pause / Resume] [⏭ Skip] ---
    @discord.ui.button(emoji="⏮", label="Previous", style=discord.ButtonStyle.secondary, custom_id="music_btn_prev", row=0)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not self.session.history:
            await interaction.followup.send("❌ No previous tracks in history.", ephemeral=True)
            return

        prev_track = self.session.history.pop()
        if self.session.current_track:
            self.session.queue.appendleft(self.session.current_track)

        bot: RaiMusicBot = interaction.client  # type: ignore
        await MusicPlayerService.start_playback(bot, self.session, prev_track)
        await interaction.followup.send(f"⏮ Returned to **{prev_track.title}**.", ephemeral=True)

    @discord.ui.button(emoji="⏸", label="Pause", style=discord.ButtonStyle.secondary, custom_id="music_btn_play_pause", row=0)
    async def play_pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not self.session.voice_client:
            await interaction.followup.send("❌ Music bot is not connected to voice.", ephemeral=True)
            return

        if self.session.voice_client.is_playing():
            self.session.voice_client.pause()
            self.session.pause_time = time.time()
            self.session.state = PlaybackState.PAUSED
            action_text = "⏸ Playback paused."
        elif self.session.voice_client.is_paused():
            self.session.voice_client.resume()
            if self.session.pause_time > 0:
                self.session.paused_duration += time.time() - self.session.pause_time
                self.session.pause_time = 0.0
            self.session.state = PlaybackState.PLAYING
            action_text = "▶ Playback resumed."
        else:
            action_text = "⏹ No track active."

        self._update_button_states()
        await MusicPlayerService.send_now_playing_panel(self.session)
        await interaction.followup.send(action_text, ephemeral=True)

    @discord.ui.button(emoji="⏭", label="Skip", style=discord.ButtonStyle.secondary, custom_id="music_btn_skip", row=0)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not self.session.voice_client or not self.session.voice_client.is_playing():
            await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            return

        track_title = self.session.current_track.title if self.session.current_track else "Track"
        self.session.voice_client.stop()  # Triggers after_playback -> handle_track_finished
        await interaction.followup.send(f"⏭ Skipped **{track_title}**.", ephemeral=True)

    # --- ROW 1: [📜 Queue] [🔀 Shuffle] [🔁 Loop] ---
    @discord.ui.button(emoji="📜", label="Queue", style=discord.ButtonStyle.secondary, custom_id="music_btn_queue", row=1)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        tracks = list(self.session.queue)
        if not tracks and not self.session.current_track:
            await interaction.followup.send("🐾 The music queue is currently empty.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📜 NEKO SONGS QUEUE ({len(tracks)} tracks)",
            color=0x00B0FF,
        )
        if self.session.current_track:
            embed.description = f"**Now Playing:** [{self.session.current_track.title}]({self.session.current_track.url})\n\n"
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

        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(emoji="🔀", label="Shuffle", style=discord.ButtonStyle.secondary, custom_id="music_btn_shuffle", row=1)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if len(self.session.queue) < 2:
            await interaction.followup.send("❌ Need at least 2 tracks in queue to shuffle.", ephemeral=True)
            return

        tracks = list(self.session.queue)
        random.shuffle(tracks)
        self.session.queue = asyncio.queues.deque(tracks)  # type: ignore
        await interaction.followup.send(f"🔀 Shuffled `{len(tracks)}` tracks in queue.", ephemeral=True)

    @discord.ui.button(emoji="🔁", label="Loop", style=discord.ButtonStyle.secondary, custom_id="music_btn_loop", row=1)
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if self.session.loop_mode == LoopMode.OFF:
            self.session.loop_mode = LoopMode.TRACK
            msg = "🔂 Track loop **ENABLED**."
        elif self.session.loop_mode == LoopMode.TRACK:
            self.session.loop_mode = LoopMode.QUEUE
            msg = "🔁 Queue loop **ENABLED**."
        else:
            self.session.loop_mode = LoopMode.OFF
            msg = "➡️ Loop **DISABLED**."

        await MusicPlayerService.send_now_playing_panel(self.session)
        await interaction.followup.send(msg, ephemeral=True)

    # --- ROW 2: [🔊 Volume] [❤️ Favorite] [⏹ Stop] ---
    @discord.ui.button(emoji="🔊", label="Volume", style=discord.ButtonStyle.secondary, custom_id="music_btn_vol", row=2)
    async def volume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = VolumeAdjustView(self.session)
        await interaction.response.send_message(
            f"🔊 **Volume Adjustment** (Current: `{self.session.volume}%`):", view=view, ephemeral=True
        )

    @discord.ui.button(emoji="❤️", label="Favorite", style=discord.ButtonStyle.secondary, custom_id="music_btn_fav", row=2)
    async def favorite_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not self.session.current_track:
            await interaction.followup.send("❌ No track currently playing to add to favorites.", ephemeral=True)
            return

        bot: RaiMusicBot = interaction.client  # type: ignore
        success = await bot.db.add_favorite(interaction.user.id, self.session.current_track)
        if success:
            await interaction.followup.send(
                f"❤️ Saved **{self.session.current_track.title}** to your favorites! View with `/music favorites`.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"❤️ **{self.session.current_track.title}** is already in your favorites!",
                ephemeral=True,
            )

    @discord.ui.button(emoji="⏹", label="Stop", style=discord.ButtonStyle.danger, custom_id="music_btn_stop", row=2)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        self.session.queue.clear()
        if self.session.voice_client:
            self.session.voice_client.stop()
            await self.session.voice_client.disconnect()
            self.session.voice_client = None

        self.session.reset()
        await interaction.followup.send("⏹ Stopped music playback and disconnected. 🐾", ephemeral=True)


# Module-level convenience function
build_now_playing_embed = MusicPlayerService.build_now_playing_embed


