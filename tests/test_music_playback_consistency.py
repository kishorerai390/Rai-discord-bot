import asyncio
from collections import deque
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from music_bot.database.models import QueuedTrack
from music_bot.services.player_service import MusicPlayerService
from music_bot.services.session_service import GuildMusicSession, LoopMode, PlaybackState


def make_track(title: str, url: str = "https://youtube.com/watch?v=mock", duration: int = 180) -> QueuedTrack:
    return QueuedTrack(
        title=title,
        url=url,
        stream_url="https://mock.stream/audio.mp3",
        duration=duration,
        artist="Mock Artist",
        thumbnail="https://mock/thumb.jpg",
        requester_id=12345,
        requester_name="TestUser",
    )


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    bot.loop = loop
    bot.db = AsyncMock()
    bot.db.delete_session = AsyncMock()
    bot.db.record_history = AsyncMock()
    bot.db.save_session = AsyncMock()
    return bot


@pytest.fixture
def mock_session():
    session = GuildMusicSession(guild_id=999)
    mock_vc = MagicMock()
    mock_vc.is_connected.return_value = True
    mock_vc.is_playing.return_value = True
    mock_vc.is_paused.return_value = False
    mock_vc.stop = MagicMock()
    mock_vc.pause = MagicMock()
    mock_vc.resume = MagicMock()
    mock_vc.disconnect = AsyncMock()
    session.voice_client = mock_vc

    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()
    mock_msg = AsyncMock()
    session.text_channel = mock_channel
    session.now_playing_message = mock_msg
    return session


@pytest.mark.asyncio
class TestPlaybackConsistency:

    async def test_authoritative_pause_and_resume(self, mock_bot, mock_session):
        """Verify authoritative pause and resume state synchronization."""
        t1 = make_track("Song A")
        mock_session.current_track = t1
        mock_session.state = PlaybackState.PLAYING

        with patch.object(MusicPlayerService, "send_now_playing_panel", new_callable=AsyncMock) as mock_panel:
            # 1. Pause
            success, msg = await MusicPlayerService.pause(mock_session)
            assert success is True
            assert mock_session.state == PlaybackState.PAUSED
            assert mock_session.pause_time > 0
            mock_session.voice_client.pause.assert_called_once()
            mock_panel.assert_called_once()

            # 2. Cannot pause if already paused
            mock_session.voice_client.is_playing.return_value = False
            mock_session.voice_client.is_paused.return_value = True
            success2, msg2 = await MusicPlayerService.pause(mock_session)
            assert success2 is False
            assert "already paused" in msg2

            # 3. Resume
            mock_panel.reset_mock()
            success3, msg3 = await MusicPlayerService.resume(mock_bot, mock_session)
            assert success3 is True
            assert mock_session.state == PlaybackState.PLAYING
            assert mock_session.pause_time == 0.0
            mock_session.voice_client.resume.assert_called_once()
            mock_panel.assert_called_once()

    async def test_authoritative_stop(self, mock_bot, mock_session):
        """Verify authoritative stop clears queue, resets session, and deletes DB session."""
        t1 = make_track("Song A")
        t2 = make_track("Song B")
        mock_session.current_track = t1
        mock_session.queue = deque([t2])
        mock_session.state = PlaybackState.PLAYING
        vc = mock_session.voice_client

        success, msg = await MusicPlayerService.stop(mock_bot, mock_session)
        assert success is True
        assert len(mock_session.queue) == 0
        assert mock_session.current_track is None
        assert mock_session.state == PlaybackState.IDLE
        assert mock_bot.db.delete_session.called
        vc.stop.assert_called_once()

    async def test_authoritative_previous(self, mock_bot, mock_session):
        """Verify previous pops from history and unshifts current track to queue."""
        t_prev = make_track("Previous Song")
        t_curr = make_track("Current Song")

        mock_session.history = [t_prev]
        mock_session.current_track = t_curr

        with patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:
            mock_start.return_value = True
            success, msg, track = await MusicPlayerService.previous(mock_bot, mock_session)

            assert success is True
            assert track == t_prev
            assert len(mock_session.history) == 0
            assert mock_session.queue[0] == t_curr
            mock_start.assert_called_once_with(mock_bot, mock_session, t_prev)

    async def test_twenty_four_seven_channel_mode_on_stop(self, mock_bot, mock_session):
        """24/7 mode preserves voice connection on stop instead of disconnecting."""
        mock_session.twenty_four_seven = True
        mock_session.current_track = make_track("Active Song")
        mock_session.state = PlaybackState.PLAYING
        vc = mock_session.voice_client

        success, msg = await MusicPlayerService.stop(mock_bot, mock_session)
        assert success is True
        vc.stop.assert_called_once()
        vc.disconnect.assert_not_called()
        assert mock_session.voice_client is not None

    async def test_spotify_metadata_integration(self):
        """Verify Spotify metadata resolution parses title, artist, and album thumbnail."""
        from music_bot.services.resolver_service import AudioResolver
        fake_oembed = {
            "title": "Blinding Lights",
            "thumbnail_url": "https://spotify.cdn/blinding_lights.jpg",
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = (
                b'{"title": "Blinding Lights", "thumbnail_url": "https://spotify.cdn/blinding_lights.jpg"}'
            )
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            res = await AudioResolver.resolve_spotify_metadata("https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b")
            assert res is not None
            assert res["title"] == "Blinding Lights"
            assert "Blinding Lights" in res["search_query"]
            assert res["thumbnail"] == "https://spotify.cdn/blinding_lights.jpg"

    async def test_eq_filter_application(self, mock_bot, mock_session):
        """Verify EQ filter preset updates preset display name and audio filter chain."""
        with patch.object(MusicPlayerService, "send_now_playing_panel", new_callable=AsyncMock):
            success = await MusicPlayerService.apply_filter_or_eq(
                mock_bot, mock_session, "bassboost", "Bass Boost"
            )
            assert success is True
            assert mock_session.eq_preset == "Bass Boost"
            assert "equalizer=f=60" in mock_session.audio_filter
