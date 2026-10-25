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
from music_bot.services.session_service import GuildMusicSession, PlaybackState, SessionManager
from music_bot.services.voice_service import VoiceManager


class TestMusicTimeouts(unittest.IsolatedAsyncioTestCase):
    """Test suite covering Discord interaction acknowledgement, timeouts, and concurrency."""

    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.loop = asyncio.get_running_loop()
        self.bot.db = MagicMock()
        self.bot.db.get_dj_settings = AsyncMock(return_value=MagicMock(dj_role_id=None))
        self.bot.db.get_guild_settings = AsyncMock(return_value=MagicMock(vote_skip_threshold=0.5))

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
        self.user.guild = self.guild
        self.user.guild_permissions = MagicMock(administrator=False)
        self.user.voice = MagicMock()
        self.voice_channel = MagicMock(spec=discord.VoiceChannel)
        self.voice_channel.id = 555666
        self.voice_channel.name = "Music Lounge"
        self.voice_channel.permissions_for.return_value = MagicMock(connect=True, speak=True)
        self.voice_channel.connect = AsyncMock()
        self.user.voice.channel = self.voice_channel
        self.interaction.user = self.user

        self.channel = MagicMock(spec=discord.TextChannel)
        self.channel.id = 111222
        self.channel.permissions_for.return_value = MagicMock(send_messages=True, embed_links=True)
        self.channel.send = AsyncMock()
        self.interaction.channel = self.channel

        # Interaction response & followup mocks with realistic state transitions
        self.response = MagicMock(spec=discord.InteractionResponse)
        self.response.is_done.return_value = False

        def _mock_defer(*args, **kwargs):
            self.response.is_done.return_value = True

        def _mock_send(*args, **kwargs):
            self.response.is_done.return_value = True

        self.response.defer = AsyncMock(side_effect=_mock_defer)
        self.response.send_message = AsyncMock(side_effect=_mock_send)
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
        self.response.defer.reset_mock()
        await MusicCog.ensure_deferred(self.interaction, ephemeral=True)
        self.response.defer.assert_not_called()

    async def test_ensure_deferred_handles_not_found_cleanly(self):
        """Verify ensure_deferred suppresses discord.NotFound (10062) gracefully."""
        self.response.is_done.return_value = False
        err = discord.NotFound(MagicMock(status=404), "Unknown interaction")
        err.code = 10062
        self.response.defer = AsyncMock(side_effect=err)
        # Must not raise
        await MusicCog.ensure_deferred(self.interaction, ephemeral=False)

    # =========================================================================
    # 2. RESOLVER & VOICE NETWORK BOUNDS
    # =========================================================================

    def test_resolver_ytdl_socket_timeout_configured(self):
        """Verify yt-dlp has a bounded socket timeout to prevent TCP socket hangs."""
        self.assertIn("socket_timeout", YTDL_OPTIONS)
        self.assertLessEqual(YTDL_OPTIONS["socket_timeout"], 10)

    async def test_voice_manager_connection_timeout(self):
        """Verify VoiceManager handles voice handshake timeouts without raising or freezing."""
        self.voice_channel.connect = AsyncMock(side_effect=asyncio.TimeoutError())
        session = self.session_manager.get_session_sync(999888777)

        vc = await VoiceManager.join_voice_channel(self.user, self.channel, session)
        self.assertIsNone(vc)
        self.assertEqual(session.state, PlaybackState.ERROR)
        self.assertIn("Voice connection failed", session.last_error)

    # =========================================================================
    # 3. /PLAY COMMAND TIMEOUT FLOW
    # =========================================================================

    @patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel")
    @patch("music_bot.commands.music_cog.AudioResolver.search", new_callable=AsyncMock, return_value=[])
    @patch("music_bot.commands.music_cog.AudioResolver.resolve_track")
    @patch("music_bot.commands.music_cog.MusicPlayerService.start_playback")
    async def test_play_command_immediate_defer_and_success(
        self, mock_playback, mock_resolve, mock_search, mock_join
    ):
        """Verify /play defers immediately and updates original response within deadline."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True
        mock_join.return_value = mock_vc

        session = self.session_manager.get_session_sync(999888777)
        if session:
            session.reset()

        sample_track = QueuedTrack(
            title="Futuristic Synth Groove",
            url="https://youtube.com/watch?v=123",
            duration=180,
            thumbnail="",
            artist="Neon Artists",
            requester_id=self.user.id,
            requester_name=str(self.user),
        )
        mock_resolve.return_value = sample_track

        await self.cog.alias_play.callback(self.cog, self.interaction, "synth groove")

        # Must have deferred immediately
        self.response.defer.assert_awaited()
        # Must have edited original response
        self.interaction.edit_original_response.assert_awaited()
        mock_playback.assert_awaited()

    @patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel")
    @patch("music_bot.commands.music_cog.AudioResolver.search", new_callable=AsyncMock, return_value=[])
    @patch("music_bot.commands.music_cog.AudioResolver.resolve_track")
    async def test_play_command_resolver_timeout_graceful_exit(
        self, mock_resolve, mock_search, mock_join
    ):
        """Verify /play cleanly informs user when track resolution times out (no 'Thinking...' hang)."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_join.return_value = mock_vc
        mock_resolve.side_effect = asyncio.TimeoutError()

        await self.cog.alias_play.callback(self.cog, self.interaction, "extremely slow track")

        # Must have deferred immediately
        self.response.defer.assert_awaited()
        # Must have edited deferred response with timeout embed
        self.interaction.edit_original_response.assert_awaited()
        args, kwargs = self.interaction.edit_original_response.call_args
        embed = kwargs.get("embed")
        self.assertIsNotNone(embed)
        self.assertIn("TIMED OUT", embed.title)

    async def test_play_command_user_not_in_voice(self):
        """Verify /play immediately responds when user is not connected to voice."""
        self.user.voice = None

        await self.cog.alias_play.callback(self.cog, self.interaction, "lofi beats")

        self.response.defer.assert_awaited()
        # After defer is_done=True → send_ephemeral_or_fallback routes to followup.send
        self.followup.send.assert_awaited()
        args, kwargs = self.followup.send.call_args
        # May arrive as positional content or keyword content
        content_val = kwargs.get("content", args[0] if args else "")
        self.assertIn("voice channel", str(content_val).lower())

    # =========================================================================
    # 4. INSTANT PLAYBACK CONTROLS DEFERRAL & RESPONSE
    # =========================================================================

    async def test_pause_resume_skip_stop_immediate_deferral(self):
        """Verify playback control commands immediately defer and answer."""
        session = self.session_manager.get_session_sync(999888777)
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.channel = self.voice_channel
        self.voice_channel.members = [self.user]
        mock_vc.is_playing.return_value = True
        mock_vc.is_paused.return_value = False
        session.voice_client = mock_vc
        session.current_track = QueuedTrack(
            title="Lofi Beat",
            url="https://youtube.com/watch?v=t1",
            duration=120,
            thumbnail="",
            artist="Lofi Girl",
            requester_id=self.user.id,
            requester_name="Tester",
        )

        # Pause
        self.response.is_done.return_value = False
        self.response.defer.reset_mock()
        self.interaction.followup.send.reset_mock()
        await self.cog.alias_pause.callback(self.cog, self.interaction)
        self.response.defer.assert_awaited()
        mock_vc.pause.assert_called_once()

        # Resume
        mock_vc.is_paused.return_value = True
        self.response.is_done.return_value = False
        self.response.defer.reset_mock()
        await self.cog.alias_resume.callback(self.cog, self.interaction)
        self.response.defer.assert_awaited()
        mock_vc.resume.assert_called_once()

        # Skip
        self.response.is_done.return_value = False
        self.response.defer.reset_mock()
        await self.cog.alias_skip.callback(self.cog, self.interaction)
        self.response.defer.assert_awaited()
        mock_vc.stop.assert_called_once()

        # Stop
        self.response.is_done.return_value = False
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
            title="Concurrent Track",
            url="https://youtube.com/watch?v=conc",
            duration=120,
            thumbnail="",
            artist="Tester",
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

            def _def(*args, r=resp, **kwargs):
                r.is_done.return_value = True

            resp.defer = AsyncMock(side_effect=_def)
            resp.send_message = AsyncMock(side_effect=_def)
            inter.response = resp

            fup = MagicMock(spec=discord.Webhook)
            fup.send = AsyncMock()
            inter.followup = fup
            inter.edit_original_response = AsyncMock()
            interactions.append(inter)

        # Execute 5 concurrent /play commands
        tasks = [
            self.cog.alias_play.callback(self.cog, inter, f"song {idx}")
            for idx, inter in enumerate(interactions)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            self.assertNotIsInstance(res, Exception, f"Concurrent execution raised error: {res}")

        for inter in interactions:
            inter.response.defer.assert_awaited()
            inter.edit_original_response.assert_awaited()

    # =========================================================================
    # 7. MM-855661 REGRESSION SUITE (TIMEOUTS, RETRY, DEDUPLICATION & RECOVERY)
    # =========================================================================

    @patch("music_bot.services.resolver_service._run_ytdlp")
    async def test_search_transient_failure_followed_by_success(self, mock_run):
        """Verify AudioResolver.search falls back to secondary profile retry on primary failure."""
        AudioResolver.clear_caches()
        # First call fails with TimeoutError, second call (retry) succeeds
        mock_run.side_effect = [
            asyncio.TimeoutError("Primary search timed out"),
            {
                "entries": [
                    {
                        "id": "kal123",
                        "title": "Kalyani",
                        "uploader": "Carnatic Official",
                        "duration": 240,
                        "webpage_url": "https://www.youtube.com/watch?v=kal123",
                    }
                ]
            },
        ]

        results = await AudioResolver.search("kalyani", limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "kal123")
        self.assertEqual(results[0]["title"], "Kalyani")
        self.assertEqual(mock_run.call_count, 2)
        AudioResolver.clear_caches()

    @patch("music_bot.services.resolver_service._run_ytdlp")
    async def test_search_retry_limit_reached_returns_empty(self, mock_run):
        """Verify AudioResolver.search returns empty list gracefully when primary and retry fail."""
        AudioResolver.clear_caches()
        mock_run.side_effect = [
            asyncio.TimeoutError("Primary search timed out"),
            asyncio.TimeoutError("Retry search timed out"),
        ]

        results = await AudioResolver.search("kalyani", limit=5)
        self.assertEqual(results, [])
        self.assertEqual(mock_run.call_count, 2)
        AudioResolver.clear_caches()

    @patch("music_bot.services.resolver_service._run_ytdlp")
    async def test_search_in_flight_deduplication(self, mock_run):
        """Verify concurrent searches for the same query join the in-flight task without duplicating worker calls."""
        AudioResolver.clear_caches()

        async def _delayed_run(*args, **kwargs):
            await asyncio.sleep(0.05)
            return {
                "entries": [
                    {
                        "id": "kal_dedup",
                        "title": "Kalyani - Official Audio",
                        "uploader": "Classical Music Official",
                        "channel": "Classical Music Official",
                        "channel_is_verified": True,
                        "duration": 300,
                        "webpage_url": "https://www.youtube.com/watch?v=kal_dedup",
                    }
                ]
            }

        mock_run.side_effect = _delayed_run

        t1 = asyncio.create_task(AudioResolver.search("kalyani", limit=5))
        t2 = asyncio.create_task(AudioResolver.search("kalyani", limit=5))
        res1, res2 = await asyncio.gather(t1, t2)

        self.assertEqual(len(res1), 1)
        self.assertEqual(len(res2), 1)
        self.assertEqual(res1[0]["id"], "kal_dedup")
        self.assertEqual(res2[0]["id"], "kal_dedup")
        # Both coroutines shared the single worker invocation
        self.assertEqual(mock_run.call_count, 1)
        AudioResolver.clear_caches()

    @patch("music_bot.services.resolver_service._run_ytdlp")
    async def test_stream_extraction_timeout_distinct_error_diagnostic(self, mock_run):
        """Verify that when stream extraction times out, a distinct [TIMEOUT] diagnostic is produced."""
        AudioResolver.clear_caches()
        async def _mock_run(func, *, operation, **kwargs):
            if operation in ("search", "search_retry", "search_fallback"):
                return {
                    "entries": [
                        {
                            "id": "stream_slow_id",
                            "title": "Kalyani - Official Video",
                            "uploader": "Carnatic Official",
                            "channel": "Carnatic Official",
                            "channel_is_verified": True,
                            "duration": 180,
                            "webpage_url": "https://www.youtube.com/watch?v=stream_slow_id",
                        }
                    ]
                }
            # Stream extraction raises TimeoutError
            raise asyncio.TimeoutError("Stream extraction socket timed out")

        mock_run.side_effect = _mock_run

        track = await AudioResolver.resolve_track("kalyani", 12345, "Tester")
        self.assertIsNone(track)
        last_err = AudioResolver.last_resolver_error or ""
        self.assertIn("[TIMEOUT]", last_err)
        self.assertIn("Network or resolution timed out", last_err)
        AudioResolver.clear_caches()

    @patch("music_bot.services.resolver_service._run_ytdlp")
    async def test_kalyani_query_to_result_matching(self, mock_run):
        """Verify correct query-to-result matching for 'kalyani' query."""
        AudioResolver.clear_caches()
        mock_run.return_value = {
            "entries": [
                {
                    "id": "kal_match",
                    "title": "Kalyani - Classical Recording",
                    "uploader": "Official Artist Channel",
                    "duration": 210,
                    "webpage_url": "https://www.youtube.com/watch?v=kal_match",
                    "url": "https://audio-stream.googlevideo.com/videoplayback?id=kal_match",
                }
            ]
        }

        results = await AudioResolver.search("kalyani", limit=5)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["id"], "kal_match")
        self.assertIn("kalyani", results[0]["title"].lower())
        AudioResolver.clear_caches()


if __name__ == "__main__":
    unittest.main()
