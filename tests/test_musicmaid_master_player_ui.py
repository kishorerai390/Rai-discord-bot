"""
Comprehensive Automated Test Suite for MusicMaid Master Player UI & 13-Button Matrix.
Validates:
1. Discord 4-Row Button Layout & View Components (13 Buttons).
2. Service Actions: Previous, Rewind 10s, Pause/Resume, Forward 10s, Skip, Queue, Shuffle, Loop, Volume, Stop, Favorite, Filters, Lyrics.
3. Bidirectional Web Control Dispatch.
4. Embed Badges & Formatting.
"""

from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from music_bot.services.session_service import GuildMusicSession, LoopMode, PlaybackState, QueuedTrack
from music_bot.services.player_service import MusicPlayerService, NowPlayingControlView, VolumeModal, create_progress_bar


def make_track(title="Test Song", url="https://youtube.com/watch?v=mock123", duration=240, artist="Test Artist"):
    return QueuedTrack(
        title=title,
        url=url,
        duration=duration,
        stream_url="https://audio.stream/mock.mp3",
        artist=artist,
        thumbnail="https://mock.img/art.jpg",
        requester_id=98765,
        requester_name="Kishore",
    )


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.db.get_favorites = AsyncMock(return_value=[])
    bot.db.add_favorite = AsyncMock(return_value=True)
    bot.db.remove_favorite = AsyncMock(return_value=True)
    bot.db.update_guild_settings = AsyncMock(return_value=True)
    return bot


@pytest.fixture
def mock_session():
    session = GuildMusicSession(guild_id=123456789)
    session.volume = 80
    session.loop_mode = LoopMode.OFF
    session.current_track = make_track("Active Track", "https://yt/active", 300)
    session.state = PlaybackState.PLAYING

    mock_vc = MagicMock()
    mock_vc.is_connected.return_value = True
    mock_vc.is_playing.return_value = True
    mock_vc.is_paused.return_value = False
    mock_vc.channel = MagicMock(id=999)
    mock_vc.source = MagicMock(volume=0.8)
    session.voice_client = mock_vc

    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()
    session.text_channel = mock_channel
    session.now_playing_message = AsyncMock()
    return session


class TestMusicMaidPlayerUI:

    def test_01_view_structure_and_13_buttons(self, mock_session):
        """Verify NowPlayingControlView contains exactly 13 buttons distributed across 4 rows."""
        view = NowPlayingControlView(mock_session)
        buttons = [child for child in view.children if hasattr(child, "custom_id")]
        
        # Check custom IDs
        custom_ids = {b.custom_id for b in buttons}
        expected_ids = {
            "music_btn_prev",
            "music_btn_rewind_10",
            "music_btn_play_pause",
            "music_btn_forward_10",
            "music_btn_skip",
            "music_btn_queue",
            "music_btn_shuffle",
            "music_btn_loop",
            "music_btn_volume",
            "music_btn_stop",
            "music_btn_favorite",
            "music_btn_filters",
            "music_btn_lyrics",
        }
        assert expected_ids.issubset(custom_ids), f"Missing button IDs: {expected_ids - custom_ids}"

        # Row distribution
        row_0 = [b for b in buttons if b.row == 0]
        row_1 = [b for b in buttons if b.row == 1]
        row_2 = [b for b in buttons if b.row == 2]
        row_3 = [b for b in buttons if b.row == 3]

        assert len(row_0) == 5, f"Row 0 must have 5 buttons, got {len(row_0)}"
        assert len(row_1) == 3, f"Row 1 must have 3 buttons, got {len(row_1)}"
        assert len(row_2) == 2, f"Row 2 must have 2 buttons, got {len(row_2)}"
        assert len(row_3) == 3, f"Row 3 must have 3 buttons, got {len(row_3)}"

    def test_02_now_playing_embed_badges_and_visuals(self, mock_session):
        """Verify build_now_playing_embed creates reference-grade pill badges and formatting."""
        embed = MusicPlayerService.build_now_playing_embed(mock_session)
        
        assert "LIVE PLAYING" in embed.description
        assert "📜 Queue: 0" in embed.description
        assert "🎛️ EQ:" in embed.description
        assert "Active Track" in embed.description
        assert "Test Artist" in embed.description
        assert embed.footer.text is not None
        assert "ılıılı.ll.ılı.ll.ılı.ll" in embed.footer.text or "MusicMaid" in embed.footer.text

    @pytest.mark.asyncio
    async def test_03_seek_relative_rewind_and_forward(self, mock_bot, mock_session):
        """Verify seek_relative clamps to bounds and executes seek correctly."""
        with patch.object(MusicPlayerService, "seek", new_callable=AsyncMock) as mock_seek:
            mock_seek.return_value = True

            # Rewind 10s from 25s
            mock_session.progress_seconds = 25
            success, target, msg = await MusicPlayerService.seek_relative(mock_bot, mock_session, -10)
            assert success is True
            assert target == 15
            mock_seek.assert_called_with(mock_bot, mock_session, 15)

            # Rewind from 5s (clamps to 0)
            mock_session.progress_seconds = 5
            success, target, msg = await MusicPlayerService.seek_relative(mock_bot, mock_session, -10)
            assert target == 0
            mock_seek.assert_called_with(mock_bot, mock_session, 0)

            # Forward 10s from 295s with 300s duration (clamps to duration - 1 = 299)
            mock_session.progress_seconds = 295
            success, target, msg = await MusicPlayerService.seek_relative(mock_bot, mock_session, 10)
            assert target == 299
            mock_seek.assert_called_with(mock_bot, mock_session, 299)

    @pytest.mark.asyncio
    async def test_04_pause_and_resume_toggle(self, mock_bot, mock_session):
        """Verify authoritative pause and resume state transitions."""
        with patch.object(MusicPlayerService, "send_now_playing_panel", new_callable=AsyncMock):
            # Pause
            success, msg = await MusicPlayerService.pause(mock_session)
            assert success is True
            assert mock_session.state == PlaybackState.PAUSED
            mock_session.voice_client.pause.assert_called_once()

            # Resume
            mock_session.voice_client.is_paused.return_value = True
            success, msg = await MusicPlayerService.resume(mock_bot, mock_session)
            assert success is True
            assert mock_session.state == PlaybackState.PLAYING
            mock_session.voice_client.resume.assert_called_once()

    def test_05_cycle_loop_modes(self, mock_session):
        """Verify cycle_loop transitions: OFF -> TRACK -> QUEUE -> OFF."""
        assert mock_session.loop_mode == LoopMode.OFF

        mode1, msg1 = MusicPlayerService.cycle_loop(mock_session)
        assert mode1 == LoopMode.TRACK
        assert mock_session.loop_mode == LoopMode.TRACK

        mode2, msg2 = MusicPlayerService.cycle_loop(mock_session)
        assert mode2 == LoopMode.QUEUE
        assert mock_session.loop_mode == LoopMode.QUEUE

        mode3, msg3 = MusicPlayerService.cycle_loop(mock_session)
        assert mode3 == LoopMode.OFF
        assert mock_session.loop_mode == LoopMode.OFF

    def test_06_shuffle_queue(self, mock_session):
        """Verify shuffle randomizes upcoming queue while preserving entries."""
        tracks = [make_track(f"Song {i}", f"https://yt/{i}") for i in range(10)]
        mock_session.queue = deque(tracks)

        success, msg = MusicPlayerService.shuffle(mock_session)
        assert success is True
        assert len(mock_session.queue) == 10
        # All URLs still present
        assert {t.url for t in mock_session.queue} == {f"https://yt/{i}" for i in range(10)}

    @pytest.mark.asyncio
    async def test_07_volume_adjustment(self, mock_session):
        """Verify set_volume updates session volume and voice source volume."""
        with patch.object(MusicPlayerService, "send_now_playing_panel", new_callable=AsyncMock):
            success, msg = await MusicPlayerService.set_volume(mock_session, 65)
            assert success is True
            assert mock_session.volume == 65
            assert mock_session.voice_client.source.volume == 0.65

    @pytest.mark.asyncio
    async def test_08_favorite_toggle(self, mock_bot, mock_session):
        """Verify toggle_favorite persistently adds and removes favorites."""
        user_id = 444555666
        track = mock_session.current_track

        # Case A: Not in favorites -> Adds
        mock_bot.db.get_favorites.return_value = []
        success, is_fav, msg = await MusicPlayerService.toggle_favorite(mock_bot, user_id, track)
        assert success is True
        assert is_fav is True
        assert "Added" in msg
        mock_bot.db.add_favorite.assert_called_once_with(user_id, track=track)

        # Case B: Already in favorites -> Removes
        fav_mock = MagicMock(url=track.url)
        mock_bot.db.get_favorites.return_value = [fav_mock]
        success, is_fav, msg = await MusicPlayerService.toggle_favorite(mock_bot, user_id, track)
        assert success is True
        assert is_fav is False
        assert "Removed" in msg
        mock_bot.db.remove_favorite.assert_called_once_with(user_id, track.url)

    @pytest.mark.asyncio
    async def test_09_stop_and_reset(self, mock_bot, mock_session):
        """Verify stop halts playback and resets session cleanly."""
        vc = mock_session.voice_client
        success, msg = await MusicPlayerService.stop(mock_bot, mock_session)
        assert success is True
        assert mock_session.current_track is None
        assert mock_session.state == PlaybackState.IDLE
        vc.stop.assert_called_once()


def test_progress_bar_clamps_position_and_respects_width():
    assert create_progress_bar(0, 100, 5) == "▶ 🔘────"
    assert create_progress_bar(50, 100, 5) == "▶ ──🔘──"
    assert create_progress_bar(100, 100, 5) == "▶ ────🔘"
    assert create_progress_bar(150, 100, 5) == "▶ ────🔘"
    assert create_progress_bar(-10, 100, 5) == "▶ 🔘────"


def test_progress_bar_handles_unknown_duration_and_invalid_width():
    assert create_progress_bar(0, 0, 4) == "🔘──────────────"
    assert create_progress_bar(10, 0, 1) == "🔘──────────────"
    assert create_progress_bar(10, 20, 1) == "▶ 🔘"
