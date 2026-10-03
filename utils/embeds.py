"""
Discord Embed Builder Utilities.
Ensures cohesive, elegant, and modern visual design across all bot interactions.
"""

from __future__ import annotations

import datetime
from typing import Optional, Any
import discord

from config import Colors


def create_embed(
    title: str,
    description: Optional[str] = None,
    color: int = Colors.PRIMARY,
    footer_text: Optional[str] = "Rai Security",
    footer_icon: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    image_url: Optional[str] = None,
    timestamp: bool = True,
) -> discord.Embed:
    """Base embed builder with consistent design tokens."""
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


def success_embed(title: str = "Success", description: Optional[str] = None) -> discord.Embed:
    return create_embed(
        title=f"✅ {title}",
        description=description,
        color=Colors.SUCCESS,
    )


def error_embed(title: str = "Error", description: Optional[str] = None) -> discord.Embed:
    return create_embed(
        title=f"❌ {title}",
        description=description,
        color=Colors.ERROR,
    )


def warning_embed(title: str = "Warning", description: Optional[str] = None) -> discord.Embed:
    return create_embed(
        title=f"⚠️ {title}",
        description=description,
        color=Colors.WARNING,
    )


def alert_embed(title: str = "Security Alert", description: Optional[str] = None) -> discord.Embed:
    return create_embed(
        title=f"🚨 {title}",
        description=description,
        color=Colors.ALERT,
    )


def security_embed(title: str = "Security Alert", description: Optional[str] = None) -> discord.Embed:
    return create_embed(
        title=f"🛡️ {title}",
        description=description,
        color=Colors.SECURITY,
    )


def info_embed(title: str = "Information", description: Optional[str] = None) -> discord.Embed:
    return create_embed(
        title=f"ℹ️ {title}",
        description=description,
        color=Colors.INFO,
    )
