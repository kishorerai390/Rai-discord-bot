"""
Comprehensive regression test suite for MusicMaid YouTube playback resilience,
access restriction handling, cookie validation, cooldown enforcement, and multi-provider fallbacks.

Tests all 12 specific requirements in Section 5 of the bug fix task:
1. Successful YouTube extraction.
2. YouTube access restriction handling.
3. Missing or invalid cookie configuration.
4. Cooldown activation, expiry, and suppression of repeated attempts.
5. Fallback from failed YouTube resolution to Audius.
6. Fallback from failed YouTube resolution to Jamendo.
7. Direct audio URL playback with SSRF validation.
8. Invalid or mismatched video IDs rejection.
9. Wrong-song selection prevention.
10. Duplicate song-selection and duplicate interaction prevention.
11. Failure of all available sources with an accurate final error.
12. Ensuring no secrets appear in logs or diagnostics.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest

from music_bot.database.models import QueuedTrack
from music_bot.services import youtube_health_monitor
from music_bot.services.resolver_service import (
    AudioResolver,
    _validate_cookies_content,
    get_active_cookie_file,
    get_cookie_diagnostics,
)
from music_bot.commands.music_cog import TrackSelectView


@pytest.fixture(autouse=True)
def reset_resolver_state():
    AudioResolver.clear_caches()
    youtube_health_monitor.reset_cooldown()
    yield
    AudioResolver.clear_caches()
    youtube_health_monitor.reset_cooldown()


# ---------------------------------------------------------------------------
# 1. Successful YouTube Extraction
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_successful_youtube_extraction():
    """Verify standard YouTube search and public stream extraction works cleanly."""
    candidate = {
        "id": "valid123456",
        "title": "Shape of You - Official Audio",
        "url": "https://www.youtube.com/watch?v=valid123456",
        "duration": 235,
        "artist": "Ed Sheeran",
        "uploader": "Ed Sheeran",
        "channel_is_verified": True,
    }
    extracted_data = {
        "id": "valid123456",
        "title": "Shape of You - Official Audio",
        "webpage_url": "https://www.youtube.com/watch?v=valid123456",
        "url": "https://audio.googlevideo.com/videoplayback?expire=9999",
        "duration": 235,
        "uploader": "Ed Sheeran",
    }
    with patch.object(AudioResolver, "search", new_callable=AsyncMock, return_value=[candidate]), \
         patch("music_bot.services.resolver_service._run_ytdlp", new_callable=AsyncMock, return_value=extracted_data):
        track = await AudioResolver.resolve_track("Shape of You", 123, "User")
        assert track is not None
        assert track.title == "Shape of You - Official Audio"
        assert "googlevideo.com" in track.stream_url


# ---------------------------------------------------------------------------
# 2. YouTube Access Restriction Handling
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_youtube_access_restriction_handling():
    """Verify that YouTube 403 / Sign in to confirm you're not a bot triggers ACCESS_RESTRICTION and records failure."""
    with patch.object(AudioResolver, "search", new_callable=AsyncMock, return_value=[{"url": "https://www.youtube.com/watch?v=fail123"}]), \
         patch("music_bot.services.resolver_service._run_ytdlp", side_effect=RuntimeError("HTTP Error 403: Forbidden - Sign in to confirm you're not a bot")), \
         patch("music_bot.services.alternative_providers.AudiusProviderService.search", new_callable=AsyncMock, return_value=[]), \
         patch("music_bot.services.alternative_providers.JamendoProviderService.search", new_callable=AsyncMock, return_value=[]):
        track = await AudioResolver.resolve_track("test access restriction", 123, "User")
        assert track is None
        err = AudioResolver.last_resolver_error or ""
        assert "[ACCESS_RESTRICTION]" in err
        cd_status = youtube_health_monitor.cooldown_status()
        assert cd_status["cooldown_active"] is True
        assert cd_status["last_failure"] == "access_denied"


# ---------------------------------------------------------------------------
# 3. Missing or Invalid Cookie Configuration
# ---------------------------------------------------------------------------
def test_missing_and_invalid_cookie_configuration(tmp_path):
    """Verify missing cookies return None safely, and expired cookies are suppressed from extraction."""
    # Empty / non-existent
    with patch("music_bot.services.resolver_service.WRITABLE_COOKIE_PATH", tmp_path / "nonexistent.txt"):
        assert get_active_cookie_file(require_valid=True) is None

    # Expired session cookies
    expired_file = tmp_path / "expired_cookie.txt"
    expired_file.write_text(
        "# Netscape HTTP Cookie File\n"
        f".youtube.com\tTRUE\t/\tTRUE\t{int(time.time() - 3600)}\tLOGIN_INFO\tEXPIRED_SESSION_TOKEN\n",
        encoding="utf-8",
    )
    with patch("music_bot.services.resolver_service.WRITABLE_COOKIE_PATH", expired_file):
        # require_valid=True MUST return None so expired cookies aren't passed to yt-dlp
        assert get_active_cookie_file(require_valid=True) is None
        # require_valid=False allows diagnostic tools to inspect metadata
        assert get_active_cookie_file(require_valid=False) == str(expired_file)


# ---------------------------------------------------------------------------
# 4. Cooldown Activation, Expiry, and Repeated Attempt Suppression
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cooldown_activation_expiry_and_suppression():
    """Verify cooldown stops repeated YouTube calls and proceeds cleanly."""
    youtube_health_monitor.record_failure("HTTP Error 403: Forbidden - Bot detected")
    status = youtube_health_monitor.cooldown_status()
    assert status["cooldown_active"] is True
    assert status["cooldown_remaining_seconds"] > 0

    # Under cooldown, YouTube should not be queried at all
    with patch.object(AudioResolver, "search", new_callable=AsyncMock) as mock_yt_search, \
         patch("music_bot.services.alternative_providers.AudiusProviderService.search", new_callable=AsyncMock, return_value=[]), \
         patch("music_bot.services.alternative_providers.JamendoProviderService.search", new_callable=AsyncMock, return_value=[]):
        track = await AudioResolver.resolve_track("cool song", 123, "User")
        assert track is None
        assert not mock_yt_search.called
        assert "cooldown active" in (AudioResolver.last_resolver_error or "")

    # Expiry
    youtube_health_monitor.reset_cooldown()
    assert youtube_health_monitor.cooldown_status()["cooldown_active"] is False


# ---------------------------------------------------------------------------
# 5. Fallback from Failed YouTube Resolution to Audius
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fallback_youtube_to_audius():
    """When YouTube is restricted, resolver falls back to Audius."""
    youtube_health_monitor.record_failure("403 Forbidden")
    audius_item = {
        "id": "aud_1",
        "title": "Summer Breeze - Official Audio",
        "artist": "Summer Band",
        "uploader": "Summer Band",
        "channel_is_verified": True,
        "url": "https://audius.co/artist/summer-breeze",
        "stream_url": "https://creatornode.audius.co/tracks/stream/123",
        "duration": 180,
        "thumbnail": "https://audius.co/thumb.jpg",
        "provider": "audius",
    }
    with patch("music_bot.services.alternative_providers.AudiusProviderService.search", new_callable=AsyncMock, return_value=[audius_item]):
        track = await AudioResolver.resolve_track("Summer Breeze", 123, "User")
        assert track is not None
        assert track.title == "Summer Breeze - Official Audio"
        assert track.stream_url == "https://creatornode.audius.co/tracks/stream/123"
        assert getattr(track, "provider", "") == "audius"


# ---------------------------------------------------------------------------
# 6. Fallback from Failed YouTube Resolution to Jamendo
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fallback_youtube_to_jamendo():
    """When YouTube fails and Audius has no match, resolver falls back to Jamendo."""
    youtube_health_monitor.record_failure("403 Forbidden")
    jamendo_item = {
        "id": "jam_1",
        "title": "Chill Morning - Official Release",
        "artist": "Chill Artist",
        "uploader": "Chill Artist",
        "channel_is_verified": True,
        "url": "https://www.jamendo.com/track/456",
        "stream_url": "https://prod-1.storage.jamendo.com/download/track/456/mp32/",
        "duration": 210,
        "thumbnail": "https://usercontent.jamendo.com/thumb.jpg",
        "provider": "jamendo",
    }
    with patch("music_bot.services.alternative_providers.AudiusProviderService.search", new_callable=AsyncMock, return_value=[]), \
         patch("music_bot.services.alternative_providers.JamendoProviderService.search", new_callable=AsyncMock, return_value=[jamendo_item]):
        track = await AudioResolver.resolve_track("Chill Morning", 123, "User")
        assert track is not None
        assert track.title == "Chill Morning - Official Release"
        assert "jamendo.com" in track.stream_url
        assert getattr(track, "provider", "") == "jamendo"


# ---------------------------------------------------------------------------
# 7. Direct Audio URL Playback with SSRF Validation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_direct_audio_url_playback_and_ssrf():
    """Verify safe direct URL playback and blocked SSRF targets."""
    # SSRF blocked target
    track_unsafe = await AudioResolver.resolve_track("http://127.0.0.1:8080/audio.mp3", 123, "User")
    assert track_unsafe is None
    assert "[SECURITY_VIOLATION]" in (AudioResolver.last_resolver_error or "")

    # Valid external direct URL
    direct_data = {
        "id": "direct1",
        "title": "Podcast Episode 1",
        "url": "https://example.com/audio/podcast.mp3",
        "duration": 1200,
        "uploader": "Podcaster",
    }
    with patch("music_bot.services.resolver_service._run_ytdlp", new_callable=AsyncMock, return_value=direct_data):
        track_safe = await AudioResolver.resolve_track("https://example.com/audio/podcast.mp3", 123, "User")
        assert track_safe is not None
        assert track_safe.title == "Podcast Episode 1"
        assert getattr(track_safe, "provider", "") == "direct_audio"


# ---------------------------------------------------------------------------
# 8. Invalid or Mismatched Video IDs Rejection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mismatched_video_id_rejection():
    """Ensure that if yt-dlp returns a different video ID than expected, it is rejected."""
    candidate = {
        "id": "expected123",
        "title": "Target Song",
        "url": "https://www.youtube.com/watch?v=expected123",
        "duration": 200,
        "artist": "Artist",
        "uploader": "Artist",
        "channel_is_verified": True,
    }
    mismatched_data = {
        "id": "different999",
        "title": "Completely Different Video",
        "webpage_url": "https://www.youtube.com/watch?v=different999",
        "url": "https://audio.example/stream",
        "duration": 200,
        "uploader": "Artist",
    }
    with patch.object(AudioResolver, "search", new_callable=AsyncMock, return_value=[candidate]), \
         patch("music_bot.services.resolver_service._run_ytdlp", new_callable=AsyncMock, return_value=mismatched_data), \
         patch("music_bot.services.alternative_providers.AudiusProviderService.search", new_callable=AsyncMock, return_value=[]), \
         patch("music_bot.services.alternative_providers.JamendoProviderService.search", new_callable=AsyncMock, return_value=[]):
        track = await AudioResolver.resolve_track("Target Song", 123, "User")
        assert track is None


# ---------------------------------------------------------------------------
# 9. Wrong-Song Selection Prevention
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_wrong_song_selection_prevention():
    """Verify that unverified DJ remixes or covers are rejected when original is sought."""
    remix_candidate = {
        "id": "remix123",
        "title": "Kalyani DJ Remix Bass Boosted",
        "uploader": "Random DJ Channel",
        "duration": 180,
    }
    with patch.object(AudioResolver, "search", new_callable=AsyncMock, return_value=[]), \
         patch("music_bot.services.resolver_service.yt_dlp.YoutubeDL") as mock_ydl_cls, \
         patch("music_bot.services.alternative_providers.AudiusProviderService.search", new_callable=AsyncMock, return_value=[]), \
         patch("music_bot.services.alternative_providers.JamendoProviderService.search", new_callable=AsyncMock, return_value=[]):
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {"entries": [remix_candidate]}
        mock_ydl_cls.return_value = mock_ydl
        track = await AudioResolver.resolve_track("Kalyani", 123, "User")
        assert track is None
        assert "NO_ORIGINAL_MATCH" in (AudioResolver.last_resolver_error or "")


# ---------------------------------------------------------------------------
# 10. Duplicate Song Selection and Duplicate Interaction Prevention
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_interaction_prevention_in_view():
    """Verify TrackSelectView ignores second interaction and disables components."""
    candidates = [
        {"title": "Song A", "artist": "Artist A", "duration": 180},
        {"title": "Song B", "artist": "Artist B", "duration": 200},
    ]
    callback_calls = []

    async def mock_on_select(interaction, idx):
        callback_calls.append(idx)

    view = TrackSelectView(candidates=candidates, user_id=12345, on_select_coro=mock_on_select)

    mock_interaction_1 = MagicMock()
    mock_interaction_1.user.id = 12345
    mock_interaction_1.data = {"values": ["0"]}
    mock_interaction_1.response.defer = AsyncMock()

    # First interaction executes callback
    await view.select_callback(mock_interaction_1)
    assert len(callback_calls) == 1
    assert callback_calls[0] == 0
    assert view._selected is True

    # Second interaction should immediately return without executing callback again
    mock_interaction_2 = MagicMock()
    mock_interaction_2.user.id = 12345
    mock_interaction_2.data = {"values": ["1"]}
    mock_interaction_2.response.defer = AsyncMock()

    await view.select_callback(mock_interaction_2)
    assert len(callback_calls) == 1  # Still 1, duplicate suppressed!


# ---------------------------------------------------------------------------
# 11. Failure of All Available Sources with Accurate Final Error
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_failure_of_all_sources_gives_accurate_diagnostic():
    """Verify when YouTube, Audius, and Jamendo all fail, accurate error and ref ID are set."""
    with patch.object(AudioResolver, "search", new_callable=AsyncMock, return_value=[]), \
         patch("music_bot.services.resolver_service._run_ytdlp", side_effect=RuntimeError("YouTube 403 Forbidden")), \
         patch("music_bot.services.alternative_providers.AudiusProviderService.search", new_callable=AsyncMock, return_value=[]), \
         patch("music_bot.services.alternative_providers.JamendoProviderService.search", new_callable=AsyncMock, return_value=[]):
        track = await AudioResolver.resolve_track("obscure nonexistent track 999", 123, "User")
        assert track is None
        err = AudioResolver.last_resolver_error or ""
        assert "Ref: MM-" in err
        assert "403 Forbidden" in err or "YouTube" in err


# ---------------------------------------------------------------------------
# 12. Ensuring No Secrets Appear in Logs or Diagnostics
# ---------------------------------------------------------------------------
def test_no_secrets_in_cookie_diagnostics(tmp_path):
    """Ensure cookie values, passwords, or tokens never appear in diagnostics."""
    secret_token = "SECRET_SAPISID_COOKIE_VAL_ABC987"
    cookie_file = tmp_path / "secret_cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        f".youtube.com\tTRUE\t/\tTRUE\t{int(time.time() + 86400)}\tSAPISID\t{secret_token}\n",
        encoding="utf-8",
    )
    with patch("music_bot.services.resolver_service.WRITABLE_COOKIE_PATH", cookie_file):
        diag = get_cookie_diagnostics()
        diag_repr = repr(diag)
        assert secret_token not in diag_repr
        assert diag["present"] is True
        assert diag["is_valid"] is True


# ---------------------------------------------------------------------------
# 13. Resolving Embed Hides Raw URLs
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resolving_embed_hides_raw_url_and_clears_view():
    """Verify loading and resolving embeds do not display raw URLs and dismiss views."""
    from music_bot.commands.music_cog import MusicCog

    mock_bot = MagicMock()
    mock_bot.db = AsyncMock()
    cog = MusicCog(mock_bot)

    mock_interaction = MagicMock()
    mock_interaction.response.is_done.return_value = True
    mock_interaction.guild_id = 9999
    mock_guild = MagicMock(spec=discord.Guild)
    mock_guild.id = 9999
    mock_interaction.guild = mock_guild
    mock_member = MagicMock(spec=discord.Member)
    mock_member.id = 12345
    mock_member.guild_permissions.administrator = True
    mock_interaction.user = mock_member
    mock_channel = MagicMock(spec=discord.TextChannel)
    mock_interaction.channel = mock_channel
    mock_interaction.edit_original_response = AsyncMock()
    mock_interaction.followup.send = AsyncMock()

    # Case A: URL with display_name (e.g. chosen from candidate dropdown)
    with patch.object(AudioResolver, "resolve_track", new_callable=AsyncMock, return_value=None), \
         patch.object(cog.session_manager, "get_session", new_callable=AsyncMock) as mock_get_sess, \
         patch("music_bot.services.voice_service.VoiceManager.join_voice_channel", new_callable=AsyncMock, return_value=MagicMock()):
        mock_sess = MagicMock()
        mock_sess.lock = asyncio.Lock()
        mock_get_sess.return_value = mock_sess

        await cog._play_query(
            mock_interaction,
            "https://www.youtube.com/watch?v=jR3rWCBeO6M",
            display_name="Raadhima (Official Video)",
        )

        # Inspect call args to edit_original_response for the loading embed
        calls = mock_interaction.edit_original_response.call_args_list
        assert len(calls) >= 1
        loading_call = calls[0]
        embed = loading_call.kwargs.get("embed")
        assert embed is not None
        assert "https://" not in embed.description
        assert "youtube.com" not in embed.description
        assert "Raadhima (Official Video)" in embed.description
        assert loading_call.kwargs.get("content") is None
        assert loading_call.kwargs.get("view") is None

    # Case B: Direct URL without display_name
    mock_interaction.reset_mock()
    with patch.object(AudioResolver, "resolve_track", new_callable=AsyncMock, return_value=None), \
         patch.object(cog.session_manager, "get_session", new_callable=AsyncMock) as mock_get_sess, \
         patch("music_bot.services.voice_service.VoiceManager.join_voice_channel", new_callable=AsyncMock, return_value=MagicMock()):
        mock_sess = MagicMock()
        mock_sess.lock = asyncio.Lock()
        mock_get_sess.return_value = mock_sess

        await cog._play_query(
            mock_interaction,
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )

        calls = mock_interaction.edit_original_response.call_args_list
        assert len(calls) >= 1
        loading_call = calls[0]
        embed = loading_call.kwargs.get("embed")
        assert embed is not None
        assert "https://" not in embed.description
        assert "youtube.com" not in embed.description
        assert "Resolving audio track" in embed.description


# ---------------------------------------------------------------------------
# 13. FFmpeg HTTP 403 Stream Recovery & Provider Fallback
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ffmpeg_403_stream_recovery_to_audius_fallback():
    """Verify that when FFmpeg receives 0 bytes from a YouTube stream (HTTP 403),
    PlayerService evicts cache, retries YouTube, and falls back to a verified Audius track."""
    from music_bot.services.player_service import PlayerService
    from music_bot.services.session_service import GuildMusicSession, PlaybackState

    bot = MagicMock()
    session = GuildMusicSession(guild_id=123)
    mock_vc = MagicMock()
    mock_vc.is_playing.return_value = False
    mock_vc.is_paused.return_value = False
    mock_vc.is_connected.return_value = True
    session.voice_client = mock_vc

    track = QueuedTrack(
        title="Kalyani",
        url="https://www.youtube.com/watch?v=xvT1jH8B9AM",
        stream_url="https://rr1---sn-4g5ednks.googlevideo.com/videoplayback?expire=123",
        duration=240,
        requester_id=1,
        requester_name="Tester",
        artist="Shreya Ghoshal",
        http_headers={"User-Agent": "Mozilla/5.0"},
    )

    audius_track = QueuedTrack(
        title="Kalyani",
        url="https://audius.co/shreya/kalyani",
        stream_url="https://audius-discovery-1.audius.co/v1/tracks/kalyani/stream",
        duration=240,
        requester_id=1,
        requester_name="Tester",
        artist="Shreya Ghoshal",
    )
    setattr(audius_track, "provider", "audius")

    # Mock FFmpegPCMAudio and PCMVolumeTransformer
    with patch("discord.FFmpegPCMAudio") as mock_ffmpeg, \
         patch("discord.PCMVolumeTransformer") as mock_transformer, \
         patch.object(AudioResolver, "evict_track", new_callable=AsyncMock) as mock_evict, \
         patch.object(AudioResolver, "resolve_track", new_callable=AsyncMock, return_value=None), \
         patch.object(AudioResolver, "resolve_alternative_fallback", new_callable=AsyncMock, return_value=(audius_track, None)) as mock_fb:

        # First read (initial YouTube attempt) returns empty bytes (403 block)
        # Second read (fallback Audius attempt) returns valid audio bytes
        mock_reader = MagicMock()
        mock_reader.read.side_effect = [b"", b"\x01\x02" * 50]
        mock_transformer.return_value = mock_reader

        result = await PlayerService.start_playback(bot, session, track)
        assert result is True
        assert mock_evict.called
        assert mock_fb.called
        assert track.stream_url == audius_track.stream_url
        assert getattr(track, "provider", None) == "audius"


@pytest.mark.asyncio
async def test_ffmpeg_403_stream_all_sources_exhausted_diagnostic():
    """Verify that when YouTube fails and alternative providers find no valid match,
    PlayerService stops safely and records a comprehensive diagnostic."""
    from music_bot.services.player_service import PlayerService
    from music_bot.services.session_service import GuildMusicSession, PlaybackState

    bot = MagicMock()
    session = GuildMusicSession(guild_id=123)
    mock_vc = MagicMock()
    mock_vc.is_playing.return_value = False
    mock_vc.is_paused.return_value = False
    mock_vc.is_connected.return_value = True
    session.voice_client = mock_vc

    track = QueuedTrack(
        title="Rare Unreleased Track",
        url="https://www.youtube.com/watch?v=unreleased1",
        stream_url="https://googlevideo.com/videoplayback?expire=123",
        duration=200,
        requester_id=1,
        requester_name="Tester",
        artist="Unknown",
    )

    with patch("discord.FFmpegPCMAudio"), \
         patch("discord.PCMVolumeTransformer") as mock_transformer, \
         patch.object(AudioResolver, "evict_track", new_callable=AsyncMock), \
         patch.object(AudioResolver, "resolve_track", new_callable=AsyncMock, return_value=None), \
         patch.object(AudioResolver, "resolve_alternative_fallback", new_callable=AsyncMock, return_value=(None, "No matching verified tracks found on Audius or Jamendo")):

        mock_reader = MagicMock()
        mock_reader.read.return_value = b""
        mock_transformer.return_value = mock_reader

        result = await PlayerService.start_playback(bot, session, track)
        assert result is False
        assert session.state == PlaybackState.ERROR
        assert "HTTP 403 / datacenter IP restriction" in session.last_error
        assert "Secondary fallback (Audius / Jamendo)" in session.last_error


@pytest.mark.asyncio
async def test_build_ffmpeg_options_includes_custom_user_agent_and_cookies():
    """Verify build_ffmpeg_options injects User-Agent and Cookies into before_options."""
    from music_bot.services.resolver_service import build_ffmpeg_options

    track = QueuedTrack(
        title="Test Song",
        url="https://www.youtube.com/watch?v=123",
        stream_url="https://googlevideo.com/videoplayback",
        duration=180,
        requester_id=1,
        requester_name="Tester",
        http_headers={"User-Agent": "Custom-Android-Client/1.0"},
    )

    with patch("music_bot.services.resolver_service.get_active_cookie_file", return_value="dummy_cookies.txt"), \
         patch("music_bot.services.resolver_service._extract_cookie_header_from_file", return_value="SID=12345; HSID=67890"):
        opts = build_ffmpeg_options(track, start_seconds=15)
        before = opts.get("before_options", "")
        assert "-ss 15" in before
        assert "-user_agent \"Custom-Android-Client/1.0\"" in before
        assert "-headers \"Cookie: SID=12345; HSID=67890\\r\\n\"" in before


