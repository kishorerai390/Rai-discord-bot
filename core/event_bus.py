"""
RAI — CENTRALIZED ASYNCHRONOUS EVENT BUS
Provides a high-throughput, decoupled pub/sub architecture for all Rai modules.

Guarantees:
1. Complete failure isolation: an exception in one subscriber never affects others.
2. Ordered subscriber execution via priority levels.
3. Event timeline recording for auditing and `/rai timeline`.
4. Asynchronous non-blocking dispatch with timeout guards.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

logger = logging.getLogger("Rai.EventBus")


class EventPriority(IntEnum):
    CRITICAL = 0
    HIGH = 10
    NORMAL = 20
    LOW = 30
    MONITOR = 40


@dataclass
class EventEnvelope:
    event_id: str
    event_name: str
    payload: Dict[str, Any]
    timestamp: float
    iso_time: str
    guild_id: Optional[int] = None
    user_id: Optional[int] = None
    source: str = "core"


SubscriberCallback = Callable[[EventEnvelope], Coroutine[Any, Any, None]]


@dataclass
class Subscription:
    id: str
    event_name: str
    callback: SubscriberCallback
    priority: EventPriority
    module_name: str
    predicate: Optional[Callable[[EventEnvelope], bool]] = None


class EventBus:
    """Central internal event bus orchestrating cross-module communication."""

    _instance: Optional[EventBus] = None

    def __init__(self, max_timeline_size: int = 200) -> None:
        self._subscribers: Dict[str, List[Subscription]] = {}
        self._wildcard_subscribers: List[Subscription] = []
        self._timeline: List[EventEnvelope] = []
        self._max_timeline_size = max_timeline_size
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> EventBus:
        if cls._instance is None:
            cls._instance = EventBus()
        return cls._instance

    def subscribe(
        self,
        event_name: str,
        callback: SubscriberCallback,
        priority: EventPriority = EventPriority.NORMAL,
        module_name: str = "unknown",
        predicate: Optional[Callable[[EventEnvelope], bool]] = None,
    ) -> str:
        """Subscribe to an event topic (supports '*' for wildcard)."""
        sub_id = str(uuid.uuid4())[:8]
        sub = Subscription(
            id=sub_id,
            event_name=event_name,
            callback=callback,
            priority=priority,
            module_name=module_name,
            predicate=predicate,
        )

        if event_name == "*":
            self._wildcard_subscribers.append(sub)
            self._wildcard_subscribers.sort(key=lambda s: s.priority)
        else:
            if event_name not in self._subscribers:
                self._subscribers[event_name] = []
            self._subscribers[event_name].append(sub)
            self._subscribers[event_name].sort(key=lambda s: s.priority)

        logger.debug(f"Subscribed {module_name} to '{event_name}' (ID: {sub_id})")
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        """Unsubscribe by subscription ID."""
        for name, subs in list(self._subscribers.items()):
            for s in subs:
                if s.id == sub_id:
                    subs.remove(s)
                    return True
        for s in self._wildcard_subscribers:
            if s.id == sub_id:
                self._wildcard_subscribers.remove(s)
                return True
        return False

    async def publish(
        self,
        event_name: str,
        payload: Optional[Dict[str, Any]] = None,
        guild_id: Optional[int] = None,
        user_id: Optional[int] = None,
        source: str = "core",
        timeout: float = 10.0,
    ) -> EventEnvelope:
        """
        Publish an event to all subscribers asynchronously.
        Catches errors per subscriber with strict failure isolation.
        """
        now = time.time()
        envelope = EventEnvelope(
            event_id=f"EVT-{str(uuid.uuid4())[:8].upper()}",
            event_name=event_name,
            payload=payload or {},
            timestamp=now,
            iso_time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            guild_id=guild_id,
            user_id=user_id,
            source=source,
        )

        # Record into timeline ring buffer
        self._timeline.append(envelope)
        if len(self._timeline) > self._max_timeline_size:
            self._timeline.pop(0)

        # Match subscribers
        matched: List[Subscription] = []
        if event_name in self._subscribers:
            matched.extend(self._subscribers[event_name])
        matched.extend(self._wildcard_subscribers)
        matched.sort(key=lambda s: s.priority)

        # Execute matched subscribers with isolation
        for sub in matched:
            if sub.predicate and not sub.predicate(envelope):
                continue

            try:
                # Wrap with timeout guard
                await asyncio.wait_for(sub.callback(envelope), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    f"Event subscriber '{sub.module_name}' timed out processing '{event_name}' ({envelope.event_id})"
                )
            except Exception as e:
                logger.error(
                    f"Error in event subscriber '{sub.module_name}' handling '{event_name}': {e}",
                    exc_info=True,
                )

        return envelope

    def get_timeline(
        self,
        limit: int = 50,
        guild_id: Optional[int] = None,
        event_name: Optional[str] = None,
    ) -> List[EventEnvelope]:
        """Query recent timeline events for diagnostic display."""
        events = list(self._timeline)
        if guild_id:
            events = [e for e in events if e.guild_id is None or e.guild_id == guild_id]
        if event_name:
            events = [e for e in events if e.event_name == event_name]
        return events[-limit:]

    def clear(self) -> None:
        """Clear all subscriptions and timeline (primarily for testing)."""
        self._subscribers.clear()
        self._wildcard_subscribers.clear()
        self._timeline.clear()
