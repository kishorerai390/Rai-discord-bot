"""
Redis-Powered Rate Limiter with In-Memory Sliding-Window Fallback for 『RΛI』.
Provides fast distributed rate limiting with 100% survival guarantee if Redis is offline.
"""

from __future__ import annotations

import collections
import logging
import time
from typing import Dict, List, Optional, Tuple

from database.redis.connection import RedisConnectionManager

logger = logging.getLogger("Rai.Database.Redis.RateLimit")


class RedisRateLimiter:
    """
    High-performance sliding-window rate limiter.
    Uses Redis Sorted Sets (ZSET) when online, and automatically degrades
    to local memory sliding windows without raising exceptions or blocking security.
    """

    def __init__(self, conn_manager: Optional[RedisConnectionManager] = None):
        self.conn = conn_manager or RedisConnectionManager.get_instance()
        # In-memory sliding window fallback: key -> deque of timestamps
        self._local_buckets: Dict[str, collections.deque[float]] = collections.defaultdict(
            lambda: collections.deque(maxlen=500)
        )
        self._last_local_cleanup = time.time()

    def _cleanup_local_buckets(self, ttl: float = 120.0) -> None:
        now = time.time()
        if now - self._last_local_cleanup < 60.0:
            return
        self._last_local_cleanup = now
        expired = [k for k, dq in self._local_buckets.items() if not dq or (now - dq[-1] > ttl)]
        for k in expired:
            self._local_buckets.pop(k, None)

    async def is_rate_limited(
        self,
        key: str,
        limit: int,
        window_seconds: float,
    ) -> Tuple[bool, int, float]:
        """
        Evaluates sliding-window rate limit.
        Returns: (is_limited: bool, current_count: int, retry_after: float).
        """
        now = time.time()
        client = await self.conn.get_client()

        if client is not None:
            redis_key = f"rai:ratelimit:{key}"
            try:
                pipe = client.pipeline()
                # 1. Remove expired timestamps older than sliding window
                pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
                # 2. Count current elements in window
                pipe.zcard(redis_key)
                # 3. Add current timestamp
                pipe.zadd(redis_key, {str(now): now})
                # 4. Set TTL on key to auto-expire
                pipe.expire(redis_key, int(window_seconds * 2) + 5)
                results = await pipe.execute()

                current_count = results[1] + 1
                if current_count > limit:
                    # Fetch oldest timestamp to compute exact retry_after
                    oldest = await client.zrange(redis_key, 0, 0, withscores=True)
                    retry_after = round(max(0.1, (oldest[0][1] + window_seconds) - now), 2) if oldest else window_seconds
                    return True, current_count, retry_after

                return False, current_count, 0.0
            except Exception as e:
                self.conn.record_failure(e)
                logger.debug(f"Redis rate limit failed, switching to local memory fallback: {e}")

        # Local in-memory sliding window fallback
        self._cleanup_local_buckets(window_seconds * 2)
        bucket = self._local_buckets[key]
        # Prune expired timestamps
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        current_count = len(bucket) + 1
        if current_count > limit:
            oldest_ts = bucket[0] if bucket else now
            retry_after = round(max(0.1, (oldest_ts + window_seconds) - now), 2)
            return True, current_count, retry_after

        bucket.append(now)
        return False, current_count, 0.0

    async def reset(self, key: str) -> None:
        """Clears rate limit state for a key."""
        self._local_buckets.pop(key, None)
        client = await self.conn.get_client()
        if client:
            try:
                await client.delete(f"rai:ratelimit:{key}")
            except Exception as e:
                self.conn.record_failure(e)
