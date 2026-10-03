"""
Automated unit and integration tests for SQLite Database layer.
"""

import asyncio
import os
import unittest
from pathlib import Path
import aiosqlite

from database.database import Database
from database.models import SecurityIncident

TEST_DB_PATH = Path(__file__).resolve().parent / "test_bot.db"


class TestDatabase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        for p in [TEST_DB_PATH, Path(str(TEST_DB_PATH) + "-wal"), Path(str(TEST_DB_PATH) + "-shm")]:
            try:
                if p.exists():
                    os.remove(p)
            except OSError:
                pass
        self.db = Database(TEST_DB_PATH)
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        await asyncio.sleep(0.05)
        for p in [TEST_DB_PATH, Path(str(TEST_DB_PATH) + "-wal"), Path(str(TEST_DB_PATH) + "-shm")]:
            try:
                if p.exists():
                    os.remove(p)
            except OSError:
                pass

    async def test_initialization_and_integrity(self):
        self.assertTrue(self.db.is_connected)
        ok, errors = await self.db.check_integrity()
        self.assertTrue(ok, f"Integrity check failed: {errors}")

    async def test_guild_config_and_defaults(self):
        guild_id = 123456789
        cfg = await self.db.get_or_create_guild_config(guild_id)
        self.assertEqual(cfg.guild_id, guild_id)
        self.assertTrue(cfg.security_enabled)
        self.assertFalse(cfg.emergency_stop)

        # Update
        await self.db.update_guild_config(guild_id, security_enabled=False)
        cfg_after = await self.db.get_or_create_guild_config(guild_id)
        self.assertFalse(cfg_after.security_enabled)

    async def test_whitelist(self):
        guild_id = 9999
        user_id = 1111
        role_id = 2222

        # Add user
        added = await self.db.add_whitelist(guild_id, user_id, "user", 5555)
        self.assertTrue(added)
        self.assertTrue(await self.db.is_whitelisted(guild_id, user_id, []))
        self.assertFalse(await self.db.is_whitelisted(guild_id, 999999, []))

        # Add role
        await self.db.add_whitelist(guild_id, role_id, "role", 5555)
        self.assertTrue(await self.db.is_whitelisted(guild_id, 999999, [role_id]))

        # Remove
        removed = await self.db.remove_whitelist(guild_id, user_id, "user")
        self.assertTrue(removed)
        self.assertFalse(await self.db.is_whitelisted(guild_id, user_id, []))

    async def test_security_incidents(self):
        guild_id = 8888
        incident = SecurityIncident(
            event_id="INC001",
            guild_id=guild_id,
            timestamp="2026-09-30T10:00:00",
            event_type="CHANNEL_DELETE",
            executor_id=4444,
            executor_name="BadActor",
            target_id=7777,
            target_name="#announcements",
            action="channel_delete",
            detected_count=6,
            threshold=5,
            audit_log_id=98765,
            reason="Mass channel deletion",
            automated_action="Banned BadActor",
            result="Success",
            severity="high",
            audit_verified=True,
        )
        await self.db.record_security_incident(incident)

        incidents = await self.db.get_security_incidents(guild_id, limit=5)
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].event_id, "INC001")
        self.assertEqual(incidents[0].severity, "high")
        self.assertTrue(incidents[0].audit_verified)

    async def test_security_state_and_emergency_stop(self):
        guild_id = 7777
        await self.db.set_emergency_stop(guild_id, True, 123)
        state = await self.db.get_security_state(guild_id)
        self.assertTrue(state.emergency_stop)

        await self.db.set_emergency_stop(guild_id, False, 123)
        state_after = await self.db.get_security_state(guild_id)
        self.assertFalse(state_after.emergency_stop)

    async def test_violation_history(self):
        guild_id = 6666
        executor_id = 3333
        event_type = "ROLE_DELETE"

        count1 = await self.db.record_violation(guild_id, executor_id, event_type)
        self.assertEqual(count1, 1)

        count2 = await self.db.record_violation(guild_id, executor_id, event_type)
        self.assertEqual(count2, 2)

        stored_count = await self.db.get_violation_count(guild_id, executor_id, event_type)
        self.assertEqual(stored_count, 2)

    async def test_moderation_warnings(self):
        guild_id = 5555
        user_id = 2222
        mod_id = 1111

        warn_id = await self.db.add_warning(guild_id, user_id, mod_id, "Spamming links")
        self.assertGreater(warn_id, 0)

        warns = await self.db.get_warnings(guild_id, user_id)
        self.assertEqual(len(warns), 1)
        self.assertEqual(warns[0].reason, "Spamming links")

        deleted = await self.db.delete_warning(warn_id, guild_id)
        self.assertTrue(deleted)
        self.assertEqual(len(await self.db.get_warnings(guild_id, user_id)), 0)

    async def test_tickets(self):
        guild_id = 4444
        channel_id = 9898
        creator_id = 1212

        tid = await self.db.create_ticket(guild_id, channel_id, creator_id)
        self.assertGreater(tid, 0)

        record = await self.db.get_ticket_by_channel(channel_id)
        self.assertIsNotNone(record)
        self.assertEqual(record.status, "open")

        closed = await self.db.close_ticket(channel_id, 9999)
        self.assertTrue(closed)

        record_closed = await self.db.get_ticket_by_channel(channel_id)
        self.assertEqual(record_closed.status, "closed")


if __name__ == "__main__":
    unittest.main()
