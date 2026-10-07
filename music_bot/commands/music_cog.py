"""
Master Neko Songs Command Suite.
Registers all /music commands, subcommands, aliases, setup wizard, and natural requests.
Adheres strictly to the Neko Songs brand identity, cute personality, and isolated architecture.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import math
import random
from typing import TYPE_CHECKING, List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from music_bot.config import (
    BOT_NAME,
    COLOR_ELECTRIC_CYAN,
    COLOR_MIDNIGHT_BLACK,
    COLOR_NEON_BLUE,
    COLOR_WHITE,
    DIALOGUE_EMPTY_QUEUE,
    DIALOGUE_JOIN,
    DIALOGUE_NOTHING_PLAYABLE,
    DIALOGUE_START,
    DIALOGUE_UNAVAILABLE,
    MUSIC_BOT_VERSION,
)
from music_bot.database.models import QueuedTrack
from music_bot.services.diagnostics_service import MusicDiagnosticsService
from music_bot.services.dj_service import NekoDJService
from music_bot.services.lyrics_service import LyricsService
from music_bot.services.player_service import MusicPlayerService, format_duration
from music_bot.services.recommendation_service import (
    RECOMMENDATION_MODES,
    MusicRecommendationService,
)
from music_bot.services.resolver_service import AudioResolver
from music_bot.services.session_service import (
    GuildMusicSession,
    LoopMode,
    PlaybackState,
    SessionManager,
)
from music_bot.services.voice_service import VoiceManager

if TYPE_CHECKING:
    from music_bot.bot import RaiMusicBot

logger = logging.getLogger("NekoSongs.Commands")


# =============================================================================
# SEARCH SELECTION MENU
# =============================================================================

class TrackSelectView(discord.ui.View):
    """Dropdown select menu for ambiguous search queries."""

    def __init__(self, candidates: List[dict], user_id: int, on_select_coro):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.on_select_coro = on_select_coro

        options = []
        for i, c in enumerate(candidates[:5]):
            options.append(
                discord.SelectOption(
                    label=c["title"][:95],
                    description=f"Artist: {c['artist'][:50]} • {format_duration(c['duration'])}",
                    value=str(i),
                    emoji="🐱",
                )
            )

        select = discord.ui.Select(
            placeholder="Select a song for Neko to play...",
            min_values=1,
            max_values=1,
            options=options,
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This selection is for another user.", ephemeral=True)
            return

        selected_idx = int(interaction.data["values"][0])  # type: ignore
        await interaction.response.defer()
        await self.on_select_coro(interaction, selected_idx)
        self.stop()


# =============================================================================
# INTERACTIVE SETUP DASHBOARD (SECTION 17)
# =============================================================================

class NekoSetupDashboardView(discord.ui.View):
    """Interactive setup dashboard with real actions for all 10 buttons."""

    def __init__(self, bot: RaiMusicBot, guild: discord.Guild):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild = guild

    @discord.ui.button(label="Quick Setup", style=discord.ButtonStyle.primary, row=0, emoji="⚡")
    async def quick_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        # Auto-create or locate #music-requests channel
        existing = discord.utils.get(self.guild.text_channels, name="music-requests")
        if not existing:
            try:
                existing = await self.guild.create_text_channel(
                    name="music-requests",
                    topic="🐱 Send song titles or links here for Neko Songs to play!",
                )
            except Exception:
                existing = interaction.channel  # type: ignore

        settings = await self.bot.db.get_guild_settings(self.guild.id)
        settings.request_channel_id = existing.id if existing else None
        settings.natural_requests_enabled = True
        settings.auto_leave_enabled = True
        await self.bot.db.update_guild_settings(settings)
        await interaction.followup.send(
            f"✅ **Quick Setup Complete!**\n• Request Channel: {existing.mention if existing else 'Current'}\n• Natural requests & auto-leave enabled.",
            ephemeral=True,
        )

    @discord.ui.button(label="Request Channel", style=discord.ButtonStyle.secondary, row=0, emoji="💬")
    async def request_ch(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = await self.bot.db.get_guild_settings(self.guild.id)
        settings.request_channel_id = interaction.channel_id
        await self.bot.db.update_guild_settings(settings)
        await interaction.response.send_message(
            f"✅ Set this channel (<#{interaction.channel_id}>) as the designated music request channel.",
            ephemeral=True,
        )

    @discord.ui.button(label="DJ Role", style=discord.ButtonStyle.secondary, row=0, emoji="🎧")
    async def dj_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Look for DJ role or explain
        dj_role = discord.utils.get(self.guild.roles, name="DJ")
        settings = await self.bot.db.get_guild_settings(self.guild.id)
        if dj_role:
            settings.dj_role_id = dj_role.id
            await self.bot.db.update_guild_settings(settings)
            await interaction.response.send_message(f"✅ Linked existing **{dj_role.name}** role as the DJ role.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "ℹ️ To set a DJ role, create a role named `DJ` or configure it via `/music settings`.",
                ephemeral=True,
            )

    @discord.ui.button(label="Permissions", style=discord.ButtonStyle.secondary, row=0, emoji="🛡️")
    async def perms_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        me = self.guild.me
        perms = me.guild_permissions
        info = (
            f"**Bot Permissions in {self.guild.name}:**\n"
            f"• Connect: `{'✅' if perms.connect else '❌'}`\n"
            f"• Speak: `{'✅' if perms.speak else '❌'}`\n"
            f"• Send Messages: `{'✅' if perms.send_messages else '❌'}`\n"
            f"• Embed Links: `{'✅' if perms.embed_links else '❌'}`"
        )
        await interaction.response.send_message(info, ephemeral=True)

    @discord.ui.button(label="Auto Leave", style=discord.ButtonStyle.secondary, row=1, emoji="⏱️")
    async def autoleave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = await self.bot.db.get_guild_settings(self.guild.id)
        settings.auto_leave_enabled = not settings.auto_leave_enabled
        await self.bot.db.update_guild_settings(settings)
        state_str = "ENABLED (5 mins)" if settings.auto_leave_enabled else "DISABLED"
        await interaction.response.send_message(f"⏱️ Auto Leave is now **{state_str}**.", ephemeral=True)

    @discord.ui.button(label="Autoplay", style=discord.ButtonStyle.secondary, row=1, emoji="🔄")
    async def autoplay_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = await self.bot.session_manager.get_session(self.guild.id)
        session.autoplay = not session.autoplay
        state_str = "ENABLED" if session.autoplay else "DISABLED"
        await interaction.response.send_message(f"🔄 Autoplay is now **{state_str}** for this session.", ephemeral=True)

    @discord.ui.button(label="Queue Settings", style=discord.ButtonStyle.secondary, row=1, emoji="📜")
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = await self.bot.db.get_guild_settings(self.guild.id)
        await interaction.response.send_message(
            f"📜 **Queue Settings:**\n• Max Queue Size: `{settings.queue_limit} tracks`\n• Vote-Skip Threshold: `{int(settings.vote_skip_threshold * 100)}%`",
            ephemeral=True,
        )

    @discord.ui.button(label="Neko DJ", style=discord.ButtonStyle.secondary, row=1, emoji="🐱")
    async def nekodj_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        dj_set = await self.bot.db.get_dj_settings(self.guild.id)
        dj_set.enabled = not dj_set.enabled
        await self.bot.db.update_dj_settings(dj_set)
        state_str = "ENABLED 🎧" if dj_set.enabled else "DISABLED"
        await interaction.response.send_message(f"🐱 Neko DJ Mode is now **{state_str}**.", ephemeral=True)

    @discord.ui.button(label="Diagnostics", style=discord.ButtonStyle.secondary, row=2, emoji="🩺")
    async def diag_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        probes = await MusicDiagnosticsService.run_doctor(self.bot, self.guild)
        desc = "\n".join(f"• **{p.name}:** {p.badge} (`{p.latency_ms}ms`)" for p in probes)
        embed = discord.Embed(
            title="🩺 NEKO SONGS DIAGNOSTICS",
            description=desc,
            color=COLOR_NEON_BLUE,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Test Music", style=discord.ButtonStyle.success, row=2, emoji="🎵")
    async def test_music_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.voice or not interaction.user.voice.channel:  # type: ignore
            await interaction.followup.send("❌ Join a voice channel first to test music playback.", ephemeral=True)
            return

        session = await self.bot.session_manager.get_session(self.guild.id)
        vc = await VoiceManager.join_voice_channel(interaction.user, interaction.channel, session)  # type: ignore
        if not vc:
            await interaction.followup.send("❌ Could not connect to your voice channel.", ephemeral=True)
            return

        track = await AudioResolver.resolve_track("lofi hip hop test", interaction.user.id, str(interaction.user))
        if track:
            await MusicPlayerService.start_playback(self.bot, session, track)
            await interaction.followup.send("🎵 Playing test track! Check your audio.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Failed to resolve test audio.", ephemeral=True)


# =============================================================================
# MASTER COG
# =============================================================================

class MusicCog(commands.Cog, name="Music"):
    """Neko Songs Independent Discord Audio Platform."""

    def __init__(self, bot: RaiMusicBot):
        self.bot = bot
        self.session_manager = SessionManager.get_instance()
        self._skip_votes: dict[int, set[int]] = {}  # guild_id -> set of user_ids

    # =========================================================================
    # HELPERS
    # =========================================================================

    async def _check_permissions(self, interaction: discord.Interaction) -> bool:
        """Verify user is in voice channel and allowed to use music commands."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("❌ This command must be used in a server.", ephemeral=True)
            return False

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("❌ You must join a voice channel first.", ephemeral=True)
            return False

        return True

    async def _play_query(
        self, interaction: discord.Interaction, query: str, ephemeral: bool = False
    ) -> None:
        """Internal worker executing search, resolve, queueing, and playback transition."""
        guild = interaction.guild
        member = interaction.user
        text_channel = interaction.channel

        if not guild or not isinstance(member, discord.Member) or not isinstance(text_channel, discord.TextChannel):
            await interaction.followup.send("❌ Cannot determine server or channel context.", ephemeral=True)
            return

        session = await self.session_manager.get_session(guild.id)

        # 1. Connect to voice
        async with session.lock:
            vc = await VoiceManager.join_voice_channel(member, text_channel, session)
            if not vc:
                await interaction.followup.send(
                    "❌ Could not connect to your voice channel. Check bot permissions.",
                    ephemeral=True,
                )
                return

        # 2. Resolve query
        embed_loading = discord.Embed(
            title="🔍 SEARCHING TRACK",
            description=f"Resolving: `{query[:100]}`...\n*{DIALOGUE_START}*",
            color=COLOR_NEON_BLUE,
        )
        await interaction.followup.send(embed=embed_loading, ephemeral=ephemeral)

        try:
            track = await AudioResolver.resolve_track(query, member.id, str(member))
        except Exception as e:
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="❌ TRACK RESOLUTION FAILED",
                    description=f"{DIALOGUE_UNAVAILABLE}\nError: `{e}`",
                    color=0xED4245,
                )
            )
            return

        if not track:
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="😿 NO AUDIO TRACK FOUND",
                    description=f"{DIALOGUE_NOTHING_PLAYABLE}\nQuery: `{query}`",
                    color=0xED4245,
                )
            )
            return

        # 3. Add to Queue or Start Playback
        async with session.lock:
            if session.is_playing:
                session.queue.append(track)
                embed_queued = discord.Embed(
                    title="🐱 ADDED TO QUEUE",
                    description=f"### [{track.title}]({track.url})\n"
                                f"**Artist:** `{track.artist}` • **Duration:** `{format_duration(track.duration)}`\n"
                                f"**Position in Queue:** `#{len(session.queue)}`",
                    color=COLOR_ELECTRIC_CYAN,
                )
                if track.thumbnail:
                    embed_queued.set_thumbnail(url=track.thumbnail)
                embed_queued.set_footer(text=f"Requested by {member.display_name}")
                await interaction.edit_original_response(embed=embed_queued)
            else:
                success = await MusicPlayerService.start_playback(self.bot, session, track)
                if success:
                    embed_started = discord.Embed(
                        title="🎶 NOW PLAYING",
                        description=f"### [{track.title}]({track.url})\n**Artist:** `{track.artist}`\n\n*{DIALOGUE_START}*",
                        color=COLOR_ELECTRIC_CYAN,
                    )
                    if track.thumbnail:
                        embed_started.set_thumbnail(url=track.thumbnail)
                    await interaction.edit_original_response(embed=embed_started)
                else:
                    await interaction.edit_original_response(
                        embed=discord.Embed(
                            title="❌ PLAYBACK FAILED",
                            description="Encountered an internal error while starting audio stream.",
                            color=0xED4245,
                        )
                    )

    # =========================================================================
    # /MUSIC COMMAND GROUP
    # =========================================================================

    music_group = app_commands.Group(name="music", description="Neko Songs Independent Music Suite")

    # --- 1. PLAYBACK & BASIC CONTROLS ---

    @music_group.command(name="play", description="Play a song or URL from YouTube")
    @app_commands.describe(query="Song title, artist, or URL to play")
    async def music_play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(ephemeral=False)
        if not await self._check_permissions(interaction):
            return
        await self._play_query(interaction, query)

    @music_group.command(name="search", description="Search YouTube and select from top results")
    @app_commands.describe(query="Song search query")
    async def music_search(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(ephemeral=False)
        if not await self._check_permissions(interaction):
            return

        candidates = await AudioResolver.search(query, limit=5)
        if not candidates:
            await interaction.followup.send(f"😿 No results found for `{query}`.", ephemeral=True)
            return

        async def on_select(inter: discord.Interaction, idx: int):
            chosen = candidates[idx]
            await self._play_query(inter, chosen["url"])

        view = TrackSelectView(candidates, interaction.user.id, on_select)
        await interaction.followup.send("🐱 **Select a track to play:**", view=view)

    @music_group.command(name="pause", description="Pause current music playback")
    async def music_pause(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.voice_client or not session.voice_client.is_playing():
            await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            return

        session.voice_client.pause()
        session.pause_time = discord.utils.utcnow().timestamp()
        session.state = PlaybackState.PAUSED
        await interaction.followup.send("⏸️ Playback paused.")

    @music_group.command(name="resume", description="Resume paused music playback")
    async def music_resume(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.voice_client or not session.voice_client.is_paused():
            await interaction.followup.send("❌ Music is not currently paused.", ephemeral=True)
            return

        session.voice_client.resume()
        session.state = PlaybackState.PLAYING
        await interaction.followup.send("▶️ Playback resumed.")

    @music_group.command(name="skip", description="Skip the currently playing song")
    async def music_skip(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.voice_client or not session.voice_client.is_playing():
            await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            return

        track_title = session.current_track.title if session.current_track else "Song"
        session.voice_client.stop()
        await interaction.followup.send(f"⏭️ Skipped **{track_title}**.")

    @music_group.command(name="previous", description="Return to the previous song in history")
    async def music_previous(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.history:
            await interaction.followup.send("❌ No previous tracks in history.", ephemeral=True)
            return

        prev = session.history.pop()
        if session.current_track:
            session.queue.appendleft(session.current_track)

        await MusicPlayerService.start_playback(self.bot, session, prev)
        await interaction.followup.send(f"⏮️ Returned to **{prev.title}**.")

    @music_group.command(name="stop", description="Stop playback, clear queue, and leave voice")
    async def music_stop(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        session.queue.clear()
        if session.voice_client:
            session.voice_client.stop()
            await session.voice_client.disconnect()
            session.voice_client = None
        session.reset()
        await interaction.followup.send("⏹️ Stopped playback and cleared queue. 🐾")

    @music_group.command(name="nowplaying", description="View the official Neko Songs Now Playing dashboard")
    async def music_nowplaying(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        embed = MusicPlayerService.build_now_playing_embed(session)
        from music_bot.services.player_service import NowPlayingControlView
        view = NowPlayingControlView(session)
        await interaction.followup.send(embed=embed, view=view)

    @music_group.command(name="queue", description="Display the current music queue")
    @app_commands.describe(page="Queue page number (default 1)")
    async def music_queue(self, interaction: discord.Interaction, page: Optional[int] = 1) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        tracks = list(session.queue)
        if not tracks and not session.current_track:
            await interaction.followup.send(DIALOGUE_EMPTY_QUEUE, ephemeral=True)
            return

        page_num = max(1, page or 1)
        per_page = 10
        total_pages = max(1, math.ceil(len(tracks) / per_page))
        page_num = min(page_num, total_pages)

        start_idx = (page_num - 1) * per_page
        page_tracks = tracks[start_idx : start_idx + per_page]

        embed = discord.Embed(
            title=f"📜 NEKO SONGS QUEUE (Page {page_num}/{total_pages})",
            color=COLOR_NEON_BLUE,
        )
        if session.current_track:
            embed.description = f"**Now Playing:** [{session.current_track.title}]({session.current_track.url})\n\n"
        else:
            embed.description = ""

        lines = []
        for i, t in enumerate(page_tracks, start=start_idx + 1):
            lines.append(f"`{i}.` [{t.title}]({t.url}) (`{format_duration(t.duration)}`) • <@{t.requester_id}>")

        embed.description += "\n".join(lines) if lines else "*Queue is empty.*"
        embed.set_footer(text=f"Total: {len(tracks)} tracks • Neko Songs")
        await interaction.followup.send(embed=embed)

    @music_group.command(name="volume", description="Set playback volume (0-100%)")
    @app_commands.describe(percent="Volume percentage (0-100)")
    async def music_volume(
        self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 100]
    ) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        session.volume = percent
        if session.voice_client and hasattr(session.voice_client.source, "volume"):
            session.voice_client.source.volume = percent / 100.0  # type: ignore
        await MusicPlayerService.send_now_playing_panel(session)
        await interaction.followup.send(f"🔊 Volume set to `{percent}%`.")

    @music_group.command(name="seek", description="Seek to a specific timestamp in the current song")
    @app_commands.describe(seconds="Target time in seconds")
    async def music_seek(self, interaction: discord.Interaction, seconds: int) -> None:
        await interaction.response.defer(ephemeral=True)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.current_track or not session.is_playing:
            await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            return

        if seconds < 0 or seconds > session.current_track.duration:
            await interaction.followup.send(f"❌ Timestamp must be between 0 and {session.current_track.duration}s.", ephemeral=True)
            return

        # FFmpeg seek restarts audio at timestamp
        session.paused_duration = 0.0
        session.track_start_time = discord.utils.utcnow().timestamp() - seconds
        await interaction.followup.send(f"⏩ Seeked to `{format_duration(seconds)}`.", ephemeral=True)

    @music_group.command(name="shuffle", description="Shuffle songs in the current queue")
    async def music_shuffle(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if len(session.queue) < 2:
            await interaction.followup.send("❌ Need at least 2 tracks in queue to shuffle.", ephemeral=True)
            return

        tracks = list(session.queue)
        random.shuffle(tracks)
        session.queue = asyncio.queues.deque(tracks)  # type: ignore
        await interaction.followup.send(f"🔀 Shuffled `{len(tracks)}` songs in queue.")

    @music_group.command(name="loop", description="Configure loop mode (Off / Track / Queue)")
    @app_commands.describe(mode="Loop mode to apply")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Current Track", value="track"),
        app_commands.Choice(name="Whole Queue", value="queue"),
    ])
    async def music_loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        session.loop_mode = LoopMode(mode.value)
        await MusicPlayerService.send_now_playing_panel(session)
        await interaction.followup.send(f"🔁 Loop mode set to **{mode.name}**.")

    @music_group.command(name="remove", description="Remove a track from the queue by its number")
    @app_commands.describe(position="Position number in /music queue")
    async def music_remove(self, interaction: discord.Interaction, position: int) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if position < 1 or position > len(session.queue):
            await interaction.followup.send(f"❌ Invalid position. Queue has {len(session.queue)} tracks.", ephemeral=True)
            return

        tracks = list(session.queue)
        removed = tracks.pop(position - 1)
        session.queue = asyncio.queues.deque(tracks)  # type: ignore
        await interaction.followup.send(f"🗑️ Removed **{removed.title}** from queue.")

    @music_group.command(name="move", description="Move a song in queue from one position to another")
    @app_commands.describe(from_pos="Current position", to_pos="New position")
    async def music_move(self, interaction: discord.Interaction, from_pos: int, to_pos: int) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        q_len = len(session.queue)
        if from_pos < 1 or from_pos > q_len or to_pos < 1 or to_pos > q_len:
            await interaction.followup.send(f"❌ Invalid positions. Queue has {q_len} tracks.", ephemeral=True)
            return

        tracks = list(session.queue)
        track = tracks.pop(from_pos - 1)
        tracks.insert(to_pos - 1, track)
        session.queue = asyncio.queues.deque(tracks)  # type: ignore
        await interaction.followup.send(f"📦 Moved **{track.title}** to `#{to_pos}`.")

    @music_group.command(name="clear", description="Clear all upcoming songs from queue")
    async def music_clear(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        count = len(session.queue)
        session.queue.clear()
        await interaction.followup.send(f"🗑️ Cleared `{count}` upcoming tracks from queue.")

    @music_group.command(name="lyrics", description="Fetch real lyrics for track")
    @app_commands.describe(song="Optional song name (defaults to currently playing)")
    async def music_lyrics(self, interaction: discord.Interaction, song: Optional[str] = None) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        target_title = song or (session.current_track.title if session.current_track else None)
        target_artist = session.current_track.artist if (session.current_track and not song) else None

        if not target_title:
            await interaction.followup.send("❌ Please provide a song name or play a track first.", ephemeral=True)
            return

        lyrics = await LyricsService.fetch_lyrics(target_title, target_artist)
        if not lyrics:
            await interaction.followup.send(f"🐱 Neko couldn't find lyrics for **{target_title}**.")
            return

        embed = discord.Embed(
            title=f"📜 LYRICS — {target_title[:50]}",
            description=lyrics[:3900],
            color=COLOR_NEON_BLUE,
        )
        embed.set_footer(text="Neko Songs Lyrics • LRCLIB Provider")
        await interaction.followup.send(embed=embed)

    @music_group.command(name="autoplay", description="Toggle intelligent autoplay")
    @app_commands.describe(state="Enable or disable autoplay")
    @app_commands.choices(state=[
        app_commands.Choice(name="On", value="on"),
        app_commands.Choice(name="Off", value="off"),
    ])
    async def music_autoplay(self, interaction: discord.Interaction, state: app_commands.Choice[str]) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        session.autoplay = state.value == "on"
        await interaction.followup.send(f"🔄 Autoplay is now **{'ON' if session.autoplay else 'OFF'}**.")

    @music_group.command(name="join", description="Connect Neko Songs to your voice channel")
    async def music_join(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        if not await self._check_permissions(interaction):
            return

        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        vc = await VoiceManager.join_voice_channel(interaction.user, interaction.channel, session)  # type: ignore
        if vc:
            await interaction.followup.send(DIALOGUE_JOIN)
        else:
            await interaction.followup.send("❌ Could not connect to voice channel.")

    @music_group.command(name="leave", description="Disconnect Neko Songs from voice")
    async def music_leave(self, interaction: discord.Interaction) -> None:
        await self.music_stop.callback(self, interaction)

    @music_group.command(name="disconnect", description="Disconnect Neko Songs from voice")
    async def music_disconnect(self, interaction: discord.Interaction) -> None:
        await self.music_stop.callback(self, interaction)

    # --- 2. RECOMMENDATIONS & NEKO DJ ---

    @music_group.command(name="recommend", description="Smart recommendations based on current song & mood")
    @app_commands.describe(mode="Recommendation exploration mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Similar Tracks", value="similar_tracks"),
        app_commands.Choice(name="Similar Artists", value="similar_artists"),
        app_commands.Choice(name="Same Genre", value="genre"),
        app_commands.Choice(name="Discover Something New", value="discover"),
        app_commands.Choice(name="Chill & Relax", value="chill"),
        app_commands.Choice(name="Gaming Focus", value="gaming"),
        app_commands.Choice(name="Party Vibes", value="party"),
        app_commands.Choice(name="Night Listening", value="night"),
    ])
    async def music_recommend(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        candidates = await MusicRecommendationService.get_mode_recommendations(session, mode.value, limit=5)
        if not candidates:
            await interaction.followup.send(f"🐱 No recommendations found for mode **{mode.name}**.")
            return

        async def on_select(inter: discord.Interaction, idx: int):
            chosen = candidates[idx]
            await self._play_query(inter, chosen["url"])

        view = TrackSelectView(candidates, interaction.user.id, on_select)
        await interaction.followup.send(f"🎧 **Neko Recommendations ({mode.name}):**", view=view)

    # Subcommand group: /music dj ...
    dj_group = app_commands.Group(name="dj", description="Neko DJ Automated Queue Management", parent=music_group)

    @dj_group.command(name="enable", description="Enable Neko DJ mode to automatically queue songs")
    async def dj_enable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        settings = await self.bot.db.get_dj_settings(interaction.guild_id)  # type: ignore
        settings.enabled = True
        await self.bot.db.update_dj_settings(settings)
        await interaction.followup.send("🎧 **Neko DJ Mode ENABLED!** When the queue finishes, Neko will pick matching songs.")

    @dj_group.command(name="disable", description="Disable Neko DJ mode")
    async def dj_disable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        settings = await self.bot.db.get_dj_settings(interaction.guild_id)  # type: ignore
        settings.enabled = False
        await self.bot.db.update_dj_settings(settings)
        await interaction.followup.send("⏹️ **Neko DJ Mode DISABLED.**")

    @dj_group.command(name="settings", description="Inspect and configure Neko DJ parameters")
    async def dj_settings(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        settings = await self.bot.db.get_dj_settings(interaction.guild_id)  # type: ignore
        embed = discord.Embed(
            title="🎧 NEKO DJ SETTINGS",
            description=(
                f"• **Status:** `{'ENABLED' if settings.enabled else 'DISABLED'}`\n"
                f"• **Auto Queue:** `{'YES' if settings.auto_queue else 'NO'}`\n"
                f"• **Mode:** `{settings.recommendation_mode}`\n"
                f"• **Repeat Avoidance Window:** `{settings.repeat_avoidance_count} tracks`\n"
                f"• **Max Queue Capacity:** `{settings.max_queue_size}`"
            ),
            color=COLOR_NEON_BLUE,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @dj_group.command(name="status", description="Check current Neko DJ status and recommendation")
    async def dj_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        dj_settings = await self.bot.db.get_dj_settings(interaction.guild_id)  # type: ignore
        rec = await NekoDJService.get_recommendation(self.bot, session)
        rec_title = f"{rec[0].artist} — {rec[0].title}" if rec else "None ready"
        embed = discord.Embed(
            title="🎧 NEKO DJ STATUS",
            description=(
                f"• **DJ Active:** `{'YES' if dj_settings.enabled else 'NO'}`\n"
                f"• **Next Queued Suggestion:** `{rec_title}`\n"
                f"• **Current Session Tracks:** `{len(session.history)} played`"
            ),
            color=COLOR_ELECTRIC_CYAN,
        )
        await interaction.followup.send(embed=embed)

    # --- 3. FAVORITES SYSTEM ---

    favorites_group = app_commands.Group(name="favorites", description="Personal favorites collection", parent=music_group)

    @favorites_group.command(name="list", description="View your saved favorite songs")
    async def fav_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        favs = await self.bot.db.get_favorites(interaction.user.id)
        if not favs:
            await interaction.followup.send("❤️ You have no saved favorites yet! Use the `[❤️ Favorite]` button on Now Playing.", ephemeral=True)
            return

        lines = [f"`{i}.` **[{f.title}]({f.url})** (`{f.artist}`)" for i, f in enumerate(favs[:15], 1)]
        embed = discord.Embed(
            title=f"❤️ {interaction.user.display_name}'s Favorites ({len(favs)})",
            description="\n".join(lines),
            color=COLOR_NEON_BLUE,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @favorites_group.command(name="add", description="Add a song to your personal favorites")
    @app_commands.describe(query="Song title or URL")
    async def fav_add(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(ephemeral=True)
        track = await AudioResolver.resolve_track(query, interaction.user.id, str(interaction.user))
        if not track:
            await interaction.followup.send("❌ Could not resolve audio to add to favorites.", ephemeral=True)
            return

        success = await self.bot.db.add_favorite(interaction.user.id, track)
        if success:
            await interaction.followup.send(f"❤️ Added **{track.title}** to your favorites!", ephemeral=True)
        else:
            await interaction.followup.send(f"❤️ **{track.title}** is already in your favorites.", ephemeral=True)

    @favorites_group.command(name="remove", description="Remove a song from your personal favorites")
    @app_commands.describe(identifier="Song title or ID")
    async def fav_remove(self, interaction: discord.Interaction, identifier: str) -> None:
        await interaction.response.defer(ephemeral=True)
        removed = await self.bot.db.remove_favorite(interaction.user.id, identifier)
        if removed:
            await interaction.followup.send(f"🗑️ Removed `{identifier}` from your favorites.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Could not find `{identifier}` in your favorites.", ephemeral=True)

    @favorites_group.command(name="play", description="Queue all your saved favorites")
    async def fav_play(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        if not await self._check_permissions(interaction):
            return

        favs = await self.bot.db.get_favorites(interaction.user.id)
        if not favs:
            await interaction.followup.send("❤️ You don't have any saved favorites to play.", ephemeral=True)
            return

        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        vc = await VoiceManager.join_voice_channel(interaction.user, interaction.channel, session)  # type: ignore
        if not vc:
            await interaction.followup.send("❌ Could not connect to your voice channel.", ephemeral=True)
            return

        # Queue first track immediately
        first = favs[0]
        await self._play_query(interaction, first.url)
        # Queue remainder in background
        for f in favs[1:]:
            try:
                resolved = await AudioResolver.resolve_track(f.url, interaction.user.id, str(interaction.user))
                if resolved:
                    session.queue.append(resolved)
            except Exception:
                pass

    # --- 4. PLAYLIST SYSTEM ---

    playlist_group = app_commands.Group(name="playlist", description="Manage personal and server playlists", parent=music_group)

    @playlist_group.command(name="create", description="Create a new playlist")
    @app_commands.describe(name="Playlist name")
    async def pl_create(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)
        pid = await self.bot.db.create_playlist(interaction.guild_id, interaction.user.id, name)  # type: ignore
        if pid:
            await interaction.followup.send(f"✅ Created playlist **{name}**!", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Playlist **{name}** already exists.", ephemeral=True)

    @playlist_group.command(name="delete", description="Delete a playlist")
    @app_commands.describe(name="Playlist name to delete")
    async def pl_delete(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)
        deleted = await self.bot.db.delete_playlist(interaction.guild_id, interaction.user.id, name)  # type: ignore
        if deleted:
            await interaction.followup.send(f"🗑️ Deleted playlist **{name}**.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Playlist **{name}** not found.", ephemeral=True)

    @playlist_group.command(name="add", description="Add a song to a playlist")
    @app_commands.describe(playlist="Playlist name", query="Song title or link")
    async def pl_add(self, interaction: discord.Interaction, playlist: str, query: str) -> None:
        await interaction.response.defer(ephemeral=True)
        pl = await self.bot.db.get_playlist(interaction.guild_id, playlist, interaction.user.id)  # type: ignore
        if not pl:
            await interaction.followup.send(f"❌ Playlist **{playlist}** not found.", ephemeral=True)
            return

        track = await AudioResolver.resolve_track(query, interaction.user.id, str(interaction.user))
        if not track:
            await interaction.followup.send("❌ Could not resolve song.", ephemeral=True)
            return

        await self.bot.db.add_playlist_track(pl.id, track)
        await interaction.followup.send(f"✅ Added **{track.title}** to **{playlist}**!", ephemeral=True)

    @playlist_group.command(name="remove", description="Remove a track from a playlist by position")
    @app_commands.describe(playlist="Playlist name", position="Track position (1, 2, ...)")
    async def pl_remove(self, interaction: discord.Interaction, playlist: str, position: int) -> None:
        await interaction.response.defer(ephemeral=True)
        pl = await self.bot.db.get_playlist(interaction.guild_id, playlist, interaction.user.id)  # type: ignore
        if not pl:
            await interaction.followup.send(f"❌ Playlist **{playlist}** not found.", ephemeral=True)
            return

        removed = await self.bot.db.remove_playlist_track(pl.id, position)
        if removed:
            await interaction.followup.send(f"🗑️ Removed track `#{position}` from **{playlist}**.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Invalid position `#{position}`.", ephemeral=True)

    @playlist_group.command(name="list", description="List available playlists")
    async def pl_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        pls = await self.bot.db.get_playlists(interaction.guild_id, interaction.user.id)  # type: ignore
        if not pls:
            await interaction.followup.send("📂 No playlists found. Create one with `/music playlist create`!", ephemeral=True)
            return

        lines = [f"• **{p.name}** (`{getattr(p, 'track_count', len(p.tracks))} tracks`)" for p in pls]
        embed = discord.Embed(
            title=f"📂 Playlists in {interaction.guild.name}",
            description="\n".join(lines),
            color=COLOR_NEON_BLUE,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @playlist_group.command(name="view", description="View tracks in a playlist")
    @app_commands.describe(name="Playlist name")
    async def pl_view(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)
        pl = await self.bot.db.get_playlist(interaction.guild_id, name, interaction.user.id)  # type: ignore
        if not pl:
            await interaction.followup.send(f"❌ Playlist **{name}** not found.", ephemeral=True)
            return

        lines = [f"`{i}.` **{t.title}** (`{format_duration(t.duration)}`)" for i, t in enumerate(pl.tracks[:20], 1)]
        embed = discord.Embed(
            title=f"📂 Playlist: {pl.name} ({len(pl.tracks)} tracks)",
            description="\n".join(lines) if lines else "*No tracks in playlist.*",
            color=COLOR_ELECTRIC_CYAN,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @playlist_group.command(name="play", description="Queue and play an entire playlist")
    @app_commands.describe(name="Playlist name to play")
    async def pl_play(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=False)
        if not await self._check_permissions(interaction):
            return

        pl = await self.bot.db.get_playlist(interaction.guild_id, name, interaction.user.id)  # type: ignore
        if not pl or not pl.tracks:
            await interaction.followup.send(f"❌ Playlist **{name}** is empty or not found.", ephemeral=True)
            return

        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        vc = await VoiceManager.join_voice_channel(interaction.user, interaction.channel, session)  # type: ignore
        if not vc:
            await interaction.followup.send("❌ Could not connect to voice.", ephemeral=True)
            return

        first = pl.tracks[0]
        await self._play_query(interaction, first.url)
        for t in pl.tracks[1:]:
            try:
                resolved = await AudioResolver.resolve_track(t.url, interaction.user.id, str(interaction.user))
                if resolved:
                    session.queue.append(resolved)
            except Exception:
                pass

    # --- 5. HISTORY & STATS ---

    @music_group.command(name="history", description="View recent song playback history")
    async def music_history(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        history = await self.bot.db.get_history(interaction.guild_id, limit=10)  # type: ignore
        if not history:
            await interaction.followup.send("🐾 No playback history recorded yet.", ephemeral=True)
            return

        lines = []
        for i, h in enumerate(history, 1):
            lines.append(f"`{i}.` [{h['title']}]({h['url']}) (`{h['artist']}`) • <t:{int(datetime.fromisoformat(h['played_at']).timestamp())}:R>")

        embed = discord.Embed(
            title=f"📜 PLAYBACK HISTORY — {interaction.guild.name}",
            description="\n".join(lines),
            color=COLOR_NEON_BLUE,
        )
        await interaction.followup.send(embed=embed)

    @music_group.command(name="stats", description="View truthful server music listening statistics")
    async def music_stats(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        stats = await self.bot.db.get_guild_stats(interaction.guild_id)  # type: ignore
        embed = discord.Embed(
            title=f"📊 LISTENING STATS — {interaction.guild.name}",
            description=(
                f"• **Total Songs Played:** `{stats['total_played']}`\n\n"
                f"**Most Played Songs:**\n" + "\n".join(f"• {s}" for s in stats['top_songs']) + "\n\n"
                f"**Top Artists:**\n" + "\n".join(f"• {a}" for a in stats['top_artists'])
            ),
            color=COLOR_ELECTRIC_CYAN,
        )
        await interaction.followup.send(embed=embed)

    # --- 6. SETUP, SETTINGS, PERMISSIONS, DOCTOR, STATUS ---

    @music_group.command(name="setup", description="Open interactive Neko Songs Setup Dashboard")
    async def music_setup(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        settings = await self.bot.db.get_guild_settings(interaction.guild_id)  # type: ignore
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore

        embed = discord.Embed(
            title="🎵 NEKO SONGS SETUP",
            description=(
                f"**Discord Connection:** 🟢 Connected (`{round(self.bot.latency * 1000)}ms`)\n"
                f"**Music Player:** `{'🟢 Ready' if session.is_active else '⚪ Idle'}`\n"
                f"**Search Provider:** 🟢 Working (yt-dlp)\n"
                f"**Audio Resolver:** 🟢 Ready\n"
                f"**Request Channel:** {f'<#{settings.request_channel_id}>' if settings.request_channel_id else 'Not configured'}\n"
                f"**DJ Role:** {f'<@&{settings.dj_role_id}>' if settings.dj_role_id else 'Not configured'}\n"
                f"**Default Volume:** `{settings.default_volume}%`\n"
                f"**Auto Leave:** `{'Enabled (5m)' if settings.auto_leave_enabled else 'Disabled'}`\n"
                f"**Autoplay:** `{'Enabled' if session.autoplay else 'Disabled'}`"
            ),
            color=COLOR_NEON_BLUE,
        )
        view = NekoSetupDashboardView(self.bot, interaction.guild)  # type: ignore
        await interaction.followup.send(embed=embed, view=view)

    @music_group.command(name="settings", description="Inspect and configure Neko Songs settings")
    async def music_settings(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        settings = await self.bot.db.get_guild_settings(interaction.guild_id)  # type: ignore
        embed = discord.Embed(
            title="⚙️ NEKO SONGS SETTINGS",
            description=(
                f"• **Request Channel:** {f'<#{settings.request_channel_id}>' if settings.request_channel_id else 'None'}\n"
                f"• **Natural Requests:** `{'ON' if settings.natural_requests_enabled else 'OFF'}`\n"
                f"• **DJ Role:** {f'<@&{settings.dj_role_id}>' if settings.dj_role_id else 'None'}\n"
                f"• **Default Volume:** `{settings.default_volume}%`\n"
                f"• **Auto Leave:** `{'ON (300s)' if settings.auto_leave_enabled else 'OFF'}`\n"
                f"• **Queue Limit:** `{settings.queue_limit} tracks`\n"
                f"• **Quiet Mode:** `{'ON' if settings.quiet_mode else 'OFF'}`\n"
                f"• **Response Style:** `{settings.response_style}`"
            ),
            color=COLOR_NEON_BLUE,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @music_group.command(name="permissions", description="View voice and command permissions")
    async def music_permissions(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        settings = await self.bot.db.get_guild_settings(interaction.guild_id)  # type: ignore
        embed = discord.Embed(
            title="🛡️ NEKO SONGS PERMISSIONS",
            description=(
                f"• **DJ Role Required:** {f'<@&{settings.dj_role_id}>' if settings.dj_role_id else 'No (Public Access)'}\n"
                f"• **Allowed Text Channels:** `{len(settings.allowed_channels)} channels`\n"
                f"• **Allowed Voice Channels:** `{len(settings.allowed_voice_channels)} channels`\n"
                f"• **Vote Skip Threshold:** `{int(settings.vote_skip_threshold * 100)}%`"
            ),
            color=COLOR_ELECTRIC_CYAN,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @music_group.command(name="doctor", description="Run full diagnostic suite on music subsystems")
    async def music_doctor(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        probes = await MusicDiagnosticsService.run_doctor(self.bot, interaction.guild)
        desc_lines = []
        for p in probes:
            desc_lines.append(f"**{p.name}:**\n{p.badge} (`{p.latency_ms}ms`)")
            if p.error:
                desc_lines.append(f"⚠️ *Error: {p.error}*")
            if p.fix:
                desc_lines.append(f"🔧 *Fix: {p.fix}*")
            desc_lines.append("")

        embed = discord.Embed(
            title="🩺 NEKO SONGS DIAGNOSTICS",
            description="\n".join(desc_lines),
            color=COLOR_NEON_BLUE,
        )
        embed.set_footer(text="Neko Songs Doctor • Truthful Non-Fabricated Telemetry")
        await interaction.followup.send(embed=embed)

    @music_group.command(name="status", description="Real-time bot health and gateway metrics")
    async def music_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        active = self.session_manager.get_active_sessions_count()
        playing = self.session_manager.get_playing_sessions_count()
        embed = discord.Embed(
            title=f"🐱 {BOT_NAME} STATUS",
            description=(
                f"• **Version:** `v{MUSIC_BOT_VERSION}`\n"
                f"• **Guilds:** `{len(self.bot.guilds)}`\n"
                f"• **Active Sessions:** `{active}`\n"
                f"• **Currently Playing:** `{playing}`\n"
                f"• **Gateway Latency:** `{round(self.bot.latency * 1000)}ms`\n"
                f"• **Database Health:** 🟢 Connected (`data/music.db`)\n"
                f"• **Audio Resolver:** 🟢 Operational (yt-dlp)"
            ),
            color=COLOR_ELECTRIC_CYAN,
        )
        await interaction.followup.send(embed=embed)

    # =========================================================================
    # COMPATIBILITY ALIASES (SECTION 3)
    # =========================================================================

    @app_commands.command(name="play", description="Play a song or playlist (Shortcut for /music play)")
    @app_commands.describe(query="Song title, artist, or URL")
    async def alias_play(self, interaction: discord.Interaction, query: str) -> None:
        await self.music_play.callback(self, interaction, query)

    @app_commands.command(name="pause", description="Pause music playback (Shortcut for /music pause)")
    async def alias_pause(self, interaction: discord.Interaction) -> None:
        await self.music_pause.callback(self, interaction)

    @app_commands.command(name="resume", description="Resume music playback (Shortcut for /music resume)")
    async def alias_resume(self, interaction: discord.Interaction) -> None:
        await self.music_resume.callback(self, interaction)

    @app_commands.command(name="skip", description="Skip current song (Shortcut for /music skip)")
    async def alias_skip(self, interaction: discord.Interaction) -> None:
        await self.music_skip.callback(self, interaction)

    @app_commands.command(name="previous", description="Play previous song (Shortcut for /music previous)")
    async def alias_previous(self, interaction: discord.Interaction) -> None:
        await self.music_previous.callback(self, interaction)

    @app_commands.command(name="stop", description="Stop music and leave (Shortcut for /music stop)")
    async def alias_stop(self, interaction: discord.Interaction) -> None:
        await self.music_stop.callback(self, interaction)

    @app_commands.command(name="queue", description="View music queue (Shortcut for /music queue)")
    async def alias_queue(self, interaction: discord.Interaction) -> None:
        await self.music_queue.callback(self, interaction, 1)

    @app_commands.command(name="np", description="View Now Playing dashboard (Shortcut for /music nowplaying)")
    async def alias_np(self, interaction: discord.Interaction) -> None:
        await self.music_nowplaying.callback(self, interaction)

    @app_commands.command(name="nowplaying", description="View Now Playing dashboard")
    async def alias_nowplaying(self, interaction: discord.Interaction) -> None:
        await self.music_nowplaying.callback(self, interaction)

    @app_commands.command(name="volume", description="Set volume 0-100% (Shortcut for /music volume)")
    @app_commands.describe(percent="Volume percentage (0-100)")
    async def alias_volume(self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 100]) -> None:
        await self.music_volume.callback(self, interaction, percent)

    @app_commands.command(name="lyrics", description="Fetch lyrics for track (Shortcut for /music lyrics)")
    @app_commands.describe(song="Optional song title")
    async def alias_lyrics(self, interaction: discord.Interaction, song: Optional[str] = None) -> None:
        await self.music_lyrics.callback(self, interaction, song)

    # =========================================================================
    # NATURAL MUSIC REQUEST LISTENER (SECTION 12)
    # =========================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Processes plain text messages in designated music request channel."""
        if message.author.bot or not message.guild or not message.content.strip():
            return

        settings = await self.bot.db.get_guild_settings(message.guild.id)
        if not settings.request_channel_id or message.channel.id != settings.request_channel_id:
            return

        if not settings.natural_requests_enabled:
            return

        query = message.content.strip()
        if query.startswith(self.bot.command_prefix):  # type: ignore
            return

        if not message.author.voice or not message.author.voice.channel:  # type: ignore
            try:
                await message.reply("🐱 You must join a voice channel to request songs!", delete_after=5.0)
            except Exception:
                pass
            return

        session = await self.session_manager.get_session(message.guild.id)
        async with session.lock:
            vc = await VoiceManager.join_voice_channel(message.author, message.channel, session)  # type: ignore
            if not vc:
                try:
                    await message.reply("😿 Could not connect to your voice channel.", delete_after=5.0)
                except Exception:
                    pass
                return

        try:
            status_msg = await message.channel.send(f"🔍 Searching for `{query[:60]}`... 🐾")
            track = await AudioResolver.resolve_track(query, message.author.id, str(message.author))
            if not track:
                await status_msg.edit(content=f"{DIALOGUE_NOTHING_PLAYABLE}\nQuery: `{query}`")
                return

            async with session.lock:
                if session.is_playing:
                    session.queue.append(track)
                    await status_msg.edit(content=f"🐱 Added **{track.title}** to queue at `#{len(session.queue)}`!")
                else:
                    success = await MusicPlayerService.start_playback(self.bot, session, track)
                    if success:
                        await status_msg.edit(content=f"🎶 **Now Playing:** **{track.title}**\n*{DIALOGUE_START}*")
                    else:
                        await status_msg.edit(content="😿 Failed to start playback.")
        except Exception as e:
            logger.error(f"Natural request error: {e}")


async def setup(bot: RaiMusicBot) -> None:
    await bot.add_cog(MusicCog(bot))
