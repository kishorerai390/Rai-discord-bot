"""
PostgreSQL Async Connection Pool with Circuit Breaker and Resilient Degradation for 『RΛI』.
Handles multi-guild high-volume persistent storage without single points of failure.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional

from database.enums import DatabaseHealthStatus

logger = logging.getLogger("Rai.Database.Postgres")


class PostgresConnectionPool:
    """
    Manages asyncpg connection pool to PostgreSQL.
    If PostgreSQL is unreachable or goes offline, safely trips circuit breaker
    and routes writes to the local SQLite sync queue.
    """

    _instance: Optional[PostgresConnectionPool] = None

    def __init__(self, postgres_url: Optional[str] = None):
        self.postgres_url = postgres_url or os.getenv("POSTGRES_URL")
        self.enabled = os.getenv("POSTGRES_ENABLED", "true").lower() in ("true", "1", "yes") and bool(self.postgres_url)
        self._pool: Any = None
        self._health_status = DatabaseHealthStatus.STARTING if self.enabled else DatabaseHealthStatus.DISABLED
        self._failure_count = 0
        self._max_failures = 3
        self._last_failure_time = 0.0
        self._circuit_open = False
        self._circuit_reset_timeout = 30.0  # seconds
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> PostgresConnectionPool:
        if cls._instance is None:
            cls._instance = PostgresConnectionPool()
        return cls._instance

    @property
    def is_connected(self) -> bool:
        return self._pool is not None and not self._circuit_open

    @property
    def health_status(self) -> DatabaseHealthStatus:
        if not self.enabled:
            return DatabaseHealthStatus.DISABLED
        if self._circuit_open:
            return DatabaseHealthStatus.DEGRADED
        if self._pool is not None:
            return DatabaseHealthStatus.ONLINE
        return self._health_status

    async def connect(self) -> bool:
        """Establishes connection pool to PostgreSQL. Returns True on success, False on graceful failure."""
        if not self.enabled:
            logger.info("PostgreSQL is disabled or POSTGRES_URL is not configured. Cloud writes will queue locally.")
            self._health_status = DatabaseHealthStatus.DISABLED
            return False

        now = time.time()
        if self._circuit_open and (now - self._last_failure_time < self._circuit_reset_timeout):
            return False

        try:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                dsn=self.postgres_url,
                min_size=2,
                max_size=10,
                command_timeout=5.0,
                timeout=3.0,
            )
            # Validate connection
            async with self._pool.acquire() as conn:
                await conn.execute("SELECT 1;")

            self._circuit_open = False
            self._failure_count = 0
            self._health_status = DatabaseHealthStatus.ONLINE
            logger.info("PostgreSQL connection pool established successfully.")
            return True
        except Exception as e:
            self._failure_count += 1
            self._last_failure_time = now
            if self._failure_count >= self._max_failures:
                self._circuit_open = True
                self._health_status = DatabaseHealthStatus.DEGRADED
                logger.warning(f"PostgreSQL unavailable ({e}). Circuit breaker OPEN. SQLite queue active.")
            else:
                self._health_status = DatabaseHealthStatus.RECONNECTING
                logger.debug(f"PostgreSQL connect attempt failed: {e}")
            return False

    async def get_connection(self) -> Optional[Any]:
        """Acquires a connection from pool if online."""
        if not self.is_connected:
            now = time.time()
            if self._circuit_open and (now - self._last_failure_time >= self._circuit_reset_timeout):
                logger.info("PostgreSQL circuit breaker half-open: probing connection...")
                await self.connect()

        if self._pool is not None and not self._circuit_open:
            try:
                return self._pool.acquire()
            except Exception as e:
                self.record_failure(e)
        return None

    def record_failure(self, error: Exception) -> None:
        """Records a database error, tripping circuit breaker if threshold is exceeded."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self._max_failures:
            self._circuit_open = True
            self._health_status = DatabaseHealthStatus.DEGRADED
            logger.warning(f"PostgreSQL query failure ({error}). Circuit breaker TRIPPED.")

    async def close(self) -> None:
        """Gracefully closes pool."""
        if self._pool is not None:
            try:
                await self._pool.close()
            except Exception as e:
                logger.debug(f"Postgres pool close note: {e}")
            finally:
                self._pool = None
        self._health_status = DatabaseHealthStatus.OFFLINE
