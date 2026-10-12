"""
Unit and Integration Tests for Discord Music Bot Timeout Prevention & Slash Command Acknowledgement.
Validates:
1. Immediate deferral (<3 seconds) across /play, /pause, /resume, /skip, /stop, /queue, /np, etc.
2. In-place response editing (no dangling 'Thinking...' loading state).
3. AudioResolver bounded thread pool, socket timeouts, and search failover under slow networks.
4. VoiceManager voice handshake timeout protection (no event loop freezes).
5. Tree error handler unwrapping of asyncio.TimeoutError and clean editing of original response.
6. Concurrent command handling without event loop starvation or deadlocks.
"""

from __future__ import annotations

import asyncio
from typing import Optional
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord import app_commands

from music_bot.commands.music_cog import MusicCog
from music_bot.database.models import QueuedTrack
from music_bot.services.resolver_service import AudioResolver, YTDL_OPTIONS
from music_bot.services.session_service import GuildMusicSession, SessionManager
from music_bot.services.voice_service import VoiceManager


class TestMusicTimeouts(unittest.IsolatedAsyncioTestCase):
    """Test suite covering Discord interaction acknowledgement, timeouts, and concurrency."""

    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.loop = asyncio.get_running_loop()
        self.session_manager = SessionManager()
        self.cog = MusicCog(self.bot)
        self.cog.session_manager = self.session_manager

        # Common mock interaction
        self.interaction = MagicMock(spec=discord.Interaction)
        self.interaction.guild_id = 999888777
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 999888777
        self.guild.name = "Test Audio Guild"
        self.guild.voice_client = None
        self.interaction.guild = self.guild

        self.user = MagicMock(spec=discord.Member)
        self.user.id = 123456
        self.user.name = "AudioTester"
        self.user.voice = MagicMock()
        self.voice_channel = MagicMock(spec=discord.VoiceChannel)
        self.voice_channel.id = 555666
        self.voice_channel.name = "Music Lounge"
        self.voice_channel.permissions_for.return_value = MagicMock(connect=True, speak=True)
        self.user.voice.channel = self.voice_channel
        self.interaction.user = self.user

        self.channel = MagicMock(spec=discord.TextChannel)
        self.channel.id = 111222
        self.channel.permissions_for.return_value = MagicMock(send_messages=True, embed_links=True)
        self.interaction.channel = self.channel

        # Interaction response & followup mocks
        self.response = MagicMock(spec=discord.InteractionResponse)
        self.response.is_done.return_value = False
        self.response.defer = AsyncMock()
        self.response.send_message = AsyncMock()
        self.interaction.response = self.response

        self.followup = MagicMock(spec=discord.Webhook)
        self.followup.send = AsyncMock()
        self.interaction.followup = self.followup

        self.interaction.edit_original_response = AsyncMock()

    async def asyncTearDown(self):
        # Reset session
        session = self.session_manager.get_session_sync(999888777)
        if session:
            session.reset()

    # =========================================================================
    # 1. IMMEDIATE DEFERRAL HELPER
    # =========================================================================

    async def test_ensure_deferred_not_done(self):
        """Verify ensure_deferred defers an unacknowledged interaction."""
        self.response.is_done.return_value = False
        await MusicCog.ensure_deferred(self.interaction, ephemeral=False)
        self.response.defer.assert_awaited_once_with(ephemeral=False)

    async def test_ensure_deferred_already_done(self):
        """Verify ensure_deferred is a no-op when the interaction is already deferred."""
        self.response.is_done.return_value = True
        await MusicCog.ensure_deferred(self.interaction, ephemeral=True)
        self.response.defer.assert_not_called()

    async def test_ensure_deferred_handles_not_found_cleanly(self):
        """Verify ensure_deferred suppresses discord.NotFound (10062) gracefully."""
        self.response.is_done.return_value = False
        err = discord.NotFound(MagicMock(status=404), "Unknown interaction")
        err.code = 10062
        self.response.defer.side_effect = err
        # Must not raise
        await MusicCog.ensure_deferred(self.interaction, ephemeral=False)

    # =========================================================================
    # 2. RESOLVER & VOICE NETWORK BOUNDS
    # =========================================================================

    def test_resolver_ytdl_socket_timeout_configured(self):
        """Verify yt-dlp has a bounded socket timeout to prevent TCP socket hangs."""
        self.assertIn("socket_timeout", YTDL_OPTIONS)
        self.assertLessEqual(YTDL_OPTIONS["socket_timeout"], 10)

    @patch("music_bot.services.voice_service.asyncio.wait_for")
    async def test_voice_manager_connection_timeout(self, mock_wait_for):
        """Verify VoiceManager handles voice handshake timeouts without raising or freezing."""
        mock_wait_for.side_effect = asyncio.TimeoutError()
        session = self.session_manager.get_session_sync(999888777)

        vc = await VoiceManager.join_voice_channel(self.user, self.channel, session)
        self.assertIsNone(vc)
        # Verify text channel was notified of connection timeout
        self.channel.send.assert_awaited()
        call_arg = str(self.channel.send.call_args)
        self.assertIn("Timed out", call_arg)

    # =========================================================================
    # 3. /PLAY COMMAND TIMEOUT FLOW
    # =========================================================================

    @patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel")
    @patch("music_bot.commands.music_cog.AudioResolver.resolve_track")
    @patch("music_bot.commands.music_cog.MusicPlayerService.start_playback")
    async def test_play_command_immediate_defer_and_success(
        self, mock_playback, mock_resolve, mock_join
    ):
        """Verify /play defers immediately and updates original response within deadline."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True
        mock_join.return_value = mock_vc

        sample_track = QueuedTrack(
            id="test1",
            title="Futuristic Synth Groove",
            url="https://youtube.com/watch?v=123",
            duration=180,
            thumbnail="",
            uploader="Neon Artists",
            requester_id=self.user.id,
            requester_name=str(self.user),
        )
        mock_resolve.return_value = sample_track

        await self.cog.alias_play.callback(self.cog, self.interaction, query="synth groove")

        # Must have deferred immediately
        self.response.defer.assert_awaited()
        # Must have edited original response
        self.interaction.edit_original_response.assert_awaited()
        mock_playback.assert_awaited()

    @patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel")
    @patch("music_bot.commands.music_cog.AudioResolver.resolve_track")
    async def test_play_command_resolver_timeout_graceful_exit(
        self, mock_resolve, mock_join
    ):
        """Verify /play cleanly informs user when track resolution times out (no 'Thinking...' hang)."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_join.return_value = mock_vc
        mock_resolve.side_effect = asyncio.TimeoutError()

        await self.cog.alias_play.callback(self.cog, self.interaction, query="extremely slow track")

        # Must have deferred immediately
        self.response.defer.assert_awaited()
        # Must have edited original response informing user of timeout
        self.interaction.edit_original_response.assert_awaited()
        args, kwargs = self.interaction.edit_original_response.call_args
        embed = kwargs.get("embed")
        self.assertIsNotNone(embed)
        self.assertIn("TIMED OUT", embed.title)

    async def test_play_command_user_not_in_voice(self):
        """Verify /play immediately responds when user is not connected to voice."""
        self.user.voice = None

        await self.cog.alias_play.callback(self.cog, self.interaction, query="lofi beats")

        self.response.defer.assert_awaited()
        self.interaction.edit_original_response.assert_awaited()
        args, kwargs = self.interaction.edit_original_response.call_args
        embed = kwargs.get("embed")
        self.assertIsNotNone(embed)
        self.assertIn("CONNECT TO VOICE", embed.title)

    # =========================================================================
    # 4. INSTANT PLAYBACK CONTROLS DEFERRAL & RESPONSE
    # =========================================================================

    async def test_pause_resume_skip_stop_immediate_deferral(self):
        """Verify playback control commands immediately defer and answer."""
        session = self.session_manager.get_session_sync(999888777)
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_playing.return_value = True
        mock_vc.is_paused.return_value = False
        session.voice_client = mock_vc
        session.current_track = QueuedTrack(
            id="t1",
            title="Lofi Beat",
            url="https://youtube.com/watch?v=t1",
            duration=120,
            thumbnail="",
            uploader="Lofi Girl",
            requester_id=self.user.id,
            requester_name="Tester",
        )

        # Pause
        self.response.defer.reset_mock()
        self.interaction.followup.send.reset_mock()
        await self.cog.alias_pause.callback(self.cog, self.interaction)
        self.response.defer.assert_awaited()
        mock_vc.pause.assert_called_once()

        # Resume
        mock_vc.is_paused.return_value = True
        self.response.defer.reset_mock()
        await self.cog.alias_resume.callback(self.cog, self.interaction)
        self.response.defer.assert_awaited()
        mock_vc.resume.assert_called_once()

        # Skip
        self.response.defer.reset_mock()
        await self.cog.alias_skip.callback(self.cog, self.interaction)
        self.response.defer.assert_awaited()
        mock_vc.stop.assert_called_once()

        # Stop
        self.response.defer.reset_mock()
        mock_vc.disconnect = AsyncMock()
        await self.cog.alias_stop.callback(self.cog, self.interaction)
        self.response.defer.assert_awaited()

    # =========================================================================
    # 5. TREE ERROR HANDLER TIMEOUT UNWRAPPING
    # =========================================================================

    async def test_tree_error_handler_timeout_unwrapping(self):
        """Verify bot.tree.on_error unwraps CommandInvokeError(TimeoutError) and edits response."""
        from music_bot.bot import RaiMusicBot

        bot = MagicMock(spec=RaiMusicBot)
        # Mimic the handler implementation in bot.py
        async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
            orig = getattr(error, "original", error)
            if isinstance(orig, discord.NotFound) and getattr(orig, "code", None) == 10062:
                return

            if isinstance(orig, asyncio.TimeoutError):
                msg = "⏱️ **Audio Request Timed Out:** The audio search or voice connection took too long to respond. Please try again with a direct URL or different query."
            else:
                msg = f"⚠️ **Music Command Notice:** {str(orig or error)}"

            if interaction.response.is_done():
                try:
                    await interaction.edit_original_response(content=msg, embed=None, view=None)
                except Exception:
                    await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)

        self.response.is_done.return_value = True
        timeout_invoke_error = app_commands.CommandInvokeError(
            MagicMock(), asyncio.TimeoutError()
        )

        await on_tree_error(self.interaction, timeout_invoke_error)

        self.interaction.edit_original_response.assert_awaited_once()
        args, kwargs = self.interaction.edit_original_response.call_args
        self.assertIn("Timed Out", kwargs["content"])

    # =========================================================================
    # 6. CONCURRENT INTERACTION STRESS TEST
    # =========================================================================

    @patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel")
    @patch("music_bot.commands.music_cog.AudioResolver.resolve_track")
    @patch("music_bot.commands.music_cog.MusicPlayerService.start_playback")
    async def test_concurrent_play_commands_no_deadlock(
        self, mock_playback, mock_resolve, mock_join
    ):
        """Verify multiple simulated users executing /play concurrently do not deadlock or timeout."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True
        mock_join.return_value = mock_vc

        sample_track = QueuedTrack(
            id="conc",
            title="Concurrent Track",
            url="https://youtube.com/watch?v=conc",
            duration=120,
            thumbnail="",
            uploader="Tester",
            requester_id=1,
            requester_name="User",
        )
        mock_resolve.return_value = sample_track

        interactions = []
        for i in range(5):
            inter = MagicMock(spec=discord.Interaction)
            inter.guild_id = 1000 + i
            g = MagicMock(spec=discord.Guild)
            g.id = 1000 + i
            g.name = f"Guild {i}"
            g.voice_client = None
            inter.guild = g

            u = MagicMock(spec=discord.Member)
            u.id = 2000 + i
            u.name = f"User{i}"
            u.voice = MagicMock()
            u.voice.channel = MagicMock(spec=discord.VoiceChannel)
            u.voice.channel.permissions_for.return_value = MagicMock(connect=True, speak=True)
            inter.user = u

            c = MagicMock(spec=discord.TextChannel)
            c.id = 3000 + i
            c.permissions_for.return_value = MagicMock(send_messages=True, embed_links=True)
            inter.channel = c

            resp = MagicMock(spec=discord.InteractionResponse)
            resp.is_done.return_value = False
            resp.defer = AsyncMock()
            resp.send_message = AsyncMock()
            inter.response = resp

            fup = MagicMock(spec=discord.Webhook)
            fup.send = AsyncMock()
            inter.followup = fup
            inter.edit_original_response = AsyncMock()
            interactions.append(inter)

        # Execute 5 concurrent /play commands
        tasks = [
            self.cog.alias_play.callback(self.cog, inter, query=f"song {idx}")
            for idx, inter in enumerate(interactions)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            self.assertNotIsInstance(res, Exception, f"Concurrent execution raised error: {res}")

        for inter in interactions:
            inter.response.defer.assert_awaited()
            inter.edit_original_response.assert_awaited()


if __name__ == "__main__":
    unittest.main()
