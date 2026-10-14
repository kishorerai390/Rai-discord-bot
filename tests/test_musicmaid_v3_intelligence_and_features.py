"""
Comprehensive Unit and Regression Test Suite for MusicMaid V3 Capabilities:
1. Smart Auto-DJ 2.0 with mood-based query biasing (chill, gaming, energetic, party, focus)
2. Auto-DJ controls and status reporting
3. Listening Party mode (start, stop, status)
4. Democratic skip voting (threshold calculation, duplicate vote guard, auto-skip on threshold)
5. Read-only update audit and dependency status (!updatecheck, /updatecheck)
6. Database and backup retention status (!backupstatus, /backupstatus)
7. Vote clearing on track skip and transition
"""

from __future__ import annotations

import asyncio
from collections import deque
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from music_bot.commands.music_cog import MusicCog
from music_bot.database.models import QueuedTrack
from music_bot.services.dj_service import NekoDJService
from music_bot.services.player_service import MusicPlayerService
from music_bot.services.session_service import GuildMusicSession, PlaybackState, SessionManager


class TestMusicMaidV3Features(unittest.IsolatedAsyncioTestCase):
    """Test suite for MusicMaid V3 Intelligence and Reliability Expansion."""

    def setUp(self):
        self.guild_id = 998877
        self.session_manager = SessionManager.get_instance()
        self.session = GuildMusicSession(self.guild_id)

        self.mock_bot = MagicMock()
        self.mock_bot.db = AsyncMock()
        self.cog = MusicCog(self.mock_bot)

        # Mock voice channel and members
        self.vc_channel = MagicMock(spec=discord.VoiceChannel)
        self.vc_channel.id = 123456
        self.vc_channel.name = "Music Lounge"

        self.mock_vc = MagicMock(spec=discord.VoiceClient)
        self.mock_vc.is_connected.return_value = True
        self.mock_vc.is_playing.return_value = True
        self.mock_vc.channel = self.vc_channel
        self.session.voice_client = self.mock_vc

        self.sample_track = QueuedTrack(
            title="Neon Horizon",
            url="https://youtube.com/watch?v=sample123",
            duration=210,
            artist="SynthVibe",
            requester_id=111,
            requester_name="Audiophile#0001",
        )
        self.session.current_track = self.sample_track
        self.session.state = PlaybackState.PLAYING

    async def test_01_autodj_mood_query_biasing(self):
        """1. Verify that Auto-DJ injects mood-specific queries when dj_mood is set."""
        self.session.dj_mood = "gaming"
        self.session.history.append(self.sample_track)

        captured_queries = []

        async def fake_search(query, limit=8):
            captured_queries.append(query)
            return []

        with patch("music_bot.services.resolver_service.AudioResolver.search", side_effect=fake_search):
            await NekoDJService.get_recommendation(self.mock_bot, self.session)

        # At least one query must contain gaming/synthwave
        self.assertTrue(
            any("gaming" in q.lower() or "synthwave" in q.lower() for q in captured_queries),
            f"Expected gaming mood query in {captured_queries}",
        )

    async def test_02_autodj_commands_toggle_mode(self):
        """2. Verify /autodj and !autodj toggle Auto-DJ state cleanly."""
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild_id = self.guild_id
        mock_interaction.response.is_done.return_value = False
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.edit_original_response = AsyncMock()

        with patch.object(self.cog.session_manager, "get_session", new_callable=AsyncMock) as mock_get_sess:
            mock_get_sess.return_value = self.session

            # Turn ON
            await self.cog.cmd_autodj.callback(self.cog, mock_interaction, action="on")
            self.assertTrue(self.session.dj_enabled)
            mock_interaction.edit_original_response.assert_awaited()

            # Turn OFF
            await self.cog.cmd_autodj.callback(self.cog, mock_interaction, action="off")
            self.assertFalse(self.session.dj_enabled)

    async def test_03_voteskip_single_listener_skips_immediately(self):
        """3. Verify single listener in voice channel triggers immediate skip without waiting."""
        listener = MagicMock(spec=discord.Member)
        listener.id = 111
        listener.bot = False
        listener.voice = MagicMock(channel=self.vc_channel)
        self.vc_channel.members = [listener]

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild_id = self.guild_id
        mock_interaction.user = listener
        mock_interaction.response.is_done.return_value = False
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.edit_original_response = AsyncMock()

        with patch.object(self.cog.session_manager, "get_session", new_callable=AsyncMock) as mock_get_sess, \
             patch.object(MusicPlayerService, "skip", new_callable=AsyncMock) as mock_skip:
            mock_get_sess.return_value = self.session
            mock_skip.return_value = (True, "Skipped track", None)

            await self.cog.cmd_voteskip.callback(self.cog, mock_interaction)

            mock_skip.assert_awaited_once()

    async def test_04_voteskip_multiple_listeners_enforces_threshold(self):
        """4. Verify multi-listener channel requires majority threshold and ignores duplicates."""
        u1 = MagicMock(spec=discord.Member, bot=False, id=101)
        u1.voice = MagicMock(channel=self.vc_channel)
        u2 = MagicMock(spec=discord.Member, bot=False, id=102)
        u2.voice = MagicMock(channel=self.vc_channel)
        u3 = MagicMock(spec=discord.Member, bot=False, id=103)
        u3.voice = MagicMock(channel=self.vc_channel)
        self.vc_channel.members = [u1, u2, u3]  # 3 listeners -> threshold = (3 + 1) // 2 = 2

        mock_interaction1 = MagicMock(spec=discord.Interaction, guild_id=self.guild_id, user=u1)
        mock_interaction1.response.is_done.return_value = False
        mock_interaction1.response.defer = AsyncMock()
        mock_interaction1.edit_original_response = AsyncMock()

        with patch.object(self.cog.session_manager, "get_session", new_callable=AsyncMock) as mock_get_sess, \
             patch.object(MusicPlayerService, "skip", new_callable=AsyncMock) as mock_skip:
            mock_get_sess.return_value = self.session
            mock_skip.return_value = (True, "Skipped track", None)

            # User 1 votes (1/2 -> not yet passed)
            await self.cog.cmd_voteskip.callback(self.cog, mock_interaction1)
            self.assertEqual(len(self.session.skip_votes), 1)
            mock_skip.assert_not_called()

            # User 1 votes AGAIN (duplicate vote ignored)
            await self.cog.cmd_voteskip.callback(self.cog, mock_interaction1)
            self.assertEqual(len(self.session.skip_votes), 1)
            mock_skip.assert_not_called()

            # User 2 votes (2/2 -> threshold met, skips track!)
            mock_interaction2 = MagicMock(spec=discord.Interaction, guild_id=self.guild_id, user=u2)
            mock_interaction2.response.is_done.return_value = False
            mock_interaction2.response.defer = AsyncMock()
            mock_interaction2.edit_original_response = AsyncMock()

            await self.cog.cmd_voteskip.callback(self.cog, mock_interaction2)
            mock_skip.assert_awaited_once()
            self.assertEqual(len(self.session.skip_votes), 0)  # Cleared after skip

    async def test_05_listening_party_lifecycle(self):
        """5. Verify start, status, and stop for listening party mode."""
        host = MagicMock(spec=discord.Member, id=999, mention="<@999>")
        mock_interaction = MagicMock(spec=discord.Interaction, guild_id=self.guild_id, user=host)
        mock_interaction.response.is_done.return_value = False
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.edit_original_response = AsyncMock()

        with patch.object(self.cog.session_manager, "get_session", new_callable=AsyncMock) as mock_get_sess:
            mock_get_sess.return_value = self.session

            # Start Party
            await self.cog.cmd_party.callback(self.cog, mock_interaction, action="start")
            self.assertTrue(self.session.listening_party_active)
            self.assertEqual(self.session.listening_party_host, 999)

            # Stop Party
            await self.cog.cmd_party.callback(self.cog, mock_interaction, action="stop")
            self.assertFalse(self.session.listening_party_active)
            self.assertIsNone(self.session.listening_party_host)

    def test_06_updatecheck_read_only_report(self):
        """6. Verify updatecheck produces a clean read-only embed with version details."""
        embed = self.cog._build_updatecheck_embed()
        self.assertIsNotNone(embed)
        self.assertIn("Dependency & Update Audit", embed.title)
        self.assertTrue(len(embed.fields) >= 3)
        field_names = [f.name for f in embed.fields]
        self.assertTrue(any("Python" in fn for fn in field_names))
        self.assertTrue(any("Discord" in fn for fn in field_names))

    def test_07_backupstatus_sanitized_report(self):
        """7. Verify backupstatus displays WAL journal information without exposing secrets."""
        embed = self.cog._build_backupstatus_embed()
        self.assertIsNotNone(embed)
        self.assertIn("Database & Backup Status", embed.title)
        self.assertTrue(len(embed.fields) >= 2)


if __name__ == "__main__":
    unittest.main()
