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

    @patch("cogs.basic.dispatch_message", new_callable=AsyncMock)
    @patch("cogs.basic.LangHandler.get_lang", new_callable=AsyncMock, return_value=["LIVE", " (pos %s)", " (now)"])
    @patch("cogs.basic.voicelink.connect_channel", new_callable=AsyncMock)
    async def test_play_recovers_stale_voice_client(self, mock_connect, mock_get_lang, mock_dispatch):
        """Case 4: `play` command detects stale client, tears it down, and connects to user."""
        self.bot_member.voice = None
        stale_player = MagicMock()
        stale_player.teardown = AsyncMock()
        self.guild.voice_client = stale_player

        # Live player connected to user's channel
        live_player = MagicMock()
        live_player.is_user_join.return_value = True
        mock_track = MagicMock()
        mock_track.title = "moodbaazi"
        mock_track.uri = "https://youtube.com/watch?v=123"
        mock_track.author = "Artist"
        mock_track.formatted_length = "3:30"
        mock_track.is_stream = False
        live_player.get_tracks = AsyncMock(return_value=[mock_track])
        live_player.add_track = AsyncMock(return_value=0)
        live_player.is_playing = False
        live_player.do_next = AsyncMock()
        mock_connect.return_value = live_player

        self.ctx.interaction = None
        self.ctx.author = MagicMock()

        await self.cog.play.callback(self.cog, self.ctx, query="moodbaazi")

        # Stale player must have been torn down
        stale_player.teardown.assert_awaited_once()
        # Connect channel was called to connect to user's channel
        mock_connect.assert_awaited_once_with(self.ctx)
        # Track was fetched and queued
        live_player.get_tracks.assert_awaited_once_with("moodbaazi", requester=self.ctx.author)

    @patch("cogs.basic.dispatch_message", new_callable=AsyncMock)
    @patch("cogs.basic.LangHandler.get_lang", new_callable=AsyncMock, return_value=["LIVE", " (pos %s)", " (now)"])
    @patch("cogs.basic.voicelink.connect_channel", new_callable=AsyncMock)
    async def test_play_moves_idle_bot_from_empty_channel(self, mock_connect, mock_get_lang, mock_dispatch):
        """Case 5: `play` moves bot when it's sitting alone in an empty channel and user is in another VC."""
        bot_voice_state = MagicMock()
        bot_channel = MagicMock()
        bot_channel.id = 111111111
        # Only the bot member in bot_channel
        bot_channel.members = [self.bot_member]
        self.bot_member.bot = True
        bot_voice_state.channel = bot_channel
        self.bot_member.voice = bot_voice_state

        user_channel = MagicMock()
        user_channel.id = 222222222
        user = MagicMock()
        user.bot = False
        user_voice_state = MagicMock()
        user_voice_state.channel = user_channel
        user.voice = user_voice_state
        self.ctx.author = user

        live_player = MagicMock()
        live_player.move_to = AsyncMock()
        live_player.is_user_join.return_value = True
        mock_track = MagicMock()
        mock_track.title = "moodbaazi"
        mock_track.uri = "https://youtube.com/watch?v=123"
        mock_track.author = "Artist"
        mock_track.formatted_length = "3:30"
        mock_track.is_stream = False
        live_player.get_tracks = AsyncMock(return_value=[mock_track])
        live_player.add_track = AsyncMock(return_value=0)
        live_player.is_playing = False
        live_player.do_next = AsyncMock()
        self.guild.voice_client = live_player

        self.ctx.interaction = None

        await self.cog.play.callback(self.cog, self.ctx, query="moodbaazi")

        # Bot must have moved to user's channel!
        live_player.move_to.assert_awaited_once_with(user_channel)
        self.assertEqual(live_player.channel, user_channel)


if __name__ == "__main__":
    unittest.main()

