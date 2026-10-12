import asyncio
from collections import deque
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from music_bot.database.models import QueuedTrack
from music_bot.services.player_service import MusicPlayerService, NowPlayingControlView
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
    bot.db.get_dj_settings = AsyncMock(return_value=MagicMock(enabled=False))
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
    session.voice_client = mock_vc

    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()
    mock_msg = AsyncMock()
    session.text_channel = mock_channel
    session.now_playing_message = mock_msg
    return session


@pytest.mark.asyncio
class TestSkipAndAntiRepeat:

    async def test_skip_with_two_queued_tracks(self, mock_bot, mock_session):
        """1. Skip with two queued tracks: advances queue exactly once and plays next."""
        t1 = make_track("Song 1", "https://yt/1")
        t2 = make_track("Song 2", "https://yt/2")
        t3 = make_track("Song 3", "https://yt/3")

        mock_session.current_track = t1
        mock_session.queue = deque([t2, t3])

        with patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:
            mock_start.return_value = True

            success, msg, next_t = await MusicPlayerService.skip(mock_bot, mock_session)

            assert success is True
            assert next_t == t2
            assert len(mock_session.queue) == 1
            assert mock_session.queue[0] == t3
            assert t1 in mock_session.history
            assert t1.url in mock_session.recent_skipped_urls
            mock_session.voice_client.stop.assert_called_once()
            mock_start.assert_called_once_with(mock_bot, mock_session, t2)

    async def test_skip_with_empty_queue(self, mock_bot, mock_session):
        """2. Skip with empty queue: transitions to IDLE and edits Now Playing embed."""
        t1 = make_track("Only Song", "https://yt/only")
        mock_session.current_track = t1
        mock_session.queue = deque()

        success, msg, next_t = await MusicPlayerService.skip(mock_bot, mock_session)

        assert success is True
        assert next_t is None
        assert mock_session.state == PlaybackState.IDLE
        assert mock_session.current_track is None
        assert mock_bot.db.delete_session.called
        assert mock_session.now_playing_message.edit.called

    async def test_rapid_double_click_skip(self, mock_bot, mock_session):
        """3. Rapid double-click on Skip: debounces and skips only one track."""
        t1 = make_track("Song 1", "https://yt/1")
        t2 = make_track("Song 2", "https://yt/2")
        t3 = make_track("Song 3", "https://yt/3")

        mock_session.current_track = t1
        mock_session.queue = deque([t2, t3])

        with patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:
            mock_start.return_value = True

            # Simulate concurrent second click while _is_skipping is True
            mock_session._is_skipping = True
            success2, msg2, next_t2 = await MusicPlayerService.skip(mock_bot, mock_session)

            assert success2 is False
            assert "already processing" in msg2
            assert len(mock_session.queue) == 2
            mock_start.assert_not_called()

            # Reset flag and perform genuine skip
            mock_session._is_skipping = False
            success1, msg1, next_t1 = await MusicPlayerService.skip(mock_bot, mock_session)
            assert success1 is True
            assert next_t1 == t2
            assert len(mock_session.queue) == 1

    async def test_natural_track_completion_loop_off_vs_track_vs_queue(self, mock_bot, mock_session):
        """4 & 5. Loop Off vs Loop Track vs Loop Queue on track completion."""
        t1 = make_track("Track A", "https://yt/a")
        t2 = make_track("Track B", "https://yt/b")

        # CASE A: Loop Off
        mock_session.loop_mode = LoopMode.OFF
        mock_session.current_track = t1
        mock_session.queue = deque([t2])
        with patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:
            await MusicPlayerService.handle_track_finished(mock_bot, mock_session)
            assert t1 in mock_session.history
            assert t1 not in mock_session.queue
            mock_start.assert_called_once_with(mock_bot, mock_session, t2)

        # CASE B: Loop Track
        mock_session.loop_mode = LoopMode.TRACK
        mock_session.current_track = t1
        mock_session.queue = deque([t2])
        with patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:
            await MusicPlayerService.handle_track_finished(mock_bot, mock_session)
            # Replays t1
            mock_start.assert_called_once_with(mock_bot, mock_session, t1)

        # CASE C: Loop Queue
        mock_session.loop_mode = LoopMode.QUEUE
        mock_session.current_track = t1
        mock_session.queue = deque([t2])
        with patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:
            await MusicPlayerService.handle_track_finished(mock_bot, mock_session)
            # t1 appended to queue, t2 popped and played
            assert t1 in mock_session.queue
            mock_start.assert_called_once_with(mock_bot, mock_session, t2)

    async def test_autodj_after_manual_queue_empty(self, mock_bot, mock_session):
        """6. Auto-DJ activates only when manual queue is empty and avoids repeating skipped song."""
        t1 = make_track("Party Song", "https://yt/party")
        rec_track = make_track("New Discovery", "https://yt/discovery")

        mock_session.current_track = t1
        mock_session.queue = deque()
        mock_session.dj_enabled = True

        with patch("music_bot.services.dj_service.NekoDJService.get_recommendation", new_callable=AsyncMock) as mock_rec, \
             patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:
            mock_rec.return_value = (rec_track, "Vibe match")
            mock_start.return_value = True

            success, msg, next_t = await MusicPlayerService.skip(mock_bot, mock_session)

            assert success is True
            assert next_t == rec_track
            assert t1.url in mock_session.recent_skipped_urls
            mock_start.assert_called_once_with(mock_bot, mock_session, rec_track)

    async def test_paused_playback_followed_by_skip(self, mock_bot, mock_session):
        """8. Paused playback followed by Skip cleanly advances and resets paused state."""
        t1 = make_track("Paused Song", "https://yt/paused")
        t2 = make_track("Next Song", "https://yt/next")

        mock_session.current_track = t1
        mock_session.queue = deque([t2])
        mock_session.voice_client.is_playing.return_value = False
        mock_session.voice_client.is_paused.return_value = True
        mock_session.state = PlaybackState.PAUSED
        mock_session.pause_time = 100.0

        with patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:
            mock_start.return_value = True

            success, msg, next_t = await MusicPlayerService.skip(mock_bot, mock_session)

            assert success is True
            assert next_t == t2
            mock_session.voice_client.stop.assert_called_once()
            mock_start.assert_called_once_with(mock_bot, mock_session, t2)

    async def test_skip_button_interaction_defer_and_authorization(self, mock_bot, mock_session):
        """9. Skip button interaction handles permissions, defers immediately, and calls skip."""
        view = NowPlayingControlView(mock_session)

        mock_interaction = AsyncMock()
        mock_interaction.response.is_done = MagicMock(return_value=False)
        mock_interaction.guild.id = mock_session.guild_id
        mock_interaction.client = mock_bot

        skip_btn = [c for c in view.children if c.custom_id == "music_btn_skip"][0]

        # Case A: User in different VC
        import discord
        mock_user = MagicMock(spec=discord.Member)
        mock_user.voice = MagicMock()
        mock_user.voice.channel = MagicMock()
        mock_user.voice.channel.id = 11111  # different from bot
        mock_interaction.user = mock_user
        mock_session.voice_client.channel = MagicMock()
        mock_session.voice_client.channel.id = 22222
        mock_session.voice_client.channel.mention = "<#22222>"

        await skip_btn.callback(mock_interaction)
        mock_interaction.response.defer.assert_called_once()
        mock_interaction.followup.send.assert_called_once()
        assert "same voice channel" in mock_interaction.followup.send.call_args[0][0]

        # Case B: User in same VC
        mock_user.voice.channel.id = mock_session.voice_client.channel.id
        mock_interaction.followup.send.reset_mock()
        with patch.object(MusicPlayerService, "skip", new_callable=AsyncMock) as mock_skip:
            mock_skip.return_value = (True, "⏭ Skipped **Song**.", None)
            await skip_btn.callback(mock_interaction)
            mock_skip.assert_called_once_with(mock_bot, mock_session)
            mock_interaction.followup.send.assert_called_once_with("⏭ Skipped **Song**.", ephemeral=True)

    async def test_start_playback_with_valid_frames(self, mock_bot, mock_session):
        """10. Start playback: validates first frame, wraps in ValidatedAudioSource, starts playing."""
        t1 = make_track("Good Track")
        mock_session.voice_client.is_playing.return_value = False
        mock_session.voice_client.is_paused.return_value = False
        mock_session.voice_client.guild.me.voice.mute = False
        mock_session.voice_client.guild.me.voice.self_mute = False

        fake_pcm = b"\x01\x02\x03\x04" * 960  # 3840 bytes of PCM
        mock_transformer = MagicMock()
        mock_transformer.read.return_value = fake_pcm

        with patch("music_bot.services.player_service.discord.FFmpegPCMAudio") as mock_ffmpeg, \
             patch("music_bot.services.player_service.discord.PCMVolumeTransformer", return_value=mock_transformer):
            success = await MusicPlayerService.start_playback(mock_bot, mock_session, t1)

            assert success is True
            assert mock_session.state == PlaybackState.PLAYING
            assert mock_session.current_track == t1
            mock_session.voice_client.play.assert_called_once()
            played_source = mock_session.voice_client.play.call_args[0][0]
            # Verify source produces the buffered first frame
            assert played_source.read() == fake_pcm

    async def test_start_playback_aborts_on_empty_audio_stream(self, mock_bot, mock_session):
        """11. Start playback aborts and skips if audio source outputs 0 bytes (expired or dead URL)."""
        t1 = make_track("Dead Track")
        mock_session.voice_client.is_playing.return_value = False
        mock_session.voice_client.is_paused.return_value = False

        mock_transformer = MagicMock()
        mock_transformer.read.return_value = b""  # Empty audio stream

        with patch("music_bot.services.player_service.discord.FFmpegPCMAudio"), \
             patch("music_bot.services.player_service.discord.PCMVolumeTransformer", return_value=mock_transformer), \
             patch("music_bot.services.resolver_service.AudioResolver.resolve_track", new_callable=AsyncMock, return_value=None), \
             patch.object(MusicPlayerService, "handle_track_finished", new_callable=AsyncMock) as mock_finished:

            success = await MusicPlayerService.start_playback(mock_bot, mock_session, t1)

            assert success is False
            assert mock_session.state == PlaybackState.ERROR
            mock_session.voice_client.play.assert_not_called()
            mock_finished.assert_called_once_with(mock_bot, mock_session)

    async def test_server_mute_reported_in_now_playing_embed(self, mock_session):
        """12. Server-muted condition is clearly displayed in Now Playing status."""
        t1 = make_track("Muted Track")
        mock_session.current_track = t1
        mock_session.state = PlaybackState.PLAYING
        mock_session.voice_client.is_playing.return_value = True

        # Bot is server-muted
        mock_session.voice_client.guild.me.voice.mute = True

        embed = MusicPlayerService.build_now_playing_embed(mock_session)
        assert "Server Muted" in embed.description
        assert "🟢 Playing (⚠️ Server Muted)" in embed.description

    async def test_now_playing_embed_does_not_display_fake_playing(self, mock_session):
        """13. Embed does not show 'Playing' if voice_client is not actively playing audio."""
        t1 = make_track("Silent Track")
        mock_session.current_track = t1
        mock_session.state = PlaybackState.IDLE
        mock_session.voice_client.is_playing.return_value = False

        embed = MusicPlayerService.build_now_playing_embed(mock_session)
        assert "🟢 Playing" not in embed.description
        assert "⏹️ Idle" in embed.description

    async def test_validated_audio_source_volume_pass_through(self, mock_session):
        """14. ValidatedAudioSource passes through volume changes to underlying volume transformer."""
        from music_bot.services.player_service import ValidatedAudioSource, VolumeAdjustView

        mock_inner = MagicMock()
        mock_inner.volume = 0.8
        wrapped = ValidatedAudioSource(mock_inner, b"test_frame")

        assert wrapped.volume == 0.8
        wrapped.volume = 0.5
        assert mock_inner.volume == 0.5

        # Test VolumeAdjustView._set_vol
        mock_session.voice_client.source = wrapped
        view = VolumeAdjustView(mock_session)
        mock_interaction = AsyncMock()
        mock_interaction.response.is_done.return_value = False
        with patch.object(MusicPlayerService, "send_now_playing_panel", new_callable=AsyncMock):
            await view._set_vol(mock_interaction, 50)

        assert mock_session.volume == 50
        assert mock_inner.volume == 0.5
        mock_interaction.followup.send.assert_called_once_with("🔊 Volume set to `50%`.", ephemeral=True)


