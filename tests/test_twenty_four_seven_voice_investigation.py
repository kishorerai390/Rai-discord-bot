"""
Tests for 24/7 Voice Disconnect Investigation & Fixes.

Covers all 7 required scenarios from the investigation prompt:
1. 24/7 enabled + empty queue -> remain connected.
2. 24/7 enabled + paused player -> remain connected.
3. 24/7 enabled + inactivity watchdog -> no automatic disconnect.
4. 24/7 disabled + normal idle conditions -> existing cleanup still works.
5. Unexpected voice disconnect + 24/7 enabled -> bounded recovery is attempted.
6. User-initiated disconnect -> reconnect logic does not fight the user's action.
7. Multiple watchdogs or repeated events -> no duplicate reconnect loops.
"""

import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from music_bot.database import MusicDatabase, MusicGuildSettings
from music_bot.services.player_service import MusicPlayerService
from music_bot.services.session_memory_service import MusicSessionMemoryService
from music_bot.services.session_service import (
    GuildMusicSession,
    PlaybackState,
    QueuedTrack,
    SessionManager,
)
from music_bot.services.voice_service import VoiceManager


class TestTwentyFourSevenVoiceInvestigation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_path = Path(f"test_247_investigation_{os.getpid()}_{id(self)}.db")
        self.db = MusicDatabase(self.db_path)
        await self.db.connect()

        self.guild_id = 999111222333
        self.channel_id = 888777666555

        # Configure guild settings with 24/7 enabled by default
        settings = MusicGuildSettings(
            guild_id=self.guild_id,
            twenty_four_seven_enabled=True,
            twenty_four_seven_channel_id=self.channel_id,
            default_volume=100,
        )
        await self.db.update_guild_settings(settings)

        # Mock Bot
        self.bot = MagicMock()
        self.bot.db = self.db
        self.bot.is_ready.return_value = True

        # Mock Guild and Channel
        self.channel = MagicMock()
        self.channel.id = self.channel_id
        self.channel.name = "247-lounge"
        self.channel.members = []

        self.guild = MagicMock()
        self.guild.id = self.guild_id
        self.guild.name = "Test Guild"
        self.guild.get_channel.return_value = self.channel
        self.guild.fetch_channel = AsyncMock(return_value=self.channel)
        self.bot.get_guild.return_value = self.guild
        self.bot.fetch_guild = AsyncMock(return_value=self.guild)

        # Mock Voice Client
        self.vc = MagicMock()
        self.vc.is_connected.return_value = True
        self.vc.is_playing.return_value = False
        self.vc.is_paused.return_value = False
        self.vc.channel = self.channel
        self.vc.guild = self.guild
        self.vc.disconnect = AsyncMock()
        self.vc.stop = MagicMock()

        self.guild.voice_client = self.vc

        # Session Manager and Guild Session
        self.session_manager = SessionManager()
        self.session = GuildMusicSession(self.guild_id)
        self.session.voice_client = self.vc
        self.session.twenty_four_seven = True
        self.session_manager._sessions[self.guild_id] = self.session
        self.bot.session_manager = self.session_manager

    async def asyncTearDown(self):
        if self.session.auto_leave_task and not self.session.auto_leave_task.done():
            self.session.auto_leave_task.cancel()
        await self.db.close()
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except OSError:
                pass

    async def test_01_twenty_four_seven_enabled_empty_queue_remains_connected(self):
        """1. 24/7 enabled + empty queue -> remain connected without disconnecting voice."""
        self.session.twenty_four_seven = True
        self.session.queue.clear()
        self.session.current_track = None

        # Stop playback with 24/7 enabled
        success, msg = await MusicPlayerService.stop(self.bot, self.session)
        self.assertTrue(success)

        # Voice client must NOT be disconnected
        self.vc.disconnect.assert_not_called()
        self.assertIsNotNone(self.session.voice_client)
        self.assertTrue(self.session.voice_client.is_connected())

        # Playback stop was intentional, but voice disconnect must NOT be intentional
        self.assertTrue(self.session.is_intentional_stop)
        self.assertFalse(self.session.is_intentional_disconnect)

    async def test_02_twenty_four_seven_enabled_paused_player_remains_connected(self):
        """2. 24/7 enabled + paused player -> remain connected."""
        self.session.twenty_four_seven = True
        self.vc.is_paused.return_value = True
        self.session.state = PlaybackState.PAUSED

        # Schedule auto leave while paused
        VoiceManager.schedule_auto_leave(self.bot, self.session, timeout=1)

        # In-memory guard should bypass auto leave creation immediately
        self.assertIsNone(self.session.auto_leave_task)
        self.vc.disconnect.assert_not_called()
        self.assertTrue(self.session.voice_client.is_connected())

    async def test_03_twenty_four_seven_enabled_inactivity_watchdog_no_auto_disconnect(self):
        """3. 24/7 enabled + inactivity watchdog -> no automatic disconnect even when channel has 0 humans."""
        # Voice channel has 0 humans
        self.channel.members = []
        self.session.twenty_four_seven = True

        # Run _auto_leave_worker directly with timeout=0
        await VoiceManager._auto_leave_worker(self.bot, self.session, timeout=0, task_id="test-watchdog")

        # Must abort disconnect because 24/7 is active
        self.vc.disconnect.assert_not_called()
        self.assertIsNotNone(self.session.voice_client)

    async def test_04_twenty_four_seven_disabled_normal_idle_conditions_disconnects(self):
        """4. 24/7 disabled + normal idle conditions -> existing cleanup still works."""
        # Disable 24/7 in database settings and session
        settings = await self.db.get_guild_settings(self.guild_id)
        settings.twenty_four_seven_enabled = False
        settings.twenty_four_seven_channel_id = None
        await self.db.update_guild_settings(settings)
        self.session.twenty_four_seven = False

        # Channel has 0 human members
        self.channel.members = []

        # Run _auto_leave_worker with timeout=0
        await VoiceManager._auto_leave_worker(self.bot, self.session, timeout=0, task_id="test-cleanup")

        # Disconnect MUST be called when 24/7 is disabled
        self.vc.disconnect.assert_called_once()
        self.assertIsNone(self.session.voice_client)
        self.assertEqual(self.session.state, PlaybackState.IDLE)

    async def test_05_unexpected_voice_disconnect_with_twenty_four_seven_bounded_recovery(self):
        """5. Unexpected voice disconnect + 24/7 enabled -> bounded recovery is attempted."""
        # Setup: Bot dropped voice connection unexpectedly
        self.session.voice_client = None
        self.session.is_intentional_disconnect = False
        self.session.is_intentional_stop = False

        # Ensure database confirms 24/7 enabled
        settings = await self.db.get_guild_settings(self.guild_id)
        self.assertTrue(settings.twenty_four_seven_enabled)

        # Mock VoiceManager.join_voice_channel to succeed
        reconnected_vc = MagicMock()
        reconnected_vc.is_connected.return_value = True

        with patch.object(VoiceManager, "join_voice_channel", AsyncMock(return_value=reconnected_vc)) as mock_join, \
             patch("asyncio.sleep", AsyncMock()):
            # Trigger unexpected disconnect handler
            await MusicSessionMemoryService.handle_unexpected_disconnect(
                self.bot, self.guild_id, channel_id=self.channel_id
            )

            # Assert join_voice_channel was called with target channel
            mock_join.assert_called_once()
            call_kwargs = mock_join.call_args.kwargs
            self.assertEqual(call_kwargs.get("target_channel"), self.channel)

    async def test_06_user_initiated_disconnect_does_not_fight_user(self):
        """6. User-initiated disconnect -> reconnect logic does not fight the user's action."""
        # User explicitly disconnects
        self.session.is_intentional_disconnect = True
        self.session.is_intentional_stop = True
        self.session.voice_client = None

        with patch.object(VoiceManager, "join_voice_channel", AsyncMock()) as mock_join:
            # Trigger unexpected disconnect handler
            await MusicSessionMemoryService.handle_unexpected_disconnect(
                self.bot, self.guild_id, channel_id=self.channel_id
            )

            # Must NOT attempt to rejoin because user intentionally disconnected
            mock_join.assert_not_called()

    async def test_07_multiple_watchdogs_repeated_events_no_duplicate_reconnect_loops(self):
        """7. Multiple watchdogs or repeated events -> no duplicate reconnect loops."""
        self.session.voice_client = None
        self.session.is_intentional_disconnect = False

        call_count = 0

        async def fake_join(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            mock_vc = MagicMock()
            mock_vc.is_connected.return_value = True
            return mock_vc

        with patch.object(VoiceManager, "join_voice_channel", side_effect=fake_join), \
             patch("asyncio.sleep", AsyncMock()):
            # Fire multiple concurrent disconnect events simultaneously
            await asyncio.gather(
                MusicSessionMemoryService.handle_unexpected_disconnect(self.bot, self.guild_id, channel_id=self.channel_id),
                MusicSessionMemoryService.handle_unexpected_disconnect(self.bot, self.guild_id, channel_id=self.channel_id),
                MusicSessionMemoryService.handle_unexpected_disconnect(self.bot, self.guild_id, channel_id=self.channel_id),
            )

            # Reconnection lock / tracking ensures only 1 recovery flow executed
            self.assertEqual(call_count, 1)


if __name__ == "__main__":
    unittest.main()
