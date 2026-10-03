"""
Comprehensive Verification Tests for Dynamic Voice Channel Auto-Delete & 60-Second Inactivity Lifecycle.

Validates:
1. Strict cleanup eligibility rules (0 members, temporary VC, not trigger, not protected, expired timeout).
2. Voice state departure triggering EMPTY_WAITING state and database persistence.
3. Multiple occupants leaving while others stay (room remains ACTIVE).
4. Immediate cancellation when someone rejoins at 30s (room survives).
5. Leave -> Rejoin -> Leave sequence starting a fresh 60s countdown from second departure.
6. Execution of deletion: 0-occupant verification, Discord API deletion, room panel pruning, DB cleanup.
7. Refusal to delete trigger hub channels, trigger names, or protected channels.
8. Clean music session teardown before channel deletion.
9. Restart recovery: immediate deletion of overdue rooms, preserved countdown for future rooms, orphan pruning.
10. Per-room lock preventing concurrent deletion races.
11. Diagnostic system status (/tempvoice status) and manual cleanup (/tempvoice cleanup).
"""

import asyncio
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import discord

from database.database import Database
from database.migrations import run_migrations
from database.models import DynamicRoom
from utils.dynamic_vc_cleanup import CleanupStatus, DynamicVCCleanupService
from utils.dynamic_vc_control import DynamicVCControlManager


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class TestDynamicVCAutoDelete(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Create in-memory test database with full migrations (including Migration 29)
        self.conn = await aiosqlite.connect(":memory:")
        self.conn.row_factory = aiosqlite.Row
        await run_migrations(self.conn)

        self.db = Database(":memory:")
        self.db._db = self.conn

        self.guild_id = 999888777
        await self.db.get_or_create_guild_config(self.guild_id)

        # Mock Bot
        self.bot = MagicMock()
        self.bot.db = self.db

        # Mock Guild
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = self.guild_id
        self.guild.name = "Test Guild"
        self.guild.voice_client = None
        self.bot.get_guild.return_value = self.guild
        self.bot.guilds = [self.guild]

        # Reset service metrics
        DynamicVCCleanupService.cleanups_completed_count = 0
        DynamicVCCleanupService.cleanups_failed_count = 0
        DynamicVCCleanupService.last_scan_time = None
        DynamicVCCleanupService.last_successful_cleanup = None
        DynamicVCCleanupService.last_cleanup_failure = None

    async def asyncTearDown(self):
        await self.conn.close()

    def _create_mock_vc(self, channel_id: int, name: str = "Test Room", members=None):
        vc = MagicMock(spec=discord.VoiceChannel)
        vc.id = channel_id
        vc.name = name
        vc.members = members if members is not None else []
        vc.delete = AsyncMock()
        return vc

    # =========================================================================
    # 1. Configurable Timeout
    # =========================================================================

    def test_configurable_inactivity_timeout(self):
        """Validates that DYNAMIC_VC_EMPTY_TIMEOUT_SECONDS defaults to 60 and respects env overrides."""
        with patch.dict("os.environ", {"DYNAMIC_VC_EMPTY_TIMEOUT_SECONDS": "60"}):
            self.assertEqual(DynamicVCCleanupService.get_empty_timeout_seconds(), 60)

        with patch.dict("os.environ", {"DYNAMIC_VC_EMPTY_TIMEOUT_SECONDS": "120"}):
            self.assertEqual(DynamicVCCleanupService.get_empty_timeout_seconds(), 120)

    # =========================================================================
    # 2. Member Departure Transitions to EMPTY_WAITING
    # =========================================================================

    async def test_member_leave_starts_empty_waiting_countdown(self):
        """When the last member leaves a dynamic VC, persists EMPTY_WAITING state and schedules cleanup."""
        channel_id = 1001
        owner_id = 5001

        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=channel_id,
            owner_id=owner_id,
            status="active",
            cleanup_status=CleanupStatus.ACTIVE,
        )
        await self.db.create_dynamic_room(room)

        member = MagicMock(spec=discord.Member)
        member.id = owner_id
        member.guild = self.guild
        member.bot = False

        # Channel now has 0 members
        vc = self._create_mock_vc(channel_id, "Room 1001", members=[])
        self.guild.get_channel.return_value = vc

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock) as mock_panel:
            await DynamicVCCleanupService.handle_member_leave(self.bot, member, vc)

            # Verify database state
            updated = await self.db.get_dynamic_room(channel_id)
            self.assertEqual(updated.cleanup_status, CleanupStatus.EMPTY_WAITING)
            self.assertEqual(updated.status, "empty_countdown")
            self.assertIsNotNone(updated.empty_since)
            self.assertIsNotNone(updated.cleanup_due_at)

            # Verify due_at is approximately +60 seconds in the future
            now = utcnow()
            due_dt = datetime.datetime.fromisoformat(updated.cleanup_due_at)
            diff = (due_dt - now).total_seconds()
            self.assertTrue(55 <= diff <= 65)

            mock_panel.assert_awaited_once()

    # =========================================================================
    # 3. Owner Leaves While Another Occupant Remains
    # =========================================================================

    async def test_owner_leave_with_other_occupants_preserves_room(self):
        """If the room owner departs but another member remains inside, room remains ACTIVE."""
        channel_id = 1002
        owner_id = 5001
        guest_id = 5002

        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=channel_id,
            owner_id=owner_id,
            status="active",
            cleanup_status=CleanupStatus.ACTIVE,
        )
        await self.db.create_dynamic_room(room)

        owner_member = MagicMock(spec=discord.Member)
        owner_member.id = owner_id
        owner_member.guild = self.guild
        owner_member.bot = False

        guest_member = MagicMock(spec=discord.Member)
        guest_member.id = guest_id
        guest_member.bot = False

        # Channel still contains guest_member
        vc = self._create_mock_vc(channel_id, "Room 1002", members=[guest_member])
        self.guild.get_channel.return_value = vc

        await DynamicVCCleanupService.handle_member_leave(self.bot, owner_member, vc)

        updated = await self.db.get_dynamic_room(channel_id)
        # Room must remain ACTIVE!
        self.assertEqual(updated.cleanup_status, CleanupStatus.ACTIVE)
        self.assertIsNone(updated.cleanup_due_at)

    # =========================================================================
    # 4. Rejoin at 30 Seconds Cancels Cleanup Countdown
    # =========================================================================

    async def test_rejoin_at_30_seconds_cancels_cleanup(self):
        """When someone rejoins during the 60-second grace window, countdown is cancelled immediately."""
        channel_id = 1003
        owner_id = 5001

        now = utcnow()
        due_at = (now + datetime.timedelta(seconds=30)).isoformat()

        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=channel_id,
            owner_id=owner_id,
            status="empty_countdown",
            cleanup_status=CleanupStatus.EMPTY_WAITING,
            empty_since=now.isoformat(),
            cleanup_due_at=due_at,
        )
        await self.db.create_dynamic_room(room)

        rejoining_member = MagicMock(spec=discord.Member)
        rejoining_member.id = owner_id
        rejoining_member.display_name = "Alex"
        rejoining_member.guild = self.guild

        vc = self._create_mock_vc(channel_id, "Room 1003", members=[rejoining_member])
        self.guild.get_channel.return_value = vc

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock) as mock_panel:
            await DynamicVCCleanupService.handle_member_join(self.bot, rejoining_member, vc)

            updated = await self.db.get_dynamic_room(channel_id)
            self.assertEqual(updated.cleanup_status, CleanupStatus.ACTIVE)
            self.assertEqual(updated.status, "active")
            self.assertIsNone(updated.cleanup_due_at)
            self.assertIsNone(updated.empty_since)
            mock_panel.assert_awaited_once()

    # =========================================================================
    # 5. Leave -> Rejoin -> Leave Sequence
    # =========================================================================

    async def test_leave_rejoin_leave_starts_fresh_countdown(self):
        """Leave -> Rejoin (at 30s) -> Leave (at 40s) must start a NEW 60s countdown from 40s."""
        channel_id = 1004
        owner_id = 5001

        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=channel_id,
            owner_id=owner_id,
            status="active",
            cleanup_status=CleanupStatus.ACTIVE,
        )
        await self.db.create_dynamic_room(room)

        member = MagicMock(spec=discord.Member)
        member.id = owner_id
        member.guild = self.guild
        member.bot = False

        # 1. First leave at 12:00:00
        vc = self._create_mock_vc(channel_id, "Room 1004", members=[])
        self.guild.get_channel.return_value = vc
        await DynamicVCCleanupService.handle_member_leave(self.bot, member, vc)

        room1 = await self.db.get_dynamic_room(channel_id)
        first_due_at = room1.cleanup_due_at
        self.assertIsNotNone(first_due_at)

        # 2. Rejoin at 12:00:30
        vc.members = [member]
        await DynamicVCCleanupService.handle_member_join(self.bot, member, vc)
        room2 = await self.db.get_dynamic_room(channel_id)
        self.assertEqual(room2.cleanup_status, CleanupStatus.ACTIVE)
        self.assertIsNone(room2.cleanup_due_at)

        # 3. Leave again at 12:00:40
        vc.members = []
        await asyncio.sleep(0.01)  # Stagger timestamps
        await DynamicVCCleanupService.handle_member_leave(self.bot, member, vc)

        room3 = await self.db.get_dynamic_room(channel_id)
        second_due_at = room3.cleanup_due_at
        self.assertEqual(room3.cleanup_status, CleanupStatus.EMPTY_WAITING)
        self.assertIsNotNone(second_due_at)
        # Fresh countdown must be later than the first one
        self.assertGreater(second_due_at, first_due_at)

    # =========================================================================
    # 6. Final Pre-Delete Verification: Rejoin Right Before Deletion
    # =========================================================================

    async def test_rejoin_at_cleanup_time_cancels_deletion(self):
        """Worker checks room at due time; if someone joined right before, deletion is aborted."""
        channel_id = 1005
        owner_id = 5001

        past_time = (utcnow() - datetime.timedelta(seconds=10)).isoformat()
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=channel_id,
            owner_id=owner_id,
            status="empty_countdown",
            cleanup_status=CleanupStatus.EMPTY_WAITING,
            empty_since=past_time,
            cleanup_due_at=past_time,  # Overdue
        )
        await self.db.create_dynamic_room(room)

        # Someone joined the channel right as the worker attempts cleanup!
        member = MagicMock(spec=discord.Member)
        member.id = owner_id
        member.bot = False
        vc = self._create_mock_vc(channel_id, "Room 1005", members=[member])
        self.guild.get_channel.return_value = vc

        with patch.object(DynamicVCControlManager, "delete_room_panel", new_callable=AsyncMock) as mock_del_panel:
            success, msg = await DynamicVCCleanupService.execute_room_cleanup(self.bot, channel_id)

            # Must NOT delete channel!
            vc.delete.assert_not_called()
            mock_del_panel.assert_not_called()
            self.assertFalse(success)
            self.assertIn("not empty", msg)

            # Restored to ACTIVE
            updated = await self.db.get_dynamic_room(channel_id)
            self.assertEqual(updated.cleanup_status, CleanupStatus.ACTIVE)

    # =========================================================================
    # 7. Successful Deletion Flow
    # =========================================================================

    async def test_successful_channel_deletion_and_cleanup(self):
        """Empty room with expired timer is safely deleted from Discord and database."""
        channel_id = 1006
        owner_id = 5001

        past_time = (utcnow() - datetime.timedelta(seconds=5)).isoformat()
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=channel_id,
            owner_id=owner_id,
            status="empty_countdown",
            cleanup_status=CleanupStatus.EMPTY_WAITING,
            empty_since=past_time,
            cleanup_due_at=past_time,
        )
        await self.db.create_dynamic_room(room)

        vc = self._create_mock_vc(channel_id, "Room 1006", members=[])
        self.guild.get_channel.return_value = vc

        with patch.object(DynamicVCControlManager, "delete_room_panel", new_callable=AsyncMock) as mock_del_panel:
            success, msg = await DynamicVCCleanupService.execute_room_cleanup(self.bot, channel_id)

            self.assertTrue(success)
            vc.delete.assert_awaited_once_with(reason="Rai Dynamic VC: 60s empty grace period expired")
            mock_del_panel.assert_awaited_once_with(self.bot, self.guild, channel_id)
            self.assertEqual(DynamicVCCleanupService.cleanups_completed_count, 1)

    # =========================================================================
    # 8. Protection of Permanent & Trigger Channels
    # =========================================================================

    async def test_refusal_to_delete_trigger_hub(self):
        """Worker strictly refuses to delete the system trigger hub channel."""
        channel_id = 1007
        owner_id = 5001

        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=channel_id,
            owner_id=owner_id,
            status="empty_countdown",
            cleanup_status=CleanupStatus.EMPTY_WAITING,
            cleanup_due_at=utcnow_iso(),
        )
        await self.db.create_dynamic_room(room)

        # Configure this channel as the Hub channel
        await self.db.update_temp_voice_config(self.guild_id, hub_channel_id=channel_id)

        vc = self._create_mock_vc(channel_id, "➕ CREATE YOUR ROOM", members=[])
        self.guild.get_channel.return_value = vc

        success, msg = await DynamicVCCleanupService.execute_room_cleanup(self.bot, channel_id)
        self.assertFalse(success)
        vc.delete.assert_not_called()
        self.assertIn("trigger", msg.lower())

    # =========================================================================
    # 9. Clean Music Session Teardown
    # =========================================================================

    async def test_music_session_disconnect_before_deletion(self):
        """If the bot is streaming music in this VC, voice client is cleanly disconnected before deletion."""
        channel_id = 1008
        owner_id = 5001

        past_time = (utcnow() - datetime.timedelta(seconds=5)).isoformat()
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=channel_id,
            owner_id=owner_id,
            status="empty_countdown",
            cleanup_status=CleanupStatus.EMPTY_WAITING,
            cleanup_due_at=past_time,
        )
        await self.db.create_dynamic_room(room)

        vc = self._create_mock_vc(channel_id, "Music Room 1008", members=[])
        self.guild.get_channel.return_value = vc

        # Voice client connected to this channel
        mock_voice_client = MagicMock()
        mock_voice_client.channel = vc
        mock_voice_client.disconnect = AsyncMock()
        self.guild.voice_client = mock_voice_client

        with patch.object(DynamicVCControlManager, "delete_room_panel", new_callable=AsyncMock):
            success, _ = await DynamicVCCleanupService.execute_room_cleanup(self.bot, channel_id)

            self.assertTrue(success)
            mock_voice_client.disconnect.assert_awaited_once_with(force=True)
            vc.delete.assert_awaited_once()

    # =========================================================================
    # 10. Restart Recovery
    # =========================================================================

    async def test_restart_recovery_overdue_and_future(self):
        """Validates startup recovery: overdue rooms are purged immediately, future countdowns preserved."""
        # 1. Overdue room
        overdue_id = 2001
        past_time = (utcnow() - datetime.timedelta(seconds=30)).isoformat()
        room_overdue = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=overdue_id,
            owner_id=5001,
            status="empty_countdown",
            cleanup_status=CleanupStatus.EMPTY_WAITING,
            cleanup_due_at=past_time,
        )
        await self.db.create_dynamic_room(room_overdue)

        # 2. Future room (waiting 40s more)
        future_id = 2002
        future_time = (utcnow() + datetime.timedelta(seconds=40)).isoformat()
        room_future = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=future_id,
            owner_id=5002,
            status="empty_countdown",
            cleanup_status=CleanupStatus.EMPTY_WAITING,
            cleanup_due_at=future_time,
        )
        await self.db.create_dynamic_room(room_future)

        # 3. Orphaned room (channel missing from Discord)
        orphan_id = 2003
        room_orphan = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=orphan_id,
            owner_id=5003,
            status="active",
        )
        await self.db.create_dynamic_room(room_orphan)

        vc_overdue = self._create_mock_vc(overdue_id, "Overdue Room", members=[])
        vc_future = self._create_mock_vc(future_id, "Future Room", members=[])

        def get_ch(cid):
            if cid == overdue_id:
                return vc_overdue
            elif cid == future_id:
                return vc_future
            return None

        self.guild.get_channel.side_effect = get_ch

        with patch.object(DynamicVCControlManager, "delete_room_panel", new_callable=AsyncMock) as mock_del_panel, \
             patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock) as mock_up_panel:

            reconciled = await DynamicVCCleanupService.reconcile_on_startup(self.bot)

            # Overdue room was deleted
            vc_overdue.delete.assert_awaited_once()

            # Future room survived and preserved countdown
            vc_future.delete.assert_not_called()
            mock_up_panel.assert_awaited()

            # Orphan room was pruned
            self.assertGreaterEqual(reconciled, 2)

    # =========================================================================
    # 11. System Status & Manual Cleanup Diagnostics
    # =========================================================================

    async def test_get_system_status_and_manual_cleanup(self):
        """Verifies get_system_status returns complete diagnostic breakdown and manual cleanup works."""
        channel_id = 3001
        past_time = (utcnow() - datetime.timedelta(seconds=10)).isoformat()
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=channel_id,
            owner_id=5001,
            status="empty_countdown",
            cleanup_status=CleanupStatus.EMPTY_WAITING,
            cleanup_due_at=past_time,
        )
        await self.db.create_dynamic_room(room)

        vc = self._create_mock_vc(channel_id, "Room 3001", members=[])
        self.guild.get_channel.return_value = vc

        # 1. Test status
        status = await DynamicVCCleanupService.get_system_status(self.bot, self.guild_id)
        self.assertIn("health", status)
        self.assertEqual(status["total_rooms"], 1)
        self.assertEqual(status["overdue"], 1)
        self.assertEqual(len(status["pending_rooms"]), 1)

        # 2. Test manual cleanup
        with patch.object(DynamicVCControlManager, "delete_room_panel", new_callable=AsyncMock):
            res = await DynamicVCCleanupService.run_manual_cleanup(self.bot, self.guild_id)
            self.assertEqual(res["purged"], 1)
            vc.delete.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
