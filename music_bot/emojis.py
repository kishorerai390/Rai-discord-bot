"""
MusicMaid Centralized Emoji Configuration and Resolver System.
Provides seamless support for:
1. Configurable custom Discord emojis via environment variables or runtime dictionary.
2. Verified Discord bot accessibility check (avoids 400 Bad Request if bot lacks access).
3. Graceful fallback to rich, anime-styled Unicode emojis.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional, Union
import discord

logger = logging.getLogger("MusicMaid.Emojis")

# Default Unicode Fallbacks (Curated Anime / Cyberpunk Aesthetic)
DEFAULT_EMOJI_REGISTRY: Dict[str, str] = {
    # Brand & Identity
    "LOGO": "🐾",
    "MASCOT": "🐱",
    "SPARKLES": "✨",
    "STAR": "⭐",
    
    # Music & Audio
    "NOTE": "🎵",
    "NOTES": "🎶",
    "DISC": "💿",
    "HEADPHONES": "🎧",
    "RADIO": "📻",
    "MICROPHONE": "🎙️",
    
    # Playback Controls
    "PLAY": "▶️",
    "PAUSE": "⏸️",
    "PREVIOUS": "⏮️",
    "NEXT": "⏭️",
    "SKIP": "⏭️",
    "STOP": "⏹️",
    "REWIND_10": "⏪",
    "FORWARD_10": "⏩",
    "LOOP": "🔁",
    "LOOP_ONE": "🔂",
    "SHUFFLE": "🔀",
    
    # Navigation & Actions
    "QUEUE": "📜",
    "PLAYLIST": "📑",
    "AUTODJ": "🎧",
    "VOLUME": "🔊",
    "VOLUME_MUTED": "🔇",
    "VOLUME_LOW": "🔉",
    "EQUALIZER": "🎛️",
    "FILTERS": "🎛️",
    "LYRICS": "🎤",
    "FAVORITE": "💖",
    "FAVORITE_OFF": "🤍",
    "PREMIUM": "💎",
    "VIP": "👑",
    
    # System & States
    "SEARCH": "🔍",
    "LOADING": "⏳",
    "BUFFERING": "🌀",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WARNING": "⚠️",
    "INFO": "ℹ️",
    "SETTINGS": "⚙️",
    "STATS": "📊",
    "DOCTOR": "🩺",
    "REFRESH": "🔄",
    "BACK": "⬅️",
    "CLOSE": "✖️",
    "TRASH": "🗑️",
    "PIN": "📌",
    "LIGHTNING": "⚡",
    "LINK": "🔗",
}

# Regex to detect custom emoji format: <:name:id> or <a:name:id>
CUSTOM_EMOJI_REGEX = re.compile(r"^<(?P<animated>a)?:(?P<name>[a-zA-Z0-9_]+):(?P<id>[0-9]+)>$")


class EmojiManager:
    """Centralized manager for MusicMaid emoji resolution, overrides, and Discord UI safety."""

    _overrides: Dict[str, str] = {}

    @classmethod
    def configure(cls, mapping: Dict[str, Any]) -> None:
        """Register runtime custom emoji overrides."""
        for k, v in mapping.items():
            if v is not None:
                cls._overrides[k.upper()] = str(v).strip()

    @classmethod
    def get_configured_val(cls, key: str) -> Optional[str]:
        """Look up override in memory, then in environment (e.g. EMOJI_PLAY or EMOJI_QUEUE)."""
        key_upper = key.upper()
        if key_upper in cls._overrides:
            return cls._overrides[key_upper]

        # Check environment variable
        env_val = os.getenv(f"EMOJI_{key_upper}", "").strip()
        if env_val:
            return env_val

        return None

    @classmethod
    def parse_emoji_id(cls, raw: str) -> Optional[int]:
        """Extract numeric Snowflake ID from integer, numeric string, or <:name:id> format."""
        if not raw:
            return None
        raw = raw.strip()
        if raw.isdigit():
            try:
                return int(raw)
            except ValueError:
                return None
        match = CUSTOM_EMOJI_REGEX.match(raw)
        if match:
            try:
                return int(match.group("id"))
            except ValueError:
                return None
        return None

    @classmethod
    def get(cls, key: str, bot: Optional[discord.Client] = None) -> str:
        """
        Return the emoji string suitable for Discord embeds and chat messages.
        If a custom emoji ID is configured and accessible via bot.get_emoji, returns <:name:id>.
        Otherwise falls back cleanly to the curated Unicode emoji.
        """
        key_upper = key.upper()
        fallback = DEFAULT_EMOJI_REGISTRY.get(key_upper, "✨")
        configured = cls.get_configured_val(key_upper)

        if not configured:
            return fallback

        # If already formatted as <:name:id> or <a:name:id>
        match = CUSTOM_EMOJI_REGEX.match(configured)
        if match:
            emoji_id = int(match.group("id"))
            if bot is not None:
                emoji_obj = bot.get_emoji(emoji_id)
                if emoji_obj is not None:
                    return str(emoji_obj)
                # Bot does not have access to this custom emoji; return fallback
                return fallback
            return configured

        # If configured as raw snowflake ID
        if configured.isdigit():
            emoji_id = int(configured)
            if bot is not None:
                emoji_obj = bot.get_emoji(emoji_id)
                if emoji_obj is not None:
                    return str(emoji_obj)
                return fallback
            return fallback

        # If configured as custom Unicode character or string
        return configured

    @classmethod
    def get_button_emoji(
        cls, key: str, bot: Optional[discord.Client] = None
    ) -> Union[discord.Emoji, str]:
        """
        Return an emoji object or string guaranteed safe for discord.ui.Button(emoji=...).
        Will NEVER cause an API 400 Bad Request error by attempting to send an inaccessible custom snowflake.
        """
        key_upper = key.upper()
        fallback = DEFAULT_EMOJI_REGISTRY.get(key_upper, "✨")
        configured = cls.get_configured_val(key_upper)

        if not configured:
            return fallback

        emoji_id = cls.parse_emoji_id(configured)
        if emoji_id is not None and bot is not None:
            emoji_obj = bot.get_emoji(emoji_id)
            if emoji_obj is not None:
                return emoji_obj

        # If not accessible or not a snowflake, check if it's standard Unicode string
        if not configured.isdigit() and not CUSTOM_EMOJI_REGEX.match(configured):
            return configured

        return fallback

    @classmethod
    def get_diagnostic_map(cls, bot: Optional[discord.Client] = None) -> Dict[str, Dict[str, Any]]:
        """Return diagnostic status of every emoji key."""
        result = {}
        for key, fallback in DEFAULT_EMOJI_REGISTRY.items():
            conf = cls.get_configured_val(key)
            emoji_id = cls.parse_emoji_id(conf) if conf else None
            accessible = False
            if emoji_id and bot:
                accessible = bot.get_emoji(emoji_id) is not None
            result[key] = {
                "configured": conf,
                "is_custom": emoji_id is not None,
                "emoji_id": emoji_id,
                "accessible": accessible,
                "active_display": cls.get(key, bot),
                "fallback": fallback,
            }
        return result
