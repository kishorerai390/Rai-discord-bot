"""DJ role authorization and fair 50% voice-channel skip voting."""

from __future__ import annotations

import asyncio
import math
from typing import Any, Iterable, Optional

import discord


class DJAccessService:
    """Central policy for DJ-only stop and DJ-bypass / listener-vote skip."""

    @staticmethod
    async def is_dj(bot: Any, guild: Optional[discord.Guild], member: Any) -> bool:
        if guild is None or member is None:
            return False

        permissions = getattr(member, "guild_permissions", None)
        if permissions and (
            getattr(permissions, "administrator", False)
            or getattr(permissions, "manage_guild", False)
        ):
            return True

        db = getattr(bot, "db", None)
        if db is None or not hasattr(db, "get_guild_settings"):
            return False

        try:
            settings = await db.get_guild_settings(guild.id)
            role_id = getattr(settings, "dj_role_id", None)
        except Exception:
            return False

        if not role_id:
            return False

        return any(getattr(role, "id", None) == int(role_id) for role in getattr(member, "roles", []))

    @staticmethod
    def required_votes(listener_count: int) -> int:
        """Return the ceiling of 50% of connected human listeners."""
        return max(1, math.ceil(max(0, listener_count) * 0.5))

    @staticmethod
    def record_vote(votes: set[int], user_id: int, listener_ids: Iterable[int]) -> int:
        """Discard stale/non-listener votes, add this listener once, and return count."""
        eligible = {int(uid) for uid in listener_ids}
        votes.intersection_update(eligible)
        if int(user_id) in eligible:
            votes.add(int(user_id))
        return len(votes)

    @classmethod
    async def request_skip(cls, bot: Any, session: Any, member: Any) -> tuple[bool, str, Optional[Any]]:
        """Skip immediately for DJs; otherwise require 50% of humans in the bot's VC."""
        guild = getattr(member, "guild", None) or getattr(bot, "get_guild", lambda _id: None)(session.guild_id)
        voice = getattr(member, "voice", None)
        member_channel = getattr(voice, "channel", None)
        vc = getattr(session, "voice_client", None)
        bot_channel = getattr(vc, "channel", None)

        if not member_channel or not bot_channel or member_channel.id != bot_channel.id:
            return False, "❌ Join Rem's voice channel before voting to skip.", None

        if await cls.is_dj(bot, guild, member):
            session.skip_votes.clear()
            from music_bot.services.player_service import MusicPlayerService
            return await MusicPlayerService.skip(bot, session)

        listeners = [
            listener for listener in getattr(bot_channel, "members", [])
            if not getattr(listener, "bot", False)
        ]
        listener_ids = {int(listener.id) for listener in listeners}
        vote_lock = getattr(session, "_dj_vote_lock", None)
        if vote_lock is None:
            vote_lock = asyncio.Lock()
            session._dj_vote_lock = vote_lock

        async with vote_lock:
            if getattr(session, "_dj_vote_skip_in_progress", False):
                return False, "⏳ A vote-approved skip is already processing.", None
            current_votes = cls.record_vote(session.skip_votes, int(member.id), listener_ids)
            required = cls.required_votes(len(listener_ids))
            passed = current_votes >= required
            if passed:
                session.skip_votes.clear()
                session._dj_vote_skip_in_progress = True

        if passed:
            try:
                from music_bot.services.player_service import MusicPlayerService
                success, message, next_track = await MusicPlayerService.skip(bot, session)
                if success:
                    return True, f"⏭️ **Vote passed!** ({current_votes}/{required})\n{message}", next_track
                return success, message, next_track
            finally:
                session._dj_vote_skip_in_progress = False

        return False, (
            f"🗳️ **Vote to Skip:** {current_votes}/{required} listeners voted. "
            f"Need {required - current_votes} more vote(s) to skip."
        ), None
