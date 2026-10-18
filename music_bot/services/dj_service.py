"""
Neko DJ Recommendation Engine and Auto-Queue Supervisor.
Proactively manages queue transitions, generates metadata-based recommendations,
and displays interactive recommendation cards.
"""

from __future__ import annotations

import asyncio
import logging
import re
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
            title=recommended_query or "Recommended Track",
            url="https://youtube.com",
            duration=180,
            requester_id=requester_id or 0,
            requester_name="MusicMaid Auto-DJ",
        )


    @discord.ui.button(emoji="➕", label="Add to Queue", style=discord.ButtonStyle.primary, custom_id="neko_dj_add_queue")
    async def add_queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        async with self.session.lock:
            self.session.queue.append(self.track)
        await interaction.followup.send(f"Added **{self.track.title}** to the queue.", ephemeral=True)
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
        await interaction.followup.send(f"**{self.track.title}** will play next.", ephemeral=True)
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

        def _clean_title(t: str) -> str:
            t = re.sub(r"[\(\[\{].*?[\)\]\}]", "", t.lower())
            return re.sub(r"[^\w\s]", "", t).strip()

        recent_history = session.history[-30:]
        recent_titles = {h.title.lower() for h in recent_history}
        clean_recent_titles = {_clean_title(h.title) for h in recent_history}
        recent_urls = {h.url for h in recent_history} | set(getattr(session, "recent_skipped_urls", set()))

        if session.current_track:
            recent_titles.add(session.current_track.title.lower())
            clean_recent_titles.add(_clean_title(session.current_track.title))
            recent_urls.add(session.current_track.url)
        if base_track:
            recent_titles.add(base_track.title.lower())
            clean_recent_titles.add(_clean_title(base_track.title))
            recent_urls.add(base_track.url)
        for q in session.queue:
            recent_titles.add(q.title.lower())
            clean_recent_titles.add(_clean_title(q.title))
            recent_urls.add(q.url)

        artist = (base_track.artist if base_track and base_track.artist != "Unknown Artist" else None)
        title = base_track.title if base_track else ""

        # Prioritized query hierarchy for continuous infinite variety
        queries_to_try = []
        dj_mood = getattr(session, "dj_mood", "balanced") or "balanced"
        mood_queries = {
            "chill": ("chill acoustic indie pop lofi study songs", "Relaxing chill acoustic vibe matching your mood."),
            "energetic": ("upbeat high energy workout dance party hits", "High-energy banger matching your energetic mood."),
            "focus": ("lofi beats concentration study instrumental focus", "Concentration beats matching your focus mood."),
            "gaming": ("synthwave cyberpunk electronic gaming bass playlist", "Cyberpunk gaming soundtrack matching your gaming mood."),
            "relaxing": ("deep ambient peaceful sleep piano meditation songs", "Soothing ambient soundscape matching your relaxing mood."),
            "party": ("club bangers dance electronic festival anthems", "Crowd-pleasing party hits matching your party mood."),
        }
        if dj_mood.lower() in mood_queries:
            q_str, r_str = mood_queries[dj_mood.lower()]
            if artist:
                queries_to_try.append((f"{artist} {dj_mood} songs", f"More {dj_mood} style hits by **{artist}**."))
            queries_to_try.append((q_str, r_str))

        if artist:
            queries_to_try.append((f"{artist} top tracks songs", f"More top hits by **{artist}**."))
            queries_to_try.append((f"{artist} mix playlist", f"Related artists & styles matching **{artist}**."))
        if title:
            clean_t = _clean_title(title)[:30]
            queries_to_try.append((f"{clean_t} radio mix", f"Songs with matching tempo & vibe to **{title[:30]}**."))
            queries_to_try.append((f"{clean_t} style similar songs", f"Curated vibe matching **{title[:30]}**."))

        # Global trending & circadian fallbacks if specific track queries are exhausted
        queries_to_try.append(("trending top viral hits playlist songs", "Trending global hit recommended by Neko DJ."))
        queries_to_try.append(("upbeat energetic party dance hits", "Energetic groove to keep the vibe going."))
        queries_to_try.append(("chill acoustic indie pop focus", "Smooth acoustic flow recommended by Neko DJ."))
        queries_to_try.append(("lofi chill morning beats study", "Relaxing continuous ambient beats."))

        for query, rationale in queries_to_try:
            try:
                candidates = await AudioResolver.search(query, limit=8)
                # First pass: strictly exclude recently played songs and skipped URLs
                for c in candidates:
                    cand_title = c.get("title", "")
                    cand_url = c.get("url", "")
                    if cand_url in recent_urls or cand_title.lower() in recent_titles or _clean_title(cand_title) in clean_recent_titles:
                        continue
                    resolved = await AudioResolver.resolve_track(cand_url, 0, "Neko DJ Non-Stop")
                    if resolved:
                        return resolved, rationale

                # Second pass: if user exhausted all new songs, allow songs not played in last 5 tracks, but NEVER the just-finished or just-skipped track
                strict_recent = {h.title.lower() for h in session.history[-5:]}
                strict_clean = {_clean_title(h.title) for h in session.history[-5:]}
                for c in candidates:
                    cand_title = c.get("title", "")
                    cand_url = c.get("url", "")
                    if cand_url in getattr(session, "recent_skipped_urls", set()) or (base_track and cand_url == base_track.url):
                        continue
                    if cand_title.lower() in strict_recent or _clean_title(cand_title) in strict_clean:
                        continue
                    resolved = await AudioResolver.resolve_track(cand_url, 0, "Neko DJ Non-Stop")
                    if resolved:
                        return resolved, rationale
            except Exception as e:
                logger.debug(f"Neko DJ candidate probe notice for '{query}': {e}")

        # Diverse radio fallbacks that avoid repeating recent selections
        fallback_streams = [
            ("chill morning lofi coffee beats study relax", "Continuous 24/7 Neko DJ Morning Lofi radio."),
            ("synthwave retrowave cyberpunk gaming night drive", "Continuous 24/7 Neko DJ Synthwave radio."),
            ("deep sleep ambient meditation lofi space calm", "Continuous 24/7 Neko DJ Ambient radio."),
            ("gaming edm bass boost high energy workout", "Continuous 24/7 Neko DJ EDM radio."),
        ]
        for fb_query, fb_rationale in fallback_streams:
            try:
                fb_clean = _clean_title(fb_query)
                if fb_clean in clean_recent_titles or any(fb_clean in cr for cr in clean_recent_titles):
                    continue
                resolved = await AudioResolver.resolve_track(fb_query, 0, "Neko DJ Non-Stop")
                if resolved and resolved.url not in recent_urls:
                    return resolved, fb_rationale
            except Exception:
                continue

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
            title="MusicMaid Auto-DJ",
            description=(
                f"**Now Playing:**\n`{current_artist}` — **{current_title}**\n\n"
                f"**Recommended Track:**\n`{track.artist}` — **[{track.title}]({track.url})**\n\n"
                f"**Reason:**\n{rationale}"
            ),
            color=COLOR_ELECTRIC_CYAN,
        )
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        embed.set_footer(text="MusicMaid Auto-DJ • Intelligent Recommendations")

        view = DJRecommendationCardView(bot, session, track)
        try:
            await session.text_channel.send(embed=embed, view=view)
        except Exception as e:
            logger.warning(f"Failed to post DJ recommendation card: {e}")
