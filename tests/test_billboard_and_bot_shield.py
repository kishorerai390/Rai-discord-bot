"""
Unit and Integration Tests for:
1. Live Dynamic Server Billboard (utils/server_billboard.py & cogs/billboard.py)
2. Third-Party Bot Least-Privilege Shield (security/bot_privilege_shield.py & cogs/security.py)
"""

import asyncio
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import discord

from database.database import Database
from database.migrations import run_migrations
from database.models import ServerBillboardConfig, BotShieldAuditRecord
from security.bot_privilege_shield import (
    BotPrivilegeShield,
    BotRiskTier,
    BotShieldActionView,
)
from utils.server_billboard import (
    BillboardInteractiveView,
    ServerBillboardManager,
)


class TestBillboardAndBotShield(unittest.IsolatedAsyncioTestCase):
    """Test suite for Billboard telemetry and Bot Privilege Shield isolation."""

    async def asyncSetUp(self):
        # 1. Setup In-Memory SQLite with all migrations
        self.conn = await aiosqlite.connect(":memory:")
        self.conn.row_factory = aiosqlite.Row
        await run_migrations(self.conn)

        self.db = Database(":memory:")
        self.db._db = self.conn

        # 2. Mock Bot and Guild
        self.bot = MagicMock()
        self.bot.db = self.db
        self.bot.user = MagicMock(spec=discord.ClientUser)
        self.bot.user.id = 99999999
        self.bot.user.name = "Rai"
        self.bot.user.display_avatar.url = "https://example.com/rai.png"
        self.bot.cogs = {}

        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 1457382179981099090
        self.guild.name = "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦"
        self.guild.icon = None
        self.guild.member_count = 41

        # Rai Bot Member
        self.rai_member = MagicMock(spec=discord.Member)
        self.rai_member.id = self.bot.user.id
        self.rai_member.name = "Rai"
        self.rai_member.bot = True
        self.rai_role = MagicMock(spec=discord.Role)
        self.rai_role.position = 50
        self.rai_member.top_role = self.rai_role
        self.rai_member.guild_permissions = discord.Permissions(administrator=True, manage_roles=True)
        self.guild.me = self.rai_member

        # Third-party bots
        self.admin_bot = MagicMock(spec=discord.Member)
        self.admin_bot.id = 11111111
        self.admin_bot.name = "ThirdPartyAdminBot"
        self.admin_bot.display_name = "ThirdPartyAdminBot"
        self.admin_bot.bot = True
        self.admin_bot_role = MagicMock(spec=discord.Role)
        self.admin_bot_role.name = "External Admin Bot"
        self.admin_bot_role.position = 20
        self.admin_bot_role.is_default.return_value = False
        self.admin_bot_role.managed = False
        self.admin_bot_role.permissions = discord.Permissions(administrator=True)
        self.admin_bot.roles = [self.admin_bot_role]
        self.admin_bot.top_role = self.admin_bot_role
        self.admin_bot.add_roles = AsyncMock()
        self.admin_bot.remove_roles = AsyncMock()

        self.music_bot = MagicMock(spec=discord.Member)
        self.music_bot.id = 22222222
        self.music_bot.name = "ExternalMusicBot"
        self.music_bot.display_name = "ExternalMusicBot"
        self.music_bot.bot = True
        self.music_bot_role = MagicMock(spec=discord.Role)
        self.music_bot_role.name = "Music Role"
        self.music_bot_role.position = 15
        self.music_bot_role.is_default.return_value = False
        self.music_bot_role.managed = False
        self.music_bot_role.permissions = discord.Permissions(
            send_messages=True, connect=True, speak=True
        )
        self.music_bot.roles = [self.music_bot_role]
        self.music_bot.top_role = self.music_bot_role
        self.music_bot.add_roles = AsyncMock()
        self.music_bot.remove_roles = AsyncMock()

        # Human user
        self.human_user = MagicMock(spec=discord.Member)
        self.human_user.id = 33333333
        self.human_user.name = "FounderKishore"
        self.human_user.bot = False
        self.human_user.guild_permissions = discord.Permissions(administrator=True)
        self.human_user.roles = []
        self.human_user.voice = None

        self.guild.members = [self.rai_member, self.admin_bot, self.music_bot, self.human_user]
        self.guild.roles = [self.rai_role, self.admin_bot_role, self.music_bot_role]
        self.guild.create_role = AsyncMock()

    async def asyncTearDown(self):
        await self.conn.close()

    # =========================================================================
    # 1. SERVER BILLBOARD TESTS
    # =========================================================================

    async def test_billboard_db_crud(self):
        """Billboard configuration persists and retrieves cleanly in SQLite."""
        cfg = ServerBillboardConfig(
            guild_id=self.guild.id,
            channel_id=123456,
            message_id=789012,
            is_active=True,
            update_interval=60,
            last_updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        await self.db.set_billboard_config(cfg)

        fetched = await self.db.get_billboard_config(self.guild.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.channel_id, 123456)
        self.assertEqual(fetched.message_id, 789012)
        self.assertTrue(fetched.is_active)

        deleted = await self.db.delete_billboard_config(self.guild.id)
        self.assertTrue(deleted)
        self.assertIsNone(await self.db.get_billboard_config(self.guild.id))

    def test_billboard_embed_rendering(self):
        """Billboard embed correctly compiles server metrics, voice, and music."""
        manager = ServerBillboardManager(self.bot)
        embed = manager.build_billboard_embed(self.guild)

        self.assertIn("✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓛ɪᴠᴇ 𝕾ᴇʀᴠᴇʀ 𝕳ᴜʙ ✦", embed.title)
        self.assertEqual(len(embed.fields), 4)

        field_names = [f.name for f in embed.fields]
        self.assertIn("👥 ┃ 𝓢ᴇʀᴠᴇʀ・𝕻ᴜʟsᴇ", field_names)
        self.assertIn("🎙️ ┃ 𝓥ᴏɪᴄᴇ・𝓛ᴏᴜɴɢᴇ", field_names)
        self.assertIn("🎵 ┃ 𝓜ᴜsɪᴄ・𝕷ᴏᴜɴɢᴇ", field_names)
        self.assertIn("🛡️ ┃ 𝓡ᴀɪ・𝕾ᴇᴄᴜʀɪᴛʏ・𝕾ʜɪᴇʟᴅ", field_names)

    async def test_billboard_update_success(self):
        """Billboard updates live Discord message and records sync timestamp."""
        manager = ServerBillboardManager(self.bot)

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 555555
        self.guild.get_channel.return_value = channel

        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.id = 777777
        mock_msg.edit = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=mock_msg)

        cfg = ServerBillboardConfig(
            guild_id=self.guild.id,
            channel_id=channel.id,
            message_id=mock_msg.id,
            is_active=True,
        )
        await self.db.set_billboard_config(cfg)

        ok, msg = await manager.update_billboard(self.guild, force=True)
        self.assertTrue(ok)
        mock_msg.edit.assert_called_once()

    # =========================================================================
    # 2. THIRD-PARTY BOT PRIVILEGE SHIELD TESTS
    # =========================================================================

    async def test_bot_privilege_audit(self):
        """Audits third-party bots and correctly flags over-privileged accounts."""
        shield = BotPrivilegeShield(self.bot)
        items = await shield.audit_guild_bots(self.guild)

        # 2 external bots audited (Rai is excluded)
        self.assertEqual(len(items), 2)

        # Admin bot must be classified as CRITICAL
        admin_item = next(i for i in items if i.bot_member.id == self.admin_bot.id)
        self.assertEqual(admin_item.risk_tier, BotRiskTier.CRITICAL)
        self.assertIn("Administrator", admin_item.dangerous_permissions)

        # Music bot must be classified as LOW/SAFE
        music_item = next(i for i in items if i.bot_member.id == self.music_bot.id)
        self.assertEqual(music_item.risk_tier, BotRiskTier.LOW)
        self.assertEqual(len(music_item.dangerous_permissions), 0)

    async def test_bot_privilege_shield_embed(self):
        """Audit report embed renders with proper risk counts and indicators."""
        shield = BotPrivilegeShield(self.bot)
        items = await shield.audit_guild_bots(self.guild)
        embed = shield.build_audit_embed(self.guild, items)

        self.assertIn("𝓣ʜɪʀᴅ-𝕻ᴀʀᴛʏ 𝕭ᴏᴛ 𝕾ʜɪᴇʟᴅ", embed.title)
        self.assertIn("🔴 **Critical**: `1`", embed.description)
        self.assertIn("🤖 **Total External Bots**: `2`", embed.description)

    async def test_bot_isolation_flow(self):
        """Isolating a dangerous bot creates Safe Bot role and strips destructive roles."""
        shield = BotPrivilegeShield(self.bot)

        # Mock safe role creation
        safe_role = MagicMock(spec=discord.Role)
        safe_role.name = "🤖 ╏ Safe Bot"
        self.guild.create_role.return_value = safe_role

        ok, msg = await shield.isolate_bot(self.guild, self.admin_bot, self.human_user)
        self.assertTrue(ok)
        self.assertIn("Successfully isolated", msg)

        # Verified safe role assigned and dangerous role removed
        self.admin_bot.add_roles.assert_called_once_with(
            safe_role, reason=f"Isolated by {self.human_user} via Rai Bot Shield"
        )
        self.admin_bot.remove_roles.assert_called_once_with(
            self.admin_bot_role, reason=f"High-risk permission stripped by {self.human_user} via Rai Bot Shield"
        )

        # Verified recorded in SQLite
        audits = await self.db.get_bot_shield_audits(self.guild.id)
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].bot_id, self.admin_bot.id)
        self.assertTrue(audits[0].is_isolated)

    async def test_bot_isolation_role_hierarchy_protection(self):
        """Shield rejects isolation if target bot has higher role than Rai."""
        shield = BotPrivilegeShield(self.bot)

        # Target bot higher than Rai
        superior_role = MagicMock(spec=discord.Role)
        superior_role.position = 99
        self.admin_bot.top_role = superior_role

        ok, msg = await shield.isolate_bot(self.guild, self.admin_bot, self.human_user)
        self.assertFalse(ok)
        self.assertIn("Role hierarchy blocked", msg)
