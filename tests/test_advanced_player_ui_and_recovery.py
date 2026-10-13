"""
Unit and Integration Tests for Advanced Discord Music Player UI,
Authoritative State Transitions, Interactive Buttons, and Persistent Playback.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from music_bot.database.models import QueuedTrack
from music_bot.services.player_service import (
    AudioEqualizerView,
    MusicPlayerService,
    NowPlayingControlView,
    VolumeAdjustView,
    build_now_playing_embed,
    format_duration,
)
from music_bot.services.session_service import (
    GuildMusicSession,
    LoopMode,
    PlaybackState,
    SessionManager,
)
from music_bot.services.voice_service import VoiceManager


class TestAdvancedPlayerUIAndRecovery(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.session_manager = SessionManager()
        self.session = GuildMusicSession(guild_id=123456789)
        self.sample_track = QueuedTrack(
            title="Cybernetic Dream",
            url="https://youtube.com/watch?v=mocktrack123",
            stream_url="http://127.0.0.1:8000/stream.mp3",
            duration=210,  # 3m 30s
            artist="SynthNeko",
            thumbnail="https://images.unsplash.com/photo-mock.jpg",
            requester_id=987654321,
            requester_name="Audiophile#0001",
        )

    def test_now_playing_embed_metadata_and_progress(self):
        """1. Verify Now Playing embed displays all required metadata, progress bar, and remaining time."""
        self.session.current_track = self.sample_track
        self.session.state = PlaybackState.PLAYING
        self.session.track_start_time = time.time() - 70  # 1m 10s elapsed
        self.session.volume = 85
        self.session.loop_mode = LoopMode.TRACK
        self.session.eq_preset = "8D Audio"
        self.session.twenty_four_seven = True
        self.session.recovery_status = "Restored from checkpoint (1:10)"

        embed = build_now_playing_embed(self.session)
        self.assertIsNotNone(embed)
        self.assertEqual(embed.title, "🎶 NOW PLAYING")
        self.assertIn("Cybernetic Dream", embed.description)
        self.assertIn("https://youtube.com/watch?v=mocktrack123", embed.description)
        self.assertIn("SynthNeko", embed.description)
        self.assertIn("<@987654321>", embed.description)
        self.assertIn("85%", embed.description)
        self.assertIn("8D Audio", embed.description)
        self.assertIn("Track", embed.description)  # Loop mode
        self.assertIn("Restored from checkpoint", embed.description)  # Recovery status
        self.assertIn("(-02:20)", embed.description)  # Remaining time (210 - 70 = 140s = 02:20)
        self.assertEqual(embed.thumbnail.url, "https://images.unsplash.com/photo-mock.jpg")

    def test_now_playing_embed_playback_statuses(self):
        """Verify Playback status reflects Playing, Paused, Buffering, and Idle states accurately."""
        self.session.current_track = self.sample_track

        self.session.state = PlaybackState.PLAYING
        embed = build_now_playing_embed(self.session)
        self.assertIn("Playing", embed.description)

        self.session.state = PlaybackState.PAUSED
        embed = build_now_playing_embed(self.session)
        self.assertIn("Paused", embed.description)

        self.session.state = PlaybackState.LOADING
        embed = build_now_playing_embed(self.session)
        self.assertIn("Buffering", embed.description)

        self.session.state = PlaybackState.SEARCHING
        embed = build_now_playing_embed(self.session)
        self.assertIn("Buffering", embed.description)

        self.session.state = PlaybackState.RECOVERING
        embed = build_now_playing_embed(self.session)
        self.assertIn("Recovering", embed.description)

        self.session.state = PlaybackState.IDLE
        self.session.current_track = None
        embed = build_now_playing_embed(self.session)
        self.assertIn("No music is currently playing", embed.description)

    def test_now_playing_control_view_clean_redesign(self):
        """2. Verify NowPlayingControlView defines clean minimal 2-row layout and modular sub-panels."""
        from music_bot.services.player_service import QueueSubView, AudioSettingsSubView, AutoDJSubView, SettingsSubView
        view = NowPlayingControlView(self.session)
        custom_ids = {item.custom_id for item in view.children if isinstance(item, discord.ui.Button)}

        expected_buttons = {
            "music_btn_prev",         # Previous
            "music_btn_rewind_10",    # Rewind 10s
            "music_btn_play_pause",   # Pause / Resume
            "music_btn_forward_10",   # Forward 10s
            "music_btn_skip",         # Skip
            "music_btn_queue",        # Queue (Opens Queue Sub-View)
            "music_btn_refresh",      # Refresh panel
            "music_btn_nav_audio",    # Audio & EQ (Opens Audio Sub-View)
            "music_btn_nav_autodj",   # Auto-DJ (Opens Auto-DJ Sub-View)
            "music_btn_nav_settings", # Settings (Opens Settings Sub-View)
            "music_btn_fav",          # Favorite
            "music_btn_stop",         # Stop
        }
        self.assertTrue(expected_buttons.issubset(custom_ids))
        self.assertEqual(len(custom_ids), 12)


        # Verify sub-views are instantiable and possess modular controls
        q_view = QueueSubView(self.session)
        self.assertGreaterEqual(len(q_view.children), 4)

        a_view = AudioSettingsSubView(self.session)
        self.assertGreaterEqual(len(a_view.children), 8)

        dj_view = AutoDJSubView(self.session)
        self.assertGreaterEqual(len(dj_view.children), 5)

        s_view = SettingsSubView(self.session)
        self.assertGreaterEqual(len(s_view.children), 4)


    async def test_send_now_playing_panel_reuses_existing_message(self):
        """Verify send_now_playing_panel edits existing message instead of creating new messages."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.edit = AsyncMock()
        mock_channel.send = AsyncMock(return_value=mock_msg)

        self.session.text_channel = mock_channel
        self.session.current_track = self.sample_track
        self.session.state = PlaybackState.PLAYING

        # First call: no existing message -> sends new message
        await MusicPlayerService.send_now_playing_panel(self.session)
        mock_channel.send.assert_awaited_once()
        self.assertEqual(self.session.now_playing_message, mock_msg)

        # Second call: existing message present -> edits existing message
        await MusicPlayerService.send_now_playing_panel(self.session)
        mock_msg.edit.assert_awaited_once()
        mock_channel.send.assert_awaited_once()  # Still only called once!

    async def test_button_seeking_and_skipping_while_paused(self):
        """3. Verify rewind, forward, and skip buttons work when paused without false 'nothing playing'."""
        self.session.current_track = self.sample_track
        self.session.state = PlaybackState.PAUSED
        self.session.track_start_time = time.time() - 60
        self.session.pause_time = time.time()

        mock_vc = MagicMock()
        mock_vc.is_playing.return_value = False
        mock_vc.is_paused.return_value = True
        mock_vc.channel = MagicMock(id=111, mention="<#111>")
        self.session.voice_client = mock_vc

        view = NowPlayingControlView(self.session)

        # Mock interaction
        mock_member = MagicMock(spec=discord.Member)
        mock_voice_state = MagicMock()
        mock_voice_state.channel = mock_vc.channel
        mock_member.voice = mock_voice_state

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock(id=self.session.guild_id)
        mock_interaction.user = mock_member
        mock_interaction.response.is_done.return_value = False
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()

        with patch.object(MusicPlayerService, "seek", new_callable=AsyncMock) as mock_seek:
            # Rewind 10s button
            rewind_btn = next(b for b in view.children if b.custom_id == "music_btn_rewind_10")
            await rewind_btn.callback(mock_interaction)
            mock_seek.assert_awaited_once()

        with patch.object(MusicPlayerService, "seek", new_callable=AsyncMock) as mock_seek:
            # Forward 10s button
            fwd_btn = next(b for b in view.children if b.custom_id == "music_btn_forward_10")
            await fwd_btn.callback(mock_interaction)
            mock_seek.assert_awaited_once()

        # Skip button while paused
        skip_btn = next(b for b in view.children if b.custom_id == "music_btn_skip")
        await skip_btn.callback(mock_interaction)
        mock_vc.stop.assert_called_once()

    async def test_stop_button_atomically_transitions_to_stopped(self):
        """Verify stop button sets STOPPED state, clears queue, disconnects voice client."""
        self.session.current_track = self.sample_track
        self.session.state = PlaybackState.PLAYING
        self.session.queue.append(self.sample_track)

        mock_vc = MagicMock()
        mock_vc.channel = MagicMock(id=111, mention="<#111>")
        mock_vc.disconnect = AsyncMock()
        self.session.voice_client = mock_vc

        mock_msg = MagicMock()
        mock_msg.delete = AsyncMock()
        mock_msg.edit = AsyncMock()
        self.session.now_playing_message = mock_msg

        view = NowPlayingControlView(self.session)

        mock_member = MagicMock(spec=discord.Member)
        mock_voice_state = MagicMock()
        mock_voice_state.channel = mock_vc.channel
        mock_member.voice = mock_voice_state

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock(id=self.session.guild_id)
        mock_interaction.user = mock_member
        mock_interaction.response.is_done.return_value = False
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()

        stop_btn = next(b for b in view.children if b.custom_id == "music_btn_stop")
        await stop_btn.callback(mock_interaction)

        self.assertTrue(self.session.is_intentional_stop)
        self.assertEqual(len(self.session.queue), 0)
        self.assertIsNone(self.session.current_track)
        mock_vc.stop.assert_called_once()
        mock_vc.disconnect.assert_awaited_once()
        self.assertTrue(mock_msg.edit.awaited or mock_msg.delete.awaited)

    async def test_empty_voice_channel_preserves_session(self):
        """4. Verify VoiceManager._auto_leave_worker checkpoints session before disconnecting."""
        self.session.current_track = self.sample_track
        self.session.state = PlaybackState.PLAYING
        self.session.queue.append(self.sample_track)

        mock_vc = MagicMock()
        mock_channel = MagicMock()
        mock_channel.members = [MagicMock(bot=True)]  # Only bot present
        mock_vc.channel = mock_channel
        mock_vc.is_connected.return_value = True
        mock_vc.is_playing.return_value = True
        mock_vc.disconnect = AsyncMock()
        self.session.voice_client = mock_vc

        mock_bot = MagicMock()
        mock_bot.db = None

        with patch("music_bot.services.session_memory_service.MusicSessionMemoryService.checkpoint_session", new_callable=AsyncMock) as mock_cp:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await VoiceManager._auto_leave_worker(mock_bot, self.session, timeout=1)

                mock_cp.assert_awaited_once()
                self.assertFalse(self.session.is_intentional_stop)
                self.assertIsNotNone(self.session.recovery_status)
                self.assertIn("Saved on empty channel", self.session.recovery_status)
                self.assertEqual(len(self.session.queue), 1)  # Queue preserved!

    def test_multi_guild_session_isolation(self):
        """5. Verify independent playback state and locks across distinct guilds."""
        sess_1 = self.session_manager.get_session_sync(guild_id=101)
        sess_2 = self.session_manager.get_session_sync(guild_id=202)

        self.assertNotEqual(sess_1.session_id, sess_2.session_id)
        sess_1.volume = 40
        sess_2.volume = 95
        self.assertEqual(sess_1.volume, 40)
        self.assertEqual(sess_2.volume, 95)

        sess_1.state = PlaybackState.PLAYING
        sess_2.state = PlaybackState.IDLE
        self.assertEqual(sess_1.state, PlaybackState.PLAYING)
        self.assertEqual(sess_2.state, PlaybackState.IDLE)

    async def test_skip_current_helper(self):
        """Verify MusicPlayerService.skip_current cleanly stops voice client."""
        mock_vc = MagicMock()
        mock_vc.is_playing.return_value = True
        self.session.voice_client = mock_vc

        result = await MusicPlayerService.skip_current(self.session)
        self.assertTrue(result)
        mock_vc.stop.assert_called_once()

    async def test_queue_move_and_remove_operations(self):
        """6. Verify /move, /remove, and /shuffle commands execute cleanly without deque attribute errors."""
        from collections import deque
        from music_bot.commands.music_cog import MusicCog

        t1 = QueuedTrack(title="Track 1", url="http://1", duration=100)
        t2 = QueuedTrack(title="Track 2", url="http://2", duration=200)
        t3 = QueuedTrack(title="Track 3", url="http://3", duration=300)
        self.session.queue = deque([t1, t2, t3])

        mock_bot = MagicMock()
        cog = MusicCog(mock_bot)

        # Mock interaction for /move
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild_id = self.session.guild_id
        mock_interaction.response.is_done.return_value = False
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()

        with patch.object(cog.session_manager, "get_session", new_callable=AsyncMock) as mock_get_sess:
            mock_get_sess.return_value = self.session

            # Move Track 3 (pos 3) to pos 1
            await cog.music_move.callback(cog, mock_interaction, from_pos=3, to_pos=1)
            self.assertEqual(self.session.queue[0].title, "Track 3")
            self.assertEqual(self.session.queue[1].title, "Track 1")
            self.assertEqual(self.session.queue[2].title, "Track 2")

            # Remove Track 2 (pos 3)
            await cog.music_remove.callback(cog, mock_interaction, position=3)
            self.assertEqual(len(self.session.queue), 2)
            self.assertEqual(self.session.queue[0].title, "Track 3")
            self.assertEqual(self.session.queue[1].title, "Track 1")

            # Shuffle remaining 2 tracks
            await cog.music_shuffle.callback(cog, mock_interaction)
            self.assertEqual(len(self.session.queue), 2)
            self.assertIsInstance(self.session.queue, deque)


if __name__ == "__main__":
    unittest.main()
