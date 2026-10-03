"""
Unit tests for the Smart Verification System.
"""

import unittest
import uuid
from pathlib import Path

from database.database import Database


class TestVerification(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_path = Path(f"data/test_verif_{uuid.uuid4().hex[:8]}.db")
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

    async def test_verification_config_lifecycle(self):
        guild_id = 666001
        cfg = await self.db.get_verification_config(guild_id)
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.min_account_age_hours, 0)

        # Update
        await self.db.update_verification_config(
            guild_id,
            enabled=True,
            role_id=987654,
            channel_id=123456,
            min_account_age_hours=24,
        )
        updated = await self.db.get_verification_config(guild_id)
        self.assertTrue(updated.enabled)
        self.assertEqual(updated.role_id, 987654)
        self.assertEqual(updated.channel_id, 123456)
        self.assertEqual(updated.min_account_age_hours, 24)

    async def test_member_verification_records(self):
        guild_id = 666002
        user_id = 555111

        self.assertFalse(await self.db.is_user_verified(guild_id, user_id))

        await self.db.record_verification(guild_id, user_id, account_age_hours=48.5)
        self.assertTrue(await self.db.is_user_verified(guild_id, user_id))


if __name__ == "__main__":
    unittest.main()
