"""
Deterministic Risk Engine and Threat Hysteresis Controller for 『RΛI』.

Core Responsibilities:
1. Translates continuous threat scores from the Security Brain into deterministic Risk Levels:
   - NORMAL (0-24)
   - ELEVATED (25-49)
   - HIGH_ALERT (50-74)
   - CRITICAL (75-89)
   - EMERGENCY (90-100)
2. Implements strict state hysteresis with cooldowns to prevent state flapping:
   CRITICAL / EMERGENCY ➔ RECOVERY (120s) ➔ MONITORING (60s) ➔ NORMAL
3. Manages unique security incident identifiers: RAI-INC-000001 lifecycle.
4. Persists real-time risk posture to SQLite database (security_risk_state).
5. Strict Priority: Deterministic rules govern transitions; AI is advisory only.
"""

from __future__ import annotations

import asyncio
import datetime
import enum
import logging
import random
import string
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from database.models import SecurityRiskState
from security.brain import CorrelatedThreatAssessment

logger = logging.getLogger("Rai.RiskEngine")


class RiskLevel(str, enum.Enum):
    """Deterministic security operational posture tiers."""
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH_ALERT = "HIGH_ALERT"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


class HysteresisState(str, enum.Enum):
    """De-escalation staging states preventing rapid state flapping."""
    NORMAL = "NORMAL"
    ACTIVE_THREAT = "ACTIVE_THREAT"
    RECOVERY = "RECOVERY"
    MONITORING = "MONITORING"


def generate_incident_id(prefix: str = "RAI-INC") -> str:
    """Generates standardized incident identifier: RAI-INC-XXXXXX."""
    num = "".join(random.choices(string.digits, k=6))
    return f"{prefix}-{num}"


@dataclass
class RiskEvaluationResult:
    """Evaluated risk decision with hysteresis tracking."""
    guild_id: int
    risk_level: RiskLevel
    previous_risk_level: RiskLevel
    hysteresis_state: HysteresisState
    threat_score: float
    escalated: bool
    deescalated: bool
    incident_id: Optional[str]
    cooldown_remaining_seconds: float
    reason: str
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


class GuildRiskContext:
    """Maintains active risk posture and hysteresis cooldowns for a single guild."""

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.current_risk_level: RiskLevel = RiskLevel.NORMAL
        self.hysteresis_state: HysteresisState = HysteresisState.NORMAL
        self.threat_score: float = 0.0
        self.last_escalation: float = 0.0
        self.last_deescalation: float = 0.0
        self.cooldown_until: float = 0.0
        self.active_incident_id: Optional[str] = None
        self.recovery_cooldown_seconds: float = 120.0
        self.monitoring_cooldown_seconds: float = 60.0


class RiskEngine:
    """Deterministic Threat Risk and Hysteresis Engine."""

    _instance: Optional[RiskEngine] = None

    def __init__(self, db: Any = None):
        self.db = db
        self._guilds: Dict[int, GuildRiskContext] = {}

    @classmethod
    def get_instance(cls, db: Any = None) -> RiskEngine:
        if cls._instance is None:
            cls._instance = RiskEngine(db)
        elif db is not None and cls._instance.db is None:
            cls._instance.db = db
        return cls._instance

    def _get_context(self, guild_id: int) -> GuildRiskContext:
        if guild_id not in self._guilds:
            self._guilds[guild_id] = GuildRiskContext(guild_id)
        return self._guilds[guild_id]

    def _score_to_level(self, score: float) -> RiskLevel:
        """Deterministic score mapping."""
        if score >= 90.0:
            return RiskLevel.EMERGENCY
        if score >= 75.0:
            return RiskLevel.CRITICAL
        if score >= 50.0:
            return RiskLevel.HIGH_ALERT
        if score >= 25.0:
            return RiskLevel.ELEVATED
        return RiskLevel.NORMAL

    def map_score_to_risk(self, score: float) -> RiskLevel:
        """Public score-to-level mapping entry point."""
        return self._score_to_level(score)

    @staticmethod
    def generate_incident_id(prefix: str = "RAI-INC") -> str:
        """Public standardized incident ID generator."""
        return generate_incident_id(prefix=prefix)

    async def evaluate_risk(
        self,
        assessment: CorrelatedThreatAssessment,
        now: Optional[float] = None,
    ) -> RiskEvaluationResult:
        """
        Evaluates real-time risk level based on threat score and enforces hysteresis rules.
        """
        current_time = now if now is not None else time.time()
        ctx = self._get_context(assessment.guild_id)
        prev_level = ctx.current_risk_level
        prev_hysteresis = ctx.hysteresis_state
        target_level = self._score_to_level(assessment.threat_score)
        ctx.threat_score = assessment.threat_score

        escalated = False
        deescalated = False
        reason = ""

        # Risk priority order mapping
        level_ranks = {
            RiskLevel.NORMAL: 0,
            RiskLevel.ELEVATED: 1,
            RiskLevel.HIGH_ALERT: 2,
            RiskLevel.CRITICAL: 3,
            RiskLevel.EMERGENCY: 4,
        }

        current_rank = level_ranks[prev_level]
        target_rank = level_ranks[target_level]

        # ==========================================
        # 1. ESCALATION (IMMEDIATE)
        # ==========================================
        if target_rank > current_rank:
            ctx.current_risk_level = target_level
            ctx.hysteresis_state = HysteresisState.ACTIVE_THREAT
            ctx.last_escalation = current_time
            ctx.cooldown_until = 0.0  # Reset cooldown upon new escalation
            escalated = True

            # If escalated to CRITICAL or EMERGENCY and no incident exists, create one
            if target_level in (RiskLevel.CRITICAL, RiskLevel.EMERGENCY) and not ctx.active_incident_id:
                ctx.active_incident_id = generate_incident_id()
                logger.warning(
                    f"[RISK ESCALATION] Guild {ctx.guild_id} escalated to {target_level.value}. Opened incident {ctx.active_incident_id}."
                )

            reason = f"Threat score increased to {assessment.threat_score:.1f} ({assessment.dominant_vector})"

        # ==========================================
        # 2. DE-ESCALATION (HYSTERESIS & COOLDOWNS)
        # ==========================================
        elif target_rank < current_rank:
            # Threat score has subsided, but hysteresis prevents immediate drop
            if prev_level in (RiskLevel.EMERGENCY, RiskLevel.CRITICAL):
                if ctx.hysteresis_state == HysteresisState.ACTIVE_THREAT:
                    # Move to RECOVERY state
                    ctx.hysteresis_state = HysteresisState.RECOVERY
                    ctx.cooldown_until = current_time + ctx.recovery_cooldown_seconds
                    ctx.last_deescalation = current_time
                    reason = f"Threat subsided. Entered RECOVERY mode for {int(ctx.recovery_cooldown_seconds)}s."
                elif ctx.hysteresis_state == HysteresisState.RECOVERY:
                    if current_time >= ctx.cooldown_until:
                        # Recovery completed, step down to HIGH_ALERT in MONITORING state
                        ctx.current_risk_level = RiskLevel.HIGH_ALERT
                        ctx.hysteresis_state = HysteresisState.MONITORING
                        ctx.cooldown_until = current_time + ctx.monitoring_cooldown_seconds
                        deescalated = True
                        reason = f"Recovery verified. Stepped down to HIGH_ALERT ({int(ctx.monitoring_cooldown_seconds)}s monitoring)."
                    else:
                        remaining = int(ctx.cooldown_until - current_time)
                        reason = f"Maintaining {prev_level.value} during RECOVERY cooldown ({remaining}s remaining)."
                elif ctx.hysteresis_state == HysteresisState.MONITORING:
                    if current_time >= ctx.cooldown_until:
                        # Monitoring completed, step down to target level
                        ctx.current_risk_level = target_level
                        ctx.hysteresis_state = HysteresisState.NORMAL
                        ctx.cooldown_until = 0.0
                        deescalated = True
                        # Close incident if fully subsided to NORMAL
                        if target_level == RiskLevel.NORMAL and ctx.active_incident_id:
                            logger.info(
                                f"[INCIDENT RESOLVED] Incident {ctx.active_incident_id} resolved as threat normalized."
                            )
                            ctx.active_incident_id = None
                        reason = f"Monitoring period cleared. Returned to {target_level.value}."
                    else:
                        remaining = int(ctx.cooldown_until - current_time)
                        reason = f"Maintaining HIGH_ALERT during MONITORING cooldown ({remaining}s remaining)."
            else:
                # Lower severity (ELEVATED / HIGH_ALERT) direct de-escalation with slight buffer
                ctx.current_risk_level = target_level
                ctx.hysteresis_state = HysteresisState.NORMAL
                deescalated = True
                reason = f"Threat normalized to {target_level.value}."

        else:
            reason = f"Threat steady at {ctx.current_risk_level.value}."

        cooldown_rem = max(0.0, ctx.cooldown_until - current_time)

        # 3. Asynchronously record state in SQLite
        if self.db and hasattr(self.db, "_db") and self.db._db:
            asyncio.create_task(self._persist_state(ctx))

        return RiskEvaluationResult(
            guild_id=ctx.guild_id,
            risk_level=ctx.current_risk_level,
            previous_risk_level=prev_level,
            hysteresis_state=ctx.hysteresis_state,
            threat_score=assessment.threat_score,
            escalated=escalated,
            deescalated=deescalated,
            incident_id=ctx.active_incident_id,
            cooldown_remaining_seconds=cooldown_rem,
            reason=reason,
        )

    async def _persist_state(self, ctx: GuildRiskContext) -> None:
        """Persists guild risk state to SQLite database."""
        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cd_iso = (
                datetime.datetime.fromtimestamp(ctx.cooldown_until, datetime.timezone.utc).isoformat()
                if ctx.cooldown_until > 0.0
                else None
            )
            is_emergency = 1 if ctx.current_risk_level == RiskLevel.EMERGENCY else 0

            await self.db._db.execute(
                """
                INSERT INTO security_risk_state (
                    guild_id, current_risk_level, threat_score, hysteresis_state,
                    last_escalation, last_deescalation, cooldown_until, active_incident_id,
                    emergency_mode, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    current_risk_level = excluded.current_risk_level,
                    threat_score = excluded.threat_score,
                    hysteresis_state = excluded.hysteresis_state,
                    last_escalation = excluded.last_escalation,
                    last_deescalation = excluded.last_deescalation,
                    cooldown_until = excluded.cooldown_until,
                    active_incident_id = excluded.active_incident_id,
                    emergency_mode = excluded.emergency_mode,
                    updated_at = excluded.updated_at
                """,
                (
                    ctx.guild_id,
                    ctx.current_risk_level.value,
                    ctx.threat_score,
                    ctx.hysteresis_state.value,
                    str(ctx.last_escalation) if ctx.last_escalation else None,
                    str(ctx.last_deescalation) if ctx.last_deescalation else None,
                    cd_iso,
                    ctx.active_incident_id,
                    is_emergency,
                    now_iso,
                ),
            )
            await self.db._db.commit()
        except Exception as e:
            logger.warning(f"[RISK_PERSIST] Could not persist risk state for guild {ctx.guild_id}: {e}")

    def get_guild_state(self, guild_id: int) -> Tuple[RiskLevel, HysteresisState, float, Optional[str]]:
        """Returns active risk level, hysteresis state, threat score, and active incident ID."""
        ctx = self._get_context(guild_id)
        return ctx.current_risk_level, ctx.hysteresis_state, ctx.threat_score, ctx.active_incident_id
