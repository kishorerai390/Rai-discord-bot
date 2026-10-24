"""
Regression Test Suite for:
1. EQ Preset switching without stopping, skipping, or advancing the queue.
2. Individual-Song Auto-DJ mode with strict manual queue priority.
3. Traditional Prefix Music Commands (!play, !p, !pause, !resume, !skip, !stop, !queue, !np, !volume, !seek, !loop, !shuffle, !previous).
"""

import asyncio
from collections import deque
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from music_bot.database.models import QueuedTrack
from music_bot.services.player_service import AudioEqualizerView, MusicPlayerService
from music_bot.services.session_service import GuildMusicSession, LoopMode, PlaybackState, SessionManager
from music_bot.services.dj_service import NekoDJService


def make_track(title: str, url: str, duration: int = 200, artist: str = "Test Artist", requester_id: int = 12345) -> QueuedTrack:
    return QueuedTrack(
        title=title,
        url=url,
        duration=duration,
        artist=artist,
        requester_id=requester_id,
        requester_name="TestRequester",
        stream_url=f"http://audio.stream/{title.replace(' ', '_')}.opus",
        thumbnail="https://thumb.url/image.jpg",
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
    bot.get_guild_prefix = AsyncMock(return_value="!")
    return bot


@pytest.fixture
def mock_session():
    session = GuildMusicSession(guild_id=99901)
    session.voice_client = MagicMock()
    session.voice_client.is_connected = MagicMock(return_value=True)
    session.voice_client.is_playing = MagicMock(return_value=True)
    session.voice_client.is_paused = MagicMock(return_value=False)
    session.text_channel = MagicMock()
    session.text_channel.send = AsyncMock()
    return session


@pytest.mark.asyncio
class TestEQPresetBehavior:
    """Tests verifying that EQ preset changes preserve current track, queue order, position, and pause state."""

    async def test_changing_flat_to_bassboost_does_not_skip(self, mock_bot, mock_session):
        t1 = make_track("Song A", "http://yt/a")
        t2 = make_track("Song B", "http://yt/b")
        mock_session.current_track = t1
        mock_session.queue = deque([t2])
        mock_session.track_start_time = time.time() - 45  # 45s elapsed
        mock_session.state = PlaybackState.PLAYING

        with patch.object(MusicPlayerService, "resume_track_stream", new_callable=AsyncMock) as mock_resume:
            mock_resume.return_value = True
            success = await MusicPlayerService.apply_filter_or_eq(mock_bot, mock_session, "bassboost", "Bass Boost")

            assert success is True
            # Song must NOT be skipped
            assert mock_session.current_track == t1
            assert mock_session.current_track.title == "Song A"
            # Queue must NOT advance
            assert len(mock_session.queue) == 1
            assert mock_session.queue[0] == t2
            # EQ preset updated
            assert mock_session.eq_preset == "Bass Boost"
            assert "equalizer=f=60" in mock_session.audio_filter
            # resume_track_stream was called with position around 45s
            mock_resume.assert_called_once()
            called_pos = mock_resume.call_args[0][3]
            assert 44 <= called_pos <= 46

    async def test_changing_bassboost_to_flat_preserves_current_song(self, mock_bot, mock_session):
        t1 = make_track("Song A", "http://yt/a")
        mock_session.current_track = t1
        mock_session.eq_preset = "Bass Boost"
        mock_session.audio_filter = "-af equalizer=f=60:width_type=h:width=50:g=10"
        mock_session.track_start_time = time.time() - 30

        with patch.object(MusicPlayerService, "resume_track_stream", new_callable=AsyncMock) as mock_resume:
            mock_resume.return_value = True
            success = await MusicPlayerService.apply_filter_or_eq(mock_bot, mock_session, "reset", "Flat / Normal")

            assert success is True
            assert mock_session.current_track == t1
            assert mock_session.eq_preset == "Flat / Normal"
            assert mock_session.audio_filter == ""

    async def test_eq_change_preserves_queue_order(self, mock_bot, mock_session):
        t1 = make_track("Active Song", "http://yt/active")
        q1 = make_track("Next 1", "http://yt/q1")
        q2 = make_track("Next 2", "http://yt/q2")
        q3 = make_track("Next 3", "http://yt/q3")
        mock_session.current_track = t1
        mock_session.queue = deque([q1, q2, q3])

        with patch.object(MusicPlayerService, "resume_track_stream", new_callable=AsyncMock) as mock_resume:
            mock_resume.return_value = True
            await MusicPlayerService.apply_filter_or_eq(mock_bot, mock_session, "8d", "8D Audio")

            # Entire queue order must be preserved untouched
            assert list(mock_session.queue) == [q1, q2, q3]
            assert mock_session.current_track == t1

    async def test_eq_change_while_paused_does_not_resume(self, mock_bot, mock_session):
        t1 = make_track("Paused Song", "http://yt/paused")
        mock_session.current_track = t1
        mock_session.state = PlaybackState.PAUSED
        mock_session.pause_time = time.time() - 10
        mock_session.track_start_time = time.time() - 50
        mock_session.voice_client.is_playing = MagicMock(return_value=False)
        mock_session.voice_client.is_paused = MagicMock(return_value=True)

        with patch.object(MusicPlayerService, "resume_track_stream", new_callable=AsyncMock) as mock_resume:
            mock_resume.return_value = True
            await MusicPlayerService.apply_filter_or_eq(mock_bot, mock_session, "vaporwave", "Lo-Fi Relax")

            # Voice client pause must have been called to preserve paused state
            mock_session.voice_client.pause.assert_called()
            assert mock_session.state == PlaybackState.PAUSED

    async def test_eq_failure_rolls_back_and_does_not_stop_playback(self, mock_bot, mock_session):
        t1 = make_track("Active Song", "http://yt/active")
        mock_session.current_track = t1
        mock_session.eq_preset = "Flat"
        mock_session.audio_filter = ""
        mock_session.track_start_time = time.time() - 10

        call_count = 0

        async def fake_resume(bot, session, track, pos):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return False  # Failed to apply new EQ
            return True  # Fallback to old EQ succeeded

        with patch.object(MusicPlayerService, "resume_track_stream", side_effect=fake_resume):
            success = await MusicPlayerService.apply_filter_or_eq(mock_bot, mock_session, "bassboost", "Bass Boost")

            assert success is False
            # Rolled back to Flat
            assert mock_session.eq_preset == "Flat"
            assert mock_session.audio_filter == ""
            # Current song preserved
            assert mock_session.current_track == t1

    async def test_repeated_eq_changes_increment_generation_and_ignore_stale_callbacks(self, mock_bot, mock_session):
        t1 = make_track("Song Live", "http://yt/live")
        mock_session.current_track = t1
        mock_session.queue = deque([make_track("Upcoming", "http://yt/next")])
        initial_gen = mock_session.playback_generation

        with patch.object(MusicPlayerService, "resume_track_stream", new_callable=AsyncMock) as mock_resume:
            mock_resume.return_value = True
            await MusicPlayerService.apply_filter_or_eq(mock_bot, mock_session, "bassboost", "Bass Boost")
            await MusicPlayerService.apply_filter_or_eq(mock_bot, mock_session, "pop", "Pop")
            await MusicPlayerService.apply_filter_or_eq(mock_bot, mock_session, "rock", "Rock")

            assert mock_session.playback_generation > initial_gen + 2
            # Queue was never advanced
            assert len(mock_session.queue) == 1
            assert mock_session.queue[0].title == "Upcoming"

    async def test_multi_guild_eq_isolation(self, mock_bot):
        s1 = GuildMusicSession(guild_id=101)
        s2 = GuildMusicSession(guild_id=102)
        s1.current_track = make_track("Guild 1 Song", "http://yt/1")
        s2.current_track = make_track("Guild 2 Song", "http://yt/2")

        with patch.object(MusicPlayerService, "resume_track_stream", new_callable=AsyncMock) as mock_resume:
            mock_resume.return_value = True
            await MusicPlayerService.apply_filter_or_eq(mock_bot, s1, "bassboost", "Bass Boost")

            assert s1.eq_preset == "Bass Boost"
            assert "equalizer=f=60" in s1.audio_filter
            # Guild 2 remains untouched
            assert s2.eq_preset == "Flat"
            assert s2.audio_filter == ""


@pytest.mark.asyncio
class TestIndividualSongAutoDJ:
    """Tests verifying individual-song Auto-DJ queue behavior, priority, and skipping."""

    async def test_manual_queue_has_strict_priority_over_autodj(self, mock_bot, mock_session):
        user_track = make_track("Manual User Song", "http://yt/manual")
        mock_session.current_track = make_track("Current Playing", "http://yt/cur")
        mock_session.queue = deque([user_track])
        mock_session.dj_enabled = True

        with patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:
            mock_start.return_value = True
            # When track finishes, manual queue item must play first!
            await MusicPlayerService.handle_track_finished(mock_bot, mock_session)

            mock_start.assert_called_once_with(mock_bot, mock_session, user_track)
            assert len(mock_session.queue) == 0

    async def test_autodj_recommends_one_individual_song_when_queue_empty(self, mock_bot, mock_session):
        mock_session.current_track = make_track("Current Finished", "http://yt/cur")
        mock_session.queue = deque()
        mock_session.dj_enabled = True
        rec_track = make_track("Recommended Single", "http://yt/rec")

        mock_bot.db.get_dj_settings = AsyncMock(return_value=MagicMock(enabled=True))

        with patch("music_bot.services.dj_service.NekoDJService.get_recommendation", new_callable=AsyncMock) as mock_rec, \
             patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:
            mock_rec.return_value = (rec_track, "Artist similarity")
            mock_start.return_value = True

            await MusicPlayerService.handle_track_finished(mock_bot, mock_session)

            mock_rec.assert_called_once()
            # Plays only the ONE recommended track
            mock_start.assert_called_once_with(mock_bot, mock_session, rec_track)
            assert len(mock_session.queue) == 0

    async def test_manual_skip_with_autodj_picks_different_track(self, mock_bot, mock_session):
        skipped_track = make_track("Skip Me", "http://yt/skip")
        mock_session.current_track = skipped_track
        mock_session.queue = deque()
        mock_session.dj_enabled = True
        next_rec = make_track("Next Discovery", "http://yt/next_rec")

        mock_bot.db.get_dj_settings = AsyncMock(return_value=MagicMock(enabled=True))

        with patch("music_bot.services.dj_service.NekoDJService.get_recommendation", new_callable=AsyncMock) as mock_rec, \
             patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:
            mock_rec.return_value = (next_rec, "Trending vibe")
            mock_start.return_value = True

            # Manual skip cleanly invokes skip_current, which stops voice client, triggering handle_track_finished
            await MusicPlayerService.skip_current(mock_session)
            mock_session.voice_client.stop.assert_called_once()

            await MusicPlayerService.handle_track_finished(mock_bot, mock_session)

            # Skipped track is now in history
            assert skipped_track in mock_session.history
            # Next individual song started
            mock_start.assert_called_once_with(mock_bot, mock_session, next_rec)
            # Auto-DJ is NOT disabled
            assert mock_session.dj_enabled is True

    async def test_autodj_off_becomes_idle_when_queue_empty(self, mock_bot, mock_session):
        mock_session.current_track = make_track("Current Finished", "http://yt/cur")
        mock_session.queue = deque()
        mock_session.dj_enabled = False
        mock_session.autoplay = False
        mock_bot.db.get_dj_settings = AsyncMock(return_value=MagicMock(enabled=False))

        with patch("music_bot.services.dj_service.NekoDJService.get_recommendation", new_callable=AsyncMock) as mock_rec, \
             patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:

            await MusicPlayerService.handle_track_finished(mock_bot, mock_session)

            mock_rec.assert_not_called()
            mock_start.assert_not_called()


@pytest.mark.asyncio
class TestPrefixMusicCommands:
    """Tests verifying prefix commands (!play, !p, !pause, !resume, !skip, !stop, !queue, !np, !volume, !seek, !loop, !shuffle, !previous)."""

    async def test_pfx_play_queues_and_replies_compact_embed(self, mock_bot, mock_session):
        from music_bot.commands.music_cog import MusicCog

        cog = MusicCog(mock_bot)
        ctx = MagicMock()
        ctx.guild = MagicMock(id=99901)
        ctx.author = MagicMock()
        ctx.author.id = 777
        ctx.author.voice = MagicMock()
        ctx.author.voice.channel = MagicMock(id=111, name="Voice 1")
        ctx.reply = AsyncMock()

        status_msg = MagicMock()
        status_msg.edit = AsyncMock()
        ctx.reply.return_value = status_msg

        track = make_track("Kalyani", "http://yt/kalyani", duration=320, artist="Maestro", requester_id=777)

        # Session currently playing
        mock_session.current_track = make_track("Existing Track", "http://yt/exist")
        mock_session.state = PlaybackState.PLAYING
        mock_session.queue = deque()

        with patch.object(cog.session_manager, "get_session", new_callable=AsyncMock) as mock_get_s, \
             patch("music_bot.services.voice_service.VoiceManager.join_voice_channel", new_callable=AsyncMock) as mock_join, \
             patch("music_bot.services.resolver_service.AudioResolver.search", new_callable=AsyncMock, return_value=[]), \
             patch("music_bot.services.resolver_service.AudioResolver.resolve_track", new_callable=AsyncMock) as mock_resolve:
            mock_get_s.return_value = mock_session
            mock_join.return_value = mock_session.voice_client
            mock_resolve.return_value = track

            await cog.pfx_play.callback(cog, ctx, query="kalyani")

            assert len(mock_session.queue) == 1
            assert mock_session.queue[0] == track

            status_msg.edit.assert_called_once()
            called_kwargs = status_msg.edit.call_args[1]
            embed = called_kwargs.get("embed")
            assert embed is not None
            assert "Added to Queue" in embed.title
            assert "Kalyani" in embed.description
            assert "Maestro" in embed.description
            assert "Position:" in embed.description
            assert "#1" in embed.description

    async def test_pfx_play_empty_query_replies_usage(self, mock_bot):
        from music_bot.commands.music_cog import MusicCog

        cog = MusicCog(mock_bot)
        ctx = MagicMock()
        ctx.guild = MagicMock(id=99901)
        ctx.author = MagicMock()
        ctx.reply = AsyncMock()

        await cog.pfx_play.callback(cog, ctx, query="")
        ctx.reply.assert_called_once()
        assert "Usage:" in ctx.reply.call_args[0][0]

    async def test_pfx_play_without_voice_replies_error(self, mock_bot):
        from music_bot.commands.music_cog import MusicCog

        cog = MusicCog(mock_bot)
        ctx = MagicMock()
        ctx.guild = MagicMock(id=99901)
        ctx.author = MagicMock()
        ctx.author.voice = None
        ctx.reply = AsyncMock()

        await cog.pfx_play.callback(cog, ctx, query="kalyani")
        ctx.reply.assert_called_once()
        assert "Join a voice channel first" in ctx.reply.call_args[0][0]

    async def test_pfx_play_reports_resolution_timeout(self, mock_bot, mock_session):
        from music_bot.commands.music_cog import MusicCog

        cog = MusicCog(mock_bot)
        ctx = MagicMock()
        ctx.guild = MagicMock(id=99901)
        ctx.author = MagicMock()
        ctx.author.id = 777
        ctx.author.voice = MagicMock()
        ctx.author.voice.channel = MagicMock(id=111, name="Voice 1")
        ctx.reply = AsyncMock()
        status_msg = MagicMock()
        status_msg.edit = AsyncMock()
        ctx.reply.return_value = status_msg

        with patch.object(cog.session_manager, "get_session", new_callable=AsyncMock) as mock_get_s, \
             patch("music_bot.services.voice_service.VoiceManager.join_voice_channel", new_callable=AsyncMock) as mock_join, \
             patch("music_bot.services.resolver_service.AudioResolver.resolve_track", new_callable=AsyncMock) as mock_resolve:
            mock_get_s.return_value = mock_session
            mock_join.return_value = mock_session.voice_client
            mock_resolve.side_effect = asyncio.TimeoutError

            await cog.pfx_play.callback(cog, ctx, query="rasagula anirudh")

        assert "timed out" in status_msg.edit.call_args.kwargs["content"].lower()

    async def test_pfx_seek_and_previous(self, mock_bot, mock_session):
        from music_bot.commands.music_cog import MusicCog

        cog = MusicCog(mock_bot)
        ctx = MagicMock()
        ctx.guild = MagicMock(id=99901)
        ctx.reply = AsyncMock()

        mock_session.current_track = make_track("Current", "http://yt/c", duration=300)
        mock_session.state = PlaybackState.PLAYING
        mock_session.history = [make_track("Old Song", "http://yt/old")]

        with patch.object(cog.session_manager, "get_session", new_callable=AsyncMock) as mock_get_s, \
             patch.object(MusicPlayerService, "seek", new_callable=AsyncMock) as mock_seek, \
             patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:
            mock_get_s.return_value = mock_session
            mock_seek.return_value = True
            mock_start.return_value = True

            # Test !seek 120
            await cog.pfx_seek.callback(cog, ctx, seconds=120)
            mock_seek.assert_called_once_with(mock_bot, mock_session, 120)
            assert "Seeked to" in ctx.reply.call_args[0][0]

            # Test !previous
            await cog.pfx_previous.callback(cog, ctx)
            mock_start.assert_called_once()
            assert "Old Song" in ctx.reply.call_args[0][0]
