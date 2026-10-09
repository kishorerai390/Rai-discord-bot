"""
Discord Embed Builder Utilities.
Ensures cohesive, elegant, and modern visual design across all bot interactions.
"""

from __future__ import annotations

import datetime
from typing import Optional, Any
import discord

from config import Colors


DEFAULT_BRAND = "『RΛI』"
DEFAULT_FOOTER = "RΛI://CORE"


def create_embed(
    title: str,
    description: Optional[str] = None,
    color: int = Colors.PRIMARY,
    footer_text: Optional[str] = DEFAULT_FOOTER,
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
    desc = f"> ✅ {description}" if description else None
    return create_embed(
        title=f"{DEFAULT_BRAND} • {title}",
        description=desc,
        color=Colors.SUCCESS,
        footer_text=DEFAULT_FOOTER,
    )


def error_embed(title: str = "Error", description: Optional[str] = None) -> discord.Embed:
    desc = f"> ❌ {description}" if description else None
    return create_embed(
        title=f"{DEFAULT_BRAND} • {title}",
        description=desc,
        color=Colors.ERROR,
        footer_text=DEFAULT_FOOTER,
    )


def warning_embed(title: str = "Warning", description: Optional[str] = None) -> discord.Embed:
    desc = f"> ⚠️ {description}" if description else None
    return create_embed(
        title=f"{DEFAULT_BRAND} • {title}",
        description=desc,
        color=Colors.WARNING,
        footer_text=DEFAULT_FOOTER,
    )


def alert_embed(title: str = "Security Alert", description: Optional[str] = None) -> discord.Embed:
    return create_embed(
        title=f"🚨 {title}",
        description=description,
        color=Colors.ALERT,
        footer_text=DEFAULT_FOOTER,
    )


def security_embed(title: str = "Security Alert", description: Optional[str] = None) -> discord.Embed:
    desc = f"> 🛡️ {description}" if description else None
    return create_embed(
        title=f"{DEFAULT_BRAND} • {title}",
        description=desc,
        color=Colors.SECURITY,
        footer_text=DEFAULT_FOOTER,
    )


def normalize_severity(severity: str) -> str:
    s = str(severity).upper()
    if "EMERGENCY" in s:
        return "☢️ EMERGENCY"
    elif "CRITICAL" in s:
        return "🔴 CRITICAL"
    elif "HIGH" in s:
        return "🟠 HIGH"
    elif "MEDIUM" in s:
        return "🟡 MEDIUM"
    else:
        return "🟢 LOW"


def security_alert_embed(
    event_type: str = "Security Event",
    severity: str = "MEDIUM",
    guild_name: Optional[str] = None,
    user_str: Optional[str] = None,
    action_taken: Optional[str] = None,
    incident_id: Optional[str] = None,
    details: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> discord.Embed:
    embed = create_embed(
        title=title or f"{DEFAULT_BRAND} • SECURITY ALERT",
        description=description or (f"> 🚨 Threat detected in **{guild_name}**" if guild_name else None),
        color=Colors.ALERT,
        footer_text=DEFAULT_FOOTER,
    )
    embed.add_field(name="🚨 Event Type", value=event_type, inline=True)
    embed.add_field(name="⚡ Severity", value=normalize_severity(severity), inline=True)
    if incident_id:
        embed.add_field(name="🆔 Incident ID", value=f"`{incident_id}`", inline=True)
    if guild_name:
        embed.add_field(name="🏛️ Guild", value=guild_name, inline=True)
    if user_str:
        embed.add_field(name="👤 Target / Actor", value=user_str, inline=True)
    if action_taken:
        embed.add_field(name="🛡️ Action Taken", value=action_taken, inline=False)
    if details:
        embed.add_field(name="📝 Details", value=details, inline=False)
    return embed


def security_dashboard_embed(guild_name: str, metrics: dict[str, Any]) -> discord.Embed:
    emoji_map = {
        "Protection": "🛡️",
        "Anti-Raid": "⚔️",
        "Anti-Nuke": "☢️",
        "Anti-Spam": "🔐",
        "AutoMod": "🤖",
        "Monitoring": "📡",
        "Health": "🩺",
    }
    lines = []
    for key, val in metrics.items():
        em = emoji_map.get(key, "🔹")
        lines.append(f"{em} {key:<16} {val}")
    desc = "\n".join(lines)
    return create_embed(
        title=f"{DEFAULT_BRAND} // SECURITY CENTER",
        description=desc,
        color=Colors.PRIMARY,
        footer_text=DEFAULT_FOOTER,
    )


def info_embed(title: str = "Information", description: Optional[str] = None) -> discord.Embed:
    return create_embed(
        title=f"ℹ️ {title}",
        description=description,
        color=Colors.INFO,
        footer_text=DEFAULT_FOOTER,
    )


def music_now_playing_embed(
    track_title: str,
    artist: str = "Unknown Artist",
    duration_str: str = "00:00",
    requested_by: str = "",
    queue_position: str = "Playing",
    player_status: str = "▶️ Playing",
    track_url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
) -> discord.Embed:
    """Standardized luxury now-playing embed for Rai Music."""
    if track_url:
        desc = f"**[{track_title}]({track_url})**\n`{artist}`\n"
    else:
        desc = f"**{track_title}**\n`{artist}`\n"
    embed = create_embed(
        title=f"{DEFAULT_BRAND} • NOW PLAYING",
        description=desc,
        color=Colors.PRIMARY,
        thumbnail_url=thumbnail_url,
        footer_text="Rai Audio Engine",
    )
    embed.add_field(name="⏱️ Duration", value=f"`{duration_str}`", inline=True)
    embed.add_field(name="👤 Requested by", value=str(requested_by), inline=True)
    embed.add_field(name="📜 Position", value=str(queue_position), inline=True)
    embed.add_field(name="🎚️ Player Status", value=str(player_status), inline=True)
    return embed
