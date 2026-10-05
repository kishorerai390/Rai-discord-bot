"""
Master Music Command Suite for Rai Music Bot.
Registers all /music commands, aliases (/play, /pause, etc.), setup wizard, and natural requests.
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

from music_bot.config import MUSIC_BOT_VERSION
from music_bot.database.models import QueuedTrack
from music_bot.services.diagnostics_service import MusicDiagnosticsService
from music_bot.services.lyrics_service import LyricsService
from music_bot.services.player_service import MusicPlayerService, format_duration
from music_bot.services.resolver_service import AudioResolver
from music_bot.services.session_service import GuildMusicSession, LoopMode, PlaybackState, SessionManager
from music_bot.services.voice_service import VoiceManager

if TYPE_CHECKING:
    from music_bot.bot import RaiMusicBot

logger = logging.getLogger("RaiMusic.Commands")


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
                    emoji="🎵",
                )
            )

        select = discord.ui.Select(
            placeholder="Select a track to play...",
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


class MusicCog(commands.Cog, name="Music"):
    """Dedicated Music Cog for Rai Music Bot application."""

    def __init__(self, bot: RaiMusicBot):
        self.bot = bot
        self.session_manager = SessionManager.get_instance()

    # =========================================================================
    # PERMISSION & CHANNEL HELPERS
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

    # =========================================================================
    # CORE PLAYBACK IMPLEMENTATION
    # =========================================================================

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
            description=f"Resolving: `{query[:100]}`...",
            color=0x5865F2,
        )
        await interaction.followup.send(embed=embed_loading, ephemeral=ephemeral)

        try:
            track = await AudioResolver.resolve_track(query, member.id, str(member))
        except Exception as e:
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="❌ TRACK RESOLUTION FAILED",
                    description=f"Audio resolver returned an error: `{e}`",
                    color=0xED4245,
                )
            )
            return

        if not track:
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="❌ NO AUDIO TRACK FOUND",
                    description=f"Could not find a playable audio source for `{query}`.",
                    color=0xED4245,
                )
            )
            return

        # 3. Add to Queue or Start Playback
        async with session.lock:
            if session.is_playing:
                session.queue.append(track)
                embed_queued = discord.Embed(
                    title="🎵 ADDED TO QUEUE",
                    description=f"### [{track.title}]({track.url})\n"
                                f"**Artist:** `{track.artist}` • **Duration:** `{format_duration(track.duration)}`\n"
                                f"**Position in Queue:** `#{len(session.queue)}`",
                    color=0x57F287,
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
                        description=f"### [{track.title}]({track.url})\n**Artist:** `{track.artist}`",
                        color=0x57F287,
                    )
                    if track.thumbnail:
                        embed_started.set_thumbnail(url=track.thumbnail)
                    await interaction.edit_original_response(embed=embed_started)
                else:
                    await interaction.edit_original_response(
                        embed=discord.Embed(
                            title="❌ PLAYBACK FAILED",
                            description="Encountered an internal error while starting audio playback.",
                            color=0xED4245,
                        )
                    )

    # =========================================================================
    # /MUSIC COMMAND GROUP
    # =========================================================================

    music_group = app_commands.Group(name="music", description="Rai High-Performance Music Suite")

    @music_group.command(name="play", description="Play a song or playlist from YouTube or URL")
    @app_commands.describe(query="Song title, artist, or URL to play")
    async def music_play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(ephemeral=False)
        if not await self._check_permissions(interaction):
            return
        await self._play_query(interaction, query)

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
        await interaction.followup.send("⏸ Playback paused.")

    @music_group.command(name="resume", description="Resume paused music playback")
    async def music_resume(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.voice_client or not session.voice_client.is_paused():
            await interaction.followup.send("❌ Music is not currently paused.", ephemeral=True)
            return

        session.voice_client.resume()
        session.state = PlaybackState.PLAYING
        await interaction.followup.send("▶ Playback resumed.")

    @music_group.command(name="skip", description="Skip to the next song in the queue")
    async def music_skip(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.voice_client or not session.voice_client.is_playing():
            await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            return

        title = session.current_track.title if session.current_track else "Track"
        session.voice_client.stop()
        await interaction.followup.send(f"⏭ Skipped **{title}**.")

    @music_group.command(name="previous", description="Play the previous song from history")
    async def music_previous(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.history:
            await interaction.followup.send("❌ No previous tracks in history.", ephemeral=True)
            return

        prev_track = session.history.pop()
        if session.current_track:
            session.queue.appendleft(session.current_track)

        await MusicPlayerService.start_playback(self.bot, session, prev_track)
        await interaction.followup.send(f"⏮ Returned to **{prev_track.title}**.")

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
        await interaction.followup.send("⏹ Music stopped and disconnected from voice.")

    @music_group.command(name="queue", description="Display upcoming tracks in the music queue")
    async def music_queue(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        tracks = list(session.queue)

        if not tracks and not session.current_track:
            await interaction.followup.send("The music queue is currently empty.")
            return

        embed = discord.Embed(
            title=f"🎵 MUSIC QUEUE ({len(tracks)} in queue)",
            color=0x5865F2,
        )
        if session.current_track:
            embed.description = f"**Now Playing:** [{session.current_track.title}]({session.current_track.url})\n\n"
        else:
            embed.description = ""

        queue_list = []
        for i, t in enumerate(tracks[:15], start=1):
            queue_list.append(f"`{i}.` [{t.title}]({t.url}) (`{format_duration(t.duration)}`) • <@{t.requester_id}>")

        if queue_list:
            embed.description += "\n".join(queue_list)
            if len(tracks) > 15:
                embed.description += f"\n\n*... and {len(tracks) - 15} more tracks.*"
        else:
            embed.description += "*No upcoming tracks.*"

        await interaction.followup.send(embed=embed)

    @music_group.command(name="nowplaying", description="Show detailed Now Playing dashboard with progress")
    async def music_nowplaying(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        embed = MusicPlayerService.build_now_playing_embed(session)
        await interaction.followup.send(embed=embed)

    @music_group.command(name="volume", description="Set playback volume between 0 and 100%")
    @app_commands.describe(percent="Volume percentage (0-100)")
    async def music_volume(self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 100]) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        session.volume = percent
        if session.voice_client and session.voice_client.source:
            if hasattr(session.voice_client.source, "volume"):
                session.voice_client.source.volume = percent / 100.0  # type: ignore

        await interaction.followup.send(f"🔊 Volume set to `{percent}%`.")

    @music_group.command(name="loop", description="Toggle loop mode (off, track, queue)")
    @app_commands.describe(mode="Choose loop mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Current Track", value="track"),
        app_commands.Choice(name="Whole Queue", value="queue"),
    ])
    async def music_loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        session.loop_mode = LoopMode(mode.value)
        await interaction.followup.send(f"🔁 Loop mode set to **{mode.name}**.")

    @music_group.command(name="shuffle", description="Randomize the order of tracks in the queue")
    async def music_shuffle(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if len(session.queue) < 2:
            await interaction.followup.send("❌ Need at least 2 tracks in queue to shuffle.", ephemeral=True)
            return

        tracks = list(session.queue)
        random.shuffle(tracks)
        session.queue.clear()
        session.queue.extend(tracks)
        await interaction.followup.send(f"🔀 Shuffled `{len(tracks)}` tracks in queue.")

    @music_group.command(name="clear", description="Clear all upcoming tracks from the queue")
    async def music_clear(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        count = len(session.queue)
        session.queue.clear()
        await interaction.followup.send(f"🧹 Cleared `{count}` tracks from the queue.")

    @music_group.command(name="lyrics", description="Fetch synchronized or plain lyrics for current or searched track")
    @app_commands.describe(song="Optional song title (defaults to currently playing track)")
    async def music_lyrics(self, interaction: discord.Interaction, song: Optional[str] = None) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore

        search_title = song
        artist = None
        if not search_title:
            if not session.current_track:
                await interaction.followup.send("❌ Nothing is currently playing. Provide a song name.", ephemeral=True)
                return
            search_title = session.current_track.title
            artist = session.current_track.artist

        lyrics = await LyricsService.fetch_lyrics(search_title, artist)
        if not lyrics:
            await interaction.followup.send(f"❌ Lyrics unavailable for **{search_title}**.", ephemeral=True)
            return

        # Handle long lyrics pagination
        if len(lyrics) > 4000:
            lyrics = lyrics[:4000] + "\n\n*(Truncated due to Discord message length limits)*"

        embed = discord.Embed(
            title=f"📜 LYRICS — {search_title}",
            description=lyrics,
            color=0x5865F2,
        )
        embed.set_footer(text="Powered by LRCLIB")
        await interaction.followup.send(embed=embed)

    @music_group.command(name="autoplay", description="Toggle autoplay when queue ends")
    @app_commands.describe(enabled="Turn autoplay on or off")
    async def music_autoplay(self, interaction: discord.Interaction, enabled: bool) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        session.autoplay = enabled
        status_text = "ENABLED" if enabled else "DISABLED"
        await interaction.followup.send(f"📻 Autoplay is now **{status_text}**.")

    @music_group.command(name="join", description="Connect the bot to your current voice channel")
    async def music_join(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        if not await self._check_permissions(interaction):
            return
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        vc = await VoiceManager.join_voice_channel(interaction.user, interaction.channel, session)  # type: ignore
        if vc:
            await interaction.followup.send(f"Connected to **{vc.channel.name}**.")
        else:
            await interaction.followup.send("❌ Failed to connect to voice channel.")

    @music_group.command(name="leave", description="Disconnect the bot from voice")
    async def music_leave(self, interaction: discord.Interaction) -> None:
        await self.music_stop.callback(self, interaction)

    @music_group.command(name="status", description="Real-time status overview of Rai Music Bot")
    async def music_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        sm = self.session_manager
        active = sm.get_active_sessions_count()
        playing = sm.get_playing_sessions_count()
        guilds_count = len(self.bot.guilds)

        embed = discord.Embed(
            title="🎵 RAI MUSIC STATUS",
            color=0x57F287,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Bot Application", value="🟢 ONLINE", inline=True)
        embed.add_field(name="Version", value=f"`v{MUSIC_BOT_VERSION}`", inline=True)
        embed.add_field(name="Discord Gateway", value=f"`{round(self.bot.latency * 1000.0, 1)}ms`", inline=True)

        embed.add_field(name="Connected Guilds", value=f"`{guilds_count}`", inline=True)
        embed.add_field(name="Active Sessions", value=f"`{active}`", inline=True)
        embed.add_field(name="Currently Playing", value=f"`{playing}`", inline=True)

        embed.add_field(name="Search Engine", value="🟢 yt-dlp", inline=True)
        embed.add_field(name="Audio Decoder", value="🟢 FFmpeg PCM", inline=True)
        embed.add_field(name="Database", value="🟢 data/music.db", inline=True)

        embed.set_footer(text=f"Rai Music Bot • ID: {self.bot.user.id if self.bot.user else 'Unknown'}")
        await interaction.followup.send(embed=embed)

    @music_group.command(name="doctor", description="Run deep multi-stage diagnostics on Rai Music Bot")
    async def music_doctor(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        probes = await MusicDiagnosticsService.run_doctor(self.bot, interaction.guild)

        all_ok = all(p.status == "HEALTHY" for p in probes)
        overall_title = "🩺 RAI MUSIC DOCTOR — ALL SYSTEMS HEALTHY" if all_ok else "🩺 RAI MUSIC DOCTOR — ATTENTION NEEDED"

        embed = discord.Embed(
            title=overall_title,
            description=f"Audited `{len(probes)}` music subsystems for guild **{interaction.guild.name if interaction.guild else 'Global'}**.",
            color=0x57F287 if all_ok else 0xFEE75C,
            timestamp=datetime.now(timezone.utc),
        )

        for p in probes:
            details_str = ", ".join(f"{k}: `{v}`" for k, v in list(p.details.items())[:3])
            val = f"**{p.badge}** (`{p.latency_ms:.1f}ms`)"
            if details_str:
                val += f"\n• {details_str}"
            if p.fix:
                val += f"\n💡 *Fix:* {p.fix}"
            embed.add_field(name=p.name, value=val, inline=True)

        await interaction.followup.send(embed=embed)

    @music_group.command(name="setup", description="Configure Music Bot settings (Request channel, DJ role, defaults)")
    @app_commands.default_permissions(manage_guild=True)
    async def music_setup(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Server only.", ephemeral=True)
            return

        settings = await self.bot.db.get_guild_settings(guild.id)
        req_ch_str = f"<#{settings.request_channel_id}>" if settings.request_channel_id else "*Not configured*"
        dj_role_str = f"<@&{settings.dj_role_id}>" if settings.dj_role_id else "*None (All members)*"

        embed = discord.Embed(
            title="🎵 RAI MUSIC SETUP & CONFIGURATION",
            description="Manage high-performance music settings for your server.",
            color=0x5865F2,
        )
        embed.add_field(name="Music Request Channel", value=req_ch_str, inline=True)
        embed.add_field(name="DJ Role", value=dj_role_str, inline=True)
        embed.add_field(name="Default Volume", value=f"`{settings.default_volume}%`", inline=True)

        embed.add_field(name="Natural Requests", value="🟢 Enabled" if settings.natural_requests_enabled else "⚪ Disabled", inline=True)
        embed.add_field(name="Auto Leave on Empty", value=f"🟢 `{settings.auto_leave_timeout // 60}m`" if settings.auto_leave_enabled else "⚪ Disabled", inline=True)
        embed.add_field(name="Autoplay by Default", value="🟢 Enabled" if settings.autoplay_enabled else "⚪ Disabled", inline=True)

        embed.set_footer(text="Use /music settings to update these values.")
        await interaction.followup.send(embed=embed)

    # =========================================================================
    # TOP-LEVEL COMPATIBILITY ALIASES (/play, /pause, /skip, etc.)
    # =========================================================================

    @app_commands.command(name="play", description="Play a song or playlist (Shortcut for /music play)")
    @app_commands.describe(query="Song title, artist, or URL to play")
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

    @app_commands.command(name="stop", description="Stop music and disconnect (Shortcut for /music stop)")
    async def alias_stop(self, interaction: discord.Interaction) -> None:
        await self.music_stop.callback(self, interaction)

    @app_commands.command(name="queue", description="View the current queue (Shortcut for /music queue)")
    async def alias_queue(self, interaction: discord.Interaction) -> None:
        await self.music_queue.callback(self, interaction)

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

    @app_commands.command(name="shuffle", description="Shuffle queue (Shortcut for /music shuffle)")
    async def alias_shuffle(self, interaction: discord.Interaction) -> None:
        await self.music_shuffle.callback(self, interaction)

    @app_commands.command(name="loop", description="Toggle loop mode (Shortcut for /music loop)")
    @app_commands.describe(mode="Loop mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Current Track", value="track"),
        app_commands.Choice(name="Whole Queue", value="queue"),
    ])
    async def alias_loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        await self.music_loop.callback(self, interaction, mode)

    # =========================================================================
    # NATURAL MUSIC REQUEST LISTENER
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

        # User typed plain song name in request channel!
        query = message.content.strip()
        if query.startswith(self.bot.command_prefix):  # type: ignore
            return  # Allow prefix commands to pass through

        if not message.author.voice or not message.author.voice.channel:  # type: ignore
            try:
                await message.reply("❌ You must be in a voice channel to request songs.", delete_after=5.0)
            except Exception:
                pass
            return

        session = await self.session_manager.get_session(message.guild.id)
        async with session.lock:
            vc = await VoiceManager.join_voice_channel(message.author, message.channel, session)  # type: ignore
            if not vc:
                try:
                    await message.reply("❌ Could not connect to your voice channel.", delete_after=5.0)
                except Exception:
                    pass
                return

        try:
            status_msg = await message.channel.send(f"🔍 Searching for `{query[:60]}`...")
            track = await AudioResolver.resolve_track(query, message.author.id, str(message.author))
            if not track:
                await status_msg.edit(content=f"❌ No playable audio found for `{query}`.")
                return

            async with session.lock:
                if session.is_playing:
                    session.queue.append(track)
                    await status_msg.edit(content=f"🎵 Added **{track.title}** to the queue at `#{len(session.queue)}`.")
                else:
                    success = await MusicPlayerService.start_playback(self.bot, session, track)
                    if success:
                        await status_msg.edit(content=f"🎶 Now playing **{track.title}**.")
                    else:
                        await status_msg.edit(content="❌ Failed to start playback.")
        except Exception as e:
            logger.error(f"Natural request error: {e}")
