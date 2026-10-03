"""
Unified Security Signal Engine for 『RΛI』.

Core Responsibilities:
1. Provides a strongly typed, standardized security signal container across all detectors
   (Anti-Raid, Anti-Nuke, Anti-Spam, Mass Mention, AutoMod, Audit Logs, and Simulator).
2. Manages an asynchronous, bounded Security Signal Bus with memory and rate protection.
3. Implements deterministic signal deduplication to prevent event amplification.
4. Supports multi-subscriber routing (Security Brain, Threat Timeline, Local Persistence).
5. Guarantees failure isolation: subscriber errors or database outages NEVER crash detection.
"""

from __future__ import annotations

import asyncio
import datetime
import enum
import hashlib
import json
import logging
import random
import string
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("Rai.SecuritySignals")


class SignalSeverity(str, enum.Enum):
    """Categorical severity classification for security signals."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SignalSource(str, enum.Enum):
    """Component originating the security signal."""
    ANTI_RAID = "anti_raid"
    ANTI_NUKE = "anti_nuke"
    ANTI_SPAM = "anti_spam"
    MENTION_SPAM = "mention_spam"
    AUTOMOD = "automod"
    AUDIT_LOG = "audit_log"
    PERMISSION_MONITOR = "permission_monitor"
    MEMBER_MONITOR = "member_monitor"
    SIMULATOR = "simulator"
    MANUAL = "manual"


class SignalEventType(str, enum.Enum):
    """Standardized event taxonomy for threat intelligence."""
    # Raid & Join Activity
    JOIN_BURST = "join_burst"
    AVATARLESS_BURST = "avatarless_burst"
    SUSPICIOUS_ACCOUNT = "suspicious_account"
    SUSPICIOUS_MEMBER_ACTIVITY = "suspicious_member_activity"

    # Mentions & Message Spam
    MASS_MENTION = "mass_mention"
    REPEATED_MENTION_SPAM = "repeated_mention_spam"
    CROSS_CHANNEL_SPAM = "cross_channel_spam"
    MESSAGE_VELOCITY_SPIKE = "message_velocity_spike"
    SPAM_BURST = "spam_burst"

    # Administrative & Anti-Nuke
    MASS_CHANNEL_DELETE = "mass_channel_delete"
    MASS_CHANNEL_CREATE = "mass_channel_create"
    MASS_ROLE_DELETE = "mass_role_delete"
    MASS_ROLE_CREATE = "mass_role_create"
    MASS_BAN = "mass_ban"
    MASS_KICK = "mass_kick"
    DANGEROUS_PERMISSION_CHANGE = "dangerous_permission_change"
    WEBHOOK_ABUSE = "webhook_abuse"
    UNAUTHORIZED_BOT_INVITE = "unauthorized_bot_invite"

    # System & Audit
    AUDIT_LOG_ALERT = "audit_log_alert"
    LOCKDOWN_TRIGGERED = "lockdown_triggered"
    SECURITY_BREACH = "security_breach"
    SIMULATED_ATTACK = "simulated_attack"


def generate_signal_id(prefix: str = "SIG") -> str:
    """Generates unique, timestamped signal identifier (e.g. SIG-20261001-A9F21)."""
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    rand_chars = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"{prefix}-{ts}-{rand_chars}"


@dataclass(frozen=True)
class SecuritySignal:
    """
    Unified typed security signal representation across 『RΛI』.
    Represents an atomic, normalized detection event.
    """
    guild_id: int
    event_type: str
    source: str
    severity: str
    confidence: float = 1.0  # 0.0 to 1.0
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    signal_id: str = field(default_factory=generate_signal_id)
    actor_id: Optional[int] = None
    actor_name: Optional[str] = None
    channel_id: Optional[int] = None
    channel_name: Optional[str] = None
    target_id: Optional[int] = None
    target_name: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    incident_id: Optional[str] = None
    dedup_key: Optional[str] = None

    def get_dedup_key(self) -> str:
        """Returns or computes a deterministic deduplication fingerprint."""
        if self.dedup_key:
            return self.dedup_key
        raw = f"{self.guild_id}:{self.event_type}:{self.source}:{self.actor_id or 0}:{self.channel_id or 0}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    def to_dict(self) -> Dict[str, Any]:
        """Converts signal to dictionary for serialization."""
        return {
            "signal_id": self.signal_id,
            "guild_id": self.guild_id,
            "event_type": self.event_type,
            "source": self.source,
            "severity": self.severity,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "evidence": self.evidence,
            "incident_id": self.incident_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SecuritySignal:
        """Restores a SecuritySignal from a serialized dictionary."""
        return cls(
            guild_id=data["guild_id"],
            event_type=data["event_type"],
            source=data["source"],
            severity=data["severity"],
            confidence=data.get("confidence", 1.0),
            timestamp=data.get("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat()),
            signal_id=data.get("signal_id", generate_signal_id()),
            actor_id=data.get("actor_id"),
            actor_name=data.get("actor_name"),
            channel_id=data.get("channel_id"),
            channel_name=data.get("channel_name"),
            target_id=data.get("target_id"),
            target_name=data.get("target_name"),
            evidence=data.get("evidence", {}),
            incident_id=data.get("incident_id"),
            dedup_key=data.get("dedup_key"),
        )


SubscriberFunc = Callable[[SecuritySignal], Coroutine[Any, Any, None]]


class SecuritySignalBus:
    """
    Central Asynchronous Signal Bus for 『RΛI』.
    Features:
    - Bounded internal queue (5000 items max) with backpressure protection.
    - In-memory sliding window deduplication cache with TTL.
    - Zero publisher blocking: publish() completes in microseconds.
    - Error isolation: failing subscribers never crash publishers or other subscribers.
    """

    _instance: Optional[SecuritySignalBus] = None

    def __init__(self, db: Any = None, max_queue_size: int = 5000):
        self.db = db
        self.max_queue_size = max_queue_size
        self._queue: asyncio.Queue[SecuritySignal] = asyncio.Queue(maxsize=max_queue_size)
        self._subscribers: List[Tuple[Optional[str], SubscriberFunc]] = []
        # dedup_key -> expiry_timestamp
        self._dedup_cache: Dict[str, float] = {}
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._metrics = {
            "signals_published": 0,
            "signals_processed": 0,
            "signals_dropped": 0,
            "signals_deduplicated": 0,
        }

    @classmethod
    def get_instance(cls, db: Any = None, max_queue_size: int = 5000) -> SecuritySignalBus:
        if cls._instance is None:
            cls._instance = SecuritySignalBus(db, max_queue_size=max_queue_size)
        elif db is not None and cls._instance.db is None:
            cls._instance.db = db
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Cleans up the singleton instance for testing or restart."""
        if cls._instance and cls._instance._worker_task:
            cls._instance._worker_task.cancel()
        cls._instance = None

    def start(self) -> None:
        """Starts the background signal distribution worker."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._process_queue())
        logger.info("SecuritySignalBus worker started.")

    def stop(self) -> None:
        """Stops the background worker cleanly."""
        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            self._worker_task = None
        logger.info("SecuritySignalBus worker stopped.")

    def subscribe(
        self,
        handler: SubscriberFunc,
        event_type: Optional[str] = None,
    ) -> None:
        """Subscribes an async handler to all or filtered signal event types."""
        self._subscribers.append((event_type, handler))

    def unsubscribe(self, handler: SubscriberFunc) -> None:
        """Removes a registered subscriber handler."""
        self._subscribers = [s for s in self._subscribers if s[1] != handler]

    def _is_duplicate(self, dedup_key: str, now: float, ttl_seconds: float = 10.0) -> bool:
        """Prunes expired keys and checks if dedup_key is currently active."""
        # Periodic prune if cache exceeds 1000 items
        if len(self._dedup_cache) > 1000:
            self._dedup_cache = {k: exp for k, exp in self._dedup_cache.items() if exp > now}

        if dedup_key in self._dedup_cache:
            if self._dedup_cache[dedup_key] > now:
                return True

        self._dedup_cache[dedup_key] = now + ttl_seconds
        return False

    def publish(
        self,
        signal: SecuritySignal,
        dedup_ttl_seconds: float = 5.0,
    ) -> bool:
        """
        Publishes a security signal into the bus without blocking.
        Returns True if accepted, False if dropped or deduplicated.
        """
        now = time.time()
        dedup_key = signal.get_dedup_key()

        if dedup_ttl_seconds > 0.0 and self._is_duplicate(dedup_key, now, dedup_ttl_seconds):
            self._metrics["signals_deduplicated"] += 1
            logger.debug(f"[SIGNAL_DEDUP] Dropped duplicate signal {signal.signal_id} ({dedup_key})")
            return False

        try:
            self._queue.put_nowait(signal)
            self._metrics["signals_published"] += 1
            return True
        except asyncio.QueueFull:
            self._metrics["signals_dropped"] += 1
            logger.critical(
                f"[SECURITY BACKPRESSURE] Signal bus queue full ({self.max_queue_size})! Dropping signal {signal.signal_id}"
            )
            return False

    async def _process_queue(self) -> None:
        """Main asynchronous processing loop delivering signals to subscribers."""
        while self._running:
            try:
                signal = await self._queue.get()
                self._metrics["signals_processed"] += 1

                # 1. Dispatch to all matching subscribers
                handlers = [
                    handler
                    for (filt, handler) in self._subscribers
                    if filt is None or filt == signal.event_type
                ]

                if handlers:
                    # Execute subscribers concurrently with error isolation
                    tasks = [asyncio.create_task(self._safe_dispatch(h, signal)) for h in handlers]
                    await asyncio.gather(*tasks, return_exceptions=True)

                # 2. Persist signal to SQLite if database is configured
                if self.db and hasattr(self.db, "_db") and self.db._db:
                    asyncio.create_task(self._persist_signal_async(signal))

                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SIGNAL_BUS] Unexpected processing error: {e}", exc_info=True)
                await asyncio.sleep(0.1)

    async def _safe_dispatch(self, handler: SubscriberFunc, signal: SecuritySignal) -> None:
        """Invokes a subscriber handler while trapping all exceptions."""
        try:
            await handler(signal)
        except Exception as e:
            logger.error(
                f"[SIGNAL_BUS] Subscriber error in {getattr(handler, '__name__', str(handler))}: {e}",
                exc_info=True,
            )

    async def _persist_signal_async(self, signal: SecuritySignal) -> None:
        """Persists signal into SQLite database asynchronously."""
        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            evidence_json = json.dumps(signal.evidence)
            await self.db._db.execute(
                """
                INSERT OR IGNORE INTO security_intelligence_signals (
                    signal_id, guild_id, event_type, source, severity, confidence,
                    timestamp, actor_id, actor_name, channel_id, channel_name,
                    target_id, target_name, evidence, incident_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_id,
                    signal.guild_id,
                    signal.event_type,
                    signal.source,
                    signal.severity,
                    signal.confidence,
                    signal.timestamp,
                    signal.actor_id,
                    signal.actor_name,
                    signal.channel_id,
                    signal.channel_name,
                    signal.target_id,
                    signal.target_name,
                    evidence_json,
                    signal.incident_id,
                    now_iso,
                ),
            )
            await self.db._db.commit()
        except Exception as e:
            # Database failure must NEVER impact signal delivery
            logger.warning(f"[SIGNAL_PERSIST] Could not persist signal {signal.signal_id}: {e}")

    def get_metrics(self) -> Dict[str, Any]:
        """Returns health and throughput telemetry for observability."""
        return {
            **self._metrics,
            "queue_depth": self._queue.qsize(),
            "active_subscribers": len(self._subscribers),
            "dedup_cache_size": len(self._dedup_cache),
        }
