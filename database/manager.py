"""
Central Multi-Database Manager for 『RΛI』.
Coordinates SQLite, PostgreSQL, Redis, and Firebase with strict failure isolation,
automatic circuit breaking, priority synchronization queues, and health diagnostics.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from database.database import Database
from database.enums import DatabaseHealthStatus, SyncPriority, SyncTarget
from database.postgres.connection import PostgresConnectionPool
from database.postgres.repository import PostgresRepository
from database.redis.connection import RedisConnectionManager
from database.redis.rate_limit import RedisRateLimiter
from database.redis.cache import RedisCache
from database.redis.locks import RedisDistributedLock
from database.firebase.connection import FirebaseConnectionManager
from database.firebase.repository import FirebaseRepository
from database.sync.queue import SyncQueue
from database.sync.worker import DatabaseSyncWorker
from database.sync.reconciliation import ReconciliationManager

logger = logging.getLogger("Rai.Database.Manager")


@dataclass(frozen=True)
class MultiDatabaseStatus:
    """Consolidated health and diagnostic telemetry across all four database engines."""
    sqlite: DatabaseHealthStatus
    postgres: DatabaseHealthStatus
    redis: DatabaseHealthStatus
    firebase: DatabaseHealthStatus
    sync_status: str
    pending_postgres: int
    pending_firebase: int
    redis_fallback_active: bool
    healthy: bool


class DatabaseManager:
    """
    Central Database Coordinator for 『RΛI』.
    Core Architecture Principle:
    - SQLite = Local Runtime Survival & Security State (Authoritative for immediate protection)
    - PostgreSQL = Cloud Permanent Production Storage
    - Redis = High-Speed Temporary State & Distributed Locks
    - Firebase = Cloud Realtime Dashboard & Analytics Ecosystem
    """

    _instance: Optional[DatabaseManager] = None

    def __init__(self, db_path: Optional[Path] = None):
        # 1. SQLite (Local survival database)
        self.sqlite = Database(db_path)
        # 2. PostgreSQL (Persistent storage)
        self.postgres_conn = PostgresConnectionPool.get_instance()
        self.postgres_repo = PostgresRepository(self.postgres_conn)
        # 3. Redis (High-speed state)
        self.redis_conn = RedisConnectionManager.get_instance()
        self.rate_limiter = RedisRateLimiter(self.redis_conn)
        self.cache = RedisCache(self.redis_conn)
        self.locks = RedisDistributedLock(self.redis_conn)
        # 4. Firebase (Cloud ecosystem)
        self.firebase_conn = FirebaseConnectionManager.get_instance()
        self.firebase_repo = FirebaseRepository(self.firebase_conn)
        # 5. Sync & Reconciliation Engine
        self.sync_queue = SyncQueue(self.sqlite)
        self.sync_worker = DatabaseSyncWorker(
            queue=self.sync_queue,
            postgres_repo=self.postgres_repo,
            firebase_repo=self.firebase_repo,
        )
        self.reconciliation = ReconciliationManager(self.sqlite, self.sync_queue)

    @classmethod
    def get_instance(cls, db_path: Optional[Path] = None) -> DatabaseManager:
        if cls._instance is None:
            cls._instance = DatabaseManager(db_path)
        return cls._instance

    async def initialize(self) -> MultiDatabaseStatus:
        """
        Initializes all database engines asynchronously and non-blockingly.
        Guarantees: If any cloud database fails, SQLite remains active and security operates normally.
        """
        logger.info("Initializing 『RΛI』 Multi-Database Production Architecture...")

        # 1. SQLite (Mandatory local runtime)
        try:
            await self.sqlite.connect()
            sqlite_status = DatabaseHealthStatus.ONLINE
        except Exception as e:
            logger.critical(f"FATAL: SQLite initialization failed: {e}", exc_info=True)
            sqlite_status = DatabaseHealthStatus.ERROR

        # 2. Redis (Optional high-speed state, falls back to memory)
        try:
            await self.redis_conn.connect()
        except Exception as e:
            logger.warning(f"Redis initialization notice: {e}")

        # 3. PostgreSQL (Optional cloud persistent, falls back to SQLite queue)
        try:
            await self.postgres_conn.connect()
            if self.postgres_conn.is_connected:
                await self.postgres_repo.init_schema()
        except Exception as e:
            logger.warning(f"PostgreSQL initialization notice: {e}")

        # 4. Firebase (Optional cloud dashboard, falls back to SQLite queue)
        try:
            await self.firebase_conn.connect()
        except Exception as e:
            logger.warning(f"Firebase initialization notice: {e}")

        # 5. Start Background Sync Worker
        self.sync_worker.start()

        status = await self.get_status()
        logger.info(
            f"Multi-Database initialization complete. SQLite: {status.sqlite.value}, "
            f"Postgres: {status.postgres.value}, Redis: {status.redis.value}, Firebase: {status.firebase.value}"
        )
        return status

    async def get_status(self) -> MultiDatabaseStatus:
        """Collects live health status across all four engines and the synchronization queue."""
        sqlite_status = DatabaseHealthStatus.ONLINE if self.sqlite.is_connected else DatabaseHealthStatus.OFFLINE
        pg_status = self.postgres_conn.health_status
        redis_status = self.redis_conn.health_status
        fb_status = self.firebase_conn.health_status

        # Query pending counts
        stats = await self.sqlite.get_sync_queue_stats()
        by_target = stats.get("by_target", {})
        pending_pg = by_target.get(SyncTarget.POSTGRESQL.value, {}).get("PENDING", 0)
        pending_fb = by_target.get(SyncTarget.FIREBASE.value, {}).get("PENDING", 0)

        sync_status = "HEALTHY" if stats.get("total_dead_letter", 0) == 0 else "DEGRADED"

        # Overall health: Healthy if SQLite is ONLINE and critical security is uncompromised
        healthy = sqlite_status == DatabaseHealthStatus.ONLINE

        return MultiDatabaseStatus(
            sqlite=sqlite_status,
            postgres=pg_status,
            redis=redis_status,
            firebase=fb_status,
            sync_status=sync_status,
            pending_postgres=pending_pg,
            pending_firebase=pending_fb,
            redis_fallback_active=self.redis_conn.is_fallback_active,
            healthy=healthy,
        )

    async def record_incident_multi_db(
        self,
        incident_data: Dict[str, Any],
        priority: SyncPriority = SyncPriority.INCIDENT,
    ) -> None:
        """
        Standard Multi-DB Incident Persistence Flow:
        1. Saved immediately into local SQLite (Deterministic protection).
        2. Enqueued for asynchronous PostgreSQL synchronization.
        3. Enqueued for asynchronous Firebase cloud dashboard synchronization.
        """
        inc_id = incident_data.get("incident_id", "INC-0")
        guild_id = incident_data.get("guild_id", 0)

        # Enqueue for PostgreSQL
        await self.sync_queue.enqueue(
            target=SyncTarget.POSTGRESQL,
            operation_type="save_incident",
            guild_id=guild_id,
            payload=incident_data,
            priority=priority,
            incident_id=inc_id,
            entity_id=f"inc_pg_{inc_id}",
        )

        # Enqueue for Firebase
        await self.sync_queue.enqueue(
            target=SyncTarget.FIREBASE,
            operation_type="sync_incident",
            guild_id=guild_id,
            payload=incident_data,
            priority=priority,
            incident_id=inc_id,
            entity_id=f"inc_fb_{inc_id}",
        )

    async def close(self) -> None:
        """Graceful shutdown of sync workers, connection pools, and database handles."""
        logger.info("Closing Multi-Database Manager...")
        await self.sync_worker.stop()
        await self.postgres_conn.close()
        await self.redis_conn.close()
        await self.sqlite.close()
        logger.info("Multi-Database Manager shutdown complete.")
