"""
Temporary High-Speed Cache with In-Memory TTL Fallback for 『RΛI』.
Enforces mandatory TTL on all keys to prevent unbounded memory growth.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

from database.redis.connection import RedisConnectionManager

logger = logging.getLogger("Rai.Database.Redis.Cache")


class RedisCache:
    """
    Key-Value cache with mandatory TTL.
    Uses Redis when available, otherwise stores in local memory with timestamp expiration.
    """

    def __init__(self, conn_manager: Optional[RedisConnectionManager] = None):
        self.conn = conn_manager or RedisConnectionManager.get_instance()
        # In-memory store: key -> (value, expiry_timestamp)
        self._local_cache: Dict[str, Tuple[Any, float]] = {}

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [k for k, (_, exp) in self._local_cache.items() if now > exp]
        for k in expired:
            self._local_cache.pop(k, None)

    async def get(self, key: str) -> Optional[Any]:
        """Retrieves cached value if not expired."""
        client = await self.conn.get_client()
        redis_key = f"rai:cache:{key}"

        if client is not None:
            try:
                raw = await client.get(redis_key)
                if raw is not None:
                    try:
                        return json.loads(raw)
                    except Exception:
                        return raw
                return None
            except Exception as e:
                self.conn.record_failure(e)

        # In-memory fallback
        self._cleanup_expired()
        item = self._local_cache.get(key)
        if item and time.time() <= item[1]:
            return item[0]
        self._local_cache.pop(key, None)
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 300) -> bool:
        """Stores value with mandatory TTL (seconds)."""
        client = await self.conn.get_client()
        redis_key = f"rai:cache:{key}"

        if client is not None:
            try:
                payload = json.dumps(value, default=str) if not isinstance(value, str) else value
                await client.set(redis_key, payload, ex=ttl_seconds)
                return True
            except Exception as e:
                self.conn.record_failure(e)

        # In-memory fallback
        self._cleanup_expired()
        self._local_cache[key] = (value, time.time() + ttl_seconds)
        return True

    async def delete(self, key: str) -> bool:
        """Deletes cached key."""
        self._local_cache.pop(key, None)
        client = await self.conn.get_client()
        if client is not None:
            try:
                await client.delete(f"rai:cache:{key}")
            except Exception as e:
                self.conn.record_failure(e)
        return True
