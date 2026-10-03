"""
Background Cloud Synchronization Workers for 『RΛI』.
Asynchronously drains pending operations to PostgreSQL and Firebase with backoff and jitter.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Optional

from database.enums import SyncPriority, SyncStatus, SyncTarget
from database.postgres.repository import PostgresRepository
from database.firebase.repository import FirebaseRepository
from database.sync.queue import SyncQueue

logger = logging.getLogger("Rai.Database.Sync.Worker")


class DatabaseSyncWorker:
    """
    Dedicated background worker for draining SQLite sync queues.
    Operates independently for PostgreSQL and Firebase: a failure in one
    never interrupts processing for the other.
    """

    BACKOFF_STEPS = [1.0, 2.0, 5.0, 10.0, 30.0]

    def __init__(
        self,
        queue: SyncQueue,
        postgres_repo: PostgresRepository,
        firebase_repo: FirebaseRepository,
        interval_seconds: float = 3.0,
    ):
        self.queue = queue
        self.postgres_repo = postgres_repo
        self.firebase_repo = firebase_repo
        self.interval_seconds = interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_loop(), name="rai_database_sync_worker")
            logger.info("Database synchronization worker started.")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Database synchronization worker stopped.")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                # 1. Process PostgreSQL Batch
                await self._drain_postgres_batch()

                # 2. Process Firebase Batch
                await self._drain_firebase_batch()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in sync worker loop: {e}", exc_info=True)

            await asyncio.sleep(self.interval_seconds)

    async def _drain_postgres_batch(self, limit: int = 25) -> int:
        """Drains pending operations for PostgreSQL."""
        if not self.postgres_repo.pool.is_connected:
            return 0

        batch = await self.queue.get_next_batch(target=SyncTarget.POSTGRESQL, limit=limit)
        processed = 0

        for op in batch:
            try:
                res = None
                if op.operation_type == "save_incident":
                    res = await self.postgres_repo.save_incident(op.payload)
                elif op.operation_type == "save_security_event":
                    res = await self.postgres_repo.save_security_event(op.payload)

                if res and res.success:
                    await self.queue.mark_success(op.operation_id)
                    processed += 1
                else:
                    # Failure - schedule retry with backoff + jitter
                    attempt = op.attempt_count + 1
                    idx = min(attempt - 1, len(self.BACKOFF_STEPS) - 1)
                    delay = self.BACKOFF_STEPS[idx] + random.uniform(0.1, 1.0)
                    err_code = res.error.code if res and res.error else "POSTGRES_SYNC_FAILED"
                    await self.queue.mark_retry(op.operation_id, attempt, err_code, delay)
            except Exception as e:
                attempt = op.attempt_count + 1
                await self.queue.mark_retry(op.operation_id, attempt, "UNHANDLED_EXCEPTION", 10.0)

        return processed

    async def _drain_firebase_batch(self, limit: int = 25) -> int:
        """Drains pending operations for Firebase."""
        if not self.firebase_repo.conn.is_connected:
            return 0

        batch = await self.queue.get_next_batch(target=SyncTarget.FIREBASE, limit=limit)
        processed = 0

        for op in batch:
            try:
                res = None
                if op.operation_type == "sync_incident":
                    res = await self.firebase_repo.sync_incident(op.payload)
                elif op.operation_type == "sync_dashboard":
                    res = await self.firebase_repo.sync_dashboard_summary(op.guild_id, op.payload)

                if res and res.success:
                    await self.queue.mark_success(op.operation_id)
                    processed += 1
                else:
                    attempt = op.attempt_count + 1
                    idx = min(attempt - 1, len(self.BACKOFF_STEPS) - 1)
                    delay = self.BACKOFF_STEPS[idx] + random.uniform(0.1, 1.0)
                    err_code = res.error.code if res and res.error else "FIREBASE_SYNC_FAILED"
                    await self.queue.mark_retry(op.operation_id, attempt, err_code, delay)
            except Exception as e:
                attempt = op.attempt_count + 1
                await self.queue.mark_retry(op.operation_id, attempt, "UNHANDLED_EXCEPTION", 10.0)

        return processed
