"""
RAI — DISCORD API RELIABILITY LAYER / DISCORD API SERVICE
Centralized reliability wrapper for all Discord API interactions.

Guarantees:
1. Bounded request timeouts (default 10s).
2. Rate-limit awareness and automatic Retry-After handling with jitter.
3. Safe exponential backoff.
4. Non-destructive vs Destructive operation isolation:
   - Destructive operations (delete, ban, kick, modify) are NEVER blindly retried.
5. In-flight request deduplication for idempotent read queries.
6. Error classification: PERMISSION_DENIED (403), NOT_FOUND (404), RATE_LIMITED (429), SERVER_ERROR (5xx).
7. Automatic local state reconciliation hook on 404.
8. Structured API metrics and health telemetry.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, TypeVar

import discord
from core.results import ErrorCodes, Result, ResultStatus

logger = logging.getLogger("Rai.DiscordAPI")

T = TypeVar("T")


class APIActionCategory(str, Enum):
    READ = "READ"
    MESSAGE = "MESSAGE"
    MUTATION = "MUTATION"
    DESTRUCTIVE = "DESTRUCTIVE"


@dataclass
class APIMetrics:
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limited_count: int = 0
    forbidden_count: int = 0
    not_found_count: int = 0
    retried_count: int = 0
    total_latency_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round(self.total_latency_ms / self.total_requests, 2)


class DiscordReliabilityLayer:
    """
    Singleton reliability layer orchestrating Discord API traffic.
    Prevents API flooding, retry storms, and unhandled 403/404 crashes.
    """

    _instance: Optional[DiscordReliabilityLayer] = None

    def __init__(self, bot: Optional[discord.Client] = None) -> None:
        self.bot = bot
        self.metrics = APIMetrics()
        self._in_flight: Dict[str, asyncio.Future] = {}
        self._reconciliation_callbacks: List[Callable[[str, int], Coroutine[Any, Any, None]]] = []
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls, bot: Optional[discord.Client] = None) -> DiscordReliabilityLayer:
        if cls._instance is None:
            cls._instance = DiscordReliabilityLayer(bot)
        elif bot is not None and cls._instance.bot is None:
            cls._instance.bot = bot
        return cls._instance

    def register_reconciliation_callback(
        self, cb: Callable[[str, int], Coroutine[Any, Any, None]]
    ) -> None:
        """Register hook called when 404 NotFound occurs (e.g. channel or role deleted externally)."""
        self._reconciliation_callbacks.append(cb)

    async def execute(
        self,
        action_name: str,
        coro_factory: Callable[[], Coroutine[Any, Any, T]],
        category: APIActionCategory = APIActionCategory.READ,
        max_retries: int = 2,
        timeout: float = 10.0,
        dedup_key: Optional[str] = None,
        guild_id: Optional[int] = None,
    ) -> Result[T]:
        """
        Executes a Discord API coroutine with full reliability protections.
        """
        # Deduplication for idempotent requests
        if dedup_key and category == APIActionCategory.READ:
            async with self._lock:
                if dedup_key in self._in_flight:
                    logger.debug(f"[API] Deduplicating in-flight call: {dedup_key}")
                    fut = self._in_flight[dedup_key]
                    try:
                        res = await asyncio.shield(fut)
                        return Result.success(res)
                    except Exception as e:
                        return Result.failure(
                            error=f"Deduplicated request failed: {e}",
                            status=ResultStatus.DISCORD_ERROR,
                        )

                loop = asyncio.get_running_loop()
                fut = loop.create_future()
                self._in_flight[dedup_key] = fut

        t0 = time.perf_counter()
        retries = 0
        effective_max_retries = 0 if category == APIActionCategory.DESTRUCTIVE else max_retries

        try:
            while True:
                self.metrics.total_requests += 1
                try:
                    res = await asyncio.wait_for(coro_factory(), timeout=timeout)
                    elapsed = (time.perf_counter() - t0) * 1000.0
                    self.metrics.total_latency_ms += elapsed
                    self.metrics.successful_requests += 1

                    if dedup_key and dedup_key in self._in_flight:
                        f = self._in_flight.pop(dedup_key, None)
                        if f and not f.done():
                            f.set_result(res)

                    return Result.success(res)

                except asyncio.TimeoutError:
                    self.metrics.failed_requests += 1
                    logger.warning(f"[API] Timeout ({timeout}s) executing {action_name}")
                    return Result.failure(
                        error=f"Discord API timeout after {timeout}s",
                        status=ResultStatus.DISCORD_ERROR,
                        error_code=ErrorCodes.INTERNAL_ERROR,
                        retryable=False,
                    )

                except discord.NotFound as nf:
                    self.metrics.not_found_count += 1
                    self.metrics.failed_requests += 1
                    logger.debug(f"[API] Resource not found (404) in {action_name}: {nf}")

                    # Trigger state reconciliation if resource ID is provided or in message
                    for cb in self._reconciliation_callbacks:
                        try:
                            asyncio.create_task(cb(action_name, guild_id or 0))
                        except Exception:
                            pass

                    return Result.failure(
                        error=f"Target resource does not exist (404): {nf}",
                        status=ResultStatus.NOT_FOUND,
                        error_code=ErrorCodes.TARGET_NOT_FOUND,
                        retryable=False,
                    )

                except discord.Forbidden as fb:
                    self.metrics.forbidden_count += 1
                    self.metrics.failed_requests += 1
                    logger.warning(f"[API] Forbidden (403) executing {action_name}: {fb}")
                    return Result.failure(
                        error=f"Permission or hierarchy forbidden (403): {fb}",
                        status=ResultStatus.PERMISSION_DENIED,
                        error_code=ErrorCodes.BOT_MISSING_PERMS,
                        retryable=False,
                    )

                except discord.RateLimited as rl:
                    self.metrics.rate_limited_count += 1
                    wait_time = min(getattr(rl, "retry_after", 2.0), 5.0)
                    jitter = random.uniform(0.1, 0.5)
                    logger.warning(f"[API] Rate limited on {action_name}. Backing off {wait_time + jitter:.2f}s")
                    if retries < effective_max_retries:
                        retries += 1
                        self.metrics.retried_count += 1
                        await asyncio.sleep(wait_time + jitter)
                        continue
                    return Result.failure(
                        error=f"Rate limited by Discord. Backoff limit reached ({wait_time:.1f}s)",
                        status=ResultStatus.RATE_LIMITED,
                        error_code=ErrorCodes.MENTION_RATE_LIMIT,
                        retryable=True,
                    )

                except discord.HTTPException as http_err:
                    if http_err.status == 429:
                        self.metrics.rate_limited_count += 1
                        if retries < effective_max_retries:
                            retries += 1
                            self.metrics.retried_count += 1
                            delay = (2 ** retries) * 0.5 + random.uniform(0.1, 0.4)
                            logger.warning(f"[API] HTTP 429 on {action_name}. Retry {retries}/{effective_max_retries} in {delay:.2f}s")
                            await asyncio.sleep(delay)
                            continue
                        return Result.failure(
                            error=f"Discord API 429 Rate Limit exceeded: {http_err}",
                            status=ResultStatus.RATE_LIMITED,
                            retryable=True,
                        )

                    # 5xx Server Error from Discord
                    if 500 <= http_err.status < 600:
                        if retries < effective_max_retries:
                            retries += 1
                            self.metrics.retried_count += 1
                            delay = (1.5 ** retries) * 0.8 + random.uniform(0.1, 0.3)
                            logger.warning(f"[API] Discord server error {http_err.status} on {action_name}. Retry {retries}/{effective_max_retries}")
                            await asyncio.sleep(delay)
                            continue

                    self.metrics.failed_requests += 1
                    return Result.failure(
                        error=f"Discord API error (HTTP {http_err.status}): {http_err}",
                        status=ResultStatus.DISCORD_ERROR,
                        retryable=False,
                    )

                except Exception as unhandled:
                    self.metrics.failed_requests += 1
                    logger.error(f"[API] Unhandled error during {action_name}: {unhandled}", exc_info=True)
                    return Result.failure(
                        error=f"Unexpected error in API call: {unhandled}",
                        status=ResultStatus.INTERNAL_ERROR,
                        retryable=False,
                    )

        finally:
            if dedup_key and dedup_key in self._in_flight:
                f = self._in_flight.pop(dedup_key, None)
                if f and not f.done():
                    f.set_exception(RuntimeError("API request ended"))

    def get_telemetry(self) -> Dict[str, Any]:
        return {
            "total_requests": self.metrics.total_requests,
            "successful_requests": self.metrics.successful_requests,
            "failed_requests": self.metrics.failed_requests,
            "rate_limited": self.metrics.rate_limited_count,
            "forbidden_403": self.metrics.forbidden_count,
            "not_found_404": self.metrics.not_found_count,
            "retries": self.metrics.retried_count,
            "avg_latency_ms": self.metrics.avg_latency_ms,
        }
