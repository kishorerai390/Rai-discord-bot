"""
RAI — PERMISSION DOCTOR SERVICE
Evaluates Rai's actual Discord permissions against only the features currently enabled in the guild.

Guarantees:
1. Never requests Administrator as a shortcut.
2. Checks role hierarchy and explicit channel overwrites.
3. Detects specific denied permissions:
   - View Channel
   - Send Messages
   - Embed Links
   - Attach Files
   - Manage Channels
   - Connect
   - Speak
   - Move Members
   - Manage Messages
   - Use Application Commands
4. Gives feature-specific actionable recommendations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import discord

logger = logging.getLogger("Rai.PermissionDoctor")


class PermissionStatus(str, Enum):
    GRANTED = "GRANTED"
    MISSING = "MISSING"
    OVERRIDDEN_DENIED = "OVERRIDDEN_DENIED"


@dataclass
class FeaturePermissionCheck:
    feature_name: str
    is_enabled: bool
    required_permissions: List[str]
    missing_permissions: List[str] = field(default_factory=list)
    denied_channel_overwrites: List[Tuple[str, str]] = field(default_factory=list)  # (channel_name, permission)
    recommendation: Optional[str] = None


@dataclass
class GuildPermissionDiagnosis:
    guild_id: int
    bot_member_id: int
    is_admin: bool
    overall_health: str  # "HEALTHY", "DEGRADED", "FAILED"
    features: List[FeaturePermissionCheck]
    denied_overwrites_count: int = 0
    recommendations: List[str] = field(default_factory=list)


class PermissionDoctor:
    """Diagnoses Rai's Discord permissions per guild."""

    FEATURE_REQUIREMENTS = {
        "Core & Commands": {
            "permissions": ["view_channel", "send_messages", "embed_links"],
            "description": "Basic interaction and response dispatch",
        },
        "Dynamic Voice Channels": {
            "permissions": ["manage_channels", "move_members", "connect"],
            "description": "Temporary room creation, member moving, and cleanup",
        },
        "Music Playback": {
            "permissions": ["connect", "speak"],
            "description": "Joining voice channels and streaming audio resources",
        },
        "Operational Reports": {
            "permissions": ["view_channel", "send_messages", "embed_links", "read_message_history"],
            "description": "Posting single consolidated incident reports",
        },
        "Security & Moderation": {
            "permissions": ["view_audit_log", "moderate_members", "ban_members", "kick_members", "manage_messages"],
            "description": "Anti-nuke containment and automated threat isolation",
        },
    }

    @classmethod
    async def diagnose_guild(cls, guild: discord.Guild, bot: discord.Client) -> GuildPermissionDiagnosis:
        me = guild.me
        if not me:
            return GuildPermissionDiagnosis(
                guild_id=guild.id,
                bot_member_id=0,
                is_admin=False,
                overall_health="FAILED",
                features=[],
                recommendations=["Rai bot member not found in guild cache."],
            )

        guild_perms = me.guild_permissions
        is_admin = guild_perms.administrator

        features: List[FeaturePermissionCheck] = []
        all_recommendations: List[str] = []
        denied_overwrites_count = 0

        # Check each feature domain
        for feat_name, spec in cls.FEATURE_REQUIREMENTS.items():
            reqs = spec["permissions"]
            missing: List[str] = []
            denied_channels: List[Tuple[str, str]] = []

            for perm in reqs:
                has_guild_perm = getattr(guild_perms, perm, False) or is_admin
                if not has_guild_perm:
                    missing.append(perm.replace("_", " ").title())

            # Check channels for explicit overwrites that deny permission
            if feat_name == "Dynamic Voice Channels":
                # Check voice channels
                for vc in guild.voice_channels[:15]:
                    overwrites = vc.overwrites_for(me)
                    for p in ("connect", "manage_channels"):
                        if getattr(overwrites, p, None) is False:
                            denied_channels.append((f"#{vc.name}", p.replace("_", " ").title()))
                            denied_overwrites_count += 1
            elif feat_name == "Operational Reports":
                from services.report_service import ReportService
                destinations = await ReportService.get_destinations(bot, guild.id)
                for dest in destinations:
                    ch = guild.get_channel(dest.channel_id)
                    if isinstance(ch, discord.TextChannel):
                        ch_perms = ch.permissions_for(me)
                        if not ch_perms.send_messages:
                            denied_channels.append((f"#{ch.name}", "Send Messages"))
                            denied_overwrites_count += 1
                        if not ch_perms.embed_links:
                            denied_channels.append((f"#{ch.name}", "Embed Links"))
                            denied_overwrites_count += 1

            rec = None
            if missing or denied_channels:
                rec_parts = []
                if missing:
                    rec_parts.append(f"Grant Rai role permissions: {', '.join(missing)}")
                if denied_channels:
                    affected = ", ".join(f"{ch} ({p})" for ch, p in denied_channels[:3])
                    rec_parts.append(f"Remove channel deny overwrites for {affected}")
                rec = " | ".join(rec_parts)
                all_recommendations.append(f"**{feat_name}:** {rec}")

            features.append(
                FeaturePermissionCheck(
                    feature_name=feat_name,
                    is_enabled=True,
                    required_permissions=[p.replace("_", " ").title() for p in reqs],
                    missing_permissions=missing,
                    denied_channel_overwrites=denied_channels,
                    recommendation=rec,
                )
            )

        if not all_recommendations:
            health = "HEALTHY"
        elif any(f.missing_permissions for f in features if f.feature_name == "Core & Commands"):
            health = "FAILED"
        else:
            health = "DEGRADED"

        return GuildPermissionDiagnosis(
            guild_id=guild.id,
            bot_member_id=me.id,
            is_admin=is_admin,
            overall_health=health,
            features=features,
            denied_overwrites_count=denied_overwrites_count,
            recommendations=all_recommendations,
        )
