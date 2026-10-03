"""
Rai Watch Party & Movie Cog.
Provides:
- Community watch party scheduling and announcements
- Temporary cinema and movie lounge voice rooms
- Community movie and series reviews with 1-10 rating scale
- Curated recommendations across genres
- Interactive community movie night polls
- Full compliance with media redistribution standards (metadata & scheduling only)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from database.models import WatchEvent
from utils.embeds import create_embed, error_embed, info_embed, success_embed

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

RECOMMENDATIONS = {
    "sci-fi": [
        ("Interstellar (2014)", "A team of explorers travel through a wormhole in space in an attempt to ensure humanity's survival."),
        ("Blade Runner 2049 (2017)", "Young Blade Runner K unearths a long-buried secret that leads him to track down former Blade Runner Rick Deckard."),
        ("Dune: Part Two (2024)", "Paul Atreides unites with Chani and the Fremen while seeking revenge against the conspirators who destroyed his family."),
    ],
    "thriller": [
        ("Parasite (2019)", "Greed and class discrimination threaten the newly formed symbiotic relationship between the wealthy Park family and the destitute Kim clan."),
        ("Shutter Island (2010)", "A U.S. Marshal investigates the disappearance of a murderer who escaped from a hospital for the criminally insane."),
        ("Se7en (1995)", "Two detectives hunt a serial killer who uses the seven deadly sins as his motives."),
    ],
    "animation": [
        ("Spider-Man: Into the Spider-Verse", "Teen Miles Morales becomes the new Spider-Man and joins other Spider-heroes from parallel dimensions."),
        ("Spirited Away (2001)", "A ten-year-old girl wanders into a world ruled by gods, witches, and spirits, where humans are changed into beasts."),
        ("Arcane (Series)", "Amidst the clash between two cities, two sisters fight on rival sides of a war between magic technologies and incompatible convictions."),
    ],
    "comedy": [
        ("The Grand Budapest Hotel (2014)", "A writer encounters the owner of an aging high-class European hotel, who tells him of his early years serving as a lobby boy."),
        ("Knives Out (2019)", "A detective investigates the death of a patriarch of an eccentric, combative family."),
    ],
}


class MoviesCog(commands.Cog, name="Movies"):
    """Community Watch Parties, Cinema Rooms, Reviews, and Movie Polls."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    watch_group = app_commands.Group(name="watchparty", description="Watch party events and cinema rooms")
    movie_group = app_commands.Group(name="movie", description="Movie reviews, polls, and recommendations")

    # ==========================================
    # WATCH PARTY COMMANDS
    # ==========================================

    @watch_group.command(name="schedule", description="Schedule a community movie or watch party event")
    @app_commands.describe(
        title="Title of movie, show, or event",
        platform="Viewing platform (e.g. Netflix, Crunchyroll, Disney+, Prime Video, YouTube)",
        start_time="Date & time (e.g. Friday at 9 PM EST)",
        voice_channel="Designated voice channel (optional)"
    )
    async def schedule_watchparty(
        self,
        interaction: discord.Interaction,
        title: str,
        platform: str,
        start_time: str,
        voice_channel: Optional[discord.VoiceChannel] = None,
    ):
        await interaction.response.defer()
        vc_id = voice_channel.id if voice_channel else None

        event_id = await self.bot.db.create_watch_event(
            guild_id=interaction.guild.id,
            title=title.strip(),
            platform=platform.strip(),
            start_time=start_time.strip(),
            host_id=interaction.user.id,
            voice_channel_id=vc_id,
        )

        embed = create_embed(
            title=f"🎬 WATCH PARTY: {title.strip()}",
            description=f"Host {interaction.user.mention} is hosting a community watch party!",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="📺 Platform", value=platform, inline=True)
        embed.add_field(name="⏰ Time", value=start_time, inline=True)
        if voice_channel:
            embed.add_field(name="🔊 Voice Channel", value=voice_channel.mention, inline=False)
        embed.set_footer(text="React with 🍿 to join the watch crew!")

        msg = await interaction.followup.send(embed=embed)
        try:
            await msg.add_reaction("🍿")
            await msg.add_reaction("🎉")
        except Exception:
            pass

    @watch_group.command(name="list", description="List upcoming community watch parties")
    async def list_watchparties(self, interaction: discord.Interaction):
        await interaction.response.defer()
        events = await self.bot.db.list_watch_events(interaction.guild.id)
        if not events:
            await interaction.followup.send("ℹ️ No watch parties are currently scheduled. Use `/watchparty schedule`!")
            return

        embed = create_embed(
            title="🍿 Upcoming Watch Parties",
            description="Join fellow members for upcoming group streams:",
            color=Colors.PRIMARY,
        )
        for e in events:
            host_mention = f"<@{e.host_id}>"
            embed.add_field(
                name=f"🎬 {e.title} ({e.platform or 'Stream'})",
                value=f"⏰ **Time:** {e.start_time}\n👤 **Host:** {host_mention}",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    @watch_group.command(name="room", description="Create a temporary Cinema or Watch Lounge voice channel")
    @app_commands.describe(name="Name of the room (e.g. Cinema Night, Anime Screening)")
    async def create_cinema_room(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        guild = interaction.guild
        category = discord.utils.find(lambda c: "WATCH" in c.name.upper() or "MOVIE" in c.name.upper(), guild.categories)

        vc = await guild.create_voice_channel(
            name=f"🎬・{name.strip()[:20]}",
            category=category,
            reason=f"Watch lounge created by {interaction.user}",
        )

        if interaction.user.voice and interaction.user.voice.channel:
            try:
                await interaction.user.move_to(vc)
            except Exception:
                pass

        embed = success_embed(
            "Cinema Room Created",
            f"Created watch lounge {vc.mention}. Grab your snacks and tune in!",
        )
        await interaction.followup.send(embed=embed)

    # ==========================================
    # MOVIE REVIEWS, POLLS & RECOMMENDATIONS
    # ==========================================

    @movie_group.command(name="review", description="Share your review and rating of a movie or series")
    @app_commands.describe(
        title="Movie or series title",
        rating="Rating from 1 to 10",
        review="Your thoughts, favorite scenes, or verdict"
    )
    async def review_movie(
        self,
        interaction: discord.Interaction,
        title: str,
        rating: app_commands.Range[int, 1, 10],
        review: str,
    ):
        await interaction.response.defer()
        stars = "⭐" * rating
        embed = create_embed(
            title=f"📽️ Community Review: {title.strip()}",
            description=f"Reviewed by {interaction.user.mention}\n\n**Rating:** {stars} (`{rating}/10`)\n\n>>> {review.strip()}",
            color=Colors.GOLD if rating >= 8 else Colors.PRIMARY,
        )
        embed.set_footer(text="Agree or disagree? Share your thoughts below!")
        msg = await interaction.followup.send(embed=embed)
        try:
            await msg.add_reaction("👍")
            await msg.add_reaction("👎")
        except Exception:
            pass

    @movie_group.command(name="recommend", description="Get high-rated recommendations by genre")
    @app_commands.describe(genre="Select genre")
    @app_commands.choices(
        genre=[
            app_commands.Choice(name="Sci-Fi / Mind-Bending", value="sci-fi"),
            app_commands.Choice(name="Suspense / Thriller", value="thriller"),
            app_commands.Choice(name="Animation & Anime", value="animation"),
            app_commands.Choice(name="Comedy & Wholesome", value="comedy"),
        ]
    )
    async def recommend_movie(self, interaction: discord.Interaction, genre: app_commands.Choice[str]):
        await interaction.response.defer()
        recs = RECOMMENDATIONS.get(genre.value, [])
        embed = create_embed(
            title=f"🍿 Recommendations — {genre.name}",
            description="Critically acclaimed titles to add to your watchlist:",
            color=Colors.PRIMARY,
        )
        for title, desc in recs:
            embed.add_field(name=f"🎬 {title}", value=desc, inline=False)
        await interaction.followup.send(embed=embed)

    @movie_group.command(name="poll", description="Create a movie night vote between titles")
    @app_commands.describe(
        option_1="First choice title",
        option_2="Second choice title",
        option_3="Third choice title (optional)",
        option_4="Fourth choice title (optional)"
    )
    async def movie_poll(
        self,
        interaction: discord.Interaction,
        option_1: str,
        option_2: str,
        option_3: Optional[str] = None,
        option_4: Optional[str] = None,
    ):
        await interaction.response.defer()
        options = [option_1.strip(), option_2.strip()]
        if option_3:
            options.append(option_3.strip())
        if option_4:
            options.append(option_4.strip())

        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
        lines = [f"{emojis[i]} **{opt}**" for i, opt in enumerate(options)]

        embed = create_embed(
            title="🗳️ Movie Night Vote!",
            description="Cast your vote by reacting with the corresponding number:\n\n" + "\n".join(lines),
            color=Colors.PRIMARY,
        )
        embed.set_footer(text=f"Poll created by {interaction.user.display_name}")
        msg = await interaction.followup.send(embed=embed)
        for i in range(len(options)):
            try:
                await msg.add_reaction(emojis[i])
            except Exception:
                pass


async def setup(bot: SentinelBot):
    await bot.add_cog(MoviesCog(bot))
