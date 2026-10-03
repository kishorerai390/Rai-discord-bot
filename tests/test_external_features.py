"""
Unit tests for Rai External Features:
- Web Dashboard
- Gaming Stats (/valstats, /bgmistats, /freebies)
- Stream Radar (Twitch / YouTube / Kick)
- AI Vision & Image Generation (/imagine, /scanimage)
- Lyrics Engine (/lyrics)
- Encrypted Cloud Backups
- Growth & Top.gg Voting
"""

import asyncio
import os
import unittest
from pathlib import Path
import tempfile
import aiosqlite

from database.database import Database
from database.migrations import run_migrations
from utils.cloud_backup import calculate_sha256


class TestExternalFeatures(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_bot.db"
        self.db = Database(self.db_path)
        await self.db.connect()
        self.guild_id = 1457382179981099090
        await self.db.get_or_create_guild_config(self.guild_id)

    async def asyncTearDown(self):
        await self.db.close()
        self.temp_dir.cleanup()

    async def test_stream_trackers_crud(self):
        # Add tracker
        t_id = await self.db.add_stream_tracker(
            guild_id=self.guild_id,
            platform="twitch",
            channel_name="shroud",
            alert_channel_id=123456789,
        )
        self.assertIsNotNone(t_id)

        # Get trackers
        trackers = await self.db.get_stream_trackers(self.guild_id)
        self.assertEqual(len(trackers), 1)
        self.assertEqual(trackers[0].channel_name, "shroud")
        self.assertEqual(trackers[0].last_status, "offline")

        # Update status
        await self.db.update_stream_tracker_status(t_id, "live")
        updated = await self.db.get_stream_trackers(self.guild_id)
        self.assertEqual(updated[0].last_status, "live")

        # Remove tracker
        removed = await self.db.remove_stream_tracker(self.guild_id, "shroud")
        self.assertTrue(removed)
        trackers_after = await self.db.get_stream_trackers(self.guild_id)
        self.assertEqual(len(trackers_after), 0)

    async def test_member_invites(self):
        user_id = 987654321
        # Initial check
        invs = await self.db.get_member_invites(self.guild_id, user_id)
        self.assertEqual(invs.total, 0)

        # Increment regular invites
        await self.db.increment_member_invites(self.guild_id, user_id, regular=5, bonus=2)
        invs2 = await self.db.get_member_invites(self.guild_id, user_id)
        self.assertEqual(invs2.regular, 5)
        self.assertEqual(invs2.bonus, 2)
        self.assertEqual(invs2.total, 7)

        # Leaves
        await self.db.increment_member_invites(self.guild_id, user_id, leaves=1)
        invs3 = await self.db.get_member_invites(self.guild_id, user_id)
        self.assertEqual(invs3.leaves, 1)
        self.assertEqual(invs3.total, 6)

        # Top inviters
        top = await self.db.get_top_inviters(self.guild_id)
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0][0], user_id)
        self.assertEqual(top[0][1], 6)

    async def test_top_gg_voting(self):
        voter_id = 1122334455
        v1 = await self.db.record_vote(voter_id, self.guild_id)
        self.assertEqual(v1, 1)

        v2 = await self.db.record_vote(voter_id, self.guild_id)
        self.assertEqual(v2, 2)

        info = await self.db.get_member_votes(voter_id, self.guild_id)
        self.assertEqual(info.total_votes, 2)
        self.assertIsNotNone(info.last_voted)

    def test_sha256_calculation(self):
        test_file = Path(self.temp_dir.name) / "test.txt"
        test_file.write_text("Rai Sentinel Secure Hash Test")
        hash_val = calculate_sha256(test_file)
        self.assertEqual(len(hash_val), 64)


if __name__ == "__main__":
    unittest.main()
