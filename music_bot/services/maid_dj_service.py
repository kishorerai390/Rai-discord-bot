"""
AI Anime Maid Voice DJ Service for MusicMaid.
Provides configurable voice personality announcements (Maid, Tsundere, Hype, Chill, Cyberpunk),
TTS speech synthesis bumper generation, and stylish animated embed intros.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path
import random
import re
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request

import discord

from music_bot.database.models import QueuedTrack

logger = logging.getLogger("MusicMaid.MaidDJ")

CACHE_DIR = Path("data/maid_dj_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class MaidDJService:
    """Service managing Anime Maid Voice DJ announcements and TTS bumpers."""

    PERSONALITIES = {
        "maid": {
            "name": "Devoted Maid (メイド)",
            "avatar": "https://cdn.discordapp.com/emojis/1149721021484081232.webp?size=96&quality=lossless",
            "color": 0xEC4899,
            "badge": "☕ DEVOTED MAID",
            "lang": "en",
            "templates": [
                "Goshujin-sama~ Now serving {title} for Master {requester}! Enjoy your musical tea time nya~ ✨",
                "Master {requester}, your requested track {title} by {artist} is now playing! May it bring you joy~ 🌸",
                "Special melody prepared with love for Master {requester}: {title}! Please relax and enjoy nya~ ☕💖",
                "Right away Master {requester}! Up next in the mansion is {title}. Let the music soothe your heart~ 🎀",
            ],
        },
        "tsundere": {
            "name": "Tsundere Maid (ツンデレ)",
            "avatar": "https://cdn.discordapp.com/emojis/1149721025816793138.webp?size=96&quality=lossless",
            "color": 0xFF4757,
            "badge": "💢 TSUNDERE MAID",
            "lang": "en",
            "templates": [
                "B-Baka! It's not like I queued {title} just for you, {requester}... Just sit back and listen! 💢",
                "Hmph! Next track is {title} by {artist}. You better appreciate this, {requester}! 😤",
                "Don't get the wrong idea, {requester}! I was going to play {title} anyway... enjoy it or else! 💥",
                "Fine, {requester}! Here is your precious {title}! It's actually not bad... b-but don't tell anyone! 💫",
            ],
        },
        "hype": {
            "name": "Festival DJ Maid (フェスDJ)",
            "avatar": "https://cdn.discordapp.com/emojis/1149721029105123398.webp?size=96&quality=lossless",
            "color": 0xFF6B81,
            "badge": "🔥 HYPE DJ MAID",
            "lang": "en",
            "templates": [
                "DJ Maid in the mix! Drop the bass for {requester}! Turning up the energy with {title}! Let's GOOO! 🔥🎧",
                "Hands in the air! We got {title} coming in hot for {requester}! Let the beats drop! 🚀⚡",
                "Bass boosted and ready! Crank the volume for {requester}'s anthem: {title}! 💥🔊",
                "Club stage is on fire! Spinning {title} by {artist} for {requester}! Dance like nobody's watching! 💃🔥",
            ],
        },
        "chill": {
            "name": "Lo-Fi Night Maid (夜カフェ)",
            "avatar": "https://cdn.discordapp.com/emojis/1149721033282662481.webp?size=96&quality=lossless",
            "color": 0x70A1FF,
            "badge": "🌙 CHILL LO-FI MAID",
            "lang": "en",
            "templates": [
                "Welcome back. Take a deep breath and unwind. Up next for {requester} is {title} by {artist}. 🌙☕",
                "Midnight vibes activated. Sink into the cushions and let {title} wash over you, {requester}. 🌸✨",
                "Soft rain outside, warm melodies inside. Enjoy {title} for {requester}. Peaceful dreams. 🌧️🕯️",
                "Dim the lights. Floating through the night sky with {title} for {requester}. Relax and breathe. 🌌💜",
            ],
        },
        "cyberpunk": {
            "name": "Neo-Tokyo Synth Maid (電脳メイド)",
            "avatar": "https://cdn.discordapp.com/emojis/1149721036814274640.webp?size=96&quality=lossless",
            "color": 0x00E5FF,
            "badge": "⚡ CYBERPUNK MAID",
            "lang": "en",
            "templates": [
                "Neural sync established. Transmitting {title} into the cyber-grid for operative {requester}. Stream locked. ⚡🦾",
                "Grid frequency calibrated. Uplinking {title} by {artist}. Cybernetic audio engaged for {requester}. 🌐💾",
                "Neon protocol active. Broadcasting synthesized soundwave {title} for agent {requester}. System online. 🔮🚀",
                "Holographic buffer clear. Injecting {title} into cyber-space for {requester}. Audio bandwidth 100%. 🤖✨",
            ],
        },
    }

    @classmethod
    def clean_name(cls, name: str) -> str:
        """Sanitize requester name or track title for speech."""
        cleaned = re.sub(r"[^\w\s\-\.\,\!\?]", "", name or "")
        return cleaned.strip()[:35] or "Master"

    @classmethod
    def clean_title(cls, title: str) -> str:
        """Sanitize track title for spoken intro."""
        # Strip common video clutter like (Official Video), [MV], HD, 4K
        clean = re.sub(r"[\(\[\{].*?[\)\]\}]", "", title or "")
        clean = re.sub(r"(?i)\b(official|video|audio|lyrics|mv|hd|4k|remastered)\b", "", clean)
        clean = re.sub(r"[^\w\s\-\,\.\'\!]", "", clean)
        return clean.strip()[:40] or "this special song"

    @classmethod
    def clean_artist(cls, artist: str) -> str:
        """Sanitize artist name."""
        clean = re.sub(r"[^\w\s\-\,\.\'\!]", "", artist or "")
        return clean.strip()[:30] or "our favorite artist"

    @classmethod
    def generate_intro_text(
        cls,
        personality: str,
        track: QueuedTrack,
        requester_name: Optional[str] = None,
    ) -> str:
        """Generate a personalized spoken track intro for the given personality."""
        p_key = personality.lower().strip()
        if p_key not in cls.PERSONALITIES:
            p_key = "maid"

        cfg = cls.PERSONALITIES[p_key]
        template = random.choice(cfg["templates"])

        req = cls.clean_name(requester_name or track.requester_name or "Master")
        title = cls.clean_title(track.title)
        artist = cls.clean_artist(track.artist)

        return template.format(
            title=title,
            artist=artist,
            requester=req,
        )

    @classmethod
    async def fetch_speech_audio(cls, text: str, lang: str = "en") -> Optional[str]:
        """
        Synthesize speech MP3 via Google Translate TTS and cache locally.
        Returns the path to the MP3 file or None if unavailable.
        """
        try:
            # Hash text and lang for stable cache key
            cache_hash = hashlib.md5(f"{lang}:{text.strip()}".encode("utf-8")).hexdigest()
            cache_file = CACHE_DIR / f"tts_{cache_hash}.mp3"

            if cache_file.exists() and cache_file.stat().st_size > 1000:
                return str(cache_file.resolve())

            # Limit query string for TTS URL limit
            short_text = text.strip()[:100]
            encoded_query = urllib.parse.quote_plus(short_text)
            tts_url = (
                f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl={lang}&q={encoded_query}"
            )

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            }

            def _download() -> Optional[bytes]:
                req = urllib.request.Request(tts_url, headers=headers)
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    if resp.status == 200:
                        return resp.read()
                return None

            loop = asyncio.get_running_loop()
            audio_bytes = await loop.run_in_executor(None, _download)

            if audio_bytes and len(audio_bytes) > 500:
                cache_file.write_bytes(audio_bytes)
                return str(cache_file.resolve())

            return None
        except Exception as e:
            logger.debug(f"[MaidDJ] Failed to generate TTS audio bumper: {e}")
            return None

    @classmethod
    def build_announcement_embed(
        cls,
        track: QueuedTrack,
        intro_text: str,
        personality: str = "maid",
    ) -> discord.Embed:
        """Create a beautiful anime dialogue box embed."""
        p_key = personality.lower().strip()
        if p_key not in cls.PERSONALITIES:
            p_key = "maid"

        cfg = cls.PERSONALITIES[p_key]

        embed = discord.Embed(
            title=f"🎙️ {cfg['badge']}",
            description=f"💬 *\"{intro_text}\"*",
            color=cfg["color"],
        )
        embed.set_author(name=f"MusicMaid AI Voice DJ • {cfg['name']}", icon_url=cfg["avatar"])
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)

        embed.add_field(
            name="🎵 Up Next",
            value=f"**[{track.title}]({track.url})**",
            inline=True,
        )
        embed.add_field(
            name="👤 Requested By",
            value=f"<@{track.requester_id}>" if track.requester_id else track.requester_name,
            inline=True,
        )
        embed.set_footer(
            text="AI Maid DJ Announcer • Toggle with /maid-dj or m!maiddj",
            icon_url=cfg["avatar"],
        )
        return embed

    @classmethod
    async def announce_track(
        cls,
        bot: Any,
        session: Any,
        track: QueuedTrack,
    ) -> bool:
        """
        Handle voice and/or text intro announcement for the incoming track.
        """
        if not getattr(session, "maid_voice_dj_enabled", False):
            return False

        personality = getattr(session, "maid_dj_personality", "maid")
        cfg = cls.PERSONALITIES.get(personality, cls.PERSONALITIES["maid"])
        intro_text = cls.generate_intro_text(personality, track)

        # 1. Post animated dialogue embed to text channel
        if session.text_channel:
            try:
                embed = cls.build_announcement_embed(track, intro_text, personality)
                await session.text_channel.send(embed=embed)
            except Exception as embed_err:
                logger.debug(f"[MaidDJ] Failed to send intro embed: {embed_err}")

        # 2. Synthesize TTS speech audio bumper and play in voice channel before music starts
        if session.voice_client and session.voice_client.is_connected() and not session.voice_client.is_playing():
            try:
                speech_path = await cls.fetch_speech_audio(intro_text, lang=cfg.get("lang", "en"))
                if speech_path and os.path.exists(speech_path):
                    loop = asyncio.get_running_loop()
                    done_event = asyncio.Event()

                    def _after(err: Optional[Exception]):
                        loop.call_soon_threadsafe(done_event.set)

                    audio_source = discord.FFmpegPCMAudio(speech_path)
                    session.voice_client.play(audio_source, after=_after)

                    # Wait up to 4.5 seconds for the bumper to conclude, then proceed to the music
                    try:
                        await asyncio.wait_for(done_event.wait(), timeout=4.5)
                    except asyncio.TimeoutError:
                        pass
                    return True
            except Exception as voice_err:
                logger.debug(f"[MaidDJ] Voice intro speech playback bypassed: {voice_err}")

        return True
