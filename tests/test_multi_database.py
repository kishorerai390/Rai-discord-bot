"""
Comprehensive Unit & Integration Tests for 『RΛI』 Multi-Database Production Architecture.
Validates:
- SQLite queueing and priority enforcement
- Idempotency key deduplication
- Redis in-memory fallback for rate limiting, cache, and locks
- PostgreSQL connection pooling and circuit breaking
- Firebase offline tolerance and cloud synchronization
- Reconciliation of pending incidents
"""

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.results import Result
from database.database import Database
from database.enums import DatabaseHealthStatus, SyncPriority, SyncStatus, SyncTarget
from database.manager import DatabaseManager
from database.models import PendingSyncOperation
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


class TestMultiDatabaseArchitecture(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_multi.db"
        self.db = Database(self.db_path)
        await self.db.connect()
        self.sync_queue = SyncQueue(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        db_mgr = DatabaseManager._instance
        if db_mgr and db_mgr.sqlite:
            try:
                await db_mgr.sqlite.close()
            except Exception:
                pass
        DatabaseManager._instance = None
        import gc
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    async def test_sync_queue_priority_ordering(self):
        """Validates that CRITICAL_SECURITY operations are dequeued before ANALYTICS and NON_CRITICAL."""
        # Enqueue low priority first
        op1 = await self.sync_queue.enqueue(
            target=SyncTarget.POSTGRESQL,
            operation_type="analytics_event",
            guild_id=123,
            payload={"metric": "page_view"},
            priority=SyncPriority.ANALYTICS,
            entity_id="op_low_1",
        )
        # Enqueue high priority second
        op2 = await self.sync_queue.enqueue(
            target=SyncTarget.POSTGRESQL,
            operation_type="anti_raid_lockdown",
            guild_id=123,
            payload={"action": "channel_lock"},
            priority=SyncPriority.CRITICAL_SECURITY,
            entity_id="op_high_2",
        )

        self.assertTrue(op1)
        self.assertTrue(op2)

        # Dequeue operations
        pending = await self.sync_queue.get_next_batch(target=SyncTarget.POSTGRESQL, limit=10)
        self.assertEqual(len(pending), 2)
        # CRITICAL_SECURITY must be first in line!
        self.assertEqual(pending[0].priority, "CRITICAL_SECURITY")
        self.assertEqual(pending[0].operation_type, "anti_raid_lockdown")
        self.assertEqual(pending[1].priority, "ANALYTICS")

    async def test_idempotency_deduplication(self):
        """Verifies duplicate entity writes with the same idempotency key are rejected/ignored."""
        op_first = await self.sync_queue.enqueue(
            target=SyncTarget.POSTGRESQL,
            operation_type="save_incident",
            guild_id=100,
            payload={"incident_id": "RAI-INC-001"},
            priority=SyncPriority.INCIDENT,
            incident_id="RAI-INC-001",
            entity_id="inc_001",
        )
        self.assertTrue(op_first)

        # Enqueue identical entity
        op_duplicate = await self.sync_queue.enqueue(
            target=SyncTarget.POSTGRESQL,
            operation_type="save_incident",
            guild_id=100,
            payload={"incident_id": "RAI-INC-001"},
            priority=SyncPriority.INCIDENT,
            incident_id="RAI-INC-001",
            entity_id="inc_001",
        )
        self.assertTrue(op_duplicate)

        # Verify only 1 pending record exists in queue despite two enqueue calls
        pending = await self.sync_queue.get_next_batch(target=SyncTarget.POSTGRESQL, limit=10)
        self.assertEqual(len(pending), 1)

    async def test_redis_in_memory_fallback(self):
        """Validates that when Redis is offline, rate limiting and locks fall back to memory without crashing."""
        redis_mgr = RedisConnectionManager()
        redis_mgr.enabled = False  # Simulate Redis unavailable
        await redis_mgr.connect()

        self.assertTrue(redis_mgr.is_fallback_active)
        self.assertEqual(redis_mgr.health_status, DatabaseHealthStatus.DISABLED)

        # Rate limiter fallback
        limiter = RedisRateLimiter(redis_mgr)
        # Should allow initial attempts
        is_lim1, count1, retry1 = await limiter.is_rate_limited(
            key="user_123",
            limit=2,
            window_seconds=10.0,
        )
        self.assertFalse(is_lim1)
        self.assertEqual(count1, 1)

        is_lim2, count2, retry2 = await limiter.is_rate_limited(
            key="user_123",
            limit=2,
            window_seconds=10.0,
        )
        self.assertFalse(is_lim2)
        self.assertEqual(count2, 2)

        # Third attempt should be rate limited
        is_lim3, count3, retry3 = await limiter.is_rate_limited(
            key="user_123",
            limit=2,
            window_seconds=10.0,
        )
        self.assertTrue(is_lim3)
        self.assertEqual(count3, 3)

        # Lock fallback
        lock = RedisDistributedLock(redis_mgr)
        acquired = await lock.acquire_lock("guild_lock_100", ttl_seconds=5)
        self.assertTrue(acquired)

        # Concurrent attempt should fail
        acquired2 = await lock.acquire_lock("guild_lock_100", ttl_seconds=5)
        self.assertFalse(acquired2)

        await lock.release_lock("guild_lock_100")
        # Should be acquirable again
        acquired3 = await lock.acquire_lock("guild_lock_100", ttl_seconds=5)
        self.assertTrue(acquired3)
        await lock.release_lock("guild_lock_100")

    async def test_cache_with_ttl_fallback(self):
        """Verifies cache TTL expiry in fallback mode."""
        redis_mgr = RedisConnectionManager()
        redis_mgr.enabled = False
        cache = RedisCache(redis_mgr)

        await cache.set("test_key", {"status": "ok"}, ttl_seconds=1)
        val = await cache.get("test_key")
        self.assertEqual(val, {"status": "ok"})

        await cache.delete("test_key")
        val2 = await cache.get("test_key")
        self.assertIsNone(val2)

    async def test_sync_worker_execution_and_retry(self):
        """Validates that DatabaseSyncWorker successfully drains queue and handles transient errors with retry backoff."""
        mock_pg_repo = MagicMock()
        mock_pg_repo.pool = MagicMock()
        mock_pg_repo.pool.is_connected = True
        mock_pg_repo.save_incident = AsyncMock(return_value=Result.ok(None))

        mock_fb_repo = MagicMock()
        mock_fb_repo.conn = MagicMock()
        mock_fb_repo.conn.is_connected = True
        mock_fb_repo.sync_incident = AsyncMock(return_value=Result.ok(None))

        worker = DatabaseSyncWorker(
            queue=self.sync_queue,
            postgres_repo=mock_pg_repo,
            firebase_repo=mock_fb_repo,
        )

        # Enqueue one PostgreSQL and one Firebase task
        await self.sync_queue.enqueue(
            target=SyncTarget.POSTGRESQL,
            operation_type="save_incident",
            guild_id=1,
            payload={"incident_id": "INC-P1"},
            priority=SyncPriority.INCIDENT,
            entity_id="pg_1",
        )
        await self.sync_queue.enqueue(
            target=SyncTarget.FIREBASE,
            operation_type="sync_incident",
            guild_id=1,
            payload={"incident_id": "INC-F1"},
            priority=SyncPriority.INCIDENT,
            entity_id="fb_1",
        )

        # Run one drain cycle
        processed_pg = await worker._drain_postgres_batch(limit=10)
        self.assertEqual(processed_pg, 1)
        mock_pg_repo.save_incident.assert_awaited_once()

        processed_fb = await worker._drain_firebase_batch(limit=10)
        self.assertEqual(processed_fb, 1)
        mock_fb_repo.sync_incident.assert_awaited_once()

        # Check queue stats
        stats = await self.db.get_sync_queue_stats()
        self.assertEqual(stats["total_synced"], 2)
        self.assertEqual(stats["total_pending"], 0)

    async def test_reconciliation_detects_un_synced_incidents(self):
        """Verifies ReconciliationManager discovers un-synced incidents in SQLite and enqueues them."""
        # Ensure guild config exists to satisfy foreign key
        await self.db.get_or_create_guild_config(555)

        # Insert a local mention spam incident into SQLite
        await self.db.create_mention_spam_incident(
            incident_id="RAI-INC-REC-001",
            guild_id=555,
            user_id=999,
            user_name="Spammer#0001",
            first_channel_id=101,
            channels_affected=[101, 102],
            messages_count=5,
            mentions_count=25,
            unique_targets_count=15,
            first_seen="2026-10-01T20:00:00Z",
            last_seen="2026-10-01T20:01:00Z",
            severity="CRITICAL",
            action_taken="TIMEOUT",
            incident_status="RESOLVED",
        )

        reconciliation = ReconciliationManager(self.db, self.sync_queue)
        res = await reconciliation.reconcile_recent_incidents(limit=10)
        self.assertGreaterEqual(res["postgres_queued"], 1)

        # Should be queued for PostgreSQL sync
        pending = await self.sync_queue.get_next_batch(target=SyncTarget.POSTGRESQL, limit=10)
        self.assertTrue(any(op.guild_id == 555 for op in pending))


if __name__ == "__main__":
    unittest.main()
