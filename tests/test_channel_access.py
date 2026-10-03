"""
Unit and Integration Test Suite for RAI Automatic Empty Channel Access Engine.

Tests:
1. Channel type eligibility (text, announcement, forum vs voice, stage).
2. Private channel exclusion (@everyone view_channel=False).
3. Preservation of channels explicitly denied to RAI by design.
4. Empty channel detection (empty vs populated with messages).
5. Channels already accessible (no unnecessary modifications).
6. Minimum required overwrite application (View Channel, Send Messages, Read Message History only).
7. Non-overwrite of other member/role overwrites (preserves existing configuration).
8. Absence of dangerous permissions (No Administrator, Manage Roles, Manage Channels, etc.).
9. Role hierarchy and permission failure isolation (Missing Manage Roles / Forbidden).
10. Dry-run audit calculation and embed formatting.
11. Actual scan execution, reporting, and database state recording.
12. Discord API rate limit (HTTP 429) backoff and retry handling.
13. Failure isolation (single channel failure does not abort scan).
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import discord

from core.channel_access import (
    ChannelAccessEvaluation,
    ChannelAccessOperation,
    ChannelAccessScanSummary,
    ChannelAccessService,
)
from core.results import ErrorCodes, ResultStatus
from database.database import Database
from database.models import ChannelAccessConfig, ChannelAccessState


class TestChannelAccessEngine(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create an isolated temporary SQLite database and initialize migrations
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_channel_access.db"
        self.db = Database(self.db_path)
        await self.db.connect()

        # Ensure guild_config row exists for foreign key constraint
        await self.db.get_or_create_guild_config(1457382179981099090)

        # Guild mock
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 1457382179981099090
        self.guild.name = "RAI HQ"

        # Default role (@everyone)
        self.everyone_role = MagicMock(spec=discord.Role)
        self.everyone_role.id = self.guild.id
        self.guild.default_role = self.everyone_role

        # Bot member mock
        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_member.id = 999888777
        self.bot_member.guild = self.guild
        self.bot_member.guild_permissions = discord.Permissions(manage_roles=True)
        self.bot_member.roles = []
        self.guild.me = self.bot_member

        # Service instance
        self.service = ChannelAccessService(self.db)
        ChannelAccessService._instance = self.service

        # Default config
        self.config = ChannelAccessConfig(
            guild_id=self.guild.id,
            enabled=True,
            empty_channels_only=True,
            include_text=True,
            include_announcement=True,
            include_forum=True,
            include_voice=False,
            include_stage=False,
            include_private=False,
            auto_update=True,
        )

    async def asyncTearDown(self):
        if self.db.is_connected:
            await self.db.close()
        self.temp_dir.cleanup()

    # ==========================================
    # 1. CHANNEL TYPE ELIGIBILITY
    # ==========================================

    def test_channel_type_eligibility(self):
        # Text channel -> Eligible
        text_ch = MagicMock(spec=discord.TextChannel)
        text_ch.type = discord.ChannelType.text
        text_ch.is_news.return_value = False
        eligible, _ = self.service.is_eligible_channel_type(text_ch, self.config)
        self.assertTrue(eligible)

        # News / Announcement channel -> Eligible
        news_ch = MagicMock(spec=discord.TextChannel)
        news_ch.type = discord.ChannelType.news
        news_ch.is_news.return_value = True
        eligible, _ = self.service.is_eligible_channel_type(news_ch, self.config)
        self.assertTrue(eligible)

        # Forum channel -> Eligible
        forum_ch = MagicMock(spec=discord.ForumChannel)
        forum_ch.type = discord.ChannelType.forum
        eligible, _ = self.service.is_eligible_channel_type(forum_ch, self.config)
        self.assertTrue(eligible)

        # Voice channel -> Ineligible by default
        voice_ch = MagicMock(spec=discord.VoiceChannel)
        voice_ch.type = discord.ChannelType.voice
        eligible, reason = self.service.is_eligible_channel_type(voice_ch, self.config)
        self.assertFalse(eligible)
        self.assertIn("Voice channels excluded", reason)

        # Stage channel -> Ineligible by default
        stage_ch = MagicMock(spec=discord.StageChannel)
        stage_ch.type = discord.ChannelType.stage_voice
        eligible, reason = self.service.is_eligible_channel_type(stage_ch, self.config)
        self.assertFalse(eligible)
        self.assertIn("Stage channels excluded", reason)

    # ==========================================
    # 2. PRIVATE CHANNEL EXCLUSION
    # ==========================================

    def test_private_channel_exclusion(self):
        ch = MagicMock(spec=discord.TextChannel)
        ch.type = discord.ChannelType.text
        ch.guild = self.guild

        # Case A: @everyone has view_channel = False -> Private
        private_ow = discord.PermissionOverwrite(view_channel=False)
        ch.overwrites = {self.everyone_role: private_ow}
        self.assertTrue(self.service.is_private_channel(ch, self.guild))

        # Case B: @everyone has view_channel = None or True -> Public
        public_ow = discord.PermissionOverwrite(view_channel=True)
        ch.overwrites = {self.everyone_role: public_ow}
        self.assertFalse(self.service.is_private_channel(ch, self.guild))

    # ==========================================
    # 3. CHANNELS EXPLICITLY DENIED BY DESIGN
    # ==========================================

    def test_channels_explicitly_denied_by_design(self):
        ch = MagicMock(spec=discord.TextChannel)
        ch.type = discord.ChannelType.text

        # Explicit deny for bot member
        denied_ow = discord.PermissionOverwrite(view_channel=False)
        ch.overwrites = {self.bot_member: denied_ow}
        self.assertTrue(self.service.is_explicitly_denied_by_design(ch, self.bot_member))

        # Explicit allow
        allowed_ow = discord.PermissionOverwrite(view_channel=True)
        ch.overwrites = {self.bot_member: allowed_ow}
        self.assertFalse(self.service.is_explicitly_denied_by_design(ch, self.bot_member))

    # ==========================================
    # 4. EMPTY CHANNEL DETECTION
    # ==========================================

    async def test_empty_channel_detection(self):
        ch = MagicMock(spec=discord.TextChannel)
        perms = discord.Permissions(view_channel=True, read_message_history=True)
        ch.permissions_for.return_value = perms

        # Empty history
        async def empty_history(*args, **kwargs):
            if False:
                yield None

        ch.history = empty_history
        self.assertTrue(await self.service.is_channel_empty(ch, self.bot_member))

        # Non-empty history
        async def non_empty_history(*args, **kwargs):
            yield MagicMock(spec=discord.Message)

        ch.history = non_empty_history
        self.assertFalse(await self.service.is_channel_empty(ch, self.bot_member))

    # ==========================================
    # 5. ALREADY ACCESSIBLE CHANNEL
    # ==========================================

    def test_already_accessible_channel(self):
        ch = MagicMock(spec=discord.TextChannel)
        # Full access
        ch.permissions_for.return_value = discord.Permissions(
            view_channel=True, send_messages=True, read_message_history=True
        )
        has_access, missing = self.service.check_bot_access(ch, self.bot_member)
        self.assertTrue(has_access)
        self.assertEqual(len(missing), 0)

        # Missing send_messages
        ch.permissions_for.return_value = discord.Permissions(
            view_channel=True, send_messages=False, read_message_history=True
        )
        has_access, missing = self.service.check_bot_access(ch, self.bot_member)
        self.assertFalse(has_access)
        self.assertEqual(missing, ["send_messages"])

    # ==========================================
    # 6. MINIMUM OVERWRITE APPLICATION
    # ==========================================

    async def test_minimum_overwrite_application(self):
        ch = AsyncMock(spec=discord.TextChannel)
        ch.id = 111222333
        ch.name = "welcome-chat"

        # Pre-flight perms: Bot has manage_roles
        ch.permissions_for.side_effect = [
            # Check for can_manage_roles
            discord.Permissions(manage_roles=True),
            # Post-flight verification
            discord.Permissions(view_channel=True, send_messages=True, read_message_history=True),
        ]

        # Existing overwrite preserves unrelated flags
        existing_ow = discord.PermissionOverwrite(embed_links=True, attach_files=False)
        ch.overwrites_for.return_value = existing_ow

        missing_perms = ["view_channel", "send_messages", "read_message_history"]
        result = await self.service.apply_minimum_overwrite(ch, self.bot_member, missing_perms)

        self.assertTrue(result.success)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.data.action, "granted")
        self.assertIn("View Channel", result.data.permissions_added)
        self.assertIn("Send Messages", result.data.permissions_added)
        self.assertIn("Read Message History", result.data.permissions_added)

        # Verify channel.set_permissions was called with preserved attributes
        ch.set_permissions.assert_awaited_once()
        called_args, called_kwargs = ch.set_permissions.call_args
        self.assertEqual(called_args[0], self.bot_member)
        applied_ow = called_kwargs["overwrite"]

        # Minimum required were set
        self.assertTrue(applied_ow.view_channel)
        self.assertTrue(applied_ow.send_messages)
        self.assertTrue(applied_ow.read_message_history)

        # Unrelated permissions in overwrite were preserved
        self.assertTrue(applied_ow.embed_links)
        self.assertFalse(applied_ow.attach_files)

        # Dangerous permissions were NOT granted
        self.assertIsNone(applied_ow.administrator)
        self.assertIsNone(applied_ow.manage_channels)
        self.assertIsNone(applied_ow.manage_roles)
        self.assertIsNone(applied_ow.ban_members)
        self.assertIsNone(applied_ow.kick_members)
        self.assertIsNone(applied_ow.manage_webhooks)

    # ==========================================
    # 7. PERMISSION FAILURE & ROLE HIERARCHY
    # ==========================================

    async def test_permission_failure_when_lacking_manage_roles(self):
        ch = AsyncMock(spec=discord.TextChannel)
        ch.id = 111222333
        ch.name = "locked-down"

        # Bot does not have manage_roles
        self.bot_member.guild_permissions = discord.Permissions(manage_roles=False)
        ch.permissions_for.return_value = discord.Permissions(manage_roles=False)

        result = await self.service.apply_minimum_overwrite(ch, self.bot_member, ["view_channel"])

        self.assertFalse(result.success)
        self.assertEqual(result.status, ResultStatus.PERMISSION_DENIED)
        self.assertEqual(result.error.code, ErrorCodes.MISSING_MANAGE_ROLES)
        ch.set_permissions.assert_not_awaited()

    async def test_discord_forbidden_role_hierarchy(self):
        ch = AsyncMock(spec=discord.TextChannel)
        ch.id = 111222333
        ch.name = "role-locked"

        ch.permissions_for.return_value = discord.Permissions(manage_roles=True)
        ch.overwrites_for.return_value = discord.PermissionOverwrite()
        ch.set_permissions.side_effect = discord.Forbidden(
            response=MagicMock(status=403), message="Role hierarchy blocks modification"
        )

        result = await self.service.apply_minimum_overwrite(ch, self.bot_member, ["view_channel"])

        self.assertFalse(result.success)
        self.assertEqual(result.status, ResultStatus.ROLE_HIERARCHY_BLOCKED)
        self.assertEqual(result.error.code, ErrorCodes.ROLE_HIERARCHY_BLOCKED)

    # ==========================================
    # 8. DRY RUN MODE
    # ==========================================

    async def test_dry_run_scan(self):
        # Channel 1: Accessible
        ch1 = MagicMock(spec=discord.TextChannel)
        ch1.id = 101
        ch1.name = "general"
        ch1.type = discord.ChannelType.text
        ch1.is_news.return_value = False
        ch1.overwrites = {}
        ch1.permissions_for.return_value = discord.Permissions(
            view_channel=True, send_messages=True, read_message_history=True, manage_roles=True
        )

        async def ch1_hist(*a, **k):
            if False:
                yield None

        ch1.history = ch1_hist

        # Channel 2: Empty, missing view_channel
        ch2 = AsyncMock(spec=discord.TextChannel)
        ch2.id = 102
        ch2.name = "empty-announcements"
        ch2.type = discord.ChannelType.text
        ch2.is_news.return_value = False
        ch2.overwrites = {}
        ch2.last_message_id = None
        ch2.permissions_for.return_value = discord.Permissions(
            view_channel=False, send_messages=False, read_message_history=False, manage_roles=True
        )

        # Channel 3: Voice channel (skipped)
        ch3 = MagicMock(spec=discord.VoiceChannel)
        ch3.id = 103
        ch3.name = "General Voice"
        ch3.type = discord.ChannelType.voice

        self.guild.channels = [ch1, ch2, ch3]

        # Run Dry Run Scan
        summary = await self.service.scan_guild(
            self.guild, dry_run=True, bot_member=self.bot_member, config=self.config
        )

        self.assertTrue(summary.is_dry_run)
        self.assertEqual(summary.total_scanned, 3)
        self.assertEqual(summary.eligible_count, 2)
        self.assertEqual(summary.already_accessible, 1)
        self.assertEqual(summary.missing_access, 1)
        self.assertEqual(summary.would_modify, 1)
        self.assertEqual(summary.updated, 0)  # Dry run MUST NOT modify
        self.assertEqual(summary.skipped, 1)  # Voice channel skipped

        # ch2.set_permissions must NOT be called in dry-run
        ch2.set_permissions.assert_not_awaited()

        # Check Dry Run Embed Format
        embed = self.service.create_scan_embed(summary)
        self.assertIn("CHANNEL ACCESS AUDIT", embed.title)
        field_dict = {f.name: f.value for f in embed.fields}
        self.assertEqual(field_dict["Eligible Channels"], "2")
        self.assertEqual(field_dict["Already Accessible"], "1")
        self.assertEqual(field_dict["Missing Access"], "1")
        self.assertEqual(field_dict["Would Modify"], "1")
        self.assertIn("No changes were made", embed.footer.text)

    # ==========================================
    # 9. ACTUAL LIVE SCAN MODE
    # ==========================================

    async def test_live_scan_mode_and_database_state(self):
        # Channel 1: Empty, missing access
        ch1 = AsyncMock(spec=discord.TextChannel)
        ch1.id = 201
        ch1.name = "new-empty-channel"
        ch1.type = discord.ChannelType.text
        ch1.is_news.return_value = False
        ch1.overwrites = {}
        ch1.last_message_id = None
        ch1.overwrites_for.return_value = discord.PermissionOverwrite()

        updated = False

        def get_perms(member):
            if updated:
                return discord.Permissions(
                    view_channel=True, send_messages=True, read_message_history=True, manage_roles=True
                )
            return discord.Permissions(
                view_channel=False, send_messages=False, read_message_history=False, manage_roles=True
            )

        async def mock_set_permissions(*a, **k):
            nonlocal updated
            updated = True

        ch1.permissions_for = MagicMock(side_effect=get_perms)
        ch1.set_permissions = AsyncMock(side_effect=mock_set_permissions)

        self.guild.channels = [ch1]

        summary = await self.service.scan_guild(
            self.guild, dry_run=False, bot_member=self.bot_member, config=self.config
        )

        self.assertFalse(summary.is_dry_run)
        self.assertEqual(summary.total_scanned, 1)
        self.assertEqual(summary.updated, 1)
        self.assertEqual(summary.failed, 0)
        ch1.set_permissions.assert_awaited_once()

        # Check Live Scan Embed Format
        embed = self.service.create_scan_embed(summary)
        self.assertIn("CHANNEL ACCESS", embed.title)
        field_dict = {f.name: f.value for f in embed.fields}
        self.assertEqual(field_dict["Channels Scanned"], "1")
        self.assertEqual(field_dict["Updated"], "1")
        self.assertEqual(field_dict["Status"], "🟢 COMPLETE")

        # Verify DB recorded the state
        state = await self.db.get_channel_access_state(self.guild.id, 201)
        self.assertNotNull = self.assertIsNotNone(state)
        self.assertEqual(state.access_status, "UPDATED")

    # ==========================================
    # 10. DISCORD RATE LIMIT RETRY (HTTP 429)
    # ==========================================

    async def test_rate_limit_backoff_and_retry(self):
        ch = AsyncMock(spec=discord.TextChannel)
        ch.id = 301
        ch.name = "rate-limited-channel"

        ch.permissions_for.side_effect = [
            discord.Permissions(manage_roles=True),
            discord.Permissions(view_channel=True, send_messages=True, read_message_history=True),
        ]
        ch.overwrites_for.return_value = discord.PermissionOverwrite()

        # Simulate 1x 429 rate limit then success
        resp_mock = MagicMock(status=429)
        rl_exc = discord.HTTPException(response=resp_mock, message="You are being rate limited.")
        rl_exc.retry_after = 0.05

        ch.set_permissions.side_effect = [rl_exc, None]

        result = await self.service.apply_minimum_overwrite(ch, self.bot_member, ["view_channel"])

        self.assertTrue(result.success)
        self.assertEqual(ch.set_permissions.await_count, 2)

    # ==========================================
    # 11. AUDIT EMBED FORMAT SPECIFICATION
    # ==========================================

    def test_audit_embed_format_specification(self):
        op = ChannelAccessOperation(
            channel_id=401,
            channel_name="general-chat",
            status=ResultStatus.SUCCESS,
            action="granted",
            permissions_added=["View Channel", "Send Messages", "Read Message History"],
            reason="Eligible empty channel",
        )

        embed = self.service.create_audit_embed(op, "general-chat")
        self.assertEqual(embed.title, "『RΛI』 • CHANNEL ACCESS")
        fields = {f.name: f.value for f in embed.fields}
        self.assertEqual(fields["Channel"], "`#general-chat`")
        self.assertEqual(fields["Action"], "Bot access granted")
        self.assertEqual(fields["Permissions"], "View Channel\nSend Messages\nRead Message History")
        self.assertEqual(fields["Reason"], "Eligible empty channel")
        self.assertEqual(fields["Status"], "🟢 SUCCESS")


if __name__ == "__main__":
    unittest.main()
