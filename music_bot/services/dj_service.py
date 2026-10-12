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

    def __init__(
        self,
        bot: RaiMusicBot,
        session: GuildMusicSession,
        track: Optional[QueuedTrack] = None,
        recommended_query: Optional[str] = None,
        reason: Optional[str] = None,
        requester_id: Optional[int] = None,
    ):
        super().__init__(timeout=60.0)
        self.bot = bot
        self.session = session
        self.track = track or QueuedTrack(
            title=recommended_query or "Neko Recommendation",
            url="https://youtube.com",
            duration=180,
            requester_id=requester_id or 0,
            requester_name="Neko DJ",
        )


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
    async def recommend_next_track(cls, session: GuildMusicSession) -> Optional[dict[str, str]]:
        """Inspect session and return recommendation query and reason."""
        base_track = session.current_track
        if not base_track and session.history:
            base_track = session.history[-1]
        if not base_track:
            return None
        artist = base_track.artist if base_track.artist != "Unknown Artist" else None
        query = f"{artist} songs" if artist else f"{base_track.title} mix"
        reason = f"Similar artist ({artist}) and musical style." if artist else "Similar musical style."
        return {"query": query, "reason": reason}

    @classmethod
    async def get_recommendation(
        cls, bot: RaiMusicBot, session: GuildMusicSession
    ) -> Optional[tuple[QueuedTrack, str]]:

        """
        Inspect session metadata and find a suitable next track that hasn't
        been played in recent history. Guaranteed non-stop fallback mechanism.
        Returns: (QueuedTrack, rationale_string)
        """
        base_track = session.current_track
        if not base_track and session.history:
            base_track = session.history[-1]

        recent_titles = {h.title.lower() for h in session.history[-15:]}
        if session.current_track:
            recent_titles.add(session.current_track.title.lower())
        for q in session.queue:
            recent_titles.add(q.title.lower())

        artist = (base_track.artist if base_track and base_track.artist != "Unknown Artist" else None)
        title = base_track.title if base_track else ""

        # Prioritized query hierarchy for continuous infinite variety
        queries_to_try = []
        if artist:
            queries_to_try.append((f"{artist} top tracks songs", f"More top hits by **{artist}**."))
            queries_to_try.append((f"{artist} mix playlist", f"Related artists & styles matching **{artist}**."))
        if title:
            queries_to_try.append((f"{title} radio mix", f"Songs with matching tempo & vibe to **{title[:30]}**."))
            queries_to_try.append((f"{title} style similar songs", f"Curated vibe matching **{title[:30]}**."))

        # Global trending & circadian fallbacks if specific track queries are exhausted
        queries_to_try.append(("trending top viral hits playlist songs", "Trending global hit recommended by Neko DJ."))
        queries_to_try.append(("upbeat energetic party dance hits", "Energetic groove to keep the vibe going."))
        queries_to_try.append(("chill acoustic indie pop focus", "Smooth acoustic flow recommended by Neko DJ."))
        queries_to_try.append(("lofi chill morning beats study", "Relaxing continuous ambient beats."))

        for query, rationale in queries_to_try:
            try:
                candidates = await AudioResolver.search(query, limit=8)
                # First pass: strictly exclude recently played songs
                for c in candidates:
                    if c["title"].lower() in recent_titles:
                        continue
                    resolved = await AudioResolver.resolve_track(c["url"], 0, "Neko DJ Non-Stop")
                    if resolved:
                        return resolved, rationale

                # Second pass: if user exhausted all new songs, allow songs not played in last 3 tracks
                strict_recent = {h.title.lower() for h in session.history[-3:]}
                for c in candidates:
                    if c["title"].lower() in strict_recent:
                        continue
                    resolved = await AudioResolver.resolve_track(c["url"], 0, "Neko DJ Non-Stop")
                    if resolved:
                        return resolved, rationale
            except Exception as e:
                logger.debug(f"Neko DJ candidate probe notice for '{query}': {e}")

        # Ultimate failsafe: resolve dependable stream
        try:
            resolved = await AudioResolver.resolve_track("lofi hip hop radio beats to relax study to", 0, "Neko DJ Non-Stop")
            if resolved:
                return resolved, "Continuous 24/7 Neko DJ radio stream."
        except Exception:
            pass

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
