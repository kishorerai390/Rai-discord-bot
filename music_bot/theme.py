"""
MusicMaid Centralized Theme & Visual Identity System.
Defines:
- Curated anime-inspired neon palette (Electric Violet, Cyber Cyan, Midnight Blue, Emerald, Crimson).
- Standardized, consistent embed builders.
- Reusable UI tokens and badges for all commands and panels.
"""

from __future__ import annotations

import datetime
from typing import Optional, Union
import discord

from music_bot.emojis import EmojiManager

# =============================================================================
# COLOR PALETTE TOKENS
# =============================================================================

COLOR_PRIMARY: int = 0x9333EA      # Electric Violet / Anime Neon Purple
COLOR_CYAN: int = 0x00E5FF         # Cyber Neon Cyan
COLOR_MIDNIGHT: int = 0x0B0E14     # Deep Midnight Black
COLOR_SURFACE: int = 0x121725      # Surface Card Dark
COLOR_SUCCESS: int = 0x10B981      # Emerald Neon Green
COLOR_WARNING: int = 0xF59E0B      # Amber Glow
COLOR_ERROR: int = 0xEF4444        # Electric Crimson
COLOR_INFO: int = 0x00B0FF         # Neon Sky Blue
COLOR_PREMIUM: int = 0xEC4899      # Anime Neon Pink / VIP
COLOR_VIOLET: int = 0x8A2BE2       # Deep Blue Violet
COLOR_PLATINUM: int = 0xE2E8F0     # Platinum Silver Accent
COLOR_OBSIDIAN: int = 0x0A0A0F     # Deep Obsidian Midnight

BRAND_NAME: str = "MusicMaid"
STUDIO_BRAND: str = "Noctyra Studio"
DEFAULT_FOOTER: str = "MusicMaid ✦ Noctyra Studio Lossless Audio Engine"


def create_branded_embed(
    title: str,
    description: Optional[str] = None,
    color: int = COLOR_PRIMARY,
    footer_text: Optional[str] = DEFAULT_FOOTER,
    footer_icon: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    image_url: Optional[str] = None,
    timestamp: bool = True,
    bot: Optional[discord.Client] = None,
) -> discord.Embed:
    """Base embed builder with consistent anime neon styling and tokens."""
    embed = discord.Embed(
        title=title,
        description=description or "",
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc) if timestamp else None,
    )
    if footer_text:
        embed.set_footer(text=footer_text, icon_url=footer_icon)
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    if image_url:
        embed.set_image(url=image_url)
    return embed


def success_embed(
    title: str = "Success",
    description: Optional[str] = None,
    bot: Optional[discord.Client] = None,
) -> discord.Embed:
    """Construct an attractive success embed with anime-styled emerald accent."""
    icon = EmojiManager.get("SUCCESS", bot)
    desc = f"> {icon} {description}" if description else None
    return create_branded_embed(
        title=f"{EmojiManager.get('LOGO', bot)} {BRAND_NAME} ✦ {title}",
        description=desc,
        color=COLOR_SUCCESS,
        bot=bot,
    )


def error_embed(
    title: str = "Error",
    description: Optional[str] = None,
    bot: Optional[discord.Client] = None,
) -> discord.Embed:
    """Construct an error embed with clear, concise diagnosis and electric crimson accent."""
    icon = EmojiManager.get("ERROR", bot)
    desc = f"> {icon} {description}" if description else None
    return create_branded_embed(
        title=f"{EmojiManager.get('LOGO', bot)} {BRAND_NAME} ✦ {title}",
        description=desc,
        color=COLOR_ERROR,
        bot=bot,
    )


def warning_embed(
    title: str = "Warning",
    description: Optional[str] = None,
    bot: Optional[discord.Client] = None,
) -> discord.Embed:
    """Construct an amber warning embed."""
    icon = EmojiManager.get("WARNING", bot)
    desc = f"> {icon} {description}" if description else None
    return create_branded_embed(
        title=f"{EmojiManager.get('LOGO', bot)} {BRAND_NAME} ✦ {title}",
        description=desc,
        color=COLOR_WARNING,
        bot=bot,
    )


def loading_embed(
    title: str = "Processing",
    description: Optional[str] = None,
    bot: Optional[discord.Client] = None,
) -> discord.Embed:
    """Construct a loading/resolving embed with cyber cyan accent."""
    icon = EmojiManager.get("LOADING", bot)
    desc = f"> {icon} {description}" if description else None
    return create_branded_embed(
        title=f"{EmojiManager.get('LOGO', bot)} {BRAND_NAME} ✦ {title}",
        description=desc,
        color=COLOR_CYAN,
        bot=bot,
    )


def info_embed(
    title: str = "Information",
    description: Optional[str] = None,
    bot: Optional[discord.Client] = None,
) -> discord.Embed:
    """Construct an informational embed with neon sky blue accent."""
    icon = EmojiManager.get("INFO", bot)
    desc = f"> {icon} {description}" if description else None
    return create_branded_embed(
        title=f"{EmojiManager.get('LOGO', bot)} {BRAND_NAME} ✦ {title}",
        description=desc,
        color=COLOR_INFO,
        bot=bot,
    )


def premium_embed(
    title: str = "Premium Perks",
    description: Optional[str] = None,
    bot: Optional[discord.Client] = None,
) -> discord.Embed:
    """Construct a premium embed with anime neon pink accent."""
    icon = EmojiManager.get("PREMIUM", bot)
    return create_branded_embed(
        title=f"{icon} {BRAND_NAME} ✦ {title}",
        description=description,
        color=COLOR_PREMIUM,
        bot=bot,
    )
