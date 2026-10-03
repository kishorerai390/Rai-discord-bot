"""
RAI — CONTEXT ENGINE.
Understands channel-scoped purposes without ever executing unsolicited or dangerous actions.
Offers optional interactive suggestion buttons with strict user confirmation.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING, Optional

import discord

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.ContextEngine")


class ChannelContext(Enum):
    MUSIC_CONTEXT = "music"
    GAMING_CONTEXT = "gaming"
    CREATOR_CONTEXT = "creator"
    IDEA_CONTEXT = "idea"
    GENERAL_CONTEXT = "general"


class ContextEngine:
    _instance: Optional[ContextEngine] = None

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    @classmethod
    def get_instance(cls, bot: Optional[SentinelBot] = None) -> ContextEngine:
        if cls._instance is None:
            if bot is None:
                raise RuntimeError("ContextEngine requires bot instance.")
            cls._instance = cls(bot)
        return cls._instance

    def detect_context(self, channel: discord.abc.GuildChannel) -> ChannelContext:
        """Determines the operational scope of a channel based on name and category."""
        name = getattr(channel, "name", "").lower()
        cat_name = getattr(getattr(channel, "category", None), "name", "").lower()
        combined = f"{cat_name} {name}"

        if any(w in combined for w in ("music", "song", "request", "queue", "listening")):
            return ChannelContext.MUSIC_CONTEXT
        if any(w in combined for w in ("game", "gaming", "lfg", "squad", "scrim", "valorant", "bgmi", "teammate", "team")):
            return ChannelContext.GAMING_CONTEXT
        if any(w in combined for w in ("creator", "edit", "editing", "clip", "showcase", "vfx")):
            return ChannelContext.CREATOR_CONTEXT
        if any(w in combined for w in ("idea", "suggest", "feedback", "proposal")):
            return ChannelContext.IDEA_CONTEXT
        return ChannelContext.GENERAL_CONTEXT
