"""
Redis Connection Manager with Automatic In-Memory Fallback and Circuit Breaker for 『RΛI』.
Ensures Redis outages NEVER crash the bot or block security operations.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional

from database.enums import DatabaseHealthStatus

logger = logging.getLogger("Rai.Database.Redis")


class RedisConnectionManager:
    """
    Manages Redis connection lifecycle, automatic circuit breaking,
    and seamless in-memory fallback when Redis is unreachable.
    """

    _instance: Optional[RedisConnectionManager] = None

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.enabled = os.getenv("REDIS_ENABLED", "true").lower() in ("true", "1", "yes")
        self._client: Any = None
        self._fallback_active = False
        self._health_status = DatabaseHealthStatus.STARTING if self.enabled else DatabaseHealthStatus.DISABLED
        self._failure_count = 0
        self._max_failures = 3
        self._last_failure_time = 0.0
        self._circuit_open = False
        self._circuit_reset_timeout = 30.0  # seconds
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> RedisConnectionManager:
        if cls._instance is None:
            cls._instance = RedisConnectionManager()
        return cls._instance

    @property
    def is_connected(self) -> bool:
        return self._client is not None and not self._fallback_active and not self._circuit_open

    @property
    def is_fallback_active(self) -> bool:
        return self._fallback_active

    @property
    def health_status(self) -> DatabaseHealthStatus:
        if not self.enabled:
            return DatabaseHealthStatus.DISABLED
        if self._circuit_open:
            return DatabaseHealthStatus.DEGRADED
        if self._client is not None:
            return DatabaseHealthStatus.ONLINE
        if self._fallback_active:
            return DatabaseHealthStatus.DEGRADED
        return self._health_status

    async def connect(self) -> bool:
        """Attempts connection to Redis. If unavailable, seamlessly enables in-memory fallback."""
        if not self.enabled:
            logger.info("Redis is disabled via REDIS_ENABLED=false. Operating in local memory fallback.")
            self._fallback_active = True
            self._health_status = DatabaseHealthStatus.DISABLED
            return False

        now = time.time()
        if self._circuit_open and (now - self._last_failure_time < self._circuit_reset_timeout):
            self._fallback_active = True
            return False

        try:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            # Test ping
            await self._client.ping()
            self._fallback_active = False
            self._circuit_open = False
            self._failure_count = 0
            self._health_status = DatabaseHealthStatus.ONLINE
            logger.info("Redis connection established successfully.")
            return True
        except Exception as e:
            self._failure_count += 1
            self._last_failure_time = now
            self._fallback_active = True
            if self._failure_count >= self._max_failures:
                self._circuit_open = True
                self._health_status = DatabaseHealthStatus.DEGRADED
                logger.warning(
                    f"Redis unavailable ({e}). Circuit breaker OPEN. Operating in in-memory fallback."
                )
            else:
                self._health_status = DatabaseHealthStatus.RECONNECTING
                logger.debug(f"Redis ping attempt failed ({e}). In-memory fallback active.")
            return False

    async def get_client(self) -> Optional[Any]:
        """Returns the active Redis client if connected, or None if fallback is active."""
        if not self.is_connected:
            # Check if circuit reset is due
            now = time.time()
            if self._circuit_open and (now - self._last_failure_time >= self._circuit_reset_timeout):
                logger.info("Redis circuit breaker half-open: attempting reconnection probe...")
                await self.connect()
        return self._client if self.is_connected else None

    def record_failure(self, error: Exception) -> None:
        """Records an execution error on Redis command, tripping circuit breaker if threshold reached."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        self._fallback_active = True
        if self._failure_count >= self._max_failures:
            self._circuit_open = True
            self._health_status = DatabaseHealthStatus.DEGRADED
            logger.warning(f"Redis operation error ({error}). Circuit breaker TRIPPED.")

    async def close(self) -> None:
        """Gracefully closes Redis connection pool."""
        if self._client:
            try:
                await self._client.aclose()
            except Exception as e:
                logger.debug(f"Redis close note: {e}")
            finally:
                self._client = None
        self._health_status = DatabaseHealthStatus.OFFLINE
