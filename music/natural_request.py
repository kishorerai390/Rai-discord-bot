"""
RAI — Natural Song Requests & Zero-Interference Playback Engine.

Implements:
1. Designated request-channel filtering (#music-requests).
2. Conservative music intent detection (High, Medium, Low confidence).
3. Zero-interference playback (never interrupts active stream; enqueues by default).
4. Explicit immediate play (/playnow) support.
5. Per-user duplicate request protection (10s window).
6. Per-user request rate limiting (5 per 30s).
7. Requester voice validation (requires active voice connection; joins Dynamic VCs seamlessly).
8. Queue fairness and ownership preservation.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import re
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import discord

from config import Colors, MUSIC_DUPLICATE_REQUEST_WINDOW_SECONDS, MUSIC_USER_RATE_LIMIT_COUNT, MUSIC_USER_RATE_LIMIT_WINDOW
from music.provider import MusicErrorCode, QueryType, TrackCandidate, generate_music_diagnostic_id
from music.search_service import MusicSearchService
from music.resolver_service import MusicResolverService
from utils.embeds import create_embed, error_embed, info_embed, success_embed, warning_embed

if TYPE_CHECKING:
    from core.bot import SentinelBot
    from cogs.music import MusicCog, GuildMusicPlayer, Song

logger = logging.getLogger("Rai.NaturalMusicRequest")


class MusicIntent(enum.Enum):
    PLAY = "PLAY"
    PLAYNOW = "PLAYNOW"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    SKIP = "SKIP"
    STOP = "STOP"
    QUEUE = "QUEUE"
    NOW_PLAYING = "NOW_PLAYING"
    UNKNOWN = "UNKNOWN"


class IntentConfidence(enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# Conversational phrases and chit-chat that MUST NEVER trigger music
NON_MUSIC_PATTERNS = [
    r"^(?:hello|hi|hey|heya|yo|sup|hola)\b",
    r"^(?:good\s+(?:morning|afternoon|evening|night))\b",
    r"^(?:bro|dude|man|guys|everyone|anybody|anyone)\b",
    r"\b(?:what\s+are\s+you\b|what\s+game\b|who\s+is\b|anyone\s+gaming\b|anyone\s+here\b|what\s+should\s+we\b)\b",
    r"\b(?:lol|lmao|rofl|xd|haha|hehe|😂|🤣|💀)\b",
    r"\b(?:nice\s+song|good\s+song|great\s+track|this\s+song\s+is\s+amazing|is\s+amazing|is\s+awesome|is\s+great|is\s+good)\b",
    r"\b(?:is\s+my\s+favorite\s+song|i\s+love\b|i\s+like\b|my\s+favorite\b|favorite\s+song)\b",
    r"\b(?:what\s+are\s+you\s+listening\s+to|what\s+song\s+is\s+this)\b",
    r"^(?:yes|no|yeah|nah|yep|nope|ok|okay|k|cool|sure|thanks|ty|thx|gg|gl)\b",
]

NON_MUSIC_REGEXES = [re.compile(p, re.IGNORECASE) for p in NON_MUSIC_PATTERNS]


class NaturalMusicRequestDetector:
    """Classifies message text into music intents and confidence scores."""

    @classmethod
    def analyze_message(cls, content: str) -> Tuple[MusicIntent, str, IntentConfidence]:
        clean = content.strip()
        if not clean:
            return MusicIntent.UNKNOWN, "", IntentConfidence.LOW

        lower = clean.lower()

        # Check explicit chit-chat filters first
        for rgx in NON_MUSIC_REGEXES:
            if rgx.search(lower):
                # If conversational message says e.g. "I love Kalyani" or "hello bro"
                # it should NOT be treated as a play command
                if not lower.startswith(("play ", "playnow ", "/play", "!play")):
                    return MusicIntent.UNKNOWN, clean, IntentConfidence.LOW

        # 1. Explicit playback controls in request channel
        if lower in ("pause", "pause music", "stop playing"):
            return MusicIntent.PAUSE, "", IntentConfidence.HIGH

        if lower in ("resume", "resume music", "continue playing", "unpause"):
            return MusicIntent.RESUME, "", IntentConfidence.HIGH

        if lower in ("skip", "skip this", "skip song", "next song", "next track", "skip track"):
            return MusicIntent.SKIP, "", IntentConfidence.HIGH

        if lower in ("stop", "stop music", "halt music", "clear queue"):
            return MusicIntent.STOP, "", IntentConfidence.HIGH

        if lower in ("queue", "show queue", "music queue", "list queue", "songs"):
            return MusicIntent.QUEUE, "", IntentConfidence.HIGH

        if lower in ("now playing", "what's playing", "what is playing", "np", "song"):
            return MusicIntent.NOW_PLAYING, "", IntentConfidence.HIGH

        # 2. Explicit playnow command (interrupt current song)
        if lower.startswith("playnow "):
            query = clean[8:].strip()
            if query:
                return MusicIntent.PLAYNOW, query, IntentConfidence.HIGH

        # 3. Explicit play command prefix
        if lower.startswith(("play ", "song: ", "music ", "search: ")):
            prefix_len = lower.find(" ") + 1
            query = clean[prefix_len:].strip()
            if query:
                return MusicIntent.PLAY, query, IntentConfidence.HIGH

        # 4. Direct URLs (YouTube, Spotify, SoundCloud, etc.)
        if lower.startswith(("http://", "https://")):
            return MusicIntent.PLAY, clean, IntentConfidence.HIGH

        # 5. Question phrases like "can we play X" or "could you play X"
        question_match = re.match(r"^(?:can\s+(?:you|we)\s+play|could\s+(?:you|we)\s+play|please\s+play)\s+(.+)", clean, re.IGNORECASE)
        if question_match:
            query = question_match.group(1).strip(" ?.")
            if query:
                return MusicIntent.PLAY, query, IntentConfidence.HIGH

        # 6. Conversational mentions ("is X a song", "do you know X") -> MEDIUM confidence
        conv_query = re.match(r"^(?:do\s+you\s+know|what\s+about|how\s+about)\s+(.+)", clean, re.IGNORECASE)
        if conv_query:
            query = conv_query.group(1).strip(" ?.")
            return MusicIntent.PLAY, query, IntentConfidence.MEDIUM

        # Conversational questions ending in '?' that weren't explicit playback requests
        if clean.endswith("?"):
            return MusicIntent.UNKNOWN, clean, IntentConfidence.LOW

        # 7. Natural song title or artist name (e.g. "Kalyani", "Perfect Ed Sheeran", "Believer")
        # Check if text looks like a valid search query (no excessive punctuation, 1-12 words, not pure numbers)
        words = clean.split()
        if 1 <= len(words) <= 12 and not clean.isdigit() and len(clean) >= 2:
            # If contains typical song keywords like "by", "feat", "ft", "remix", "acoustic", "official" -> HIGH
            if any(k in lower for k in (" by ", " feat ", " ft. ", " ft ", " remix", " audio", " live", " version")):
                return MusicIntent.PLAY, clean, IntentConfidence.HIGH

            # Single word or title like "Kalyani", "Believer", "Shape of You" -> HIGH in request channel
            return MusicIntent.PLAY, clean, IntentConfidence.HIGH

        return MusicIntent.UNKNOWN, clean, IntentConfidence.LOW


class MusicRequestConfirmView(discord.ui.View):
    """Interactive confirmation view when query intent has MEDIUM confidence."""

    def __init__(
        self,
        service: "NaturalMusicService",
        bot: "SentinelBot",
        requester: discord.Member,
        query: str,
        target_channel: discord.VoiceChannel,
    ):
        super().__init__(timeout=60.0)
        self.service = service
        self.bot = bot
        self.requester = requester
        self.query = query
        self.target_channel = target_channel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester.id:
            await interaction.response.send_message("❌ This confirmation is for someone else.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Play Song", style=discord.ButtonStyle.success, emoji="▶️")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.stop()
        await interaction.edit_original_response(
            content=f"🔎 Searching for **{self.query}**...",
            view=None,
        )
        await self.service.execute_play_request(
            bot=self.bot,
            guild=interaction.guild,
            channel=interaction.channel,
            user=self.requester,
            query=self.query,
            play_now=False,
            voice_channel=self.target_channel,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            content=f"❌ Cancelled request for **{self.query}**.",
            view=None,
        )


class NaturalMusicService:
    """
    Dedicated coordinator for natural song requests and zero-interference playback.
    """

    _instance: Optional["NaturalMusicService"] = None

    def __init__(self):
        self._user_requests: Dict[int, List[float]] = {}
        self._recent_song_requests: Dict[int, Dict[str, float]] = {}
        self._guild_locks: Dict[int, asyncio.Lock] = {}

    @classmethod
    def get_instance(cls) -> "NaturalMusicService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_guild_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._guild_locks:
            self._guild_locks[guild_id] = asyncio.Lock()
        return self._guild_locks[guild_id]

    def check_rate_limit(self, user_id: int) -> bool:
        """Enforces 5 requests per 30 seconds limit."""
        now = time.time()
        timestamps = self._user_requests.get(user_id, [])
        # Prune expired
        timestamps = [t for t in timestamps if now - t < MUSIC_USER_RATE_LIMIT_WINDOW]
        self._user_requests[user_id] = timestamps

        if len(timestamps) >= MUSIC_USER_RATE_LIMIT_COUNT:
            return True

        timestamps.append(now)
        self._user_requests[user_id] = timestamps
        return False

    def check_duplicate_request(self, user_id: int, query: str) -> bool:
        """Prevents accidental duplicate requests within configured window (default 10s)."""
        now = time.time()
        norm = query.strip().lower()
        user_history = self._recent_song_requests.get(user_id, {})
        # Prune older than window
        user_history = {q: t for q, t in user_history.items() if now - t < MUSIC_DUPLICATE_REQUEST_WINDOW_SECONDS}
        self._recent_song_requests[user_id] = user_history

        if norm in user_history:
            return True

        user_history[norm] = now
        self._recent_song_requests[user_id] = user_history
        return False

    async def process_message(self, bot: "SentinelBot", message: discord.Message) -> bool:
        """
        Main entry point for incoming Discord messages.
        Returns True if the message was handled as a natural music request.
        """
        if message.author.bot or not message.guild:
            return False

        # Load guild music configuration
        cfg = await bot.db.get_music_config(message.guild.id)

        # RULE: Natural requests are ONLY interpreted inside the configured request channel!
        if not cfg.request_channel_id or message.channel.id != cfg.request_channel_id:
            # Normal chat in outside channels MUST NEVER control music
            return False

        # Verify Message Content intent
        intents = getattr(bot, "intents", None)
        if intents and not getattr(intents, "message_content", True):
            await message.channel.send(
                "❌ Natural song requests are unavailable because message-content access is not enabled. Use `/play <song>`."
            )
            return True

        if not cfg.natural_requests_enabled:
            return False

        # Detect intent and confidence
        intent, query, confidence = NaturalMusicRequestDetector.analyze_message(message.content)

        if confidence == IntentConfidence.LOW or intent == MusicIntent.UNKNOWN:
            # Treat as ordinary chat in channel; no action
            return False

        # Requester voice check
        user: discord.Member = message.author  # type: ignore
        voice_state = getattr(user, "voice", None)
        if not voice_state or not voice_state.channel:
            await message.channel.send("Join a voice channel first and I'll play it there. 🎧")
            return True

        voice_channel = voice_state.channel

        # Handle controls (pause, resume, skip, stop, queue, now_playing)
        music_cog: Optional["MusicCog"] = bot.cogs.get("Music")  # type: ignore
        if not music_cog:
            return False

        player: "GuildMusicPlayer" = music_cog.get_player(message.guild)
        player.text_channel = message.channel

        if intent == MusicIntent.PAUSE:
            if player.voice_client and player.voice_client.is_playing():
                player.voice_client.pause()
                await message.channel.send("⏸️ Paused music playback.")
                await player.update_panel()
            else:
                await message.channel.send("⚠️ Nothing is currently playing.")
            return True

        if intent == MusicIntent.RESUME:
            if player.voice_client and player.voice_client.is_paused():
                player.voice_client.resume()
                await message.channel.send("▶️ Resumed music playback.")
                await player.update_panel()
            else:
                await message.channel.send("⚠️ Playback is not paused.")
            return True

        if intent == MusicIntent.SKIP:
            if player.voice_client and (player.voice_client.is_playing() or player.voice_client.is_paused()):
                current_title = player.current.title if player.current else "Track"
                player.voice_client.stop()
                await message.channel.send(f"⏭️ Skipped **{current_title}**.")
            else:
                await message.channel.send("⚠️ Nothing to skip.")
            return True

        if intent == MusicIntent.STOP:
            player.queue.clear()
            player.current = None
            if player.voice_client:
                player.voice_client.stop()
            await message.channel.send("⏹️ Cleared queue and stopped playback.")
            await player.update_panel()
            return True

        if intent == MusicIntent.QUEUE:
            total_queued = len(player.queue)
            cur = player.current.title if player.current else "None"
            lines = [f"**▶️ Now Playing:** {cur}"]
            if player.queue:
                lines.append(f"\n**Up Next ({total_queued}):**")
                for i, s in enumerate(player.queue[:5], 1):
                    dur_str = f"{s.duration // 60}:{s.duration % 60:02d}" if s.duration else "Live"
                    req = s.requester.mention if s.requester else "Unknown"
                    lines.append(f"`{i}.` [{s.title}]({s.url}) (`{dur_str}`) — {req}")
            else:
                lines.append("\n*The queue is empty.*")
            embed = create_embed(
                title=f"🎧 Music Queue — {message.guild.name}",
                description="\n".join(lines),
                color=Colors.PRIMARY,
            )
            embed.set_footer(text=f"Total: {total_queued} queued tracks")
            await message.channel.send(embed=embed)
            return True

        if intent == MusicIntent.NOW_PLAYING:
            if not player.current:
                await message.channel.send("ℹ️ No track is currently playing.")
                return True
            embed = music_cog._create_now_playing_embed(player, player.current)
            await message.channel.send(embed=embed)
            return True

        # Handle PLAY / PLAYNOW
        if confidence == IntentConfidence.MEDIUM:
            view = MusicRequestConfirmView(
                service=self,
                bot=bot,
                requester=user,
                query=query,
                target_channel=voice_channel,
            )
            await message.channel.send(
                f"Did you want me to play **{query}**? 🎵",
                view=view,
            )
            return True

        # Check rate limit
        if self.check_rate_limit(user.id):
            await message.channel.send("Slow down 🎵 Try again in a few seconds.")
            return True

        # Check duplicate
        if self.check_duplicate_request(user.id, query):
            await message.channel.send("That song is already queued. 🎵")
            return True

        play_now = (intent == MusicIntent.PLAYNOW)
        await self.execute_play_request(
            bot=bot,
            guild=message.guild,
            channel=message.channel,
            user=user,
            query=query,
            play_now=play_now,
            voice_channel=voice_channel,
        )
        return True

    async def execute_play_request(
        self,
        bot: "SentinelBot",
        guild: discord.Guild,
        channel: discord.abc.Messageable,
        user: discord.Member,
        query: str,
        play_now: bool,
        voice_channel: Optional[discord.VoiceChannel] = None,
    ) -> bool:
        """
        Executes verified song resolution, queue insertion, and zero-interference playback.
        """
        async with self._get_guild_lock(guild.id):
            music_cog: Optional["MusicCog"] = bot.cogs.get("Music")  # type: ignore
            if not music_cog:
                return False

            player: "GuildMusicPlayer" = music_cog.get_player(guild)
            player.text_channel = channel

            # 1. Connect or verify voice channel (seamless Dynamic VC support)
            target_vc = voice_channel or getattr(getattr(user, "voice", None), "channel", None)
            if not target_vc:
                await channel.send("Join a voice channel first and I'll play it there. 🎧")
                return False

            vc = guild.voice_client
            if vc is None:
                perms = target_vc.permissions_for(guild.me)
                if not perms.connect or not perms.speak:
                    await channel.send("❌ Rai does not have permission to connect/speak in your voice channel.")
                    return False
                try:
                    vc = await target_vc.connect()
                except Exception as exc:
                    logger.error(f"Voice connection failure in {guild.name}: {exc}")
                    await channel.send(f"❌ Failed to connect to voice channel: {exc}")
                    return False
            elif vc.channel.id != target_vc.id:
                try:
                    await vc.move_to(target_vc)
                except Exception as exc:
                    logger.warning(f"Could not move voice client in {guild.name}: {exc}")

            # 2. Search & Candidate Lookup
            search_service = music_cog.search_service
            resolver_service = music_cog.resolver_service
            query_type, clean_query = search_service.classify_query(query)

            await channel.send(f"🔎 Searching for **{clean_query}**...")

            # 3. Direct URL or Candidate Resolution
            song_to_enqueue: Optional[Any] = None
            if query_type == QueryType.DIRECT_URL:
                res = await resolver_service.resolve_track(
                    clean_query,
                    requester=user,
                    guild_id=guild.id,
                    voice_channel_id=target_vc.id,
                    bot=bot,
                )
                if not res.is_success or not res.track:
                    diag_id = res.diagnostic.diagnostic_id if res.diagnostic else generate_music_diagnostic_id()
                    await channel.send(
                        f"❌ Could not resolve audio stream for this URL.\n\nDiagnostic: `{diag_id}`"
                    )
                    return False
                from cogs.music import Song
                song_to_enqueue = Song.from_resolved(res.track, requester=user)
            else:
                candidates = await search_service.search_candidates(clean_query, limit=5, requester=user)
                if not candidates:
                    diag_id = generate_music_diagnostic_id()
                    await channel.send(f"❌ I couldn't find a playable track for: **{clean_query}**")
                    return False

                # Resolve first candidate
                selected_candidate = candidates[0]
                res = await resolver_service.resolve_track(
                    selected_candidate,
                    requester=user,
                    guild_id=guild.id,
                    voice_channel_id=target_vc.id,
                    bot=bot,
                )
                if not res.is_success or not res.track:
                    diag_id = res.diagnostic.diagnostic_id if res.diagnostic else generate_music_diagnostic_id()
                    await channel.send(
                        f"❌ I found the track, but the audio source could not be prepared.\n\nDiagnostic: `{diag_id}`"
                    )
                    return False
                from cogs.music import Song
                song_to_enqueue = Song.from_resolved(res.track, requester=user)

            if not song_to_enqueue or not song_to_enqueue.stream_url:
                await channel.send("❌ Audio stream validation failed for this track.")
                return False

            # 4. ZERO-INTERFERENCE PLAYBACK ENFORCEMENT
            # If explicit play_now requested: stop current and play immediately
            if play_now:
                player.current = song_to_enqueue
                if vc.is_playing() or vc.is_paused():
                    vc.stop()
                try:
                    from cogs.music import FFMPEG_OPTIONS, MusicControlView
                    source = discord.PCMVolumeTransformer(
                        discord.FFmpegPCMAudio(song_to_enqueue.stream_url, **FFMPEG_OPTIONS),
                        volume=player.volume,
                    )
                    vc.play(source, after=player.play_next)
                    panel_embed = music_cog._create_now_playing_embed(player, song_to_enqueue)
                    panel_view = MusicControlView(music_cog, guild)
                    await channel.send(embed=panel_embed, view=panel_view)
                    return True
                except Exception as exc:
                    logger.error(f"Playback error in {guild.name}: {exc}")
                    await channel.send(f"❌ Failed to start playback: {exc}")
                    return False

            # Normal natural song request behavior:
            # If ALREADY PLAYING: DO NOT INTERRUPT! Add to queue!
            if vc.is_playing() or player.current:
                player.queue.append(song_to_enqueue)
                dur_str = f"{song_to_enqueue.duration // 60}:{song_to_enqueue.duration % 60:02d}" if song_to_enqueue.duration else "Live"
                pos = len(player.queue)
                await channel.send(
                    f"🎵 Added to queue: **{song_to_enqueue.title}** (Position #{pos}) — `{dur_str}`"
                )
                await player.update_panel()
                return True

            # If nothing is currently playing: start playback immediately
            player.current = song_to_enqueue
            try:
                from cogs.music import FFMPEG_OPTIONS, MusicControlView
                source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(song_to_enqueue.stream_url, **FFMPEG_OPTIONS),
                    volume=player.volume,
                )
                vc.play(source, after=player.play_next)
                panel_embed = music_cog._create_now_playing_embed(player, song_to_enqueue)
                panel_view = MusicControlView(music_cog, guild)
                await channel.send(embed=panel_embed, view=panel_view)
                return True
            except Exception as exc:
                logger.error(f"Playback error in {guild.name}: {exc}")
                await channel.send(f"❌ Failed to start playback: {exc}")
                return False


class NaturalMusicRequestHandler:
    """Convenience handler binding NaturalMusicService to a specific bot & cog instance."""

    def __init__(self, bot: Any, cog: Any):
        self.bot = bot
        self.cog = cog
        self.service = NaturalMusicService.get_instance()

    async def handle_message(self, message: discord.Message) -> bool:
        return await self.service.handle_message(self.bot, message)
