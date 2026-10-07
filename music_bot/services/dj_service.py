"""
Neko DJ Recommendation Engine and Auto-Queue Supervisor.
Proactively manages queue transitions, generates metadata-based recommendations,
and displays interactive recommendation cards.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import discord

from music_bot.config import (
    COLOR_ELECTRIC_CYAN,
    COLOR_MIDNIGHT_BLACK,
    COLOR_NEON_BLUE,
)
from music_bot.database.models import QueuedTrack
from music_bot.services.resolver_service import AudioResolver
from music_bot.services.session_service import GuildMusicSession

if TYPE_CHECKING:
    from music_bot.bot import RaiMusicBot

logger = logging.getLogger("RaiMusic.DJ")


class DJRecommendationCardView(discord.ui.View):
    """Interactive action buttons for Neko DJ recommendation card."""

    def __init__(self, bot: RaiMusicBot, session: GuildMusicSession, track: QueuedTrack):
        super().__init__(timeout=60.0)
        self.bot = bot
        self.session = session
        self.track = track

    @discord.ui.button(emoji="➕", label="Add to Queue", style=discord.ButtonStyle.primary, custom_id="neko_dj_add_queue")
    async def add_queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        async with self.session.lock:
            self.session.queue.append(self.track)
        await interaction.followup.send(f"🐱 Added **{self.track.title}** to the queue!", ephemeral=True)
        self.stop()
        try:
            await interaction.message.delete()
        except Exception:
            pass

    @discord.ui.button(emoji="▶", label="Play Next", style=discord.ButtonStyle.secondary, custom_id="neko_dj_play_next")
    async def play_next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        async with self.session.lock:
            self.session.queue.appendleft(self.track)
        await interaction.followup.send(f"🎵 **{self.track.title}** will play next!", ephemeral=True)
        self.stop()
        try:
            await interaction.message.delete()
        except Exception:
            pass

    @discord.ui.button(emoji="❌", label="Dismiss", style=discord.ButtonStyle.danger, custom_id="neko_dj_dismiss")
    async def dismiss_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        self.stop()
        try:
            await interaction.message.delete()
        except Exception:
            pass


class NekoDJService:
    """Intelligent queue assistant and track recommender."""

    @classmethod
    async def get_recommendation(
        cls, bot: RaiMusicBot, session: GuildMusicSession
    ) -> Optional[tuple[QueuedTrack, str]]:
        """
        Inspect session metadata and find a suitable next track that hasn't
        been played in the recent history window.
        Returns: (QueuedTrack, rationale_string)
        """
        base_track = session.current_track
        if not base_track and session.history:
            base_track = session.history[-1]

        if not base_track:
            return None

        recent_titles = {h.title.lower() for h in session.history[-15:]}
        if session.current_track:
            recent_titles.add(session.current_track.title.lower())
        for q in session.queue:
            recent_titles.add(q.title.lower())

        artist = base_track.artist if base_track.artist != "Unknown Artist" else None
        search_query = f"{artist} songs" if artist else f"{base_track.title} remix style"
        rationale = f"Similar artist ({artist}) and musical style." if artist else f"Similar theme to '{base_track.title[:30]}'."

        try:
            candidates = await AudioResolver.search(search_query, limit=6)
            for c in candidates:
                if c["title"].lower() in recent_titles:
                    continue

                resolved = await AudioResolver.resolve_track(
                    c["url"], 0, "Neko DJ"
                )
                if resolved:
                    return resolved, rationale
        except Exception as e:
            logger.warning(f"Neko DJ recommendation query failed: {e}")

        return None

    @classmethod
    async def post_recommendation_card(
        cls, bot: RaiMusicBot, session: GuildMusicSession
    ) -> None:
        """Construct and send the official Neko DJ recommendation card."""
        if not session.text_channel:
            return

        rec = await cls.get_recommendation(bot, session)
        if not rec:
            return

        track, rationale = rec
        current_title = session.current_track.title if session.current_track else "End of Queue"
        current_artist = session.current_track.artist if session.current_track else "Recent Tracks"

        embed = discord.Embed(
            title="🎧 NEKO DJ",
            description=(
                f"**Now Playing:**\n`{current_artist}` — **{current_title}**\n\n"
                f"🐱 **Neko recommends:**\n`{track.artist}` — **[{track.title}]({track.url})**\n\n"
                f"**Why:**\n{rationale}"
            ),
            color=COLOR_ELECTRIC_CYAN,
        )
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        embed.set_footer(text="Neko DJ • Smart Music Companion")

        view = DJRecommendationCardView(bot, session, track)
        try:
            await session.text_channel.send(embed=embed, view=view)
        except Exception as e:
            logger.warning(f"Failed to post DJ recommendation card: {e}")
