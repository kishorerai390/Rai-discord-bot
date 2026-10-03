"""
Rai Genius & Synchronized Lyrics Engine Cog.
Features:
- /lyrics [song]: Fetch full lyrics with intelligent music queue sync
- If song is not provided, automatically detects the currently playing track from Rai Music
- Backed by open-source high-speed lyrics providers (LRCLIB & Lyrics.ovh)
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import urllib.parse
from typing import TYPE_CHECKING, List, Optional
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import error_embed, info_embed

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


class LyricsPaginator(discord.ui.View):
    """Paginator view for longer lyrics across multiple pages."""

    def __init__(self, pages: List[discord.Embed]):
        super().__init__(timeout=120)
        self.pages = pages
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = self.current_page == 0
        self.next_btn.disabled = self.current_page >= len(self.pages) - 1

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)


class LyricsCog(commands.Cog, name="Lyrics"):
    """Genius & High-Fidelity Music Lyrics Engine."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    async def fetch_lyrics(self, query: str):
        """Fetch lyrics from open API (LRCLIB or Lyrics.ovh)."""
        encoded = urllib.parse.quote(query)
        headers = {"User-Agent": "RaiDiscordBot/2.5.0 (https://github.com/)"}

        # 1. Try LRCLIB Search
        try:
            url = f"https://lrclib.net/api/search?q={encoded}"
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                    if resp.status == 200:
                        results = await resp.json()
                        if results and isinstance(results, list):
                            best = results[0]
                            lyrics_text = best.get("plainLyrics") or best.get("syncedLyrics")
                            track_name = best.get("trackName", query)
                            artist_name = best.get("artistName", "Unknown Artist")
                            if lyrics_text:
                                return track_name, artist_name, lyrics_text
        except Exception as e:
            logger.debug(f"LRCLIB fetch error: {e}")

        # 2. Try generic split artist - title for ovh
        if "-" in query:
            parts = query.split("-", 1)
            artist, title = parts[0].strip(), parts[1].strip()
            try:
                ovh_url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(ovh_url, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            lyr = data.get("lyrics")
                            if lyr:
                                return title, artist, lyr
            except Exception as e:
                logger.debug(f"Lyrics.ovh fetch error: {e}")

        return None, None, None

    @app_commands.command(name="lyrics", description="Look up lyrics for a song or the currently playing music")
    @app_commands.describe(song="Song title and artist (leave empty to fetch currently playing song)")
    async def lyrics(self, interaction: discord.Interaction, song: Optional[str] = None):
        """Search song lyrics or sync with active voice player."""
        await interaction.response.defer()

        target_query = song
        # If no query supplied, inspect active music player
        if not target_query:
            music_cog = self.bot.get_cog("Music")
            if music_cog and interaction.guild:
                player = getattr(music_cog, "get_player", None)
                if callable(player):
                    try:
                        p = player(interaction.guild.id)
                        if p and getattr(p, "current_track", None):
                            track = p.current_track
                            target_query = getattr(track, "title", None)
                    except Exception:
                        pass

        if not target_query:
            await interaction.followup.send(
                embed=error_embed(
                    "No Song Specified",
                    "Please provide a song title (e.g. `/lyrics Starboy The Weeknd`) or start playing music first!",
                ),
                ephemeral=True,
            )
            return

        track_name, artist_name, lyrics_text = await self.fetch_lyrics(target_query)

        if not lyrics_text:
            await interaction.followup.send(
                embed=error_embed(
                    "Lyrics Not Found",
                    f"Could not find lyrics for **{target_query}**.\nTry searching with both artist and song name!",
                ),
                ephemeral=True,
            )
            return

        # Format and paginate lyrics (Discord embed descriptions have 4096 char limit)
        max_chunk = 3000
        chunks = []
        lines = lyrics_text.splitlines()
        current_chunk = []
        current_len = 0

        for line in lines:
            line_len = len(line) + 1
            if current_len + line_len > max_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_len = line_len
            else:
                current_chunk.append(line)
                current_len += line_len
        if current_chunk:
            chunks.append("\n".join(current_chunk))

        embeds = []
        total_pages = len(chunks)
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"🎵 Lyrics: {track_name}",
                description=f"**Artist:** {artist_name}\n\n{chunk}",
                color=0xFA4454,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            if total_pages > 1:
                embed.set_footer(text=f"Page {i+1} of {total_pages} • RAI FAM💗 Genius Engine")
            else:
                embed.set_footer(text="RAI FAM💗 Genius Engine")
            embeds.append(embed)

        if len(embeds) == 1:
            await interaction.followup.send(embed=embeds[0])
        else:
            view = LyricsPaginator(embeds)
            await interaction.followup.send(embed=embeds[0], view=view)


async def setup(bot: SentinelBot):
    await bot.add_cog(LyricsCog(bot))
