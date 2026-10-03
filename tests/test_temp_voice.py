"""
Unit tests for the Join-to-Create Temporary Voice Channels.
"""

import unittest
import uuid
from pathlib import Path

from database.database import Database


class TestTempVoice(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_path = Path(f"data/test_tv_{uuid.uuid4().hex[:8]}.db")
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

    async def test_temp_voice_config_lifecycle(self):
        guild_id = 555001
        cfg = await self.db.get_temp_voice_config(guild_id)
        self.assertFalse(cfg.enabled)

        await self.db.update_temp_voice_config(
            guild_id,
            enabled=True,
            hub_channel_id=111222,
            category_id=333444,
            default_user_limit=5,
        )
        updated = await self.db.get_temp_voice_config(guild_id)
        self.assertTrue(updated.enabled)
        self.assertEqual(updated.hub_channel_id, 111222)
        self.assertEqual(updated.category_id, 333444)
        self.assertEqual(updated.default_user_limit, 5)

    async def test_temp_voice_channel_tracking(self):
        guild_id = 555002
        ch_id = 777888
        owner_id = 999111

        # Create
        await self.db.create_temp_voice_channel(ch_id, guild_id, owner_id)
        record = await self.db.get_temp_voice_channel(ch_id)
        self.assertIsNotNone(record)
        self.assertEqual(record.owner_id, owner_id)

        # Delete
        await self.db.delete_temp_voice_channel(ch_id)
        deleted = await self.db.get_temp_voice_channel(ch_id)
        self.assertIsNone(deleted)


if __name__ == "__main__":
    unittest.main()
