"""
Unit Test Suite for VoiceManager Voice Connection Lifecycle, Concurrency, and Diagnostic Telemetry.
Validates:
1. Concurrency singleflight coalescing (multiple simultaneous play requests do NOT spawn competing connections).
2. Existing connection reuse (instant return when already in target channel).
3. Seamless channel move (VoiceClient.move_to when caller is in a different voice channel).
4. Permission rejection (fast-fails with clear error when Connect/Speak permission missing).
5. AFK channel anti-join sentry.
6. Stale client cleanup before reconnecting.
7. Bounded retries and diagnostic reporting on transient timeouts.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import unittest
import discord

from music_bot.services.session_service import GuildMusicSession, PlaybackState
from music_bot.services.voice_service import VoiceManager


class TestVoiceConnectionLifecycle(unittest.IsolatedAsyncioTestCase):
    """Test suite covering the 5-stage voice connection sequence and concurrency protection."""

    def setUp(self):
        # Reset VoiceManager global state before each test
        VoiceManager._guild_locks.clear()
        VoiceManager._in_flight_tasks.clear()

        self.guild_id = 123456789
        self.session = GuildMusicSession(self.guild_id)

        # Mock Guild
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = self.guild_id
        self.guild.name = "Test Server"
        self.guild.afk_channel = None
        self.guild.voice_client = None
        self.guild.change_voice_state = AsyncMock()

        # Mock Bot Member
        self.bot_member = MagicMock(spec=discord.Member)
        self.guild.me = self.bot_member

        # Mock Voice Channel
        self.voice_channel = MagicMock(spec=discord.VoiceChannel)
        self.voice_channel.id = 987654321
        self.voice_channel.name = "Developers Zone </>"
        self.voice_channel.mention = "<#987654321>"
        self.voice_channel.guild = self.guild

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

    async def test_01_successful_connection_first_attempt(self):
        """Verify successful connection sets session state and returns VoiceClient."""
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

    async def test_02_concurrency_singleflight_coalescing(self):
        """Verify multiple simultaneous play requests coalesce into a single connection task."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True
        mock_vc.channel = self.voice_channel

        # Slow connect to simulate network handshake delay
        async def slow_connect(*args, **kwargs):
            await asyncio.sleep(0.05)
            return mock_vc

        self.voice_channel.connect = AsyncMock(side_effect=slow_connect)

        # Launch 3 simultaneous connection requests
        t1 = asyncio.create_task(VoiceManager.join_voice_channel(self.member, self.text_channel, self.session))
        t2 = asyncio.create_task(VoiceManager.join_voice_channel(self.member, self.text_channel, self.session))
        t3 = asyncio.create_task(VoiceManager.join_voice_channel(self.member, self.text_channel, self.session))

        results = await asyncio.gather(t1, t2, t3)

        # All 3 callers must receive the exact same VoiceClient
        self.assertEqual(results[0], mock_vc)
        self.assertEqual(results[1], mock_vc)
        self.assertEqual(results[2], mock_vc)

        # connect() must have been called EXACTLY ONCE despite 3 simultaneous requests!
        self.assertEqual(self.voice_channel.connect.await_count, 1)

    async def test_03_existing_connection_reused_instantly(self):
        """Verify if already connected to target channel, VoiceClient is reused without reconnecting."""
        existing_vc = MagicMock(spec=discord.VoiceClient)
        existing_vc.is_connected.return_value = True
        existing_vc.channel = self.voice_channel
        self.guild.voice_client = existing_vc

        self.voice_channel.connect = AsyncMock()

        vc = await VoiceManager.join_voice_channel(self.member, self.text_channel, self.session)

        self.assertEqual(vc, existing_vc)
        # connect() must NOT be called when already connected
        self.voice_channel.connect.assert_not_called()

    async def test_04_channel_move_when_caller_in_different_channel(self):
        """Verify bot seamlessly moves to caller's channel if already connected elsewhere."""
        old_channel = MagicMock(spec=discord.VoiceChannel)
        old_channel.id = 555555
        old_channel.name = "General Voice"

        existing_vc = MagicMock(spec=discord.VoiceClient)
        existing_vc.is_connected.return_value = True
        existing_vc.channel = old_channel
        existing_vc.move_to = AsyncMock()
        self.guild.voice_client = existing_vc

        vc = await VoiceManager.join_voice_channel(self.member, self.text_channel, self.session)

        self.assertEqual(vc, existing_vc)
        existing_vc.move_to.assert_awaited_once_with(self.voice_channel)

    async def test_05_permission_denial_fast_fails(self):
        """Verify missing Connect or Speak permission fast-fails without retries."""
        self.perms.connect = False
        self.voice_channel.permissions_for.return_value = self.perms

        vc = await VoiceManager.join_voice_channel(self.member, self.text_channel, self.session)

        self.assertIsNone(vc)
        self.assertIn("Connect", self.session.last_error)

    async def test_06_afk_channel_sentry_blocks_join(self):
        """Verify bot refuses to join designated AFK voice channel."""
        self.guild.afk_channel = self.voice_channel

        vc = await VoiceManager.join_voice_channel(self.member, self.text_channel, self.session)

        self.assertIsNone(vc)
        self.assertIn("AFK", self.session.last_error)

    async def test_07_stale_voice_client_cleanup(self):
        """Verify disconnected / orphaned VoiceClient is forcefully cleaned up before new connect."""
        dead_vc = MagicMock(spec=discord.VoiceClient)
        dead_vc.is_connected.return_value = False
        dead_vc.disconnect = AsyncMock()
        self.guild.voice_client = dead_vc

        fresh_vc = MagicMock(spec=discord.VoiceClient)
        fresh_vc.is_connected.return_value = True
        fresh_vc.channel = self.voice_channel

        async def fake_connect(*args, **kwargs):
            return fresh_vc

        self.voice_channel.connect = AsyncMock(side_effect=fake_connect)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            vc = await VoiceManager.join_voice_channel(self.member, self.text_channel, self.session)

        self.assertEqual(vc, fresh_vc)
        dead_vc.disconnect.assert_awaited_once_with(force=True)

    async def test_08_bounded_retries_and_diagnostics_on_timeout(self):
        """Verify that repeated TimeoutErrors are bounded to 3 attempts and set clear diagnostics."""
        self.voice_channel.connect = AsyncMock(side_effect=asyncio.TimeoutError)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            vc = await VoiceManager.join_voice_channel(self.member, self.text_channel, self.session)

        self.assertIsNone(vc)
        self.assertEqual(self.session.state, PlaybackState.ERROR)
        self.assertEqual(self.voice_channel.connect.await_count, 3)
        self.assertIn("Voice connection timed out after 3 attempts", self.session.last_error)
        self.assertIn("Region Override", self.session.last_error)


if __name__ == "__main__":
    unittest.main()
