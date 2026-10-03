"""
Security Brain for 『RΛI』.

Core Responsibilities:
1. Aggregates and correlates multi-vector security signals across sliding time windows (60s, 300s, 900s).
2. Detects coordinated attacks (e.g. Join Burst + Mass Mention Spam + Cross-Channel Activity).
3. Evaluates multi-channel attack trajectories and distributed bad actors.
4. Produces deterministic threat assessments with confidence weighting without double-counting.
5. Feeds correlated assessments directly into the Risk Engine.
"""

from __future__ import annotations

import collections
import datetime
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from security.signals import SecuritySignal, SignalEventType, SignalSeverity, SignalSource

logger = logging.getLogger("Rai.SecurityBrain")

SEVERITY_WEIGHTS: Dict[str, float] = {
    SignalSeverity.CRITICAL.value: 28.0,
    SignalSeverity.HIGH.value: 16.0,
    SignalSeverity.MEDIUM.value: 8.0,
    SignalSeverity.LOW.value: 3.0,
}


@dataclass
class CorrelatedThreatAssessment:
    """Consolidated threat intelligence evaluation produced by the Security Brain."""
    guild_id: int
    threat_score: float  # Normalized 0.0 to 100.0
    dominant_vector: str
    active_signals_count: int
    unique_actors: List[int]
    channels_affected: List[int]
    patterns_detected: List[str]
    confidence: float
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "guild_id": self.guild_id,
            "threat_score": round(self.threat_score, 1),
            "dominant_vector": self.dominant_vector,
            "active_signals_count": self.active_signals_count,
            "unique_actors_count": len(self.unique_actors),
            "channels_affected_count": len(self.channels_affected),
            "patterns_detected": self.patterns_detected,
            "confidence": round(self.confidence, 2),
            "timestamp": self.timestamp,
        }

    @property
    def signal_count(self) -> int:
        return self.active_signals_count

    @property
    def compound_patterns(self) -> List[str]:
        return self.patterns_detected

    @property
    def involved_actors(self) -> List[int]:
        return self.unique_actors

    @property
    def primary_attack_vector(self) -> str:
        return self.dominant_vector


class GuildSecurityContext:
    """Sliding-window signal accumulator and trajectory tracker for a single guild."""

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        # (timestamp, SecuritySignal)
        self.signals: collections.deque[Tuple[float, SecuritySignal]] = collections.deque()
        self.actor_frequency: collections.defaultdict[int, int] = collections.defaultdict(int)
        self.channel_frequency: collections.defaultdict[int, int] = collections.defaultdict(int)
        self.last_assessment: Optional[CorrelatedThreatAssessment] = None

    def add_signal(self, signal: SecuritySignal, now: float) -> None:
        signal_time = now
        if signal.timestamp:
            try:
                dt = datetime.datetime.fromisoformat(signal.timestamp.replace("Z", "+00:00"))
                signal_time = dt.timestamp()
            except Exception:
                signal_time = now
        self.signals.append((signal_time, signal))
        if signal.actor_id:
            self.actor_frequency[signal.actor_id] += 1
        if signal.channel_id:
            self.channel_frequency[signal.channel_id] += 1
        self.prune(now - 900.0)  # Retain up to 15 minutes of context

    def prune(self, cutoff: float) -> None:
        while self.signals and self.signals[0][0] < cutoff:
            _, old_sig = self.signals.popleft()
            if old_sig.actor_id and old_sig.actor_id in self.actor_frequency:
                self.actor_frequency[old_sig.actor_id] = max(
                    0, self.actor_frequency[old_sig.actor_id] - 1
                )
            if old_sig.channel_id and old_sig.channel_id in self.channel_frequency:
                self.channel_frequency[old_sig.channel_id] = max(
                    0, self.channel_frequency[old_sig.channel_id] - 1
                )


class SecurityBrain:
    """Central Intelligence & Multi-Signal Correlation Engine."""

    _instance: Optional[SecurityBrain] = None

    def __init__(self, window_seconds: float = 300.0):
        self.window_seconds = window_seconds
        self._guild_contexts: Dict[int, GuildSecurityContext] = {}

    @classmethod
    def get_instance(cls, window_seconds: float = 300.0) -> SecurityBrain:
        if cls._instance is None:
            cls._instance = SecurityBrain(window_seconds=window_seconds)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def _get_context(self, guild_id: int) -> GuildSecurityContext:
        if guild_id not in self._guild_contexts:
            self._guild_contexts[guild_id] = GuildSecurityContext(guild_id)
        return self._guild_contexts[guild_id]

    async def ingest_signal(self, signal: SecuritySignal) -> CorrelatedThreatAssessment:
        """
        Ingests an incoming security signal, prunes stale history,
        and computes a real-time correlated threat assessment.
        """
        now = time.time()
        ctx = self._get_context(signal.guild_id)
        ctx.add_signal(signal, now)
        assessment = self.evaluate_guild(signal.guild_id, now)
        ctx.last_assessment = assessment
        return assessment

    def evaluate_guild(self, guild_id: int, now: Optional[float] = None) -> CorrelatedThreatAssessment:
        """
        Evaluates active signals within 60s and 300s windows, detects compound attack patterns,
        and calculates normalized threat scores (0-100).
        """
        current_time = now if now is not None else time.time()
        ctx = self._get_context(guild_id)
        ctx.prune(current_time - self.window_seconds)

        # Separate immediate window and broader trend window
        short_window = min(60.0, self.window_seconds)
        recent_60s = [sig for (t, sig) in ctx.signals if t >= (current_time - short_window)]
        recent_300s = [sig for (t, sig) in ctx.signals if t >= (current_time - self.window_seconds)]

        if not recent_300s:
            return CorrelatedThreatAssessment(
                guild_id=guild_id,
                threat_score=0.0,
                dominant_vector="NONE",
                active_signals_count=0,
                unique_actors=[],
                channels_affected=[],
                patterns_detected=[],
                confidence=1.0,
            )

        raw_score = 0.0
        confidence_sum = 0.0
        patterns_detected: List[str] = []
        actors_set: Set[int] = set()
        channels_set: Set[int] = set()
        vector_counts: collections.defaultdict[str, int] = collections.defaultdict(int)

        # 1. Base Weighted Score from Signals in the last 60s (primary) & 300s (secondary)
        for sig in recent_60s:
            weight = SEVERITY_WEIGHTS.get(sig.severity, 4.0)
            raw_score += weight * sig.confidence
            confidence_sum += sig.confidence
            vector_counts[sig.event_type] += 1
            if sig.actor_id:
                actors_set.add(sig.actor_id)
            if sig.channel_id:
                channels_set.add(sig.channel_id)

        # Add decay-weighted older signals from 60s-300s
        for sig in recent_300s:
            if sig not in recent_60s:
                weight = SEVERITY_WEIGHTS.get(sig.severity, 4.0) * 0.4
                raw_score += weight * sig.confidence
                confidence_sum += sig.confidence * 0.4
                if sig.actor_id:
                    actors_set.add(sig.actor_id)
                if sig.channel_id:
                    channels_set.add(sig.channel_id)

        # 2. Compound Attack Pattern Detection
        event_types = {sig.event_type for sig in recent_60s}

        # Pattern A: Coordinated Raid Attack (Join Burst + Mention Spam)
        has_joins = any(
            t in event_types
            for t in (SignalEventType.JOIN_BURST.value, SignalEventType.AVATARLESS_BURST.value)
        )
        has_mentions = any(
            t in event_types
            for t in (SignalEventType.MASS_MENTION.value, SignalEventType.REPEATED_MENTION_SPAM.value)
        )
        if has_joins and has_mentions:
            patterns_detected.append("COORDINATED_RAID_SPAM")
            raw_score += 35.0  # Compound threat amplifier

        # Pattern B: Rogue Administrator / Anti-Nuke Multi-Destruction
        destructive_ops = sum(
            1
            for sig in recent_60s
            if sig.event_type
            in (
                SignalEventType.MASS_CHANNEL_DELETE.value,
                SignalEventType.MASS_ROLE_DELETE.value,
                SignalEventType.MASS_BAN.value,
                SignalEventType.MASS_KICK.value,
                SignalEventType.DANGEROUS_PERMISSION_CHANGE.value,
            )
        )
        if destructive_ops >= 2:
            patterns_detected.append("INSIDER_NUKE_VELOCITY")
            raw_score += 45.0

        # Pattern C: Cross-Channel Trajectory (attack traversing multiple channels)
        if len(channels_set) >= 3:
            patterns_detected.append(f"CROSS_CHANNEL_ATTACK ({len(channels_set)} channels)")
            raw_score += min(20.0, len(channels_set) * 5.0)

        # Pattern D: Distributed Bad Actors (coordinated swarm)
        if len(actors_set) >= 3 and (has_mentions or has_joins):
            patterns_detected.append(f"DISTRIBUTED_BOTNET ({len(actors_set)} actors)")
            raw_score += min(25.0, len(actors_set) * 6.0)

        # Determine dominant vector
        dominant = max(vector_counts.items(), key=lambda x: x[1])[0] if vector_counts else "GENERAL_THREAT"

        # Calculate normalized score (0.0 - 100.0)
        threat_score = max(0.0, min(100.0, raw_score))
        avg_confidence = (confidence_sum / len(recent_300s)) if recent_300s else 1.0

        return CorrelatedThreatAssessment(
            guild_id=guild_id,
            threat_score=threat_score,
            dominant_vector=dominant,
            active_signals_count=len(recent_60s),
            unique_actors=list(actors_set),
            channels_affected=list(channels_set),
            patterns_detected=patterns_detected,
            confidence=min(1.0, max(0.2, avg_confidence)),
        )

    def clear_guild(self, guild_id: int) -> None:
        """Resets intelligence tracking for a guild upon recovery."""
        if guild_id in self._guild_contexts:
            del self._guild_contexts[guild_id]
