"""
Diagnostics and Health Audit Engine for Rai Music Bot (/music doctor & /music status).
Provides truthful, non-fabricated metrics and status verification across all music stages.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import discord

from music_bot.config import MUSIC_BOT_ID, MUSIC_BOT_VERSION
from music_bot.services.resolver_service import AudioResolver
from music_bot.services.session_service import SessionManager

if TYPE_CHECKING:
    from music_bot.bot import RaiMusicBot

logger = logging.getLogger("RaiMusic.Diagnostics")


@dataclass
class DiagnosticProbe:
    name: str
    status: str  # "HEALTHY", "DEGRADED", "FAILED"
    badge: str
    latency_ms: float
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    fix: Optional[str] = None


class MusicDiagnosticsService:
    """Master health auditor for Rai Music Bot."""

    @classmethod
    async def run_doctor(cls, bot: RaiMusicBot, guild: Optional[discord.Guild] = None) -> List[DiagnosticProbe]:
        """Perform comprehensive probes across all components."""
        probes: List[DiagnosticProbe] = []

        # 1. Discord Gateway probe
        t0 = time.perf_counter()
        gw_lat = round(bot.latency * 1000.0, 2)
        gw_status = "HEALTHY" if gw_lat < 250 else ("DEGRADED" if gw_lat < 600 else "FAILED")
        probes.append(DiagnosticProbe(
            name="Discord Gateway",
            status=gw_status,
            badge="🟢 READY" if gw_status == "HEALTHY" else ("🟡 SLOW" if gw_status == "DEGRADED" else "🔴 UNSTABLE"),
            latency_ms=gw_lat,
            details={"gateway_ms": gw_lat, "bot_user": str(bot.user), "bot_id": bot.user.id if bot.user else None},
        ))

        # 2. Database probe
        t0 = time.perf_counter()
        db_ok = False
        db_err = None
        if bot.db:
            try:
                hb = await bot.db.get_heartbeat(MUSIC_BOT_ID)
                db_ok = True
            except Exception as e:
                db_err = str(e)
        db_lat = round((time.perf_counter() - t0) * 1000.0, 2)
        probes.append(DiagnosticProbe(
            name="Music Database",
            status="HEALTHY" if db_ok else "FAILED",
            badge="🟢 CONNECTED" if db_ok else "🔴 FAILED",
            latency_ms=db_lat,
            details={"sqlite_file": "data/music.db"},
            error=db_err,
            fix="Check file permissions or re-initialize data/music.db." if not db_ok else None,
        ))

        # 3. Search & Extraction probe
        t0 = time.perf_counter()
        search_ok = False
        search_err = None
        sample_title = None
        try:
            results = await asyncio.wait_for(AudioResolver.search("lofi hip hop", limit=1), timeout=6.0)
            if results:
                search_ok = True
                sample_title = results[0]["title"][:30]
        except Exception as e:
            search_err = str(e)
        search_lat = round((time.perf_counter() - t0) * 1000.0, 2)
        probes.append(DiagnosticProbe(
            name="Search Provider",
            status="HEALTHY" if search_ok else "DEGRADED",
            badge="🟢 OPERATIONAL" if search_ok else "🟡 DEGRADED",
            latency_ms=search_lat,
            details={"engine": "yt-dlp", "probe_sample": sample_title},
            error=search_err,
            fix="Ensure yt-dlp is updated to the latest release." if not search_ok else None,
        ))

        # 4. Audio Stream Resolver probe
        t0 = time.perf_counter()
        res_ok = False
        res_err = None
        try:
            track = await asyncio.wait_for(
                AudioResolver.resolve_track("test audio", 0, "Doctor"), timeout=8.0
            )
            if track and track.stream_url:
                res_ok = True
        except Exception as e:
            res_err = str(e)
        res_lat = round((time.perf_counter() - t0) * 1000.0, 2)
        probes.append(DiagnosticProbe(
            name="Audio Stream Resolver",
            status="HEALTHY" if res_ok else "DEGRADED",
            badge="🟢 READY" if res_ok else "🟡 PROBE TIMEOUT",
            latency_ms=res_lat,
            details={"stream_available": res_ok},
            error=res_err,
            fix="YouTube extractor stream throttling or temporary IP block." if not res_ok else None,
        ))

        # 5. Session & Player State probe
        sm = SessionManager.get_instance()
        active = sm.get_active_sessions_count()
        playing = sm.get_playing_sessions_count()
        probes.append(DiagnosticProbe(
            name="Music Player & Sessions",
            status="HEALTHY",
            badge="🟢 READY",
            latency_ms=0.0,
            details={"active_sessions": active, "currently_playing": playing, "total_guild_sessions": len(sm.get_all_sessions())},
        ))

        # 6. Guild Permissions probe (if run in guild context)
        if guild:
            me = guild.me
            perms = me.guild_permissions
            has_voice = perms.connect and perms.speak
            has_text = perms.send_messages and perms.embed_links
            all_ok = has_voice and has_text
            probes.append(DiagnosticProbe(
                name="Discord Guild Permissions",
                status="HEALTHY" if all_ok else "DEGRADED",
                badge="🟢 VERIFIED" if all_ok else "🔴 MISSING PERMISSIONS",
                latency_ms=0.0,
                details={
                    "Connect": perms.connect,
                    "Speak": perms.speak,
                    "Send Messages": perms.send_messages,
                    "Embed Links": perms.embed_links,
                },
                fix="Grant Connect, Speak, Send Messages, and Embed Links permissions to Rai Music bot." if not all_ok else None,
            ))

        return probes
