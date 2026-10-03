"""
Unit tests for the Suggestion and Atomic Voting System.
"""

import asyncio
import os
import unittest
from pathlib import Path

from database.database import Database
from database.migrations import run_migrations


import uuid

class TestSuggestionsSystem(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_path = Path(f"data/test_suggestions_{uuid.uuid4().hex[:8]}.db")
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

    async def test_suggestion_crud(self):
        guild_id = 999001
        author_id = 12345

        # 1. Create suggestion
        s_id = await self.db.create_suggestion(
            guild_id=guild_id,
            channel_id=111,
            message_id=222,
            author_id=author_id,
            content="Add a new game night voice channel",
        )
        self.assertGreater(s_id, 0)

        # 2. Retrieve suggestion
        record = await self.db.get_suggestion(s_id)
        self.assertIsNotNone(record)
        self.assertEqual(record.content, "Add a new game night voice channel")
        self.assertEqual(record.status, "pending")
        self.assertEqual(record.upvotes, 0)
        self.assertEqual(record.downvotes, 0)

        # 3. Update status to approved
        await self.db.update_suggestion_status(s_id, "approved", reviewer_id=999)
        updated = await self.db.get_suggestion(s_id)
        self.assertEqual(updated.status, "approved")
        self.assertEqual(updated.reviewed_by, 999)

        # 4. Update status to rejected with reason
        await self.db.update_suggestion_status(s_id, "rejected", reason="Not suitable right now", reviewer_id=999)
        rejected = await self.db.get_suggestion(s_id)
        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(rejected.reason, "Not suitable right now")

    async def test_atomic_voting_lifecycle(self):
        guild_id = 999002
        s_id = await self.db.create_suggestion(
            guild_id=guild_id,
            channel_id=111,
            message_id=222,
            author_id=101,
            content="Persistent Suggestions Test",
        )

        user_a = 501
        user_b = 502

        # User A upvotes
        up, down, action = await self.db.cast_vote(guild_id, s_id, user_a, "upvote")
        self.assertEqual(action, "added")
        self.assertEqual(up, 1)
        self.assertEqual(down, 0)

        # User B downvotes
        up, down, action = await self.db.cast_vote(guild_id, s_id, user_b, "downvote")
        self.assertEqual(action, "added")
        self.assertEqual(up, 1)
        self.assertEqual(down, 1)

        # User A changes vote from upvote to downvote
        up, down, action = await self.db.cast_vote(guild_id, s_id, user_a, "downvote")
        self.assertEqual(action, "switched")
        self.assertEqual(up, 0)
        self.assertEqual(down, 2)

        # User B toggles downvote off (clicks same button again)
        up, down, action = await self.db.cast_vote(guild_id, s_id, user_b, "downvote")
        self.assertEqual(action, "removed")
        self.assertEqual(up, 0)
        self.assertEqual(down, 1)

    async def test_suggestion_config_persistence(self):
        guild_id = 999003
        cfg = await self.db.get_suggestion_config(guild_id)
        self.assertEqual(cfg.cooldown_seconds, 60)
        self.assertTrue(cfg.voting_enabled)

        await self.db.update_suggestion_config(
            guild_id,
            suggestion_channel_id=555666,
            cooldown_seconds=120,
            voting_enabled=False,
        )
        updated = await self.db.get_suggestion_config(guild_id)
        self.assertEqual(updated.suggestion_channel_id, 555666)
        self.assertEqual(updated.cooldown_seconds, 120)
        self.assertFalse(updated.voting_enabled)


if __name__ == "__main__":
    unittest.main()
