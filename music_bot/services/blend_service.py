"""
Friend Blend Service for MusicMaid.
Blends two Discord users' musical tastes, favorites, and listening history into a
curated dual-personality smart mix with musical taste compatibility scoring.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import random
from typing import Any, Dict, List, Optional, Set

import discord

from music_bot.database.models import QueuedTrack

logger = logging.getLogger("MusicMaid.Blend")


@dataclass
class FriendBlendResult:
    user1_name: str
    user2_name: str
    compatibility_pct: int
    blend_title: str
    vibe_description: str
    tracks: List[QueuedTrack] = field(default_factory=list)
    shared_artists: List[str] = field(default_factory=list)
    user1_track_count: int = 0
    user2_track_count: int = 0


class FriendBlendService:
    """Computes musical synergy between two users and creates a blended queue."""

    VIBE_TIERS = [
        (90, "💖 Soulmate Frequency", "Your musical tastes are in near-perfect harmonic resonance! You two share the exact same rhythm and anime/synthwave energy."),
        (80, "⚡ High-Energy Synergy", "A vibrant crossover! Your distinct tastes balance each other out with electric tempo and shared peak artists."),
        (70, "🌸 Balanced Chemistry", "A sweet harmony of styles! One brings the upbeat drive while the other supplies smooth melodies."),
        (60, "☕ Eclectic Exploration", "Two unique sonic worlds colliding! A rich contrast of chill beats and energetic anthems to expand your horizons."),
    ]

    @classmethod
    async def generate_blend(
        cls,
        bot: Any,
        guild_id: int,
        user1: discord.abc.User,
        user2: discord.abc.User,
        target_size: int = 15,
    ) -> FriendBlendResult:
        """
        Synthesize a friend blend between user1 and user2.
        """
        user1_name = getattr(user1, "display_name", str(user1))
        user2_name = getattr(user2, "display_name", str(user2))

        # 1. Fetch favorites
        favs1 = []
        favs2 = []
        if hasattr(bot, "db") and bot.db:
            try:
                favs1 = await bot.db.get_favorites(user1.id)
            except Exception as e:
                logger.debug(f"[Blend] User 1 favs error: {e}")
            try:
                favs2 = await bot.db.get_favorites(user2.id)
            except Exception as e:
                logger.debug(f"[Blend] User 2 favs error: {e}")

        # 2. Fetch guild history to identify played songs
        guild_history = []
        if hasattr(bot, "db") and bot.db:
            try:
                guild_history = await bot.db.get_history(guild_id, limit=50)
            except Exception:
                pass

        # Extract artists
        artists1 = {f.artist.lower().strip() for f in favs1 if getattr(f, "artist", None)}
        artists2 = {f.artist.lower().strip() for f in favs2 if getattr(f, "artist", None)}
        shared_raw = artists1.intersection(artists2)
        shared_artists = [a.title() for a in shared_raw if a and a != "Unknown Artist"]

        # Calculate compatibility score
        base_score = 68
        overlap_bonus = len(shared_artists) * 8
        history_bonus = min(15, len(guild_history) // 3)
        total_score = min(98, base_score + overlap_bonus + history_bonus)

        # Select vibe description based on score
        vibe_title = "💖 Soulmate Frequency"
        vibe_desc = "Your musical tastes are in harmonic resonance!"
        for threshold, v_title, v_desc in cls.VIBE_TIERS:
            if total_score >= threshold:
                vibe_title = v_title
                vibe_desc = v_desc
                break

        # Blend tracks: interweave user1 and user2 tracks
        blended_tracks: List[QueuedTrack] = []
        pool1: List[QueuedTrack] = [
            QueuedTrack(
                title=f.title,
                url=f.url,
                stream_url="",
                duration=getattr(f, "duration", 0),
                artist=getattr(f, "artist", "Various"),
                thumbnail=getattr(f, "thumbnail", None),
                requester_id=user1.id,
                requester_name=f"{user1_name}'s Pick",
            )
            for f in favs1
        ]
        pool2: List[QueuedTrack] = [
            QueuedTrack(
                title=f.title,
                url=f.url,
                stream_url="",
                duration=getattr(f, "duration", 0),
                artist=getattr(f, "artist", "Various"),
                thumbnail=getattr(f, "thumbnail", None),
                requester_id=user2.id,
                requester_name=f"{user2_name}'s Pick",
            )
            for f in favs2
        ]

        # If pools are small, supplement from guild history
        if len(pool1) < 3 and guild_history:
            for h in guild_history:
                if len(pool1) >= 6:
                    break
                pool1.append(
                    QueuedTrack(
                        title=h["title"],
                        url=h["url"],
                        stream_url="",
                        duration=180,
                        artist=h.get("artist") or "Featured",
                        requester_id=user1.id,
                        requester_name=f"{user1_name}'s Vibe",
                    )
                )

        if len(pool2) < 3 and guild_history:
            for h in reversed(guild_history):
                if len(pool2) >= 6:
                    break
                pool2.append(
                    QueuedTrack(
                        title=h["title"],
                        url=h["url"],
                        stream_url="",
                        duration=180,
                        artist=h.get("artist") or "Featured",
                        requester_id=user2.id,
                        requester_name=f"{user2_name}'s Vibe",
                    )
                )

        # Fallback if both empty
        if not pool1 and not pool2:
            default_anthems = [
                ("Suzume (Theme)", "RADWIMPS", "https://youtube.com/watch?v=mock1"),
                ("Sparkle", "RADWIMPS", "https://youtube.com/watch?v=mock2"),
                ("Idol", "YOASOBI", "https://youtube.com/watch?v=mock3"),
                ("Racing into the Night", "YOASOBI", "https://youtube.com/watch?v=mock4"),
                ("KICK BACK", "Kenshi Yonezu", "https://youtube.com/watch?v=mock5"),
            ]
            for title, art, url in default_anthems:
                pool1.append(QueuedTrack(title=title, artist=art, url=url, stream_url="", duration=210, requester_id=user1.id, requester_name=user1_name))
                pool2.append(QueuedTrack(title=title, artist=art, url=url, stream_url="", duration=210, requester_id=user2.id, requester_name=user2_name))

        # Interweave
        random.shuffle(pool1)
        random.shuffle(pool2)

        u1_count = 0
        u2_count = 0
        max_len = max(len(pool1), len(pool2))
        for i in range(max_len):
            if i < len(pool1) and len(blended_tracks) < target_size:
                blended_tracks.append(pool1[i])
                u1_count += 1
            if i < len(pool2) and len(blended_tracks) < target_size:
                blended_tracks.append(pool2[i])
                u2_count += 1

        blend_title = f"✨ {user1_name} & {user2_name}'s Neon Blend"

        return FriendBlendResult(
            user1_name=user1_name,
            user2_name=user2_name,
            compatibility_pct=total_score,
            blend_title=blend_title,
            vibe_description=f"**{vibe_title}**\n{vibe_desc}",
            tracks=blended_tracks,
            shared_artists=shared_artists[:5],
            user1_track_count=u1_count,
            user2_track_count=u2_count,
        )

    @classmethod
    def build_blend_embed(cls, blend: FriendBlendResult) -> discord.Embed:
        """Create a vibrant anime/neon embed for the blended playlist."""
        embed = discord.Embed(
            title=f"🎧 FRIEND BLEND • {blend.compatibility_pct}% MATCH",
            description=(
                f"**{blend.blend_title}**\n\n"
                f"{blend.vibe_description}\n\n"
                f"• **{blend.user1_name}'s contribution:** `{blend.user1_track_count} tracks`\n"
                f"• **{blend.user2_name}'s contribution:** `{blend.user2_track_count} tracks`\n"
                f"• **Total Blended Queue:** `{len(blend.tracks)} tracks`"
            ),
            color=0xEC4899,
        )

        if blend.shared_artists:
            embed.add_field(
                name="✨ Top Shared Artists",
                value=" • ".join(f"`{a}`" for a in blend.shared_artists),
                inline=False,
            )

        # Show preview of first 5 tracks
        preview_lines = []
        for idx, t in enumerate(blend.tracks[:6], 1):
            badge = "🟣" if idx % 2 != 0 else "🔵"
            preview_lines.append(f"{badge} **{idx}.** {t.artist} — **{t.title}** *({t.requester_name})*")

        if preview_lines:
            embed.add_field(
                name="🎶 Blend Preview (Interwoven)",
                value="\n".join(preview_lines),
                inline=False,
            )

        embed.set_footer(text="MusicMaid Friend Blend • Queued automatically into your active session")
        return embed
