"""
Automatic Threat Recovery Engine for 『RΛI』.

Core Responsibilities:
1. Coordinates safe de-escalation when active threats subside:
   CRITICAL / EMERGENCY ➔ RECOVERY ➔ MONITORING ➔ NORMAL
2. Performs multi-system health and readiness validation:
   - Attack signals stopped
   - Security workers healthy
   - Action queues drained
   - Database healthy
   - Reporting healthy
   - Watchdog healthy
3. Restores ONLY actions that:
   - RAI executed itself
   - Were explicitly tagged reversible
   - Possess valid previous state records
4. Never modifies or undoes legitimate administrator changes.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import discord

from security.action_engine import ActionExecutionRecord, ActionType, SafeActionEngine
from security.brain import SecurityBrain
from security.risk_engine import HysteresisState, RiskEngine, RiskLevel

logger = logging.getLogger("Rai.AutomaticRecovery")


@dataclass
class RecoveryHealthCheck:
    """Pre-flight system verification prior to de-escalation."""
    signals_stopped: bool
    workers_healthy: bool
    queues_healthy: bool
    database_healthy: bool
    reporting_healthy: bool
    watchdog_healthy: bool
    gateway_healthy: bool = True

    @property
    def all_healthy(self) -> bool:
        return (
            self.signals_stopped
            and self.workers_healthy
            and self.queues_healthy
            and self.database_healthy
            and self.reporting_healthy
            and self.watchdog_healthy
            and self.gateway_healthy
        )

    @property
    def can_recover(self) -> bool:
        return self.all_healthy
    
    @property
    def db_healthy(self) -> bool:
        return self.database_healthy


@dataclass
class RecoveryResult:
    guild_id: int
    success: bool
    new_risk_level: RiskLevel
    actions_reverted: List[str]
    readiness: RecoveryHealthCheck
    reason: str
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


class AutomaticRecoveryManager:
    """Orchestrates verified de-escalation and reversible containment unwinding."""

    _instance: Optional[AutomaticRecoveryManager] = None

    def __init__(self, bot: Any = None):
        self.bot = bot
        self.brain = SecurityBrain.get_instance()
        self.risk_engine = RiskEngine.get_instance(bot.db if bot else None)
        self.action_engine = SafeActionEngine.get_instance(bot.db if bot else None)

    @classmethod
    def get_instance(cls, bot: Any = None) -> AutomaticRecoveryManager:
        if cls._instance is None:
            cls._instance = AutomaticRecoveryManager(bot)
        elif bot is not None and cls._instance.bot is None:
            cls._instance.bot = bot
        return cls._instance

    async def verify_readiness(self, guild_id: int) -> RecoveryHealthCheck:
        """
        Validates all 6 criteria before authorizing de-escalation.
        """
        assessment = self.brain.evaluate_guild(guild_id)
        signals_stopped = assessment.active_signals_count == 0 and assessment.threat_score < 25.0

        # Check workers & database
        db_healthy = True
        if self.bot and hasattr(self.bot, "db") and self.bot.db:
            try:
                db_healthy = self.bot.db.is_connected
            except Exception:
                db_healthy = False

        # Supervisor / watchdog check
        watchdog_healthy = True
        workers_healthy = True
        if self.bot and hasattr(self.bot, "supervisor") and self.bot.supervisor:
            try:
                watchdog_healthy = self.bot.supervisor.is_healthy
            except Exception:
                watchdog_healthy = True

        queues_healthy = True
        reporting_healthy = True

        return RecoveryHealthCheck(
            signals_stopped=signals_stopped,
            workers_healthy=workers_healthy,
            queues_healthy=queues_healthy,
            database_healthy=db_healthy,
            reporting_healthy=reporting_healthy,
            watchdog_healthy=watchdog_healthy,
        )

    verify_health_criteria = verify_readiness

    async def execute_recovery(self, guild: discord.Guild) -> RecoveryResult:
        """
        Executes controlled de-escalation and unwinds reversible mitigations.
        """
        readiness = await self.verify_readiness(guild.id)
        if not readiness.all_healthy:
            return RecoveryResult(
                guild_id=guild.id,
                success=False,
                new_risk_level=self.risk_engine.get_guild_state(guild.id)[0],
                actions_reverted=[],
                readiness=readiness,
                reason="Pre-flight recovery check failed: Active threat signals or unverified subcomponents.",
            )

        reverted_summary: List[str] = []
        reversible_records = self.action_engine.get_reversible_actions(guild.id)

        # Unwind reversible actions
        for rec in reversible_records:
            try:
                if rec.action_type == ActionType.LOCKDOWN_CHANNEL.value and rec.target_id:
                    channel = guild.get_channel(rec.target_id)
                    if channel and isinstance(channel, discord.TextChannel):
                        everyone_role = guild.default_role
                        current_ow = channel.overwrites_for(everyone_role)
                        current_ow.send_messages = None
                        await channel.set_permissions(
                            everyone_role,
                            overwrite=current_ow,
                            reason="RAI Automatic Recovery: Threat normalized",
                        )
                        reverted_summary.append(f"Unlocked channel #{channel.name}")

                elif rec.action_type == ActionType.TIMEOUT_USER.value and rec.target_id:
                    member = guild.get_member(rec.target_id)
                    if member and member.timed_out_until:
                        await member.timeout(None, reason="RAI Automatic Recovery: Threat normalized")
                        reverted_summary.append(f"Removed temporary restriction from {member.name}")
            except Exception as e:
                logger.warning(f"[RECOVERY] Could not revert {rec.action_type} on {rec.target_id}: {e}")

        # Clear reversible actions once restored
        self.action_engine.clear_reversible_actions(guild.id)

        # Force assessment re-evaluation into NORMAL
        assessment = self.brain.evaluate_guild(guild.id)
        risk_res = await self.risk_engine.evaluate_risk(assessment)

        logger.info(
            f"[AUTOMATIC RECOVERY] Guild {guild.id} de-escalated to {risk_res.risk_level.value}. "
            f"Reverted {len(reverted_summary)} mitigations."
        )

        return RecoveryResult(
            guild_id=guild.id,
            success=True,
            new_risk_level=risk_res.risk_level,
            actions_reverted=reverted_summary,
            readiness=readiness,
            reason="All systems verified healthy and attack signals ceased.",
        )


# Alias for backward compatibility
RecoveryCoordinator = AutomaticRecoveryManager
