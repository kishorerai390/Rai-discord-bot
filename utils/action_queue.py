"""
Global Action Queue and Rate-Limit Manager for Rai Bot.
Centralizes all automated Discord API interventions (timeouts, kicks, channel locks, role updates),
enforces priority execution, and prevents duplicate actions within a deduplication window.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Dict, Optional
import discord

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger("RaiActionQueue")


@dataclass(order=True)
class QueuedAction:
    priority: int  # Lower integer = higher priority (0: Critical, 1: High, 2: Medium, 3: Low)
    action_id: str = field(compare=False)
    guild_id: int = field(compare=False)
    target_id: Optional[int] = field(compare=False)
    action_type: str = field(compare=False)  # TIMEOUT, KICK, BAN, LOCK_CHANNEL, DELETE_MESSAGE
    coroutine_func: Callable[[], Coroutine[Any, Any, Any]] = field(compare=False)
    dedup_key: Optional[str] = field(compare=False, default=None)
    created_at: float = field(compare=False, default_factory=time.time)


class GlobalActionQueue:
    """Centralized rate-limited priority action queue for automated Discord interventions."""

    PRIORITY_CRITICAL = 0
    PRIORITY_HIGH = 1
    PRIORITY_MEDIUM = 2
    PRIORITY_LOW = 3

    def __init__(self, bot: SentinelBot, max_concurrency: int = 2):
        self.bot = bot
        self._queue: asyncio.PriorityQueue[QueuedAction] = asyncio.PriorityQueue()
        self._dedup_cache: Dict[str, float] = {}  # dedup_key -> expiry timestamp
        self._dedup_window_seconds: float = 12.0
        self._workers: list[asyncio.Task] = []
        self._max_concurrency = max_concurrency
        self._running = False
        self._actions_dispatched = 0
        self._actions_deduplicated = 0
        self._actions_failed = 0

    def start(self) -> None:
        """Starts the action queue consumer workers."""
        if self._running:
            return
        self._running = True
        for i in range(self._max_concurrency):
            worker_task = asyncio.create_task(self._consumer_worker(worker_id=i))
            self._workers.append(worker_task)
        logger.info(f"GlobalActionQueue started with {self._max_concurrency} workers.")

    def stop(self) -> None:
        """Cancels all action queue consumer workers."""
        self._running = False
        for task in self._workers:
            if not task.done():
                task.cancel()
        self._workers.clear()

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def enqueue(
        self,
        guild_id: int,
        action_type: str,
        coroutine_func: Callable[[], Coroutine[Any, Any, Any]],
        target_id: Optional[int] = None,
        priority: int = PRIORITY_MEDIUM,
        custom_dedup_key: Optional[str] = None,
    ) -> Optional[str]:
        """
        Enqueues an automated action. Deduplicates identical actions within the deduplication window.
        Returns the action_id if enqueued, or None if suppressed by deduplication.
        """
        now = time.time()
        # Clean expired dedup entries
        self._dedup_cache = {k: v for k, v in self._dedup_cache.items() if v > now}

        dedup_key = custom_dedup_key or f"{guild_id}:{target_id or 'none'}:{action_type}"
        if dedup_key in self._dedup_cache:
            self._actions_deduplicated += 1
            logger.debug(f"Action '{action_type}' for target {target_id} in {guild_id} suppressed by deduplication.")
            return None

        self._dedup_cache[dedup_key] = now + self._dedup_window_seconds
        action_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"

        queued = QueuedAction(
            priority=priority,
            action_id=action_id,
            guild_id=guild_id,
            target_id=target_id,
            action_type=action_type,
            coroutine_func=coroutine_func,
            dedup_key=dedup_key,
        )

        self._queue.put_nowait(queued)
        return action_id

    async def _consumer_worker(self, worker_id: int) -> None:
        """Worker that pulls and executes actions with rate-limit and backoff handling."""
        while self._running:
            try:
                item = await self._queue.get()
                action_id = item.action_id
                retries = 0
                max_retries = 3
                success = False

                while retries < max_retries:
                    try:
                        await item.coroutine_func()
                        success = True
                        self._actions_dispatched += 1
                        logger.info(
                            f"[ActionQueue] Worker {worker_id} executed {item.action_type} "
                            f"(ID: {action_id}, target: {item.target_id})"
                        )
                        break
                    except discord.RateLimited as rle:
                        retry_after = getattr(rle, "retry_after", 2.0)
                        logger.warning(f"[ActionQueue] Rate limited on {item.action_type}, backing off {retry_after}s")
                        await asyncio.sleep(retry_after)
                        retries += 1
                    except discord.HTTPException as he:
                        if he.status == 429:
                            retry_after = float(he.response.headers.get("Retry-After", 2.0))
                            await asyncio.sleep(retry_after)
                            retries += 1
                        else:
                            logger.error(f"[ActionQueue] HTTP failure executing {item.action_type}: {he}")
                            break
                    except Exception as e:
                        logger.error(f"[ActionQueue] Unexpected error executing {item.action_type}: {e}")
                        break

                if not success:
                    self._actions_failed += 1

                # Audit log in database
                if hasattr(self.bot, "db") and self.bot.db.is_connected:
                    status = "SUCCESS" if success else "FAILED"
                    p_name = {0: "CRITICAL", 1: "HIGH", 2: "MEDIUM", 3: "LOW"}.get(item.priority, "MEDIUM")
                    await self.bot.db.log_action_queue_audit(
                        action_id=action_id,
                        guild_id=item.guild_id,
                        target_id=item.target_id,
                        action_type=item.action_type,
                        priority=p_name,
                        dedup_key=item.dedup_key,
                        status=status,
                    )

                self._queue.task_done()
                # Inter-action pacing to guarantee Discord API rate-limit friendliness
                await asyncio.sleep(0.35)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Fatal error in ActionQueue worker {worker_id}: {e}")
                await asyncio.sleep(1.0)

    def get_status(self) -> Dict[str, Any]:
        """Returns action queue telemetry."""
        return {
            "queue_size": self.queue_size,
            "dispatched": self._actions_dispatched,
            "deduplicated": self._actions_deduplicated,
            "failed": self._actions_failed,
            "active_workers": len([w for w in self._workers if not w.done()]),
        }
