"""
Unit and integration tests for THOR APEX Advanced Invite Tracker.
Tests invite link attribution, cache synchronization, single-use deletion,
vanity URL attribution, fake account age fraud detection, member departures,
reward milestones, and database persistence.
"""

from __future__ import annotations

import asyncio
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from database.database import Database
from database.models import InviteTrackerConfig, MemberInvite, InviterStats
from services.invite_tracker_service import InviteTrackerService


class TestInviteTracker(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # In-memory test database with full migrations
        self.db = Database(":memory:")
        await self.db.connect()

        self.bot = MagicMock()
        self.bot.db = self.db

        self.service = InviteTrackerService(self.bot)
        self.guild_id = 9988776655

        # Create mock guild
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = self.guild_id
        self.guild.name = "THOR APEX TEST GUILD"
        self.guild.features = ["COMMUNITY", "VANITY_URL"]
        self.guild.me = MagicMock(spec=discord.Member)
        self.guild.me.guild_permissions = discord.Permissions(manage_guild=True, manage_roles=True)
        self.guild.me.top_role = MagicMock()
        self.guild.me.top_role.position = 100
        self.guild.owner_id = 111222333

        # Default bot mock
        self.bot.get_guild.return_value = self.guild

    async def asyncTearDown(self):
        if self.db._db:
            await self.db._db.close()

    async def test_migration_v50_tables_exist(self):
        """Verify Migration v50 creates all required invite tables and indexes."""
        async with self.db._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cursor:
            rows = await cursor.fetchall()
            table_names = [r["name"] for r in rows]

        self.assertIn("invite_tracker_config", table_names)
        self.assertIn("member_invites", table_names)
        self.assertIn("inviter_stats", table_names)
        self.assertIn("invite_rewards", table_names)

    async def test_sync_guild_populates_cache(self):
        """Verify syncing guild populates invite and vanity caches."""
        mock_inv1 = MagicMock(spec=discord.Invite)
        mock_inv1.code = "apex-join"
        mock_inv1.uses = 5
        mock_inv1.inviter = MagicMock(id=12345)

        mock_inv2 = MagicMock(spec=discord.Invite)
        mock_inv2.code = "gaming-squad"
        mock_inv2.uses = 12
        mock_inv2.inviter = MagicMock(id=67890)

        self.guild.invites = AsyncMock(return_value=[mock_inv1, mock_inv2])

        mock_vanity = MagicMock(spec=discord.Invite)
        mock_vanity.uses = 40
        self.guild.vanity_invite = AsyncMock(return_value=mock_vanity)

        success = await self.service.sync_guild(self.guild)
        self.assertTrue(success)

        cached = self.service._invite_cache.get(self.guild_id, {})
        self.assertEqual(cached.get("apex-join"), 5)
        self.assertEqual(cached.get("gaming-squad"), 12)
        self.assertEqual(self.service._vanity_cache.get(self.guild_id), 40)

    async def test_member_join_tracked_regular_invite(self):
        """Verify regular member join attributes correctly and increments inviter stats."""
        # Initial state: invite code 'apex-join' with 5 uses
        self.service._invite_cache[self.guild_id] = {"apex-join": 5}
        self.service._inviter_cache[self.guild_id] = {"apex-join": 12345}

        # On join, Discord returns uses = 6
        mock_inv = MagicMock(spec=discord.Invite)
        mock_inv.code = "apex-join"
        mock_inv.uses = 6
        mock_inv.inviter = MagicMock(id=12345)
        self.guild.invites = AsyncMock(return_value=[mock_inv])

        # New joining member (account age 30 days > threshold)
        new_member = MagicMock(spec=discord.Member)
        new_member.id = 999001
        new_member.guild = self.guild
        new_member.name = "TestJoinedUser"
        new_member.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
        new_member.display_avatar = None

        inviter_id, code, classification = await self.service.process_member_join(new_member)

        self.assertEqual(inviter_id, 12345)
        self.assertEqual(code, "apex-join")
        self.assertEqual(classification, "regular")

        # Verify DB records
        stats = await self.db.get_inviter_stats(self.guild_id, 12345)
        self.assertEqual(stats.regular_invites, 1)
        self.assertEqual(stats.effective_invites, 1)

        record = await self.db.get_member_invite(self.guild_id, 999001)
        self.assertIsNotNone(record)
        self.assertEqual(record.inviter_id, 12345)
        self.assertEqual(record.classification, "regular")

    async def test_fake_invite_detection_young_account(self):
        """Verify accounts younger than threshold are classified as 'fake' and not given regular credit."""
        self.service._invite_cache[self.guild_id] = {"apex-join": 5}
        self.service._inviter_cache[self.guild_id] = {"apex-join": 12345}

        mock_inv = MagicMock(spec=discord.Invite)
        mock_inv.code = "apex-join"
        mock_inv.uses = 6
        mock_inv.inviter = MagicMock(id=12345)
        self.guild.invites = AsyncMock(return_value=[mock_inv])

        # Account created only 1 day ago (default threshold = 3 days)
        young_member = MagicMock(spec=discord.Member)
        young_member.id = 999002
        young_member.guild = self.guild
        young_member.name = "SusBotUser"
        young_member.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        young_member.display_avatar = None

        inviter_id, code, classification = await self.service.process_member_join(young_member)

        self.assertEqual(classification, "fake")

        stats = await self.db.get_inviter_stats(self.guild_id, 12345)
        self.assertEqual(stats.fake_invites, 1)
        self.assertEqual(stats.regular_invites, 0)
        self.assertEqual(stats.effective_invites, 0)

    async def test_rejoin_detection(self):
        """Verify rejoining member is classified as 'rejoin' and does not award double invite credit."""
        # Member already in DB from prior join
        await self.db.record_member_invite(
            guild_id=self.guild_id,
            member_id=999003,
            inviter_id=12345,
            invite_code="apex-join",
            classification="regular",
        )

        self.service._invite_cache[self.guild_id] = {"apex-join": 10}
        self.service._inviter_cache[self.guild_id] = {"apex-join": 12345}

        mock_inv = MagicMock(spec=discord.Invite)
        mock_inv.code = "apex-join"
        mock_inv.uses = 11
        mock_inv.inviter = MagicMock(id=12345)
        self.guild.invites = AsyncMock(return_value=[mock_inv])

        rejoin_member = MagicMock(spec=discord.Member)
        rejoin_member.id = 999003
        rejoin_member.guild = self.guild
        rejoin_member.name = "RejoiningUser"
        rejoin_member.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=50)
        rejoin_member.display_avatar = None

        inviter_id, code, classification = await self.service.process_member_join(rejoin_member)

        self.assertEqual(classification, "rejoin")
        stats = await self.db.get_inviter_stats(self.guild_id, 12345)
        # Rejoin does not increment regular invites again
        self.assertEqual(stats.regular_invites, 0)

    async def test_vanity_url_detection(self):
        """Verify join through server vanity URL is detected and classified as 'vanity'."""
        self.service._invite_cache[self.guild_id] = {"apex-join": 5}
        self.service._vanity_cache[self.guild_id] = 50

        # Regular invites unchanged
        mock_inv = MagicMock(spec=discord.Invite)
        mock_inv.code = "apex-join"
        mock_inv.uses = 5
        self.guild.invites = AsyncMock(return_value=[mock_inv])

        # Vanity URL uses incremented 50 -> 51
        mock_vanity = MagicMock(spec=discord.Invite)
        mock_vanity.code = "thor-apex"
        mock_vanity.uses = 51
        self.guild.vanity_invite = AsyncMock(return_value=mock_vanity)

        vanity_member = MagicMock(spec=discord.Member)
        vanity_member.id = 999004
        vanity_member.guild = self.guild
        vanity_member.name = "VanityJoiner"
        vanity_member.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=40)
        vanity_member.display_avatar = None

        inviter_id, code, classification = await self.service.process_member_join(vanity_member)

        self.assertIsNone(inviter_id)
        self.assertEqual(code, "thor-apex")
        self.assertEqual(classification, "vanity")

    async def test_single_use_invite_deletion_on_use(self):
        """Verify single-use invite deleted upon use is detected correctly."""
        # Invite was in cache with 0 uses
        self.service._invite_cache[self.guild_id] = {"single-use-code": 0}
        self.service._inviter_cache[self.guild_id] = {"single-use-code": 556677}

        # After join, 'single-use-code' no longer exists in live invites list
        self.guild.invites = AsyncMock(return_value=[])

        single_member = MagicMock(spec=discord.Member)
        single_member.id = 999005
        single_member.guild = self.guild
        single_member.name = "SingleUseUser"
        single_member.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=20)
        single_member.display_avatar = None

        inviter_id, code, classification = await self.service.process_member_join(single_member)

        self.assertEqual(inviter_id, 556677)
        self.assertEqual(code, "single-use-code")
        self.assertEqual(classification, "regular")

    async def test_member_leave_deduction(self):
        """Verify member departure marks left_at and increments left_invites on inviter."""
        # Record join
        await self.db.record_member_invite(
            guild_id=self.guild_id,
            member_id=999006,
            inviter_id=12345,
            invite_code="apex-join",
            classification="regular",
        )
        await self.db.increment_inviter_stats(self.guild_id, 12345, regular_delta=1)

        departing_member = MagicMock(spec=discord.Member)
        departing_member.id = 999006
        departing_member.guild = self.guild
        departing_member.name = "LeaverUser"

        inviter_id = await self.service.process_member_remove(departing_member)
        self.assertEqual(inviter_id, 12345)

        stats = await self.db.get_inviter_stats(self.guild_id, 12345)
        self.assertEqual(stats.left_invites, 1)
        self.assertEqual(stats.effective_invites, 0)

        record = await self.db.get_member_invite(self.guild_id, 999006)
        self.assertIsNotNone(record.left_at)

    async def test_missing_manage_server_permission_handles_gracefully(self):
        """Verify bot lacking manage_guild marks attribution honestly as 'unknown'."""
        self.guild.me.guild_permissions = discord.Permissions(manage_guild=False)

        new_member = MagicMock(spec=discord.Member)
        new_member.id = 999007
        new_member.guild = self.guild
        new_member.name = "NoPermsUser"
        new_member.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=10)

        inviter_id, code, classification = await self.service.process_member_join(new_member)

        self.assertIsNone(inviter_id)
        self.assertIsNone(code)
        self.assertEqual(classification, "unknown")

    async def test_invite_rewards_milestone_assignment(self):
        """Verify reaching invite milestone automatically assigns configured role."""
        # Enable rewards
        cfg = await self.db.get_invite_tracker_config(self.guild_id)
        cfg.rewards_enabled = True
        await self.db.upsert_invite_tracker_config(cfg)

        # Configure milestone: 3 invites -> role 888111
        await self.db.add_invite_reward(self.guild_id, required_invites=3, role_id=888111)

        # Mock inviter in guild
        inviter_member = MagicMock(spec=discord.Member)
        inviter_member.id = 777888
        inviter_member.roles = []
        inviter_member.add_roles = AsyncMock()
        inviter_member.remove_roles = AsyncMock()

        reward_role = MagicMock(spec=discord.Role)
        reward_role.id = 888111
        reward_role.name = "Apex Recruiter"
        reward_role.position = 50  # Lower than bot top role (100)

        self.guild.get_member.return_value = inviter_member
        self.guild.get_role.return_value = reward_role

        # Give inviter 3 invites
        await self.db.increment_inviter_stats(self.guild_id, 777888, regular_delta=3)

        await self.service.reconcile_member_rewards(self.guild, 777888)

        inviter_member.add_roles.assert_awaited_once_with(
            reward_role, reason="THOR APEX: Reached 3 invites milestone"
        )

    async def test_invites_reset_clears_metrics(self):
        """Verify resetting stats clears counts and marks records cleared."""
        await self.db.increment_inviter_stats(self.guild_id, 12345, regular_delta=10, fake_delta=2)
        await self.db.record_member_invite(self.guild_id, 999010, 12345, "code1")

        await self.db.reset_inviter_stats(self.guild_id, 12345)

        stats = await self.db.get_inviter_stats(self.guild_id, 12345)
        self.assertEqual(stats.regular_invites, 0)
        self.assertEqual(stats.fake_invites, 0)
        self.assertEqual(stats.effective_invites, 0)

        record = await self.db.get_member_invite(self.guild_id, 999010)
        self.assertTrue(record.is_cleared)

    async def test_reclassify_member_invite_adjusts_stats(self):
        """Verify moderator reclassifying an invite from fake to regular updates inviter stats atomically."""
        await self.db.record_member_invite(
            self.guild_id, 999020, 12345, "code-x", classification="fake"
        )
        await self.db.increment_inviter_stats(self.guild_id, 12345, fake_delta=1)

        # Moderator reclassifies
        reclassified = await self.db.reclassify_member_invite(
            self.guild_id, 999020, new_classification="regular", notes="Verified legitimate human"
        )
        self.assertEqual(reclassified.classification, "regular")

        stats = await self.db.get_inviter_stats(self.guild_id, 12345)
        self.assertEqual(stats.regular_invites, 1)
        self.assertEqual(stats.fake_invites, 0)


if __name__ == "__main__":
    unittest.main()
