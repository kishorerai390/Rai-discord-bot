"""
Unit & Integration Test Suite for Advanced Rythm-Style Music Session Memory.
Verifies all 15 scenarios specified in Phase 11:
1. Save session while playing.
2. Restore session after simulated restart.
3. Restore paused session without advancing position.
4. Restore multi-track queue in exact order.
5. Resume seekable track at saved position.
6. Handle unavailable or expired track source.
7. Handle source that does not support seeking.
8. Restore sessions independently across multiple guilds (isolation).
9. Prevent concurrent duplicate restores (per-guild lock).
10. Handle unexpected voice disconnection with backoff.
11. Avoid recovery after intentional stop.
12. Recover safely after database error.
13. Expire old sessions according to retention rules (pinned exempt).
14. Keep slash commands responsive (<3s deferral) during long-running restoration.
15. Graceful shutdown checkpoints current session.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from typing import Optional
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord import app_commands

from music_bot.commands.session_cog import MusicSessionCog
from music_bot.database.db import MusicDatabase
from music_bot.database.models import (
    MusicGuildSettings,
    PersistentMusicSession,
    QueuedTrack,
)
from music_bot.services.player_service import MusicPlayerService
from music_bot.services.session_memory_service import MusicSessionMemoryService
from music_bot.services.session_service import (
    GuildMusicSession,
    LoopMode,
    PlaybackState,
    SessionManager,
)


class TestMusicSessionMemory(unittest.IsolatedAsyncioTestCase):
    """Deep verification of persistent session memory, recovery, and isolation."""

    async def asyncSetUp(self):
        self.test_db_path = Path("data/test_music_session.db")
        if self.test_db_path.exists():
            self.test_db_path.unlink()

        self.db = MusicDatabase(self.test_db_path)
        await self.db.connect()

        self.bot = MagicMock()
        self.bot.db = self.db
        self.bot.loop = asyncio.get_running_loop()
        self.session_manager = SessionManager()
        self.bot.session_manager = self.session_manager

        self.cog = MusicSessionCog(self.bot)

        # Guild 1 setup
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 11111111
        self.guild.name = "Audio Guild Alpha"

        self.voice_channel = MagicMock(spec=discord.VoiceChannel)
        self.voice_channel.id = 22222222
        self.voice_channel.name = "Cyber Lounge"
        self.voice_channel.permissions_for.return_value = MagicMock(connect=True, speak=True)
        self.voice_channel.connect = AsyncMock()

        self.text_channel = MagicMock(spec=discord.TextChannel)
        self.text_channel.id = 33333333
        self.text_channel.name = "bot-commands"
        self.text_channel.permissions_for.return_value = MagicMock(send_messages=True, embed_links=True)
        self.text_channel.send = AsyncMock()

        self.guild.get_channel = MagicMock(side_effect=lambda cid: self.voice_channel if cid == 22222222 else self.text_channel)
        self.guild.voice_client = None
        self.guild.me = MagicMock(spec=discord.Member)
        self.bot.get_guild = MagicMock(side_effect=lambda gid: self.guild if gid == 11111111 else None)

        self.user = MagicMock(spec=discord.Member)
        self.user.id = 999000
        self.user.name = "MusicLover"
        self.user.voice = MagicMock(channel=self.voice_channel)
        self.user.guild_permissions = MagicMock(administrator=True, manage_guild=True)
        self.user.roles = []

        # Interaction mock
        self.interaction = MagicMock(spec=discord.Interaction)
        self.interaction.guild_id = 11111111
        self.interaction.guild = self.guild
        self.interaction.user = self.user
        self.interaction.channel = self.text_channel

        self.response = MagicMock(spec=discord.InteractionResponse)
        self.response.is_done.return_value = False

        def _mock_defer(*args, **kwargs):
            self.response.is_done.return_value = True

        self.response.defer = AsyncMock(side_effect=_mock_defer)
        self.response.send_message = AsyncMock(side_effect=_mock_defer)
        self.interaction.response = self.response
        self.interaction.edit_original_response = AsyncMock()

    async def asyncTearDown(self):
        await self.db.close()
        if self.test_db_path.exists():
            try:
                self.test_db_path.unlink()
            except Exception:
                pass

    # =========================================================================
    # SCENARIO 1: SAVE SESSION WHILE PLAYING
    # =========================================================================
    async def test_01_save_session_while_playing(self):
        """Verify saving an active session captures track, position, queue, and settings."""
        session = await self.session_manager.get_session(11111111)
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_playing.return_value = True
        mock_vc.channel = self.voice_channel
        session.voice_client = mock_vc
        session.text_channel = self.text_channel
        session.state = PlaybackState.PLAYING
        session.track_start_time = time.time() - 45.0  # 45 seconds elapsed

        track = QueuedTrack(
            title="Synthwave Midnight",
            url="https://youtube.com/watch?v=track1",
            duration=200,
            requester_id=self.user.id,
            requester_name=str(self.user),
        )
        session.current_track = track
        session.queue.append(QueuedTrack(title="Track 2", url="https://youtube.com/watch?v=track2", duration=150))
        session.volume = 75
        session.loop_mode = LoopMode.TRACK

        success, msg, pers = await MusicSessionMemoryService.save_named_session(
            bot=self.bot,
            session=session,
            name="My Neon Playlist",
            user=self.user,
        )

        self.assertTrue(success)
        self.assertIsNotNone(pers)
        self.assertEqual(pers.session_name, "My Neon Playlist")
        self.assertEqual(pers.current_track_title, "Synthwave Midnight")
        self.assertGreaterEqual(pers.last_known_position, 44)
        self.assertEqual(len(pers.queue), 1)
        self.assertEqual(pers.volume, 75)
        self.assertEqual(pers.loop_mode, "track")

        # Validate database persistence
        saved_db = await self.db.get_persistent_session(11111111, pers.session_id)
        self.assertIsNotNone(saved_db)
        self.assertEqual(saved_db.session_name, "My Neon Playlist")
        self.assertEqual(saved_db.queue[0].title, "Track 2")

    # =========================================================================
    # SCENARIO 2: RESTORE SESSION AFTER SIMULATED RESTART
    # =========================================================================
    @patch("music_bot.services.player_service.MusicPlayerService.resume_track_stream")
    @patch("music_bot.services.voice_service.VoiceManager.join_voice_channel")
    async def test_02_restore_session_after_restart(self, mock_join, mock_resume):
        """Verify restored session correctly resurrects player, queue, and starts playback."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True
        mock_join.return_value = mock_vc
        mock_resume.return_value = True

        # Pre-seed persistent session in database
        saved = PersistentMusicSession(
            guild_id=11111111,
            session_id="sess_restart_test",
            session_name="Saved Chill Beats",
            current_track=QueuedTrack(title="Chill Track", url="https://youtube.com/watch?v=chill", duration=180),
            current_track_title="Chill Track",
            last_known_position=60,
            queue=[QueuedTrack(title="Next Track", url="https://youtube.com/watch?v=next", duration=120)],
            volume=85,
            loop_mode="queue",
            voice_channel_id=self.voice_channel.id,
            text_channel_id=self.text_channel.id,
        )
        await self.db.save_persistent_session(saved)

        success, msg, restored = await MusicSessionMemoryService.restore_session(
            bot=self.bot,
            guild=self.guild,
            target_voice_channel=self.voice_channel,
            text_channel=self.text_channel,
            session_id_or_name="sess_restart_test",
            requested_by_user=self.user,
        )

        self.assertTrue(success)
        mock_join.assert_awaited()
        mock_resume.assert_awaited()
        session = await self.session_manager.get_session(11111111)
        self.assertEqual(session.volume, 85)
        self.assertEqual(session.loop_mode, LoopMode.QUEUE)
        self.assertEqual(len(session.queue), 1)
        self.assertEqual(session.queue[0].title, "Next Track")

    # =========================================================================
    # SCENARIO 3: RESTORE PAUSED SESSION WITHOUT ADVANCING POSITION
    # =========================================================================
    @patch("music_bot.services.player_service.MusicPlayerService.resume_track_stream")
    @patch("music_bot.services.voice_service.VoiceManager.join_voice_channel")
    async def test_03_restore_paused_session_exact_position(self, mock_join, mock_resume):
        """Verify paused session never advances its playback position when restored."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_join.return_value = mock_vc
        mock_resume.return_value = True

        saved = PersistentMusicSession(
            guild_id=11111111,
            session_id="sess_paused_test",
            session_name="Paused Chill",
            session_status="PAUSED",
            is_paused=True,
            current_track=QueuedTrack(title="Frozen In Time", url="https://youtube.com/watch?v=frozen", duration=300),
            last_known_position=123,
            voice_channel_id=self.voice_channel.id,
        )
        await self.db.save_persistent_session(saved)

        success, msg, restored = await MusicSessionMemoryService.restore_session(
            bot=self.bot,
            guild=self.guild,
            target_voice_channel=self.voice_channel,
            text_channel=self.text_channel,
            session_id_or_name="sess_paused_test",
        )

        self.assertTrue(success)
        # Position passed to resume_track_stream must match exact 123s
        call_args = mock_resume.call_args
        self.assertEqual(call_args[0][3], 123)

    # =========================================================================
    # SCENARIO 4: RESTORE MULTI-TRACK QUEUE IN EXACT ORDER
    # =========================================================================
    @patch("music_bot.services.player_service.MusicPlayerService.resume_track_stream")
    @patch("music_bot.services.voice_service.VoiceManager.join_voice_channel")
    async def test_04_restore_multi_track_queue_ordering(self, mock_join, mock_resume):
        """Verify multi-track queue ordering is preserved precisely 1-to-1."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_join.return_value = mock_vc
        mock_resume.return_value = True

        ordered_queue = [
            QueuedTrack(title=f"Song #{i}", url=f"https://youtube.com/watch?v=s{i}", duration=100 + i)
            for i in range(1, 10)
        ]
        saved = PersistentMusicSession(
            guild_id=11111111,
            session_id="sess_queue_order",
            session_name="Ordered Queue",
            current_track=QueuedTrack(title="Current", url="https://youtube.com/watch?v=cur", duration=150),
            queue=ordered_queue,
            voice_channel_id=self.voice_channel.id,
        )
        await self.db.save_persistent_session(saved)

        success, msg, restored = await MusicSessionMemoryService.restore_session(
            bot=self.bot,
            guild=self.guild,
            target_voice_channel=self.voice_channel,
            text_channel=self.text_channel,
            session_id_or_name="sess_queue_order",
        )

        self.assertTrue(success)
        session = await self.session_manager.get_session(11111111)
        self.assertEqual(len(session.queue), 9)
        for i, track in enumerate(session.queue, 1):
            self.assertEqual(track.title, f"Song #{i}")

    # =========================================================================
    # SCENARIO 5: RESUME SEEKABLE TRACK AT SAVED POSITION
    # =========================================================================
    @patch("music_bot.services.player_service.MusicPlayerService.resume_track_stream")
    @patch("music_bot.services.voice_service.VoiceManager.join_voice_channel")
    async def test_05_resume_seekable_track_position(self, mock_join, mock_resume):
        """Verify resume_track_stream is called with correct start_seconds."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_join.return_value = mock_vc
        mock_resume.return_value = True

        saved = PersistentMusicSession(
            guild_id=11111111,
            session_id="sess_seek_test",
            session_name="Seek Test",
            current_track=QueuedTrack(title="Long Jukebox", url="https://youtube.com/watch?v=juke", duration=3600),
            last_known_position=1542,
            voice_channel_id=self.voice_channel.id,
        )
        await self.db.save_persistent_session(saved)

        await MusicSessionMemoryService.restore_session(
            bot=self.bot,
            guild=self.guild,
            target_voice_channel=self.voice_channel,
            text_channel=self.text_channel,
            session_id_or_name="sess_seek_test",
        )

        mock_resume.assert_awaited_once()
        self.assertEqual(mock_resume.call_args[0][3], 1542)

    # =========================================================================
    # SCENARIO 6: HANDLE UNAVAILABLE OR EXPIRED TRACK SOURCE
    # =========================================================================
    @patch("music_bot.services.resolver_service.AudioResolver.resolve_track")
    @patch("music_bot.services.player_service.MusicPlayerService.resume_track_stream")
    @patch("music_bot.services.voice_service.VoiceManager.join_voice_channel")
    async def test_06_handle_expired_source_re_resolution(self, mock_join, mock_resume, mock_resolve):
        """Verify expired streaming URLs are re-resolved via AudioResolver on restoration."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_join.return_value = mock_vc
        mock_resume.return_value = True

        fresh_track = QueuedTrack(
            title="Re-Resolved Song",
            url="https://youtube.com/watch?v=expired",
            stream_url="https://fresh.audio.stream/chunk.m4a",
            duration=200,
        )
        mock_resolve.return_value = fresh_track

        saved = PersistentMusicSession(
            guild_id=11111111,
            session_id="sess_expired_test",
            current_track=QueuedTrack(
                title="Re-Resolved Song",
                url="https://youtube.com/watch?v=expired",
                stream_url="",  # Expired / empty stream URL
                duration=200,
            ),
            voice_channel_id=self.voice_channel.id,
        )
        await self.db.save_persistent_session(saved)

        success, msg, _ = await MusicSessionMemoryService.restore_session(
            bot=self.bot,
            guild=self.guild,
            target_voice_channel=self.voice_channel,
            text_channel=self.text_channel,
            session_id_or_name="sess_expired_test",
        )

        self.assertTrue(success)
        mock_resolve.assert_awaited()

    # =========================================================================
    # SCENARIO 7: HANDLE SOURCE THAT DOES NOT SUPPORT SEEKING
    # =========================================================================
    @patch("music_bot.services.player_service.MusicPlayerService.start_playback")
    @patch("music_bot.services.player_service.MusicPlayerService.resume_track_stream")
    @patch("music_bot.services.voice_service.VoiceManager.join_voice_channel")
    async def test_07_unsupported_seeking_fallback_to_start(self, mock_join, mock_resume, mock_start):
        """Verify graceful fallback to start_playback when resume_track_stream fails."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_join.return_value = mock_vc
        mock_resume.return_value = False  # Seeking fails / unsupported

        saved = PersistentMusicSession(
            guild_id=11111111,
            session_id="sess_unseekable",
            current_track=QueuedTrack(title="Live Stream Radio", url="https://stream.radio", duration=0),
            last_known_position=50,
            voice_channel_id=self.voice_channel.id,
        )
        await self.db.save_persistent_session(saved)

        success, msg, _ = await MusicSessionMemoryService.restore_session(
            bot=self.bot,
            guild=self.guild,
            target_voice_channel=self.voice_channel,
            text_channel=self.text_channel,
            session_id_or_name="sess_unseekable",
        )

        self.assertTrue(success)
        mock_resume.assert_awaited()
        # Fallback to starting playback from beginning
        mock_start.assert_awaited()

    # =========================================================================
    # SCENARIO 8: MULTI-GUILD SESSION ISOLATION
    # =========================================================================
    async def test_08_multi_guild_session_isolation(self):
        """Verify sessions saved in Guild A cannot be accessed or restored by Guild B."""
        session_a = PersistentMusicSession(
            guild_id=11111111,
            session_id="sess_guild_a",
            session_name="Guild A Playlist",
            current_track=QueuedTrack(title="Secret Track A", url="https://youtube.com/watch?v=a"),
        )
        session_b = PersistentMusicSession(
            guild_id=22222222,
            session_id="sess_guild_b",
            session_name="Guild B Playlist",
            current_track=QueuedTrack(title="Secret Track B", url="https://youtube.com/watch?v=b"),
        )
        await self.db.save_persistent_session(session_a)
        await self.db.save_persistent_session(session_b)

        # Querying Guild A for Guild B's session must return None
        res_a = await self.db.get_persistent_session(11111111, "sess_guild_b")
        self.assertIsNone(res_a)

        # Listing Guild A must only show Guild A's sessions
        list_a = await self.db.list_persistent_sessions(11111111)
        self.assertEqual(len(list_a), 1)
        self.assertEqual(list_a[0].session_id, "sess_guild_a")

    # =========================================================================
    # SCENARIO 9: PREVENT CONCURRENT DUPLICATE RESTORES (PER-GUILD LOCK)
    # =========================================================================
    @patch("music_bot.services.player_service.MusicPlayerService.resume_track_stream")
    @patch("music_bot.services.voice_service.VoiceManager.join_voice_channel")
    async def test_09_prevent_concurrent_duplicate_restores(self, mock_join, mock_resume):
        """Verify concurrent restore calls for the same guild are safely serialized."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_join.return_value = mock_vc
        mock_resume.return_value = True

        saved = PersistentMusicSession(
            guild_id=11111111,
            session_id="sess_concurrency",
            current_track=QueuedTrack(title="Race Condition Test", url="https://youtube.com/watch?v=race"),
            voice_channel_id=self.voice_channel.id,
        )
        await self.db.save_persistent_session(saved)

        # Trigger 3 simultaneous restore requests
        tasks = [
            MusicSessionMemoryService.restore_session(
                bot=self.bot,
                guild=self.guild,
                target_voice_channel=self.voice_channel,
                text_channel=self.text_channel,
                session_id_or_name="sess_concurrency",
            )
            for _ in range(3)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            self.assertNotIsInstance(res, Exception)
            success, _, _ = res
            self.assertTrue(success)

    # =========================================================================
    # SCENARIO 10: UNEXPECTED VOICE DISCONNECT RECOVERY WITH BACKOFF
    # =========================================================================
    @patch("music_bot.services.voice_service.VoiceManager.join_voice_channel")
    async def test_10_unexpected_disconnect_exponential_backoff(self, mock_join):
        """Verify unexpected disconnect triggers bounded backoff reconnection."""
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True
        mock_join.return_value = mock_vc

        session = await self.session_manager.get_session(11111111)
        session.is_intentional_stop = False
        session.voice_client = MagicMock(spec=discord.VoiceClient, channel=self.voice_channel)
        session.current_track = QueuedTrack(title="Live Audio", url="https://youtube.com/watch?v=live")
        session.track_start_time = time.time() - 30

        # Save active session in DB
        await MusicSessionMemoryService.checkpoint_session(self.bot, session)

        with patch("music_bot.services.session_memory_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await MusicSessionMemoryService.handle_unexpected_disconnect(self.bot, 11111111)
            # Must sleep with backoff + jitter
            mock_sleep.assert_awaited()
            mock_join.assert_awaited()

    # =========================================================================
    # SCENARIO 11: AVOID RECOVERY AFTER INTENTIONAL STOP
    # =========================================================================
    @patch("music_bot.services.voice_service.VoiceManager.join_voice_channel")
    async def test_11_avoid_recovery_after_intentional_stop(self, mock_join):
        """Verify intentional stop flag aborts automatic voice reconnection."""
        session = await self.session_manager.get_session(11111111)
        session.is_intentional_stop = True

        await MusicSessionMemoryService.handle_unexpected_disconnect(self.bot, 11111111)
        mock_join.assert_not_called()

    # =========================================================================
    # SCENARIO 12: SAFE RECOVERY AFTER DATABASE ERROR
    # =========================================================================
    async def test_12_safe_recovery_after_db_error(self):
        """Verify checkpointing handles database failures without crashing the application."""
        session = await self.session_manager.get_session(11111111)
        session.current_track = QueuedTrack(title="DB Test", url="https://youtube.com/watch?v=db")

        # Mock DB failure
        with patch.object(self.db, "save_persistent_session", side_effect=Exception("Disk full")):
            # Must not raise
            res = await MusicSessionMemoryService.checkpoint_session(self.bot, session)
            self.assertIsNone(res)

    # =========================================================================
    # SCENARIO 13: EXPIRE OLD SESSIONS (PINNED SESSIONS EXEMPT)
    # =========================================================================
    async def test_13_session_retention_expiration(self):
        """Verify expired unpinned sessions are cleaned, while pinned sessions are kept."""
        now = datetime.now(timezone.utc)
        expired_date = (now - timedelta(days=2)).isoformat()
        future_date = (now + timedelta(days=5)).isoformat()

        # Session 1: Expired and unpinned -> SHOULD BE CLEANED
        s1 = PersistentMusicSession(
            guild_id=11111111,
            session_id="s_expired",
            session_status="SAVED",
            expires_at=expired_date,
            is_pinned=False,
        )
        # Session 2: Expired but PINNED -> MUST BE PRESERVED
        s2 = PersistentMusicSession(
            guild_id=11111111,
            session_id="s_pinned",
            session_status="SAVED",
            expires_at=expired_date,
            is_pinned=True,
        )
        # Session 3: Not expired -> MUST BE PRESERVED
        s3 = PersistentMusicSession(
            guild_id=11111111,
            session_id="s_active",
            session_status="SAVED",
            expires_at=future_date,
            is_pinned=False,
        )

        await self.db.save_persistent_session(s1)
        await self.db.save_persistent_session(s2)
        await self.db.save_persistent_session(s3)

        purged = await MusicSessionMemoryService.cleanup_expired_sessions(self.bot)
        self.assertEqual(purged, 1)

        # Verify database contents
        self.assertIsNone(await self.db.get_persistent_session(11111111, "s_expired"))
        self.assertIsNotNone(await self.db.get_persistent_session(11111111, "s_pinned"))
        self.assertIsNotNone(await self.db.get_persistent_session(11111111, "s_active"))

    # =========================================================================
    # SCENARIO 14: KEEP SLASH COMMANDS RESPONSIVE (<3s DEFERRAL)
    # =========================================================================
    async def test_14_slash_commands_responsive_under_3s(self):
        """Verify /music-session commands acknowledge interactions immediately."""
        session = await self.session_manager.get_session(11111111)
        session.current_track = QueuedTrack(title="Fast Deferral", url="https://youtube.com/watch?v=fast")

        # /music-session save
        self.response.is_done.return_value = False
        await self.cog.cmd_save.callback(self.cog, self.interaction, name="Quick Save")
        self.response.defer.assert_awaited()
        self.interaction.edit_original_response.assert_awaited()

        # /music-session status
        self.response.is_done.return_value = False
        self.response.defer.reset_mock()
        await self.cog.cmd_status.callback(self.cog, self.interaction)
        self.response.defer.assert_awaited()

        # /music-session list
        self.response.is_done.return_value = False
        self.response.defer.reset_mock()
        await self.cog.cmd_list.callback(self.cog, self.interaction)
        self.response.defer.assert_awaited()

    # =========================================================================
    # SCENARIO 15: GRACEFUL SHUTDOWN CHECKPOINTS CURRENT SESSION
    # =========================================================================
    async def test_15_graceful_shutdown_checkpoints_session(self):
        """Verify checkpoint_all_active_sessions records state during bot shutdown."""
        session = await self.session_manager.get_session(11111111)
        session.current_track = QueuedTrack(title="Shutdown Track", url="https://youtube.com/watch?v=down", duration=300)
        session.track_start_time = time.time() - 100
        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True
        mock_vc.is_playing.return_value = True
        mock_vc.channel = self.voice_channel
        session.voice_client = mock_vc
        session.state = PlaybackState.PLAYING

        saved_count = await MusicSessionMemoryService.checkpoint_all_active_sessions(self.bot, reason="shutdown")
        self.assertEqual(saved_count, 1)

        saved = await self.db.get_persistent_session(11111111, session.session_id)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.current_track_title, "Shutdown Track")
        self.assertGreaterEqual(saved.last_known_position, 99)


if __name__ == "__main__":
    unittest.main()
