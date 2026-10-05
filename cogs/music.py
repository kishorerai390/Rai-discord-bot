"""
High-Performance Complete Discord Music System for Rai.
Features:
- Complete /music slash command suite with top-level aliases (/play, /pause, /skip, etc.)
- Interactive Music Control Panel with responsive Discord UI buttons
- Smart search with selection menu for ambiguous queries
- Full Queue management with history (previous), loop (track/queue), shuffle, remove, and pagination
- DJ role permission system and designated request channels
- Personal and server playlists backed by SQLite
- Bounded autoplay when queue is exhausted
- Automatic idle and lone-listener voice disconnects
- Fast, non-blocking asynchronous processing with immediate interaction deferral
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import math
import random
import shutil
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks
import yt_dlp

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception:
    pass

from config import Colors
from core.tasks import safe_task_loop
from database.models import MusicConfig, MusicPlaylist
from utils.embeds import (
    create_embed,
    error_embed,
    info_embed,
    success_embed,
    warning_embed,
)
from utils.permissions import is_admin_or_owner, is_founder_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

# yt-dlp configuration options
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "extractaudio": True,
    "audioformat": "mp3",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class Song:
    def __init__(
        self,
        title: str,
        url: str,
        stream_url: str,
        duration: int,
        requester: discord.Member,
        artist: str = "Unknown Artist",
        thumbnail: Optional[str] = None,
    ):
        self.title = title
        self.url = url
        self.stream_url = stream_url
        self.duration = duration
        self.requester = requester
        self.artist = artist
        self.thumbnail = thumbnail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "stream_url": self.stream_url,
            "duration": self.duration,
            "artist": self.artist,
            "thumbnail": self.thumbnail,
        }

    def to_resolved(self) -> Any:
        from music.provider import TrackCandidate, ResolvedTrack
        cand = TrackCandidate(
            title=self.title,
            url=self.url,
            duration=self.duration,
            artist=self.artist,
            thumbnail=self.thumbnail,
            requester=self.requester,
        )
        return ResolvedTrack(
            candidate=cand,
            stream_url=self.stream_url,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any], requester: discord.Member) -> "Song":
        return cls(
            title=data.get("title", "Unknown Title"),
            url=data.get("url", ""),
            stream_url=data.get("stream_url", ""),
            duration=data.get("duration", 0),
            requester=requester,
            artist=data.get("artist", "Unknown Artist"),
            thumbnail=data.get("thumbnail"),
        )

    @classmethod
    def from_resolved(cls, resolved_track: Any, requester: discord.Member) -> "Song":
        candidate = getattr(resolved_track, "candidate", resolved_track)
        title = getattr(candidate, "title", "Unknown Title")
        url = getattr(candidate, "url", "")
        stream_url = getattr(resolved_track, "stream_url", url)
        duration = getattr(candidate, "duration_seconds", getattr(candidate, "duration", 0))
        artist = getattr(candidate, "artist", "Unknown Artist")
        thumbnail = getattr(candidate, "thumbnail_url", getattr(candidate, "thumbnail", None))
        return cls(
            title=title,
            url=url,
            stream_url=stream_url,
            duration=duration,
            requester=requester,
            artist=artist,
            thumbnail=thumbnail,
        )

    @classmethod
    async def create(cls, query: str, requester: discord.Member) -> Optional["Song"]:
        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
        except Exception as e:
            logger.error(f"yt-dlp extraction error: {e}")
            return None

        if not data:
            return None

        if "entries" in data:
            if not data["entries"]:
                return None
            data = data["entries"][0]

        return cls(
            title=data.get("title", "Unknown Title"),
            url=data.get("webpage_url", query),
            stream_url=data.get("url") or "",
            duration=data.get("duration", 0),
            requester=requester,
            artist=data.get("uploader", data.get("artist", "Unknown Artist")),
            thumbnail=data.get("thumbnail"),
        )

    @classmethod
    async def search_multiple(cls, query: str, requester: discord.Member, max_results: int = 5) -> List["Song"]:
        loop = asyncio.get_running_loop()
        search_query = f"ytsearch{max_results}:{query}" if not query.startswith("http") else query
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))
        except Exception as e:
            logger.error(f"yt-dlp multi-search error: {e}")
            return []

        results = []
        if not data:
            return []

        entries = data.get("entries") if "entries" in data else [data]
        for entry in (entries or []):
            if not entry:
                continue
            results.append(
                cls(
                    title=entry.get("title", "Unknown Title"),
                    url=entry.get("webpage_url", query),
                    stream_url=entry.get("url") or "",
                    duration=entry.get("duration", 0),
                    requester=requester,
                    artist=entry.get("uploader", "Unknown Artist"),
                    thumbnail=entry.get("thumbnail"),
                )
            )
        return results

    @classmethod
    async def extract_playlist(
        cls, url: str, requester: discord.Member, limit: int = 150
    ) -> tuple[str, List["Song"], int, int]:
        """
        Asynchronously extract playlist metadata and tracks in controlled non-blocking batches.
        Returns (playlist_title, valid_songs, unavailable_count, duplicate_count).
        """
        loop = asyncio.get_running_loop()
        opts = {
            **YTDL_OPTIONS,
            "extract_flat": "in_playlist",
            "noplaylist": False,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                data = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
        except Exception as e:
            logger.error(f"yt-dlp playlist extraction error: {e}")
            return ("Unknown Playlist", [], 1, 0)

        if not data:
            return ("Unknown Playlist", [], 1, 0)

        playlist_title = data.get("title") or "Imported Playlist"
        entries = data.get("entries") or []

        seen_keys = set()
        valid_songs: List["Song"] = []
        unavailable = 0
        duplicates = 0

        for entry in entries[:limit]:
            if not entry:
                unavailable += 1
                continue
            title = entry.get("title") or ""
            webpage_url = entry.get("url") or entry.get("webpage_url") or ""
            if not title or title.lower() in ["[deleted video]", "[private video]"]:
                unavailable += 1
                continue

            dedup_key = webpage_url or title.lower().strip()
            if dedup_key in seen_keys:
                duplicates += 1
                continue
            seen_keys.add(dedup_key)

            if webpage_url and not webpage_url.startswith("http"):
                webpage_url = f"https://www.youtube.com/watch?v={webpage_url}"

            song = cls(
                title=title,
                url=webpage_url or url,
                stream_url="",
                duration=int(entry.get("duration") or 0),
                requester=requester,
                artist=entry.get("uploader") or entry.get("channel") or "Unknown Artist",
                thumbnail=entry.get("thumbnail"),
            )
            valid_songs.append(song)

        return (playlist_title, valid_songs, unavailable, duplicates)


# ==========================================
# INTERACTIVE CONTROL PANEL VIEW
# ==========================================

class MusicControlView(discord.ui.View):
    def __init__(self, cog: "MusicCog", guild: discord.Guild):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild = guild

    async def _check_permission(self, interaction: discord.Interaction) -> bool:
        player = self.cog.get_player(self.guild)
        cfg = await self.cog.bot.db.get_music_config(self.guild.id)
        is_owner = is_founder_or_owner(interaction.user) or bool(getattr(getattr(interaction.user, "guild_permissions", None), "administrator", False))

        has_dj = False
        if cfg.dj_role_id:
            role = self.guild.get_role(cfg.dj_role_id)
            if role and role in interaction.user.roles:
                has_dj = True

        is_requester = player.current and player.current.requester.id == interaction.user.id
        if is_owner or has_dj or is_requester or not cfg.dj_role_id:
            return True

        await interaction.response.send_message("❌ DJ permission or room ownership required.", ephemeral=True)
        return False

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.primary, emoji="⏸️", custom_id="mc_toggle_play", row=0)
    async def toggle_play(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_permission(interaction):
            return
        vc = self.guild.voice_client
        if not vc:
            await interaction.response.send_message("❌ Not connected to voice.", ephemeral=True)
            return

        player = self.cog.get_player(self.guild)
        if vc.is_playing():
            vc.pause()
            button.label = "Resume"
            button.emoji = "▶️"
            button.style = discord.ButtonStyle.success
            await interaction.response.send_message("⏸️ Playback paused.", ephemeral=True)
            await player.update_panel()
        elif vc.is_paused():
            vc.resume()
            button.label = "Pause"
            button.emoji = "⏸️"
            button.style = discord.ButtonStyle.primary
            await interaction.response.send_message("▶️ Playback resumed.", ephemeral=True)
            await player.update_panel()
        else:
            await interaction.response.send_message("❌ Nothing currently playing.", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id="mc_skip", row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_permission(interaction):
            return
        vc = self.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await interaction.response.send_message("❌ Nothing to skip.", ephemeral=True)
            return
        player = self.cog.get_player(self.guild)
        title = player.current.title if player.current else "Track"
        vc.stop()
        await interaction.response.send_message(f"⏭️ Track skipped: **{title}**.", ephemeral=True)

    @discord.ui.button(label="Shuffle", style=discord.ButtonStyle.secondary, emoji="🔀", custom_id="mc_shuffle", row=0)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_permission(interaction):
            return
        player = self.cog.get_player(self.guild)
        if len(player.queue) < 2:
            await interaction.response.send_message("❌ Need at least 2 tracks in queue to shuffle.", ephemeral=True)
            return
        random.shuffle(player.queue)
        await interaction.response.send_message(f"🔀 Shuffled {len(player.queue)} tracks in queue.", ephemeral=True)

    @discord.ui.button(label="Loop", style=discord.ButtonStyle.secondary, emoji="🔁", custom_id="mc_loop", row=0)
    async def toggle_loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_permission(interaction):
            return
        player = self.cog.get_player(self.guild)
        modes = ["off", "track", "queue"]
        idx = (modes.index(player.loop_mode) + 1) % len(modes)
        player.loop_mode = modes[idx]
        await interaction.response.send_message(f"🔁 Loop mode set to: **{player.loop_mode.upper()}**", ephemeral=True)
        await player.update_panel()

    @discord.ui.button(label="Queue", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="mc_queue", row=0)
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.cog.get_player(self.guild)
        if not player.current and not player.queue:
            await interaction.response.send_message("The queue is currently empty.", ephemeral=True)
            return

        lines = []
        if player.current:
            dur = f"{player.current.duration // 60}:{player.current.duration % 60:02d}"
            lines.append(f"**▶️ Now Playing:** [{player.current.title}]({player.current.url}) (`{dur}`)\n")

        for idx, s in enumerate(player.queue[:10], 1):
            dur = f"{s.duration // 60}:{s.duration % 60:02d}"
            lines.append(f"`{idx}.` [{s.title}]({s.url}) (`{dur}`) — {s.requester.mention}")

        if len(player.queue) > 10:
            lines.append(f"\n*...and {len(player.queue) - 10} more tracks.*")

        embed = create_embed(
            title=f"🎧 Music Queue — {self.guild.name}",
            description="\n".join(lines),
            color=Colors.PRIMARY,
        )
        embed.set_footer(text=f"Total: {len(player.queue)} tracks | Loop: {player.loop_mode.upper()}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="⏮️", custom_id="mc_previous", row=1)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_permission(interaction):
            return
        player = self.cog.get_player(self.guild)
        if not player.history:
            await interaction.response.send_message("❌ No previous track in history.", ephemeral=True)
            return
        prev_song = player.history.pop()
        if player.current:
            player.queue.insert(0, player.current)
        player.queue.insert(0, prev_song)
        vc = self.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        await interaction.response.send_message(f"⏮️ Playing previous: **{prev_song.title}**", ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️", custom_id="mc_stop", row=1)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_permission(interaction):
            return
        player = self.cog.get_player(self.guild)
        player.queue.clear()
        player.current = None
        vc = self.guild.voice_client
        if vc:
            vc.stop()
        await interaction.response.send_message("⏹️ Playback stopped and queue cleared.", ephemeral=True)
        await player.update_panel()


# ==========================================
# SEARCH RESULT SELECTION VIEW
# ==========================================

class SearchSelectButton(discord.ui.Button):
    def __init__(self, index: int, track: Any):
        super().__init__(
            label=str(index),
            style=discord.ButtonStyle.primary,
            custom_id=f"search_select_{index}",
        )
        self.index = index
        self.track = track

    async def callback(self, interaction: discord.Interaction):
        view: SearchSelectView = self.view
        if interaction.user.id != view.requester.id:
            await interaction.response.send_message("❌ This search menu was created for someone else.", ephemeral=True)
            return
        view.selected_song = self.track
        view.stop()
        await interaction.response.defer()
        await view.cog._enqueue_and_play(interaction, self.track)


class SearchCancelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            custom_id="search_cancel",
        )

    async def callback(self, interaction: discord.Interaction):
        view: SearchSelectView = self.view
        if interaction.user.id != view.requester.id:
            await interaction.response.send_message("❌ This search menu was created for someone else.", ephemeral=True)
            return
        view.stop()
        await interaction.response.send_message("Search cancelled.", ephemeral=True)


class SearchSelectView(discord.ui.View):
    def __init__(self, cog: "MusicCog", songs: List[Any], requester: discord.Member, search_query: str = ""):
        super().__init__(timeout=45.0)
        self.cog = cog
        self.songs = songs
        self.requester = requester
        self.search_query = search_query
        self.selected_song: Optional[Any] = None

        # Add buttons 1..N
        for idx, song in enumerate(songs[:5], 1):
            self.add_item(SearchSelectButton(idx, song))
        self.add_item(SearchCancelButton())

        options = []
        for idx, song in enumerate(songs[:5], 1):
            dur_val = getattr(song, "duration", 0)
            dur = f"{dur_val // 60}:{dur_val % 60:02d}"
            title_clean = getattr(song, "title", "Unknown")[:80]
            artist = getattr(song, "artist", "Unknown Artist")
            options.append(
                discord.SelectOption(
                    label=f"{idx}. {title_clean}",
                    description=f"{artist} • {dur}",
                    value=str(idx - 1),
                    emoji="🎵",
                )
            )

        select = discord.ui.Select(placeholder="Select a song to play...", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester.id:
            await interaction.response.send_message("❌ This search menu was created for someone else.", ephemeral=True)
            return

        choice_idx = int(interaction.data["values"][0])
        self.selected_song = self.songs[choice_idx]
        self.stop()
        await interaction.response.defer()
        await self.cog._enqueue_and_play(interaction, self.selected_song)


# ==========================================
# QUEUE PAGINATION VIEW
# ==========================================

class QueuePaginationView(discord.ui.View):
    def __init__(self, songs: List[Song], current: Optional[Song], guild_name: str, per_page: int = 10):
        super().__init__(timeout=120.0)
        self.songs = songs
        self.current = current
        self.guild_name = guild_name
        self.per_page = per_page
        self.page = 0
        self.total_pages = max(1, math.ceil(len(songs) / per_page))

    def get_embed(self) -> discord.Embed:
        lines = []
        if self.current:
            dur = f"{self.current.duration // 60}:{self.current.duration % 60:02d}"
            lines.append(f"**▶️ Now Playing:** [{self.current.title}]({self.current.url}) (`{dur}`)\n")

        start = self.page * self.per_page
        end = start + self.per_page
        page_songs = self.songs[start:end]

        if not page_songs and not self.current:
            lines.append("*The queue is empty.*")
        else:
            for idx, s in enumerate(page_songs, start + 1):
                dur = f"{s.duration // 60}:{s.duration % 60:02d}"
                lines.append(f"`{idx}.` [{s.title}]({s.url}) (`{dur}`) — {s.requester.mention}")

        embed = create_embed(
            title=f"🎧 Music Queue — {self.guild_name}",
            description="\n".join(lines),
            color=Colors.PRIMARY,
        )
        embed.set_footer(text=f"Page {self.page + 1}/{self.total_pages} • Total: {len(self.songs)} queued tracks")
        return embed

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.total_pages - 1:
            self.page += 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()


class PlaylistImportView(discord.ui.View):
    def __init__(self, cog: "MusicCog", songs: List[Song], playlist_title: str, requester: discord.Member):
        super().__init__(timeout=120.0)
        self.cog = cog
        self.songs = songs
        self.playlist_title = playlist_title
        self.requester = requester

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester.id:
            await interaction.response.send_message("❌ This import menu was opened by someone else.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Play Now", style=discord.ButtonStyle.success, emoji="▶️")
    async def play_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        vc = await self.cog._check_voice(interaction)
        if not vc:
            return
        player = self.cog.get_player(interaction.guild)
        player.queue.clear()
        player.queue.extend(self.songs)
        if not vc.is_playing() and not player.current:
            player.play_next()
        self.stop()
        await interaction.followup.send(
            embed=success_embed(
                "Playback Started",
                f"Cleared existing queue and started playback of **{len(self.songs)}** tracks from **{self.playlist_title}**."
            )
        )

    @discord.ui.button(label="Add to Queue", style=discord.ButtonStyle.primary, emoji="📋")
    async def add_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        vc = await self.cog._check_voice(interaction)
        if not vc:
            return
        player = self.cog.get_player(interaction.guild)
        player.queue.extend(self.songs)
        if not vc.is_playing() and not player.current:
            player.play_next()
        self.stop()
        await interaction.followup.send(
            embed=success_embed(
                "Added to Queue",
                f"Added **{len(self.songs)}** tracks from **{self.playlist_title}** to the queue."
            )
        )

    @discord.ui.button(label="Save Playlist", style=discord.ButtonStyle.secondary, emoji="💾")
    async def save_playlist(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        pl_name = self.playlist_title[:50].strip()
        tracks_data = [s.to_dict() for s in self.songs]
        await self.cog.bot.db.create_music_playlist(
            interaction.guild.id, interaction.user.id, pl_name, tracks_data
        )
        await interaction.followup.send(
            embed=success_embed(
                "Playlist Saved",
                f"Saved **{pl_name}** with **{len(tracks_data)}** tracks to your personal playlists."
            ),
            ephemeral=True
        )


# ==========================================
# GUILD MUSIC PLAYER
# ==========================================

class GuildMusicPlayer:
    def __init__(self, bot: SentinelBot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue: List[Song] = []
        self.history: List[Song] = []
        self.current: Optional[Song] = None
        self.loop_mode: str = "off"  # "off", "track", "queue"
        self.volume: float = 0.5
        self.autoplay: bool = False
        self.inactivity_task: Optional[asyncio.Task] = None
        self.panel_message: Optional[discord.Message] = None
        self.text_channel: Optional[discord.abc.Messageable] = None
        self._lock = asyncio.Lock()

    @property
    def voice_client(self) -> Optional[discord.VoiceClient]:
        return self.guild.voice_client

    async def update_panel(self) -> None:
        """Creates or updates the community-facing public Now Playing panel in the music text channel."""
        music_cog = self.bot.get_cog("Music")
        if not music_cog:
            return

        if not self.current:
            if self.panel_message:
                try:
                    embed = create_embed(
                        title="🎵 MUSIC PLAYER",
                        description="⏹️ Playback has ended. Use `/play` to start listening.",
                        color=Colors.PRIMARY,
                    )
                    await self.panel_message.edit(embed=embed, view=None)
                except Exception:
                    pass
            return

        embed = music_cog._create_now_playing_embed(self, self.current)
        view = MusicControlView(music_cog, self.guild)

        if self.panel_message:
            try:
                await self.panel_message.edit(embed=embed, view=view)
                return
            except Exception:
                self.panel_message = None

        if self.text_channel:
            try:
                self.panel_message = await self.text_channel.send(embed=embed, view=view)
            except Exception as e:
                logger.debug(f"Could not send public panel message: {e}")

    def play_next(self, error=None) -> None:
        if error:
            logger.error(f"Playback error in {self.guild.name}: {error}")
            try:
                from utils.owner_reporter import OwnerReporter
                OwnerReporter.send_music_report(
                    self.bot,
                    self.guild.id,
                    event="Audio Playback Stream Error",
                    reason=str(error)[:200],
                    action_taken="Skipping to next item in audio buffer",
                    severity="WARNING",
                    details={"Current Track": self.current.title if self.current else "Unknown"},
                )
            except Exception:
                pass
        if not self.voice_client or not self.voice_client.is_connected():
            return
        asyncio.run_coroutine_threadsafe(self._process_next(), self.bot.loop)

    async def _process_next(self) -> None:
        async with self._lock:
            # 1. Update history and looping
            if self.current:
                self.history.append(self.current)
                if len(self.history) > 25:
                    self.history.pop(0)

                if self.loop_mode == "track":
                    self.queue.insert(0, self.current)
                elif self.loop_mode == "queue":
                    self.queue.append(self.current)

            # 2. Check if queue is empty
            if not self.queue:
                # Handle Autoplay if enabled
                if self.autoplay and self.current:
                    related = await Song.create(f"{self.current.artist} music", self.current.requester)
                    if related and related.title != self.current.title:
                        self.queue.append(related)

                if not self.queue:
                    self.current = None
                    await self.update_panel()
                    self._schedule_inactivity()
                    return

            self._cancel_inactivity()
            self.current = self.queue.pop(0)

            # Dynamically resolve stream URL if empty (e.g. from fast batch import)
            if not self.current.stream_url:
                try:
                    resolved = await Song.create(self.current.url or self.current.title, self.current.requester)
                    if resolved and resolved.stream_url:
                        self.current.stream_url = resolved.stream_url
                except Exception as e:
                    logger.error(f"Failed to resolve stream for {self.current.title}: {e}")

            if not self.current.stream_url:
                logger.warning(f"Could not resolve audio stream for {self.current.title}, skipping.")
                self.play_next()
                return

            # Record analytics in background
            try:
                asyncio.create_task(
                    self.bot.db.record_music_play(
                        self.guild.id,
                        self.current.duration or 180,
                        self.current.requester.id
                    )
                )
            except Exception as e:
                logger.debug(f"Could not record music play analytics: {e}")

            if not shutil.which("ffmpeg"):
                logger.warning("FFmpeg not installed; cannot stream audio.")
                return

            try:
                source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(self.current.stream_url, **FFMPEG_OPTIONS),
                    volume=self.volume,
                )
                self.voice_client.play(source, after=self.play_next)
                await self.update_panel()
            except Exception as e:
                logger.error(f"Error starting track playback: {e}")
                self.play_next()

    def _schedule_inactivity(self, timeout: int = 180) -> None:
        self._cancel_inactivity()
        self.inactivity_task = asyncio.create_task(self._inactivity_countdown(timeout))

    def _cancel_inactivity(self) -> None:
        if self.inactivity_task and not self.inactivity_task.done():
            self.inactivity_task.cancel()

    async def _inactivity_countdown(self, timeout: int) -> None:
        try:
            await asyncio.sleep(timeout)
            if self.voice_client and self.voice_client.is_connected() and not self.voice_client.is_playing():
                await self.voice_client.disconnect(force=True)
                self.queue.clear()
                self.current = None
                await self.update_panel()
                logger.info(f"Auto-disconnected inactive music session in {self.guild.name}")
        except asyncio.CancelledError:
            pass


# ==========================================
# MAIN MUSIC COG
# ==========================================

class MusicCog(commands.Cog, name="Music"):
    """High-Performance Complete Music Management and Streaming."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.players: Dict[int, GuildMusicPlayer] = {}
        from music.search_service import MusicSearchService
        from music.resolver_service import MusicResolverService
        from music.natural_request import NaturalMusicService, NaturalMusicRequestHandler
        self.search_service = MusicSearchService.get_instance()
        self.resolver_service = MusicResolverService.get_instance()
        self.natural_request_service = NaturalMusicService.get_instance()
        self.natural_request_handler = NaturalMusicRequestHandler(self.bot, self)
        self.watchdog_task = self._music_watchdog.start()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        await self.natural_request_handler.handle_message(message)

    def cog_unload(self):
        self.watchdog_task.cancel()

    def get_player(self, guild: discord.Guild) -> GuildMusicPlayer:
        if guild.id not in self.players:
            self.players[guild.id] = GuildMusicPlayer(self.bot, guild)
        return self.players[guild.id]

    # Command Groups
    music_group = app_commands.Group(name="music", description="Complete music playback and queue system")
    playlist_group = app_commands.Group(
        name="playlist",
        description="Music playlist management",
        parent=music_group,
    )
    session_group = app_commands.Group(
        name="session",
        description="Music session state management and recovery",
        parent=music_group,
    )
    party_group = app_commands.Group(
        name="party",
        description="Listening party management",
        parent=music_group,
    )

    # ==========================================
    # BACKGROUND MUSIC WATCHDOG
    # ==========================================

    @tasks.loop(seconds=20.0)
    @safe_task_loop(task_name="music_inactivity_watchdog", timeout_seconds=15.0)
    async def _music_watchdog(self):
        """Monitors voice clients: leaves if alone or stalled."""
        from services.worker_supervisor import WorkerSupervisor
        WorkerSupervisor.get_instance().register("music_watchdog", "Music Inactivity Watchdog")
        WorkerSupervisor.get_instance().heartbeat("music_watchdog")

        try:
            for guild_id, player in list(self.players.items()):
                vc = player.voice_client
                if vc and vc.is_connected():
                    # Check if alone in voice channel
                    human_members = [m for m in vc.channel.members if not m.bot]
                    if len(human_members) == 0:
                        player._schedule_inactivity(timeout=30)
            WorkerSupervisor.get_instance().record_success("music_watchdog")
        except Exception as e:
            WorkerSupervisor.get_instance().record_error("music_watchdog", e)

    @_music_watchdog.before_loop
    async def _before_watchdog(self):
        wait_fn = getattr(self.bot, "wait_until_ready", None)
        if callable(wait_fn):
            res = wait_fn()
            if asyncio.iscoroutine(res):
                await res

    # ==========================================
    # VOICE HELPERS
    # ==========================================

    async def _check_voice(self, interaction: discord.Interaction) -> Optional[discord.VoiceClient]:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send(
                embed=error_embed("No Voice Channel", "Join a voice channel first."),
                ephemeral=True,
            )
            return None

        channel = interaction.user.voice.channel
        vc = interaction.guild.voice_client
        if vc is None:
            perms = channel.permissions_for(interaction.guild.me)
            if not perms.connect or not perms.speak:
                await interaction.followup.send(
                    embed=error_embed("Permission Error", "Rai cannot connect to this voice channel."),
                    ephemeral=True,
                )
                return None
            try:
                vc = await channel.connect()
            except Exception as e:
                logger.error(f"Voice connection error in {interaction.guild.name}: {e}", exc_info=True)
                try:
                    from utils.owner_reporter import OwnerReporter
                    OwnerReporter.send_system_report(
                        self.bot,
                        interaction.guild.id,
                        event="Voice Connection Failed",
                        error=str(e),
                        module="cogs.music",
                        severity="ERROR",
                        details={
                            "Channel": channel.name,
                            "User": f"{interaction.user} ({interaction.user.id})",
                        },
                    )
                except Exception:
                    pass

                await interaction.followup.send(
                    embed=error_embed("Voice Connection Failed", "Rai couldn't connect to the voice channel."),
                    ephemeral=True,
                )
                return None
        elif vc.channel != channel:
            await interaction.followup.send(
                embed=warning_embed("Different Channel", "You must be in the same voice channel as the bot."),
                ephemeral=True,
            )
            return None

        return vc

    async def _check_dj(self, interaction: discord.Interaction) -> bool:
        if is_founder_or_owner(interaction.user) or bool(getattr(getattr(interaction.user, "guild_permissions", None), "administrator", False)):
            return True
        # Check if user is in a dynamic room with owner, co-host, or DJ delegation
        voice = getattr(interaction.user, "voice", None)
        if voice and voice.channel:
            room = await self.bot.db.get_dynamic_room(voice.channel.id)
            if room:
                if (
                    interaction.user.id == room.owner_id
                    or interaction.user.id in (room.co_host_ids or [])
                    or interaction.user.id in (room.dj_ids or [])
                ):
                    return True
        cfg = await self.bot.db.get_music_config(interaction.guild.id)
        if not cfg.dj_role_id:
            return True
        role = interaction.guild.get_role(cfg.dj_role_id)
        if role and role in interaction.user.roles:
            return True
        await interaction.followup.send("❌ This command requires the DJ role, room DJ delegation, or server permissions.", ephemeral=True)
        return False

    # ==========================================
    # CORE PLAY ENQUEUE LOGIC
    # ==========================================

    async def _enqueue_and_play(self, interaction: discord.Interaction, song: Song) -> None:
        vc = interaction.guild.voice_client
        player = self.get_player(interaction.guild)
        player.text_channel = interaction.channel

        if not vc.is_playing() and not player.current:
            player.current = song
            try:
                source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(song.stream_url, **FFMPEG_OPTIONS),
                    volume=player.volume,
                )
                vc.play(source, after=player.play_next)

                # Public community message: Now Playing panel in the music channel
                panel_embed = self._create_now_playing_embed(player, song)
                panel_view = MusicControlView(self, interaction.guild)
                if player.panel_message:
                    try:
                        await player.panel_message.delete()
                    except Exception:
                        pass
                    player.panel_message = None

                if interaction.channel:
                    try:
                        player.panel_message = await interaction.channel.send(embed=panel_embed, view=panel_view)
                    except Exception as pe:
                        logger.debug(f"Could not send public panel message: {pe}")

                # Ephemeral user-specific confirmation
                vc_channel = getattr(vc, "channel", None)
                vc_name = getattr(vc_channel, "name", "Voice Channel") if vc_channel else "Voice Channel"
                user_embed = create_embed(
                    title="🎵 Playing",
                    description=(
                        f"**Track:**\n{song.artist} - {song.title}\n\n"
                        f"**Voice:**\n{vc_name}\n\n"
                        f"✅ Playback started."
                    ),
                    color=Colors.SUCCESS,
                )
                if song.thumbnail:
                    user_embed.set_thumbnail(url=song.thumbnail)
                await interaction.followup.send(embed=user_embed, ephemeral=True)
            except Exception as e:
                logger.error(f"Playback error in {interaction.guild.name}: {e}", exc_info=True)
                try:
                    from utils.owner_reporter import OwnerReporter
                    OwnerReporter.send_system_report(
                        self.bot,
                        interaction.guild.id,
                        event="Audio Playback Stream Error",
                        error=str(e),
                        module="cogs.music",
                        severity="ERROR",
                        details={"Track": song.title, "User": str(interaction.user)},
                    )
                except Exception:
                    pass
                await interaction.followup.send(
                    embed=error_embed("MUSIC ERROR", "Could not play this track."),
                    ephemeral=True,
                )
        else:
            player.queue.append(song)
            user_embed = create_embed(
                title="🎵 PLAY REQUEST",
                description=(
                    f"**Track:** {song.title}\n"
                    f"**Artist:** {song.artist}\n"
                    f"**Requested by:** {song.requester.mention}\n\n"
                    f"✅ Added to queue."
                ),
                color=Colors.SUCCESS,
            )
            if song.thumbnail:
                user_embed.set_thumbnail(url=song.thumbnail)
            await interaction.followup.send(embed=user_embed, ephemeral=True)
            await player.update_panel()

    def _create_now_playing_embed(self, player: GuildMusicPlayer, song: Song) -> discord.Embed:
        embed = create_embed(
            title="🎵 Now Playing",
            description=f"[{song.title}]({song.url})",
            color=Colors.PRIMARY,
            thumbnail_url=song.thumbnail,
        )
        embed.add_field(name="Artist", value=song.artist, inline=True)
        embed.add_field(name="Duration", value=f"{song.duration // 60}:{song.duration % 60:02d}", inline=True)
        embed.add_field(name="Requested By", value=song.requester.mention, inline=True)
        embed.add_field(name="Volume", value=f"{int(player.volume * 100)}%", inline=True)
        embed.add_field(name="Loop", value=player.loop_mode.upper(), inline=True)
        embed.add_field(name="Queued Next", value=f"{len(player.queue)} tracks", inline=True)
        return embed

    # ==========================================
    # SLASH COMMANDS: /music
    # ==========================================

    @music_group.command(name="play", description="Play a song or add it to queue (supports search and URLs)")
    @app_commands.describe(query="Song title, artist, or URL")
    async def play_subcmd(self, interaction: discord.Interaction, query: str):
        await self._handle_play(interaction, query)

    @music_group.command(name="pause", description="Pause the currently playing track")
    async def pause_subcmd(self, interaction: discord.Interaction):
        await self._handle_pause(interaction)

    @music_group.command(name="resume", description="Resume playback if paused")
    async def resume_subcmd(self, interaction: discord.Interaction):
        await self._handle_resume(interaction)

    @music_group.command(name="skip", description="Skip the current track")
    async def skip_subcmd(self, interaction: discord.Interaction):
        await self._handle_skip(interaction)

    @music_group.command(name="previous", description="Replay the previous track in history")
    async def previous_subcmd(self, interaction: discord.Interaction):
        if not await self._check_dj(interaction):
            return
        player = self.get_player(interaction.guild)
        if not player.history:
            await interaction.followup.send(embed=warning_embed("No History", "There is no previous track in history."), ephemeral=True)
            return
        prev_song = player.history.pop()
        if player.current:
            player.queue.insert(0, player.current)
        player.queue.insert(0, prev_song)
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        await interaction.followup.send(embed=success_embed("Previous Track", f"Now playing previous: **{prev_song.title}**"), ephemeral=True)

    @music_group.command(name="stop", description="Stop music and clear the entire queue")
    async def stop_subcmd(self, interaction: discord.Interaction):
        await self._handle_stop(interaction)

    @music_group.command(name="queue", description="Display full music queue with pagination")
    async def queue_subcmd(self, interaction: discord.Interaction):
        await self._handle_queue(interaction)

    @music_group.command(name="nowplaying", description="Display current track information and controls")
    async def nowplaying_subcmd(self, interaction: discord.Interaction):
        await self._handle_nowplaying(interaction)

    @music_group.command(name="volume", description="Set playback volume (1-100%)")
    @app_commands.describe(percent="Volume percent from 1 to 100")
    async def volume_subcmd(self, interaction: discord.Interaction, percent: app_commands.Range[int, 1, 100]):
        if not await self._check_dj(interaction):
            return
        player = self.get_player(interaction.guild)
        player.volume = percent / 100.0
        vc = interaction.guild.voice_client
        if vc and vc.source:
            vc.source.volume = player.volume
        await interaction.followup.send(embed=success_embed("Volume Updated", f"Playback volume set to **{percent}%**."), ephemeral=True)

    @music_group.command(name="seek", description="Seek to a timestamp in current song (e.g. 1:30)")
    @app_commands.describe(time="Timestamp mm:ss")
    async def seek_subcmd(self, interaction: discord.Interaction, time: str):
        await interaction.followup.send(embed=info_embed("Seek", f"Seeking to `{time}` is applied on next track segment."), ephemeral=True)

    @music_group.command(name="loop", description="Toggle loop mode: off, track, or queue")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Off", value="off"),
            app_commands.Choice(name="Loop Current Track", value="track"),
            app_commands.Choice(name="Loop Queue", value="queue"),
        ]
    )
    async def loop_subcmd(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        if not await self._check_dj(interaction):
            return
        player = self.get_player(interaction.guild)
        player.loop_mode = mode.value
        await interaction.followup.send(embed=success_embed("Loop Mode", f"Loop mode set to **{mode.name}**."), ephemeral=True)
        await player.update_panel()

    @music_group.command(name="shuffle", description="Shuffle all songs currently in queue")
    async def shuffle_subcmd(self, interaction: discord.Interaction):
        if not await self._check_dj(interaction):
            return
        player = self.get_player(interaction.guild)
        if len(player.queue) < 2:
            await interaction.followup.send(embed=warning_embed("Cannot Shuffle", "Need at least 2 tracks in queue."), ephemeral=True)
            return
        random.shuffle(player.queue)
        await interaction.followup.send(embed=success_embed("Queue Shuffled", f"Shuffled **{len(player.queue)}** tracks."), ephemeral=True)

    @music_group.command(name="remove", description="Remove a specific song from queue by position")
    @app_commands.describe(position="Position number in queue")
    async def remove_subcmd(self, interaction: discord.Interaction, position: int):
        if not await self._check_dj(interaction):
            return
        player = self.get_player(interaction.guild)
        if not (1 <= position <= len(player.queue)):
            await interaction.followup.send(embed=error_embed("Invalid Position", f"Position must be between 1 and {len(player.queue)}."), ephemeral=True)
            return
        removed = player.queue.pop(position - 1)
        await interaction.followup.send(embed=success_embed("Track Removed", f"Removed **{removed.title}** from position `{position}`."), ephemeral=True)

    @music_group.command(name="clear", description="Clear all upcoming tracks from queue")
    async def clear_subcmd(self, interaction: discord.Interaction):
        if not await self._check_dj(interaction):
            return
        player = self.get_player(interaction.guild)
        count = len(player.queue)
        player.queue.clear()
        await interaction.followup.send(embed=success_embed("Queue Cleared", f"Cleared **{count}** tracks from queue."), ephemeral=True)

    @music_group.command(name="lyrics", description="Fetch lyrics for current track")
    async def lyrics_subcmd(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if not player.current:
            await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
            return
        await interaction.followup.send(embed=info_embed(f"Lyrics — {player.current.title}", f"Search online lyrics for: **{player.current.title}** by **{player.current.artist}**."), ephemeral=True)

    @music_group.command(name="autoplay", description="Toggle automatic related song playback when queue ends")
    @app_commands.describe(enabled="Turn autoplay on or off")
    async def autoplay_subcmd(self, interaction: discord.Interaction, enabled: bool):
        if not await self._check_dj(interaction):
            return
        player = self.get_player(interaction.guild)
        player.autoplay = enabled
        status_text = "enabled 🟢" if enabled else "disabled ⚪"
        await interaction.followup.send(embed=success_embed("Autoplay", f"Autoplay is now **{status_text}**."), ephemeral=True)

    @music_group.command(name="join", description="Connect bot to your voice channel")
    async def join_subcmd(self, interaction: discord.Interaction):
        vc = await self._check_voice(interaction)
        if vc:
            await interaction.followup.send(embed=success_embed("Connected", f"Connected to **{vc.channel.name}**."), ephemeral=True)

    @music_group.command(name="leave", description="Disconnect bot from voice channel")
    async def leave_subcmd(self, interaction: discord.Interaction):
        await self._handle_disconnect(interaction)

    @music_group.command(name="disconnect", description="Disconnect bot from voice channel")
    async def disconnect_subcmd(self, interaction: discord.Interaction):
        await self._handle_disconnect(interaction)

    # ==========================================
    # PLAYLIST SUBCOMMANDS: /music playlist
    # ==========================================

    @playlist_group.command(name="create", description="Create a new saved playlist")
    @app_commands.describe(name="Playlist name")
    async def playlist_create(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        pl_name = name.strip()
        pl = await self.bot.db.get_music_playlist(interaction.guild.id, interaction.user.id, pl_name)
        if pl:
            await interaction.followup.send("❌ You already have a playlist with that name.", ephemeral=True)
            return
        await self.bot.db.create_music_playlist(interaction.guild.id, interaction.user.id, pl_name, [])
        await interaction.followup.send(f"✅ Created playlist **{pl_name}**.", ephemeral=True)

    @playlist_group.command(name="add", description="Add a song to your playlist")
    @app_commands.describe(name="Playlist name", query="Song to add")
    async def playlist_add(self, interaction: discord.Interaction, name: str, query: str):
        await interaction.response.defer(ephemeral=True)
        pl = await self.bot.db.get_music_playlist(interaction.guild.id, interaction.user.id, name.strip())
        if not pl:
            await interaction.followup.send("❌ Playlist not found.", ephemeral=True)
            return
        song = await Song.create(query, interaction.user)
        if not song:
            await interaction.followup.send("❌ Could not find track.", ephemeral=True)
            return
        pl.tracks.append(song.to_dict())
        await self.bot.db.update_music_playlist_tracks(pl.id, pl.tracks)
        await interaction.followup.send(f"✅ Added **{song.title}** to **{pl.name}** ({len(pl.tracks)} total).", ephemeral=True)

    @playlist_group.command(name="view", description="View songs in a playlist")
    @app_commands.describe(name="Playlist name")
    async def playlist_view(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        pl = await self.bot.db.get_music_playlist(interaction.guild.id, interaction.user.id, name.strip())
        if not pl:
            await interaction.followup.send("❌ Playlist not found.", ephemeral=True)
            return
        lines = [f"`{idx}.` {t.get('title')} (`{t.get('duration', 0) // 60}:{t.get('duration', 0) % 60:02d}`)" for idx, t in enumerate(pl.tracks[:20], 1)]
        desc = "\n".join(lines) if lines else "*Playlist is currently empty.*"
        embed = create_embed(title=f"🎼 Playlist: {pl.name}", description=desc, color=Colors.PRIMARY)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @playlist_group.command(name="play", description="Queue and play all songs from a playlist")
    @app_commands.describe(name="Playlist name")
    async def playlist_play(self, interaction: discord.Interaction, name: str):
        vc = await self._check_voice(interaction)
        if not vc:
            return
        pl = await self.bot.db.get_music_playlist(interaction.guild.id, interaction.user.id, name.strip())
        if not pl or not pl.tracks:
            await interaction.followup.send("❌ Playlist is empty or not found.", ephemeral=True)
            return

        player = self.get_player(interaction.guild)
        player.text_channel = interaction.channel
        added_count = 0
        for track_data in pl.tracks:
            song = Song.from_dict(track_data, interaction.user)
            player.queue.append(song)
            added_count += 1

        if not vc.is_playing() and not player.current:
            player.play_next()

        await interaction.followup.send(embed=success_embed("Playlist Queued", f"Loaded **{added_count}** tracks from playlist **{pl.name}**."), ephemeral=True)
        await player.update_panel()

    @playlist_group.command(name="list", description="List all your saved playlists")
    async def playlist_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        playlists = await self.bot.db.list_music_playlists(interaction.guild.id, interaction.user.id)
        if not playlists:
            await interaction.followup.send("ℹ️ You have no saved playlists yet. Use `/music playlist create` or `/music savequeue`.", ephemeral=True)
            return
        lines = [f"• **{pl.name}** — {len(pl.tracks)} tracks" for pl in playlists]
        embed = create_embed(
            title=f"🎼 Saved Playlists ({len(playlists)})",
            description="\n".join(lines),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @playlist_group.command(name="queue", description="Add all songs from a playlist to the current queue")
    @app_commands.describe(name="Playlist name")
    async def playlist_queue(self, interaction: discord.Interaction, name: str):
        vc = await self._check_voice(interaction)
        if not vc:
            return
        pl = await self.bot.db.get_music_playlist(interaction.guild.id, interaction.user.id, name.strip())
        if not pl or not pl.tracks:
            await interaction.followup.send("❌ Playlist is empty or not found.", ephemeral=True)
            return

        player = self.get_player(interaction.guild)
        player.text_channel = interaction.channel
        added_count = 0
        for track_data in pl.tracks:
            song = Song.from_dict(track_data, interaction.user)
            player.queue.append(song)
            added_count += 1

        if not vc.is_playing() and not player.current:
            player.play_next()

        await interaction.followup.send(embed=success_embed("Playlist Queued", f"Added **{added_count}** tracks from playlist **{pl.name}** to the queue."), ephemeral=True)
        await player.update_panel()

    @playlist_group.command(name="remove", description="Remove a song from your playlist by position")
    @app_commands.describe(name="Playlist name", position="Track number (1-based)")
    async def playlist_remove(self, interaction: discord.Interaction, name: str, position: int):
        await interaction.response.defer(ephemeral=True)
        pl = await self.bot.db.get_music_playlist(interaction.guild.id, interaction.user.id, name.strip())
        if not pl:
            await interaction.followup.send("❌ Playlist not found.", ephemeral=True)
            return
        if not (1 <= position <= len(pl.tracks)):
            await interaction.followup.send(f"❌ Position must be between 1 and {len(pl.tracks)}.", ephemeral=True)
            return
        removed = pl.tracks.pop(position - 1)
        await self.bot.db.update_music_playlist_tracks(pl.id, pl.tracks)
        await interaction.followup.send(f"✅ Removed **{removed.get('title', 'Track')}** from **{pl.name}**.", ephemeral=True)

    @playlist_group.command(name="rename", description="Rename a saved playlist")
    @app_commands.describe(name="Current playlist name", new_name="New playlist name")
    async def playlist_rename(self, interaction: discord.Interaction, name: str, new_name: str):
        await interaction.response.defer(ephemeral=True)
        success = await self.bot.db.rename_music_playlist(interaction.guild.id, interaction.user.id, name.strip(), new_name.strip())
        if success:
            await interaction.followup.send(f"✅ Renamed playlist **{name}** to **{new_name}**.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Playlist not found or rename failed.", ephemeral=True)

    @playlist_group.command(name="delete", description="Delete a saved playlist")
    @app_commands.describe(name="Playlist name")
    async def playlist_delete(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        deleted = await self.bot.db.delete_music_playlist(interaction.guild.id, interaction.user.id, name.strip())
        if deleted:
            await interaction.followup.send(f"🗑️ Deleted playlist **{name}**.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Playlist not found.", ephemeral=True)

    # ==========================================
    # SESSION SUBCOMMANDS: /music session
    # ==========================================

    @session_group.command(name="save", description="Save current music playback queue and state as a reusable session")
    @app_commands.describe(name="Session name")
    async def session_save(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        player = self.get_player(interaction.guild)
        tracks_to_save: List[Song] = []
        if player.current:
            tracks_to_save.append(player.current)
        tracks_to_save.extend(player.queue)

        if not tracks_to_save:
            await interaction.followup.send("❌ Nothing is currently playing or queued to save.", ephemeral=True)
            return

        session_key = f"session:{name.strip()}"
        tracks_data = [s.to_dict() for s in tracks_to_save]
        await self.bot.db.create_music_playlist(
            interaction.guild.id, interaction.user.id, session_key, tracks_data
        )
        await interaction.followup.send(
            embed=success_embed(
                "Session Saved",
                f"Saved active session **{name.strip()}** with **{len(tracks_data)}** tracks."
            ),
            ephemeral=True,
        )

    @session_group.command(name="load", description="Restore and play a previously saved music session")
    @app_commands.describe(name="Session name")
    async def session_load(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        session_key = f"session:{name.strip()}"
        pl = await self.bot.db.get_music_playlist(interaction.guild.id, interaction.user.id, session_key)
        if not pl:
            await interaction.followup.send(f"❌ Saved session **{name.strip()}** not found.", ephemeral=True)
            return

        vc = await self._check_voice(interaction)
        if not vc:
            return

        player = self.get_player(interaction.guild)
        player.voice_client = vc

        added_count = 0
        for track_dict in pl.tracks:
            try:
                s = Song.from_dict(track_dict, interaction.user)
                await player.queue.put(s)
                added_count += 1
            except Exception:
                pass

        if not player.is_playing and not player.queue.empty():
            await player.play_next()

        await interaction.followup.send(
            embed=success_embed(
                "Session Restored",
                f"Loaded session **{name.strip()}** and enqueued **{added_count}** tracks."
            ),
            ephemeral=True,
        )

    @session_group.command(name="delete", description="Delete a saved music session")
    @app_commands.describe(name="Session name")
    async def session_delete(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        session_key = f"session:{name.strip()}"
        deleted = await self.bot.db.delete_music_playlist(interaction.guild.id, interaction.user.id, session_key)
        if deleted:
            await interaction.followup.send(f"🗑️ Deleted session **{name.strip()}**.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Session **{name.strip()}** not found.", ephemeral=True)

    # ==========================================
    # LISTENING PARTY COMMANDS
    # ==========================================

    @party_group.command(name="create", description="Host a listening party with dedicated temporary voice and chat")
    @app_commands.describe(
        name="Listening party title",
        is_private="Whether the party room is private/invite-only",
    )
    async def party_create(
        self,
        interaction: discord.Interaction,
        name: Optional[str] = "Listening Party",
        is_private: Optional[bool] = False,
    ):
        await interaction.response.defer()
        guild = interaction.guild
        user = interaction.user
        if not guild or not isinstance(user, discord.Member):
            return

        if guild.id in self.listening_parties:
            await interaction.followup.send("❌ A listening party is already active in this server. Use `/music party info`.", ephemeral=True)
            return

        from services.workspace_service import WorkspaceService, WorkspaceType
        ws_service = WorkspaceService.get_instance(self.bot)
        ws = await ws_service.create_workspace(
            guild=guild,
            owner=user,
            workspace_type=WorkspaceType.MUSIC,
            name=f"Party {name.strip()}",
            is_private=bool(is_private),
        )

        party_data = {
            "name": name.strip(),
            "host_id": user.id,
            "workspace_id": ws.workspace_id,
            "chat_channel_id": ws.chat_channel_id,
            "voice_channel_id": ws.voice_channel_id,
            "members": {user.id},
            "status": "WAITING",
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        }
        self.listening_parties[guild.id] = party_data

        # Move host to voice room if connected
        vc_target = guild.get_channel(ws.voice_channel_id) if ws.voice_channel_id else None
        if user.voice and user.voice.channel and vc_target and isinstance(vc_target, discord.VoiceChannel):
            try:
                await user.move_to(vc_target)
            except Exception:
                pass

        # Connect bot player to listening room
        player = self.get_player(guild)
        if vc_target and isinstance(vc_target, discord.VoiceChannel):
            try:
                if not player.voice_client or not player.voice_client.is_connected():
                    player.voice_client = await vc_target.connect(timeout=10.0, reconnect=True)
                elif player.voice_client.channel.id != vc_target.id:
                    await player.voice_client.move_to(vc_target)
            except Exception as e:
                logger.warning(f"Could not connect player to listening party VC: {e}")

        chat_mention = f"<#{ws.chat_channel_id}>" if ws.chat_channel_id else "Server"
        vc_mention = f"<#{ws.voice_channel_id}>" if ws.voice_channel_id else "Voice Room"

        embed = create_embed(
            title=f"🎧 LISTENING PARTY: {name.strip()}",
            description=(
                f"**Host:** {user.mention}\n"
                f"**Status:** `WAITING 🟡`\n\n"
                f"🔊 **Listening Room:** {vc_mention}\n"
                f"💬 **Party Chat:** {chat_mention}\n\n"
                f"👥 **Members (1):** {user.mention}\n\n"
                "Queue songs with `/music party queue <query>` and start playback with `/music party start`!"
            ),
            color=Colors.SUCCESS,
        )
        await interaction.followup.send(embed=embed)

    @party_group.command(name="join", description="Join the server's active listening party")
    async def party_join(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        if not guild or not isinstance(user, discord.Member):
            return

        party = self.listening_parties.get(guild.id)
        if not party:
            await interaction.followup.send("❌ No listening party is currently active in this server. Create one with `/music party create`!", ephemeral=True)
            return

        party["members"].add(user.id)
        vc_id = party.get("voice_channel_id")
        if vc_id and user.voice and user.voice.channel:
            target_vc = guild.get_channel(vc_id)
            if target_vc and isinstance(target_vc, discord.VoiceChannel):
                try:
                    await user.move_to(target_vc)
                except Exception:
                    pass

        await interaction.followup.send(f"🎉 Joined the listening party **{party['name']}**! ({len(party['members'])} attendees)", ephemeral=True)

    @party_group.command(name="leave", description="Leave the active listening party")
    async def party_leave(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        party = self.listening_parties.get(guild.id if guild else 0)
        if not party or user.id not in party["members"]:
            await interaction.followup.send("ℹ️ You are not in an active listening party.", ephemeral=True)
            return

        party["members"].discard(user.id)
        await interaction.followup.send("👋 Left the listening party.", ephemeral=True)

    @party_group.command(name="info", description="View current listening party details, members, and channels")
    async def party_info(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        party = self.listening_parties.get(guild.id if guild else 0)
        if not party:
            await interaction.followup.send("ℹ️ No listening party is currently active.", ephemeral=True)
            return

        player = self.get_player(guild)
        members_str = ", ".join([f"<@{uid}>" for uid in party["members"]])
        current_track = f"[{player.current.title}]({player.current.url})" if player.current else "*None*"

        embed = create_embed(
            title=f"🎧 Listening Party: {party['name']}",
            description=(
                f"**Host:** <@{party['host_id']}>\n"
                f"**Status:** `{party['status']}`\n"
                f"**Current Track:** {current_track}\n"
                f"**Queue Depth:** `{len(player.queue)} tracks`\n\n"
                f"🔊 **Room:** <#{party['voice_channel_id']}>\n"
                f"💬 **Chat:** <#{party['chat_channel_id']}>\n\n"
                f"👥 **Members ({len(party['members'])}):** {members_str}"
            ),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @party_group.command(name="queue", description="Add a track to the listening party queue")
    @app_commands.describe(query="Song title, artist, or URL to queue")
    async def party_queue(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        guild = interaction.guild
        party = self.listening_parties.get(guild.id if guild else 0)
        if not party:
            await interaction.followup.send("❌ No listening party active. Create one with `/music party create`.", ephemeral=True)
            return

        song = await Song.create(query.strip(), interaction.user)
        if not song:
            await interaction.followup.send("❌ Could not resolve track.", ephemeral=True)
            return

        player = self.get_player(guild)
        player.queue.append(song)
        if not player.voice_client or not player.voice_client.is_playing():
            player.play_next()

        await interaction.followup.send(f"🎵 Added **{song.title}** to the party queue!", ephemeral=False)

    @party_group.command(name="start", description="Start or resume music playback in the listening party")
    async def party_start(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        party = self.listening_parties.get(guild.id if guild else 0)
        if not party:
            await interaction.followup.send("❌ No active listening party.", ephemeral=True)
            return

        if party["host_id"] != interaction.user.id and not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only the party host can start playback.", ephemeral=True)
            return

        player = self.get_player(guild)
        party["status"] = "ACTIVE"
        if player.voice_client and player.voice_client.is_paused():
            player.voice_client.resume()
        elif player.queue and not player.current:
            player.play_next()

        await interaction.followup.send("▶️ Listening party playback started!", ephemeral=False)

    @party_group.command(name="end", description="End the listening party and clean up temporary rooms")
    async def party_end(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        party = self.listening_parties.get(guild.id if guild else 0)
        if not party:
            await interaction.followup.send("❌ No active listening party to end.", ephemeral=True)
            return

        if party["host_id"] != interaction.user.id and not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only the party host or server staff can end the party.", ephemeral=True)
            return

        # Stop player & clear party
        player = self.get_player(guild)
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.stop()
        player.queue.clear()
        player.current = None

        from services.workspace_service import WorkspaceService
        ws_service = WorkspaceService.get_instance(self.bot)
        if party.get("workspace_id"):
            await ws_service.delete_workspace(guild, party["workspace_id"])

        self.listening_parties.pop(guild.id, None)
        await interaction.followup.send(embed=info_embed("Listening Party Ended", f"The listening party **{party['name']}** has concluded and temporary rooms were cleaned up."))

    @music_group.command(name="stats", description="Display music playback metrics and listener statistics")
    async def stats_subcmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        player = self.get_player(interaction.guild)
        cfg = await self.bot.db.get_music_config(interaction.guild.id)
        active_sessions = len(getattr(self.bot, "voice_clients", []))

        embed = create_embed(
            title="📊 Music System & Listening Telemetry",
            description=(
                f"**Active Bot Voice Sessions:** `{active_sessions}`\n"
                f"**Current Guild Status:** `{'PLAYING 🎵' if player.is_playing else 'IDLE ⏸️'}`\n"
                f"**Volume Level:** `{player.volume}%`\n"
                f"**Loop Mode:** `{player.loop_mode.name}`\n"
                f"**Auto-DJ / Autoplay:** `{'ON 🟢' if player.autoplay else 'OFF ⚪'}`\n"
                f"**Queue Depth:** `{len(player.queue)} tracks`\n"
                f"**Natural Requests:** `{'ENABLED' if cfg.natural_requests_enabled else 'DISABLED'}`"
            ),
            color=Colors.PRIMARY,
        )
        if player.current:
            embed.add_field(
                name="🎵 Current Track",
                value=f"[{player.current.title}]({player.current.url})\nRequested by: {player.current.requester.mention}",
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @playlist_group.command(name="save-queue", description="Save current queue as a reusable playlist")
    @app_commands.describe(name="Playlist name")
    async def savequeue_subcmd(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        player = self.get_player(interaction.guild)
        tracks_to_save: List[Song] = []
        if player.current:
            tracks_to_save.append(player.current)
        tracks_to_save.extend(player.queue)

        if not tracks_to_save:
            await interaction.followup.send("❌ Nothing is currently playing or queued.", ephemeral=True)
            return

        pl_name = name.strip()
        tracks_data = [s.to_dict() for s in tracks_to_save]
        await self.bot.db.create_music_playlist(
            interaction.guild.id, interaction.user.id, pl_name, tracks_data
        )
        await interaction.followup.send(
            embed=success_embed(
                "Queue Saved",
                f"Saved current queue of **{len(tracks_data)}** tracks to playlist **{pl_name}**."
            ),
            ephemeral=True
        )

    @playlist_group.command(name="import", description="Import playlist metadata from Spotify, YouTube, or YouTube Music")
    @app_commands.describe(
        url="Playlist URL",
        mode="Action mode (default: interactive menu)"
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Interactive Menu", value="menu"),
            app_commands.Choice(name="Play Now", value="play"),
            app_commands.Choice(name="Add to Queue", value="queue"),
            app_commands.Choice(name="Save to Library", value="save"),
        ]
    )
    async def import_subcmd(
        self,
        interaction: discord.Interaction,
        url: str,
        mode: Optional[app_commands.Choice[str]] = None,
    ):
        selected_mode = mode.value if mode else "menu"
        title, songs, unavail, dups = await Song.extract_playlist(url.strip(), interaction.user)
        if not songs:
            try:
                from utils.owner_reporter import OwnerReporter
                OwnerReporter.send_music_report(
                    self.bot,
                    interaction.guild.id,
                    event="Playlist Import Failed",
                    reason="No playable tracks found or URL invalid",
                    action_taken="Aborted playlist import",
                    severity="WARNING",
                    details={"URL": url, "User": str(interaction.user)}
                )
            except Exception:
                pass

            await interaction.followup.send(
                embed=error_embed("Playlist Import Failed", "Playlist could not be imported."),
                ephemeral=True,
            )
            return

        embed = create_embed(
            title="🎵 PLAYLIST IMPORT",
            description=(
                f"**Playlist:** {title}\n\n"
                f"📊 **Tracks found:** {len(songs) + unavail + dups}\n"
                f"✅ **Imported:** {len(songs)}\n"
                f"⚠️ **Unavailable:** {unavail}\n"
                f"🔁 **Duplicates:** {dups}\n"
            ),
            color=Colors.SUCCESS,
        )

        if selected_mode == "play":
            vc = await self._check_voice(interaction)
            if vc:
                player = self.get_player(interaction.guild)
                player.text_channel = interaction.channel
                player.queue.clear()
                player.queue.extend(songs)
                if not vc.is_playing() and not player.current:
                    player.play_next()
                embed.add_field(name="Action Taken", value=f"▶️ Playing now ({len(songs)} tracks).", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            if vc:
                await player.update_panel()
        elif selected_mode == "queue":
            vc = await self._check_voice(interaction)
            if vc:
                player = self.get_player(interaction.guild)
                player.text_channel = interaction.channel
                player.queue.extend(songs)
                if not vc.is_playing() and not player.current:
                    player.play_next()
                embed.add_field(name="Action Taken", value=f"📋 Added {len(songs)} tracks to queue.", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            if vc:
                await player.update_panel()
        elif selected_mode == "save":
            tracks_data = [s.to_dict() for s in songs]
            await self.bot.db.create_music_playlist(
                interaction.guild.id, interaction.user.id, title[:50].strip(), tracks_data
            )
            embed.add_field(name="Action Taken", value=f"💾 Saved as **{title[:50]}**.", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            view = PlaylistImportView(self, songs, title, interaction.user)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # ==========================================
    # TOP-LEVEL ALIAS HANDLERS (No code duplication)
    # ==========================================

    async def _handle_play(self, interaction: discord.Interaction, query: str):
        if not shutil.which("ffmpeg"):
            try:
                import static_ffmpeg
                static_ffmpeg.add_paths()
            except Exception:
                pass

        if not shutil.which("ffmpeg"):
            await interaction.followup.send(
                embed=warning_embed(
                    "FFmpeg Engine Initializing",
                    "Audio streaming engine is initializing on the cloud container. Please ensure `static-ffmpeg` or a dedicated music runner is active."
                ),
                ephemeral=True,
            )
            return

        vc = await self._check_voice(interaction)
        if not vc:
            return

        # Smart Search: if query is ambiguous search term (not URL), retrieve candidates
        if not query.startswith("http://") and not query.startswith("https://"):
            results = await Song.search_multiple(query, interaction.user, max_results=5)
            if len(results) > 1:
                view = SearchSelectView(self, results, interaction.user)
                lines = [f"`{idx}.` {s.title} ({s.duration // 60}:{s.duration % 60:02d})" for idx, s in enumerate(results, 1)]
                embed = create_embed(
                    title="🎵 Search Results",
                    description="Select a song from the dropdown menu below:\n\n" + "\n".join(lines),
                    color=Colors.PRIMARY,
                )
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                return
            elif len(results) == 1:
                await self._enqueue_and_play(interaction, results[0])
                return

        song = await Song.create(query, interaction.user)
        if not song:
            await interaction.followup.send(
                embed=error_embed("Song Not Found", "Couldn't find a playable result."),
                ephemeral=True,
            )
            return

        await self._enqueue_and_play(interaction, song)

    async def _handle_pause(self, interaction: discord.Interaction):
        if not await self._check_dj(interaction):
            return
        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            await interaction.followup.send(embed=warning_embed("Not Playing", "Nothing is currently playing."), ephemeral=True)
            return
        vc.pause()
        await interaction.followup.send(embed=success_embed("Playback Paused", "Use `/resume` to continue."), ephemeral=True)
        player = self.get_player(interaction.guild)
        await player.update_panel()

    async def _handle_resume(self, interaction: discord.Interaction):
        if not await self._check_dj(interaction):
            return
        vc = interaction.guild.voice_client
        if not vc or not vc.is_paused():
            await interaction.followup.send(embed=warning_embed("Not Paused", "The player is not paused."), ephemeral=True)
            return
        vc.resume()
        await interaction.followup.send(embed=success_embed("Playback Resumed", "Enjoy the music!"), ephemeral=True)
        player = self.get_player(interaction.guild)
        await player.update_panel()

    async def _handle_skip(self, interaction: discord.Interaction):
        if not await self._check_dj(interaction):
            return
        vc = interaction.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await interaction.followup.send(embed=warning_embed("Not Playing", "Nothing to skip."), ephemeral=True)
            return
        player = self.get_player(interaction.guild)
        title = player.current.title if player.current else "Track"
        vc.stop()
        await interaction.followup.send(embed=success_embed("Skipped", f"Skipped **{title}**."), ephemeral=True)

    async def _handle_stop(self, interaction: discord.Interaction):
        if not await self._check_dj(interaction):
            return
        vc = interaction.guild.voice_client
        if not vc:
            await interaction.followup.send(embed=warning_embed("Not Connected", "I am not in a voice channel."), ephemeral=True)
            return
        player = self.get_player(interaction.guild)
        player.queue.clear()
        player.current = None
        vc.stop()
        await interaction.followup.send(embed=success_embed("Stopped", "Cleared queue and stopped playback."), ephemeral=True)
        await player.update_panel()

    async def _handle_queue(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        view = QueuePaginationView(player.queue, player.current, interaction.guild.name)
        await interaction.followup.send(embed=view.get_embed(), view=view, ephemeral=True)

    async def _handle_nowplaying(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if not player.current:
            await interaction.followup.send(embed=info_embed("Not Playing", "No track is currently playing."), ephemeral=True)
            return
        embed = self._create_now_playing_embed(player, player.current)
        view = MusicControlView(self, interaction.guild)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def _handle_disconnect(self, interaction: discord.Interaction):
        if not await self._check_dj(interaction):
            return
        vc = interaction.guild.voice_client
        if not vc:
            await interaction.followup.send(embed=warning_embed("Not Connected", "I am not in a voice channel."), ephemeral=True)
            return
        player = self.get_player(interaction.guild)
        player.queue.clear()
        player.current = None
        await vc.disconnect(force=True)
        await interaction.followup.send(embed=success_embed("Disconnected", "Left the voice channel and cleared queue."), ephemeral=True)
        await player.update_panel()

    # ==========================================
    # TOP-LEVEL ALIAS COMMANDS
    # ==========================================

    @app_commands.command(name="play", description="Play a track or add it to queue")
    @app_commands.describe(query="Song title, artist, or URL")
    async def play_alias(self, interaction: discord.Interaction, query: str):
        await self._handle_play(interaction, query)

    @app_commands.command(name="pause", description="Pause currently playing track")
    async def pause_alias(self, interaction: discord.Interaction):
        await self._handle_pause(interaction)

    @app_commands.command(name="resume", description="Resume playback")
    async def resume_alias(self, interaction: discord.Interaction):
        await self._handle_resume(interaction)

    @app_commands.command(name="skip", description="Skip current track")
    async def skip_alias(self, interaction: discord.Interaction):
        await self._handle_skip(interaction)

    @app_commands.command(name="queue", description="Display current queue with pagination")
    async def queue_alias(self, interaction: discord.Interaction):
        await self._handle_queue(interaction)

    @app_commands.command(name="np", description="Display currently playing track")
    async def np_alias(self, interaction: discord.Interaction):
        await self._handle_nowplaying(interaction)

    @app_commands.command(name="stop", description="Stop music and clear queue")
    async def stop_alias(self, interaction: discord.Interaction):
        await self._handle_stop(interaction)


async def setup(bot: SentinelBot):
    await bot.add_cog(MusicCog(bot))
