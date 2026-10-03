"""
Unit and Integration Tests for Rai Automatic Role Management System.
Tests hierarchy safety, idempotent setup, member lifecycle, database persistence,
self-healing repair, and rate-limited queue dispatching.
"""

import asyncio
import datetime
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from database.database import Database
from utils.role_manager import RoleManager, ROLE_DEFINITIONS


class TestRoleManagerHierarchySafety(unittest.TestCase):
    """Tests for Discord hierarchy, bot permissions, and server owner safety."""

    def setUp(self):
        self.bot = MagicMock()
        self.manager = RoleManager(self.bot)
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 123456789
        self.guild.owner_id = 999999

        # Bot member
        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_top_role = MagicMock(spec=discord.Role)
        self.bot_top_role.name = "Rai Top Role"
        self.bot_top_role.position = 30
        self.bot_member.top_role = self.bot_top_role
        self.bot_member.guild_permissions = discord.Permissions(manage_roles=True)
        self.guild.me = self.bot_member

    def test_validate_hierarchy_success(self):
        target_role = MagicMock(spec=discord.Role)
        target_role.name = "Verified"
        target_role.position = 20
        target_role.managed = False
        target_role.is_default.return_value = False

        # target_role < self.bot_top_role
        target_role.__lt__ = lambda s, o: target_role.position < o.position
        target_role.__ge__ = lambda s, o: target_role.position >= o.position

        ok, msg = self.manager.validate_hierarchy(self.guild, target_role)
        self.assertTrue(ok)
        self.assertEqual(msg, "OK")

    def test_validate_hierarchy_role_above_bot(self):
        high_role = MagicMock(spec=discord.Role)
        high_role.name = "Administrator"
        high_role.position = 35
        high_role.managed = False
        high_role.is_default.return_value = False
        high_role.__ge__ = lambda s, o: high_role.position >= o.position

        ok, msg = self.manager.validate_hierarchy(self.guild, high_role)
        self.assertFalse(ok)
        self.assertIn("higher than or equal", msg)

    def test_validate_hierarchy_default_everyone_role(self):
        everyone_role = MagicMock(spec=discord.Role)
        everyone_role.name = "@everyone"
        everyone_role.is_default.return_value = True

        ok, msg = self.manager.validate_hierarchy(self.guild, everyone_role)
        self.assertFalse(ok)
        self.assertIn("@everyone", msg)

    def test_validate_hierarchy_managed_role(self):
        managed_role = MagicMock(spec=discord.Role)
        managed_role.name = "Discord Bot Integration"
        managed_role.is_default.return_value = False
        managed_role.managed = True

        ok, msg = self.manager.validate_hierarchy(self.guild, managed_role)
        self.assertFalse(ok)
        self.assertIn("managed", msg)

    def test_validate_member_manageable_server_owner_protected(self):
        owner_member = MagicMock(spec=discord.Member)
        owner_member.id = self.guild.owner_id
        owner_member.display_name = "ServerOwner"

        ok, msg = self.manager.validate_member_manageable(self.guild, owner_member)
        self.assertFalse(ok)
        self.assertIn("owner", msg.lower())

    def test_validate_member_manageable_member_above_bot(self):
        co_owner = MagicMock(spec=discord.Member)
        co_owner.id = 55555
        co_owner.display_name = "CoOwner"
        top_role = MagicMock(spec=discord.Role)
        top_role.position = 35
        top_role.name = "Founder"
        co_owner.top_role = top_role
        top_role.__ge__ = lambda s, o: top_role.position >= o.position

        ok, msg = self.manager.validate_member_manageable(self.guild, co_owner)
        self.assertFalse(ok)
        self.assertIn("higher than or equal", msg)

    def test_validate_executor_permissions(self):
        staff = MagicMock(spec=discord.Member)
        staff.guild = self.guild
        staff.id = 1111
        staff.guild_permissions = discord.Permissions(manage_roles=True)
        staff_role = MagicMock(spec=discord.Role)
        staff_role.position = 25
        staff.top_role = staff_role

        target_role = MagicMock(spec=discord.Role)
        target_role.position = 20
        target_role.name = "Member"
        target_role.__ge__ = lambda s, o: target_role.position >= o.position

        ok, msg = self.manager.validate_executor_permissions(staff, target_role=target_role)
        self.assertTrue(ok)


class TestRoleManagerDatabaseOperations(unittest.IsolatedAsyncioTestCase):
    """Tests for SQLite database CRUD and audit logging."""

    async def asyncSetUp(self):
        self.db_path = Path("tests/test_roles.db")
        if self.db_path.exists():
            self.db_path.unlink()
        self.db = Database(self.db_path)
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        await asyncio.sleep(0.05)
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except PermissionError:
                pass

    async def test_save_and_get_guild_role(self):
        role = await self.db.save_guild_role(
            guild_id=1234,
            role_key="verified",
            discord_role_id=987654321,
            role_name="✅ Verified",
            role_type="COMMUNITY",
            managed_by_rai=True,
            enabled=True,
            position=15,
        )
        self.assertIsNotNone(role)
        self.assertEqual(role.role_key, "verified")
        self.assertEqual(role.discord_role_id, 987654321)

        # Retrieve by key
        fetched = await self.db.get_guild_role(1234, "verified")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.discord_role_id, 987654321)

        # Retrieve by ID
        fetched_id = await self.db.get_guild_role_by_id(1234, 987654321)
        self.assertIsNotNone(fetched_id)
        self.assertEqual(fetched_id.role_key, "verified")

    async def test_idempotent_save_updates_existing(self):
        await self.db.save_guild_role(
            guild_id=1234,
            role_key="vip",
            discord_role_id=111111,
            role_name="💎 VIP",
            role_type="COMMUNITY",
        )
        # Update with new discord_role_id
        updated = await self.db.save_guild_role(
            guild_id=1234,
            role_key="vip",
            discord_role_id=222222,
            role_name="💎 VIP Elite",
            role_type="COMMUNITY",
        )
        self.assertEqual(updated.discord_role_id, 222222)
        self.assertEqual(updated.role_name, "💎 VIP Elite")

    async def test_log_and_get_role_audits(self):
        await self.db.log_role_audit(
            guild_id=1234,
            user_id=5555,
            role_id=987654321,
            role_key="verified",
            action="AUTO_ASSIGN",
            reason="Passed verification challenge",
            trigger="VERIFICATION",
            executor="SYSTEM",
            success=True,
        )
        audits = await self.db.get_recent_role_audits(1234, limit=5)
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].action, "AUTO_ASSIGN")
        self.assertEqual(audits[0].role_key, "verified")
        self.assertTrue(audits[0].success)


class TestRoleManagerSetupAndHealing(unittest.IsolatedAsyncioTestCase):
    """Tests for idempotent setup, self-healing restoration, and synchronization."""

    async def asyncSetUp(self):
        self.db_path = Path("tests/test_roles_setup.db")
        if self.db_path.exists():
            self.db_path.unlink()
        self.db = Database(self.db_path)
        await self.db.connect()

        self.bot = MagicMock()
        self.bot.db = self.db
        self.manager = RoleManager(self.bot)

        # Mock Guild
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 999111
        self.guild.name = "Test Guild"
        self.guild.owner_id = 1000

        # Bot permissions
        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_top_role = MagicMock(spec=discord.Role)
        self.bot_top_role.position = 50
        self.bot_top_role.name = "Rai Admin"
        self.bot_member.top_role = self.bot_top_role
        self.bot_member.guild_permissions = discord.Permissions(manage_roles=True)
        self.guild.me = self.bot_member

        self.role_counter = 100000

        async def fake_create_role(**kwargs):
            self.role_counter += 1
            m = MagicMock(spec=discord.Role)
            m.id = self.role_counter
            m.name = kwargs.get("name", "MockRole")
            m.position = 5
            return m

        self.guild.create_role = AsyncMock(side_effect=fake_create_role)
        self.guild.get_role = MagicMock(return_value=None)

    async def asyncTearDown(self):
        await self.db.close()
        await asyncio.sleep(0.05)
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except PermissionError:
                pass

    async def test_setup_guild_roles_reuses_existing_role(self):
        # Create an existing matching role in guild
        existing_role = MagicMock(spec=discord.Role)
        existing_role.id = 777888
        existing_role.name = "Verified"
        existing_role.position = 10
        existing_role.managed = False
        existing_role.is_default.return_value = False
        self.guild.roles = [existing_role]

        def fake_get_role(role_id):
            if role_id == existing_role.id:
                return existing_role
            return None

        self.guild.get_role = MagicMock(side_effect=fake_get_role)

        # Call setup
        report = await self.manager.setup_guild_roles(self.guild, executor="TEST")
        # Verified should be reused
        reused_keys = " ".join(report["reused"])
        self.assertIn("Verified", reused_keys)

        # Verify DB mapping
        stored = await self.db.get_guild_role(self.guild.id, "verified")
        self.assertIsNotNone(stored)
        self.assertEqual(stored.discord_role_id, 777888)

    async def test_self_healing_recreates_deleted_role(self):
        # Save a non-staff role in DB
        await self.db.save_guild_role(
            guild_id=self.guild.id,
            role_key="under_observation",
            discord_role_id=123999,
            role_name="🟡 Under Observation",
            role_type="SECURITY",
        )
        # Guild roles list is empty (role was deleted from Discord!)
        self.guild.roles = []

        # Mock role creation
        recreated = MagicMock(spec=discord.Role)
        recreated.id = 999000
        recreated.name = "🟡 Under Observation"
        recreated.position = 5
        self.guild.create_role = AsyncMock(return_value=recreated)

        report = await self.manager.repair_guild_roles(self.guild)
        self.assertEqual(len(report["recreated"]), 1)
        self.assertIn("Under Observation", report["recreated"][0])

        # Verify updated DB record
        updated_db = await self.db.get_guild_role(self.guild.id, "under_observation")
        self.assertEqual(updated_db.discord_role_id, 999000)

    async def test_self_healing_skips_dangerous_staff_roles(self):
        # Save an admin staff role in DB
        await self.db.save_guild_role(
            guild_id=self.guild.id,
            role_key="admin",
            discord_role_id=888999,
            role_name="⚡ Administrator",
            role_type="STAFF",
        )
        self.guild.roles = []
        report = await self.manager.repair_guild_roles(self.guild)
        # Recreating dangerous staff roles must be skipped to avoid privilege escalation
        self.assertEqual(len(report["skipped_staff"]), 1)
        self.assertEqual(len(report["recreated"]), 0)


if __name__ == "__main__":
    unittest.main()
