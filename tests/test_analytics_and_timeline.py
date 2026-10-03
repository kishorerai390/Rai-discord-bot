"""
Unit tests for Threat Timeline and Security Analytics.
"""

import unittest
import uuid
from pathlib import Path

from database.database import Database


class TestAnalyticsAndTimeline(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_path = Path(f"data/test_atl_{uuid.uuid4().hex[:8]}.db")
        self.db = Database(self.db_path)
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        for ext in ["", "-wal", "-shm"]:
            f = Path(str(self.db_path) + ext)
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

    async def test_threat_timeline_events(self):
        guild_id = 444001
        inc_id = "TEST-INCIDENT-001"

        await self.db.record_threat_timeline_event(
            incident_id=inc_id,
            guild_id=guild_id,
            module="Anti-Raid",
            event_type="JOIN_SPIKE",
            description="15 joins in 60s",
            risk_score=75,
            severity="high",
        )
        await self.db.record_threat_timeline_event(
            incident_id=inc_id,
            guild_id=guild_id,
            module="Anti-Spam",
            event_type="MESSAGE_BURST",
            description="Repeated duplicate spam detected",
            risk_score=85,
            severity="high",
        )

        timeline = await self.db.get_threat_timeline(inc_id)
        self.assertEqual(len(timeline), 2)
        self.assertEqual(timeline[0].module, "Anti-Raid")
        self.assertEqual(timeline[1].module, "Anti-Spam")
        self.assertEqual(timeline[1].risk_score, 85)

    async def test_analytics_aggregation(self):
        guild_id = 444002

        # Create sample data
        await self.db.create_raid_incident(guild_id, "RAID-2026-01", "HIGH", 82)
        await self.db.record_verification(guild_id, 12345, 12.0)

        stats = await self.db.get_analytics(guild_id, days=7)
        self.assertEqual(stats["raid_incidents"], 1)
        self.assertEqual(stats["peak_raid_score"], 82)
        self.assertEqual(stats["verifications"], 1)


if __name__ == "__main__":
    unittest.main()
