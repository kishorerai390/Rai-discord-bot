"""
Unit & Integration Tests for RAI Natural Language Owner Control Engine.
Validates:
- Intent recognition across natural language variants.
- Strict owner and admin permission gates.
- Fast rejection of casual conversation.
- Confirmation gate for dangerous commands.
- Chained tasks execution and failure halt with diagnostic ID.
- Context-aware follow-ups (details, clean them).
- Context isolation across guilds and users.
- Integration with BackupManager, Health, Dynamic Rooms, and Music.
- Next action buttons and audit logging.
"""

import asyncio
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from backups.manager import BackupManager, BackupRecord
from core.nl_control import (
    ADMIN_INTENTS,
    DANGEROUS_INTENTS,
    NLActionDispatcher,
    NLContextManager,
    NLControlEngine,
    NLIntent,
    NLParser,
    NLSessionContext,
    ParsedTask,
)
from database.manager import DatabaseManager


class TestNLControlEngine(墙 := unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_bot.db"
        self.backups_dir = Path(self.temp_dir) / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)

        import aiosqlite
        from database.database import Database
        from database.migrations import run_migrations

        DatabaseManager._instance = None
        self.conn = await aiosqlite.connect(str(self.db_path))
        self.conn.row_factory = aiosqlite.Row
        await run_migrations(self.conn)

        self.db = Database(str(self.db_path))
        self.db._db = self.conn

        self.db_mgr = DatabaseManager(self.db_path)
        self.db_mgr.sqlite = self.db
        DatabaseManager._instance = self.db_mgr

        # Reset singleton BackupManager
        BackupManager._instance = None
        self.backup_mgr = BackupManager(db_path=self.db_path, backups_dir=self.backups_dir)

        # Mock Bot
        self.bot = MagicMock()
        self.bot.db = self.db
        self.bot.db_manager = self.db_mgr
        self.bot.user = MagicMock(id=1554732669072445532, spec=discord.ClientUser)
        self.bot.cogs = {}

        # Mock Guild, Owner & Admin
        self.guild = MagicMock(spec=discord.Guild, id=1001, name="Test Guild")
        self.guild.owner_id = 9999
        self.guild.members = []
        self.guild.categories = []
        self.guild.text_channels = []
        self.guild.voice_client = None

        # Owner Member
        self.owner_member = MagicMock(spec=discord.Member, id=9999, name="GuildOwner", display_name="Owner")
        self.owner_member.bot = False
        self.owner_member.guild_permissions.administrator = True
        self.guild.members.append(self.owner_member)

        # Normal Member
        self.normal_member = MagicMock(spec=discord.Member, id=2222, name="CasualUser", display_name="Casual")
        self.normal_member.bot = False
        self.normal_member.guild_permissions.administrator = False
        self.normal_member.voice = None
        self.guild.members.append(self.normal_member)

        # Mock Text Channel
        self.channel = MagicMock(spec=discord.TextChannel, id=5001, name="general")
        self.channel.guild = self.guild
        self.channel.send = AsyncMock()

    async def asyncTearDown(self):
        await self.conn.close()
        DatabaseManager._instance = None
        BackupManager._instance = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =========================================================================
    # 1. PARSER & INTENT RECOGNITION TESTS
    # =========================================================================

    def test_parser_backup_recognition(self):
        phrases = [
            "you auto backup",
            "do an automatic backup",
            "backup the server",
            "run backup",
            "auto backup",
            "backup",
        ]
        for p in phrases:
            tasks = NLParser.parse_message(p, bot_id=self.bot.user.id)
            self.assertEqual(len(tasks), 1, f"Failed on phrase: {p}")
            self.assertEqual(tasks[0].intent, NLIntent.BACKUP_CREATE, f"Intent mismatch for: {p}")

    def test_parser_health_and_status(self):
        phrases = [
            "check health",
            "show system status",
            "check the bot",
            "is the bot okay",
            "system health",
        ]
        for p in phrases:
            tasks = NLParser.parse_message(p, bot_id=self.bot.user.id)
            self.assertTrue(len(tasks) >= 1, f"Failed on: {p}")
            self.assertIn(tasks[0].intent, (NLIntent.HEALTH_CHECK, NLIntent.SYSTEM_STATUS))

    def test_parser_dynamic_rooms(self):
        # Room list
        tasks = NLParser.parse_message("show active rooms")
        self.assertEqual(tasks[0].intent, NLIntent.ROOM_LIST)

        # Room cleanup
        tasks = NLParser.parse_message("clean empty rooms")
        self.assertEqual(tasks[0].intent, NLIntent.ROOM_CLEANUP)

        # Lock all rooms (dangerous)
        tasks = NLParser.parse_message("lock all rooms")
        self.assertEqual(tasks[0].intent, NLIntent.LOCK_ALL_ROOMS)

        # Delete all rooms (dangerous)
        tasks = NLParser.parse_message("delete all rooms")
        self.assertEqual(tasks[0].intent, NLIntent.DELETE_ALL_ROOMS)

    def test_parser_music(self):
        tasks = NLParser.parse_message("show music queue")
        self.assertEqual(tasks[0].intent, NLIntent.MUSIC_QUEUE)

        tasks = NLParser.parse_message("skip")
        self.assertEqual(tasks[0].intent, NLIntent.MUSIC_SKIP)

        tasks = NLParser.parse_message("pause")
        self.assertEqual(tasks[0].intent, NLIntent.MUSIC_PAUSE)

        tasks = NLParser.parse_message("resume")
        self.assertEqual(tasks[0].intent, NLIntent.MUSIC_RESUME)

    def test_parser_room_controls_and_entities(self):
        # Make private / public
        tasks = NLParser.parse_message("make my room private")
        self.assertEqual(tasks[0].intent, NLIntent.ROOM_PRIVACY_PRIVATE)

        tasks = NLParser.parse_message("make my room public")
        self.assertEqual(tasks[0].intent, NLIntent.ROOM_PRIVACY_PUBLIC)

        # Invite entity
        tasks = NLParser.parse_message("invite Alex")
        self.assertEqual(tasks[0].intent, NLIntent.ROOM_INVITE)
        self.assertEqual(tasks[0].entities.get("target"), "Alex")

        tasks = NLParser.parse_message("invite <@123456789>")
        self.assertEqual(tasks[0].intent, NLIntent.ROOM_INVITE)
        self.assertEqual(tasks[0].entities.get("target"), "123456789")

        # DJ delegation
        tasks = NLParser.parse_message("give Alex DJ")
        self.assertEqual(tasks[0].intent, NLIntent.DJ_ADD)
        self.assertEqual(tasks[0].entities.get("target"), "Alex")

        # Co-host delegation
        tasks = NLParser.parse_message("make Alex cohost")
        self.assertEqual(tasks[0].intent, NLIntent.COHOST_ADD)
        self.assertEqual(tasks[0].entities.get("target"), "Alex")

    def test_parser_fast_drop_casual_chat(self):
        casual = ["hello", "good morning", "what's up", "nice music", "thanks", "lol", "ok"]
        for c in casual:
            tasks = NLParser.parse_message(c, bot_id=self.bot.user.id)
            self.assertEqual(len(tasks), 0, f"Did not drop casual text: {c}")

    # =========================================================================
    # 2. CHAINED TASKS & FAILURE STOP
    # =========================================================================

    def test_parser_chained_tasks(self):
        tasks = NLParser.parse_message("backup the server and then check health")
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0].intent, NLIntent.BACKUP_CREATE)
        self.assertEqual(tasks[1].intent, NLIntent.HEALTH_CHECK)

    async def test_chained_execution_success(self):
        session = NLContextManager.get_session(self.guild.id, self.owner_member.id, self.channel.id)
        msg = MagicMock(spec=discord.Message)
        msg.guild = self.guild
        msg.author = self.owner_member
        msg.channel = self.channel
        msg.content = "backup the server and then check health"

        # Mock typing context manager
        self.channel.typing.return_value.__aenter__ = AsyncMock()
        self.channel.typing.return_value.__aexit__ = AsyncMock()

        handled = await NLControlEngine.process_message(self.bot, msg)
        self.assertTrue(handled)
        self.channel.send.assert_called_once()

        # Audit log should have 2 records for the chain
        audits = await self.db.get_recent_nl_audits(self.guild.id, limit=5)
        self.assertEqual(len(audits), 2)

    async def test_chained_execution_failure_stops_chain(self):
        msg = MagicMock(spec=discord.Message)
        msg.guild = self.guild
        msg.author = self.owner_member
        msg.channel = self.channel
        msg.content = "backup the server and then check health"

        self.channel.typing.return_value.__aenter__ = AsyncMock()
        self.channel.typing.return_value.__aexit__ = AsyncMock()

        # Simulate backup failure
        with patch.object(BackupManager, "get_instance") as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.run_backup = AsyncMock(side_effect=RuntimeError("Disk write failed"))
            mock_mgr_cls.return_value = mock_mgr

            handled = await NLControlEngine.process_message(self.bot, msg)
            self.assertTrue(handled)

            # Check that error embed with diagnostic ID was sent
            self.channel.send.assert_called_once()
            call_args = self.channel.send.call_args[1]
            embed = call_args.get("embed")
            self.assertIn("TASK CHAIN STOPPED", embed.title)
            self.assertIn("Diagnostic ID", embed.description)

    # =========================================================================
    # 3. PERMISSION & OWNER GATES
    # =========================================================================

    async def test_unauthorized_user_blocked_from_admin_commands(self):
        session = NLContextManager.get_session(self.guild.id, self.normal_member.id, self.channel.id)
        task = ParsedTask(intent=NLIntent.BACKUP_CREATE, raw_segment="backup", confidence=1.0)

        res = await NLActionDispatcher.dispatch(
            bot=self.bot,
            guild=self.guild,
            user=self.normal_member,
            channel=self.channel,
            task=task,
            session=session,
        )
        self.assertFalse(res.success)
        self.assertEqual(res.title, "Unauthorized")

    async def test_owner_authorized_for_admin_commands(self):
        session = NLContextManager.get_session(self.guild.id, self.owner_member.id, self.channel.id)
        task = ParsedTask(intent=NLIntent.BACKUP_CREATE, raw_segment="backup", confidence=1.0)

        res = await NLActionDispatcher.dispatch(
            bot=self.bot,
            guild=self.guild,
            user=self.owner_member,
            channel=self.channel,
            task=task,
            session=session,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.title, "Backup Completed")
        self.assertTrue(len(res.next_actions) > 0)

    # =========================================================================
    # 4. CONFIRMATION FOR DANGEROUS ACTIONS
    # =========================================================================

    async def test_lock_all_rooms_requires_confirmation(self):
        session = NLContextManager.get_session(self.guild.id, self.owner_member.id, self.channel.id)
        task = ParsedTask(intent=NLIntent.LOCK_ALL_ROOMS, raw_segment="lock all rooms", confidence=1.0)

        # 1. Unconfirmed dispatch
        res = await NLActionDispatcher.dispatch(
            bot=self.bot,
            guild=self.guild,
            user=self.owner_member,
            channel=self.channel,
            task=task,
            session=session,
            is_confirmed=False,
        )
        self.assertTrue(res.requires_confirmation)
        self.assertIn("CONFIRMATION REQUIRED", res.embed.title)

        # 2. Confirmed dispatch
        res_confirmed = await NLActionDispatcher.dispatch(
            bot=self.bot,
            guild=self.guild,
            user=self.owner_member,
            channel=self.channel,
            task=task,
            session=session,
            is_confirmed=True,
        )
        self.assertFalse(res_confirmed.requires_confirmation)
        self.assertEqual(res_confirmed.title, "Rooms Locked")

    # =========================================================================
    # 5. CONTEXT-AWARE FOLLOW-UP
    # =========================================================================

    async def test_contextual_follow_up_details(self):
        session = NLContextManager.get_session(self.guild.id, self.owner_member.id, self.channel.id)

        # Step 1: User runs backup
        task_backup = ParsedTask(intent=NLIntent.BACKUP_CREATE, raw_segment="backup", confidence=1.0)
        await NLActionDispatcher.dispatch(
            bot=self.bot,
            guild=self.guild,
            user=self.owner_member,
            channel=self.channel,
            task=task_backup,
            session=session,
        )
        self.assertEqual(session.last_result_type, "backup")
        backup_id = session.last_result_data.get("backup_id")

        # Step 2: User says "show details"
        task_details = NLParser.parse_message("show details", context=session)
        self.assertEqual(task_details[0].intent, NLIntent.FOLLOW_UP_DETAILS)

        res = await NLActionDispatcher.dispatch(
            bot=self.bot,
            guild=self.guild,
            user=self.owner_member,
            channel=self.channel,
            task=task_details[0],
            session=session,
        )
        self.assertTrue(res.success)
        self.assertIn(backup_id, res.embed.title)
        self.assertIn("SHA-256", res.embed.description)

    async def test_context_isolation_across_guilds_and_users(self):
        # Guild 1, User 1
        s1 = NLContextManager.get_session(1001, 9999, 5001)
        NLContextManager.update_session(1001, 9999, 5001, NLIntent.BACKUP_CREATE, "backup", {"backup_id": "BAK-1"})

        # Guild 2, User 1
        s2 = NLContextManager.get_session(1002, 9999, 5001)
        self.assertIsNone(s2.last_result_type)

        # Guild 1, User 2
        s3 = NLContextManager.get_session(1001, 8888, 5001)
        self.assertIsNone(s3.last_result_type)

    # =========================================================================
    # 6. INTEGRATION WITH EXISTING SERVICES
    # =========================================================================

    async def test_security_check_and_dual_reporting(self):
        session = NLContextManager.get_session(self.guild.id, self.owner_member.id, self.channel.id)
        task = ParsedTask(intent=NLIntent.SECURITY_CHECK, raw_segment="check security", confidence=1.0)

        with patch.object(NLActionDispatcher, "_execute_security_check", wraps=NLActionDispatcher._execute_security_check) as mock_sec:
            res = await NLActionDispatcher.dispatch(
                bot=self.bot,
                guild=self.guild,
                user=self.owner_member,
                channel=self.channel,
                task=task,
                session=session,
            )
            self.assertTrue(res.success)
            self.assertIn("Security Status Overview", res.embed.title)
            self.assertIsNotNone(res.sensitive_details)

    async def test_music_queue_and_skip(self):
        session = NLContextManager.get_session(self.guild.id, self.owner_member.id, self.channel.id)

        # Mock Music Cog & Player
        mock_music_cog = MagicMock()
        mock_player = MagicMock()
        mock_song = MagicMock(title="Cyberpunk Synthwave", artist="Rai")
        mock_player.current = mock_song
        mock_player.queue = [MagicMock(title="Night City Beats")]
        mock_music_cog.players = {self.guild.id: mock_player}
        self.bot.cogs["Music"] = mock_music_cog

        # Configure request channel isolation for test channel
        await self.bot.db.update_music_config(self.guild.id, request_channel_id=self.channel.id)

        # Test Queue
        task_q = ParsedTask(intent=NLIntent.MUSIC_QUEUE, raw_segment="show queue", confidence=1.0)
        res_q = await NLActionDispatcher.dispatch(
            bot=self.bot, guild=self.guild, user=self.owner_member, channel=self.channel, task=task_q, session=session
        )
        self.assertTrue(res_q.success)
        self.assertIn("Cyberpunk Synthwave", res_q.embed.description)

        # Test Skip
        task_s = ParsedTask(intent=NLIntent.MUSIC_SKIP, raw_segment="skip", confidence=1.0)
        res_s = await NLActionDispatcher.dispatch(
            bot=self.bot, guild=self.guild, user=self.owner_member, channel=self.channel, task=task_s, session=session
        )
        self.assertTrue(res_s.success)
        mock_player.skip.assert_called_once()


if __name__ == "__main__":
    unittest.main()
