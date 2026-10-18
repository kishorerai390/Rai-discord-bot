"""
Test suite for MusicMaid automated bot role creation and permission setup.
Verifies idempotent startup setup, new guild join lifecycle, duplicate prevention,
role reuse, permission repair, hierarchy safety, and safe failure handling.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from music_bot.services.role_service import (
    BOT_ROLE_NAME,
    REQUIRED_PERMISSIONS_DICT,
    BotRoleService,
)


class TestBotRoleService(unittest.IsolatedAsyncioTestCase):
    """Test suite covering all requirements of the MusicMaid role automation system."""

    def setUp(self):
        # Create mock Discord Guild
        self.mock_guild = MagicMock(spec=discord.Guild)
        self.mock_guild.id = 123456789012345678
        self.mock_guild.name = "MusicMaid Test Server"
        self.mock_guild.roles = []

        # Create mock Bot Member (guild.me)
        self.mock_me = MagicMock(spec=discord.Member)
        self.mock_me.id = 999999999999999999
        self.mock_me.roles = []
        self.mock_guild.me = self.mock_me

        # Setup top role for bot
        self.mock_bot_top_role = MagicMock(spec=discord.Role)
        self.mock_bot_top_role.name = "Bot Integration"
        self.mock_bot_top_role.position = 10
        self.mock_me.top_role = self.mock_bot_top_role

        # Default permissions: Has manage_roles
        self.mock_guild_perms = MagicMock()
        self.mock_guild_perms.manage_roles = True
        for p in REQUIRED_PERMISSIONS_DICT.keys():
            setattr(self.mock_guild_perms, p, True)
        self.mock_guild_perms.administrator = False
        self.mock_me.guild_permissions = self.mock_guild_perms

        # Mock database
        self.mock_db = MagicMock()
        self.mock_db.get_bot_role_id = AsyncMock(return_value=None)
        self.mock_db.set_bot_role_id = AsyncMock()

    # =========================================================================
    # 1. PERMISSION CONFIGURATION VERIFICATION
    # =========================================================================

    def test_01_target_permissions_configuration(self):
        """Verify target permissions match exact requirements and administrator is False."""
        perms = BotRoleService.get_target_permissions()

        # Text & Player Permissions
        self.assertTrue(perms.view_channel, "view_channel must be True")
        self.assertTrue(perms.send_messages, "send_messages must be True")
        self.assertTrue(perms.embed_links, "embed_links must be True")
        self.assertTrue(perms.read_message_history, "read_message_history must be True")
        self.assertTrue(perms.use_application_commands, "use_application_commands must be True")

        # Voice Permissions
        self.assertTrue(perms.connect, "connect must be True")
        self.assertTrue(perms.speak, "speak must be True")

        # STRICT SECURITY GUARANTEE: Never grant Administrator
        self.assertFalse(perms.administrator, "administrator must be False")

    # =========================================================================
    # 2. ROLE CREATION WHEN MISSING
    # =========================================================================

    async def test_02_creates_role_when_missing(self):
        """Verify role is created once with exact name and assigned to bot."""
        created_role = MagicMock(spec=discord.Role)
        created_role.id = 888888888888888888
        created_role.name = BOT_ROLE_NAME
        created_role.position = 5

        self.mock_guild.create_role = AsyncMock(return_value=created_role)
        self.mock_me.add_roles = AsyncMock()
        self.mock_bot_top_role.__gt__ = MagicMock(return_value=True)

        success, role, msg = await BotRoleService.setup_guild_role(self.mock_guild, self.mock_db)

        self.assertTrue(success)
        self.assertEqual(role, created_role)
        self.assertIn("Created new dedicated role", msg)
        self.mock_guild.create_role.assert_awaited_once()
        self.mock_me.add_roles.assert_awaited_once_with(
            created_role, reason="MusicMaid dedicated bot role assignment"
        )
        self.mock_db.set_bot_role_id.assert_awaited_once_with(self.mock_guild.id, created_role.id)

    # =========================================================================
    # 3. ROLE REUSE AND DUPLICATE PREVENTION
    # =========================================================================

    async def test_03_duplicate_prevention_and_reuse(self):
        """Verify existing MusicMaid role is reused and no duplicate is created."""
        existing_role = MagicMock(spec=discord.Role)
        existing_role.id = 777777777777777777
        existing_role.name = BOT_ROLE_NAME
        existing_role.position = 5

        # All required permissions are present
        role_perms = MagicMock()
        for p in REQUIRED_PERMISSIONS_DICT.keys():
            setattr(role_perms, p, True)
        role_perms.administrator = False
        existing_role.permissions = role_perms

        self.mock_guild.roles = [existing_role]
        self.mock_me.roles = [existing_role]  # Already assigned
        self.mock_guild.create_role = AsyncMock()

        success, role, msg = await BotRoleService.setup_guild_role(self.mock_guild, self.mock_db)

        self.assertTrue(success)
        self.assertEqual(role, existing_role)
        self.assertIn("Reused existing role", msg)
        self.mock_guild.create_role.assert_not_called()

    # =========================================================================
    # 4. PERMISSION REPAIR ON EXISTING ROLE
    # =========================================================================

    async def test_04_permission_repair_on_existing_role(self):
        """Verify missing approved permissions are repaired when bot has hierarchy."""
        existing_role = MagicMock(spec=discord.Role)
        existing_role.id = 777777777777777777
        existing_role.name = BOT_ROLE_NAME
        existing_role.position = 5
        existing_role.edit = AsyncMock()

        # Missing 'speak' and 'embed_links'
        role_perms = MagicMock()
        for p in REQUIRED_PERMISSIONS_DICT.keys():
            setattr(role_perms, p, False if p in ("speak", "embed_links") else True)
        role_perms.value = 12345
        existing_role.permissions = role_perms

        self.mock_guild.roles = [existing_role]
        self.mock_me.roles = [existing_role]
        self.mock_bot_top_role.__gt__ = MagicMock(return_value=True)

        success, role, msg = await BotRoleService.setup_guild_role(self.mock_guild, self.mock_db)

        self.assertTrue(success)
        existing_role.edit.assert_awaited_once()

    # =========================================================================
    # 5. MISSING MANAGE ROLES FAILURE HANDLING
    # =========================================================================

    async def test_05_graceful_handling_missing_manage_roles(self):
        """Verify bot does not crash or loop when missing Manage Roles permission."""
        self.mock_guild_perms.manage_roles = False
        self.mock_guild.create_role = AsyncMock()

        success, role, msg = await BotRoleService.setup_guild_role(self.mock_guild, self.mock_db)

        self.assertFalse(success)
        self.assertIsNone(role)
        self.assertIn("Missing 'Manage Roles' permission", msg)
        self.mock_guild.create_role.assert_not_called()

    # =========================================================================
    # 6. ROLE HIERARCHY RESTRICTION HANDLING
    # =========================================================================

    async def test_06_role_hierarchy_restriction_logged(self):
        """Verify bot detects when role is higher than bot's top role and does not fail fatally."""
        existing_role = MagicMock(spec=discord.Role)
        existing_role.id = 555555555555555555
        existing_role.name = BOT_ROLE_NAME
        existing_role.position = 20  # Above bot's top role

        self.mock_guild.roles = [existing_role]
        self.mock_me.roles = []  # Not assigned
        self.mock_bot_top_role.__gt__ = MagicMock(return_value=False)
        self.mock_bot_top_role.__le__ = MagicMock(return_value=True)

        self.mock_me.add_roles = AsyncMock()

        success, role, msg = await BotRoleService.setup_guild_role(self.mock_guild, self.mock_db)

        self.assertTrue(success)  # Role setup completes, but assignment is safely deferred
        self.mock_me.add_roles.assert_not_called()

    # =========================================================================
    # 7. STARTUP SETUP ALL GUILDS INSPECTION
    # =========================================================================

    async def test_07_setup_all_guilds_startup(self):
        """Verify setup_all_guilds iterates all guilds sequentially."""
        mock_bot = MagicMock(spec=discord.Client)
        guild2 = MagicMock(spec=discord.Guild)
        guild2.id = 222222222222222222
        guild2.name = "Second Guild"
        guild2.me = self.mock_me
        guild2.roles = []
        guild2.create_role = AsyncMock(return_value=MagicMock(spec=discord.Role, id=1, position=1))

        mock_bot.guilds = [self.mock_guild, guild2]

        with patch.object(BotRoleService, "setup_guild_role", AsyncMock(return_value=(True, MagicMock(id=1), "Created new dedicated role"))):
            res = await BotRoleService.setup_all_guilds(mock_bot, self.mock_db)

            self.assertEqual(res["total_guilds"], 2)
            self.assertEqual(res["created"], 2)
            self.assertEqual(res["failed"], 0)

    # =========================================================================
    # 8. NEW GUILD JOIN LIFECYCLE
    # =========================================================================

    async def test_08_on_guild_join_lifecycle(self):
        """Verify on_guild_join hook executes setup_guild_role."""
        from music_bot.bot import RaiMusicBot

        bot = MagicMock(spec=RaiMusicBot)
        bot.db = self.mock_db

        with patch.object(BotRoleService, "setup_guild_role", AsyncMock(return_value=(True, MagicMock(id=1), "Created new dedicated role"))) as mock_setup:
            await RaiMusicBot.on_guild_join(bot, self.mock_guild)
            mock_setup.assert_awaited_once_with(self.mock_guild, self.mock_db)


if __name__ == "__main__":
    unittest.main()
