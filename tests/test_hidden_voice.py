"""
Unit tests for the Personal Hidden Voice Channel System.
Tests configuration persistence, room tracking, invited member access,
grace period handling, and ownership transfer isolation.
"""

import unittest
import uuid
from pathlib import Path

from database.database import Database
from database.models import HiddenVoiceConfig, HiddenVoiceRoom


class TestHiddenVoice(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_path = Path(f"data/test_hv_{uuid.uuid4().hex[:8]}.db")
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

    async def test_hidden_voice_config_defaults(self):
        guild_id = 999001
        cfg = await self.db.get_hidden_voice_config(guild_id)
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.max_rooms_per_user, 1)
        self.assertEqual(cfg.max_users_per_room, 99)
        self.assertEqual(cfg.empty_grace_period, 60)
        self.assertTrue(cfg.allow_invited_members)
        self.assertTrue(cfg.allow_ownership_transfer)
        # CRITICAL PRIVACY REQUIREMENT: staff cannot view by default
        self.assertFalse(cfg.staff_can_view_hidden_rooms)
        self.assertEqual(cfg.room_name_format, "🔒・{username}-private")

    async def test_hidden_voice_config_update(self):
        guild_id = 999002
        await self.db.update_hidden_voice_config(
            guild_id,
            category_id=123456789,
            entry_channel_id=987654321,
            empty_grace_period=90,
            staff_can_view_hidden_rooms=False,
            room_name_format="🔒・{display_name}'s Sanctuary",
        )
        cfg = await self.db.get_hidden_voice_config(guild_id)
        self.assertEqual(cfg.category_id, 123456789)
        self.assertEqual(cfg.entry_channel_id, 987654321)
        self.assertEqual(cfg.empty_grace_period, 90)
        self.assertFalse(cfg.staff_can_view_hidden_rooms)
        self.assertEqual(cfg.room_name_format, "🔒・{display_name}'s Sanctuary")

    async def test_room_lifecycle_and_invites(self):
        guild_id = 999003
        ch_id = 11223344
        owner_id = 55667788

        # 1. Create room
        await self.db.create_hidden_voice_room(
            channel_id=ch_id,
            guild_id=guild_id,
            owner_id=owner_id,
            name="🔒・Kishore's Private Room",
            user_limit=5,
        )

        room = await self.db.get_hidden_voice_room(ch_id)
        self.assertIsNotNone(room)
        self.assertEqual(room.owner_id, owner_id)
        self.assertEqual(room.invited_members, [])
        self.assertEqual(room.user_limit, 5)
        self.assertTrue(room.is_hidden)
        self.assertFalse(room.is_locked)

        # 2. Invite member
        invited_user_id = 44332211
        await self.db.update_hidden_voice_room(
            ch_id,
            invited_members=[invited_user_id],
            is_locked=True,
        )
        updated = await self.db.get_hidden_voice_room(ch_id)
        self.assertIn(invited_user_id, updated.invited_members)
        self.assertTrue(updated.is_locked)

        # 3. Ownership transfer
        new_owner_id = 99887766
        await self.db.update_hidden_voice_room(
            ch_id,
            owner_id=new_owner_id,
            transferred_from=owner_id,
        )
        transferred = await self.db.get_hidden_voice_room(ch_id)
        self.assertEqual(transferred.owner_id, new_owner_id)
        self.assertEqual(transferred.transferred_from, owner_id)

        # 4. Grace period handling
        await self.db.update_hidden_voice_room(
            ch_id,
            grace_period_until="2026-10-01T00:00:00+00:00",
            room_status="cleanup_pending",
        )
        pending = await self.db.get_hidden_voice_room(ch_id)
        self.assertEqual(pending.room_status, "cleanup_pending")
        self.assertEqual(pending.grace_period_until, "2026-10-01T00:00:00+00:00")

        # 5. Delete room
        await self.db.delete_hidden_voice_room(ch_id)
        deleted = await self.db.get_hidden_voice_room(ch_id)
        self.assertIsNone(deleted)


if __name__ == "__main__":
    unittest.main()
