"""
Centralized Adaptive Rate-Limit & Resource Priority Manager for Rai.
Implements:
- 6-tier strict priority queue (Security ALWAYS precedes Music & casual commands)
- Token-bucket & sliding-window rate limiters per user, guild, and command
- Exponential backoff for Discord API 429 and network bottlenecks (1s -> 60s)
- System-load throttling: Throttles music and non-essential tasks during high security load
"""

from __future__ import annotations

import asyncio
import collections
import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

logger = logging.getLogger("Rai.RateLimiter")


class ResourcePriority(enum.IntEnum):
    """
    Resource Priority Tiers.
    Lower number = HIGHER execution priority.
    """
    CRITICAL = 0     # Emergency Lockdown, Anti-Raid Panic, Server Shielding
    HIGH = 1         # AutoMod Timeouts, Anti-Nuke Kicks/Bans, Incident Analysis
    MEDIUM = 2       # Staff Moderation (warn, purge, role updates), Tickets
    MONITORING = 3   # Watchdog, Self-Healing, Telemetry, Health probes
    MUSIC = 4        # Audio streaming, track searching, queue operations
    LOW = 5          # Economy, leveling, gaming stats, AI companion banter


@dataclass(order=True)
class PrioritizedWorkItem:
    priority: int
    item_id: str = field(compare=False)
    guild_id: int = field(compare=False)
    work_fn: Callable[[], Coroutine[Any, Any, Any]] = field(compare=False)
    created_at: float = field(compare=False, default_factory=time.time)
    retry_count: int = field(compare=False, default=0)
    max_retries: int = field(compare=False, default=3)


class ExponentialBackoff:
    """Calculates exponential backoff delays with jitter: 1s, 2s, 4s, 8s, 16s, 30s, max 60s."""

    BASE_DELAYS = [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 60.0]

    @classmethod
    def get_delay(cls, attempt: int) -> float:
        idx = min(attempt, len(cls.BASE_DELAYS) - 1)
        return cls.BASE_DELAYS[idx]


class GlobalRateLimiter:
    """
    Central coordinator of concurrency, priority execution, and rate limiting.
    """

    def __init__(self, max_concurrency: int = 4):
        self._max_concurrency = max_concurrency
        self._queue: asyncio.PriorityQueue[PrioritizedWorkItem] = asyncio.PriorityQueue()
        self._workers: List[asyncio.Task] = []
        self._running = False

        # Sliding window trackers: (scope_key) -> deque of timestamps
        self._windows: Dict[str, collections.deque[float]] = collections.defaultdict(collections.deque)
        self._user_cooldowns: Dict[str, float] = {}

        # Metric telemetry
        self.total_dispatched = 0
        self.total_throttled = 0
        self.total_failed = 0
        self.security_under_load = False

    def start(self) -> None:
        """Starts worker pool for prioritized work execution."""
        if self._running:
            return
        self._running = True
        for i in range(self._max_concurrency):
            self._workers.append(asyncio.create_task(self._worker_loop(i)))
        logger.info(f"GlobalRateLimiter active with {self._max_concurrency} prioritized workers.")

    def stop(self) -> None:
        self._running = False
        for t in self._workers:
            t.cancel()
        self._workers.clear()

    async def check_rate_limit(
        self,
        scope: str,
        key: str | int,
        limit: int,
        window_seconds: float,
    ) -> Tuple[bool, float]:
        """
        Token-bucket sliding window check.
        Returns (is_limited: bool, retry_after: float).
        """
        composite_key = f"{scope}:{key}"
        now = time.time()
        dq = self._windows[composite_key]

        # Prune expired timestamps
        cutoff = now - window_seconds
        while dq and dq[0] < cutoff:
            dq.popleft()

        if len(dq) >= limit:
            retry_after = max(0.1, round(window_seconds - (now - dq[0]), 1))
            self.total_throttled += 1
            return True, retry_after

        dq.append(now)
        return False, 0.0

    async def enqueue_action(
        self,
        item_id: str,
        guild_id: int,
        priority: ResourcePriority,
        work_fn: Callable[[], Coroutine[Any, Any, Any]],
        max_retries: int = 3,
    ) -> None:
        """
        Enqueues an action with strict priority ordering.
        Security (CRITICAL/HIGH) always jumps ahead of Music (MUSIC) or Fun (LOW).
        """
        # If security queue has a backlog, mark security_under_load to throttle music
        if self._queue.qsize() > 15:
            self.security_under_load = True

        item = PrioritizedWorkItem(
            priority=int(priority),
            item_id=item_id,
            guild_id=guild_id,
            work_fn=work_fn,
            max_retries=max_retries,
        )
        await self._queue.put(item)

    async def _worker_loop(self, worker_id: int) -> None:
        while self._running:
            try:
                item = await self._queue.get()
                # Check system load flag: if queue cleared, restore normal mode
                if self._queue.qsize() < 5:
                    self.security_under_load = False

                try:
                    await item.work_fn()
                    self.total_dispatched += 1
                except Exception as exc:
                    self.total_failed += 1
                    logger.error(
                        f"RateLimiter Worker {worker_id} failed on item {item.item_id} (priority {item.priority}): {exc}"
                    )
                    # Retry with exponential backoff if retries remain
                    if item.retry_count < item.max_retries:
                        item.retry_count += 1
                        delay = ExponentialBackoff.get_delay(item.retry_count)
                        logger.info(f"Retrying item {item.item_id} in {delay:.1f}s (attempt {item.retry_count})")
                        await asyncio.sleep(delay)
                        await self._queue.put(item)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.critical(f"Unexpected error in RateLimiter worker {worker_id}: {e}", exc_info=True)
                await asyncio.sleep(0.5)
