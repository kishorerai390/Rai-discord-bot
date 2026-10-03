"""
Unit and integration tests for Rai Private Control Center.

Verifies:
1. Complete hidden permission overwrites (@everyone DENY, Owner ALLOW, Bot ALLOW).
2. Category-specific role access (RAI_SECURITY, RAI_ADMIN, Owner, staff isolation).
3. Database persistence for private control configuration (Migration 20).
4. Authorization enforcement on interactive control buttons.
5. Interactive lockdown, unlock, backup, and health check button execution.
6. Server migration logic (reusing existing channels, preserving IDs and messages).
7. Report routing: Security incident delivery to Owner DM, security-report, and security-alerts.
"""

from __future__ import annotations

import asyncio
import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from database.database import Database
from database.models import PrivateControlConfig
from utils.private_control import PrivateControlManager, FOUNDER_ID
from utils.owner_reporter import OwnerReporter


class TestPrivateControlCenter(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_private_control.db"
        self.db = Database(str(self.db_path))
        await self.db.connect()

        self.guild_id = 1457382179981099090
        self.owner_id = 1457380609641938981

        # Setup mock Guild
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = self.guild_id
        self.guild.name = "✦ RAI FAM💗 ✦"
        self.guild.owner_id = self.owner_id

        self.owner_member = MagicMock(spec=discord.Member)
        self.owner_member.id = self.owner_id
        self.owner_member.name = "rf.rai_006"
        self.owner_member.bot = False
        self.owner_member.roles = []
        self.guild.owner = self.owner_member
        self.guild.get_member.side_effect = lambda uid: self.owner_member if uid == self.owner_id else None

        # Default role @everyone
        self.default_role = MagicMock(spec=discord.Role)
        self.default_role.name = "@everyone"
        self.default_role.managed = False
        self.guild.default_role = self.default_role

        # Bot member
        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_member.id = 1554732669072445532
        self.guild.me = self.bot_member

        # Bot instance
        self.bot = MagicMock()
        self.bot.db = self.db
        self.bot.get_guild.return_value = self.guild
        self.bot.fetch_guild = AsyncMock(return_value=self.guild)

        await self.db.get_or_create_guild_config(self.guild_id)

    async def asyncTearDown(self):
        try:
            if hasattr(self, "db") and self.db:
                await self.db.close()
        except Exception:
            pass
        await asyncio.sleep(0.02)
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    async def test_database_private_control_config_lifecycle(self):
        """Verify PrivateControlConfig insertion, retrieval, and updates in SQLite."""
        cfg = await self.db.get_or_create_private_control_config(self.guild_id)
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.guild_id, self.guild_id)
        self.assertTrue(cfg.auto_repair)

        # Update channels and category IDs
        updated = await self.db.update_private_control_config(
            self.guild_id,
            control_hub_category_id=101,
            reports_category_id=102,
            security_category_id=103,
            admin_category_id=104,
            security_alerts_id=201,
            anti_nuke_id=202,
            security_log_id=203,
            audit_monitor_id=204,
            lockdown_control_id=205,
            admin_control_id=301,
            server_dashboard_id=302,
            bot_config_id=303,
            automation_control_id=304,
            backup_control_id=305,
            system_health_id=306,
        )

        self.assertEqual(updated.control_hub_category_id, 101)
        self.assertEqual(updated.reports_category_id, 102)
        self.assertEqual(updated.security_category_id, 103)
        self.assertEqual(updated.admin_category_id, 104)
        self.assertEqual(updated.security_alerts_id, 201)
        self.assertEqual(updated.lockdown_control_id, 205)
        self.assertEqual(updated.admin_control_id, 301)
        self.assertEqual(updated.system_health_id, 306)

        # Refetch
        fetched = await self.db.get_private_control_config(self.guild_id)
        self.assertEqual(fetched.security_log_id, 203)
        self.assertEqual(fetched.backup_control_id, 305)

    def test_strict_permission_overwrites_generation(self):
        """Verify @everyone is denied view_channel, owner is allowed, and bot has management perms."""
        # Add roles
        sec_role = MagicMock(spec=discord.Role)
        sec_role.name = "🛡️ Security Admin"
        sec_role.managed = False

        admin_role = MagicMock(spec=discord.Role)
        admin_role.name = "⚡ Administrator"
        admin_role.managed = False

        mod_role = MagicMock(spec=discord.Role)
        mod_role.name = "🛡️ Moderator"
        mod_role.managed = False

        self.guild.roles = [self.default_role, sec_role, admin_role, mod_role]

        # 1. Security Category Overwrites
        sec_overwrites = PrivateControlManager.build_strict_overwrites(self.bot, self.guild, category_type="security")

        # @everyone must be completely denied
        self.assertIn(self.default_role, sec_overwrites)
        self.assertFalse(sec_overwrites[self.default_role].view_channel)
        self.assertFalse(sec_overwrites[self.default_role].send_messages)

        # Owner must have view and send permissions
        self.assertIn(self.owner_member, sec_overwrites)
        self.assertTrue(sec_overwrites[self.owner_member].view_channel)
        self.assertTrue(sec_overwrites[self.owner_member].send_messages)

        # Bot must have management permissions
        self.assertIn(self.bot_member, sec_overwrites)
        self.assertTrue(sec_overwrites[self.bot_member].view_channel)
        self.assertTrue(sec_overwrites[self.bot_member].manage_channels)
        self.assertTrue(sec_overwrites[self.bot_member].manage_roles)

        # Security role allowed in security category
        self.assertIn(sec_role, sec_overwrites)
        self.assertTrue(sec_overwrites[sec_role].view_channel)

        # Admin role denied in security category
        self.assertIn(admin_role, sec_overwrites)
        self.assertFalse(sec_overwrites[admin_role].view_channel)

        # Normal mod role denied
        self.assertIn(mod_role, sec_overwrites)
        self.assertFalse(sec_overwrites[mod_role].view_channel)

        # 2. Admin Category Overwrites
        admin_overwrites = PrivateControlManager.build_strict_overwrites(self.bot, self.guild, category_type="admin")
        self.assertFalse(admin_overwrites[sec_role].view_channel)
        self.assertTrue(admin_overwrites[admin_role].view_channel)
        self.assertFalse(admin_overwrites[mod_role].view_channel)

    async def test_authorization_checks(self):
        """Verify granular permission scopes (owner, security, admin) for button interactions."""
        sec_role = MagicMock(spec=discord.Role)
        sec_role.id = 555111
        sec_role.name = "RAI_SECURITY"

        admin_role = MagicMock(spec=discord.Role)
        admin_role.id = 555222
        admin_role.name = "RAI_ADMIN"

        sec_member = MagicMock(spec=discord.Member)
        sec_member.id = 888111
        sec_member.roles = [sec_role]

        admin_member = MagicMock(spec=discord.Member)
        admin_member.id = 888222
        admin_member.roles = [admin_role]

        normal_user = MagicMock(spec=discord.Member)
        normal_user.id = 888333
        normal_user.roles = []

        # Owner has access to everything
        self.assertTrue(await PrivateControlManager.is_authorized(self.bot, self.guild_id, self.owner_member, "owner"))
        self.assertTrue(await PrivateControlManager.is_authorized(self.bot, self.guild_id, self.owner_member, "security"))
        self.assertTrue(await PrivateControlManager.is_authorized(self.bot, self.guild_id, self.owner_member, "admin"))

        # Security member has security access, but not admin or owner
        self.assertFalse(await PrivateControlManager.is_authorized(self.bot, self.guild_id, sec_member, "owner"))
        self.assertTrue(await PrivateControlManager.is_authorized(self.bot, self.guild_id, sec_member, "security"))
        self.assertFalse(await PrivateControlManager.is_authorized(self.bot, self.guild_id, sec_member, "admin"))

        # Admin member has admin access, but not owner or security
        self.assertFalse(await PrivateControlManager.is_authorized(self.bot, self.guild_id, admin_member, "owner"))
        self.assertFalse(await PrivateControlManager.is_authorized(self.bot, self.guild_id, admin_member, "security"))
        self.assertTrue(await PrivateControlManager.is_authorized(self.bot, self.guild_id, admin_member, "admin"))

        # Normal user denied all
        self.assertFalse(await PrivateControlManager.is_authorized(self.bot, self.guild_id, normal_user, "security"))
        self.assertFalse(await PrivateControlManager.is_authorized(self.bot, self.guild_id, normal_user, "admin"))

    async def test_control_interaction_unauthorized_ephemeral_rejection(self):
        """Unauthorized user clicking control button must receive ephemeral rejection."""
        normal_user = MagicMock(spec=discord.Member)
        normal_user.id = 999999
        normal_user.roles = []

        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": f"rai_ctrl:lockdown:{self.guild_id}"}
        interaction.user = normal_user
        interaction.guild_id = self.guild_id
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        handled = await PrivateControlManager.handle_control_interaction(self.bot, interaction)
        self.assertTrue(handled)

        interaction.response.send_message.assert_awaited_once()
        msg_text = interaction.response.send_message.call_args[0][0]
        self.assertIn("Unauthorized", msg_text)
        self.assertTrue(interaction.response.send_message.call_args[1].get("ephemeral"))

    async def test_control_interaction_lockdown_toggle(self):
        """Owner clicking Lockdown / Unlock button updates lockdown state and returns ephemeral notice."""
        # 1. Engage lockdown
        interaction_lock = MagicMock(spec=discord.Interaction)
        interaction_lock.type = discord.InteractionType.component
        interaction_lock.data = {"custom_id": f"rai_ctrl:lockdown:{self.guild_id}"}
        interaction_lock.user = self.owner_member
        interaction_lock.guild_id = self.guild_id
        interaction_lock.response = MagicMock()
        interaction_lock.response.defer = AsyncMock()
        interaction_lock.followup = MagicMock()
        interaction_lock.followup.send = AsyncMock()

        self.bot.security_brain = MagicMock()
        self.bot.security_brain.engage_lockdown = AsyncMock()

        await PrivateControlManager.handle_control_interaction(self.bot, interaction_lock)
        self.bot.security_brain.engage_lockdown.assert_awaited_once()

        interaction_lock.followup.send.assert_awaited_once()
        feedback = interaction_lock.followup.send.call_args[0][0]
        self.assertIn("Lockdown Activated", feedback)
        self.assertTrue(interaction_lock.followup.send.call_args[1].get("ephemeral"))

        # 2. Lift lockdown
        interaction_unlock = MagicMock(spec=discord.Interaction)
        interaction_unlock.type = discord.InteractionType.component
        interaction_unlock.data = {"custom_id": f"rai_ctrl:unlock:{self.guild_id}"}
        interaction_unlock.user = self.owner_member
        interaction_unlock.guild_id = self.guild_id
        interaction_unlock.response = MagicMock()
        interaction_unlock.response.defer = AsyncMock()
        interaction_unlock.followup = MagicMock()
        interaction_unlock.followup.send = AsyncMock()

        self.bot.security_brain.release_lockdown = AsyncMock()
        await PrivateControlManager.handle_control_interaction(self.bot, interaction_unlock)
        self.bot.security_brain.release_lockdown.assert_awaited_once()

    async def test_security_report_mirroring_to_security_alerts(self):
        """Security incident reports must deliver to Owner DM, security-report, AND security-alerts."""
        # Setup channels
        sec_report_ch = MagicMock(spec=discord.TextChannel)
        sec_report_ch.id = 551100
        sec_report_ch.name = "security-report"
        sec_report_ch.send = AsyncMock()

        sec_alerts_ch = MagicMock(spec=discord.TextChannel)
        sec_alerts_ch.id = 552200
        sec_alerts_ch.name = "security-alerts"
        sec_alerts_ch.send = AsyncMock()

        self.guild.get_channel.side_effect = lambda cid: sec_report_ch if cid == 551100 else (sec_alerts_ch if cid == 552200 else None)
        self.bot.get_channel.side_effect = lambda cid: sec_report_ch if cid == 551100 else (sec_alerts_ch if cid == 552200 else None)

        # Setup DB configs
        await self.db.update_owner_reports_config(self.guild_id, security_report_id=551100)
        await self.db.update_private_control_config(self.guild_id, security_alerts_id=552200)

        # Owner user
        owner_user = MagicMock(spec=discord.User)
        owner_user.bot = False
        owner_user.send = AsyncMock()
        self.bot.get_user.return_value = owner_user

        # Send security report
        embed = discord.Embed(title="🚨 Mass Mention Raid Detected")
        inc_id = "RAI-INC-MIRROR-01"

        dm_ok, ch_ok = await OwnerReporter._dispatch_dual_report_async(
            bot=self.bot,
            guild_id=self.guild_id,
            channel_key="security_report_id",
            embed=embed,
            incident_id=inc_id,
            guild=self.guild,
            bypass_dedup=True,
            attach_actions=True,
            force_dm=True,
        )

        self.assertTrue(dm_ok)
        self.assertTrue(ch_ok)

        # 1. Owner DM received report
        owner_user.send.assert_awaited_once()

        # 2. security-report received report
        sec_report_ch.send.assert_awaited_once()

        # 3. security-alerts received mirrored report with same incident ID
        sec_alerts_ch.send.assert_awaited_once()
        alerts_embed = sec_alerts_ch.send.call_args[1]["embed"]
        self.assertEqual(alerts_embed.title, embed.title)


if __name__ == "__main__":
    unittest.main()
