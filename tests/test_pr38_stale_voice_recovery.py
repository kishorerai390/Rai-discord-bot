"""
Tests for PR #38: Stale Voice Client Recovery in Connect Command.
Verifies:
1. When bot has a stale voice client (guild.me.voice is None but guild.voice_client is present)
   and ClientException occurs, stale_player.teardown() is called and a clean reconnect is attempted once.
2. When bot is genuinely connected (guild.me.voice.channel is not None),
   live player is preserved and 'voice.connection.alreadyConnected' is returned.
3. When reconnection attempt after cleanup fails, it logs error and exits without infinite loop.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands

from cogs.basic import Basic


class TestPR38StaleVoiceRecovery(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = Basic(self.bot)

        # Mock Discord context
        self.ctx = MagicMock(spec=commands.Context)
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 123456789
        self.ctx.guild = self.guild
        self.channel = MagicMock(spec=discord.VoiceChannel)
        self.channel.id = 987654321

        # Bot member
        self.bot_member = MagicMock(spec=discord.Member)
        self.guild.me = self.bot_member

    @patch("cogs.basic.send_localized_message", new_callable=AsyncMock)
    @patch("cogs.basic.voicelink.connect_channel", new_callable=AsyncMock)
    async def test_stale_voice_client_recovers_successfully(self, mock_connect, mock_send):
        """Case 1: Ghost/stale voice client is cleaned up and reconnect succeeds."""
        # Bot's actual Discord voice state says NOT in voice
        self.bot_member.voice = None

        # But guild.voice_client has a stale object
        stale_player = MagicMock()
        stale_player.teardown = AsyncMock()
        self.guild.voice_client = stale_player

        # New live player returned on retry
        live_player = MagicMock()
        live_player.channel = self.channel

        # First call raises ClientException ("Already connected"), second call succeeds
        mock_connect.side_effect = [
            discord.errors.ClientException("Already connected to a voice channel."),
            live_player
        ]

        await self.cog.connect.callback(self.cog, self.ctx, self.channel)

        # Stale player teardown must be called
        stale_player.teardown.assert_awaited_once()

        # Connect must be attempted twice (initial + retry)
        self.assertEqual(mock_connect.await_count, 2)

        # Success message should be sent
        mock_send.assert_awaited_once_with(self.ctx, "voice.connection.connect", self.channel)

    @patch("cogs.basic.send_localized_message", new_callable=AsyncMock)
    @patch("cogs.basic.voicelink.connect_channel", new_callable=AsyncMock)
    async def test_genuine_connection_is_preserved(self, mock_connect, mock_send):
        """Case 2: Bot is legitimately in a voice channel, live player is preserved."""
        # Bot's actual Discord voice state confirms it is in a channel
        voice_state = MagicMock()
        voice_state.channel = self.channel
        self.bot_member.voice = voice_state

        live_player = MagicMock()
        live_player.teardown = AsyncMock()
        self.guild.voice_client = live_player

        # connect_channel raises ClientException
        mock_connect.side_effect = discord.errors.ClientException("Already connected to a voice channel.")

        await self.cog.connect.callback(self.cog, self.ctx, self.channel)

        # Live player MUST NOT be torn down
        live_player.teardown.assert_not_called()

        # Connect should only be attempted once
        self.assertEqual(mock_connect.await_count, 1)

        # alreadyConnected message returned
        mock_send.assert_awaited_once_with(self.ctx, "voice.connection.alreadyConnected")

    @patch("cogs.basic.send_localized_message", new_callable=AsyncMock)
    @patch("cogs.basic.voicelink.connect_channel", new_callable=AsyncMock)
    async def test_reconnect_failure_does_not_loop(self, mock_connect, mock_send):
        """Case 3: Reconnection fails after cleanup, safely returns without looping."""
        self.bot_member.voice = None
        stale_player = MagicMock()
        stale_player.teardown = AsyncMock()
        self.guild.voice_client = stale_player

        # Both attempts raise ClientException or RuntimeError
        mock_connect.side_effect = [
            discord.errors.ClientException("Already connected to a voice channel."),
            RuntimeError("Signaling timeout")
        ]

        await self.cog.connect.callback(self.cog, self.ctx, self.channel)

        stale_player.teardown.assert_awaited_once()
        self.assertEqual(mock_connect.await_count, 2)
        mock_send.assert_awaited_once_with(self.ctx, "voice.connection.alreadyConnected")


if __name__ == "__main__":
    unittest.main()
