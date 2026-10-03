"""
Adaptive Protection Manager for 『RΛI』.

Core Responsibilities:
1. Dynamically tunes detector thresholds, rate limits, and monitoring frequencies
   based on the real-time RiskLevel evaluated by the Risk Engine.
2. Coordinates proactive containment postures without executing unauthorized destructive changes.
3. Prioritizes security worker tasks when risk escalates to HIGH_ALERT, CRITICAL, or EMERGENCY.
4. Triggers automatic owner reporting and incident escalation when critical threat thresholds are breached.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from security.risk_engine import RiskEvaluationResult, RiskLevel

logger = logging.getLogger("Rai.AdaptiveProtection")


@dataclass(frozen=True)
class AdaptivePosture:
    """Operational security settings dynamically tailored to current risk level."""
    risk_level: RiskLevel
    join_window_multiplier: float  # Multiplier for join burst window sensitivity
    mention_threshold_reduction: int  # Number of mentions subtracted from threshold
    audit_poll_interval_seconds: float  # Audit log polling frequency
    security_priority_boost: bool  # Whether security queues get top CPU priority
    emergency_lockdown_enabled: bool  # Whether emergency channel lockdown is authorized
    owner_alert_required: bool  # Whether owner notification must be dispatched


DEFAULT_POSTURES: Dict[RiskLevel, AdaptivePosture] = {
    RiskLevel.NORMAL: AdaptivePosture(
        risk_level=RiskLevel.NORMAL,
        join_window_multiplier=1.0,
        mention_threshold_reduction=0,
        audit_poll_interval_seconds=10.0,
        security_priority_boost=False,
        emergency_lockdown_enabled=False,
        owner_alert_required=False,
    ),
    RiskLevel.ELEVATED: AdaptivePosture(
        risk_level=RiskLevel.ELEVATED,
        join_window_multiplier=1.2,
        mention_threshold_reduction=1,
        audit_poll_interval_seconds=6.0,
        security_priority_boost=False,
        emergency_lockdown_enabled=False,
        owner_alert_required=False,
    ),
    RiskLevel.HIGH_ALERT: AdaptivePosture(
        risk_level=RiskLevel.HIGH_ALERT,
        join_window_multiplier=1.5,
        mention_threshold_reduction=2,
        audit_poll_interval_seconds=3.0,
        security_priority_boost=True,
        emergency_lockdown_enabled=False,
        owner_alert_required=False,
    ),
    RiskLevel.CRITICAL: AdaptivePosture(
        risk_level=RiskLevel.CRITICAL,
        join_window_multiplier=2.0,
        mention_threshold_reduction=4,
        audit_poll_interval_seconds=1.5,
        security_priority_boost=True,
        emergency_lockdown_enabled=False,
        owner_alert_required=True,
    ),
    RiskLevel.EMERGENCY: AdaptivePosture(
        risk_level=RiskLevel.EMERGENCY,
        join_window_multiplier=3.0,
        mention_threshold_reduction=6,
        audit_poll_interval_seconds=1.0,
        security_priority_boost=True,
        emergency_lockdown_enabled=True,
        owner_alert_required=True,
    ),
}


class AdaptiveProtectionManager:
    """Coordinates risk-driven tuning of Rai security subcomponents."""

    _instance: Optional[AdaptiveProtectionManager] = None

    def __init__(self):
        self._guild_postures: Dict[int, AdaptivePosture] = {}

    @classmethod
    def get_instance(cls) -> AdaptiveProtectionManager:
        if cls._instance is None:
            cls._instance = AdaptiveProtectionManager()
        return cls._instance

    def get_posture(self, guild_id: int) -> AdaptivePosture:
        """Returns the active adaptive posture for a guild."""
        return self._guild_postures.get(guild_id, DEFAULT_POSTURES[RiskLevel.NORMAL])

    def get_posture_for_level(self, level: RiskLevel) -> AdaptivePosture:
        """Returns the preset posture specification for a given risk level."""
        return DEFAULT_POSTURES.get(level, DEFAULT_POSTURES[RiskLevel.NORMAL])

    def apply_evaluation(self, eval_res: RiskEvaluationResult) -> AdaptivePosture:
        """
        Updates the active posture based on an updated risk evaluation.
        Logs posture adaptations.
        """
        posture = DEFAULT_POSTURES.get(eval_res.risk_level, DEFAULT_POSTURES[RiskLevel.NORMAL])
        self._guild_postures[eval_res.guild_id] = posture

        if eval_res.escalated:
            logger.warning(
                f"[ADAPTIVE PROTECTION] Guild {eval_res.guild_id} escalated to {eval_res.risk_level.value}. "
                f"Tighter thresholds applied (Poll: {posture.audit_poll_interval_seconds}s, "
                f"Mention reduction: -{posture.mention_threshold_reduction})."
            )
        elif eval_res.deescalated:
            logger.info(
                f"[ADAPTIVE PROTECTION] Guild {eval_res.guild_id} de-escalated to {eval_res.risk_level.value}."
            )
        return posture
