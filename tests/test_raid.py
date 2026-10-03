"""
Unit tests for the Raid Detection Engine and Security Brain.
"""

import asyncio
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from database.database import Database
from database.migrations import run_migrations
from utils.security_brain import RollingWindowTracker, SecurityBrain


import uuid

class TestRaidDetection(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_path = Path(f"data/test_raid_{uuid.uuid4().hex[:8]}.db")
        self.db = Database(self.db_path)
        await self.db.connect()

        self.mock_bot = MagicMock()
        self.mock_bot.db = self.db
        self.brain = SecurityBrain(self.mock_bot)

    async def asyncTearDown(self):
        await self.db.close()
        for ext in ["", "-wal", "-shm"]:
            f = Path(str(self.db_path) + ext)
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

    def test_rolling_window_tracker(self):
        tracker = RollingWindowTracker(max_seconds=60)
        now = time.monotonic()

        # Add 5 events across different past seconds
        tracker.joins.append(now - 70)  # Outside 60s window
        tracker.joins.append(now - 40)
        tracker.joins.append(now - 20)
        tracker.joins.append(now - 10)
        tracker.joins.append(now)

        tracker.prune(now)
        # The event at now-70 should be pruned
        self.assertEqual(len(tracker.joins), 4)

        # Count in 30s window
        count_30s = tracker.count_window(tracker.joins, now, 30.0)
        self.assertEqual(count_30s, 3)

    async def test_raid_incident_database_lifecycle(self):
        guild_id = 888001
        inc_id = "RAID-20260930-0001"

        # 1. Create raid incident
        await self.db.create_raid_incident(guild_id, inc_id, "HIGH", 78)
        active = await self.db.get_active_raid_incident(guild_id)
        self.assertIsNotNone(active)
        self.assertEqual(active.incident_id, inc_id)
        self.assertEqual(active.risk_level, "HIGH")
        self.assertEqual(active.current_score, 78)

        # 2. Update score to peak 92
        await self.db.update_raid_incident_score(inc_id, 92, "CRITICAL")
        updated = await self.db.get_active_raid_incident(guild_id)
        self.assertEqual(updated.current_score, 92)
        self.assertEqual(updated.maximum_score, 92)
        self.assertEqual(updated.risk_level, "CRITICAL")

        # 3. Resolve incident
        await self.db.resolve_raid_incident(inc_id, resolved_by=123)
        resolved = await self.db.get_active_raid_incident(guild_id)
        self.assertIsNone(resolved)

        all_incidents = await self.db.get_raid_incidents(guild_id)
        self.assertEqual(len(all_incidents), 1)
        self.assertEqual(all_incidents[0].status, "RESOLVED")

    async def test_raid_risk_evaluation(self):
        guild_id = 888002
        mock_guild = MagicMock()
        mock_guild.id = guild_id

        # Insert default raid config
        cfg = await self.db.get_raid_config(guild_id)
        self.assertTrue(cfg.enabled)

        # 1. Normal state: 0 events -> Score 0, NORMAL
        score, level, reasons = await self.brain.evaluate_raid_risk(mock_guild)
        self.assertEqual(score, 0)
        self.assertEqual(level, "NORMAL")
        self.assertEqual(len(reasons), 0)

        # 2. Simulate rapid joins exceeding threshold
        tracker = self.brain.get_tracker(guild_id)
        now = time.monotonic()
        for _ in range(12):
            tracker.joins.append(now)
            tracker.new_accounts.append(now)

        score, level, reasons = await self.brain.evaluate_raid_risk(mock_guild)
        self.assertGreaterEqual(score, 50)
        self.assertIn(level, ("SUSPICIOUS", "HIGH", "CRITICAL"))
        self.assertTrue(any("Join spike" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
