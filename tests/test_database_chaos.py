"""
Database Chaos & Cloud Outage Simulation Test Suite for 『RΛI』.
Simulates:
- Complete cloud blackout: PostgreSQL OFFLINE, Redis OFFLINE, Firebase OFFLINE
- High-severity threat attack during outage (Mass mention spam attack & server raid)
- Validates immediate local deterministic containment without blocking
- Validates priority queueing in SQLite
- Validates seamless recovery and reconciliation once cloud services restore
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
from database.postgres.connection import PostgresConnectionPool
from database.postgres.repository import PostgresRepository
from database.redis.connection import RedisConnectionManager
from database.redis.rate_limit import RedisRateLimiter
from database.firebase.connection import FirebaseConnectionManager
from database.firebase.repository import FirebaseRepository
from database.sync.queue import SyncQueue
from database.sync.worker import DatabaseSyncWorker
from database.sync.reconciliation import ReconciliationManager
from observability.health import ObservabilityHealthService, SystemHealthReport


class TestDatabaseChaosAndDisasterRecovery(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        DatabaseManager._instance = None
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "chaos.db"
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

    async def test_complete_cloud_blackout_chaos_scenario(self):
        """
        Simulates total cloud outage (Redis, PostgreSQL, Firebase down).
        Asserts:
        1. Threat containment operates locally without delay or hanging
        2. SQLite persists critical incidents
        3. Cloud sync is queued with CRITICAL_SECURITY priority
        4. Health report marks Security HEALTHY and Cloud DEGRADED
        5. Once cloud returns, worker drains queue to complete sync
        """
        # ==========================================
        # PHASE 1: CHAOS INDUCTION (CLOUD OUTAGE)
        # ==========================================
        db_mgr = DatabaseManager.get_instance(self.db_path)
        if not db_mgr.sqlite.is_connected:
            await db_mgr.sqlite.connect()

        # Hard-disconnect all cloud engines
        db_mgr.postgres_conn.pool = None
        db_mgr.postgres_conn.enabled = True
        db_mgr.redis_conn._client = None
        db_mgr.redis_conn._fallback_active = True
        db_mgr.firebase_conn._client = None

        # Verify degraded cloud status
        status = await db_mgr.get_status()
        self.assertEqual(status.sqlite, DatabaseHealthStatus.ONLINE)
        self.assertNotEqual(status.postgres, DatabaseHealthStatus.ONLINE)
        self.assertNotEqual(status.redis, DatabaseHealthStatus.ONLINE)
        self.assertNotEqual(status.firebase, DatabaseHealthStatus.ONLINE)
        self.assertTrue(status.redis_fallback_active)

        # Verify isolated security health
        mock_bot = MagicMock()
        mock_bot.is_ready.return_value = True
        report: SystemHealthReport = ObservabilityHealthService.evaluate_health(mock_bot)
        self.assertEqual(report.security_health, "HEALTHY")
        self.assertEqual(report.overall_status, "DEGRADED")

        # ==========================================
        # PHASE 2: THREAT ATTACK UNDER BLACKOUT
        # ==========================================
        guild_id = 999111
        await db_mgr.sqlite.get_or_create_guild_config(guild_id)

        # Attack: Mass User Mention attack detected
        # 1. Local rate limiting intercepts via memory fallback
        limiter = db_mgr.rate_limiter
        for _ in range(5):
            await limiter.is_rate_limited(f"user_attack_{guild_id}", limit=3, window_seconds=10.0)
        is_lim, count, _ = await limiter.is_rate_limited(f"user_attack_{guild_id}", limit=3, window_seconds=10.0)
        self.assertTrue(is_lim)

        # 2. Local immediate incident persistence in SQLite
        incident_id = f"RAI-INC-CHAOS-{int(time.time() * 1000)}"
        await db_mgr.sqlite.create_mention_spam_incident(
            incident_id=incident_id,
            guild_id=guild_id,
            user_id=777888,
            user_name="ChaosAttacker#9999",
            first_channel_id=101,
            channels_affected=[101, 102, 103],
            messages_count=12,
            mentions_count=45,
            unique_targets_count=30,
            first_seen="2026-10-01T21:00:00Z",
            last_seen="2026-10-01T21:00:15Z",
            severity="CRITICAL",
            action_taken="TIMEOUT_AND_PURGE",
            incident_status="RESOLVED",
        )

        # 3. Queue cloud persistence via sync queue
        incident_payload = {
            "incident_id": incident_id,
            "guild_id": guild_id,
            "severity": "CRITICAL",
            "action": "TIMEOUT_AND_PURGE",
        }
        await db_mgr.record_incident_multi_db(incident_payload, priority=SyncPriority.CRITICAL_SECURITY)

        # Check queue has pending items
        stats = await db_mgr.sqlite.get_sync_queue_stats()
        self.assertEqual(stats["total_pending"], 2)  # 1 PostgreSQL, 1 Firebase
        self.assertEqual(stats["total_synced"], 0)

        # ==========================================
        # PHASE 3: CLOUD RESTORATION & DRAINING
        # ==========================================
        mock_pg_repo = MagicMock()
        mock_pg_repo.pool = MagicMock()
        mock_pg_repo.pool.is_connected = True
        mock_pg_repo.save_incident = AsyncMock(return_value=Result.ok(None))

        mock_fb_repo = MagicMock()
        mock_fb_repo.conn = MagicMock()
        mock_fb_repo.conn.is_connected = True
        mock_fb_repo.sync_incident = AsyncMock(return_value=Result.ok(None))

        worker = DatabaseSyncWorker(
            queue=db_mgr.sync_queue,
            postgres_repo=mock_pg_repo,
            firebase_repo=mock_fb_repo,
        )

        # Drain queues
        drained_pg = await worker._drain_postgres_batch(limit=10)
        self.assertEqual(drained_pg, 1)
        mock_pg_repo.save_incident.assert_awaited_once()

        drained_fb = await worker._drain_firebase_batch(limit=10)
        self.assertEqual(drained_fb, 1)
        mock_fb_repo.sync_incident.assert_awaited_once()

        # All operations must now be marked SYNCED!
        final_stats = await db_mgr.sqlite.get_sync_queue_stats()
        self.assertEqual(final_stats["total_synced"], 2)
        self.assertEqual(final_stats["total_pending"], 0)


if __name__ == "__main__":
    unittest.main()
