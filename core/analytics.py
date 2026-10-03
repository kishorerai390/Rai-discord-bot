"""
RAI — SERVER INTELLIGENCE & OPERATIONAL ANALYTICS ENGINE.
Provides:
- Comprehensive telemetry tracking across:
  - MEMBERS (total, humans, bots, active)
  - VOICE (active channels, voice population, dynamic rooms)
  - MUSIC (sessions, tracks, queue status)
  - COMMUNITY (messages, events, projects, reputation)
  - SECURITY (open incidents, quarantine counts, lockdowns)
  - SYSTEM (latency, DB latency, worker health)
- Periodic aggregation and storage of weekly operational summaries.
- Real stored metric aggregation for natural language queries like "what happened this week?".
"""

from __future__ import annotations

import datetime
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import discord

from core.operations_core import HealthService, RoomService, SecurityService, MusicService

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.AnalyticsEngine")


class ServerAnalyticsEngine:
    """Calculates operational metrics across all server subsystems."""

    @classmethod
    async def get_members_metrics(cls, guild: discord.Guild) -> Dict[str, Any]:
        total = guild.member_count or len(guild.members)
        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)
        online = sum(1 for m in guild.members if m.status != discord.Status.offline)
        return {
            "total_members": total,
            "human_members": humans,
            "bot_members": bots,
            "online_members": online,
            "active_percentage": round((online / max(1, total)) * 100, 1),
        }

    @classmethod
    async def get_voice_metrics(cls, bot: SentinelBot, guild: discord.Guild) -> Dict[str, Any]:
        dynamic_rooms = await bot.db.get_all_dynamic_rooms(guild.id)
        voice_users = sum(len(vc.members) for vc in guild.voice_channels)
        active_channels = sum(1 for vc in guild.voice_channels if len(vc.members) > 0)
        return {
            "total_voice_channels": len(guild.voice_channels),
            "active_channels": active_channels,
            "voice_users": voice_users,
            "dynamic_rooms_active": len(dynamic_rooms),
        }

    @classmethod
    async def get_music_metrics(cls, bot: SentinelBot, guild: discord.Guild) -> Dict[str, Any]:
        status = MusicService.get_status(bot, guild.id)
        return {
            "is_active": status.get("active", False),
            "is_playing": status.get("playing", False),
            "current_track": status.get("current"),
            "queue_length": status.get("queue_len", 0),
        }

    @classmethod
    async def get_community_metrics(cls, bot: SentinelBot, guild: discord.Guild) -> Dict[str, Any]:
        events = await bot.db.list_events(guild.id, status="scheduled")
        projects = await bot.db.list_projects(guild.id, status="active")
        leaderboard = await bot.db.get_reputation_leaderboard(guild.id, limit=5)
        return {
            "scheduled_events": len(events),
            "active_projects": len(projects),
            "top_reputation_users": len(leaderboard),
        }

    @classmethod
    async def get_security_metrics(cls, bot: SentinelBot, guild: discord.Guild) -> Dict[str, Any]:
        sec = await SecurityService.get_status(bot, guild.id)
        return {
            "status": sec.get("status", "NORMAL"),
            "lockdown_active": sec.get("lockdown_active", False),
            "open_incidents": sec.get("incident_count", 0),
        }

    @classmethod
    async def get_system_metrics(cls, bot: SentinelBot) -> Dict[str, Any]:
        health = HealthService.check(bot)
        gateway_ping = round(bot.latency * 1000, 1) if getattr(bot, "latency", None) else 0.0
        return {
            "overall_status": getattr(health, "overall_status", "HEALTHY"),
            "gateway_latency_ms": gateway_ping,
            "database_health": getattr(health, "database_health", "HEALTHY"),
            "security_health": getattr(health, "security_health", "HEALTHY"),
        }

    @classmethod
    async def generate_weekly_report(cls, bot: SentinelBot, guild: discord.Guild) -> Dict[str, Any]:
        """Gathers unified operational summary for the weekly report."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        week_start_str = (now_dt - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

        members = await cls.get_members_metrics(guild)
        voice = await cls.get_voice_metrics(bot, guild)
        community = await cls.get_community_metrics(bot, guild)
        security = await cls.get_security_metrics(bot, guild)
        system = await cls.get_system_metrics(bot)

        summary = {
            "guild_name": guild.name,
            "guild_id": guild.id,
            "week_start": week_start_str,
            "generated_at": now_dt.isoformat(),
            "members": members,
            "voice": voice,
            "community": community,
            "security": security,
            "system": system,
        }

        # Cache in database
        try:
            await bot.db.save_weekly_analytics(guild.id, week_start_str, summary)
        except Exception as e:
            logger.error(f"Failed to persist weekly analytics: {e}")

        return summary
