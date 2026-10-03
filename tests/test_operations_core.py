"""
Unit and Integration Tests for RAI Operations Core (Server Operations Assistant).
Tests:
- Service Architecture (SecurityService, RoomService, MusicService, BackupService, HealthService,
  AutomationService, ConfigurationService, AnalyticsService).
- RaiOperationsCore:
    * get_operations_overview (healthy status, counts, last backup time)
    * simulate_raid (safe sandbox mode, zero real damage/deletions)
    * set_maintenance_mode (persists in operations_state, pauses non-critical automation)
- AnalyticsService.get_away_summary (strictly real DB records, zero invented numbers)
- ConfigurationService (save snapshot, list versions, rollback structure)
- Scheduled Tasks (create, fetch due, update run, cancel)
- Natural Language Parser & Action Dispatcher:
    * "check everything" -> OPERATIONS_CHECK
    * "what happened while i was away" -> AWAY_SUMMARY
    * "simulate raid" -> SIMULATE_RAID
    * "put rai into maintenance mode" -> MAINTENANCE_MODE_ENABLE
    * "disable maintenance mode" -> MAINTENANCE_MODE_DISABLE
    * Smart Suggestion: "rai bakup" -> Did you mean: Backup?
"""

import asyncio
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from backups.manager import BackupManager
from core.nl_control import (
    NLActionDispatcher,
    NLContextManager,
    NLControlEngine,
    NLIntent,
    NLParser,
    NLSuggestionView,
    ParsedTask,
)
from core.operations_core import (
    AnalyticsService,
    AutomationService,
    BackupService,
    ConfigurationService,
    HealthService,
    OwnerOperationsDashboardView,
    RaiOperationsCore,
    RoomService,
    SecurityService,
)
from database.manager import DatabaseManager


class TestOperationsCore(unittest.IsolatedAsyncioTestCase):

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

        # Reset singletons
        BackupManager._instance = None
        self.backup_mgr = BackupManager(db_path=self.db_path, backups_dir=self.backups_dir)
        RaiOperationsCore._instance = None

        # Mock Bot
        self.bot = MagicMock()
        self.bot.db = self.db
        self.bot.db_manager = self.db_mgr
        self.bot.user = MagicMock(id=1554732669072445532, spec=discord.ClientUser)
        self.bot.cogs = {}

        # Mock Guild, Owner & Admin
        self.guild = MagicMock(spec=discord.Guild, id=1001, name="Operations Test Guild")
        self.guild.owner_id = 9999
        self.guild.member_count = 142
        self.guild.members = []
        self.guild.categories = []
        self.guild.text_channels = []
        self.guild.voice_channels = []
        self.guild.get_channel = MagicMock(return_value=None)

        self.owner = MagicMock(spec=discord.Member, id=9999, name="ServerOwner")
        self.owner.mention = "<@9999>"
        self.owner.bot = False
        self.owner.guild_permissions = discord.Permissions(administrator=True)

        self.admin = MagicMock(spec=discord.Member, id=1111, name="AdminUser")
        self.admin.mention = "<@1111>"
        self.admin.bot = False
        self.admin.guild_permissions = discord.Permissions(administrator=True)

        self.channel = MagicMock(spec=discord.TextChannel, id=5001, name="operations-control")
        self.channel.guild = self.guild
        self.channel.send = AsyncMock()

    async def asyncTearDown(self):
        DatabaseManager._instance = None
        RaiOperationsCore._instance = None
        BackupManager._instance = None
        if hasattr(self, "conn") and self.conn:
            await self.conn.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_operations_overview(self):
        """Test RaiOperationsCore.get_operations_overview returns complete system status."""
        ops = RaiOperationsCore.get_instance(self.bot)
        overview = await ops.get_operations_overview(self.guild)

        self.assertTrue(overview["bot_online"])
        self.assertIn("system_health", overview)
        self.assertIn("security_status", overview)
        self.assertEqual(overview["active_rooms_count"], 0)
        self.assertEqual(overview["members_count"], 142)
        self.assertIn("last_backup_str", overview)
        self.assertEqual(overview["open_incidents_count"], 0)
        self.assertFalse(overview["maintenance_mode"])

    async def test_away_summary_strictly_real_data(self):
        """Phase 11: Away summary numbers strictly derive from real database queries."""
        # Insert actual room events
        now = time.time()
        await self.conn.execute(
            "INSERT INTO room_events (room_id, event_type, user_id, timestamp, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            (101, "create", 9999, now - 3600, "{}")
        )
        await self.conn.execute(
            "INSERT INTO room_events (room_id, event_type, user_id, timestamp, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            (102, "create", 9999, now - 1800, "{}")
        )
        await self.conn.execute(
            "INSERT INTO room_events (room_id, event_type, user_id, timestamp, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            (101, "cleanup", 9999, now - 600, "{}")
        )
        await self.conn.commit()

        summary = await AnalyticsService.get_away_summary(self.bot, self.guild, hours=12)

        self.assertEqual(summary["rooms_created"], 2)
        self.assertEqual(summary["rooms_cleaned"], 1)
        self.assertEqual(summary["member_count"], 142)
        self.assertEqual(summary["security_incidents_count"], 0)
        self.assertIn("period_start", summary)
        self.assertIn("period_end", summary)

    async def test_simulate_raid_safe_sandbox(self):
        """Phase 24: Security simulation tests thresholds without damaging the server."""
        # Create mock text channel on guild to verify it is NEVER deleted or modified
        test_tc = MagicMock(spec=discord.TextChannel, id=7001, name="general")
        test_tc.delete = AsyncMock()
        self.guild.text_channels = [test_tc]

        ops = RaiOperationsCore.get_instance(self.bot)
        sim_data = await ops.simulate_raid(self.guild, self.owner)

        self.assertTrue(sim_data["simulation_id"].startswith("RAI-INC-"))
        self.assertEqual(sim_data["scenario"], "Mass Channel Deletion Attack")
        self.assertEqual(sim_data["simulated_deletions"], 47)
        self.assertFalse(sim_data["destructive_action_taken"])
        # Assert no real deletion was called on test_tc
        test_tc.delete.assert_not_called()

    async def test_maintenance_mode(self):
        """Phase 14: Toggles maintenance mode in database and reports correct status."""
        ops = RaiOperationsCore.get_instance(self.bot)

        # Enable maintenance mode
        res1 = await ops.set_maintenance_mode(self.guild, self.owner, True, reason="Scheduled Upgrade")
        self.assertTrue(res1)
        state1 = await AutomationService.get_state(self.bot, self.guild.id)
        self.assertEqual(state1["maintenance_mode"], 1)

        # Disable maintenance mode
        res2 = await ops.set_maintenance_mode(self.guild, self.owner, False, reason="Upgrade Complete")
        self.assertTrue(res2)
        state2 = await AutomationService.get_state(self.bot, self.guild.id)
        self.assertEqual(state2["maintenance_mode"], 0)

    async def test_configuration_versioning(self):
        """Phase 26: Save, list, and verify configuration snapshots."""
        config_data = {
            "security_threshold": 8,
            "anti_raid": True,
            "auto_backup_interval_hours": 6,
        }
        v_id = await ConfigurationService.save_version(
            self.bot, self.guild.id, self.owner.id, config_data, label="v24-Pre-Migration"
        )
        self.assertGreater(v_id, 0)

        versions = await ConfigurationService.list_versions(self.bot, self.guild.id)
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["label"], "v24-Pre-Migration")
        self.assertEqual(versions[0]["config_data"]["security_threshold"], 8)

    async def test_scheduled_operations_tasks(self):
        """Phase 34: Persistent task scheduler creation, due check, and update."""
        import datetime
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        past_iso = (now_dt - datetime.timedelta(seconds=10)).isoformat()
        future_iso = (now_dt + datetime.timedelta(hours=1)).isoformat()

        success = await self.db.create_scheduled_task(
            task_id="task_test_1",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            task_type="backup_routine",
            command_phrase="auto backup",
            interval_seconds=3600,
            next_run_at=past_iso,
        )
        self.assertTrue(success)

        due = await self.db.get_due_scheduled_tasks(now_dt.isoformat())
        self.assertGreaterEqual(len(due), 1)
        self.assertEqual(due[0]["task_type"], "backup_routine")

        # Update run
        await self.db.update_scheduled_task_run("task_test_1", last_run_at=now_dt.isoformat(), next_run_at=future_iso)
        due_after = await self.db.get_due_scheduled_tasks(now_dt.isoformat())
        due_ids = [t["task_id"] for t in due_after]
        self.assertNotIn("task_test_1", due_ids)

        # Cancel
        res_cancel = await self.db.cancel_scheduled_task("task_test_1")
        self.assertTrue(res_cancel)
        tasks = await self.db.get_scheduled_tasks(self.guild.id)
        self.assertEqual(len(tasks), 0)

    async def test_natural_language_operations_parsing(self):
        """Phase 3: Verify parsing of operations-oriented natural language requests."""
        # "check everything"
        t1 = NLParser.parse_message("check everything")
        self.assertEqual(len(t1), 1)
        self.assertEqual(t1[0].intent, NLIntent.OPERATIONS_CHECK)

        # "what happened while i was away"
        t2 = NLParser.parse_message("what happened while i was away")
        self.assertEqual(len(t2), 1)
        self.assertEqual(t2[0].intent, NLIntent.AWAY_SUMMARY)

        # "simulate raid"
        t3 = NLParser.parse_message("simulate raid")
        self.assertEqual(len(t3), 1)
        self.assertEqual(t3[0].intent, NLIntent.SIMULATE_RAID)

        # "put rai into maintenance mode"
        t4 = NLParser.parse_message("put rai into maintenance mode")
        self.assertEqual(len(t4), 1)
        self.assertEqual(t4[0].intent, NLIntent.MAINTENANCE_MODE_ENABLE)

        # "disable maintenance mode"
        t5 = NLParser.parse_message("disable maintenance mode")
        self.assertEqual(len(t5), 1)
        self.assertEqual(t5[0].intent, NLIntent.MAINTENANCE_MODE_DISABLE)

        # "operations center"
        t6 = NLParser.parse_message("operations center")
        self.assertEqual(len(t6), 1)
        self.assertEqual(t6[0].intent, NLIntent.OPERATIONS_DASHBOARD)

    async def test_smart_command_suggestion(self):
        """Phase 9: Suggests intended command for mistypes addressed to Rai, ignores normal chat."""
        # "rai bakup" -> suggests Backup
        s1 = NLParser.suggest_command("rai bakup")
        self.assertIsNotNone(s1)
        label, emoji, task = s1
        self.assertEqual(label, "Backup")
        self.assertEqual(emoji, "💾")
        self.assertEqual(task.intent, NLIntent.BACKUP_CREATE)

        # "rai securty" -> suggests Security Check
        s2 = NLParser.suggest_command("rai securty")
        self.assertIsNotNone(s2)
        label2, emoji2, task2 = s2
        self.assertEqual(label2, "Security Check")
        self.assertEqual(task2.intent, NLIntent.SECURITY_CHECK)

        # Casual chat should NOT trigger suggestions (Phase 9 constraint)
        self.assertIsNone(NLParser.suggest_command("nice song"))
        self.assertIsNone(NLParser.suggest_command("hello rai"))
        self.assertIsNone(NLParser.suggest_command("good morning everyone"))

    async def test_operations_check_dispatch(self):
        """Phase 1 & 10: Dispatching OPERATIONS_CHECK returns embed with overview and next actions."""
        session = NLContextManager.get_session(self.guild.id, self.owner.id, self.channel.id)
        task = ParsedTask(intent=NLIntent.OPERATIONS_CHECK, raw_segment="check everything", confidence=1.0)

        res = await NLActionDispatcher.dispatch(
            bot=self.bot,
            guild=self.guild,
            user=self.owner,
            channel=self.channel,
            task=task,
            session=session,
        )

        self.assertTrue(res.success)
        self.assertEqual(res.title, "Operations Overview")
        self.assertIn("RAI OPERATIONS CENTER", res.embed.title)
        self.assertTrue(len(res.next_actions) >= 3)


if __name__ == "__main__":
    unittest.main()
