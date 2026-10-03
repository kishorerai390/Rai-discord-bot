"""
Distributed Locks with In-Memory Async Fallback for 『RΛI』.
Ensures worker coordination across instances with local lock survival.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Optional

from database.redis.connection import RedisConnectionManager

logger = logging.getLogger("Rai.Database.Redis.Locks")


class RedisDistributedLock:
    """
    Acquires distributed locks using Redis SETNX with TTL.
    Degrades to in-memory asyncio.Lock when Redis is unavailable.
    """

    def __init__(self, conn_manager: Optional[RedisConnectionManager] = None):
        self.conn = conn_manager or RedisConnectionManager.get_instance()
        self._local_locks: Dict[str, asyncio.Lock] = {}

    def _get_local_lock(self, key: str) -> asyncio.Lock:
        if key not in self._local_locks:
            self._local_locks[key] = asyncio.Lock()
        return self._local_locks[key]

    async def acquire_lock(self, lock_key: str, ttl_seconds: int = 30) -> bool:
        """Attempts to acquire lock. Returns True if acquired, False otherwise."""
        client = await self.conn.get_client()
        redis_key = f"rai:lock:{lock_key}"

        if client is not None:
            try:
                # SET key val NX EX ttl_seconds
                acquired = await client.set(redis_key, str(time.time()), nx=True, ex=ttl_seconds)
                return bool(acquired)
            except Exception as e:
                self.conn.record_failure(e)
                logger.debug(f"Redis lock error, falling back to local lock: {e}")

        # In-memory lock fallback
        local_lock = self._get_local_lock(lock_key)
        try:
            return not local_lock.locked() and await asyncio.wait_for(local_lock.acquire(), timeout=0.01)
        except (asyncio.TimeoutError, Exception):
            return False

    async def release_lock(self, lock_key: str) -> bool:
        """Releases the specified lock."""
        client = await self.conn.get_client()
        redis_key = f"rai:lock:{lock_key}"

        if client is not None:
            try:
                await client.delete(redis_key)
            except Exception as e:
                self.conn.record_failure(e)

        local_lock = self._get_local_lock(lock_key)
        if local_lock.locked():
            try:
                local_lock.release()
            except Exception:
                pass
        return True
