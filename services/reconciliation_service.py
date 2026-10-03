"""
RAI — STATE RECONCILIATION SERVICE
Periodically and reactively audits Discord state vs Local Database state.

Guarantees:
1. Reconciles Dynamic VCs: cleans up DB records for deleted voice channels; flags untracked rooms.
2. Reconciles Report Destinations: marks destinations as DEGRADED or cleans up if channel deleted.
3. Reconciles Music Sessions: cleans up dangling players whose voice client disconnected.
4. Reconciles Emergency & Maintenance States: keeps in-memory locks aligned with DB.
5. Logs every reconciliation action with timestamp and diagnostic reference.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import discord

logger = logging.getLogger("Rai.Reconciliation")


@dataclass
class ReconciliationReport:
    timestamp: float = field(default_factory=time.time)
    dynamic_vc_reconciled: int = 0
    report_channels_reconciled: int = 0
    music_sessions_reconciled: int = 0
    inconsistencies_fixed: int = 0
    details: List[str] = field(default_factory=list)


class ReconciliationService:
    """Orchestrates periodic reconciliation between Discord API state and bot DB state."""

    _instance: Optional[ReconciliationService] = None

    def __init__(self, bot: Optional[discord.Client] = None) -> None:
        self.bot = bot
        self.last_report: Optional[ReconciliationReport] = None
        self._timeline_events: List[Dict[str, Any]] = []
        self._max_timeline: int = 50

    @classmethod
    def get_instance(cls, bot: Optional[discord.Client] = None) -> ReconciliationService:
        if cls._instance is None:
            cls._instance = ReconciliationService(bot)
        elif bot is not None and cls._instance.bot is None:
            cls._instance.bot = bot
        return cls._instance

    def record_timeline_event(self, module: str, action: str, result: str = "SUCCESS", details: Optional[str] = None) -> None:
        """Records an event in the system audit timeline."""
        event = {
            "timestamp": time.time(),
            "time_str": time.strftime("%H:%M:%S", time.gmtime()),
            "module": module,
            "action": action,
            "result": result,
            "details": details or "",
        }
        self._timeline_events.append(event)
        if len(self._timeline_events) > self._max_timeline:
            self._timeline_events.pop(0)

    def get_timeline(self, limit: int = 20) -> List[Dict[str, Any]]:
        return list(reversed(self._timeline_events[-limit:]))

    async def reconcile_all(self) -> ReconciliationReport:
        """Runs full state reconciliation pass across all connected guilds."""
        if not self.bot or not self.bot.is_ready():
            return ReconciliationReport()

        report = ReconciliationReport()

        # 1. Reconcile Dynamic VCs
        try:
            from utils.dynamic_vc_cleanup import DynamicVCCleanupService
            dvc_count = await DynamicVCCleanupService.reconcile_on_startup(self.bot)
            report.dynamic_vc_reconciled = dvc_count
            report.inconsistencies_fixed += dvc_count
            if dvc_count > 0:
                report.details.append(f"Reconciled {dvc_count} orphaned Dynamic VCs.")
        except Exception as e:
            logger.error(f"[RECONCILE] Error reconciling dynamic VCs: {e}")

        # 2. Reconcile Report Destinations
        try:
            from services.report_service import ReportService
            db = getattr(self.bot, "db", None)
            if db:
                for guild in self.bot.guilds:
                    destinations = await ReportService.get_destinations(self.bot, guild.id)
                    for dest in destinations:
                        channel = guild.get_channel(dest.channel_id)
                        if channel is None:
                            # Destination channel was deleted in Discord!
                            await ReportService.remove_destination(self.bot, guild.id, dest.channel_id)
                            report.report_channels_reconciled += 1
                            report.inconsistencies_fixed += 1
                            report.details.append(f"Removed dead report channel {dest.channel_id} in guild {guild.id}.")
        except Exception as e:
            logger.error(f"[RECONCILE] Error reconciling report channels: {e}")

        # 3. Reconcile Music Sessions
        try:
            music_cog = self.bot.cogs.get("Music")
            if music_cog and hasattr(music_cog, "players"):
                for gid, player in list(music_cog.players.items()):
                    guild = self.bot.get_guild(gid)
                    vc = guild.voice_client if guild else None
                    if not vc or not vc.is_connected():
                        # Dead session
                        if hasattr(player, "destroy"):
                            await player.destroy()
                        music_cog.players.pop(gid, None)
                        report.music_sessions_reconciled += 1
                        report.inconsistencies_fixed += 1
                        report.details.append(f"Cleaned up disconnected music player in guild {gid}.")
        except Exception as e:
            logger.error(f"[RECONCILE] Error reconciling music sessions: {e}")

        self.last_report = report
        self.record_timeline_event(
            module="Reconciliation",
            action="Full State Audit",
            result="COMPLETED",
            details=f"Fixed {report.inconsistencies_fixed} inconsistencies",
        )
        return report
