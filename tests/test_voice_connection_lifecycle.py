"""
Unit Test Suite for VoiceManager Voice Connection Lifecycle, Concurrency, and Diagnostic Telemetry.
Validates all 14 lifecycle scenarios:
1. Successful voice connection
2. Delayed voice state update
3. Delayed voice server update
4. Missing handshake events
5. WebSocket timeout
6. UDP negotiation failure
7. Permission denial
8. Repeated play commands (coalescing)
9. Superseding connection when target channel changes
10. Connections in multiple guilds (isolation)
11. Cancellation during connection
12. Recovery after a temporary failure
13. Queue preservation after a failed connection
14. Stale voice client cleanup and purge
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import unittest
import discord

from music_bot.services.session_service import GuildMusicSession, PlaybackState
from music_bot.services.voice_service import VoiceManager, VoiceTelemetry


class TestVoiceConnectionLifecycle(unittest.IsolatedAsyncioTestCase):
    """Test suite covering the 5-stage voice connection sequence and concurrency protection."""

    def setUp(self):
        # Reset VoiceManager global state before each test
        VoiceManager._guild_locks.clear()
        VoiceManager._in_flight_tasks.clear()
        VoiceManager._in_flight_channels.clear()
        VoiceManager._telemetry.clear()

        self.guild_id = 123456789
        self.session = GuildMusicSession(self.guild_id)

        # Mock Guild
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = self.guild_id
        self.guild.name = "Test Server"
        self.guild.afk_channel = None
        self.guild.voice_client = None
        self.guild.change_voice_state = AsyncMock()
        self.guild._state = MagicMock()
        self.guild._state._voice_clients = {}

        # Mock Bot Member
        self.bot_member = MagicMock(spec=discord.Member)
        self.guild.me = self.bot_member

        # Mock Voice Channel
        self.voice_channel = MagicMock(spec=discord.VoiceChannel)
        self.voice_channel.id = 987654321
        self.voice_channel.name = "Developers Zone </>"
        self.voice_channel.mention = "<#987654321>"
        self.voice_channel.guild = self.guild
        self.voice_channel.user_limit = 0
        self.voice_channel.members = []

        # Default permissions: Connect=True, Speak=True
        self.perms = MagicMock()
        self.perms.connect = True
        self.perms.speak = True
        self.voice_channel.permissions_for.return_value = self.perms

        # Mock Caller Member
        self.member = MagicMock(spec=discord.Member)
        self.member.guild = self.guild
        self.member.voice = MagicMock()
        self.member.voice.channel = self.voice_channel

        # Mock Text Channel
        self.text_channel = MagicMock(spec=discord.TextChannel)
        self.text_channel.id = 111222333
        self.text_channel.mention = "<#111222333>"

    async def test_01_successful_connection(self):
        """Scenario 1: Verify successful connection sets session state and returns VoiceClient."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True
        mock_vc.channel = self.voice_channel
        self.voice_channel.connect = AsyncMock(return_value=mock_vc)

        vc = await VoiceManager.join_voice_channel(self.member, self.text_channel, self.session)

        self.assertIsNotNone(vc)
        self.assertEqual(vc, mock_vc)
        self.assertEqual(self.session.state, PlaybackState.CONNECTED)
        self.assertIsNone(self.session.last_error)
        self.voice_channel.connect.assert_awaited_once()

        telemetry = VoiceManager.get_telemetry(self.guild_id)
        self.assertIsNotNone(telemetry)
        self.assertTrue(telemetry.success)
        self.assertEqual(telemetry.stage, "Connected")

    async def test_02_delayed_voice_state_update(self):
        """Scenario 2: Gateway voice state update delayed, reports Gateway Voice State Request."""
        try:
            from discord.voice_state import ConnectionFlowState
            flow_state = ConnectionFlowState.set_guild_voice_state
        except ImportError:
            flow_state = None

        mock_conn = MagicMock()
        mock_conn.state = flow_state
        mock_vc = MagicMock()
        mock_vc._connection = mock_conn
        self.guild.voice_client = mock_vc

        stage_name, advice, _ = VoiceManager._inspect_failed_stage(self.guild, asyncio.TimeoutError())
        self.assertEqual(stage_name, "Gateway Voice State Request")
        self.assertIn("Gateway did not acknowledge", advice)

    async def test_03_delayed_voice_server_update(self):
        """Scenario 3: Gateway voice server update delayed, reports Gateway Voice Server Allocation."""
        try:
            from discord.voice_state import ConnectionFlowState
            flow_state = ConnectionFlowState.got_voice_state_update
        except ImportError:
            flow_state = None

        mock_conn = MagicMock()
        mock_conn.state = flow_state
        mock_vc = MagicMock()
        mock_vc._connection = mock_conn
        self.guild.voice_client = mock_vc

        stage_name, advice, _ = VoiceManager._inspect_failed_stage(self.guild, asyncio.TimeoutError())
        self.assertEqual(stage_name, "Gateway Voice Server Allocation")
        self.assertIn("voice server endpoint", advice)

    async def test_04_missing_handshake_events(self):
        """Scenario 4: WebSocket opened but ready payload timed out."""
        try:
            from discord.voice_state import ConnectionFlowState
            flow_state = ConnectionFlowState.websocket_connected
        except ImportError:
            flow_state = None

        mock_conn = MagicMock()
        mock_conn.state = flow_state
        mock_vc = MagicMock()
        mock_vc._connection = mock_conn
        self.guild.voice_client = mock_vc

        stage_name, advice, _ = VoiceManager._inspect_failed_stage(self.guild, asyncio.TimeoutError())
        self.assertEqual(stage_name, "Voice Session Ready Acknowledgment")
        self.assertIn("Ready payload", advice)

    async def test_05_websocket_timeout(self):
        """Scenario 5: WebSocket handshake times out before session establishment."""
        try:
            from discord.voice_state import ConnectionFlowState
            flow_state = ConnectionFlowState.got_both_voice_updates
        except ImportError:
            flow_state = None

        mock_conn = MagicMock()
        mock_conn.state = flow_state
        mock_vc = MagicMock()
        mock_vc._connection = mock_conn
        self.guild.voice_client = mock_vc

        stage_name, advice, _ = VoiceManager._inspect_failed_stage(self.guild, asyncio.TimeoutError())
        self.assertEqual(stage_name, "Voice WebSocket Handshake")
        self.assertIn("Voice WebSocket", advice)
        # Should not falsely claim Region Override is the fix!
        self.assertNotIn("Region Override", advice)

    async def test_06_udp_negotiation_failure(self):
        """Scenario 6: UDP negotiation fails after WebSocket handshake, recommends outbound UDP check."""
        try:
            from discord.voice_state import ConnectionFlowState
            flow_state = ConnectionFlowState.got_websocket_ready
        except ImportError:
            flow_state = None

        mock_conn = MagicMock()
        mock_conn.state = flow_state
        mock_vc = MagicMock()
        mock_vc._connection = mock_conn
        self.guild.voice_client = mock_vc

        stage_name, advice, _ = VoiceManager._inspect_failed_stage(self.guild, asyncio.TimeoutError())
        self.assertEqual(stage_name, "UDP Voice Transport & IP Discovery")
        self.assertIn("outbound UDP", advice)
        self.assertIn("Region Override", advice)

    async def test_07_permission_denial(self):
        """Scenario 7: Permission denial fast-fails without retries."""
        self.perms.connect = False
        self.voice_channel.permissions_for.return_value = self.perms

        vc = await VoiceManager.join_voice_channel(self.member, self.text_channel, self.session)

        self.assertIsNone(vc)
        self.assertIn("Connect", self.session.last_error)
        self.voice_channel.connect.assert_not_called()

    async def test_08_repeated_play_commands_coalesce(self):
        """Scenario 8: Multiple simultaneous play commands coalesce into a single connection task."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True
        mock_vc.channel = self.voice_channel

        async def slow_connect(*args, **kwargs):
            await asyncio.sleep(0.05)
            return mock_vc

        self.voice_channel.connect = AsyncMock(side_effect=slow_connect)

        t1 = asyncio.create_task(VoiceManager.join_voice_channel(self.member, self.text_channel, self.session))
        t2 = asyncio.create_task(VoiceManager.join_voice_channel(self.member, self.text_channel, self.session))
        t3 = asyncio.create_task(VoiceManager.join_voice_channel(self.member, self.text_channel, self.session))

        results = await asyncio.gather(t1, t2, t3)

        self.assertEqual(results[0], mock_vc)
        self.assertEqual(results[1], mock_vc)
        self.assertEqual(results[2], mock_vc)
        self.assertEqual(self.voice_channel.connect.await_count, 1)

    async def test_09_supersede_when_target_channel_changes(self):
        """Scenario 9: If target channel changes while connecting, supersede previous attempt."""
        new_channel = MagicMock(spec=discord.VoiceChannel)
        new_channel.id = 999888777
        new_channel.name = "Music Lounge"
        new_channel.mention = "<#999888777>"
        new_channel.guild = self.guild
        new_channel.user_limit = 0
        new_channel.members = []
        new_channel.permissions_for.return_value = self.perms

        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True
        mock_vc.channel = new_channel

        async def slow_connect_old(*args, **kwargs):
            await asyncio.sleep(0.5)
            return mock_vc

        self.voice_channel.connect = AsyncMock(side_effect=slow_connect_old)
        new_channel.connect = AsyncMock(return_value=mock_vc)

        # Start connecting to channel 1
        t1 = asyncio.create_task(VoiceManager.join_voice_channel(self.member, self.text_channel, self.session))
        await asyncio.sleep(0.01)

        # Caller moves to channel 2 and initiates join
        self.member.voice.channel = new_channel
        vc = await VoiceManager.join_voice_channel(self.member, self.text_channel, self.session)

        self.assertEqual(vc, mock_vc)
        new_channel.connect.assert_awaited_once()

    async def test_10_connections_in_multiple_guilds(self):
        """Scenario 10: Connections in different guilds proceed concurrently without interference."""
        guild2_id = 9876543210
        session2 = GuildMusicSession(guild2_id)

        guild2 = MagicMock(spec=discord.Guild)
        guild2.id = guild2_id
        guild2.afk_channel = None
        guild2.voice_client = None
        guild2.change_voice_state = AsyncMock()
        guild2._state = MagicMock()
        guild2._state._voice_clients = {}

        voice_channel2 = MagicMock(spec=discord.VoiceChannel)
        voice_channel2.id = 888777666
        voice_channel2.name = "Server 2 Voice"
        voice_channel2.guild = guild2
        voice_channel2.user_limit = 0
        voice_channel2.members = []
        voice_channel2.permissions_for.return_value = self.perms

        member2 = MagicMock(spec=discord.Member)
        member2.guild = guild2
        member2.voice = MagicMock()
        member2.voice.channel = voice_channel2

        vc1_mock = MagicMock(spec=discord.VoiceClient)
        vc1_mock.is_connected.return_value = True
        vc1_mock.channel = self.voice_channel

        vc2_mock = MagicMock(spec=discord.VoiceClient)
        vc2_mock.is_connected.return_value = True
        vc2_mock.channel = voice_channel2

        self.voice_channel.connect = AsyncMock(return_value=vc1_mock)
        voice_channel2.connect = AsyncMock(return_value=vc2_mock)

        r1, r2 = await asyncio.gather(
            VoiceManager.join_voice_channel(self.member, self.text_channel, self.session),
            VoiceManager.join_voice_channel(member2, self.text_channel, session2),
        )

        self.assertEqual(r1, vc1_mock)
        self.assertEqual(r2, vc2_mock)

    async def test_11_cancellation_during_connection(self):
        """Scenario 11: Task cancellation during connect cleans up and purges state safely."""
        async def hanging_connect(*args, **kwargs):
            await asyncio.sleep(10.0)

        self.voice_channel.connect = AsyncMock(side_effect=hanging_connect)

        t = asyncio.create_task(VoiceManager.join_voice_channel(self.member, self.text_channel, self.session))
        await asyncio.sleep(0.01)
        t.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await t

        # Confirm in-flight tracking is cleared
        self.assertNotIn(self.guild_id, VoiceManager._in_flight_tasks)

    async def test_12_recovery_after_temporary_failure(self):
        """Scenario 12: Temporary failure on attempt 1 (e.g. ClientException), succeeds on attempt 2."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True
        mock_vc.channel = self.voice_channel

        attempt = 0

        async def fail_once_then_succeed(*args, **kwargs):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise discord.ClientException("Already connected to a voice channel.")
            return mock_vc

        self.voice_channel.connect = AsyncMock(side_effect=fail_once_then_succeed)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            vc = await VoiceManager.join_voice_channel(self.member, self.text_channel, self.session)

        self.assertEqual(vc, mock_vc)
        self.assertEqual(self.voice_channel.connect.await_count, 2)
        self.assertEqual(self.session.state, PlaybackState.CONNECTED)

    async def test_13_queue_preservation_after_failed_connection(self):
        """Scenario 13: Failed connection leaves queue intact in session."""
        # Add tracks to queue
        fake_track = MagicMock()
        fake_track.title = "Kalyani"
        self.session.queue.append(fake_track)

        self.voice_channel.connect = AsyncMock(side_effect=asyncio.TimeoutError)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            vc = await VoiceManager.join_voice_channel(self.member, self.text_channel, self.session)

        self.assertIsNone(vc)
        self.assertEqual(self.session.state, PlaybackState.ERROR)
        # Queue must not be wiped!
        self.assertEqual(len(self.session.queue), 1)
        self.assertEqual(self.session.queue[0].title, "Kalyani")

    async def test_14_stale_voice_client_cleanup(self):
        """Scenario 14: Disconnected/orphaned VoiceClient is cleaned up and purged before connecting."""
        dead_vc = MagicMock(spec=discord.VoiceClient)
        dead_vc.is_connected.return_value = False
        dead_vc.disconnect = AsyncMock()
        dead_vc.cleanup = MagicMock()
        self.guild.voice_client = dead_vc

        fresh_vc = MagicMock(spec=discord.VoiceClient)
        fresh_vc.is_connected.return_value = True
        fresh_vc.channel = self.voice_channel
        self.voice_channel.connect = AsyncMock(return_value=fresh_vc)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            vc = await VoiceManager.join_voice_channel(self.member, self.text_channel, self.session)

        self.assertEqual(vc, fresh_vc)
        dead_vc.disconnect.assert_awaited_once_with(force=True)
        dead_vc.cleanup.assert_called()


if __name__ == "__main__":
    unittest.main()
