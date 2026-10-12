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
from music_bot.services.player_service import AudioEqualizerView, MusicPlayerService, format_duration
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
            err = session.last_error or "Could not connect to your voice channel."
            await interaction.followup.send(f"❌ **{err}**", ephemeral=True)
            return

        track = await AudioResolver.resolve_track("lofi hip hop test", interaction.user.id, str(interaction.user))
        if track:
            await MusicPlayerService.start_playback(self.bot, session, track)
            await interaction.followup.send("🎵 Playing test track! Check your audio.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Failed to resolve test audio.", ephemeral=True)


# =============================================================================
# MASTER CONTROL PANEL VIEW (/c)
# =============================================================================

class MusicControlSelect(discord.ui.Select):
    """Dropdown selector for the /c master control panel."""

    def __init__(self, panel_view: "MusicControlPanelView"):
        self.panel_view = panel_view
        options = [
            discord.SelectOption(
                label="🌟 Master Overview",
                value="overview",
                description="Live system status, active voice channel, and full command guide",
                emoji="🐾",
                default=True,
            ),
            discord.SelectOption(
                label="🎵 Playback & Queue",
                value="playback",
                description="Play, skip, pause, resume, seek, queue, volume, loop, shuffle",
                emoji="🎶",
            ),
            discord.SelectOption(
                label="🎛️ Audio Filters (DSP)",
                value="filters",
                description="Bass boost, nightcore, 8D audio, vaporwave, vocal enhancer",
                emoji="🎚️",
            ),
            discord.SelectOption(
                label="📻 24/7 & Radio Modes",
                value="247_radio",
                description="Stay in voice 24/7 and continuous 24/7 vibe radio stations",
                emoji="📻",
            ),
            discord.SelectOption(
                label="🌙 Bedtime Sleep Timer",
                value="sleeptimer",
                description="Automatic countdown with smooth 30s volume fade-out",
                emoji="💤",
            ),
            discord.SelectOption(
                label="📂 Custom Playlists",
                value="playlists",
                description="Save queues to database, load, list, and delete custom playlists",
                emoji="💾",
            ),
            discord.SelectOption(
                label="🤖 Smart DJ & Maintenance",
                value="smart_dj",
                description="DJ recommendations, synced lyrics, yt-dlp autoupdate, hot reload",
                emoji="⚡",
            ),
            discord.SelectOption(
                label="⚙️ Prefix & Shortcuts",
                value="prefix_settings",
                description="Custom server prefix, text commands (,play, ,c, etc.), and shortcuts",
                emoji="⚙️",
            ),
        ]
        super().__init__(placeholder="Select a category to view detailed commands...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        self.panel_view.current_page = selected
        for opt in self.options:
            opt.default = (opt.value == selected)
        embed = self.panel_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.panel_view)


class MusicControlPanelView(discord.ui.View):
    """Interactive master control panel and feature guide for MusicMaid (/c)."""

    def __init__(self, bot: RaiMusicBot, guild: discord.Guild, session: GuildMusicSession):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild
        self.session = session
        self.current_page = "overview"

        # Row 0: Category Select
        self.add_item(MusicControlSelect(self))

        # Dynamic Button Labels
        btn_247_label = "24/7: ON" if session.twenty_four_seven else "Toggle 24/7"
        btn_247_style = discord.ButtonStyle.success if session.twenty_four_seven else discord.ButtonStyle.primary

        # Row 1: Direct Actions
        self.toggle_247_btn.label = btn_247_label
        self.toggle_247_btn.style = btn_247_style

        # Row 2: Invite Bot link button
        bot_user_id = bot.user.id if bot.user else 1556676516274905218
        invite_url = f"https://discord.com/oauth2/authorize?client_id={bot_user_id}&permissions=36768832&integration_type=0&scope=bot+applications.commands"
        self.add_item(discord.ui.Button(label="Invite MusicMaid", style=discord.ButtonStyle.link, url=invite_url, emoji="📩", row=2))

    def build_embed(self) -> discord.Embed:
        bot_name = self.bot.user.name if self.bot.user else "MusicMaid"
        is_247 = self.session.twenty_four_seven
        vc_connected = self.session.voice_client and self.session.voice_client.is_connected()
        vc_name = self.session.voice_client.channel.name if vc_connected else "Not Connected"
        status_dot = "🟢" if vc_connected else "⚪"
        active_filter = self.session.audio_filter or "None (Flat EQ)"
        radio_mode = (getattr(self.session, "radio_station", None) or "Off").capitalize()

        if self.current_page == "overview":
            embed = discord.Embed(
                title=f"🐾 {bot_name} • Master Control Panel",
                description=(
                    f"**Welcome to {bot_name}!** High-performance, 24/7 independent audio companion.\n"
                    f"Select any category from the menu below or use the quick-action buttons.\n\n"
                    f"**Live Engine Status:**\n"
                    f"• **Voice Channel:** {status_dot} `{vc_name}`\n"
                    f"• **24/7 Mode:** {'`✅ ACTIVE`' if is_247 else '`❌ INACTIVE`'} *(Use `/247` or `/stay`)*\n"
                    f"• **Continuous Radio:** `{radio_mode}` *(Use `/radio`)*\n"
                    f"• **DSP Filter:** `{active_filter[:35]}` *(Use `/filter`)*\n"
                    f"• **Volume:** `{self.session.volume}%` • **State:** `{self.session.state.name}`\n"
                    f"• **Current Track:** {('`' + self.session.current_track.title[:35] + '`') if self.session.current_track else '`Idle`'}"
                ),
                color=COLOR_ELECTRIC_CYAN,
            )
            embed.add_field(
                name="🎵 Core Playback",
                value="`/music play` • `/skip` • `/pause` • `/resume` • `/queue` • `/volume` • `/np` • `/seek` • `/stop` • `/clear` • `/loop` • `/shuffle`",
                inline=False,
            )
            embed.add_field(
                name="🎛️ Audio Filters (DSP)",
                value="`/filter preset:bassboost` • `nightcore` • `8d` • `vaporwave` • `vocal` • `reset`",
                inline=False,
            )
            embed.add_field(
                name="📻 24/7 & Bedtime",
                value="`/247` or `/stay` *(24/7 Voice)* • `/radio <mood>` *(Continuous Radio)* • `/sleeptimer <mins>` *(Fade-out sleep timer)*",
                inline=False,
            )
            embed.add_field(
                name="📂 Playlists & Favorites",
                value="`/playlist save` • `/playlist load` • `/playlist list` • `/playlist delete` • `/music favorite` • `/music favorites`",
                inline=False,
            )
            embed.add_field(
                name="🤖 Smart DJ & Auto-Updater",
                value="`/music dj` • `/music lyrics` • `/music recommend` • `/autoupdate` • `/reload` • `/c`",
                inline=False,
            )
            embed.set_footer(text=f"{bot_name} v{MUSIC_BOT_VERSION} • Tap buttons below for instant actions")

        elif self.current_page == "playback":
            embed = discord.Embed(
                title="🎵 Playback & Queue Commands",
                description="Precision streaming audio controls for crystal clear sound:",
                color=COLOR_NEON_BLUE,
            )
            embed.add_field(name="`/music play <query>`", value="Streams audio from YouTube, Spotify links, Soundcloud, or direct search.", inline=False)
            embed.add_field(name="`/skip` (or `/music skip`)", value="Skips the current song to the next queued track.", inline=True)
            embed.add_field(name="`/pause` & `/resume`", value="Pause or resume audio playback on demand.", inline=True)
            embed.add_field(name="`/queue` (or `/music queue`)", value="View paginated list of upcoming tracks with durations.", inline=True)
            embed.add_field(name="`/volume <0-100>`", value="Set real-time software audio output volume.", inline=True)
            embed.add_field(name="`/np` (or `/music np`)", value="Show currently playing track with interactive 9-button player bar.", inline=True)
            embed.add_field(name="`/seek <seconds>`", value="Jump to a specific timestamp in the current song.", inline=True)
            embed.add_field(name="`/loop <mode>`", value="Loop modes: `off`, `track` (repeat current), or `queue` (repeat all).", inline=True)
            embed.add_field(name="`/shuffle`", value="Shuffles all songs currently queued.", inline=True)
            embed.add_field(name="`/clear`", value="Empties all upcoming songs from queue.", inline=True)
            embed.add_field(name="`/stop`", value="Stops playback, clears queue, and leaves voice channel.", inline=True)

        elif self.current_page == "filters":
            embed = discord.Embed(
                title="🎛️ Real-Time DSP Audio Filters (`/filter`)",
                description="Live sample-rate linear audio processing applied directly via FFmpeg without stutter:",
                color=COLOR_ELECTRIC_CYAN,
            )
            embed.add_field(name="🔊 `/filter preset:bassboost`", value="Deep sub-bass equalizer boost (+10dB at 60Hz) for heavy punch.", inline=False)
            embed.add_field(name="⚡ `/filter preset:nightcore`", value="1.25x tempo acceleration with high-pitched anime vocals.", inline=False)
            embed.add_field(name="🎧 `/filter preset:8d`", value="Dynamic 360° rotating stereo audio moving around your ears (use headphones!).", inline=False)
            embed.add_field(name="🌊 `/filter preset:vaporwave`", value="Relaxed, slowed-down 0.85x playback with vintage deep pitch.", inline=False)
            embed.add_field(name="🎤 `/filter preset:vocal`", value="Crystal-clear vocal clarity with mid-frequency boost & bass cutoff.", inline=False)
            embed.add_field(name="🔄 `/filter preset:reset`", value="Clears all active filters and returns to studio-flat EQ.", inline=False)

        elif self.current_page == "247_radio":
            embed = discord.Embed(
                title="📻 24/7 Mode & Continuous Radio",
                description="Keep your server alive around the clock without sudden silence:",
                color=COLOR_ELECTRIC_CYAN,
            )
            embed.add_field(
                name="🛡️ `/247` or `/stay` (24/7 Persistence)",
                value=(
                    "Locks the bot into your voice channel 24/7.\n"
                    "• **Disables auto-disconnect** when listeners leave\n"
                    "• **Auto-reconnects** across bot updates and server restarts\n"
                    "• Saved per-guild in persistent database"
                ),
                inline=False,
            )
            embed.add_field(
                name="📻 `/radio preset:<mood>` (Continuous Vibe Radio)",
                value=(
                    "When your song queue ends, the bot streams uninterrupted curated vibe music!\n"
                    "• Presets: `chill` ☕, `gaming` 🎮, `night` 🌙, `anime` 🌸, `party` 🎉, `sleep` 💤, `hits` 🔥\n"
                    "• Turn off anytime with `/radio preset:off`"
                ),
                inline=False,
            )

        elif self.current_page == "sleeptimer":
            embed = discord.Embed(
                title="🌙 Bedtime Sleep Timer (`/sleeptimer`)",
                description="Wind down and fall asleep to music without the bot playing all night:",
                color=COLOR_NEON_BLUE,
            )
            embed.add_field(
                name="💤 `/sleeptimer minutes:<mins>`",
                value=(
                    "Choose from: `15`, `30`, `45`, `60`, `90`, `120` minutes or `Cancel`.\n"
                    "• **Smooth 30-Second Volume Decay**: When time expires, volume gently steps down `100% ➔ 75% ➔ 50% ➔ 25% ➔ 5%` before peacefully disconnecting.\n"
                    "• Zero abrupt audio cuts."
                ),
                inline=False,
            )

        elif self.current_page == "playlists":
            embed = discord.Embed(
                title="📂 Custom Server Playlists & Favorites",
                description="Save queues to persistent storage and reload them instantly:",
                color=COLOR_NEON_BLUE,
            )
            embed.add_field(name="💾 `/playlist save name:<name>`", value="Saves all currently queued songs under a custom playlist name.", inline=False)
            embed.add_field(name="▶️ `/playlist load name:<name>`", value="Loads and appends all tracks from your saved playlist into queue.", inline=False)
            embed.add_field(name="📜 `/playlist list`", value="Lists all saved playlists created in this server.", inline=False)
            embed.add_field(name="🗑️ `/playlist delete name:<name>`", value="Deletes a saved playlist from the database.", inline=False)
            embed.add_field(name="⭐ `/music favorite` & `/music favorites`", value="Bookmark personal favorites and replay them with one click.", inline=False)

        elif self.current_page == "smart_dj":
            embed = discord.Embed(
                title="🤖 Smart AI DJ, Lyrics & Maintenance",
                description="Autonomous intelligence and zero-downtime maintenance:",
                color=COLOR_ELECTRIC_CYAN,
            )
            embed.add_field(name="🎧 `/music dj`", value="Interactive DJ Card providing automated recommendations based on queue history.", inline=False)
            embed.add_field(name="📜 `/music lyrics`", value="Real-time synchronized lyrics with instant in-memory LRU caching.", inline=False)
            embed.add_field(name="🔄 `/autoupdate`", value="Checks and upgrades yt-dlp automatically in background to avoid YouTube blocks.", inline=False)
            embed.add_field(name="⚡ `/reload`", value="Zero-downtime hot reload of audio modules without disconnecting voice clients.", inline=False)
            embed.add_field(name="📊 `/c` or `/control`", value="Opens this interactive Master Control Panel anytime.", inline=False)

        elif self.current_page == "prefix_settings":
            embed = discord.Embed(
                title="⚙️ Server Prefix & Text Shortcuts",
                description="Use traditional text commands without needing the slash `/` menu:",
                color=COLOR_ELECTRIC_CYAN,
            )
            embed.add_field(
                name="🔧 Custom Prefix Configuration",
                value=(
                    "• **Current Prefix:** `,` *(or custom configured symbol)*\n"
                    "• **Change Prefix:** `,prefix <symbol>` *(e.g. `,prefix !` or `,prefix .`)*\n"
                    "• **Slash Command:** `/prefix symbol:<symbol>`\n"
                    "• *(Requires Manage Server or Administrator)*"
                ),
                inline=False,
            )
            embed.add_field(
                name="🎵 Text Playback Shortcuts",
                value=(
                    "• `,play <song>` or `,p <song>` — Play track or URL\n"
                    "• `,skip` or `,s` — Skip track\n"
                    "• `,pause` & `,resume` — Pause/resume\n"
                    "• `,stop` — Stop playback & clear queue\n"
                    "• `,queue` or `,q` — Show queue\n"
                    "• `,np` — Now playing track info\n"
                    "• `,volume <0-150>` or `,v` — Set volume"
                ),
                inline=False,
            )
            embed.add_field(
                name="🎛️ Advanced Shortcuts",
                value=(
                    "• `,c` or `,panel` — Open Master Control Panel\n"
                    "• `,247` or `,stay` — Toggle 24/7 Voice persistence\n"
                    "• `,loop` — Toggle loop (track/queue/off)\n"
                    "• `,shuffle` — Shuffle queue\n"
                    "• `,clear` — Clear queue\n"
                    "• `,filter <preset>` — Set EQ (bassboost, nightcore, 8d)\n"
                    "• `,help` — List all text commands"
                ),
                inline=False,
            )

        return embed

    @discord.ui.button(label="Toggle 24/7", style=discord.ButtonStyle.primary, row=1, emoji="📻")
    async def toggle_247_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Must be used in a server.", ephemeral=True)
            return

        settings = await self.bot.db.get_guild_settings(self.guild.id)
        new_state = not settings.twenty_four_seven_enabled

        if new_state:
            target_vc = None
            if self.session.voice_client and self.session.voice_client.is_connected():
                target_vc = self.session.voice_client.channel
            elif interaction.user.voice and interaction.user.voice.channel:
                target_vc = interaction.user.voice.channel
                async with self.session.lock:
                    vc = await VoiceManager.join_voice_channel(interaction.user, interaction.channel, self.session)  # type: ignore
                    if not vc:
                        err = self.session.last_error or "Could not connect to your voice channel."
                        await interaction.response.send_message(
                            f"❌ **{err}**\n\n"
                            f"💡 **How to fix:** Please grant **MusicMaid** the **Connect** and **Speak** permissions in this channel.",
                            ephemeral=True,
                        )
                        return
            else:
                await interaction.response.send_message(
                    "⚠️ **Please join a voice channel first** so MusicMaid knows which channel to stay in 24/7!",
                    ephemeral=True,
                )
                return

            settings.twenty_four_seven_enabled = True
            self.session.twenty_four_seven = True
            if target_vc:
                settings.twenty_four_seven_channel_id = target_vc.id

            if self.session.auto_leave_task and not self.session.auto_leave_task.done():
                self.session.auto_leave_task.cancel()
                self.session.auto_leave_task = None

            await self.bot.db.update_guild_settings(settings)
            button.style = discord.ButtonStyle.success
            button.label = "24/7: ON"
        else:
            settings.twenty_four_seven_enabled = False
            self.session.twenty_four_seven = False
            settings.twenty_four_seven_channel_id = None
            await self.bot.db.update_guild_settings(settings)

            if self.session.voice_client and self.session.voice_client.is_connected():
                humans = [m for m in self.session.voice_client.channel.members if not m.bot]
                if not humans:
                    VoiceManager.schedule_auto_leave(self.bot, self.session)

            button.style = discord.ButtonStyle.primary
            button.label = "Toggle 24/7"

        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Now Playing", style=discord.ButtonStyle.secondary, row=1, emoji="🎵")
    async def np_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.session.current_track:
            await interaction.response.send_message("🐱 Nothing is currently playing!", ephemeral=True)
            return
        track = self.session.current_track
        embed = discord.Embed(
            title="🎶 Currently Playing",
            description=f"**[{track.title}]({track.url})**\nby **{track.artist}**",
            color=COLOR_ELECTRIC_CYAN,
        )
        embed.add_field(name="Duration", value=f"`{format_duration(track.duration)}`", inline=True)
        embed.add_field(name="Requested By", value=f"<@{track.requester_id}>", inline=True)
        embed.add_field(name="Volume", value=f"`{self.session.volume}%`", inline=True)
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="View Queue", style=discord.ButtonStyle.secondary, row=1, emoji="📜")
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.session.queue:
            await interaction.response.send_message("🐱 The queue is currently empty!", ephemeral=True)
            return
        lines = []
        for i, t in enumerate(self.session.queue[:10], start=1):
            lines.append(f"`{i}.` **{t.title[:45]}** (`{format_duration(t.duration)}`)")
        total_sec = sum(t.duration for t in self.session.queue)
        embed = discord.Embed(
            title=f"📜 Upcoming Queue ({len(self.session.queue)} tracks)",
            description="\n".join(lines),
            color=COLOR_NEON_BLUE,
        )
        embed.set_footer(text=f"Total Queue Time: {format_duration(total_sec)}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, row=1, emoji="🔄")
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)


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

    @staticmethod
    async def ensure_deferred(interaction: discord.Interaction, ephemeral: bool = False) -> bool:
        """Guarantee interaction is deferred within Discord's 3-second deadline."""
        if not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=ephemeral)
                return True
            except (discord.errors.NotFound, discord.errors.InteractionResponded):
                return True
            except Exception as e:
                logger.debug(f"Interaction deferral notice: {e}")
                return False
        return True

    async def _check_permissions(self, interaction: discord.Interaction) -> bool:
        """Verify user is in voice channel and allowed to use music commands."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            msg = "❌ This command must be used in a server."
            if interaction.response.is_done():
                try:
                    await interaction.edit_original_response(content=msg, embed=None, view=None)
                except Exception:
                    await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return False

        if not interaction.user.voice or not interaction.user.voice.channel:
            msg = "❌ You must join a voice channel first."
            if interaction.response.is_done():
                try:
                    await interaction.edit_original_response(content=msg, embed=None, view=None)
                except Exception:
                    await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return False

        return True

    async def _play_query(
        self, interaction: discord.Interaction, query: str, ephemeral: bool = False
    ) -> None:
        """Internal worker executing search, resolve, queueing, and playback transition."""
        start_t = time.time()
        guild = interaction.guild
        member = interaction.user
        text_channel = interaction.channel

        if not guild or not isinstance(member, discord.Member) or not isinstance(text_channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread)):
            try:
                await interaction.edit_original_response(content="❌ Cannot determine server or channel context.")
            except Exception:
                await interaction.followup.send("❌ Cannot determine server or channel context.", ephemeral=True)
            return

        session = await self.session_manager.get_session(guild.id)

        # 1. Connect to voice with timeout protection
        async with session.lock:
            try:
                vc = await asyncio.wait_for(VoiceManager.join_voice_channel(member, text_channel, session), timeout=10.0)
            except asyncio.TimeoutError:
                vc = None
                session.last_error = "Voice connection handshake timed out."
            except Exception as vc_err:
                vc = None
                session.last_error = str(vc_err)

            if not vc:
                err_detail = getattr(session, "last_error", None) or "Bot lacks Connect or Speak permissions in this channel."
                ch_name = member.voice.channel.name if member.voice and member.voice.channel else "your voice channel"
                embed_conn_err = discord.Embed(
                    title="❌ COULD NOT CONNECT TO VOICE",
                    description=(
                        f"Could not connect to **{ch_name}**.\n"
                        f"• **Reason:** {err_detail}\n\n"
                        f"💡 *How to fix:* Right-click/tap the voice channel ➔ **Edit Channel** ➔ **Permissions** ➔ grant **MusicMaid** the **Connect** & **Speak** permissions!"
                    ),
                    color=0xED4245,
                )
                try:
                    await interaction.edit_original_response(embed=embed_conn_err)
                except Exception:
                    await interaction.followup.send(embed=embed_conn_err, ephemeral=True)
                return

        # 2. Resolve query: Edit original response directly so NO duplicate dangling loading message in chat!
        embed_loading = discord.Embed(
            title="🔍 SEARCHING TRACK",
            description=f"Resolving: `{query[:100]}`...\n*{DIALOGUE_START}*",
            color=COLOR_NEON_BLUE,
        )
        try:
            await interaction.edit_original_response(embed=embed_loading)
        except Exception:
            pass

        search_start = time.time()
        try:
            track = await asyncio.wait_for(AudioResolver.resolve_track(query, member.id, str(member)), timeout=18.0)
        except asyncio.TimeoutError:
            track = None
            logger.warning(f"[Playback] Audio resolution timed out for query '{query}'")
        except Exception as e:
            track = None
            logger.error(f"[Playback] Track resolution exception for '{query}': {e}", exc_info=True)

        if not track:
            embed_fail = discord.Embed(
                title="😿 NO AUDIO TRACK FOUND",
                description=f"{DIALOGUE_NOTHING_PLAYABLE}\nQuery: `{query[:100]}`",
                color=0xED4245,
            )
            try:
                await interaction.edit_original_response(embed=embed_fail)
            except Exception:
                await interaction.followup.send(embed=embed_fail, ephemeral=True)
            return

        search_dur = time.time() - search_start
        logger.info(f"[Playback] Track '{track.title}' resolved in {search_dur:.2f}s")

        # Feature 113: Audio Track Duration Ceiling Limiter (> 3 hours rejected for non-admins)
        if track.duration > 10800 and not getattr(member.guild_permissions, "administrator", False):
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="⚠️ TRACK DURATION EXCEEDED",
                    description=f"Tracks longer than **3 hours** (`{format_duration(track.duration)}`) cannot be queued to protect audio stability. 🐾",
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
                play_start = time.time()
                success = await MusicPlayerService.start_playback(self.bot, session, track)
                play_dur = time.time() - play_start
                logger.info(f"[Playback] Stream initialization took {play_dur:.2f}s (success={success})")
                if success:
                    try:
                        await interaction.edit_original_response(
                            content=f"🎶 Started playing **{track.title}**!",
                            embed=None,
                            view=None,
                        )
                    except Exception:
                        pass
                else:
                    await interaction.edit_original_response(
                        embed=discord.Embed(
                            title="❌ PLAYBACK FAILED",
                            description="Encountered an internal error while starting audio stream.",
                            color=0xED4245,
                        ),
                        view=None,
                    )

    # =========================================================================
    # /MUSIC COMMAND GROUP
    # =========================================================================

    music_group = app_commands.Group(name="music", description="Neko Songs Independent Music Suite")

    # --- 1. PLAYBACK & BASIC CONTROLS ---

    @music_group.command(name="play", description="Play a song or URL from YouTube")
    @app_commands.describe(query="Song title, artist, or URL to play")
    async def music_play(self, interaction: discord.Interaction, query: str) -> None:
        if not interaction.response.is_done():
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

    @music_group.command(name="skip", description="Skip the currently playing song (or vote-to-skip)")
    async def music_skip(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.voice_client or not session.voice_client.is_playing():
            await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            return

        track_title = session.current_track.title if session.current_track else "Song"

        # Determine if caller has DJ, admin, or requester bypass authority
        is_dj = False
        if interaction.guild:
            dj_settings = await self.bot.db.get_dj_settings(interaction.guild.id)
            if not dj_settings.enabled or (dj_settings.role_id and any(r.id == dj_settings.role_id for r in getattr(interaction.user, "roles", []))) or getattr(interaction.user.guild_permissions, "administrator", False):
                is_dj = True
            elif session.current_track and session.current_track.requester_id == interaction.user.id:
                is_dj = True

        vc_channel = session.voice_client.channel
        # Feature 136: Dynamic active listener consensus (filter out bots and self-deafened members)
        non_bot_listeners = [
            m for m in getattr(vc_channel, "members", [])
            if not m.bot and not getattr(getattr(m, "voice", None), "self_deaf", False)
        ] if vc_channel else []

        if is_dj or len(non_bot_listeners) <= 1:
            session.skip_votes.clear()
            session.voice_client.stop()
            await interaction.followup.send(f"⏭️ Skipped **{track_title}**.")
            return

        # Scaled vote consensus: 40% for larger groups >= 5, 50% for smaller groups
        threshold_ratio = 0.4 if len(non_bot_listeners) >= 5 else 0.5
        required_votes = max(2, math.ceil(len(non_bot_listeners) * threshold_ratio))
        session.skip_votes.add(interaction.user.id)
        current_votes = len(session.skip_votes)

        if current_votes >= required_votes:
            session.skip_votes.clear()
            session.voice_client.stop()
            await interaction.followup.send(f"⏭️ **Vote-to-Skip Passed!** ({current_votes}/{required_votes} votes) Skipped **{track_title}**.")
        else:
            await interaction.followup.send(f"🗳️ **Vote to Skip:** {current_votes}/{required_votes} listeners voted to skip **{track_title}**.")

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

        # Feature 131: Queue Timeline ETA relative timestamp calculation
        lines = []
        now_ts = int(discord.utils.utcnow().timestamp())
        current_remaining = max(0, (session.current_track.duration - session.elapsed_seconds)) if session.current_track else 0
        cumulative_sec = current_remaining

        for i, t in enumerate(tracks):
            if start_idx <= i < start_idx + per_page:
                eta_ts = now_ts + cumulative_sec
                lines.append(f"`{i+1}.` [{t.title}]({t.url}) (`{format_duration(t.duration)}`) • <t:{eta_ts}:R>")
            cumulative_sec += t.duration

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

    @app_commands.command(name="seek", description="Seek to a specific timestamp in the current song")
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

        # Execute seamless FFmpeg seek
        await MusicPlayerService.seek(self.bot, session, seconds)
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

    @app_commands.command(name="remove", description="Remove a track from the queue by its number")
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

    @app_commands.command(name="move", description="Move a song in queue from one position to another")
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

    @app_commands.command(name="eq", description="Select an Audio Equalizer preset")
    async def music_eq(self, interaction: discord.Interaction) -> None:
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        view = AudioEqualizerView(session, self.bot)
        await interaction.response.send_message(
            f"🎛️ **Audio Equalizer Presets** (Current: `{getattr(session, 'eq_preset', 'Flat')}`):",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="radio", description="Toggle continuous 24/7 Vibe Radio auto-fill mode")
    @app_commands.describe(vibe="Musical mood / vibe for radio auto-fill")
    @app_commands.choices(vibe=[
        app_commands.Choice(name="Lo-Fi Chill & Relax ☕", value="chill"),
        app_commands.Choice(name="Gaming Focus 🎮", value="gaming"),
        app_commands.Choice(name="Synthwave & Night Drive 🌌", value="night"),
        app_commands.Choice(name="Anime & Japanese Pop 🌸", value="anime"),
        app_commands.Choice(name="Party Vibes ⚡", value="party"),
        app_commands.Choice(name="Deep Sleep & Meditation 💤", value="sleep"),
        app_commands.Choice(name="Global Top Hits 📈", value="hits"),
        app_commands.Choice(name="Off (Disable Radio) ⏹️", value="off"),
    ])
    async def music_radio(self, interaction: discord.Interaction, vibe: app_commands.Choice[str]) -> None:
        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        member = interaction.user
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore

        if vibe.value == "off":
            session.autoplay = False
            session.radio_station = None
            await interaction.followup.send("📻 24/7 Vibe Radio auto-fill **DISABLED**.")
            return

        session.autoplay = True
        session.twenty_four_seven = True
        session.radio_station = vibe.value
        setattr(session, "radio_vibe", vibe.value)

        # Connect if not connected
        if not session.is_active and isinstance(member, discord.Member) and member.voice and member.voice.channel:
            async with session.lock:
                await VoiceManager.join_voice_channel(member, interaction.channel, session)  # type: ignore

        if guild:
            settings = await self.bot.db.get_guild_settings(guild.id)
            settings.twenty_four_seven_enabled = True
            if session.voice_client:
                settings.twenty_four_seven_channel_id = session.voice_client.channel.id
            await self.bot.db.update_guild_settings(settings)

        embed = discord.Embed(
            title="📻 24/7 VIBE RADIO ACTIVATED",
            description=(
                f"Now streaming **{vibe.name}**!\n\n"
                f"• Continuous non-stop background playback is **ENABLED**\n"
                f"• 24/7 Voice persistence is **ACTIVATED**\n"
                f"• When the queue ends, Neko automatically plays matching tracks without stopping."
            ),
            color=COLOR_ELECTRIC_CYAN,
        )
        await interaction.followup.send(embed=embed)

        if not session.is_playing:
            radio_map = {
                "chill": "chill morning lofi coffee beats study relax",
                "gaming": "gaming edm bass boost high energy workout",
                "night": "synthwave retrowave cyberpunk gaming night drive",
                "anime": "anime japanese pop cute aesthetic lofi",
                "party": "party edm dance festival hits remix",
                "sleep": "deep sleep ambient meditation lofi space calm",
                "hits": "top hits popular pop music billboard",
            }
            query = radio_map.get(vibe.value, "chill lofi beats")
            track = await AudioResolver.resolve_track(query, 0, f"Neko {vibe.name}")
            if track:
                await MusicPlayerService.start_playback(self.bot, session, track)

    @app_commands.command(name="ducking", description="Toggle Smart Voice Audio Ducking")
    @app_commands.describe(state="Enable or disable auto-ducking volume during voice activity")
    @app_commands.choices(state=[
        app_commands.Choice(name="Enabled (Auto-lower 35% on speaking)", value="on"),
        app_commands.Choice(name="Disabled (Consistent volume)", value="off"),
    ])
    async def music_ducking(self, interaction: discord.Interaction, state: app_commands.Choice[str]) -> None:
        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        session.ducking_enabled = state.value == "on"
        await interaction.followup.send(f"🔊 Smart Audio Ducking is now **{'ENABLED' if session.ducking_enabled else 'DISABLED'}**.")

    @app_commands.command(name="watch", description="Launch Discord Watch Together / YouTube activity in voice")
    async def music_watch(self, interaction: discord.Interaction) -> None:
        if not interaction.user or not getattr(interaction.user, "voice", None) or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ You must be connected to a voice channel to start Watch Together.", ephemeral=True)
            return

        vc = interaction.user.voice.channel
        try:
            invite = await vc.create_invite(
                max_age=3600,
                max_uses=0,
                reason="Neko Songs: YouTube Watch Together Activity",
                target_type=discord.InviteTarget.embedded_application,
                target_application_id=880218394199220274,  # YouTube Watch Together App ID
            )
            embed = discord.Embed(
                title="📺 WATCH TOGETHER • YOUTUBE ACTIVITY",
                description=f"Click the link below to launch synchronized YouTube Watch Together inside **#{vc.name}**:\n\n👉 **[Click Here to Launch Watch Together]({invite.url})**",
                color=0xFF0000,
            )
            embed.set_footer(text="Neko Songs • Native Discord Voice Activity")
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Could not create Watch Together activity invite: {e}", ephemeral=True)

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

    @app_commands.command(name="disconnect", description="Disconnect Neko Songs from voice")
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

    @dj_group.command(name="enable", description="Enable Neko DJ mode to continuously play non-stop matching music")
    async def dj_enable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        settings = await self.bot.db.get_dj_settings(interaction.guild_id)  # type: ignore
        settings.enabled = True
        settings.auto_queue = True
        await self.bot.db.update_dj_settings(settings)

        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        session.dj_enabled = True

        # If nothing is currently playing and user is in a voice channel, immediately start non-stop playback!
        member = interaction.user
        started_now = False
        if isinstance(member, discord.Member) and member.voice and member.voice.channel and not session.is_playing:
            from music_bot.services.voice_service import VoiceManager
            text_channel = interaction.channel if isinstance(interaction.channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread)) else None
            vc = await VoiceManager.join_voice_channel(member, text_channel, session)
            if vc:
                from music_bot.services.dj_service import NekoDJService
                rec = await NekoDJService.get_recommendation(self.bot, session)
                if rec:
                    track, rationale = rec
                    started = await MusicPlayerService.start_playback(self.bot, session, track)
                    if started:
                        started_now = True
                        from music_bot.services.player_service import NowPlayingControlView
                        embed = MusicPlayerService.build_now_playing_embed(session)
                        view = NowPlayingControlView(session)
                        if text_channel:
                            msg = await text_channel.send(
                                f"🎧 **Neko DJ Non-Stop Mode ACTIVE!** Connected to **#{member.voice.channel.name}** and spinning continuous non-stop music for you!\n*{rationale}*",
                                embed=embed,
                                view=view,
                            )
                            session.now_playing_message = msg

        if started_now:
            await interaction.followup.send(
                "🎧 **Neko DJ Non-Stop Mode ACTIVE!**\n"
                "• Connected to your voice channel and spinning non-stop music.\n"
                "• Continuous infinite playback is now active with zero silence! 🐾",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "🎧 **Neko DJ Non-Stop Mode ACTIVE!**\n"
                "• When songs end, Neko will pick and play matching tracks non-stop without silence!\n"
                "• Continuous infinite playback is now active. 🐾",
                ephemeral=True,
            )

    @dj_group.command(name="disable", description="Disable Neko DJ mode")
    async def dj_disable(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        settings = await self.bot.db.get_dj_settings(interaction.guild_id)  # type: ignore
        settings.enabled = False
        await self.bot.db.update_dj_settings(settings)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        session.dj_enabled = False
        await interaction.followup.send("⏹️ **Neko DJ Non-Stop Mode DISABLED.** Playback will conclude when the queue finishes.", ephemeral=True)

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
            err = session.last_error or "Could not connect to your voice channel."
            await interaction.followup.send(f"❌ **{err}**", ephemeral=True)
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

    @app_commands.command(name="history", description="View recent song playback history")
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

    @app_commands.command(name="stats", description="View truthful server music listening statistics")
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

    @app_commands.command(name="permissions", description="View voice and command permissions")
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
    # 24/7 & AUTONOMOUS MAINTENANCE ROOT COMMANDS
    # =========================================================================

    @app_commands.command(name="247", description="Toggle 24/7 mode to keep the bot in voice channel indefinitely")
    async def cmd_247(self, interaction: discord.Interaction) -> None:
        """Toggles 24/7 persistence mode for the guild."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        member = interaction.user
        settings = await self.bot.db.get_guild_settings(guild.id)
        session = await self.session_manager.get_session(guild.id)

        # Toggle 24/7 state
        new_state = not settings.twenty_four_seven_enabled
        settings.twenty_four_seven_enabled = new_state
        session.twenty_four_seven = new_state

        if new_state:
            target_vc = None
            if session.voice_client and session.voice_client.is_connected():
                target_vc = session.voice_client.channel
            elif member.voice and member.voice.channel:
                target_vc = member.voice.channel
                async with session.lock:
                    vc = await VoiceManager.join_voice_channel(member, interaction.channel, session)  # type: ignore
                    if not vc:
                        err = session.last_error or "Could not connect to your voice channel."
                        await interaction.followup.send(
                            f"❌ **{err}**\n\n"
                            f"💡 **How to fix:** Please edit the voice channel permissions for **{target_vc.name}** "
                            f"and grant **MusicMaid** the **Connect** and **Speak** permissions (or move to a public voice channel).",
                            ephemeral=True,
                        )
                        return
            else:
                settings.twenty_four_seven_enabled = False
                session.twenty_four_seven = False
                await self.bot.db.update_guild_settings(settings)
                await interaction.followup.send(
                    "⚠️ **Please join a voice channel first** so MusicMaid knows which channel to stay in 24/7!\n"
                    "*(Or play a song first with `/music play`)*",
                    ephemeral=True,
                )
                return

            if target_vc:
                settings.twenty_four_seven_channel_id = target_vc.id

            if session.auto_leave_task and not session.auto_leave_task.done():
                session.auto_leave_task.cancel()
                session.auto_leave_task = None

            await self.bot.db.update_guild_settings(settings)

            embed = discord.Embed(
                title="📻 24/7 MODE ACTIVATED",
                description=(
                    f"**{self.bot.user.name if self.bot.user else 'MusicMaid'}** will now stay in "
                    f"**{target_vc.name if target_vc else 'the voice channel'}** 24/7!\n\n"
                    "• Auto-disconnection is **disabled**\n"
                    "• The bot will remain in voice even when all listeners leave\n"
                    "• Automatically reconnects across bot updates & restarts\n\n"
                    "💡 *Tip: Open the full feature panel anytime with `/c`*"
                ),
                color=COLOR_ELECTRIC_CYAN,
            )
            embed.set_footer(text="Use /247 or /stay again to toggle off")
            await interaction.followup.send(embed=embed)
        else:
            settings.twenty_four_seven_channel_id = None
            await self.bot.db.update_guild_settings(settings)

            if session.voice_client and session.voice_client.is_connected():
                humans = [m for m in session.voice_client.channel.members if not m.bot]
                if not humans:
                    VoiceManager.schedule_auto_leave(self.bot, session)

            embed = discord.Embed(
                title="📻 24/7 MODE DEACTIVATED",
                description="24/7 mode has been **disabled**. Normal auto-leave timeout rules now apply.",
                color=COLOR_NEON_BLUE,
            )
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="stay", description="Keep the bot in voice channel 24/7 (Shortcut for /247)")
    async def cmd_stay(self, interaction: discord.Interaction) -> None:
        """Alias for /247."""
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.cmd_247.callback(self, interaction)

    @app_commands.command(name="c", description="Interactive Master Control Panel showing all music bot features")
    async def cmd_c(self, interaction: discord.Interaction) -> None:
        """Interactive control panel & command center displaying all music features."""
        await self.ensure_deferred(interaction, ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("❌ This command must be used in a server.", ephemeral=True)
            return

        session = await self.session_manager.get_session(interaction.guild.id)
        view = MusicControlPanelView(self.bot, interaction.guild, session)
        embed = view.build_embed()
        try:
            await interaction.edit_original_response(embed=embed, view=view)
        except Exception:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="control", description="Interactive Master Control Panel (Shortcut for /c)")
    async def cmd_control(self, interaction: discord.Interaction) -> None:
        """Alias for /c."""
        await self.cmd_c.callback(self, interaction)

    @app_commands.command(name="autoupdate", description="Check or update yt-dlp extractor, git commits, and audio health")
    @app_commands.describe(action="Maintenance action to perform")
    @app_commands.choices(action=[
        app_commands.Choice(name="Check Status & Health", value="check"),
        app_commands.Choice(name="Update yt-dlp Now", value="update"),
        app_commands.Choice(name="Git Pull Code & Hot Reload", value="git_pull"),
        app_commands.Choice(name="Hot-Reload Changed Files & Resume", value="reload"),
        app_commands.Choice(name="Full Autonomous Self-Heal", value="self_heal"),
    ])
    async def cmd_autoupdate(self, interaction: discord.Interaction, action: Optional[app_commands.Choice[str]] = None) -> None:
        """Manages autonomous yt-dlp dependency, git sync, and extractor updates."""
        await interaction.response.defer(ephemeral=False)
        from music_bot.services.updater_service import MusicAutoUpdater

        act = action.value if action else "check"
        is_admin = getattr(interaction.user.guild_permissions, "administrator", False) if interaction.guild else False
        is_owner = str(interaction.user.id) in ("1457380609641938981",)

        if act == "update":
            if not is_admin and not is_owner:
                await interaction.followup.send("❌ Administrator permissions required to trigger dependency updates.", ephemeral=True)
                return

            embed_progress = discord.Embed(
                title="🔄 UPDATING AUDIO EXTRACTOR",
                description="Upgrading `yt-dlp` to latest release in background...\nPlayback will continue uninterrupted.",
                color=COLOR_NEON_BLUE,
            )
            await interaction.followup.send(embed=embed_progress)
            success, msg = await MusicAutoUpdater.update_ytdl(force=True, bot=self.bot)
            embed_result = discord.Embed(
                title="✅ AUDIO EXTRACTOR UPDATED" if success else "❌ UPDATE FAILED",
                description=msg,
                color=COLOR_ELECTRIC_CYAN if success else 0xED4245,
            )
            await interaction.edit_original_response(embed=embed_result)

        elif act == "git_pull":
            if not is_admin and not is_owner:
                await interaction.followup.send("❌ Administrator permissions required to trigger Git updates.", ephemeral=True)
                return

            embed_progress = discord.Embed(
                title="⚡ PULLING GIT COMMITS",
                description="Checking remote repository and applying hot-reload...\nVoice connections and songs will resume where left off.",
                color=COLOR_NEON_BLUE,
            )
            await interaction.followup.send(embed=embed_progress)
            success, msg = await MusicAutoUpdater.pull_git_updates(bot=self.bot)
            embed_result = discord.Embed(
                title="✅ GIT SYNC COMPLETE" if success else "❌ GIT SYNC FAILED",
                description=msg,
                color=COLOR_ELECTRIC_CYAN if success else 0xED4245,
            )
            await interaction.edit_original_response(embed=embed_result)

        elif act == "reload":
            if not is_admin and not is_owner:
                await interaction.followup.send("❌ Administrator permissions required to hot-reload code.", ephemeral=True)
                return

            embed_progress = discord.Embed(
                title="⚙️ HOT-RELOADING CODE CHANGES",
                description="Applying modified code without stopping the bot...\nPlayback will resume right where it left off!",
                color=COLOR_NEON_BLUE,
            )
            await interaction.followup.send(embed=embed_progress)
            success, msg = await MusicAutoUpdater.hot_reload_services(bot=self.bot)
            embed_result = discord.Embed(
                title="✅ HOT-RELOAD COMPLETE" if success else "❌ HOT-RELOAD FAILED",
                description=msg,
                color=COLOR_ELECTRIC_CYAN if success else 0xED4245,
            )
            await interaction.edit_original_response(embed=embed_result)

        elif act == "self_heal":
            health = await MusicAutoUpdater.check_extractor_health(bot=self.bot)
            is_ok = health.get("operational", False)
            embed_result = discord.Embed(
                title="🩺 EXTRACTOR HEALTH & SELF-HEAL",
                description=(
                    f"• **Extractor Probe:** {'🟢 Operational' if is_ok else '🔴 Issue Detected'}\n"
                    f"• **Diagnostics:** `{health.get('message', 'OK')[:150]}`\n"
                    f"• **Auto-Recovery:** Active (Android/iOS/Web client rotation)"
                ),
                color=COLOR_ELECTRIC_CYAN if is_ok else 0xED4245,
            )
            await interaction.followup.send(embed=embed_result)

        else:
            check = await MusicAutoUpdater.check_ytdl_version()
            curr = check.get("current", "unknown")
            latest = check.get("latest", "unknown")
            has_update = check.get("update_available", False)
            git_info = await MusicAutoUpdater.check_git_updates()

            status_text = "🟢 **Up-To-Date** (Optimal)" if not has_update else f"🟡 **Update Available** (`v{latest}` available on PyPI)"
            git_text = f"🟢 Commit `{git_info.get('current_commit', 'main')}`" if not git_info.get("has_updates") else f"🟡 `{git_info.get('pending_commits')}` new commits available"

            embed = discord.Embed(
                title="🤖 MUSIC BOT AUTO-UPDATER & SYNC STATUS",
                description=(
                    f"• **Current yt-dlp:** `v{curr}`\n"
                    f"• **Latest PyPI:** `v{latest}`\n"
                    f"• **Extractor Health:** {status_text}\n"
                    f"• **Git Repository:** {git_text}\n\n"
                    f"• **Autonomous Schedule:** Runs every **6 hours** in the background\n"
                    f"• **Self-Healing:** Client rotation (`android`, `ios`, `web`) & automatic stream recovery\n"
                    f"• **Zero-Interrupt:** In-memory hot reloads without dropping voice connections"
                ),
                color=COLOR_ELECTRIC_CYAN if not has_update else 0xFEE75C,
            )
            embed.set_footer(text="Use /autoupdate action:Git Pull Code to sync newest commits")
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="reload", description="Zero-downtime hot reload: update bot modules while music keeps playing")
    async def cmd_reload(self, interaction: discord.Interaction) -> None:
        """Hot reloads bot modules and cogs without dropping voice connections."""
        if str(interaction.user.id) not in ("1457380609641938981",):
            if not getattr(interaction.user, "guild_permissions", None) or not interaction.user.guild_permissions.administrator:  # type: ignore
                await interaction.response.send_message("❌ Administrator permissions required to hot-reload bot.", ephemeral=True)
                return

        await interaction.response.defer(ephemeral=True)
        try:
            active_count = self.session_manager.get_active_sessions_count()
            import importlib
            import music_bot.services.player_service as m_player
            import music_bot.services.resolver_service as m_resolver
            import music_bot.services.updater_service as m_updater
            import music_bot.services.lyrics_service as m_lyrics
            importlib.reload(m_player)
            importlib.reload(m_resolver)
            importlib.reload(m_updater)
            importlib.reload(m_lyrics)

            embed = discord.Embed(
                title="⚡ ZERO-DOWNTIME HOT RELOAD COMPLETE",
                description=(
                    f"Successfully hot-reloaded audio and resolver modules.\n\n"
                    f"• **Preserved Active Voice Sessions:** `{active_count}`\n"
                    f"• **Playback Status:** Uninterrupted 🟢\n"
                    f"• **Updated Binaries & Extractors:** Synchronized"
                ),
                color=COLOR_ELECTRIC_CYAN,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Hot-reload failed: `{e}`", ephemeral=True)

    # =========================================================================
    # AUDIO FILTERS & DSP ENGINE
    # =========================================================================

    @app_commands.command(name="filter", description="Apply real-time audio filters and audio effects")
    @app_commands.describe(effect="Audio effect preset to apply")
    @app_commands.choices(effect=[
        app_commands.Choice(name="🔊 Bass Boost (+10dB Sub-bass)", value="bassboost"),
        app_commands.Choice(name="⚡ Nightcore (Speed 1.25x & High Pitch)", value="nightcore"),
        app_commands.Choice(name="🎧 8D Audio (Surround Pulsator)", value="8d"),
        app_commands.Choice(name="🌴 Vaporwave (Slowed 0.85x & Deep Pitch)", value="vaporwave"),
        app_commands.Choice(name="🎤 Vocal Boost (Mid-frequency clarity)", value="vocal"),
        app_commands.Choice(name="⏹️ Reset (Clean Flat Audio)", value="reset"),
    ])
    async def cmd_filter(self, interaction: discord.Interaction, effect: app_commands.Choice[str]) -> None:
        """Applies dynamic audio effects in real-time."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.current_track or not session.is_playing:
            await interaction.followup.send("❌ Nothing is currently playing. Start a track first!", ephemeral=True)
            return

        filter_chains = {
            "bassboost": "-af equalizer=f=60:width_type=h:width=50:g=10",
            "nightcore": "-af atempo=1.25,asetrate=48000*1.25",
            "8d": "-af apulsator=hz=0.125",
            "vaporwave": "-af atempo=0.85,asetrate=48000*0.85",
            "vocal": "-af equalizer=f=1000:width_type=h:width=200:g=6",
            "reset": "",
        }

        session.audio_filter = filter_chains.get(effect.value, "")
        current_pos = session.elapsed_seconds
        await MusicPlayerService.start_playback(self.bot, session, session.current_track)
        session.paused_duration = 0.0
        session.track_start_time = time.time() - current_pos

        embed = discord.Embed(
            title="🎛️ AUDIO FILTER APPLIED",
            description=f"Applied audio effect: **{effect.name}**\n*Playback refreshed with real-time DSP filter.*",
            color=COLOR_ELECTRIC_CYAN if effect.value != "reset" else COLOR_NEON_BLUE,
        )
        await interaction.followup.send(embed=embed)

    # =========================================================================
    # BEDTIME SLEEP TIMER
    # =========================================================================

    @app_commands.command(name="sleeptimer", description="Set a countdown timer to gently fade out and stop music")
    @app_commands.describe(duration="Sleep duration in minutes (or 'cancel')")
    @app_commands.choices(duration=[
        app_commands.Choice(name="15 Minutes", value=15),
        app_commands.Choice(name="30 Minutes", value=30),
        app_commands.Choice(name="45 Minutes", value=45),
        app_commands.Choice(name="60 Minutes (1 Hour)", value=60),
        app_commands.Choice(name="90 Minutes (1.5 Hours)", value=90),
        app_commands.Choice(name="120 Minutes (2 Hours)", value=120),
        app_commands.Choice(name="Cancel Sleep Timer ⏹️", value=0),
    ])
    async def cmd_sleeptimer(self, interaction: discord.Interaction, duration: app_commands.Choice[int]) -> None:
        """Sets a bedtime sleep timer with gentle volume fade out."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return

        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if duration.value == 0:
            if session.sleep_timer_task and not session.sleep_timer_task.done():
                session.sleep_timer_task.cancel()
                session.sleep_timer_task = None
            session.sleep_timer_end = 0.0
            await interaction.response.send_message("⏰ Sleep timer has been **cancelled**.")
            return

        if session.sleep_timer_task and not session.sleep_timer_task.done():
            session.sleep_timer_task.cancel()

        total_seconds = duration.value * 60
        end_timestamp = int(time.time() + total_seconds)
        session.sleep_timer_end = end_timestamp

        async def _sleep_worker():
            try:
                fade_start = max(0, total_seconds - 30)
                await asyncio.sleep(fade_start)
                if session.voice_client and session.voice_client.is_playing() and hasattr(session.voice_client.source, "volume"):
                    orig_vol = session.voice_client.source.volume
                    for step in (0.75, 0.50, 0.25, 0.05):
                        try:
                            session.voice_client.source.volume = orig_vol * step
                        except Exception:
                            pass
                        await asyncio.sleep(7.5)
                if session.voice_client and session.voice_client.is_connected():
                    session.queue.clear()
                    session.voice_client.stop()
                    session.reset()
                if session.text_channel:
                    try:
                        await session.text_channel.send("🌙 **Sleep Timer Finished:** Music gently stopped. Goodnight! 💤")
                    except Exception:
                        pass
            except asyncio.CancelledError:
                pass

        session.sleep_timer_task = asyncio.create_task(_sleep_worker())
        embed = discord.Embed(
            title="🌙 SLEEP TIMER ACTIVATED",
            description=(
                f"Music will gently fade out and stop in **{duration.name}** (<t:{end_timestamp}:R>).\n\n"
                f"• Fall asleep peacefully to 24/7 radio or your queue\n"
                f"• Music volume smoothly decays during the final 30 seconds"
            ),
            color=COLOR_ELECTRIC_CYAN,
        )
        embed.set_footer(text="Use /sleeptimer duration:Cancel to stop early")
        await interaction.response.send_message(embed=embed)

    # =========================================================================
    # SAVED PLAYLIST MANAGEMENT
    # =========================================================================

    playlist_group = app_commands.Group(name="playlist", description="Manage personal and server music playlists")

    @playlist_group.command(name="save", description="Save the currently playing song and queue into a named playlist")
    @app_commands.describe(name="Playlist name")
    async def playlist_save(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        member = interaction.user
        if not guild:
            return
        session = await self.session_manager.get_session(guild.id)
        tracks_to_save = []
        if session.current_track:
            tracks_to_save.append(session.current_track)
        tracks_to_save.extend(session.queue)

        if not tracks_to_save:
            await interaction.followup.send("❌ Nothing is currently playing or queued to save.", ephemeral=True)
            return

        clean_name = name.strip()[:40]
        pl_id = await self.bot.db.create_playlist(guild.id, member.id, clean_name)
        if not pl_id:
            await self.bot.db.delete_playlist(guild.id, member.id, clean_name)
            pl_id = await self.bot.db.create_playlist(guild.id, member.id, clean_name)

        saved_count = 0
        for t in tracks_to_save:
            ok = await self.bot.db.add_playlist_track(pl_id, t)
            if ok:
                saved_count += 1

        embed = discord.Embed(
            title="💾 PLAYLIST SAVED",
            description=f"Saved **{saved_count}** tracks into playlist **\"{clean_name}\"**!\n\nUse `/playlist load name:{clean_name}` to load anytime.",
            color=COLOR_ELECTRIC_CYAN,
        )
        await interaction.followup.send(embed=embed)

    @playlist_group.command(name="load", description="Load a saved playlist into the queue")
    @app_commands.describe(name="Playlist name")
    async def playlist_load(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            return
        if not member.voice or not member.voice.channel:
            await interaction.followup.send("❌ Join a voice channel first to load playlists.", ephemeral=True)
            return

        pl = await self.bot.db.get_playlist(guild.id, name.strip(), user_id=member.id)
        if not pl or not pl.tracks:
            pl = await self.bot.db.get_playlist(guild.id, name.strip())
        if not pl or not pl.tracks:
            await interaction.followup.send(f"❌ Playlist **\"{name}\"** was not found or is empty.", ephemeral=True)
            return

        session = await self.session_manager.get_session(guild.id)
        async with session.lock:
            vc = await VoiceManager.join_voice_channel(member, interaction.channel, session)  # type: ignore
            if not vc:
                err = session.last_error or "Could not connect to your voice channel."
                await interaction.followup.send(f"❌ **{err}**", ephemeral=True)
                return

        loaded_count = len(pl.tracks)
        for t in pl.tracks:
            session.queue.append(t)

        embed = discord.Embed(
            title="📂 PLAYLIST LOADED",
            description=f"Added **{loaded_count}** tracks from **\"{pl.name}\"** to the queue!",
            color=COLOR_ELECTRIC_CYAN,
        )
        await interaction.followup.send(embed=embed)

        if not session.is_playing and session.queue:
            first_track = session.queue.popleft()
            await MusicPlayerService.start_playback(self.bot, session, first_track)

    @playlist_group.command(name="list", description="List all saved playlists for this server")
    async def playlist_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        if not interaction.guild:
            return
        playlists = await self.bot.db.get_playlists(interaction.guild.id)
        if not playlists:
            await interaction.followup.send("🐾 No playlists saved yet. Use `/playlist save name:...` while playing music!", ephemeral=True)
            return

        lines = [f"• **{p.name}** (`{len(p.tracks)}` tracks) • Created by <@{p.creator_id}>" for p in playlists]
        embed = discord.Embed(
            title="📜 SAVED PLAYLISTS",
            description="\n".join(lines[:20]),
            color=COLOR_NEON_BLUE,
        )
        embed.set_footer(text="Use /playlist load name:<name> to play")
        await interaction.followup.send(embed=embed)

    @playlist_group.command(name="delete", description="Delete a saved playlist")
    @app_commands.describe(name="Playlist name to delete")
    async def playlist_delete(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            return
        ok = await self.bot.db.delete_playlist(interaction.guild.id, interaction.user.id, name.strip())
        if ok:
            await interaction.followup.send(f"🗑️ Deleted playlist **\"{name}\"**.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Could not delete playlist **\"{name}\"** (not found or not created by you).", ephemeral=True)

    # =========================================================================
    # COMPATIBILITY ALIASES (SECTION 3)
    # =========================================================================

    @app_commands.command(name="play", description="Play a song or playlist (Shortcut for /music play)")
    @app_commands.describe(query="Song title, artist, or URL")
    async def alias_play(self, interaction: discord.Interaction, query: str) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_play.callback(self, interaction, query)

    @app_commands.command(name="pause", description="Pause music playback (Shortcut for /music pause)")
    async def alias_pause(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_pause.callback(self, interaction)

    @app_commands.command(name="resume", description="Resume music playback (Shortcut for /music resume)")
    async def alias_resume(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_resume.callback(self, interaction)

    @app_commands.command(name="skip", description="Skip current song (Shortcut for /music skip)")
    async def alias_skip(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_skip.callback(self, interaction)

    @app_commands.command(name="previous", description="Play previous song (Shortcut for /music previous)")
    async def alias_previous(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_previous.callback(self, interaction)

    @app_commands.command(name="stop", description="Stop music and leave (Shortcut for /music stop)")
    async def alias_stop(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_stop.callback(self, interaction)

    @app_commands.command(name="queue", description="View music queue (Shortcut for /music queue)")
    async def alias_queue(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_queue.callback(self, interaction, 1)

    @app_commands.command(name="np", description="View Now Playing dashboard (Shortcut for /music nowplaying)")
    async def alias_np(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_nowplaying.callback(self, interaction)

    @app_commands.command(name="nowplaying", description="View Now Playing dashboard")
    async def alias_nowplaying(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_nowplaying.callback(self, interaction)

    @app_commands.command(name="volume", description="Set volume 0-100% (Shortcut for /music volume)")
    @app_commands.describe(percent="Volume percentage (0-100)")
    async def alias_volume(self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 100]) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_volume.callback(self, interaction, percent)

    @app_commands.command(name="lyrics", description="Fetch lyrics for track (Shortcut for /music lyrics)")
    @app_commands.describe(song="Optional song title")
    async def alias_lyrics(self, interaction: discord.Interaction, song: Optional[str] = None) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_lyrics.callback(self, interaction, song)

    @app_commands.command(name="shuffle", description="Shuffle songs in current queue (Shortcut for /music shuffle)")
    async def alias_shuffle(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_shuffle.callback(self, interaction)

    @app_commands.command(name="loop", description="Configure loop mode (Shortcut for /music loop)")
    @app_commands.describe(mode="Loop mode to apply")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Current Track", value="track"),
        app_commands.Choice(name="Whole Queue", value="queue"),
    ])
    async def alias_loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_loop.callback(self, interaction, mode)

    @app_commands.command(name="clear", description="Clear upcoming songs from queue (Shortcut for /music clear)")
    async def alias_clear(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_clear.callback(self, interaction)


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
        guild_pref = await self.bot.get_guild_prefix(message.guild.id)
        if query.startswith(guild_pref) or query.startswith("m!") or query.startswith(","):
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
                        try:
                            await status_msg.delete()
                        except Exception:
                            pass
                    else:
                        await status_msg.edit(content="😿 Failed to start playback.")
        except Exception as e:
            logger.error(f"Natural request error: {e}")

    @app_commands.command(name="invite", description="Get official invite link for MusicMaid and SentinelBot")
    async def invite(self, interaction: discord.Interaction) -> None:
        """Provide official invite links for MusicMaid with interactive buttons."""
        bot_name = self.bot.user.name if self.bot.user else "MusicMaid"
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label=f"Invite {bot_name} (Music)",
                style=discord.ButtonStyle.link,
                url="https://discord.com/oauth2/authorize?client_id=1556676516274905218&permissions=36768832&integration_type=0&scope=bot+applications.commands",
                emoji="🎵",
            )
        )
        view.add_item(
            discord.ui.Button(
                label="Invite The Raivora (Security)",
                style=discord.ButtonStyle.link,
                url="https://discord.com/oauth2/authorize?client_id=1554732669072445532&permissions=8&integration_type=0&scope=bot+applications.commands",
                emoji="🛡️",
            )
        )
        embed = discord.Embed(
            title=f"🐾 Invite {bot_name} & The Raivora",
            description=(
                f"Bring cute, futuristic 24/7 audio and autonomous security protection to your server!\n\n"
                f"🎵 **{bot_name}** — Hi-Fi Audio, 24/7 Radio, Smart Loudness & Stage Ducking\n"
                f"🛡️ **The Raivora** — Autonomous Anti-Nuke, AutoMod & Incident Radar"
            ),
            color=0x00E5FF,
        )
        embed.set_footer(text=f"{bot_name} • Cute & Futuristic Audio Companion")
        await interaction.response.send_message(embed=embed, view=view)


    # =========================================================================
    # PREFIX CUSTOMIZATION & PREFIX COMMAND SUITE
    # =========================================================================

    @app_commands.command(name="prefix", description="View or customize the server's prefix symbol (e.g. , or ! or ?)")
    @app_commands.describe(symbol="New prefix symbol (leave empty to view current prefix)")
    async def cmd_prefix(self, interaction: discord.Interaction, symbol: Optional[str] = None) -> None:
        """View or configure server custom prefix."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return

        current_pref = await self.bot.get_guild_prefix(interaction.guild.id)
        if not symbol:
            embed = discord.Embed(
                title="⚙️ SERVER PREFIX CONFIGURATION",
                description=(
                    f"The current prefix for **{interaction.guild.name}** is: `{current_pref}`\n\n"
                    f"**How to change it:**\n"
                    f"• Run `/prefix symbol:<new_symbol>` (e.g. `/prefix symbol:!` or `/prefix symbol:,`)\n"
                    f"• Or type `{current_pref}prefix <new_symbol>`\n\n"
                    f"*(Requires Administrator or Manage Server permission)*"
                ),
                color=COLOR_NEON_BLUE,
            )
            embed.set_footer(text=f"You can also mention the bot: @MusicMaid help")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need the **Manage Server** permission to change the prefix.", ephemeral=True)
            return

        new_sym = symbol.strip()
        if not (1 <= len(new_sym) <= 5):
            await interaction.response.send_message("❌ Prefix must be between 1 and 5 characters long.", ephemeral=True)
            return

        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        settings.prefix = new_sym
        await self.bot.db.update_guild_settings(settings)
        self.bot.set_cached_prefix(interaction.guild.id, new_sym)

        embed = discord.Embed(
            title="✅ PREFIX CUSTOMIZED",
            description=f"Server prefix updated to: `{new_sym}`\n\nTry running `{new_sym}play lofi` or `{new_sym}c`!",
            color=COLOR_ELECTRIC_CYAN,
        )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="prefix")
    async def pfx_prefix(self, ctx: commands.Context, new_symbol: Optional[str] = None) -> None:
        """View or customize the server prefix."""
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return

        current_pref = await self.bot.get_guild_prefix(ctx.guild.id)
        if not new_symbol:
            embed = discord.Embed(
                title="⚙️ SERVER PREFIX CONFIGURATION",
                description=(
                    f"Current prefix for **{ctx.guild.name}**: `{current_pref}`\n\n"
                    f"**To change it:**\n"
                    f"`{current_pref}prefix <new_symbol>` (e.g. `{current_pref}prefix !`)\n\n"
                    f"*(Requires Manage Server or Administrator)*"
                ),
                color=COLOR_NEON_BLUE,
            )
            await ctx.reply(embed=embed, mention_author=False)
            return

        if not ctx.author.guild_permissions.manage_guild and not ctx.author.guild_permissions.administrator:
            await ctx.reply("❌ You need the **Manage Server** permission to change the prefix.", mention_author=False)
            return

        new_sym = new_symbol.strip()
        if not (1 <= len(new_sym) <= 5):
            await ctx.reply("❌ Prefix must be between 1 and 5 characters long.", mention_author=False)
            return

        settings = await self.bot.db.get_guild_settings(ctx.guild.id)
        settings.prefix = new_sym
        await self.bot.db.update_guild_settings(settings)
        self.bot.set_cached_prefix(ctx.guild.id, new_sym)

        embed = discord.Embed(
            title="✅ PREFIX CUSTOMIZED",
            description=f"Server prefix updated to: `{new_sym}`\n\nTry running `{new_sym}play lofi` or `{new_sym}c`!",
            color=COLOR_ELECTRIC_CYAN,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="play", aliases=["p"])
    async def pfx_play(self, ctx: commands.Context, *, query: str = "") -> None:
        """Plays audio from YouTube, Spotify, or SoundCloud via prefix command."""
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return

        pref = await self.bot.get_guild_prefix(ctx.guild.id)
        if not query.strip():
            await ctx.reply(f"🎵 **Usage:** `{pref}play <song title or URL>` (or `{pref}p <song>`)", mention_author=False)
            return

        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.reply("❌ Join a voice channel first to play music!", mention_author=False)
            return

        session = await self.session_manager.get_session(ctx.guild.id)
        async with session.lock:
            vc = await VoiceManager.join_voice_channel(ctx.author, ctx.channel, session)  # type: ignore
            if not vc:
                err = getattr(session, "last_error", None) or "Could not connect to voice channel."
                await ctx.reply(f"❌ {err}\n💡 Please check voice channel permissions for MusicMaid.", mention_author=False)
                return

        status_msg = await ctx.reply(f"🔍 Searching for `{query[:60]}`... 🐾", mention_author=False)
        track = await AudioResolver.resolve_track(query, ctx.author.id, str(ctx.author))
        if not track:
            await status_msg.edit(content=f"😿 Could not find playable audio for: `{query[:60]}`")
            return

        async with session.lock:
            if session.is_playing:
                session.queue.append(track)
                embed = discord.Embed(
                    title="🎵 ADDED TO QUEUE",
                    description=f"**[{track.title}]({track.url})**\nDuration: `{format_duration(track.duration)}` • Position: `#{len(session.queue)}`",
                    color=COLOR_NEON_BLUE,
                )
                if track.thumbnail:
                    embed.set_thumbnail(url=track.thumbnail)
                await status_msg.edit(content=None, embed=embed)
            else:
                success = await MusicPlayerService.start_playback(self.bot, session, track)
                if success:
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                else:
                    await status_msg.edit(content="😿 Failed to start playback.")

    @commands.command(name="skip", aliases=["s"])
    async def pfx_skip(self, ctx: commands.Context) -> None:
        """Skips the currently playing track."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        if not session.is_playing or not session.current_track:
            await ctx.reply("❌ Nothing is currently playing.", mention_author=False)
            return
        skipped_name = session.current_track.title
        await MusicPlayerService.skip_current(session)
        await ctx.reply(f"⏭️ Skipped: **{skipped_name[:50]}**", mention_author=False)

    @commands.command(name="pause")
    async def pfx_pause(self, ctx: commands.Context) -> None:
        """Pauses audio playback."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        if not session.voice_client or not session.is_playing:
            await ctx.reply("❌ Nothing is playing to pause.", mention_author=False)
            return
        session.voice_client.pause()
        session.is_paused = True
        await ctx.reply("⏸️ Playback paused.", mention_author=False)

    @commands.command(name="resume", aliases=["unpause"])
    async def pfx_resume(self, ctx: commands.Context) -> None:
        """Resumes paused playback."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        if not session.voice_client or not session.is_paused:
            await ctx.reply("❌ Playback is not paused.", mention_author=False)
            return
        session.voice_client.resume()
        session.is_paused = False
        await ctx.reply("▶️ Playback resumed.", mention_author=False)

    @commands.command(name="stop")
    async def pfx_stop(self, ctx: commands.Context) -> None:
        """Stops playback and clears the queue."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        async with session.lock:
            session.queue.clear()
            session.current_track = None
            session.is_playing = False
            session.is_paused = False
            if session.voice_client and session.voice_client.is_playing():
                session.voice_client.stop()
        await ctx.reply("⏹️ Stopped playback and cleared queue.", mention_author=False)

    @commands.command(name="queue", aliases=["q"])
    async def pfx_queue(self, ctx: commands.Context) -> None:
        """Views upcoming songs in queue."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        if not session.queue:
            now_playing = f"Now Playing: **{session.current_track.title}**\n\n" if session.current_track else ""
            await ctx.reply(f"{now_playing}📜 The queue is empty.", mention_author=False)
            return
        lines = []
        for i, t in enumerate(session.queue[:10], start=1):
            lines.append(f"`{i}.` **{t.title[:45]}** (`{format_duration(t.duration)}`)")
        total_sec = sum(t.duration for t in session.queue)
        embed = discord.Embed(
            title=f"📜 Queue ({len(session.queue)} tracks)",
            description="\n".join(lines),
            color=COLOR_NEON_BLUE,
        )
        embed.set_footer(text=f"Total Queue Time: {format_duration(total_sec)}")
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="np", aliases=["nowplaying"])
    async def pfx_np(self, ctx: commands.Context) -> None:
        """Displays currently playing track information."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        if not session.current_track:
            await ctx.reply("❌ Nothing is currently playing.", mention_author=False)
            return
        from music_bot.services.player_service import NowPlayingControlView
        embed = MusicPlayerService.build_now_playing_embed(session)
        view = NowPlayingControlView(session)
        msg = await ctx.reply(embed=embed, view=view, mention_author=False)
        session.now_playing_message = msg

    @commands.command(name="volume", aliases=["vol", "v"])
    async def pfx_volume(self, ctx: commands.Context, level: Optional[int] = None) -> None:
        """Adjusts playback volume (0 to 150)."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        if level is None:
            await ctx.reply(f"🔊 Current volume: **{session.volume}%**", mention_author=False)
            return
        if not (0 <= level <= 150):
            await ctx.reply("❌ Volume must be between 0 and 150%.", mention_author=False)
            return
        session.volume = level
        if session.voice_client and session.voice_client.source:
            if hasattr(session.voice_client.source, "volume"):
                session.voice_client.source.volume = level / 100.0  # type: ignore
        await ctx.reply(f"🔊 Volume set to **{level}%**.", mention_author=False)

    @commands.command(name="c", aliases=["control", "panel"])
    async def pfx_control_panel(self, ctx: commands.Context) -> None:
        """Opens the interactive Master Control Panel."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        view = MasterControlPanelView(self.bot, ctx.guild, session)
        embed = view.build_embed()
        await ctx.reply(embed=embed, view=view, mention_author=False)

    @commands.command(name="247", aliases=["stay"])
    async def pfx_247(self, ctx: commands.Context) -> None:
        """Toggles 24/7 mode in current voice channel."""
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        settings = await self.bot.db.get_guild_settings(ctx.guild.id)
        session = await self.session_manager.get_session(ctx.guild.id)
        new_state = not settings.twenty_four_seven_enabled
        settings.twenty_four_seven_enabled = new_state
        session.twenty_four_seven = new_state

        if new_state:
            target_vc = None
            if session.voice_client and session.voice_client.is_connected():
                target_vc = session.voice_client.channel
            elif ctx.author.voice and ctx.author.voice.channel:
                target_vc = ctx.author.voice.channel
                async with session.lock:
                    vc = await VoiceManager.join_voice_channel(ctx.author, ctx.channel, session)  # type: ignore
                    if not vc:
                        err = getattr(session, "last_error", None) or "Could not connect to voice channel."
                        await ctx.reply(f"❌ {err}\n💡 Please check voice channel permissions for MusicMaid.", mention_author=False)
                        return
            else:
                settings.twenty_four_seven_enabled = False
                session.twenty_four_seven = False
                await self.bot.db.update_guild_settings(settings)
                await ctx.reply("⚠️ Please join a voice channel first so MusicMaid knows where to stay!", mention_author=False)
                return

            if target_vc:
                settings.twenty_four_seven_channel_id = target_vc.id
            if session.auto_leave_task and not session.auto_leave_task.done():
                session.auto_leave_task.cancel()
                session.auto_leave_task = None
            await self.bot.db.update_guild_settings(settings)
            await ctx.reply(f"📻 **24/7 Mode ACTIVATED** in **{target_vc.name if target_vc else 'voice'}**! MusicMaid will stay connected indefinitely.", mention_author=False)
        else:
            settings.twenty_four_seven_channel_id = None
            await self.bot.db.update_guild_settings(settings)
            await ctx.reply("📻 **24/7 Mode DEACTIVATED**.", mention_author=False)

    @commands.command(name="loop")
    async def pfx_loop(self, ctx: commands.Context, mode: str = "") -> None:
        """Toggles loop mode: off, track, queue."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        mode = mode.lower().strip()
        if mode in ("track", "song", "single"):
            session.loop_mode = "track"
        elif mode in ("queue", "all"):
            session.loop_mode = "queue"
        elif mode in ("off", "none", "disable"):
            session.loop_mode = "off"
        else:
            cycle = {"off": "track", "track": "queue", "queue": "off"}
            session.loop_mode = cycle.get(session.loop_mode, "off")
        await ctx.reply(f"🔁 Loop mode is now: **{session.loop_mode.upper()}**", mention_author=False)

    @commands.command(name="shuffle")
    async def pfx_shuffle(self, ctx: commands.Context) -> None:
        """Shuffles upcoming songs in queue."""
        if not ctx.guild:
            return
        import random
        session = await self.session_manager.get_session(ctx.guild.id)
        if len(session.queue) < 2:
            await ctx.reply("❌ Need at least 2 tracks in queue to shuffle.", mention_author=False)
            return
        random.shuffle(session.queue)
        await ctx.reply(f"🔀 Shuffled **{len(session.queue)}** tracks in queue!", mention_author=False)

    @commands.command(name="clear")
    async def pfx_clear(self, ctx: commands.Context) -> None:
        """Clears all upcoming songs from queue."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        count = len(session.queue)
        session.queue.clear()
        await ctx.reply(f"🗑️ Cleared **{count}** tracks from queue.", mention_author=False)

    @commands.command(name="filter", aliases=["eq"])
    async def pfx_filter(self, ctx: commands.Context, preset: str = "") -> None:
        """Applies audio DSP preset (bassboost, nightcore, 8d, vaporwave, vocal, reset)."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        preset = preset.lower().strip()
        valid = ["bassboost", "nightcore", "8d", "vaporwave", "vocal", "reset"]
        if preset not in valid:
            pref = await self.bot.get_guild_prefix(ctx.guild.id)
            await ctx.reply(f"🎛️ **Available presets:** `{'`, `'.join(valid)}`\nUsage: `{pref}filter bassboost` (or `{pref}eq nightcore`)", mention_author=False)
            return
        session.active_preset = "none" if preset == "reset" else preset
        await ctx.reply(f"🎛️ Audio filter preset set to: **{preset.upper()}** (applies on next song/seek)", mention_author=False)

    @commands.command(name="commands", aliases=["help", "cmds"])
    async def pfx_help(self, ctx: commands.Context) -> None:
        """Displays all available prefix and slash commands."""
        if not ctx.guild:
            return
        pref = await self.bot.get_guild_prefix(ctx.guild.id)
        embed = discord.Embed(
            title="🐾 MusicMaid • Commands & Prefix Guide",
            description=(
                f"**Current Server Prefix:** `{pref}` *(Customizable!)*\n"
                f"You can also use Discord **Slash Commands** (`/`) for all features!\n\n"
                f"🎵 **Playback:** `{pref}play <song>` (`{pref}p`), `{pref}skip` (`{pref}s`), `{pref}pause`, `{pref}resume`, `{pref}stop`\n"
                f"📜 **Queue:** `{pref}queue` (`{pref}q`), `{pref}np`, `{pref}volume <0-150>` (`{pref}v`), `{pref}loop`, `{pref}shuffle`, `{pref}clear`\n"
                f"🎛️ **Audio & Filters:** `{pref}filter <preset>` (`{pref}eq`), `{pref}c` *(Master Control Panel)*\n"
                f"📻 **24/7 Voice:** `{pref}247` or `{pref}stay` *(Keep bot in voice channel 24/7)*\n"
                f"⚙️ **Prefix Customization:** `{pref}prefix <symbol>` *(e.g. `{pref}prefix !`)*"
            ),
            color=COLOR_ELECTRIC_CYAN,
        )
        embed.set_footer(text=f"Change prefix anytime with: {pref}prefix <symbol> or /prefix symbol:<symbol>")
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="reload", aliases=["hotreload"])
    async def pfx_reload(self, ctx: commands.Context) -> None:
        """Hot-reloads bot code and preserves playback without restarting from the beginning."""
        if not ctx.guild:
            return
        is_admin = getattr(ctx.author.guild_permissions, "administrator", False) if isinstance(ctx.author, discord.Member) else False
        is_owner = str(ctx.author.id) in ("1457380609641938981",)
        if not is_admin and not is_owner:
            await ctx.reply("❌ Administrator permissions required to hot-reload code.", mention_author=False)
            return

        status_msg = await ctx.reply("⚙️ **Hot-reloading code changes...** Playback will resume right where it left off!", mention_author=False)
        from music_bot.services.updater_service import MusicAutoUpdater
        success, msg = await MusicAutoUpdater.hot_reload_services(bot=self.bot)
        embed = discord.Embed(
            title="✅ HOT-RELOAD COMPLETE" if success else "❌ HOT-RELOAD FAILED",
            description=msg,
            color=COLOR_ELECTRIC_CYAN if success else 0xED4245,
        )
        await status_msg.edit(content=None, embed=embed)

    @commands.command(name="update")
    async def pfx_update(self, ctx: commands.Context) -> None:
        """Updates yt-dlp extractor in background."""
        if not ctx.guild:
            return
        is_admin = getattr(ctx.author.guild_permissions, "administrator", False) if isinstance(ctx.author, discord.Member) else False
        is_owner = str(ctx.author.id) in ("1457380609641938981",)
        if not is_admin and not is_owner:
            await ctx.reply("❌ Administrator permissions required to update dependencies.", mention_author=False)
            return

        status_msg = await ctx.reply("🔄 **Checking & updating audio extractor...**", mention_author=False)
        from music_bot.services.updater_service import MusicAutoUpdater
        success, msg = await MusicAutoUpdater.update_ytdl(force=True, bot=self.bot)
        embed = discord.Embed(
            title="✅ AUDIO EXTRACTOR UPDATED" if success else "❌ UPDATE FAILED",
            description=msg,
            color=COLOR_ELECTRIC_CYAN if success else 0xED4245,
        )
        await status_msg.edit(content=None, embed=embed)

    @commands.command(name="dj", aliases=["autoplay", "nonstop"])
    async def pfx_dj(self, ctx: commands.Context, mode: Optional[str] = None) -> None:
        """Toggle non-stop Neko DJ continuous playback (,dj, ,dj on, ,dj off)."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        settings = await self.bot.db.get_dj_settings(ctx.guild.id)

        target_state = not settings.enabled if mode is None else mode.lower() in ("on", "enable", "true", "start", "1")
        settings.enabled = target_state
        settings.auto_queue = True
        await self.bot.db.update_dj_settings(settings)
        session.dj_enabled = target_state

        if target_state:
            started_now = False
            if isinstance(ctx.author, discord.Member) and ctx.author.voice and ctx.author.voice.channel and not session.is_playing:
                from music_bot.services.voice_service import VoiceManager
                vc = await VoiceManager.join_voice_channel(ctx.author, ctx.channel, session)
                if vc:
                    from music_bot.services.dj_service import NekoDJService
                    rec = await NekoDJService.get_recommendation(self.bot, session)
                    if rec:
                        track, rationale = rec
                        started = await MusicPlayerService.start_playback(self.bot, session, track)
                        if started:
                            started_now = True
                            from music_bot.services.player_service import NowPlayingControlView
                            embed = MusicPlayerService.build_now_playing_embed(session)
                            view = NowPlayingControlView(session)
                            msg = await ctx.reply(
                                f"🎧 **Neko DJ Non-Stop Mode ACTIVE!** Connected to **#{ctx.author.voice.channel.name}**!\n*{rationale}*",
                                embed=embed,
                                view=view,
                                mention_author=False,
                            )
                            session.now_playing_message = msg

            if not started_now:
                await ctx.reply("🎧 **Neko DJ Non-Stop Mode ACTIVE!** Music will play continuously non-stop without silence. 🐾", mention_author=False)
        else:
            await ctx.reply("⏹️ **Neko DJ Non-Stop Mode DISABLED.** Playback will stop when the queue finishes.", mention_author=False)

    @app_commands.command(name="support", description="Official Support Server for MusicMaid and Rai bots (MRL GAMING)")
    async def music_support(self, interaction: discord.Interaction) -> None:
        from config import SUPPORT_INVITE_URL
        embed = discord.Embed(
            title="💬 MusicMaid Official Support Server",
            description=(
                "Need help, have feature suggestions, or want to report an issue?\n\n"
                f"👉 **[Click Here to Join MRL GAMING Support Server]({SUPPORT_INVITE_URL})**\n\n"
                "• 24/7 Audio Bot Assistance & Live Help\n"
                "• Feature Requests & Changelogs\n"
                "• Community & Music Discussions"
            ),
            color=0x5865F2,
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Join Support Server", url=SUPPORT_INVITE_URL, emoji="💬"))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @commands.command(name="support")
    async def pfx_support(self, ctx: commands.Context) -> None:
        from config import SUPPORT_INVITE_URL
        embed = discord.Embed(
            title="💬 Official Support Server",
            description=(
                "Need help? Join our official support server:\n\n"
                f"👉 **[Join MRL GAMING Support Server]({SUPPORT_INVITE_URL})**"
            ),
            color=0x5865F2,
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Join Support Server", url=SUPPORT_INVITE_URL, emoji="💬"))
        await ctx.send(embed=embed, view=view)


async def setup(bot: RaiMusicBot) -> None:
    await bot.add_cog(MusicCog(bot))
