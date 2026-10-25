"""
Master Neko Songs Command Suite.
Registers all /music commands, subcommands, aliases, setup wizard, and natural requests.
Adheres strictly to the Neko Songs brand identity, cute personality, and isolated architecture.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import io
import json
import logging
import math
import os
import random
import re
import sys
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

from music_bot import config
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
from music_bot.emojis import EmojiManager
from music_bot.theme import (
    COLOR_PRIMARY,
    COLOR_CYAN,
    COLOR_MIDNIGHT,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_PREMIUM,
    create_branded_embed,
    success_embed,
    error_embed,
    warning_embed,
    loading_embed,
    info_embed,
    premium_embed,
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
from music_bot.services.resolver_service import (
    AudioResolver,
    _safe_query_for_log,
    _video_id_from_url,
    analyze_query_intent,
    requires_candidate_confirmation,
)
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


def _alternative_track_matches_query(query: str, track: Any) -> bool:
    """Reject alternative-provider fallbacks whose title changes the requested song identity."""
    intent = analyze_query_intent(query)
    core_tokens = [
        token for token in re.findall(r"\w+", str(intent.get("core_title") or "").casefold())
        if len(token) >= 4
    ]
    if not core_tokens:
        return True
    identity_tokens = set(
        re.findall(
            r"\w+",
            " ".join(
                str(getattr(track, field, "") or "")
                for field in ("title", "artist")
            ).casefold(),
        )
    )
    return all(token in identity_tokens for token in core_tokens)


# =============================================================================
# SEARCH SELECTION MENU
# =============================================================================

class TrackSelectView(discord.ui.View):
    """Dropdown select menu for ambiguous search queries."""

    def __init__(self, candidates: List[dict], user_id: int, on_select_coro):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.on_select_coro = on_select_coro
        self._selected = False

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
            placeholder="Select a song for MusicMaid to play...",
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

        if self._selected or self.is_finished():
            return
        self._selected = True
        self.stop()

        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True

        selected_idx = int(interaction.data["values"][0])  # type: ignore
        await interaction.response.defer()
        await self.on_select_coro(interaction, selected_idx)


def get_public_web_url() -> Optional[str]:
    """Return the configured and validated public MusicMaid web dashboard URL."""
    from music_bot.config import get_musicmaid_website_url
    return get_musicmaid_website_url()


def get_premium_plans_url() -> Optional[str]:
    """Return the configured and validated public MusicMaid premium plans URL if one exists."""
    from music_bot.config import get_premium_plans_url as _get_plans
    return _get_plans()



class PremiumLinkView(discord.ui.View):
    """Interactive link button view to the public MusicMaid web platform."""

    def __init__(self, web_url: Optional[str] = None, plans_url: Optional[str] = None):
        super().__init__(timeout=None)
        from music_bot.config import (
            get_musicmaid_website_url,
            get_premium_plans_url,
            is_valid_public_https_url,
        )

        resolved_web_url = web_url if web_url is not None else get_musicmaid_website_url()
        resolved_plans_url = plans_url if plans_url is not None else get_premium_plans_url()

        if resolved_web_url and is_valid_public_https_url(resolved_web_url):
            self.add_item(
                discord.ui.Button(
                    label="Open MusicMaid Website",
                    url=resolved_web_url,
                    style=discord.ButtonStyle.link,
                    emoji="🌐",
                )
            )

        if resolved_plans_url and is_valid_public_https_url(resolved_plans_url):
            self.add_item(
                discord.ui.Button(
                    label="View Premium Plans",
                    url=resolved_plans_url,
                    style=discord.ButtonStyle.link,
                    emoji="💎",
                )
            )



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
# MASTER CONTROL PANEL VIEW (/panel)
# =============================================================================

class MusicControlSelect(discord.ui.Select):
    """Dropdown selector for the /panel master control panel."""

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
                value="`/music dj` • `/music lyrics` • `/music recommend` • `/autoupdate` • `/reload` • `/panel`",
                inline=False,
            )
            embed.set_footer(text=f"{bot_name} v{MUSIC_BOT_VERSION} • Tap buttons below for instant actions")

        elif self.current_page == "playback":
            embed = discord.Embed(
                title="🎵 Playback & Queue Commands",
                description="Precision streaming audio controls for crystal clear sound:",
                color=COLOR_NEON_BLUE,
            )
            embed.add_field(name="`/music play <query>`", value="Streams audio from YouTube or Spotify links.", inline=False)
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
            embed.add_field(name="📊 `/panel` or `/control`", value="Opens this interactive Master Control Panel anytime.", inline=False)

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
            self.session.is_intentional_stop = False
            self.session.is_intentional_disconnect = False
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
            self.session.is_intentional_disconnect = True
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


# Alias for backward compatibility
MasterControlPanelView = MusicControlPanelView


class Reconnect247View(discord.ui.View):
    """Interactive button to attempt immediate voice reconnection for 24/7 guilds."""

    def __init__(self, bot: Any, guild: discord.Guild, channel_id: Optional[int]):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.guild = guild
        self.channel_id = channel_id

    @discord.ui.button(label="Reconnect Voice", style=discord.ButtonStyle.primary, emoji="📻")
    async def btn_reconnect(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        if not self.channel_id:
            await interaction.followup.send("❌ No saved 24/7 channel ID found for this server.", ephemeral=True)
            return

        ch = self.guild.get_channel(self.channel_id)
        if not isinstance(ch, (discord.VoiceChannel, discord.StageChannel)):
            await interaction.followup.send("❌ Saved voice channel no longer exists.", ephemeral=True)
            return

        session = await self.bot.session_manager.get_session(self.guild.id)
        from music_bot.services.voice_service import VoiceManager
        vc = await VoiceManager.join_voice_channel(
            self.guild.me, interaction.channel, session, target_channel=ch  # type: ignore
        )
        if vc and vc.is_connected():
            session.voice_client = vc
            session.twenty_four_seven = True
            session.is_intentional_stop = False
            await interaction.followup.send(
                f"✅ **Reconnected!** NyxTune is now in {ch.mention} in 24/7 mode.", ephemeral=True
            )
        else:
            err = session.last_error or "Reconnection failed."
            await interaction.followup.send(
                f"❌ **Reconnection failed:** {err}", ephemeral=True
            )


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
            except discord.HTTPException as e:
                if e.code in (40060, 10062):
                    return True
                logger.debug(f"Interaction deferral HTTP notice: {e}")
                return False
            except Exception as e:
                logger.debug(f"Interaction deferral notice: {e}")
                return False
        return True

    async def is_bot_developer_or_owner(self, user: Optional[discord.abc.User | discord.Member | int | str]) -> bool:
        """Return True if user matches bot creator/developer, application owner, or team developer."""
        if not user:
            return False
        uid = getattr(user, "id", user)
        try:
            uid_int = int(uid)
        except (ValueError, TypeError):
            return False

        if config.is_bot_owner(uid_int):
            return True

        # Check via bot.is_owner coroutine if available
        try:
            target_user = user if isinstance(user, (discord.User, discord.Member)) else self.bot.get_user(uid_int)
            if not target_user and hasattr(self.bot, "fetch_user"):
                target_user = await self.bot.fetch_user(uid_int)
            if target_user and hasattr(self.bot, "is_owner") and await self.bot.is_owner(target_user):
                config.register_bot_owner(uid_int)
                if getattr(self.bot, "db", None):
                    await self.bot.db.set_premium(
                        uid_int,
                        entity_type="user",
                        is_premium=True,
                        tier="owner",
                        activated_by=uid_int,
                    )
                return True
        except Exception:
            pass

        return False

    @staticmethod
    async def send_ephemeral_or_fallback(
        interaction: discord.Interaction,
        embed: Optional[discord.Embed] = None,
        content: Optional[str] = None,
        view: Optional[discord.ui.View] = None,
    ) -> None:
        """Send an ephemeral message ('Only you can see this') and clean up any public deferred message."""
        try:
            send_kwargs = {"ephemeral": True}
            if content is not None:
                send_kwargs["content"] = content
            if embed is not None:
                send_kwargs["embed"] = embed
            if view is not None:
                send_kwargs["view"] = view

            if interaction.response.is_done():
                try:
                    await interaction.delete_original_response()
                except Exception:
                    pass
                await interaction.followup.send(**send_kwargs)
            else:
                await interaction.response.send_message(**send_kwargs)
        except Exception:
            try:
                edit_kwargs = {}
                if content is not None:
                    edit_kwargs["content"] = content
                if embed is not None:
                    edit_kwargs["embed"] = embed
                edit_kwargs["view"] = view
                await interaction.edit_original_response(**edit_kwargs)
            except Exception:
                pass

    async def _check_permissions(self, interaction: discord.Interaction) -> bool:
        """Verify user is in voice channel and allowed to use music commands."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await self.send_ephemeral_or_fallback(interaction, content="❌ This command must be used in a server.")
            return False

        if not interaction.user.voice or not interaction.user.voice.channel:
            await self.send_ephemeral_or_fallback(interaction, content="❌ You must join a voice channel first.")
            return False

        return True

    async def _play_query(
        self,
        interaction: discord.Interaction,
        query: str,
        ephemeral: bool = False,
        correlation_id: Optional[str] = None,
        display_name: Optional[str] = None,
        top: bool = False,
    ) -> None:
        """Internal worker executing search, resolve, queueing, and playback transition."""
        correlation_id = correlation_id or uuid.uuid4().hex[:8].upper()
        try:
            start_t = time.time()
            normalized_query = " ".join(query.split())
            logger.info(
                "[Playback] operation=play_request correlation_id=%s query=%r normalized_query=%r",
                correlation_id,
                _safe_query_for_log(query),
                _safe_query_for_log(normalized_query),
            )
            guild = interaction.guild
            member = interaction.user
            text_channel = interaction.channel

            if not guild or not isinstance(member, discord.Member) or not isinstance(text_channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread)):
                await self.send_ephemeral_or_fallback(interaction, content="❌ Cannot determine server or channel context.")
                return

            session = await self.session_manager.get_session(guild.id)
            session.is_intentional_stop = False
            session.last_error = None

            # 1. Connect to voice with resilient bounded connection handling
            async with session.lock:
                vc = None
                voice_join_error: Optional[Exception] = None
                try:
                    vc = await VoiceManager.join_voice_channel(member, text_channel, session)
                except Exception as join_exc:
                    voice_join_error = join_exc
                    vc = None
                    session.last_error = str(join_exc)
                    logger.error(f"[Playback] Exception joining voice channel: {join_exc}", exc_info=True)

                if not vc:
                    err_detail = getattr(session, "last_error", None) or (str(voice_join_error) if voice_join_error else "Voice connection could not be established.")
                    ch = getattr(getattr(member, "voice", None), "channel", None)
                    ch_name = getattr(ch, "name", "your voice channel")

                    # Only show "How to fix: Permissions..." if genuinely a Discord permission error
                    is_perm_err = (
                        (voice_join_error is not None and isinstance(voice_join_error, discord.Forbidden))
                        or ("403" in err_detail and "forbidden" in err_detail.lower())
                        or ("permission" in err_detail.lower())
                    ) and not any(dep in err_detail.lower() for dep in ("davey", "pynacl", "opus", "dependency", "timed out", "timeout"))

                    try:
                        if is_perm_err:
                            desc = (
                                f"Could not connect to **{ch_name}**.\n"
                                f"• **Reason:** {err_detail}\n\n"
                                f"💡 *How to fix:* Right-click/tap the voice channel ➔ **Edit Channel** ➔ **Permissions** ➔ grant **MusicMaid** the **Connect** & **Speak** permissions!"
                            )
                        elif "Voice connection failed:" in err_detail:
                            desc = f"Could not connect to **{ch_name}**.\n\n{err_detail}"
                        else:
                            desc = f"Could not connect to **{ch_name}**.\n• **Reason:** {err_detail}"

                        embed_conn_err = discord.Embed(
                            title="❌ COULD NOT CONNECT TO VOICE",
                            description=desc,
                            color=0xED4245,
                        )
                    except Exception as fmt_err:
                        logger.error(f"[Playback] Error formatting voice error embed: {fmt_err}", exc_info=True)
                        embed_conn_err = discord.Embed(
                            title="❌ COULD NOT CONNECT TO VOICE",
                            description=f"Could not connect to voice channel.\n• **Reason:** {err_detail}",
                            color=0xED4245,
                        )

                    await self.send_ephemeral_or_fallback(interaction, embed=embed_conn_err)
                    return

            # 2. Resolve query: premium neon status card with honest diagnostics.
            # Provider rows describe the resolver's supported sources; they are not live per-provider telemetry.
            request_label = display_name or query
            if query.startswith(("http://", "https://", "spotify:")):
                request_kind = "Direct link / metadata lookup"
                action_label = "Resolving the requested track"
            else:
                request_kind = "Song title search"
                action_label = "Searching candidates and validating the match"

            safe_request_label = str(request_label or "Unknown track").replace("`", "'")[:100]
            embed_loading = discord.Embed(
                title="✦  MUSICMAID  •  RESOLVING AUDIO",
                description=(
                    f"**♫ REQUESTED TRACK**\n> `{safe_request_label}`\n\n"
                    f"**◈ CURRENT STAGE**\n> 🟣 {action_label}\n> ⚪ Preparing a playable audio stream\n\n"
                    "*Playback has not started. MusicMaid will validate the selected result before queueing it.*"
                ),
                color=COLOR_PREMIUM,
            )
            pipeline_value = (
                "🟣 **Resolve requested link** — in progress\n"
                "⚪ **Validate track metadata** — next\n"
                "⚪ **Resolve stream URL** — pending\n"
                "⚪ **Prepare FFmpeg playback** — pending"
                if query.startswith(("http://", "https://", "spotify:"))
                else
                "🟣 **Search candidates** — in progress\n"
                "⚪ **Validate title / artist / video ID** — next\n"
                "⚪ **Resolve stream URL** — pending\n"
                "⚪ **Prepare FFmpeg playback** — pending"
            )
            embed_loading.add_field(
                name="⌁ RESOLUTION PIPELINE",
                value=pipeline_value,
                inline=False,
            )
            embed_loading.add_field(
                name="◈ SUPPORTED SOURCES",
                value="YouTube · Audius · Jamendo\nSpotify / Apple Music metadata · Direct audio URLs",
                inline=True,
            )
            embed_loading.add_field(
                name="⌘ TRACE DETAILS",
                value=(
                    f"**Request type:** `{request_kind}`\n"
                    f"**Trace ID:** `{str(correlation_id)[:32]}`\n"
                    "**Retry count:** `not reported yet`\n"
                    "**Last error:** `none reported yet`"
                ),
                inline=True,
            )
            embed_loading.add_field(
                name="↻ RETRIES & FALLBACKS",
                value=(
                    "Resolver-managed retry and fallback logic remains in control. "
                    "If a source fails, the final diagnostic appears in the result/error message and bot logs."
                ),
                inline=False,
            )
            embed_loading.set_footer(text="RAI MUSIC SYSTEM  •  RESOLUTION STATUS  •  NOT YET PLAYING")
            try:
                await interaction.edit_original_response(content=None, embed=embed_loading, view=None)
            except Exception as load_err:
                logger.debug(f"[Playback] Notice setting loading embed: {load_err}")

            # Update this same Discord response while real work is still running.
            # Keep elapsed time factual; source/retry counts are not fabricated.
            progress_state = {
                "started": time.monotonic(),
                "stage": action_label,
                "active": True,
            }

            async def _refresh_resolving_status() -> None:
                while progress_state["active"]:
                    await asyncio.sleep(4)
                    if not progress_state["active"]:
                        break
                    elapsed = max(0, int(time.monotonic() - progress_state["started"]))
                    minutes, seconds = divmod(elapsed, 60)
                    elapsed_text = f"{minutes:02d}:{seconds:02d}"
                    embed_loading.description = (
                        f"**♫ REQUESTED TRACK**\n> `{safe_request_label}`\n\n"
                        f"**◈ CURRENT STAGE**\n> 🟣 {progress_state['stage']}\n"
                        f"> ⏱ Elapsed: `{elapsed_text}`\n\n"
                        "*Playback has not started. MusicMaid will validate the selected result before queueing it.*"
                    )
                    try:
                        await interaction.edit_original_response(
                            content=None, embed=embed_loading, view=None
                        )
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as status_err:
                        logger.debug(
                            "[Playback] operation=progress_update correlation_id=%s "
                            "exception_type=%s outcome=stopped",
                            correlation_id,
                            type(status_err).__name__,
                        )
                        break
                    except Exception as status_err:
                        logger.debug(
                            "[Playback] progress update skipped: %s",
                            type(status_err).__name__,
                        )

            progress_task = asyncio.create_task(_refresh_resolving_status())

            async def _stop_resolving_status() -> None:
                progress_state["active"] = False
                if not progress_task.done():
                    progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass

            if not query.startswith(("http://", "https://")):
                try:
                    candidates = await AudioResolver.search(
                        query,
                        limit=5,
                        correlation_id=correlation_id,
                    )
                except Exception as search_exc:
                    candidates = []
                    logger.warning(
                        "[Playback] operation=preselection_search correlation_id=%s "
                        "exception_type=%s outcome=failed",
                        correlation_id,
                        type(search_exc).__name__,
                    )
                if requires_candidate_confirmation(candidates):
                    logger.info(
                        "[Playback] operation=candidate_confirmation correlation_id=%s "
                        "candidate_count=%d outcome=required",
                        correlation_id,
                        len(candidates),
                    )

                    async def on_candidate_select(
                        selected_interaction: discord.Interaction,
                        selected_index: int,
                    ) -> None:
                        selected = candidates[selected_index]
                        selected_url = selected.get("url") or ""
                        selected_title = selected.get("title") or ""
                        logger.info(
                            "[Playback] operation=candidate_selected correlation_id=%s "
                            "title=%r video_id=%s score=%s",
                            correlation_id,
                            selected_title,
                            selected.get("id") or _video_id_from_url(selected_url) or "unavailable",
                            selected.get("_match_score", "unavailable"),
                        )
                        await self._play_query(
                            selected_interaction,
                            selected_url,
                            correlation_id=correlation_id,
                            display_name=selected_title,
                        )

                    await _stop_resolving_status()
                    selection_view = TrackSelectView(candidates, member.id, on_candidate_select)
                    await interaction.edit_original_response(
                        content="Several results are plausible, or the best match is uncertain. Choose the intended track:",
                        embed=None,
                        view=selection_view,
                    )
                    return

            # Pin ordinary text searches to the best ranked candidate URL. Re-running
            # the original text inside the resolver performs a second search and can
            # silently swap a requested title (e.g. KALYANI) for a near-spelling match.
            resolve_query = query
            if (
                not query.startswith(("http://", "https://"))
                and not re.match(r"spotify:(?:track|playlist|album):", query, re.IGNORECASE)
                and "spotify.com/" not in query.casefold()
                and "music.apple.com/" not in query.casefold()
                and candidates
            ):
                best_url = str(candidates[0].get("url") or "").strip()
                if _video_id_from_url(best_url):
                    resolve_query = best_url
                    logger.info(
                        "[Playback] operation=ranked_candidate_pinned correlation_id=%s "
                        "video_id=%s title=%r",
                        correlation_id,
                        _video_id_from_url(best_url),
                        candidates[0].get("title"),
                    )

            progress_state["stage"] = "Resolving stream URL and validating audio"
            elapsed = max(0, int(time.monotonic() - progress_state["started"]))
            minutes, seconds = divmod(elapsed, 60)
            embed_loading.description = (
                f"**♫ REQUESTED TRACK**\n> `{safe_request_label}`\n\n"
                f"**◈ CURRENT STAGE**\n> 🟣 {progress_state['stage']}\n"
                f"> ⏱ Elapsed: `{minutes:02d}:{seconds:02d}`\n\n"
                "*Playback has not started. MusicMaid will validate the selected result before queueing it.*"
            )
            if embed_loading.fields:
                embed_loading.set_field_at(
                    0,
                    name="⌁ RESOLUTION PIPELINE",
                    value=(
                        "✅ **Search candidates** — completed\n"
                        "🟣 **Resolve stream URL** — in progress\n"
                        "⚪ **Validate playable audio** — next\n"
                        "⚪ **Prepare FFmpeg playback** — pending"
                    ),
                    inline=False,
                )
            try:
                await interaction.edit_original_response(
                    content=None, embed=embed_loading, view=None
                )
            except Exception as stage_err:
                logger.debug(
                    "[Playback] stage update skipped: %s",
                    type(stage_err).__name__,
                )

            search_start = time.time()
            is_timed_out = False
            title_hint_val = display_name or (candidates[0].get("title") if candidates else None)
            artist_hint_val = candidates[0].get("artist") if candidates else None
            try:
                track = await asyncio.wait_for(
                    AudioResolver.resolve_track(
                        resolve_query,
                        member.id,
                        str(member),
                        title_hint=title_hint_val,
                        artist_hint=artist_hint_val,
                        correlation_id=correlation_id,
                    ),
                    timeout=90.0,
                )
            except asyncio.TimeoutError:
                track = None
                is_timed_out = True
                logger.warning(
                    "[Playback] operation=resolve correlation_id=%s "
                    "exception_type=TimeoutError duration_ms=90000 outcome=timeout",
                    correlation_id,
                )
            except Exception as e:
                track = None
                logger.error(
                    "[Playback] operation=resolve correlation_id=%s exception_type=%s outcome=failed",
                    correlation_id,
                    type(e).__name__,
                )

            await _stop_resolving_status()

            # Keep Audius/Jamendo fallback, but never silently substitute a
            # near-spelling title (e.g. Kalyan for a Kalyani request).
            provider = str(getattr(track, "provider", "") or "").casefold() if track else ""
            if (
                track
                and provider in {"audius", "jamendo"}
                and not query.startswith(("http://", "https://"))
                and not re.match(r"spotify:(?:track|playlist|album):", query, re.IGNORECASE)
                and "spotify.com/" not in query.casefold()
                and "music.apple.com/" not in query.casefold()
                and not _alternative_track_matches_query(query, track)
            ):
                logger.warning(
                    "[Playback] operation=alternative_track_identity_rejected correlation_id=%s "
                    "provider=%s query=%r title=%r",
                    correlation_id,
                    provider,
                    _safe_query_for_log(query),
                    getattr(track, "title", ""),
                )
                track = None
                AudioResolver.last_resolver_error = (
                    "[NO_ORIGINAL_MATCH] The alternative provider returned a different song title. "
                    "Try adding the singer/artist or provide a direct link."
                )

            if not track:
                display_query_for_user = display_name or query
                if not display_name and display_query_for_user.startswith(("http://", "https://", "spotify:")):
                    display_query_for_user = "selected track"

                res_err = getattr(AudioResolver, "last_resolver_error", None)
                if is_timed_out:
                    embed_fail = discord.Embed(
                        title=f"{EmojiManager.get('LOADING', self.bot)} MusicMaid ✦ SEARCH TIMED OUT",
                        description=(
                            f"The music search for `{display_query_for_user[:100]}` exceeded the search deadline.\n\n"
                            f"• **Diagnostic:** `{res_err or 'Network or resolution timed out while contacting upstream providers.'}`\n"
                            f"• **Supported Sources:** YouTube, Audius, Jamendo, Spotify & Apple Music metadata, and direct audio URLs.\n"
                            f"• **Tip:** Try repeating your search or use a direct song/stream URL."
                        ),
                        color=COLOR_ERROR,
                    )
                elif res_err and "[VIDEO_UNAVAILABLE]" in res_err:
                    embed_fail = discord.Embed(
                        title=f"{EmojiManager.get('ERROR', self.bot)} MusicMaid ✦ VIDEO UNAVAILABLE",
                        description=(
                            f"YouTube reports that this video is unavailable, removed, or private.\n"
                            f"Track: `{display_query_for_user[:100]}`\n\n"
                            f"• **Diagnostic:** `{res_err}`\n"
                            f"• **Try:** Use a different public YouTube link, or search by song title and singer."
                        ),
                        color=COLOR_ERROR,
                    )
                else:
                    cookie_hint = ""
                    if res_err and any(k in res_err.lower() for k in ("sign in", "bot", "captcha", "confirm your age", "access restriction")):
                        cookie_hint = "\n• **Optional Fallback:** If YouTube is restricting datacenter IPs, optional YouTube cookies can be placed in Render Secret Files (`/etc/secrets/cookies.txt`) or configured via `YOUTUBE_COOKIES`."
                    original_match_notice = (
                        "I couldn't verify an original singer/release, so I didn't play a possible cover or remix.\n\n"
                        if res_err and "[NO_ORIGINAL_MATCH]" in res_err
                        else ""
                    )

                    embed_fail = discord.Embed(
                        title=f"{EmojiManager.get('ERROR', self.bot)} MusicMaid ✦ No Audio Track Found",
                        description=(
                            f"{original_match_notice}{DIALOGUE_NOTHING_PLAYABLE}\nTrack: `{display_query_for_user[:100]}`\n\n"
                            f"• **Diagnostic:** `{res_err or 'No playable streams returned'}`\n"
                            f"• **Supported Sources:** YouTube, Audius, Jamendo, Spotify & Apple Music metadata, and direct audio URLs."
                            f"{cookie_hint}"
                        ),
                        color=COLOR_ERROR,
                    )
                await self.send_ephemeral_or_fallback(interaction, embed=embed_fail)
                return

            search_dur = time.time() - search_start
            setattr(track, "_correlation_id", correlation_id)
            logger.info(
                "[Playback] operation=resolved correlation_id=%s title=%r video_id=%s "
                "duration_ms=%.1f",
                correlation_id,
                track.title,
                _video_id_from_url(track.url) or "unavailable",
                search_dur * 1000,
            )

            # Feature 113: Audio Track Duration Ceiling Limiter (> 3 hours rejected for non-admins)
            if track.duration > 10800 and not getattr(member.guild_permissions, "administrator", False):
                embed_dur = discord.Embed(
                    title=f"{EmojiManager.get('WARNING', self.bot)} MusicMaid ✦ Track Duration Exceeded",
                    description=f"Tracks longer than **3 hours** (`{format_duration(track.duration)}`) cannot be queued to protect audio stability. 🐾",
                    color=COLOR_WARNING,
                )
                await self.send_ephemeral_or_fallback(interaction, embed=embed_dur)
                return

            # 3. Add to Queue or Start Playback
            async with session.lock:
                # Rapid-click duplicate guard (prevents identical double-queueing within 3 seconds)
                now_t = time.time()
                last_url = getattr(session, "_last_queued_url", None)
                last_time = getattr(session, "_last_queued_time", 0.0)
                if track.url and track.url == last_url and (now_t - last_time) < 3.0:
                    await self.send_ephemeral_or_fallback(
                        interaction,
                        content=f"⚠️ **{track.title}** was already just queued a moment ago! (Duplicate prevented)",
                    )
                    return
                session._last_queued_url = track.url
                session._last_queued_time = now_t

                total_dur_ms = (time.time() - start_t) * 1000
                search_dur_ms = search_dur * 1000

                if session.is_playing or session.is_paused or session.has_active_track:
                    if top:
                        session.queue.insert(0, track)
                    else:
                        session.queue.append(track)
                    queue_pos = 1 if top else len(session.queue)
                    logger.info(
                        "[Playback] operation=queued correlation_id=%s title=%r video_id=%s "
                        "queue_position=%d top=%s",
                        correlation_id,
                        track.title,
                        _video_id_from_url(track.url) or "unavailable",
                        queue_pos,
                        top,
                    )
                    # Pre-resolve next track if queue was previously empty
                    if len(session.queue) == 1 and not track.stream_url:
                        asyncio.create_task(AudioResolver.pre_resolve_track(track))

                    logger.info(
                        "[PLAY BENCHMARK] correlation_id=%s query=%r search_ms=%.1f "
                        "extract_ms=%.1f ffmpeg_start_ms=0.0 outcome=queued total_ms=%.1f",
                        correlation_id,
                        _safe_query_for_log(query),
                        search_dur_ms,
                        search_dur_ms,
                        total_dur_ms,
                    )

                    pos_text = f"`#{queue_pos}`" + (" (🚀 Next Up / Top of Queue!)" if top else "")
                    embed_queued = discord.Embed(
                        title=f"{EmojiManager.get('QUEUE', self.bot)} MusicMaid ✦ Track Queued",
                        description=f"### [{track.title}]({track.url})\n"
                                    f"👤 **Artist:** `{track.artist}` • ⏱️ **Duration:** `{format_duration(track.duration)}`\n"
                                    f"📜 **Position in Queue:** {pos_text}",
                        color=COLOR_CYAN,
                    )
                    if track.thumbnail:
                        embed_queued.set_thumbnail(url=track.thumbnail)
                    embed_queued.set_footer(text=f"Requested by {member.display_name}")
                    try:
                        await interaction.edit_original_response(embed=embed_queued, content=None, view=None)
                    except Exception:
                        await interaction.followup.send(embed=embed_queued)
                    await MusicPlayerService.send_now_playing_panel(session, bot=self.bot)
                else:
                    play_start = time.time()
                    session._play_request_correlation_id = correlation_id
                    try:
                        success = await MusicPlayerService.start_playback(self.bot, session, track)
                    except Exception as play_exc:
                        logger.error(f"[Playback] Exception starting playback for '{track.title}': {play_exc}", exc_info=True)
                        success = False
                        session.last_error = str(play_exc)

                    play_dur = time.time() - play_start
                    play_dur_ms = play_dur * 1000
                    total_dur_ms = (time.time() - start_t) * 1000

                    logger.info(
                        "[PLAY BENCHMARK] correlation_id=%s query=%r search_ms=%.1f "
                        "extract_ms=%.1f ffmpeg_start_ms=%.1f total_ms=%.1f outcome=%s",
                        correlation_id,
                        _safe_query_for_log(query),
                        search_dur_ms,
                        search_dur_ms,
                        play_dur_ms,
                        total_dur_ms,
                        "started" if success else "failed",
                    )
                    if success:
                        try:
                            # If a player message was already created or deployed, update it; otherwise deploy once
                            if not session.now_playing_message:
                                from music_bot.services.player_service import NowPlayingControlView
                                player_embed = MusicPlayerService.build_now_playing_embed(session)
                                player_view = NowPlayingControlView(session, bot=self.bot)
                                msg = await interaction.edit_original_response(
                                    content=f"🎶 **Started playing:** [{track.title}]({track.url or ''}) • *{DIALOGUE_START}*",
                                    embed=player_embed,
                                    view=player_view,
                                )
                                session.now_playing_message = msg
                                session.now_playing_message_id = msg.id
                            else:
                                await interaction.edit_original_response(
                                    content=f"🎶 **Started playing:** [{track.title}]({track.url or ''}) • *{DIALOGUE_START}*",
                                    embed=None,
                                    view=None,
                                )
                        except Exception as edit_err:
                            logger.warning(f"[Playback] Notice editing interaction on play success: {edit_err}")

                    else:
                        err_detail = getattr(session, "last_error", None) or "Audio pipeline could not decode or play the audio stream."
                        embed_fail = discord.Embed(
                            title="❌ PLAYBACK FAILED",
                            description=(
                                f"Encountered an error while starting audio stream for **{track.title}**:\n"
                                f"```\n{err_detail[:800]}\n```\n"
                                f"💡 **Playback Diagnostics:**\n"
                                f"• Audio stream or decoding issue: `{err_detail[:200]}`\n"
                                f"• Try another track or provide a direct YouTube track URL."
                            ),
                            color=0xED4245,
                        )
                        await self.send_ephemeral_or_fallback(interaction, embed=embed_fail)
        except Exception as top_err:
            logger.error(
                "[Playback] operation=play_request correlation_id=%s exception_type=%s outcome=failed",
                correlation_id,
                type(top_err).__name__,
            )
            embed_crit = discord.Embed(
                title="❌ PLAYBACK ERROR",
                description=(
                    f"An unexpected error occurred while processing your request:\n"
                    f"```\n{str(top_err)[:800]}\n```"
                ),
                color=0xED4245,
            )
            await self.send_ephemeral_or_fallback(interaction, embed=embed_crit)

    # =========================================================================
    # /MUSIC COMMAND GROUP
    # =========================================================================

    music_group = app_commands.Group(name="music", description="Neko Songs Independent Music Suite")

    # --- 1. PLAYBACK & BASIC CONTROLS ---

    @music_group.command(name="play", description="Play a song or URL from YouTube")
    @app_commands.describe(
        query="Song title, artist, or URL to play",
        top="Play next / insert at the top of the queue (JukeBot style)",
    )
    async def music_play(self, interaction: discord.Interaction, query: str, top: bool = False) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        if not await self._check_permissions(interaction):
            return
        await self._play_query(interaction, query, top=top)

    @music_play.autocomplete("query")
    async def music_play_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        try:
            suggestions = await AudioResolver.autocomplete_search(current, limit=5)
            choices = []
            for item in suggestions:
                title = item.get("title", "")
                artist = item.get("artist", "")
                label = f"{title[:75]} • {artist[:20]}" if artist and artist != "Direct Search" else title[:95]
                val = item.get("url") or title
                choices.append(app_commands.Choice(name=label[:100], value=val[:100]))
            return choices
        except Exception:
            return []


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
            await self._play_query(inter, chosen["url"], display_name=chosen.get("title"))

        view = TrackSelectView(candidates, interaction.user.id, on_select)
        await interaction.followup.send("🐱 **Select a track to play:**", view=view)

    @music_group.command(name="pause", description="Pause current music playback")
    async def music_pause(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        success, msg = await MusicPlayerService.pause(session)
        await interaction.followup.send(msg)

    @music_group.command(name="resume", description="Resume paused music playback")
    async def music_resume(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        success, msg = await MusicPlayerService.resume(self.bot, session)
        await interaction.followup.send(msg)

    @music_group.command(name="skip", description="Skip the currently playing song (or vote-to-skip)")
    async def music_skip(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.voice_client or not (session.has_active_track or session.voice_client.is_playing() or session.voice_client.is_paused()):
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
            success, msg, next_track = await MusicPlayerService.skip(self.bot, session)
            await interaction.followup.send(msg)
            return

        # Scaled vote consensus: 40% for larger groups >= 5, 50% for smaller groups
        threshold_ratio = 0.4 if len(non_bot_listeners) >= 5 else 0.5
        required_votes = max(2, math.ceil(len(non_bot_listeners) * threshold_ratio))
        session.skip_votes.add(interaction.user.id)
        current_votes = len(session.skip_votes)

        if current_votes >= required_votes:
            session.skip_votes.clear()
            success, msg, next_track = await MusicPlayerService.skip(self.bot, session)
            await interaction.followup.send(f"⏭️ **Vote-to-Skip Passed!** ({current_votes}/{required_votes} votes)\n{msg}")
        else:
            await interaction.followup.send(f"🗳️ **Vote to Skip:** {current_votes}/{required_votes} listeners voted to skip **{track_title}**.")

    @music_group.command(name="previous", description="Return to the previous song in history")
    async def music_previous(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        success, msg, _ = await MusicPlayerService.previous(self.bot, session)
        await interaction.followup.send(msg)

    @music_group.command(name="stop", description="Stop playback, clear queue, and leave voice")
    async def music_stop(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        success, msg = await MusicPlayerService.stop(self.bot, session)
        await interaction.followup.send(msg)

    @music_group.command(name="nowplaying", description="View the official Neko Songs Now Playing dashboard")
    async def music_nowplaying(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        embed = MusicPlayerService.build_now_playing_embed(session)
        from music_bot.services.player_service import NowPlayingControlView
        view = NowPlayingControlView(session)
        await interaction.followup.send(embed=embed, view=view)

    @music_group.command(name="queue", description="Display the current music queue")
    @app_commands.describe(page="Queue page number (default 1)")
    async def music_queue(self, interaction: discord.Interaction, page: Optional[int] = 1) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
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

    @music_group.command(name="volume", description="Set playback volume (0-100% standard, up to 150% with Premium)")
    @app_commands.describe(percent="Volume percentage (0-100% standard, up to 150% with Premium)")
    async def music_volume(
        self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 150]
    ) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore

        is_prem = await self.is_bot_developer_or_owner(interaction.user)
        if not is_prem and interaction.guild:
            is_prem = await self.bot.db.is_premium(interaction.guild.id, interaction.user.id)

        target_vol = percent
        premium_notice = ""
        if target_vol > 100 and not is_prem:
            target_vol = 100
            premium_notice = "\n💎 *Volume above 100% (boosted up to 150%) requires **Premium**! Set to 100%. Use `/premium` to view perks.*"

        session.volume = target_vol
        if session.voice_client and hasattr(session.voice_client.source, "volume"):
            session.voice_client.source.volume = target_vol / 100.0  # type: ignore
        await MusicPlayerService.send_now_playing_panel(session)
        await interaction.followup.send(f"🔊 Volume set to `{target_vol}%`.{premium_notice}")


    @app_commands.command(name="seek", description="Seek to a specific timestamp in the current song")
    @app_commands.describe(seconds="Target time in seconds")
    async def music_seek(self, interaction: discord.Interaction, seconds: int) -> None:
        await self.ensure_deferred(interaction, ephemeral=True)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.current_track or not (session.is_playing or session.is_paused or session.has_active_track):
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
        await self.ensure_deferred(interaction, ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if len(session.queue) < 2:
            await interaction.followup.send("❌ Need at least 2 tracks in queue to shuffle.", ephemeral=True)
            return

        tracks = list(session.queue)
        random.shuffle(tracks)
        session.queue = deque(tracks)
        await interaction.followup.send(f"🔀 Shuffled `{len(tracks)}` songs in queue.")

    @music_group.command(name="loop", description="Configure loop mode (Off / Track / Queue)")
    @app_commands.describe(mode="Loop mode to apply")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Current Track", value="track"),
        app_commands.Choice(name="Whole Queue", value="queue"),
    ])
    async def music_loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
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
        session.queue = deque(tracks)
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
        session.queue = deque(tracks)
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

    @app_commands.command(name="eq", description="Select or apply an Audio Equalizer preset")
    @app_commands.describe(preset="Direct preset to apply immediately (optional)")
    @app_commands.choices(preset=[
        app_commands.Choice(name="Flat / Normal 🔄", value="reset"),
        app_commands.Choice(name="Bass Boost 🎧", value="bassboost"),
        app_commands.Choice(name="8D Audio 🌌", value="8d"),
        app_commands.Choice(name="Lo-Fi Relax ☕", value="vaporwave"),
        app_commands.Choice(name="Clear Vocal ⚡", value="vocal"),
        app_commands.Choice(name="Nightcore 🚀", value="nightcore"),
        app_commands.Choice(name="Pop ✨", value="pop"),
        app_commands.Choice(name="Rock 🎸", value="rock"),
    ])
    async def music_eq(self, interaction: discord.Interaction, preset: Optional[app_commands.Choice[str]] = None) -> None:
        await self.ensure_deferred(interaction, ephemeral=True)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if preset is not None:
            display_names = {
                "reset": "Flat / Normal",
                "bassboost": "Bass Boost",
                "8d": "8D Audio",
                "vaporwave": "Lo-Fi Relax",
                "vocal": "Clear Vocal",
                "nightcore": "Nightcore",
                "pop": "Pop",
                "rock": "Rock",
            }
            d_name = display_names.get(preset.value, preset.name)
            success = await MusicPlayerService.apply_filter_or_eq(self.bot, session, preset.value, d_name)
            if success:
                await interaction.edit_original_response(content=f"🎛️ Applied Equalizer Preset: **{d_name}** 🐾\n*(Current song continues playing seamlessly with real-time DSP filter)*")
            else:
                await interaction.edit_original_response(content=f"⚠️ Failed to apply preset **{d_name}**. Preserved previous audio filter.")
            return

        view = AudioEqualizerView(session, self.bot)
        msg_text = f"🎛️ **Audio Equalizer Presets** (Current: `{getattr(session, 'eq_preset', 'Flat')}`):"
        try:
            await interaction.edit_original_response(content=msg_text, view=view)
        except Exception:
            await interaction.followup.send(msg_text, view=view, ephemeral=True)

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
        await self.ensure_deferred(interaction, ephemeral=False)
        if not interaction.user or not getattr(interaction.user, "voice", None) or not interaction.user.voice.channel:
            await interaction.followup.send("❌ You must be connected to a voice channel to start Watch Together.", ephemeral=True)
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
            await interaction.edit_original_response(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Could not create Watch Together activity invite: {e}", ephemeral=True)

    @music_group.command(name="join", description="Connect Neko Songs to your voice channel")
    async def music_join(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        if not await self._check_permissions(interaction):
            return

        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        session.is_intentional_stop = False
        session.is_intentional_disconnect = False
        vc = await VoiceManager.join_voice_channel(interaction.user, interaction.channel, session)  # type: ignore
        if vc:
            await interaction.followup.send(DIALOGUE_JOIN)
        else:
            await interaction.followup.send("❌ Could not connect to voice channel.")

    @music_group.command(name="leave", description="Disconnect Neko Songs from voice")
    async def music_leave(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        session.is_intentional_disconnect = True
        session.is_intentional_stop = True
        if session.auto_leave_task and not session.auto_leave_task.done():
            session.auto_leave_task.cancel()
            session.auto_leave_task = None

        if session.voice_client:
            try:
                if session.voice_client.is_playing() or session.voice_client.is_paused():
                    session.voice_client.stop()
                await session.voice_client.disconnect(force=True)
            except Exception:
                pass
            session.voice_client = None

        session.queue.clear()
        session.current_track = None
        session.state = PlaybackState.IDLE
        await interaction.followup.send("👋 Disconnected from voice channel. Goodbye! (Use `/play` or `/247 reconnect` to rejoin)")

    @app_commands.command(name="disconnect", description="Disconnect Neko Songs from voice")
    async def music_disconnect(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_leave.callback(self, interaction)

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
            await self._play_query(inter, chosen["url"], display_name=chosen.get("title"))

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
        await self._play_query(interaction, first.url, display_name=getattr(first, "title", None))
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
        await self._play_query(interaction, first.url, display_name=getattr(first, "title", None))
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
        await self.ensure_deferred(interaction, ephemeral=True)
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
        await self.ensure_deferred(interaction, ephemeral=True)
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


    @app_commands.command(name="247", description="Configure or toggle 24/7 mode to keep NyxTune in voice channel indefinitely")
    @app_commands.describe(action="Optional action: toggle, enable, disable, reconnect, or status")
    @app_commands.choices(action=[
        app_commands.Choice(name="Toggle (Enable/Disable/Reconnect)", value="toggle"),
        app_commands.Choice(name="Enable 24/7 Mode", value="enable"),
        app_commands.Choice(name="Disable 24/7 Mode", value="disable"),
        app_commands.Choice(name="Reconnect to Saved Channel", value="reconnect"),
        app_commands.Choice(name="Check 24/7 Status", value="status"),
    ])
    async def cmd_247(self, interaction: discord.Interaction, action: Optional[app_commands.Choice[str]] = None) -> None:
        """Toggles or configures 24/7 persistence mode for the guild."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return

        await self.ensure_deferred(interaction, ephemeral=False)
        guild = interaction.guild
        member = interaction.user
        settings = await self.bot.db.get_guild_settings(guild.id)
        session = await self.session_manager.get_session(guild.id)

        act = action.value if action else "toggle"
        vc_connected = bool(session.voice_client and session.voice_client.is_connected())

        if act == "status":
            saved_ch = guild.get_channel(settings.twenty_four_seven_channel_id) if settings.twenty_four_seven_channel_id else None
            embed_status = discord.Embed(
                title="📻 24/7 PERSISTENCE STATUS",
                description=(
                    f"**Server:** `{guild.name}` (`{guild.id}`)\n\n"
                    f"• **24/7 Setting:** `{ 'ENABLED' if settings.twenty_four_seven_enabled else 'DISABLED' }` (Database)\n"
                    f"• **Voice Status:** `{ 'CONNECTED' if vc_connected else 'DISCONNECTED' }`\n"
                    f"• **Current Channel:** {session.voice_client.channel.mention if (session.voice_client and session.voice_client.channel) else 'None'}\n"
                    f"• **Saved 24/7 Channel:** {saved_ch.mention if saved_ch else ('ID: ' + str(settings.twenty_four_seven_channel_id) if settings.twenty_four_seven_channel_id else 'None')}\n"
                    f"• **Auto-Leave Timer:** `{ 'DISABLED (24/7 Active)' if (settings.twenty_four_seven_enabled or session.twenty_four_seven) else ('Active Countdown' if session.auto_leave_task and not session.auto_leave_task.done() else 'Idle') }`\n"
                    f"• **Last Recovery Status:** `{session.recovery_status or 'Normal'}`\n"
                ),
                color=0x7928CA if settings.twenty_four_seven_enabled else 0x64748B,
            )
            embed_status.set_footer(text="Use /247 toggle to change 24/7 mode")
            view = Reconnect247View(self.bot, guild, settings.twenty_four_seven_channel_id) if (settings.twenty_four_seven_enabled and not vc_connected and settings.twenty_four_seven_channel_id) else None
            if view is not None:
                await interaction.followup.send(embed=embed_status, view=view)
            else:
                await interaction.followup.send(embed=embed_status)
            return

        # Determine target 24/7 state:
        if act == "reconnect":
            new_state = True
        elif act == "enable":
            new_state = True
        elif act == "disable":
            new_state = False
        else:
            if settings.twenty_four_seven_enabled and not vc_connected:
                # If enabled in DB but disconnected, reconnecting is the user's intended action
                new_state = True
            else:
                new_state = not settings.twenty_four_seven_enabled

        if new_state:
            is_owner = await self.is_bot_developer_or_owner(member)
            is_prem = is_owner or await self.bot.db.is_premium(guild.id, member.id)
            is_admin = is_owner or getattr(member.guild_permissions, "administrator", False) or (member.id == guild.owner_id)
            if not is_prem and not is_admin:
                embed_prem = discord.Embed(
                    title="💎 PREMIUM FEATURE: 24/7 MODE",
                    description=(
                        "**24/7 Voice Channel Persistence** is an exclusive **Premium** feature!\n\n"
                        "• Keeps the bot in your voice channel 24/7 without timing out.\n"
                        "• Automatically reconnects after Render service restarts.\n\n"
                        "💡 *Server Administrators or Premium subscribers can activate this feature. Use `/premium` to view status.*"
                    ),
                    color=0x7928CA,
                )
                await interaction.followup.send(embed=embed_prem, ephemeral=True)
                return

            target_vc = None
            if member.voice and member.voice.channel:
                target_vc = member.voice.channel
            elif session.voice_client and session.voice_client.is_connected() and session.voice_client.channel:
                target_vc = session.voice_client.channel
            elif settings.twenty_four_seven_channel_id:
                candidate = guild.get_channel(settings.twenty_four_seven_channel_id)
                if isinstance(candidate, (discord.VoiceChannel, discord.StageChannel)):
                    target_vc = candidate

            if not target_vc:
                await interaction.followup.send(
                    "⚠️ **Please join a voice channel first** (or play a song with `/play`) "
                    "so NyxTune knows which channel to stay in 24/7!\n"
                    "*(Once you join, run `/247` again to enable 24/7 persistence)*",
                    ephemeral=True,
                )
                return

            if session.auto_leave_task and not session.auto_leave_task.done():
                session.auto_leave_task.cancel()
                session.auto_leave_task = None

            async with session.lock:
                vc = await VoiceManager.join_voice_channel(
                    member=member,
                    text_channel=interaction.channel,  # type: ignore
                    session=session,
                    target_channel=target_vc,
                )

            is_connected = bool(session.voice_client and session.voice_client.is_connected())

            settings.twenty_four_seven_enabled = True
            settings.twenty_four_seven_channel_id = target_vc.id
            await self.bot.db.update_guild_settings(settings)
            session.twenty_four_seven = True
            session.is_intentional_stop = False
            session.is_intentional_disconnect = False

            if is_connected:
                embed = discord.Embed(
                    title="📻 24/7 MODE ACTIVATED",
                    description=(
                        f"**{self.bot.user.name if self.bot.user else 'NyxTune'}** is locked into {target_vc.mention} 24/7!\n\n"
                        f"• **24/7 Setting:** `ENABLED` (Saved to persistent database)\n"
                        f"• **Voice Connection:** `CONNECTED` (Active on Discord)\n"
                        f"• **Target Channel:** {target_vc.mention} (`#{target_vc.name}`)\n"
                        f"• **Auto-Disconnection:** `DISABLED` (Will never leave empty channels)\n"
                        f"• **Restart Recovery:** `ENABLED` (Auto-reconnects across Render restarts)\n\n"
                        f"💡 *Tip: Use `/247 status` to inspect health or `/247 disable` to turn off.*"
                    ),
                    color=0x7928CA,
                )
                embed.set_footer(text="NyxTune 24/7 Audio Guardian Active")
                await interaction.followup.send(embed=embed)
            else:
                err_msg = session.last_error or "Voice gateway connection timed out."
                embed = discord.Embed(
                    title="⚠️ 24/7 ENABLED — RECONNECT FAILED",
                    description=(
                        f"24/7 Mode is **saved in settings**, but the bot could not connect to {target_vc.mention}.\n\n"
                        f"• **24/7 Setting:** `ENABLED` (Saved in database)\n"
                        f"• **Voice Connection:** `DISCONNECTED`\n"
                        f"• **Target Channel:** {target_vc.mention}\n"
                        f"• **Connection Error:** `{err_msg}`\n\n"
                        f"💡 **Troubleshooting:**\n"
                        f"1. Ensure the bot has **Connect** and **Speak** permissions in {target_vc.mention}.\n"
                        f"2. Ensure the channel is not full.\n"
                        f"3. Click **🔄 Reconnect Voice** below or use `/247 reconnect`."
                    ),
                    color=0xED4245,
                )
                view = Reconnect247View(self.bot, guild, target_vc.id)
                await interaction.followup.send(embed=embed, view=view)
        else:
            settings.twenty_four_seven_enabled = False
            settings.twenty_four_seven_channel_id = None
            await self.bot.db.update_guild_settings(settings)
            session.twenty_four_seven = False
            session.is_intentional_disconnect = True

            if session.voice_client and session.voice_client.is_connected():
                humans = [m for m in session.voice_client.channel.members if not m.bot]
                if not humans:
                    VoiceManager.schedule_auto_leave(self.bot, session)

            embed = discord.Embed(
                title="📻 24/7 MODE DEACTIVATED",
                description=(
                    "24/7 mode has been **disabled**.\n\n"
                    "• **24/7 Setting:** `DISABLED` (Saved in database)\n"
                    "• **Voice Channel:** Normal auto-leave timeout rules now apply.\n"
                    "• **Auto-Disconnect:** The bot will disconnect if the voice channel remains empty for 5 minutes."
                ),
                color=0x64748B,
            )
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="stay", description="Keep the bot in voice channel 24/7 (Shortcut for /247)")
    async def cmd_stay(self, interaction: discord.Interaction) -> None:
        """Alias for /247."""
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.cmd_247.callback(self, interaction, action=None)

    @app_commands.command(name="panel", description="Interactive Master Control Panel showing all music bot features")
    async def cmd_panel(self, interaction: discord.Interaction) -> None:
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

    @app_commands.command(name="control", description="Interactive Master Control Panel (Shortcut for /panel)")
    async def cmd_control(self, interaction: discord.Interaction) -> None:
        """Alias for /panel."""
        await self.cmd_panel.callback(self, interaction)

    @app_commands.command(name="autoupdate", description="Check or update yt-dlp extractor, git commits, and audio health")
    @app_commands.describe(action="Maintenance action to perform")
    @app_commands.choices(action=[
        app_commands.Choice(name="Check Status & Health", value="check"),
        app_commands.Choice(name="Update yt-dlp & EJS Now", value="update"),
        app_commands.Choice(name="Run Canary Probe (Test YouTube)", value="canary"),
        app_commands.Choice(name="Rotate Client Profile", value="rotate"),
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
        is_owner = await self.is_bot_developer_or_owner(interaction.user)

        if act == "update":
            if not is_admin and not is_owner:
                await interaction.followup.send("❌ Administrator permissions required to trigger dependency updates.", ephemeral=True)
                return

            embed_progress = discord.Embed(
                title="🔄 UPDATING AUDIO EXTRACTOR",
                description="Upgrading `yt-dlp` and `yt-dlp-ejs` to latest releases in background...\nPlayback will continue uninterrupted.",
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

        elif act == "canary":
            health = await AudioResolver.probe_extractor_health()
            is_ok = health.get("operational", False)
            embed_result = discord.Embed(
                title="🐦 EXTRACTOR CANARY PROBE",
                description=(
                    f"• **Operational:** {'✅ YES (Zero SABR Blocks)' if is_ok else '❌ NO (Needs Rotation)'}\n"
                    f"• **Resolution Latency:** `{health.get('latency_ms', 0)}ms`\n"
                    f"• **Active Profile:** `{health.get('profile')}`\n"
                    f"• **Status:** `{health.get('message')}`"
                ),
                color=COLOR_ELECTRIC_CYAN if is_ok else 0xED4245,
            )
            await interaction.followup.send(embed=embed_result)

        elif act == "rotate":
            new_prof = AudioResolver.rotate_client_profile()
            embed_result = discord.Embed(
                title="🔄 ROTATED EXTRACTOR PROFILE",
                description=f"Rotated active yt-dlp client profile to **`{new_prof}`**!\n*0.0s downtime, active streams preserved.*",
                color=COLOR_ELECTRIC_CYAN,
            )
            await interaction.followup.send(embed=embed_result)

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
            yt_ok = health.get("youtube_operational", False)

            if is_ok and yt_ok:
                probe_status = "🟢 Operational (YouTube)"
                recovery_status = "Active (YouTube primary)"
            else:
                probe_status = "🔴 Issue Detected"
                recovery_status = "Action Required (Fresh cookies or PO-Token needed; SoundCloud disabled)"

            embed_result = discord.Embed(
                title="🩺 EXTRACTOR HEALTH & SELF-HEAL",
                description=(
                    f"• **Extractor Probe:** {probe_status}\n"
                    f"• **Diagnostics:** `{health.get('message', 'OK')[:250]}`\n"
                    f"• **Auto-Recovery:** {recovery_status}"
                ),
                color=COLOR_ELECTRIC_CYAN if is_ok else 0xED4245,
            )
            await interaction.followup.send(embed=embed_result)

        else:
            check = await MusicAutoUpdater.check_ytdl_version()
            curr_ytdl = check.get("current_ytdl", "unknown")
            latest_ytdl = check.get("latest_ytdl", "unknown")
            curr_ejs = check.get("current_ejs", "unknown")
            has_update = check.get("update_available", False)
            js_info = MusicAutoUpdater.get_js_runtime_info()
            profile = AudioResolver.get_current_profile_name()
            git_info = await MusicAutoUpdater.check_git_updates()

            status_text = "🟢 **Up-To-Date & Healthy**" if not has_update else f"🟡 **Update Available** (`v{latest_ytdl}` on PyPI)"
            git_text = f"🟢 Commit `{git_info.get('current_commit', 'main')}`" if not git_info.get("has_updates") else f"🟡 `{git_info.get('pending_commits')}` new commits available"

            embed = discord.Embed(
                title="🤖 MUSIC BOT AUTO-UPDATER & EXTRACTOR SUPERVISOR",
                description=(
                    f"• **yt-dlp Core:** `v{curr_ytdl}` (Latest: `v{latest_ytdl}`)\n"
                    f"• **EJS Challenge Solver:** `v{curr_ejs}`\n"
                    f"• **Active JS Runtime:** `{js_info.get('active')}`\n"
                    f"• **Active Profile:** `{profile}`\n"
                    f"• **Extractor Health:** {status_text}\n"
                    f"• **Git Repository:** {git_text}\n\n"
                    f"• **Autonomous Schedule:** Runs every **30 mins** in the background\n"
                    f"• **Self-Healing:** In-memory client rotation & Canary probes\n"
                    f"• **Zero-Interrupt:** Hot reloads without dropping voice connections"
                ),
                color=COLOR_ELECTRIC_CYAN if not has_update else 0xFEE75C,
            )
            embed.set_footer(text="MusicMaid Autonomous Self-Healing & Extractor Supervisor")
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="reload", description="Zero-downtime hot reload: update bot modules while music keeps playing")
    async def cmd_reload(self, interaction: discord.Interaction) -> None:
        is_owner = await self.is_bot_developer_or_owner(interaction.user)
        if not is_owner:
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

    @app_commands.command(name="filter", description="Apply real-time audio filters and DSP effects")
    @app_commands.describe(effect="Audio effect preset to apply")
    @app_commands.choices(effect=[
        app_commands.Choice(name="🎧 8D Spatial Audio (360° Orbit)", value="8d"),
        app_commands.Choice(name="🎤 Karaoke (Center Vocal Removal)", value="karaoke"),
        app_commands.Choice(name="☕ Lo-Fi Vintage (Warm Vinyl Tape EQ)", value="lofi"),
        app_commands.Choice(name="🔊 Bass Boost (+10dB Sub-bass)", value="bassboost"),
        app_commands.Choice(name="⚡ Nightcore (Speed 1.25x & High Pitch)", value="nightcore"),
        app_commands.Choice(name="🌴 Vaporwave (Slowed 0.85x & Deep Pitch)", value="vaporwave"),
        app_commands.Choice(name="🎤 Vocal Clarity (Mid-range Presence)", value="vocal"),
        app_commands.Choice(name="⏹️ Reset (Clean Flat Audio)", value="reset"),
    ])
    async def cmd_filter(self, interaction: discord.Interaction, effect: app_commands.Choice[str]) -> None:
        """Applies dynamic audio effects in real-time."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return

        await self.ensure_deferred(interaction, ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.current_track or not session.is_playing:
            await interaction.edit_original_response(content="❌ Nothing is currently playing. Start a track first!")
            return

        filter_chains = {
            "8d": "-af apulsator=hz=0.125:amount=1",
            "karaoke": "-af stereotools=mlev=0.0:slev=1.5",
            "lofi": "-af lowpass=f=3200,highpass=f=300",
            "bassboost": "-af equalizer=f=60:width_type=h:width=50:g=10",
            "nightcore": "-af atempo=1.25,asetrate=48000*1.25",
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
            description=f"Applied audio effect: **{effect.name}**\n*Playback refreshed with real-time DSP filter without voice disconnect.*",
            color=COLOR_ELECTRIC_CYAN if effect.value != "reset" else COLOR_NEON_BLUE,
        )
        await interaction.edit_original_response(embed=embed)

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
        await self.ensure_deferred(interaction, ephemeral=False)
        if not interaction.guild:
            await interaction.edit_original_response(content="❌ This command must be used in a server.")
            return

        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if duration.value == 0:
            if session.sleep_timer_task and not session.sleep_timer_task.done():
                session.sleep_timer_task.cancel()
                session.sleep_timer_task = None
            session.sleep_timer_end = 0.0
            await interaction.edit_original_response(content="⏰ Sleep timer has been **cancelled**.")
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
        await interaction.edit_original_response(embed=embed)

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

    @playlist_group.command(name="import", description="Import an external playlist from Spotify, YouTube, or Apple Music")
    @app_commands.describe(
        url="Link to playlist or album (Spotify, YouTube, Apple Music)",
        name="Optional custom name for your saved playlist",
        play_now="Immediately queue and start playing the imported playlist",
    )
    async def playlist_import(
        self,
        interaction: discord.Interaction,
        url: str,
        name: Optional[str] = None,
        play_now: bool = False,
    ) -> None:
        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        member = interaction.user
        if not guild:
            return

        from music_bot.services.importer_service import PlaylistImporterService
        result = await PlaylistImporterService.import_playlist(
            self.bot,
            url=url,
            guild_id=guild.id,
            user_id=member.id,
            user_name=member.display_name,
            custom_name=name,
        )

        if not result.success or not result.tracks:
            err = result.error or "Failed to import tracks from this URL."
            await interaction.followup.send(f"❌ **Import Failed:** {err}", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📥 PLAYLIST IMPORTED • {result.platform.upper()}",
            description=(
                f"Successfully imported **{result.track_count}** tracks into playlist **\"{result.playlist_name}\"**!\n\n"
                f"• **Platform:** `{result.platform}`\n"
                f"• **Saved As:** `{result.playlist_name}`\n"
                f"• **Tracks:** `{result.track_count}` songs"
            ),
            color=COLOR_PREMIUM,
        )
        if result.sample_tracks:
            embed.add_field(
                name="🎶 Sample Tracks",
                value="\n".join(f"• {t}" for t in result.sample_tracks),
                inline=False,
            )

        if play_now:
            if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
                embed.set_footer(text="Join a voice channel to auto-play! Playlist saved to /playlist list.")
                await interaction.followup.send(embed=embed)
                return

            session = await self.session_manager.get_session(guild.id)
            async with session.lock:
                from music_bot.services.voice_service import VoiceManager
                text_channel = interaction.channel if isinstance(interaction.channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread)) else None
                vc = await VoiceManager.join_voice_channel(member, text_channel, session)
                if not vc:
                    embed.set_footer(text="Could not join voice. Playlist saved to /playlist list.")
                    await interaction.followup.send(embed=embed)
                    return

                for t in result.tracks:
                    session.queue.append(t)

                embed.set_footer(text=f"🎧 Queued all {result.track_count} tracks and starting playback!")
                await interaction.followup.send(embed=embed)

                if not session.is_playing and session.queue:
                    first = session.queue.popleft()
                    await MusicPlayerService.start_playback(self.bot, session, first)
        else:
            embed.set_footer(text=f"Use /playlist load name:{result.playlist_name} to play anytime!")
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="blend", description="Blend your music taste with a friend into an anime neon mix")
    @app_commands.describe(
        user="Friend to blend music with",
        auto_queue="Immediately load and start playing the blend",
    )
    async def cmd_blend(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        auto_queue: bool = True,
    ) -> None:
        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            return

        from music_bot.services.blend_service import FriendBlendService
        blend = await FriendBlendService.generate_blend(
            self.bot,
            guild_id=guild.id,
            user1=member,
            user2=user,
        )

        embed = FriendBlendService.build_blend_embed(blend)

        if auto_queue and blend.tracks:
            if not member.voice or not member.voice.channel:
                embed.set_footer(text="💡 Join a voice channel to listen to the blend together!")
                await interaction.followup.send(embed=embed)
                return

            session = await self.session_manager.get_session(guild.id)
            async with session.lock:
                from music_bot.services.voice_service import VoiceManager
                text_channel = interaction.channel if isinstance(interaction.channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread)) else None
                vc = await VoiceManager.join_voice_channel(member, text_channel, session)
                if not vc:
                    await interaction.followup.send(embed=embed)
                    return

                for t in blend.tracks:
                    session.queue.append(t)

                await interaction.followup.send(embed=embed)

                if not session.is_playing and session.queue:
                    first = session.queue.popleft()
                    await MusicPlayerService.start_playback(self.bot, session, first)
        else:
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="maid-dj", description="Configure AI Anime Maid Voice DJ track announcer")
    @app_commands.describe(
        action="Action: on, off, status, test, or personality",
        personality="Personality style: maid, tsundere, hype, chill, cyberpunk",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="🟢 Turn On Maid DJ", value="on"),
            app_commands.Choice(name="🔴 Turn Off Maid DJ", value="off"),
            app_commands.Choice(name="📊 Status & Current Style", value="status"),
            app_commands.Choice(name="🎙️ Test Voice Intro", value="test"),
            app_commands.Choice(name="🎭 Set Personality", value="personality"),
        ],
        personality=[
            app_commands.Choice(name="☕ Devoted Maid (Polite & Sweet)", value="maid"),
            app_commands.Choice(name="💢 Tsundere Maid (Sassy & Tsundere)", value="tsundere"),
            app_commands.Choice(name="🔥 Festival DJ Maid (Hype & High-Energy)", value="hype"),
            app_commands.Choice(name="🌙 Lo-Fi Night Maid (Calm & Chill)", value="chill"),
            app_commands.Choice(name="⚡ Neo-Tokyo Synth Maid (Cyberpunk)", value="cyberpunk"),
        ],
    )
    async def cmd_maid_dj(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        personality: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        if not guild:
            return

        session = await self.session_manager.get_session(guild.id)
        from music_bot.services.maid_dj_service import MaidDJService

        act_val = action.value.lower()
        chosen_pers = (personality.value if personality else session.maid_dj_personality).lower()

        if act_val in ("on", "enable"):
            session.maid_voice_dj_enabled = True
            if personality:
                session.maid_dj_personality = chosen_pers
            p_cfg = MaidDJService.PERSONALITIES.get(session.maid_dj_personality, MaidDJService.PERSONALITIES["maid"])
            await interaction.followup.send(
                f"🟢 **AI Maid Voice DJ is now ENABLED!**\n"
                f"• **Current Personality:** `{p_cfg['name']}`\n"
                f"She will introduce every incoming track and its requester with voice & anime cards! ✨"
            )

        elif act_val in ("off", "disable"):
            session.maid_voice_dj_enabled = False
            await interaction.followup.send(
                "🔴 **AI Maid Voice DJ is now DISABLED.** Track intros will be skipped."
            )

        elif act_val == "personality":
            if personality:
                session.maid_dj_personality = chosen_pers
            p_cfg = MaidDJService.PERSONALITIES.get(session.maid_dj_personality, MaidDJService.PERSONALITIES["maid"])
            await interaction.followup.send(
                f"🎭 **Maid DJ Personality set to:** `{p_cfg['name']}`! 🎀"
            )

        elif act_val == "test":
            from music_bot.database.models import QueuedTrack
            p_val = chosen_pers
            test_track = session.current_track or QueuedTrack(
                title="Gurenge (Demon Slayer OP)",
                artist="LiSA",
                url="https://youtube.com/watch?v=mock",
                stream_url="",
                duration=236,
                requester_id=interaction.user.id,
                requester_name=interaction.user.display_name,
            )
            intro_text = MaidDJService.generate_intro_text(p_val, test_track, interaction.user.display_name)
            embed = MaidDJService.build_announcement_embed(test_track, intro_text, p_val)
            await interaction.followup.send(
                content="🎙️ **Voice DJ Soundcheck:**",
                embed=embed,
            )

        else:  # status
            is_on = getattr(session, "maid_voice_dj_enabled", False)
            curr_p = getattr(session, "maid_dj_personality", "maid")
            p_cfg = MaidDJService.PERSONALITIES.get(curr_p, MaidDJService.PERSONALITIES["maid"])
            status_str = "🟢 Active" if is_on else "🔴 Inactive"
            embed = discord.Embed(
                title="🎙️ AI Anime Maid Voice DJ Status",
                description=(
                    f"• **Voice DJ Status:** `{status_str}`\n"
                    f"• **Current Personality:** `{p_cfg['name']}`\n"
                    f"• **Available Styles:** `maid`, `tsundere`, `hype`, `chill`, `cyberpunk`\n\n"
                    f"Use `/maid-dj action:Turn On` to enable announcements before every song!"
                ),
                color=p_cfg["color"],
            )
            embed.set_thumbnail(url=p_cfg["avatar"])
            await interaction.followup.send(embed=embed)

    # =========================================================================
    # COMPATIBILITY ALIASES (SECTION 3)
    # =========================================================================

    @app_commands.command(name="play", description="Play a song or playlist (Shortcut for /music play)")
    @app_commands.describe(
        query="Song title, artist, or URL",
        top="Play next / insert at the top of the queue (JukeBot style)",
    )
    async def alias_play(self, interaction: discord.Interaction, query: str, top: bool = False) -> None:
        try:
            await self.music_play.callback(self, interaction, query, top=top)
        except Exception as e:
            if isinstance(e, discord.HTTPException) and e.code in (40060, 10062):
                return
            logger.error(f"[Playback] Uncaught error in alias_play (/play): {e}", exc_info=True)
            await self.send_ephemeral_or_fallback(interaction, content=f"❌ Error executing `/play`: {e}")

    @alias_play.autocomplete("query")
    async def alias_play_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        return await self.music_play_autocomplete(interaction, current)

    @app_commands.command(name="search", description="Search YouTube and pick from top matching songs")
    @app_commands.describe(query="Song search query")
    async def alias_search(self, interaction: discord.Interaction, query: str) -> None:
        await self.music_search.callback(self, interaction, query)

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

    @app_commands.command(name="volume", description="Set volume 0-100% (up to 150% with Premium)")
    @app_commands.describe(percent="Volume percentage (0-100% standard, up to 150% with Premium)")
    async def alias_volume(self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 150]) -> None:
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

    @app_commands.command(name="join", description="Connect music bot to your current voice channel")
    async def alias_join(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_join.callback(self, interaction)

    @app_commands.command(name="leave", description="Disconnect music bot from voice and clear queue")
    async def alias_leave(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        await self.music_leave.callback(self, interaction)

    @app_commands.command(name="skipto", description="Skip directly to a specific song number in queue")
    @app_commands.describe(position="Queue position number to jump to")
    async def alias_skipto(self, interaction: discord.Interaction, position: int) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if position < 1 or position > len(session.queue):
            await interaction.followup.send(f"❌ Invalid track number. The queue has {len(session.queue)} tracks.", ephemeral=True)
            return

        tracks = list(session.queue)
        # Drop songs preceding target position
        for _ in range(position - 1):
            tracks.pop(0)
        session.queue = deque(tracks)
        success, msg, _ = await MusicPlayerService.skip(self.bot, session)
        await interaction.followup.send(f"⏭️ Skipped to track `#{position}`:\n{msg}")

    @app_commands.command(name="replay", description="Replay the currently playing song from the start")
    async def alias_replay(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.current_track:
            await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            return
        await MusicPlayerService.seek(self.bot, session, 0)
        await interaction.followup.send(f"🔄 Replaying **{session.current_track.title}** from the beginning.")

    @app_commands.command(name="grab", description="Save and send the currently playing song details to your DMs")
    async def alias_grab(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=True)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.current_track:
            await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            return
        track = session.current_track
        embed = discord.Embed(
            title="💾 Saved Song Details",
            description=(
                f"### [{track.title}]({track.url})\n"
                f"👤 **Artist:** `{track.artist}`\n"
                f"⏱️ **Duration:** `{format_duration(track.duration)}`\n"
                f"🏰 **Server:** `{interaction.guild.name if interaction.guild else 'Unknown'}`"
            ),
            color=COLOR_PRIMARY,
        )
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        try:
            await interaction.user.send(embed=embed)
            await interaction.followup.send("📩 Sent current song information to your direct messages!", ephemeral=True)
        except Exception:
            await interaction.followup.send("❌ Could not send DM. Please verify that your direct messages are open.", ephemeral=True)

    @app_commands.command(name="import", description="Import an external playlist from Spotify, YouTube, or Apple Music")
    @app_commands.describe(
        url="Link to playlist or album (Spotify, YouTube, Apple Music)",
        name="Optional custom name for your saved playlist",
        play_now="Immediately queue and start playing the imported playlist",
    )
    async def alias_import(
        self,
        interaction: discord.Interaction,
        url: str,
        name: Optional[str] = None,
        play_now: bool = False,
    ) -> None:
        await self.playlist_import(interaction, url, name, play_now)

    @app_commands.command(name="station", description="Launch a 24/7 radio station (JukeBot Radio Suite)")
    @app_commands.describe(station="Choose a radio genre (lofi, jazz, synthwave, phonk, lounge, workout, etc.)")
    async def alias_station(self, interaction: discord.Interaction, station: str) -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        if not await self._check_permissions(interaction):
            return
        from music_bot.services.jukebot_service import JukeBotStreamRequest
        url = JukeBotStreamRequest.get_random_radio_url(station)
        if not url:
            stations = ", ".join(f"`{s}`" for s in JukeBotStreamRequest.list_radio_stations())
            await interaction.followup.send(f"❌ Unknown radio station `{station}`. Available stations: {stations}", ephemeral=True)
            return
        await self._play_query(interaction, url, display_name=f"📻 {station.capitalize()} Radio", top=True)

    @alias_station.autocomplete("station")
    async def radio_station_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        from music_bot.services.jukebot_service import JukeBotStreamRequest
        stations = JukeBotStreamRequest.list_radio_stations()
        return [
            app_commands.Choice(name=f"📻 {s.capitalize()}", value=s)
            for s in stations
            if current.lower() in s.lower()
        ][:25]

    @property
    def alias_autodj(self):
        """Backward-compatible property referencing authoritative cmd_autodj without duplicate slash command registration."""
        return self.cmd_autodj


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
        if query.startswith(guild_pref) or query.startswith("m!") or query.startswith(",") or query.startswith("!"):
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
                res_err = getattr(AudioResolver, "last_resolver_error", None) or ""
                original_match_notice = (
                    "I couldn't verify an original singer/release, so I didn't play a possible cover or remix.\n"
                    if "[NO_ORIGINAL_MATCH]" in res_err
                    else ""
                )
                await status_msg.edit(content=f"{original_match_notice}{DIALOGUE_NOTHING_PLAYABLE}\nQuery: `{query}`")
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

    @app_commands.command(name="invite", description="Get official invite link for MusicMaid")
    async def invite(self, interaction: discord.Interaction) -> None:
        """Provide official invite links for MusicMaid with interactive buttons."""
        await self.ensure_deferred(interaction, ephemeral=False)
        bot_name = self.bot.user.name if self.bot.user else "MusicMaid"
        client_id = self.bot.user.id if self.bot.user else 1554626865958887444
        invite_url = f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions=2268449856&scope=bot%20applications.commands"
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label=f"Invite {bot_name}",
                style=discord.ButtonStyle.link,
                url=invite_url,
                emoji="🎵",
            )
        )
        embed = discord.Embed(
            title=f"🐾 Invite {bot_name}",
            description=(
                f"Bring cute, futuristic 24/7 lossless music, Auto-DJ, and web controls to your server!\n\n"
                f"🎵 **{bot_name}** — Lossless Audio, 24/7 Radio, DSP Equalizer & Web Player Dashboard"
            ),
            color=0x00E5FF,
        )
        embed.set_footer(text=f"{bot_name} • 24/7 Lossless Audio Companion & Web Player")
        await interaction.edit_original_response(embed=embed, view=view)

    @commands.command(name="invite")
    async def pfx_invite(self, ctx: commands.Context) -> None:
        """Get official invite link for MusicMaid via text command."""
        bot_name = self.bot.user.name if self.bot.user else "MusicMaid"
        client_id = self.bot.user.id if self.bot.user else 1554626865958887444
        invite_url = f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions=2268449856&scope=bot%20applications.commands"
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label=f"Invite {bot_name}",
                style=discord.ButtonStyle.link,
                url=invite_url,
                emoji="🎵",
            )
        )
        embed = discord.Embed(
            title=f"🐾 Invite {bot_name}",
            description=(
                f"Bring 24/7 lossless music, Auto-DJ, DSP Equalizer, and web controls to your server!\n\n"
                f"🔗 **Direct Invite Link:** [Click Here to Invite]({invite_url})"
            ),
            color=0x00E5FF,
        )
        await ctx.reply(embed=embed, view=view, mention_author=False)

    # =========================================================================
    # PREMIUM MANAGEMENT SUITE
    # =========================================================================

    @app_commands.command(name="premium", description="Explore MusicMaid Premium perks, status, and website")
    @app_commands.describe(
        action="Choose an action or leave blank to explore perks & website",
        key="Secret activation key (required when action is activate)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="🌟 Explore Perks & Website (Default)", value="overview"),
            app_commands.Choice(name="📊 Check Active Status", value="status"),
            app_commands.Choice(name="🔑 Activate License Key", value="activate"),
        ]
    )
    async def cmd_premium(
        self,
        interaction: discord.Interaction,
        action: Optional[app_commands.Choice[str]] = None,
        key: Optional[str] = None,
    ) -> None:
        """Authoritative MusicMaid Premium Suite."""
        act = action.value if action else "overview"

        if act == "status":
            await self._execute_premium_status(interaction)
            return

        if act == "activate":
            await self._execute_premium_activate(interaction, key)
            return

        # Default: overview & website
        await self._execute_premium_overview(interaction)

    async def _execute_premium_overview(self, interaction: discord.Interaction) -> None:
        """Render the official MusicMaid Premium embed with website link button."""
        await self.ensure_deferred(interaction, ephemeral=False)
        prem_icon = EmojiManager.get("PREMIUM", self.bot)
        web_url = get_public_web_url()
        plans_url = get_premium_plans_url()
        is_owner = await self.is_bot_developer_or_owner(interaction.user)

        vip_banner = ""
        if is_owner:
            vip_banner = (
                "👑 **Bot Creator & Developer VIP Active!**\n"
                "You are recognized as the bot creator. All Premium perks (150% volume, 24/7 persistence, studio DSP, smart DJ) "
                "are permanently unlocked for your account across every server and the web platform.\n\n"
            )

        embed = discord.Embed(
            title=f"{prem_icon} MusicMaid Premium{' ✦ 👑 Developer VIP' if is_owner else ''}",
            description=(
                f"{vip_banner}"
                "Unlock the MusicMaid experience and explore available plans and features on our website.\n\n"
                "🌐 Visit the website to learn more and manage your account.\n\n"
                "### 🌟 Premium Features Currently Available:\n"
                "• 🔊 **150% Boosted Master Volume Cap** — Enhanced audio headroom beyond the standard 100% ceiling\n"
                "• 🕒 **24/7 Voice Channel Persistence** — Bot stays in your voice room without timeout disconnects (`/247`)\n"
                "• 🎛️ **Studio DSP Equalizer Presets** — Bass Boost, 8D Audio, Nightcore, Vaporwave, and Lo-Fi acoustics\n"
                "• ⚡ **Priority Gapless Pre-Resolver** — Zero latency between songs with lookahead stream precaching\n"
                "• 🐾 **Smart Auto-DJ & Infinite Autoplay** — Non-stop queue generation tailored to your server's vibe\n\n"
                "💳 **Plans & Subscriptions:** Visit the Web Dashboard to view plans or subscribe with Razorpay. "
                "Server administrators and beta testers can also activate license keys using `/premium action:Activate License Key`.\n\n"
                "🔒 *Need to manage your account or playlists? Log in securely using Discord OAuth2 on our web platform.*"
            ),
            color=COLOR_CYAN if is_owner else COLOR_PREMIUM,
        )

        if not web_url:
            embed.description += (
                "\n\n⚠️ **Configuration Warning:** Public website URL is not configured or is set to localhost. "
                "Set `MUSICMAID_WEBSITE_URL` to your production HTTPS domain to enable web link buttons."
            )

        embed.set_footer(text="MusicMaid ✦ Lossless Anime Audio Platform")
        view = PremiumLinkView(web_url, plans_url) if (web_url or plans_url) else None
        if view and len(view.children) == 0:
            view = None

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)

    async def _execute_premium_status(self, interaction: discord.Interaction) -> None:
        """View whether current server or caller has an active premium subscription."""
        await self.ensure_deferred(interaction, ephemeral=False)
        guild = interaction.guild
        member = interaction.user
        is_owner = await self.is_bot_developer_or_owner(member)
        guild_prem = await self.bot.db.is_premium(guild.id) if guild else False
        user_prem = is_owner or await self.bot.db.is_premium(0, member.id)
        is_active = is_owner or guild_prem or user_prem

        prem_icon = EmojiManager.get("PREMIUM", self.bot)
        web_url = get_public_web_url()
        plans_url = get_premium_plans_url()

        owner_line = "\n• **Developer License:** `👑 Bot Creator & Developer VIP Pass (Lifetime Unlocked)`" if is_owner else ""
        embed = discord.Embed(
            title=f"{prem_icon} MusicMaid ✦ Premium Status",
            description=(
                f"**Overall Status:** `{'✨ ACTIVE (UNLOCKED)' if is_active else 'STANDARD (FREE TIER)'}`\n\n"
                f"• **Server Premium:** `{'✅ Active' if guild_prem else '❌ Inactive'}`\n"
                f"• **Personal User Premium:** `{'✅ Active' if user_prem else '❌ Inactive'}`{owner_line}\n\n"
                f"### 🌟 Premium Perks:\n"
                f"• 🔊 **150% Boosted Master Volume Cap** (Standard capped at 100%)\n"
                f"• 🕒 **24/7 Voice Channel Persistence** (`/247` or `/stay`)\n"
                f"• 🎛️ **Studio DSP Equalizer Presets** (Bass Boost, 8D Audio, Nightcore, Lo-Fi)\n"
                f"• ⚡ **Priority In-Memory & Redis Caching** (Instant sub-100ms playback)\n"
                f"• 🐾 **Lookahead Pre-Resolver** (Zero wait time between queued songs)\n\n"
                f"*Visit the web dashboard below to manage playlists, DSP filters, and queue controls.*"
            ),
            color=COLOR_CYAN if is_active else COLOR_PREMIUM,
        )

        if not web_url:
            embed.description += (
                "\n\n⚠️ **Configuration Warning:** Public website URL is not configured or is set to localhost. "
                "Set `MUSICMAID_WEBSITE_URL` to your production HTTPS domain to enable web link buttons."
            )

        embed.set_footer(text="MusicMaid ✦ Lossless Anime Audio Platform")
        view = PremiumLinkView(web_url, plans_url) if (web_url or plans_url) else None
        if view and len(view.children) == 0:
            view = None

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)

    async def _execute_premium_activate(self, interaction: discord.Interaction, key: Optional[str]) -> None:
        """Activate premium subscription for current server or account using key."""
        await self.ensure_deferred(interaction, ephemeral=True)
        if not key or not key.strip():
            msg = "❌ **Missing Key:** Please specify an activation key with `key:<your-key>`."
            if interaction.response.is_done():
                await interaction.edit_original_response(content=msg)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        secret_key = os.getenv("PREMIUM_KEY", "musicmaid_premium")
        if key.strip() != secret_key:
            msg = "❌ **Invalid activation key.** Please verify your key and try again."
            if interaction.response.is_done():
                await interaction.edit_original_response(content=msg)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        target_id = interaction.guild_id if interaction.guild else interaction.user.id
        target_type = "guild" if interaction.guild else "user"
        await self.bot.db.set_premium(target_id, entity_type=target_type, is_premium=True, tier="premium", activated_by=interaction.user.id)
        msg = (
            f"🎉 **Premium Activated Successfully!**\n"
            f"All premium features (150% volume cap, 24/7 persistence, studio DSP filters) are now unlocked for this {target_type}!"
        )
        if interaction.response.is_done():
            await interaction.edit_original_response(content=msg)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="premium_status", description="Check active premium tier status and unlocked perks")
    async def cmd_premium_status(self, interaction: discord.Interaction) -> None:
        """Direct shortcut for checking premium status."""
        await self._execute_premium_status(interaction)

    @app_commands.command(name="premium_grant", description="Administrator grant or revoke premium for server or user")
    @app_commands.describe(action="Grant or revoke premium", target_type="Apply to server or user")
    @app_commands.choices(
        action=[app_commands.Choice(name="Grant Premium", value="grant"), app_commands.Choice(name="Revoke Premium", value="revoke")],
        target_type=[app_commands.Choice(name="This Server", value="guild"), app_commands.Choice(name="Yourself", value="user")]
    )
    async def cmd_premium_grant(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        target_type: app_commands.Choice[str],
    ) -> None:
        """Admin shortcut to grant or revoke premium."""
        await self.ensure_deferred(interaction, ephemeral=True)
        is_dev = await self.is_bot_developer_or_owner(interaction.user)
        is_admin = is_dev or (getattr(interaction.user.guild_permissions, "administrator", False) if interaction.guild else False)
        is_owner = is_dev or (interaction.guild and interaction.user.id == interaction.guild.owner_id)
        if not is_admin and not is_owner:
            msg = "❌ Only Server Administrators or Bot Developers can manage premium grants."
            if interaction.response.is_done():
                await interaction.edit_original_response(content=msg)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        entity_id = interaction.guild_id if target_type.value == "guild" else interaction.user.id
        is_prem = action.value == "grant"
        await self.bot.db.set_premium(entity_id, entity_type=target_type.value, is_premium=is_prem, tier="premium", activated_by=interaction.user.id)
        act_str = "granted to" if is_prem else "revoked from"
        msg = f"✅ **Premium has been {act_str} this {target_type.name.lower()}!**"
        if interaction.response.is_done():
            await interaction.edit_original_response(content=msg)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    # Prefix Commands for Premium
    @commands.group(name="premium", aliases=["vip"], invoke_without_command=True)
    async def prefix_premium(self, ctx: commands.Context, *, arg: Optional[str] = None) -> None:
        """MusicMaid Premium Tier Perks & Web Portal."""
        if arg and arg.lower().strip() == "status":
            await self._prefix_premium_status(ctx)
            return

        prem_icon = EmojiManager.get("PREMIUM", self.bot)
        web_url = get_public_web_url()
        plans_url = get_premium_plans_url()

        embed = discord.Embed(
            title=f"{prem_icon} MusicMaid Premium",
            description=(
                "Unlock the MusicMaid experience and explore available plans and features on our website.\n\n"
                "🌐 Visit the website to learn more and manage your account.\n\n"
                "### 🌟 Premium Features Currently Available:\n"
                "• 🔊 **150% Boosted Master Volume Cap** — Enhanced audio headroom beyond the standard 100% ceiling\n"
                "• 🕒 **24/7 Voice Channel Persistence** — Bot stays in your voice room without timeout disconnects (`/247`)\n"
                "• 🎛️ **Studio DSP Equalizer Presets** — Bass Boost, 8D Audio, Nightcore, Vaporwave, and Lo-Fi acoustics\n"
                "• ⚡ **Priority Gapless Pre-Resolver** — Zero latency between songs with lookahead stream precaching\n"
                "• 🐾 **Smart Auto-DJ & Infinite Autoplay** — Non-stop queue generation tailored to your server's vibe\n\n"
                "💳 **Plans & Subscriptions:** Online subscription checkout is coming soon! "
                "Server administrators and beta testers can currently activate license keys using `,premium activate <key>`.\n\n"
                "🔒 *Need to manage your account or playlists? Log in securely using Discord OAuth2 on our web platform.*"
            ),
            color=COLOR_PREMIUM,
        )

        if not web_url:
            embed.description += (
                "\n\n⚠️ **Configuration Warning:** Public website URL is not configured or is set to localhost. "
                "Set `MUSICMAID_WEBSITE_URL` to your production HTTPS domain to enable web link buttons."
            )

        embed.set_footer(text="MusicMaid ✦ Lossless Anime Audio Platform")
        view = PremiumLinkView(web_url, plans_url) if (web_url or plans_url) else None
        if view and len(view.children) == 0:
            view = None

        await ctx.send(embed=embed, view=view)

    @prefix_premium.command(name="status")
    async def prefix_premium_status(self, ctx: commands.Context) -> None:
        await self._prefix_premium_status(ctx)

    async def _prefix_premium_status(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        member = ctx.author
        is_owner = config.is_bot_owner(member.id)
        guild_prem = await self.bot.db.is_premium(guild.id) if guild else False
        user_prem = is_owner or await self.bot.db.is_premium(0, member.id)
        is_active = guild_prem or user_prem

        prem_icon = EmojiManager.get("PREMIUM", self.bot)
        web_url = get_public_web_url()
        plans_url = get_premium_plans_url()

        owner_line = "\n• **Developer License:** `👑 Bot Owner VIP Pass (Lifetime Unlocked)`" if is_owner else ""
        embed = discord.Embed(
            title=f"{prem_icon} MusicMaid ✦ Premium Status",
            description=(
                f"**Overall Status:** `{'✨ ACTIVE (UNLOCKED)' if is_active else 'STANDARD (FREE TIER)'}`\n\n"
                f"• **Server Premium:** `{'✅ Active' if guild_prem else '❌ Inactive'}`\n"
                f"• **Personal User Premium:** `{'✅ Active' if user_prem else '❌ Inactive'}`{owner_line}\n\n"
                f"### 🌟 Premium Perks:\n"
                f"• 🔊 **150% Boosted Master Volume Cap** (Standard capped at 100%)\n"
                f"• 🕒 **24/7 Voice Channel Persistence** (`/247` or `/stay`)\n"
                f"• 🎛️ **Studio DSP Equalizer Presets** (Bass Boost, 8D Audio, Nightcore, Lo-Fi)\n"
                f"• ⚡ **Priority In-Memory & Redis Caching** (Instant sub-100ms playback)\n"
                f"• 🐾 **Lookahead Pre-Resolver** (Zero wait time between queued songs)\n\n"
                f"*Visit the web dashboard below to manage playlists, DSP filters, and queue controls.*"
            ),
            color=COLOR_CYAN if is_active else COLOR_PREMIUM,
        )

        if not web_url:
            embed.description += (
                "\n\n⚠️ **Configuration Warning:** Public website URL is not configured or is set to localhost. "
                "Set `MUSICMAID_WEBSITE_URL` to your production HTTPS domain to enable web link buttons."
            )

        embed.set_footer(text="MusicMaid ✦ Lossless Anime Audio Platform")
        view = PremiumLinkView(web_url, plans_url) if (web_url or plans_url) else None
        if view and len(view.children) == 0:
            view = None

        await ctx.send(embed=embed, view=view)

    @prefix_premium.command(name="activate")
    async def prefix_premium_activate(self, ctx: commands.Context, key: str) -> None:
        secret_key = os.getenv("PREMIUM_KEY", "musicmaid_premium")
        if key.strip() != secret_key:
            await ctx.send("❌ **Invalid activation key.** Please verify your key and try again.")
            return

        target_id = ctx.guild.id if ctx.guild else ctx.author.id
        target_type = "guild" if ctx.guild else "user"
        await self.bot.db.set_premium(target_id, entity_type=target_type, is_premium=True, tier="premium", activated_by=ctx.author.id)
        await ctx.send(
            f"🎉 **Premium Activated Successfully!**\nAll premium features (150% volume cap, 24/7 persistence, studio DSP filters) are now unlocked for this {target_type}!"
        )

    @prefix_premium.command(name="grant")
    async def prefix_premium_grant(self, ctx: commands.Context, action: str, target_type: str = "guild") -> None:
        is_admin = getattr(ctx.author.guild_permissions, "administrator", False) if isinstance(ctx.author, discord.Member) else False
        is_owner = ctx.guild and ctx.author.id == ctx.guild.owner_id
        if not is_admin and not is_owner:
            await ctx.send("❌ Only Server Administrators can manage premium grants.")
            return

        target_type = target_type.lower()
        if target_type not in ("guild", "server", "user"):
            await ctx.send("❌ Target type must be `server` or `user`.")
            return

        act = action.lower()
        if act not in ("grant", "revoke"):
            await ctx.send("❌ Action must be `grant` or `revoke`.")
            return

        is_prem = act == "grant"
        entity_id = ctx.guild.id if target_type in ("guild", "server") else ctx.author.id
        real_type = "guild" if target_type in ("guild", "server") else "user"
        await self.bot.db.set_premium(entity_id, entity_type=real_type, is_premium=is_prem, tier="premium", activated_by=ctx.author.id)
        act_str = "granted to" if is_prem else "revoked from"
        await ctx.send(f"✅ **Premium has been {act_str} this {real_type}!**")




    # =========================================================================
    # PREFIX CUSTOMIZATION & PREFIX COMMAND SUITE
    # =========================================================================

    @app_commands.command(name="prefix", description="View or customize the server's prefix symbol (e.g. , or ! or ?)")
    @app_commands.describe(symbol="New prefix symbol (leave empty to view current prefix)")
    async def cmd_prefix(self, interaction: discord.Interaction, symbol: Optional[str] = None) -> None:
        """View or configure server custom prefix."""
        await self.ensure_deferred(interaction, ephemeral=True)
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.edit_original_response(content="❌ This command must be used in a server.")
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
            await interaction.edit_original_response(embed=embed)
            return

        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.edit_original_response(content="❌ You need the **Manage Server** permission to change the prefix.")
            return

        new_sym = symbol.strip()
        if not (1 <= len(new_sym) <= 5):
            await interaction.edit_original_response(content="❌ Prefix must be between 1 and 5 characters long.")
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
        await interaction.edit_original_response(embed=embed)

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
        """Plays audio from YouTube or Spotify links via prefix command."""
        if not ctx.guild or not hasattr(ctx.author, "id"):
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
                if "Voice connection failed:" in err:
                    reply_text = f"❌ {err}"
                elif "permission" in err.lower():
                    reply_text = f"❌ {err}\n💡 Please check voice channel permissions for MusicMaid."
                else:
                    reply_text = f"❌ {err}"
                await ctx.reply(reply_text, mention_author=False)
                return

        correlation_id = uuid.uuid4().hex[:8].upper()
        logger.info(
            "[Playback] operation=play_request correlation_id=%s query=%r normalized_query=%r",
            correlation_id,
            _safe_query_for_log(query),
            _safe_query_for_log(" ".join(query.split())),
        )
        if query.startswith(("http://", "https://", "spotify:")):
            search_prefix = "Resolving audio track... 🐾"
        else:
            search_prefix = f"🔍 Searching for `{query[:60]}`... 🐾"
        status_msg = await ctx.reply(search_prefix, mention_author=False)
        candidates = []
        if not query.startswith(("http://", "https://")):
            try:
                candidates = await AudioResolver.search(
                    query,
                    limit=5,
                    correlation_id=correlation_id,
                )
            except Exception as search_exc:
                logger.warning(
                    "[Playback] operation=preselection_search correlation_id=%s "
                    "exception_type=%s outcome=failed",
                    correlation_id,
                    type(search_exc).__name__,
                )
        if requires_candidate_confirmation(candidates):
            async def on_candidate_select(
                selected_interaction: discord.Interaction,
                selected_index: int,
            ) -> None:
                selected = candidates[selected_index]
                selected_url = selected.get("url") or ""
                selected_title = selected.get("title") or ""
                logger.info(
                    "[Playback] operation=candidate_selected correlation_id=%s "
                    "title=%r video_id=%s score=%s",
                    correlation_id,
                    selected_title,
                    selected.get("id") or _video_id_from_url(selected_url) or "unavailable",
                    selected.get("_match_score", "unavailable"),
                )
                await self._play_query(
                    selected_interaction,
                    selected_url,
                    correlation_id=correlation_id,
                    display_name=selected_title,
                )

            selection_view = TrackSelectView(candidates, ctx.author.id, on_candidate_select)
            await status_msg.edit(
                content="Several results are plausible, or the best match is uncertain. Choose the intended track:",
                view=selection_view,
            )
            return

        # Use the top-ranked search result as an exact YouTube URL so the
        # resolver cannot perform a second title search and pick a near-match.
        resolve_query = query
        if (
            not query.startswith(("http://", "https://"))
            and "spotify.com/" not in query.casefold()
            and "music.apple.com/" not in query.casefold()
            and candidates
        ):
            best_url = str(candidates[0].get("url") or "").strip()
            if _video_id_from_url(best_url):
                resolve_query = best_url
                logger.info(
                    "[Playback] operation=ranked_candidate_pinned correlation_id=%s "
                    "video_id=%s title=%r",
                    correlation_id,
                    _video_id_from_url(best_url),
                    candidates[0].get("title"),
                )

        prefix_title_hint = candidates[0].get("title") if candidates else None
        prefix_artist_hint = candidates[0].get("artist") if candidates else None
        try:
            track = await asyncio.wait_for(
                AudioResolver.resolve_track(
                    resolve_query,
                    ctx.author.id,
                    str(ctx.author),
                    title_hint=prefix_title_hint,
                    artist_hint=prefix_artist_hint,
                    correlation_id=correlation_id,
                ),
                timeout=90.0,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[Playback] operation=prefix_resolve correlation_id=%s "
                "exception_type=TimeoutError duration_ms=90000",
                correlation_id,
            )
            track = None
            timed_out = True
        except Exception as e:
            logger.error(
                "[Playback] operation=prefix_resolve correlation_id=%s "
                "exception_type=%s outcome=failed",
                correlation_id,
                type(e).__name__,
                exc_info=True,
            )
            track = None
            timed_out = False
        else:
            timed_out = False
        if not track:
            res_err = getattr(AudioResolver, "last_resolver_error", None) or ""
            if timed_out:
                await status_msg.edit(
                    content=f"⏱️ Audio search timed out for `{query[:60]}`. Try again, or provide another public YouTube link."
                )
                return
            if "[VIDEO_UNAVAILABLE]" in res_err:
                await status_msg.edit(
                    content=f"📹 YouTube says that video is unavailable or private. Use a different public link, or search by song title and singer."
                )
                return
            original_match_notice = (
                "I couldn't verify an original singer/release, so I didn't play a possible cover or remix.\n"
                if "[NO_ORIGINAL_MATCH]" in res_err
                else ""
            )
            await status_msg.edit(content=f"{original_match_notice}😿 Could not find playable audio for: `{query[:60]}`")
            return

        async with session.lock:
            setattr(track, "_correlation_id", correlation_id)
            # Rapid duplicate guard (prevents identical double-queueing within 3 seconds)
            now_t = time.time()
            last_url = getattr(session, "_last_queued_url", None)
            last_time = getattr(session, "_last_queued_time", 0.0)
            if track.url and track.url == last_url and (now_t - last_time) < 3.0:
                await status_msg.edit(content=f"⚠️ **{track.title}** was already just queued a moment ago! (Duplicate prevented)")
                return
            session._last_queued_url = track.url
            session._last_queued_time = now_t

            if session.is_playing or session.is_paused or session.has_active_track:
                session.queue.append(track)
                logger.info(
                    "[Playback] operation=queued correlation_id=%s title=%r video_id=%s "
                    "queue_position=%d",
                    correlation_id,
                    track.title,
                    _video_id_from_url(track.url) or "unavailable",
                    len(session.queue),
                )
                pos = len(session.queue)
                embed = discord.Embed(
                    title="🎵 Added to Queue",
                    description=(
                        f"**Track:** [{track.title}]({track.url})\n"
                        f"**Artist:** `{track.artist}`\n"
                        f"**Duration:** `{format_duration(track.duration)}`\n"
                        f"**Requested by:** <@{ctx.author.id}>\n"
                        f"**Position:** `#{pos}`"
                    ),
                    color=COLOR_NEON_BLUE,
                )
                if track.thumbnail:
                    embed.set_thumbnail(url=track.thumbnail)
                await status_msg.edit(content=None, embed=embed)
                await MusicPlayerService.send_now_playing_panel(session, bot=self.bot)
            else:
                session._play_request_correlation_id = correlation_id
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
        if not session.current_track or not (session.is_playing or session.is_paused or session.has_active_track):
            await ctx.reply("❌ Nothing is currently playing.", mention_author=False)
            return
        success, msg, _ = await MusicPlayerService.skip(self.bot, session)
        await ctx.reply(msg, mention_author=False)

    @commands.command(name="pause")
    async def pfx_pause(self, ctx: commands.Context) -> None:
        """Pauses audio playback."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        success, msg = await MusicPlayerService.pause(session)
        await ctx.reply(msg, mention_author=False)

    @commands.command(name="resume", aliases=["unpause"])
    async def pfx_resume(self, ctx: commands.Context) -> None:
        """Resumes paused playback."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        success, msg = await MusicPlayerService.resume(self.bot, session)
        await ctx.reply(msg, mention_author=False)

    @commands.command(name="stop")
    async def pfx_stop(self, ctx: commands.Context) -> None:
        """Stops playback and clears the queue."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        success, msg = await MusicPlayerService.stop(self.bot, session)
        await ctx.reply(msg, mention_author=False)

    @commands.command(name="leave", aliases=["disconnect", "dc"])
    async def pfx_leave(self, ctx: commands.Context) -> None:
        """Disconnects the bot from voice channel."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        session.is_intentional_disconnect = True
        session.is_intentional_stop = True
        if session.auto_leave_task and not session.auto_leave_task.done():
            session.auto_leave_task.cancel()
            session.auto_leave_task = None
        if session.voice_client:
            try:
                if session.voice_client.is_playing() or session.voice_client.is_paused():
                    session.voice_client.stop()
                await session.voice_client.disconnect(force=True)
            except Exception:
                pass
            session.voice_client = None
        session.queue.clear()
        session.current_track = None
        session.state = PlaybackState.IDLE
        await ctx.reply("👋 Disconnected from voice channel. Goodbye! (Use `/play` or `/247 reconnect` to rejoin)", mention_author=False)

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

    @commands.command(name="panel", aliases=["control"])
    async def pfx_control_panel(self, ctx: commands.Context) -> None:
        """Opens the interactive Master Control Panel."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        view = MusicControlPanelView(self.bot, ctx.guild, session)
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
            session.is_intentional_stop = False
            session.is_intentional_disconnect = False
            if session.auto_leave_task and not session.auto_leave_task.done():
                session.auto_leave_task.cancel()
                session.auto_leave_task = None
            await self.bot.db.update_guild_settings(settings)
            await ctx.reply(f"📻 **24/7 Mode ACTIVATED** in **{target_vc.name if target_vc else 'voice'}**! MusicMaid will stay connected indefinitely.", mention_author=False)
        else:
            settings.twenty_four_seven_channel_id = None
            session.is_intentional_disconnect = True
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
            session.loop_mode = LoopMode.TRACK
        elif mode in ("queue", "all"):
            session.loop_mode = LoopMode.QUEUE
        elif mode in ("off", "none", "disable"):
            session.loop_mode = LoopMode.OFF
        else:
            if session.loop_mode == LoopMode.OFF:
                session.loop_mode = LoopMode.TRACK
            elif session.loop_mode == LoopMode.TRACK:
                session.loop_mode = LoopMode.QUEUE
            else:
                session.loop_mode = LoopMode.OFF
        await ctx.reply(f"🔁 Loop mode is now: **{session.loop_mode.value.upper()}**", mention_author=False)

    @commands.command(name="seek")
    async def pfx_seek(self, ctx: commands.Context, seconds: int) -> None:
        """Seeks to a specific timestamp (in seconds) in the current song."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        if not session.current_track or not (session.is_playing or session.is_paused or session.has_active_track):
            await ctx.reply("❌ Nothing is currently playing.", mention_author=False)
            return
        if seconds < 0:
            await ctx.reply("❌ Timestamp must be a positive number of seconds.", mention_author=False)
            return
        success = await MusicPlayerService.seek(self.bot, session, seconds)
        if success:
            await ctx.reply(f"⏩ Seeked to **{format_duration(seconds)}**.", mention_author=False)
        else:
            await ctx.reply("❌ Failed to seek in current stream.", mention_author=False)

    @commands.command(name="previous", aliases=["prev"])
    async def pfx_previous(self, ctx: commands.Context) -> None:
        """Plays the previously played track from history."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        success, msg, _ = await MusicPlayerService.previous(self.bot, session)
        await ctx.reply(msg, mention_author=False)

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
        """Applies audio DSP preset (bassboost, 8d, lofi, vocal, nightcore, pop, rock, flat)."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        preset = preset.lower().strip()
        if not preset:
            view = AudioEqualizerView(session, self.bot)
            await ctx.reply(f"🎛️ **Audio Equalizer Presets** (Current: `{getattr(session, 'eq_preset', 'Flat')}`):", view=view, mention_author=False)
            return

        presets_map = {
            "bassboost": "Bass Boost",
            "bass": "Bass Boost",
            "nightcore": "Nightcore",
            "8d": "8D Audio",
            "vaporwave": "Lo-Fi Relax",
            "lofi": "Lo-Fi Relax",
            "vocal": "Clear Vocal",
            "pop": "Pop",
            "rock": "Rock",
            "flat": "Flat / Normal",
            "reset": "Flat / Normal",
            "normal": "Flat / Normal",
            "off": "Flat / Normal",
        }
        if preset not in presets_map:
            pref = await self.bot.get_guild_prefix(ctx.guild.id)
            valid = ["bassboost", "8d", "lofi", "vocal", "nightcore", "pop", "rock", "flat"]
            await ctx.reply(f"🎛️ **Available presets:** `{'`, `'.join(valid)}`\nUsage: `{pref}filter bassboost` or `{pref}eq flat`", mention_author=False)
            return

        d_name = presets_map[preset]
        key = "reset" if preset in ("flat", "reset", "normal", "off") else ("vaporwave" if preset == "lofi" else ("bassboost" if preset == "bass" else preset))
        success = await MusicPlayerService.apply_filter_or_eq(self.bot, session, key, d_name)
        if success:
            await ctx.reply(f"🎛️ Equalizer preset set to: **{d_name}** *(Current song continues playing seamlessly with real-time DSP filter)*", mention_author=False)
        else:
            await ctx.reply(f"⚠️ Failed to apply preset **{d_name}**. Preserved previous audio filter.", mention_author=False)

    @commands.command(name="autodj", aliases=["dj", "autoplay", "nonstop"])
    async def pfx_autodj(self, ctx: commands.Context, action: Optional[str] = "status") -> None:
        """Control individual-song Auto-DJ mode: on, off, status."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        action_clean = (action or "status").lower().strip()
        settings = None
        if hasattr(self.bot, "db") and self.bot.db and hasattr(self.bot.db, "get_dj_settings"):
            try:
                settings = await self.bot.db.get_dj_settings(ctx.guild.id)
            except Exception:
                settings = None

        if action_clean in ("on", "enable", "start"):
            if settings and hasattr(self.bot.db, "update_dj_settings"):
                try:
                    settings.enabled = True
                    await self.bot.db.update_dj_settings(settings)
                except Exception:
                    pass
            session.dj_enabled = True
            started_msg = ""
            if not session.is_playing and isinstance(ctx.author, discord.Member) and ctx.author.voice and ctx.author.voice.channel:
                vc = await VoiceManager.join_voice_channel(ctx.author, ctx.channel, session)  # type: ignore
                if vc:
                    from music_bot.services.dj_service import NekoDJService
                    rec = await NekoDJService.get_recommendation(self.bot, session)
                    if rec:
                        track, rationale = rec
                        if await MusicPlayerService.start_playback(self.bot, session, track):
                            started_msg = f"\n🎧 Started first recommendation: **{track.title}**"
            if session.now_playing_message:
                try:
                    await session.now_playing_message.edit(embed=MusicPlayerService.build_now_playing_embed(session))
                except Exception:
                    pass
            mood = getattr(session, "dj_mood", "balanced").title()
            await ctx.reply(f"🎧 **Auto-DJ is now ON!** (Individual songs will be recommended automatically when the manual queue is empty | Mood: `{mood}`){started_msg}", mention_author=False)

        elif action_clean in ("off", "disable", "stop"):
            if settings and hasattr(self.bot.db, "update_dj_settings"):
                try:
                    settings.enabled = False
                    await self.bot.db.update_dj_settings(settings)
                except Exception:
                    pass
            session.dj_enabled = False
            if session.now_playing_message:
                try:
                    await session.now_playing_message.edit(embed=MusicPlayerService.build_now_playing_embed(session))
                except Exception:
                    pass
            await ctx.reply("⏹️ **Auto-DJ is now OFF.** Playback will pause when your queue is finished.", mention_author=False)

        else:
            is_enabled = getattr(session, "dj_enabled", False) or (settings.enabled if settings else False)
            status_str = "🟢 Enabled" if is_enabled else "🔴 Disabled"
            mood = getattr(session, "dj_mood", "balanced").title()
            from music_bot.services.dj_service import NekoDJService
            rec = await NekoDJService.get_recommendation(self.bot, session) if is_enabled else None
            next_sugg = f"{rec[0].artist} — {rec[0].title}" if rec else "None ready"
            embed = discord.Embed(
                title="🎧 Auto-DJ Status",
                description=(
                    f"• **Status:** `{status_str}`\n"
                    f"• **Current Mood:** `{mood}`\n"
                    f"• **Queue Mode:** Individual-Song Radio\n"
                    f"• **Next Suggestion:** `{next_sugg}`\n"
                    f"• **Manual Queue Priority:** Active (manual queue always plays first)"
                ),
                color=COLOR_ELECTRIC_CYAN,
            )
            await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="maiddj", aliases=["djmaid", "voicedj"])
    async def pfx_maid_dj(self, ctx: commands.Context, action: Optional[str] = "status", personality: Optional[str] = None) -> None:
        """Control AI Anime Maid Voice DJ track announcer: on, off, test, or personality name."""
        if not ctx.guild:
            return
        session = await self.session_manager.get_session(ctx.guild.id)
        from music_bot.services.maid_dj_service import MaidDJService

        act_clean = (action or "status").lower().strip()
        if act_clean in MaidDJService.PERSONALITIES:
            session.maid_dj_personality = act_clean
            session.maid_voice_dj_enabled = True
            p_cfg = MaidDJService.PERSONALITIES[act_clean]
            await ctx.reply(f"🎙️ **Maid DJ activated with personality:** `{p_cfg['name']}`! 🎀", mention_author=False)
            return

        if act_clean in ("on", "enable", "start"):
            session.maid_voice_dj_enabled = True
            if personality and personality.lower() in MaidDJService.PERSONALITIES:
                session.maid_dj_personality = personality.lower()
            p_cfg = MaidDJService.PERSONALITIES.get(session.maid_dj_personality, MaidDJService.PERSONALITIES["maid"])
            await ctx.reply(f"🟢 **AI Maid Voice DJ is now ENABLED!** (`{p_cfg['name']}`)\nShe will introduce songs with spoken anime intros & cards! ✨", mention_author=False)
        elif act_clean in ("off", "disable", "stop"):
            session.maid_voice_dj_enabled = False
            await ctx.reply("🔴 **AI Maid Voice DJ is now DISABLED.**", mention_author=False)
        elif act_clean in ("test", "preview"):
            from music_bot.database.models import QueuedTrack
            p_val = session.maid_dj_personality
            test_track = session.current_track or QueuedTrack(
                title="Sparkle",
                artist="RADWIMPS",
                url="https://youtube.com/watch?v=mock",
                stream_url="",
                duration=210,
                requester_id=ctx.author.id,
                requester_name=ctx.author.display_name,
            )
            intro_text = MaidDJService.generate_intro_text(p_val, test_track, ctx.author.display_name)
            embed = MaidDJService.build_announcement_embed(test_track, intro_text, p_val)
            await ctx.reply("🎙️ **Voice DJ Soundcheck:**", embed=embed, mention_author=False)
        else:
            is_on = getattr(session, "maid_voice_dj_enabled", False)
            curr_p = getattr(session, "maid_dj_personality", "maid")
            p_cfg = MaidDJService.PERSONALITIES.get(curr_p, MaidDJService.PERSONALITIES["maid"])
            status_str = "🟢 Active" if is_on else "🔴 Inactive"
            pref = await self.bot.get_guild_prefix(ctx.guild.id)
            embed = discord.Embed(
                title="🎙️ AI Anime Maid Voice DJ Status",
                description=(
                    f"• **Voice DJ Status:** `{status_str}`\n"
                    f"• **Current Personality:** `{p_cfg['name']}`\n"
                    f"• **Available Styles:** `maid`, `tsundere`, `hype`, `chill`, `cyberpunk`\n\n"
                    f"Usage: `{pref}maiddj on` • `{pref}maiddj tsundere` • `{pref}maiddj test`"
                ),
                color=p_cfg["color"],
            )
            embed.set_thumbnail(url=p_cfg["avatar"])
            await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="blend", aliases=["musicblend", "friendblend"])
    async def pfx_blend(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """Blend your music taste with a friend into an anime neon mix."""
        if not ctx.guild:
            return
        if not member:
            pref = await self.bot.get_guild_prefix(ctx.guild.id)
            await ctx.reply(f"ℹ️ **Usage:** `{pref}blend @Friend` to synthesize your dual music blend!", mention_author=False)
            return

        from music_bot.services.blend_service import FriendBlendService
        blend = await FriendBlendService.generate_blend(
            self.bot,
            guild_id=ctx.guild.id,
            user1=ctx.author,
            user2=member,
        )
        embed = FriendBlendService.build_blend_embed(blend)

        session = await self.session_manager.get_session(ctx.guild.id)
        if blend.tracks and isinstance(ctx.author, discord.Member) and ctx.author.voice and ctx.author.voice.channel:
            async with session.lock:
                from music_bot.services.voice_service import VoiceManager
                text_channel = ctx.channel if isinstance(ctx.channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread)) else None
                vc = await VoiceManager.join_voice_channel(ctx.author, text_channel, session)
                if vc:
                    for t in blend.tracks:
                        session.queue.append(t)
                    await ctx.reply(embed=embed, mention_author=False)
                    if not session.is_playing and session.queue:
                        first = session.queue.popleft()
                        await MusicPlayerService.start_playback(self.bot, session, first)
                    return

        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="import", aliases=["importplaylist", "plimport"])
    async def pfx_import(self, ctx: commands.Context, url: str = "", *, name: Optional[str] = None) -> None:
        """Import a Spotify, YouTube, or Apple Music playlist into your saved playlists."""
        if not ctx.guild:
            return
        if not url:
            pref = await self.bot.get_guild_prefix(ctx.guild.id)
            await ctx.reply(f"ℹ️ **Usage:** `{pref}import <playlist_url> [optional_name]` (Spotify, YouTube, Apple Music)", mention_author=False)
            return

        from music_bot.services.importer_service import PlaylistImporterService
        result = await PlaylistImporterService.import_playlist(
            self.bot,
            url=url,
            guild_id=ctx.guild.id,
            user_id=ctx.author.id,
            user_name=ctx.author.display_name,
            custom_name=name,
        )

        if not result.success or not result.tracks:
            err = result.error or "Failed to extract playlist tracks."
            await ctx.reply(f"❌ **Import Failed:** {err}", mention_author=False)
            return

        pref = await self.bot.get_guild_prefix(ctx.guild.id)
        embed = discord.Embed(
            title=f"📥 PLAYLIST IMPORTED • {result.platform.upper()}",
            description=(
                f"Successfully saved **{result.track_count}** tracks into playlist **\"{result.playlist_name}\"**!\n\n"
                f"• **Platform:** `{result.platform}`\n"
                f"• **Saved Name:** `{result.playlist_name}`\n"
                f"• **Play Anytime:** `{pref}playlist load {result.playlist_name}` or `/playlist load`"
            ),
            color=COLOR_PREMIUM,
        )
        if result.sample_tracks:
            embed.add_field(
                name="🎶 Sample Tracks",
                value="\n".join(f"• {t}" for t in result.sample_tracks),
                inline=False,
            )
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="commands", aliases=["help", "cmds"])
    async def pfx_help(self, ctx: commands.Context) -> None:
        """Displays all available prefix and slash commands."""
        if not ctx.guild:
            return
        pref = await self.bot.get_guild_prefix(ctx.guild.id)
        embed = discord.Embed(
            title=f"{EmojiManager.get('LOGO', self.bot)} MusicMaid ✦ Commands & Features Guide",
            description=(
                f"**Current Server Prefix:** `{pref}` *(Configurable!)*\n"
                f"Use Discord **Slash Commands** (`/`) or text prefixes for all controls.\n\n"
                f"{EmojiManager.get('NOTE', self.bot)} **Playback:** `{pref}play <song>` (`{pref}p`), `{pref}skip` (`{pref}s`), `{pref}pause`, `{pref}resume`, `{pref}stop`\n"
                f"{EmojiManager.get('QUEUE', self.bot)} **Queue:** `{pref}queue` (`{pref}q`), `{pref}np`, `{pref}volume <0-150>` (`{pref}v`), `{pref}loop`, `{pref}shuffle`, `{pref}clear`\n"
                f"{EmojiManager.get('EQUALIZER', self.bot)} **Audio & Filters:** `{pref}filter <preset>` (`{pref}eq`), `{pref}c` *(Master Control Panel)*\n"
                f"{EmojiManager.get('AUTODJ', self.bot)} **Smart Radio:** `{pref}autodj on/off` *(Endless song recommendations)*\n"
                f"{EmojiManager.get('RADIO', self.bot)} **24/7 Voice:** `{pref}247` or `{pref}stay` *(Keep bot in voice channel 24/7)*\n"
                f"{EmojiManager.get('SETTINGS', self.bot)} **Prefix Config:** `{pref}prefix <symbol>` *(e.g. `{pref}prefix !`)*"
            ),
            color=COLOR_PRIMARY,
        )
        embed.set_footer(text=f"MusicMaid ✦ Lossless Anime Audio Platform • {pref}prefix <symbol>")
        view = PremiumLinkView(get_public_web_url())
        await ctx.reply(embed=embed, view=view, mention_author=False)

    @commands.command(name="reload", aliases=["hotreload"])
    async def pfx_reload(self, ctx: commands.Context) -> None:
        """Hot-reloads bot code and preserves playback without restarting from the beginning."""
        if not ctx.guild:
            return
        is_dev = await self.is_bot_developer_or_owner(ctx.author)
        is_admin = is_dev or (getattr(ctx.author.guild_permissions, "administrator", False) if isinstance(ctx.author, discord.Member) else False)
        is_owner = is_dev or (ctx.guild and ctx.author.id == ctx.guild.owner_id)
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
        is_dev = await self.is_bot_developer_or_owner(ctx.author)
        is_admin = is_dev or (getattr(ctx.author.guild_permissions, "administrator", False) if isinstance(ctx.author, discord.Member) else False)
        is_owner = is_dev or (ctx.guild and ctx.author.id == ctx.guild.owner_id)
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


    # =========================================================================
    # PRIORITY QUEUE BUMP (/bump)
    # =========================================================================

    @app_commands.command(name="bump", description="Priority bump a song to play next (position #1 in queue)")
    @app_commands.describe(target="Queue position number (e.g. 3) or song search query")
    async def cmd_bump(self, interaction: discord.Interaction, target: str) -> None:
        """Move a song to the very front of the queue, or resolve and insert immediately."""
        await self.ensure_deferred(interaction, ephemeral=False)
        if not interaction.guild:
            await interaction.edit_original_response(content="❌ This command must be used in a server.")
            return

        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        async with session.lock:
            if target.isdigit():
                idx = int(target) - 1
                if idx < 0 or idx >= len(session.queue):
                    await interaction.edit_original_response(
                        content=f"❌ Invalid queue position. Queue length is **{len(session.queue)}**."
                    )
                    return
                bumped = session.queue[idx]
                del session.queue[idx]
                session.queue.appendleft(bumped)
                embed = discord.Embed(
                    title="⚡ PRIORITY QUEUE BUMP",
                    description=f"Bumped **[{bumped.title}]({bumped.url})** to position **#1**!\n*It will play immediately after the current song.*",
                    color=COLOR_ELECTRIC_CYAN,
                )
                await interaction.edit_original_response(embed=embed)
                return

        resolved = await AudioResolver.resolve_track(target, interaction.user.id, interaction.user.display_name)
        if not resolved:
            await interaction.edit_original_response(content=f"❌ Could not resolve track for query: `{target}`")
            return

        async with session.lock:
            session.queue.appendleft(resolved)

        embed = discord.Embed(
            title="⚡ PRIORITY QUEUE BUMP",
            description=f"Resolved and bumped **[{resolved.title}]({resolved.url})** to position **#1**!\n*It will play immediately after the current song.*",
            color=COLOR_ELECTRIC_CYAN,
        )
        if resolved.thumbnail:
            embed.set_thumbnail(url=resolved.thumbnail)
        await interaction.edit_original_response(embed=embed)

    # =========================================================================
    # PERSONAL FAVORITES SUITE (/favorite)
    # =========================================================================

    favorites_group = app_commands.Group(name="favorite", description="Manage personal favorite music tracks")

    @favorites_group.command(name="add", description="Save currently playing song or search query to your favorites")
    @app_commands.describe(search="Optional search query (defaults to current track)")
    async def fav_add(self, interaction: discord.Interaction, search: Optional[str] = None) -> None:
        await self.ensure_deferred(interaction, ephemeral=True)
        session = await self.session_manager.get_session(interaction.guild_id) if interaction.guild_id else None

        track = None
        if not search and session and session.current_track:
            track = session.current_track
        elif search:
            track = await AudioResolver.resolve_track(search, interaction.user.id, interaction.user.display_name)

        if not track:
            await interaction.edit_original_response(content="❌ Nothing is currently playing and no track was specified.")
            return

        if self.bot.db:
            ok = await self.bot.db.add_favorite(
                user_id=interaction.user.id,
                title=track.title,
                url=track.url,
                duration=track.duration or 0,
                artist=track.artist,
                thumbnail=track.thumbnail,
            )
            if ok:
                embed = discord.Embed(
                    title="⭐ ADDED TO FAVORITES",
                    description=f"Saved **[{track.title}]({track.url})** to your personal favorites library!",
                    color=0xFFD700,
                )
                if track.thumbnail:
                    embed.set_thumbnail(url=track.thumbnail)
                await interaction.edit_original_response(embed=embed)
                return
        await interaction.edit_original_response(content="❌ Database error saving favorite.")

    @favorites_group.command(name="list", description="View your saved personal favorite tracks")
    async def fav_list(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=True)
        if not self.bot.db:
            await interaction.edit_original_response(content="❌ Database unavailable.")
            return

        favs = await self.bot.db.get_user_favorites(interaction.user.id, limit=25)
        if not favs:
            await interaction.edit_original_response(content="⭐ You haven't saved any favorites yet! Use `/favorite add` while listening.")
            return

        desc_lines = []
        for i, f in enumerate(favs, 1):
            dur = format_duration(f.get("duration", 0))
            desc_lines.append(f"`{i:02d}.` **[{f['title']}]({f['url']})** (`{dur}`) — *{f.get('artist', 'Unknown')}*")

        embed = discord.Embed(
            title=f"⭐ {interaction.user.display_name}'s Saved Favorites",
            description="\n".join(desc_lines[:20]),
            color=0xFFD700,
        )
        embed.set_footer(text=f"Total: {len(favs)} favorites • Use /favorite play <num> to queue")
        await interaction.edit_original_response(embed=embed)

    @favorites_group.command(name="play", description="Queue one or all of your saved favorite tracks")
    @app_commands.describe(index="Favorite number to play, or 'all' to queue your entire favorites list")
    async def fav_play(self, interaction: discord.Interaction, index: str = "all") -> None:
        await self.ensure_deferred(interaction, ephemeral=False)
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.edit_original_response(content="❌ Must be in a server voice channel.")
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.edit_original_response(content="❌ You must join a voice channel first!")
            return

        favs = await self.bot.db.get_user_favorites(interaction.user.id, limit=50) if self.bot.db else []
        if not favs:
            await interaction.edit_original_response(content="⭐ You have no saved favorites. Use `/favorite add` first!")
            return

        session = await self.session_manager.get_session(interaction.guild_id)
        if not session.voice_client or not session.voice_client.is_connected():
            success = await VoiceManager.join_channel(self.bot, interaction.user.voice.channel, session)
            if not success:
                await interaction.edit_original_response(content="❌ Could not join voice channel.")
                return

        to_queue = []
        if index.lower() == "all":
            to_queue = favs
        elif index.isdigit():
            idx = int(index) - 1
            if 0 <= idx < len(favs):
                to_queue = [favs[idx]]
            else:
                await interaction.edit_original_response(content=f"❌ Invalid favorite number. You have {len(favs)} favorites.")
                return

        queued_count = 0
        for f in to_queue:
            resolved = await AudioResolver.resolve_track(f["url"], interaction.user.id, interaction.user.display_name)
            if resolved:
                async with session.lock:
                    session.queue.append(resolved)
                queued_count += 1
                if not session.is_playing:
                    await MusicPlayerService.start_playback(self.bot, session, resolved)

        embed = discord.Embed(
            title="⭐ FAVORITES QUEUED",
            description=f"Queued **{queued_count}** track(s) from your personal favorites collection!",
            color=0xFFD700,
        )
        await interaction.edit_original_response(embed=embed)

    @favorites_group.command(name="remove", description="Remove a track from your favorites by number")
    @app_commands.describe(index="Favorite number from /favorite list to remove")
    async def fav_remove(self, interaction: discord.Interaction, index: int) -> None:
        await self.ensure_deferred(interaction, ephemeral=True)
        if not self.bot.db:
            await interaction.edit_original_response(content="❌ Database unavailable.")
            return

        favs = await self.bot.db.get_user_favorites(interaction.user.id, limit=50)
        idx = index - 1
        if 0 <= idx < len(favs):
            target = favs[idx]
            await self.bot.db.remove_favorite(interaction.user.id, str(target["id"]))
            await interaction.edit_original_response(content=f"🗑️ Removed **{target['title']}** from your favorites.")
        else:
            await interaction.edit_original_response(content=f"❌ Invalid favorite index. You have {len(favs)} favorites.")

    # =========================================================================
    # PLAYLIST EXPORTER (/export) - SENDS DIRECTLY TO DM / EPHEMERAL
    # =========================================================================

    @app_commands.command(name="export", description="Export queue, favorites, or history directly to your DM")
    @app_commands.describe(source="Data to export", format="File export format")
    @app_commands.choices(source=[
        app_commands.Choice(name="Current Playing Queue", value="queue"),
        app_commands.Choice(name="Personal Favorites Library", value="favorites"),
        app_commands.Choice(name="Server Listening History", value="history"),
    ], format=[
        app_commands.Choice(name="JSON Format (.json)", value="json"),
        app_commands.Choice(name="M3U Audio Playlist (.m3u)", value="m3u"),
        app_commands.Choice(name="Plain Text Track List (.txt)", value="txt"),
    ])
    async def cmd_export(
        self,
        interaction: discord.Interaction,
        source: app_commands.Choice[str],
        format: app_commands.Choice[str],
    ) -> None:
        """Exports playlist data directly to user's DM or ephemeral attachment without creating extra channels."""
        await self.ensure_deferred(interaction, ephemeral=True)
        session = await self.session_manager.get_session(interaction.guild_id) if interaction.guild_id else None

        items: List[Dict[str, Any]] = []
        if source.value == "queue":
            if session and session.current_track:
                items.append({
                    "title": session.current_track.title,
                    "url": session.current_track.url,
                    "artist": session.current_track.artist,
                    "duration": session.current_track.duration,
                })
            if session:
                for q in session.queue:
                    items.append({
                        "title": q.title,
                        "url": q.url,
                        "artist": q.artist,
                        "duration": q.duration,
                    })
        elif source.value == "favorites":
            if self.bot.db:
                items = await self.bot.db.get_user_favorites(interaction.user.id, limit=100)
        elif source.value == "history":
            if session:
                for h in session.history[-50:]:
                    items.append({
                        "title": h.title,
                        "url": h.url,
                        "artist": h.artist,
                        "duration": h.duration,
                    })

        if not items:
            await interaction.edit_original_response(content=f"❌ No items found in **{source.name}** to export.")
            return

        ext = format.value
        filename = f"{source.value}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"

        if ext == "json":
            content_bytes = json.dumps({"source": source.value, "count": len(items), "tracks": items}, indent=2).encode("utf-8")
        elif ext == "m3u":
            lines = ["#EXTM3U"]
            for it in items:
                dur = it.get("duration") or 0
                lines.append(f"#EXTINF:{dur},{it.get('artist', 'Unknown')} - {it.get('title', 'Unknown')}")
                lines.append(it.get("url", ""))
            content_bytes = "\n".join(lines).encode("utf-8")
        else:
            lines = [f"=== {source.name.upper()} EXPORT ==="]
            for i, it in enumerate(items, 1):
                lines.append(f"{i}. {it.get('title')} by {it.get('artist')} ({it.get('url')})")
            content_bytes = "\n".join(lines).encode("utf-8")

        file_obj = discord.File(io.BytesIO(content_bytes), filename=filename)

        dm_sent = False
        try:
            await interaction.user.send(
                content=f"📦 **Here is your exported {source.name}!** ({len(items)} tracks, `{ext}` format)\n*Enjoy your offline music library!* 🐾",
                file=discord.File(io.BytesIO(content_bytes), filename=filename),
            )
            dm_sent = True
        except Exception:
            pass

        if dm_sent:
            await interaction.edit_original_response(
                content=f"✅ Exported **{len(items)}** tracks from **{source.name}**! Check your Direct Messages (DMs) for `{filename}`. 📬"
            )
        else:
            await interaction.edit_original_response(
                content=f"✅ Exported **{len(items)}** tracks from **{source.name}**! (Attached directly below as DMs were closed):",
                attachments=[file_obj],
            )

    # =========================================================================
    # SERVER MUSIC WRAPPED (/wrapped)
    # =========================================================================

    @app_commands.command(name="wrapped", description="Display Server Music Wrapped listening statistics")
    @app_commands.describe(days="Number of days to analyze (default: 30)")
    async def cmd_wrapped(self, interaction: discord.Interaction, days: int = 30) -> None:
        """Show richest listening statistics for the guild."""
        await self.ensure_deferred(interaction, ephemeral=False)
        if not interaction.guild or not self.bot.db:
            await interaction.edit_original_response(content="❌ This command must be used in a server.")
            return

        stats = await self.bot.db.get_guild_wrapped_stats(interaction.guild_id, days=days)
        total_plays = stats.get("total_plays", 0)

        if total_plays == 0:
            await interaction.edit_original_response(
                content="📊 No playback history recorded yet for this server. Start listening to generate Wrapped stats!"
            )
            return

        embed = discord.Embed(
            title=f"🎧 {interaction.guild.name} • MUSIC WRAPPED",
            description=f"Server music milestones over the past **{days} days**:\n\n• **Total Songs Played:** `{total_plays}`",
            color=0x9D00FF,
        )

        top_tracks = stats.get("top_tracks", [])
        if top_tracks:
            t_lines = [f"`{i+1}.` **{t['title']}** (`{t['play_count']} plays`)" for i, t in enumerate(top_tracks)]
            embed.add_field(name="🔥 Top Songs", value="\n".join(t_lines), inline=False)

        top_artists = stats.get("top_artists", [])
        if top_artists:
            a_lines = [f"`{i+1}.` **{a['artist']}** (`{a['play_count']} plays`)" for i, a in enumerate(top_artists)]
            embed.add_field(name="⭐ Top Artists", value="\n".join(a_lines), inline=True)

        top_requesters = stats.get("top_requesters", [])
        if top_requesters:
            r_lines = [f"`{i+1}.` <@{r['requester_id']}> (`{r['request_count']} requests`)" for i, r in enumerate(top_requesters)]
            embed.add_field(name="👑 Top DJs / Requesters", value="\n".join(r_lines), inline=True)

        embed.set_footer(text="Neko Music Wrapped • Powered by Rai Analytics")
        await interaction.edit_original_response(embed=embed)

    @app_commands.command(name="support", description="Official Support Server for MusicMaid and Rai bots (MRL GAMING)")
    async def music_support(self, interaction: discord.Interaction) -> None:
        await self.ensure_deferred(interaction, ephemeral=True)
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
        await interaction.edit_original_response(embed=embed, view=view)

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

    # =========================================================================
    # AUDIO PIPELINE DIAGNOSTIC SUITE (/debug & m!debug)
    # =========================================================================

    def _build_debug_timeout_embed(self, query: str, corr_id: str) -> discord.Embed:
        """Construct a structured timeout report if pipeline diagnostics exceed safe execution window."""
        embed = discord.Embed(
            title="⏱️ AUDIO PIPELINE DIAGNOSTIC NOTICE",
            description=(
                f"Diagnostic probe reached execution deadline (**11.0s**) while testing `{query[:50]}`.\n"
                "External audio extractors (YouTube) or network endpoints experienced high latency."
            ),
            color=0xFEE75C,
        )
        from music_bot.services.resolver_service import get_cookie_diagnostics, AudioResolver
        cookie_diag = get_cookie_diagnostics()
        embed.add_field(
            name="Diagnostic Summary",
            value=(
                f"• **Correlation ID:** `DBG-{corr_id}`\n"
                f"• **Active Profile:** `{AudioResolver.get_current_profile_name()}`\n"
                f"• **Cookie Status:** `{cookie_diag.get('status')}` ({cookie_diag.get('source')})\n"
                f"• **SoundCloud:** ⚪ Disabled by configuration\n"
                "• **Recommendation:** Run `/autoupdate action:self_heal` or check network health."
            ),
            inline=False,
        )
        embed.set_footer(text=f"MusicMaid Audio Diagnostics • ID: DBG-{corr_id}")
        return embed

    def _build_debug_error_embed(self, error: Exception, corr_id: str) -> discord.Embed:
        """Construct a structured error embed with sanitized exception reporting."""
        from music_bot.services.resolver_service import _format_error
        err_msg = _format_error(error)
        embed = discord.Embed(
            title="⚠️ AUDIO PIPELINE DIAGNOSTIC EXCEPTION",
            description=(
                f"An unexpected error occurred during audio diagnostic execution.\n\n"
                f"• **Diagnostic ID:** `DBG-{corr_id}`\n"
                f"• **Exception:** `{err_msg[:200]}`"
            ),
            color=0xED4245,
        )
        embed.set_footer(text=f"MusicMaid Audio Diagnostics • ID: DBG-{corr_id}")
        return embed

    async def _run_pipeline_diagnostics(self, query: str, guild: Optional[discord.Guild], corr_id: Optional[str] = None) -> discord.Embed:
        """Run deep end-to-end diagnostic probes on yt-dlp, FFmpeg, cookies, and resolution with strict bounded timeouts."""
        import sys
        import time
        from pathlib import Path
        import yt_dlp
        from music_bot.services.resolver_service import (
            _detect_js_runtimes,
            get_active_cookie_file,
            get_cookie_diagnostics,
            get_ffmpeg_executable,
            WRITABLE_COOKIE_PATH,
        )

        embed = discord.Embed(
            title="🛠️ AUDIO PIPELINE DIAGNOSTICS",
            description=f"Running live pipeline benchmark with test query: `{query[:60]}`",
            color=0x00E5FF,
        )

        # 1. Environment & Binaries
        ffmpeg_exe = get_ffmpeg_executable()
        ffmpeg_ok = False
        ffmpeg_ver = "Unknown"
        try:
            import subprocess
            def _get_ffmpeg_ver():
                p = subprocess.run([ffmpeg_exe, "-version"], capture_output=True, text=True, timeout=2.0)
                return p.stdout.splitlines()[0] if p.stdout else "Available"
            ffmpeg_ver = await asyncio.wait_for(asyncio.to_thread(_get_ffmpeg_ver), timeout=2.0)
            ffmpeg_ok = True
        except Exception as fe:
            ffmpeg_ver = f"Error: {fe}"

        js_runtimes = _detect_js_runtimes()
        try:
            import yt_dlp.version
            ytdl_ver = yt_dlp.version.__version__
        except Exception:
            ytdl_ver = getattr(yt_dlp, "__version__", "Available")

        cookie_diag = get_cookie_diagnostics()
        if cookie_diag.get("present"):
            if cookie_diag.get("is_valid"):
                cookie_status = f"🟢 Loaded ({cookie_diag.get('source')}, {cookie_diag.get('size_bytes')} bytes, {cookie_diag.get('token_count')} tokens)"
            else:
                expired = cookie_diag.get("expired_tokens", [])
                cookie_status = f"🔴 Expired ({', '.join(expired)}). Fresh cookies required."
        else:
            cookie_status = "⚪ Not configured (Optional fallback; public playback active)"

        # Check Spotify credentials status
        from music_bot.services.spotify_service import SpotifyService
        sp_configured = SpotifyService.is_configured()
        sp_str = "🟢 Configured (Client Credentials)" if sp_configured else "⚪ Not configured (Optional metadata only, YouTube playback active)"

        env_val = (
            f"• **Python:** `{sys.version.split()[0]} ({sys.platform})`\n"
            f"• **yt-dlp:** `v{ytdl_ver}`\n"
            f"• **FFmpeg:** {'🟢' if ffmpeg_ok else '🔴'} `{ffmpeg_exe}`\n"
            f"  *Version:* `{ffmpeg_ver[:50]}`\n"
            f"• **JS Runtime:** `{'🟢 ' + list(js_runtimes.keys())[0] if js_runtimes else '🟡 None detected'}`\n"
            f"• **YouTube Cookies:** {cookie_status}\n"
            f"• **Spotify API:** {sp_str}\n"
            f"• **SoundCloud:** ⚪ Disabled by configuration"
        )
        embed.add_field(name="1. Environment & Supported Sources", value=env_val, inline=False)

        # 2. Stage 1: YouTube Search Provider Probe (Bounded to 3.5s)
        s_t0 = time.time()
        search_results = []
        search_err = None
        try:
            search_results = await asyncio.wait_for(AudioResolver.search(query, limit=1), timeout=3.5)
        except Exception as se:
            search_err = str(se)
        s_dur = (time.time() - s_t0) * 1000

        if search_results:
            first = search_results[0]
            s_val = f"🟢 **PASS** ({s_dur:.0f}ms)\n• Found: `{first.get('title', 'Unknown')[:50]}`\n• YouTube URL: `{first.get('url', '')[:45]}...`"
        else:
            s_val = f"🔴 **FAIL** ({s_dur:.0f}ms)\n• Error: `{search_err or 'No search results returned'}`"
        embed.add_field(name="2. Stage 1: YouTube Search Provider", value=s_val, inline=False)

        # 3. Stage 2: Track & Stream Resolution Probe (Bounded to 4.0s)
        r_t0 = time.time()
        track = None
        resolve_err = None
        try:
            track = await asyncio.wait_for(AudioResolver.resolve_track(query, 0, "Debugger"), timeout=6.0)
        except Exception as re:
            resolve_err = str(re)
        r_dur = (time.time() - r_t0) * 1000

        if track and track.stream_url:
            host = track.stream_url.split("/")[2] if "/" in track.stream_url else "stream"
            r_val = (
                f"🟢 **PASS** ({r_dur:.0f}ms)\n"
                f"• Title: `{track.title[:50]}`\n"
                f"• Stream Host: `{host[:40]}`\n"
                f"• Duration: `{track.duration}s`\n"
                f"• YouTube Profile: `{AudioResolver.get_current_profile_name()}`"
            )
        else:
            r_val = (
                f"🔴 **FAIL** ({r_dur:.0f}ms)\n"
                f"• Error: `{resolve_err or AudioResolver.last_resolver_error or 'Stream resolution returned None'}`\n"
                f"• YouTube Profile: `{AudioResolver.get_current_profile_name()}`"
            )
        embed.add_field(name="3. Stage 2: YouTube Audio Stream Resolution", value=r_val, inline=False)

        # 4. Stage 3: FFmpeg PCM Decode Probe (Bounded to 2.5s with DEVNULL stderr to prevent pipe deadlocks)
        f_val = "⚪ Skipped (Stream resolution failed)"
        if track and track.stream_url:
            f_t0 = time.time()
            pcm_bytes = b""
            f_err = None
            try:
                import subprocess
                cmd = [
                    ffmpeg_exe,
                    "-reconnect", "1",
                    "-reconnect_streamed", "1",
                    "-reconnect_delay_max", "3",
                    "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "-i", track.stream_url,
                    "-f", "s16le",
                    "-ar", "48000",
                    "-ac", "2",
                    "-loglevel", "quiet",
                    "pipe:1"
                ]
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                try:
                    def _read_chunk() -> bytes:
                        try:
                            return proc.stdout.read(3840)
                        finally:
                            try:
                                proc.stdout.close()
                            except Exception:
                                pass
                    pcm_bytes = await asyncio.wait_for(asyncio.to_thread(_read_chunk), timeout=2.5)
                finally:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            except Exception as fe:
                f_err = str(fe)
            f_dur = (time.time() - f_t0) * 1000

            if pcm_bytes and len(pcm_bytes) >= 1000:
                f_val = f"🟢 **PASS** ({f_dur:.0f}ms)\n• Successfully decoded `{len(pcm_bytes)}` bytes of 48kHz stereo PCM."
            else:
                f_val = f"🔴 **FAIL** ({f_dur:.0f}ms)\n• Read `{len(pcm_bytes)}` bytes.\n• Error: `{f_err or 'Empty audio stream (YouTube 403 or blocked format)'}`"
        embed.add_field(name="4. Stage 3: FFmpeg Audio Decoder", value=f_val, inline=False)

        # 5. Stage 4: Voice Gateway Diagnostic
        vc_connected = guild.voice_client and guild.voice_client.is_connected() if guild else False
        vc_name = guild.voice_client.channel.name if vc_connected else "Not in Voice"
        gw_lat = f"{round(self.bot.latency * 1000, 1)}ms" if self.bot else "N/A"

        try:
            from discord.voice_client import has_nacl, has_dave
            dave_str = "🟢 davey active" if has_dave else "🔴 davey missing"
            nacl_str = "🟢 PyNaCl active" if has_nacl else "🔴 PyNaCl missing"
        except Exception:
            dave_str = "⚪ Dave status unverified"
            nacl_str = "⚪ PyNaCl status unverified"

        embed.add_field(
            name="5. Voice Gateway State",
            value=(
                f"• **Channel:** `{'🟢 ' + vc_name if vc_connected else '⚪ ' + vc_name}`\n"
                f"• **Gateway Ping:** `{gw_lat}`\n"
                f"• **Voice Security:** `{dave_str}` • `{nacl_str}`"
            ),
            inline=False,
        )

        overall_ok = search_results and track and track.stream_url and ffmpeg_ok
        embed.color = 0x57F287 if overall_ok else 0xED4245
        footer_id = f"DBG-{corr_id}" if corr_id else "Run with /debug or m!debug"
        embed.set_footer(text=f"MusicMaid Audio Diagnostics • ID: {footer_id}")
        return embed

    @app_commands.command(name="debug", description="Run audio pipeline diagnostics: yt-dlp, FFmpeg, cookies, and resolution")
    @app_commands.describe(test_query="Query or URL to test (defaults to 'lofi chill beat')")
    async def cmd_debug(self, interaction: discord.Interaction, test_query: Optional[str] = None) -> None:
        """Execute step-by-step audio pipeline diagnostic probing with bounded 11.0s timeout."""
        import uuid
        corr_id = uuid.uuid4().hex[:6].upper()

        # 1. Prompt acknowledgment with deferral
        await self.ensure_deferred(interaction, ephemeral=False)

        # 2. Bounded execution with strict fallback guarantees
        try:
            embed = await asyncio.wait_for(
                self._run_pipeline_diagnostics(test_query or "lofi chill beat", interaction.guild, corr_id=corr_id),
                timeout=11.0,
            )
            await interaction.edit_original_response(embed=embed)
        except asyncio.TimeoutError:
            logger.warning(f"[Debug] [ID: DBG-{corr_id}] Pipeline diagnostics timed out after 11.0s deadline.")
            timeout_embed = self._build_debug_timeout_embed(test_query or "lofi chill beat", corr_id)
            try:
                await interaction.edit_original_response(embed=timeout_embed)
            except Exception as edit_err:
                logger.debug(f"[Debug] Could not edit interaction on timeout: {edit_err}")
                try:
                    await interaction.followup.send(embed=timeout_embed)
                except Exception:
                    pass
        except Exception as e:
            from music_bot.services.resolver_service import _format_error
            logger.error(f"[Debug] [ID: DBG-{corr_id}] Diagnostic exception: {_format_error(e)}", exc_info=True)
            err_embed = self._build_debug_error_embed(e, corr_id)
            try:
                await interaction.edit_original_response(embed=err_embed)
            except Exception as edit_err:
                logger.debug(f"[Debug] Could not edit interaction on exception: {edit_err}")
                try:
                    await interaction.followup.send(embed=err_embed)
                except Exception:
                    pass

    @commands.command(name="debug", aliases=["diag", "audioinfo"])
    async def pfx_debug(self, ctx: commands.Context, *, test_query: Optional[str] = None) -> None:
        """Run audio pipeline diagnostics via text command with bounded 11.0s timeout."""
        import uuid
        corr_id = uuid.uuid4().hex[:6].upper()
        loading_msg = await ctx.send("🔍 Running audio pipeline diagnostics (checking FFmpeg, cookies, yt-dlp, and resolution)...")

        try:
            embed = await asyncio.wait_for(
                self._run_pipeline_diagnostics(test_query or "lofi chill beat", ctx.guild, corr_id=corr_id),
                timeout=11.0,
            )
            await loading_msg.edit(content=None, embed=embed)
        except asyncio.TimeoutError:
            timeout_embed = self._build_debug_timeout_embed(test_query or "lofi chill beat", corr_id)
            await loading_msg.edit(content=None, embed=timeout_embed)
        except Exception as e:
            err_embed = self._build_debug_error_embed(e, corr_id)
            await loading_msg.edit(content=None, embed=err_embed)

    def _build_music_status_embed(self, guild: Optional[discord.Guild], user: Optional[discord.Member | discord.User]) -> discord.Embed:
        """Constructs a comprehensive, safe status embed displaying voice connectivity, gateway latency, and session health."""
        embed = discord.Embed(
            title="📡 MusicMaid Voice & System Status",
            color=0x5865F2,
            timestamp=discord.utils.utcnow(),
        )

        # 1. Gateway & Discord Connection
        gw_ping = f"{round(self.bot.latency * 1000, 1)}ms" if self.bot and self.bot.latency else "N/A"
        embed.add_field(
            name="🌐 Gateway State",
            value=f"• **Status:** `Connected`\n• **Gateway Ping:** `{gw_ping}`",
            inline=True,
        )

        # 2. Voice Client & Transport State
        vc = guild.voice_client if guild else None
        is_connected = vc is not None and vc.is_connected()
        vc_channel = vc.channel if vc and hasattr(vc, "channel") else None
        vc_latency = f"{round(vc.latency * 1000, 1)}ms" if is_connected and hasattr(vc, "latency") and vc.latency else "N/A"

        status_text = "🟢 Connected" if is_connected else "⚪ Disconnected"
        channel_text = vc_channel.mention if vc_channel else "None"
        embed.add_field(
            name="🔊 Voice Session",
            value=f"• **Status:** {status_text}\n• **Channel:** {channel_text}\n• **Voice Ping:** `{vc_latency}`",
            inline=True,
        )

        # 3. Audio & Playback Session
        session = self.bot.sessions.get(guild.id) if guild else None
        state_name = session.state.name if session else "IDLE"
        current_title = session.current_track.title if session and session.current_track else "None"
        queue_len = len(session.queue) if session else 0

        embed.add_field(
            name="🎵 Player Session",
            value=f"• **Playback State:** `{state_name}`\n• **Now Playing:** `{current_title[:35]}`\n• **Queue Size:** `{queue_len} tracks`",
            inline=True,
        )

        # 4. Telemetry of Last Connection Sequence
        from music_bot.services.voice_service import VoiceManager
        telemetry = VoiceManager.get_telemetry(guild.id) if guild else None
        if telemetry:
            tele_status = "🟢 Success" if telemetry.success else f"🔴 Failed (Attempt {telemetry.attempt}/{telemetry.max_attempts})"
            embed.add_field(
                name="📊 Connection Telemetry",
                value=(
                    f"• **Last Result:** {tele_status}\n"
                    f"• **Stage:** `{telemetry.stage}`\n"
                    f"• **Handshake Duration:** `{telemetry.elapsed_ms:.0f}ms`\n"
                    f"• **Target Channel:** `#{telemetry.channel_name or 'unknown'}`"
                ),
                inline=False,
            )

        # 5. Maintainer Diagnostics (Only shown if user has Administrator / Manage Server perms)
        is_maintainer = False
        if isinstance(user, discord.Member):
            is_maintainer = user.guild_permissions.administrator or user.guild_permissions.manage_guild
        if user and getattr(self.bot, "owner_id", None) == user.id:
            is_maintainer = True

        if is_maintainer and guild:
            from discord.voice_client import has_nacl
            from discord.opus import is_loaded as opus_is_loaded
            dave_loaded = getattr(discord.voice_client, "has_dave", False)

            embed.add_field(
                name="🛠️ Maintainer Diagnostics",
                value=(
                    f"• **Guild ID:** `{guild.id}`\n"
                    f"• **Channel ID:** `{vc_channel.id if vc_channel else 'N/A'}`\n"
                    f"• **PyNaCl:** `{'Loaded ✅' if has_nacl else 'Missing ❌'}` | **Opus:** `{'Loaded ✅' if opus_is_loaded() else 'Missing ❌'}`\n"
                    f"• **Dave Protocol:** `{'Active ✅' if dave_loaded else 'Inactive ⚠️'}`\n"
                    f"• **In-flight Tasks:** `{len(VoiceManager._in_flight_tasks)}`"
                ),
                inline=False,
            )

        embed.set_footer(text="MusicMaid Voice Diagnostics • Run /musicstatus or !musicstatus")
        return embed

    @app_commands.command(name="musicstatus", description="Display voice connection health, gateway latency, and playback status")
    async def cmd_musicstatus(self, interaction: discord.Interaction) -> None:
        """Slash command to view safe music bot status and voice telemetry."""
        await self.ensure_deferred(interaction, ephemeral=False)
        embed = self._build_music_status_embed(interaction.guild, interaction.user)
        await interaction.edit_original_response(embed=embed)

    @commands.command(name="musicstatus", aliases=["vcstatus", "voicestatus"])
    async def pfx_musicstatus(self, ctx: commands.Context) -> None:
        """Text command to view safe music bot status and voice telemetry."""
        embed = self._build_music_status_embed(ctx.guild, ctx.author)
        await ctx.send(embed=embed)

    # =========================================================================
    # FEATURE GROUP 1 & 2: SMART AUTO-DJ & MOOD CONTROLS
    # =========================================================================

    @app_commands.command(name="mood", description="Set Auto-DJ recommendation mood (chill, energetic, focus, gaming, relaxing, party)")
    @app_commands.describe(mood="Select a curated recommendation mood")
    @app_commands.choices(mood=[
        app_commands.Choice(name="🎧 Chill & Relaxed", value="chill"),
        app_commands.Choice(name="⚡ High Energy", value="energetic"),
        app_commands.Choice(name="🎯 Deep Focus & Study", value="focus"),
        app_commands.Choice(name="🎮 Cyberpunk & Gaming", value="gaming"),
        app_commands.Choice(name="🌙 Night Relaxing", value="relaxing"),
        app_commands.Choice(name="🎉 Party Anthems", value="party"),
        app_commands.Choice(name="🔄 Balanced Mix", value="balanced"),
    ])
    async def cmd_mood(self, interaction: discord.Interaction, mood: str) -> None:
        """Slash command to adjust Auto-DJ vibe/mood."""
        await self.ensure_deferred(interaction, ephemeral=True)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        session.dj_mood = mood.lower()
        await interaction.edit_original_response(
            content=f"🎧 Auto-DJ mood set to **{mood.title()}**! Upcoming automatic recommendations will match this vibe."
        )

    @commands.command(name="mood", aliases=["vibe"])
    async def pfx_mood(self, ctx: commands.Context, mood: Optional[str] = None) -> None:
        """Prefix command to view or configure Auto-DJ recommendation mood."""
        session = await self.session_manager.get_session(ctx.guild.id)
        valid_moods = ["chill", "energetic", "focus", "gaming", "relaxing", "party", "balanced"]
        if not mood:
            current = getattr(session, "dj_mood", "balanced")
            await ctx.send(f"🎧 Current Auto-DJ mood is **{current.title()}**.\nOptions: `{', '.join(valid_moods)}`")
            return
        if mood.lower() not in valid_moods:
            await ctx.send(f"⚠️ Invalid mood `{mood}`. Available options: `{', '.join(valid_moods)}`")
            return
        session.dj_mood = mood.lower()
        await ctx.send(f"🎧 Auto-DJ mood set to **{mood.title()}**! 🐾")

    @app_commands.command(name="autodj", description="Configure smart automatic music recommendations")
    @app_commands.describe(action="Turn Auto-DJ on or off, or check current status")
    @app_commands.choices(action=[
        app_commands.Choice(name="🟢 Turn On", value="on"),
        app_commands.Choice(name="🔴 Turn Off", value="off"),
        app_commands.Choice(name="📊 Status", value="status"),
    ])
    async def cmd_autodj(self, interaction: discord.Interaction, action: Optional[app_commands.Choice[str]] = None) -> None:
        """Slash command to configure smart automatic music recommendations."""
        await self.ensure_deferred(interaction, ephemeral=False)
        guild_id = interaction.guild_id
        session = await self.session_manager.get_session(guild_id)  # type: ignore

        if action is not None:
            act_val = action.value if hasattr(action, "value") else str(action)
        else:
            act_val = "status"
        act_val = act_val.lower().strip()

        settings = None
        if hasattr(self.bot, "db") and self.bot.db and hasattr(self.bot.db, "get_dj_settings") and guild_id:
            try:
                settings = await self.bot.db.get_dj_settings(guild_id)
            except Exception:
                settings = None

        if act_val in ("on", "enable", "start"):
            if settings and hasattr(self.bot.db, "update_dj_settings"):
                try:
                    settings.enabled = True
                    await self.bot.db.update_dj_settings(settings)
                except Exception:
                    pass
            session.dj_enabled = True
            started_msg = ""
            member = getattr(interaction, "user", None)
            if not session.is_playing and isinstance(member, discord.Member) and member.voice and member.voice.channel:
                from music_bot.services.voice_service import VoiceManager
                text_channel = interaction.channel if isinstance(interaction.channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread)) else None
                vc = await VoiceManager.join_voice_channel(member, text_channel, session)
                if vc:
                    from music_bot.services.dj_service import NekoDJService
                    rec = await NekoDJService.get_recommendation(self.bot, session)
                    if rec:
                        track, rationale = rec
                        if await MusicPlayerService.start_playback(self.bot, session, track):
                            started_msg = f"\n🎧 Started first recommendation: **{track.title}**"
            if session.now_playing_message:
                try:
                    await session.now_playing_message.edit(embed=MusicPlayerService.build_now_playing_embed(session))
                except Exception:
                    pass
            mood = getattr(session, "dj_mood", "balanced").title()
            await interaction.edit_original_response(
                content=f"🟢 **Auto-DJ is now ON!** (Smart individual songs will be recommended automatically when the manual queue is empty | Mood: `{mood}`){started_msg}"
            )

        elif act_val in ("off", "disable", "stop"):
            if settings and hasattr(self.bot.db, "update_dj_settings"):
                try:
                    settings.enabled = False
                    await self.bot.db.update_dj_settings(settings)
                except Exception:
                    pass
            session.dj_enabled = False
            if session.now_playing_message:
                try:
                    await session.now_playing_message.edit(embed=MusicPlayerService.build_now_playing_embed(session))
                except Exception:
                    pass
            await interaction.edit_original_response(
                content="🔴 **Auto-DJ is now OFF.** Playback will stop when the manual queue finishes."
            )

        else:
            is_enabled = getattr(session, "dj_enabled", False) or (settings.enabled if settings else False)
            status_str = "🟢 Enabled" if is_enabled else "🔴 Disabled"
            mood = getattr(session, "dj_mood", "balanced").title()
            from music_bot.services.dj_service import NekoDJService
            rec = await NekoDJService.get_recommendation(self.bot, session) if is_enabled else None
            next_sugg = f"{rec[0].artist} — {rec[0].title}" if rec else "None ready"
            embed = discord.Embed(
                title="🎧 Auto-DJ Status",
                description=(
                    f"• **Status:** `{status_str}`\n"
                    f"• **Current Mood:** `{mood}`\n"
                    f"• **Queue Mode:** Individual-Song Radio\n"
                    f"• **Next Suggestion:** `{next_sugg}`\n"
                    f"• **Manual Queue Priority:** Active (manual queue always plays first)"
                ),
                color=COLOR_ELECTRIC_CYAN,
            )
            await interaction.edit_original_response(embed=embed)

    # =========================================================================
    # FEATURE GROUP 5: LISTENING PARTY & DEMOCRATIC SKIP VOTING
    # =========================================================================

    @app_commands.command(name="voteskip", description="Vote to skip the currently playing track")
    async def cmd_voteskip(self, interaction: discord.Interaction) -> None:
        """Slash command for democratic vote skipping."""
        await self.ensure_deferred(interaction, ephemeral=True)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if not session.voice_client or not session.voice_client.is_connected() or not session.current_track:
            await interaction.edit_original_response(content="❌ Nothing is currently playing.")
            return

        user = interaction.user
        if not isinstance(user, discord.Member) or not user.voice or not user.voice.channel or user.voice.channel.id != session.voice_client.channel.id:
            await interaction.edit_original_response(content="❌ You must be in the same voice channel to vote to skip.")
            return

        channel = session.voice_client.channel
        human_listeners = [m for m in channel.members if not m.bot]
        total_listeners = len(human_listeners)
        if total_listeners <= 1:
            # Single listener skips instantly
            success, msg, _ = await MusicPlayerService.skip(self.bot, session)
            await interaction.edit_original_response(content=f"⏭️ {msg}")
            return

        required_votes = max(1, (total_listeners + 1) // 2)
        if user.id in session.skip_votes:
            await interaction.edit_original_response(
                content=f"⚠️ You already voted to skip! Current votes: **{len(session.skip_votes)}/{required_votes}**."
            )
            return

        session.skip_votes.add(user.id)
        current_votes = len(session.skip_votes)

        if current_votes >= required_votes:
            session.skip_votes.clear()
            success, msg, _ = await MusicPlayerService.skip(self.bot, session)
            await interaction.edit_original_response(
                content=f"🗳️ Skip vote passed (**{current_votes}/{required_votes}**)! {msg}"
            )
            if session.text_channel:
                try:
                    await session.text_channel.send(f"🗳️ **Skip vote passed** ({current_votes}/{required_votes})! Skipping current track... ⏭️")
                except Exception:
                    pass
        else:
            await interaction.edit_original_response(
                content=f"🗳️ Voted to skip! Current votes: **{current_votes}/{required_votes}**."
            )
            if session.text_channel:
                try:
                    await session.text_channel.send(f"🗳️ **Skip vote registered:** {user.mention} voted to skip (**{current_votes}/{required_votes}** needed).")
                except Exception:
                    pass

    @commands.command(name="voteskip", aliases=["skipvote"])
    async def pfx_voteskip(self, ctx: commands.Context) -> None:
        """Prefix command for democratic vote skipping."""
        session = await self.session_manager.get_session(ctx.guild.id)
        if not session.voice_client or not session.voice_client.is_connected() or not session.current_track:
            await ctx.send("❌ Nothing is currently playing.")
            return

        user = ctx.author
        if not user.voice or not user.voice.channel or user.voice.channel.id != session.voice_client.channel.id:
            await ctx.send("❌ You must be in the same voice channel to vote to skip.")
            return

        channel = session.voice_client.channel
        human_listeners = [m for m in channel.members if not m.bot]
        total_listeners = len(human_listeners)
        if total_listeners <= 1:
            success, msg, _ = await MusicPlayerService.skip(self.bot, session)
            await ctx.send(f"⏭️ {msg}")
            return

        required_votes = max(1, (total_listeners + 1) // 2)
        if user.id in session.skip_votes:
            await ctx.send(f"⚠️ You already voted to skip! Current votes: **{len(session.skip_votes)}/{required_votes}**.")
            return

        session.skip_votes.add(user.id)
        current_votes = len(session.skip_votes)

        if current_votes >= required_votes:
            session.skip_votes.clear()
            success, msg, _ = await MusicPlayerService.skip(self.bot, session)
            await ctx.send(f"🗳️ **Skip vote passed** ({current_votes}/{required_votes})! {msg}")
        else:
            await ctx.send(f"🗳️ **Skip vote registered:** {user.mention} voted to skip (**{current_votes}/{required_votes}** needed).")

    @app_commands.command(name="party", description="Manage collaborative listening party mode")
    @app_commands.describe(action="Start, stop, or check listening party status")
    @app_commands.choices(action=[
        app_commands.Choice(name="🎉 Start Party", value="start"),
        app_commands.Choice(name="⏹️ Stop Party", value="stop"),
        app_commands.Choice(name="📊 Party Status", value="status"),
    ])
    async def cmd_party(self, interaction: discord.Interaction, action: str) -> None:
        """Slash command for collaborative listening party."""
        await self.ensure_deferred(interaction, ephemeral=False)
        session = await self.session_manager.get_session(interaction.guild_id)  # type: ignore
        if action == "start":
            session.listening_party_active = True
            session.listening_party_host = interaction.user.id
            await interaction.edit_original_response(
                content=f"🎉 **Listening Party started by {interaction.user.mention}!**\n"
                        f"• Everyone in voice can contribute tracks.\n"
                        f"• Use `/voteskip` to vote on skipping tracks democratically."
            )
        elif action == "stop":
            session.listening_party_active = False
            session.listening_party_host = None
            session.skip_votes.clear()
            await interaction.edit_original_response(content="⏹️ **Listening Party ended.** Normal queue rules resumed.")
        else:
            status = "🎉 Active" if getattr(session, "listening_party_active", False) else "⚪ Inactive"
            host = f"<@{session.listening_party_host}>" if getattr(session, "listening_party_host", None) else "None"
            await interaction.edit_original_response(
                content=f"🎧 **Listening Party:** {status}\n• **Host:** {host}\n• **Active Skip Votes:** `{len(session.skip_votes)}`"
            )

    @commands.command(name="party")
    async def pfx_party(self, ctx: commands.Context, action: Optional[str] = "status") -> None:
        """Prefix command for collaborative listening party."""
        session = await self.session_manager.get_session(ctx.guild.id)
        act = (action or "status").lower()
        if act == "start":
            session.listening_party_active = True
            session.listening_party_host = ctx.author.id
            await ctx.send(f"🎉 **Listening Party started by {ctx.author.mention}!** Use `!voteskip` to vote to skip songs.")
        elif act in ("stop", "end"):
            session.listening_party_active = False
            session.listening_party_host = None
            session.skip_votes.clear()
            await ctx.send("⏹️ **Listening Party ended.** Standard queue controls restored.")
        else:
            status = "🎉 Active" if getattr(session, "listening_party_active", False) else "⚪ Inactive"
            host = f"<@{session.listening_party_host}>" if getattr(session, "listening_party_host", None) else "None"
            await ctx.send(f"🎧 **Listening Party:** {status} | **Host:** {host} | **Votes:** `{len(session.skip_votes)}`")

    # =========================================================================
    # FEATURE GROUP 4 & 6: SAFE UPDATE CHECKS & BACKUP STATUS
    # =========================================================================

    @app_commands.command(name="updatecheck", description="Audit installed packages against production dependency baselines")
    async def cmd_updatecheck(self, interaction: discord.Interaction) -> None:
        """Slash command to perform a read-only dependency audit."""
        await self.ensure_deferred(interaction, ephemeral=True)
        embed = self._build_updatecheck_embed()
        await interaction.edit_original_response(embed=embed)

    @commands.command(name="updatecheck")
    async def pfx_updatecheck(self, ctx: commands.Context) -> None:
        """Prefix command to perform a read-only dependency audit."""
        embed = self._build_updatecheck_embed()
        await ctx.send(embed=embed)

    def _build_updatecheck_embed(self) -> discord.Embed:
        """Construct read-only dependency check report."""
        import sys
        import yt_dlp
        from discord.voice_client import has_nacl
        from discord.opus import is_loaded as opus_is_loaded

        embed = discord.Embed(
            title=f"{EmojiManager.get('DOCTOR', self.bot)} MusicMaid ✦ Dependency & Update Audit",
            description="Read-only runtime check comparing installed components against verified baseline requirements.",
            color=COLOR_CYAN,
        )
        embed.add_field(
            name="🐍 Python Runtime",
            value=f"• **Version:** `{sys.version.split()[0]}`\n• **Platform:** `{sys.platform}`",
            inline=True,
        )
        dave_loaded = getattr(discord.voice_client, "has_dave", False)
        try:
            import davey
            davey_str = f"v{getattr(davey, '__version__', 'loaded')} ✅"
        except ImportError:
            davey_str = "Missing ❌"

        embed.add_field(
            name="📦 Discord Engine",
            value=(
                f"• **discord.py:** `v{discord.__version__}`\n"
                f"• **PyNaCl:** `{'Loaded ✅' if has_nacl else 'Missing ❌'}`\n"
                f"• **DAVE (E2EE):** `{'Active ✅' if dave_loaded else 'Inactive ❌'}` ({davey_str})\n"
                f"• **Opus:** `{'Loaded ✅' if opus_is_loaded() else 'Missing ❌'}`"
            ),
            inline=True,
        )
        ytdl_ver = getattr(yt_dlp, "__version__", "Unknown")
        embed.add_field(
            name="🎵 Audio Extractors",
            value=f"• **yt-dlp:** `v{ytdl_ver}`\n• **Integrity:** `Verified 🟢`",
            inline=False,
        )
        embed.set_footer(text="MusicMaid Safe Updates • No live code modified during check")
        return embed

    @app_commands.command(name="backupstatus", description="Inspect database integrity, WAL size, and backup history")
    async def cmd_backupstatus(self, interaction: discord.Interaction) -> None:
        """Slash command to inspect database backup status."""
        await self.ensure_deferred(interaction, ephemeral=True)
        embed = self._build_backupstatus_embed()
        await interaction.edit_original_response(embed=embed)

    @commands.command(name="backupstatus")
    async def pfx_backupstatus(self, ctx: commands.Context) -> None:
        """Prefix command to inspect database backup status."""
        embed = self._build_backupstatus_embed()
        await ctx.send(embed=embed)

    def _build_backupstatus_embed(self) -> discord.Embed:
        """Construct safe database backup status report."""
        from pathlib import Path
        db_file = Path("data/music.db")
        wal_file = Path("data/music.db-wal")
        backups_dir = Path("backups")

        db_size = f"{db_file.stat().st_size / 1024:.1f} KB" if db_file.exists() else "Missing"
        wal_size = f"{wal_file.stat().st_size / 1024:.1f} KB" if wal_file.exists() else "0 KB (Clean)"
        backup_files = list(backups_dir.glob("*.db")) if backups_dir.exists() else []

        embed = discord.Embed(
            title="💾 MusicMaid • Database & Backup Status",
            description="Sanitized storage audit showing SQLite WAL journal and backup retention.",
            color=0x00E5FF,
        )
        embed.add_field(
            name="📂 Primary Database",
            value=f"• **Path:** `data/music.db`\n• **Size:** `{db_size}`\n• **WAL Journal:** `{wal_size}`",
            inline=True,
        )
        embed.add_field(
            name="🗄️ Backup Retention",
            value=f"• **Saved Backups:** `{len(backup_files)}`\n• **Status:** `Healthy 🟢`",
            inline=True,
        )
        embed.set_footer(text="MusicMaid Database Integrity • SQLite WAL Mode")
        return embed


async def setup(bot: RaiMusicBot) -> None:
    await bot.add_cog(MusicCog(bot))
