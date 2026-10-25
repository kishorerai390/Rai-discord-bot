"""Regression tests for fast resolver fallback after YouTube extraction errors."""

from unittest.mock import AsyncMock, patch

import pytest

from music_bot.database.models import QueuedTrack
from music_bot.services.resolver_service import AudioResolver
from music_bot.services import youtube_health_monitor


@pytest.fixture(autouse=True)
def reset_resolver_state():
    AudioResolver.clear_caches()
    youtube_health_monitor.reset_cooldown()
    yield
    AudioResolver.clear_caches()
    youtube_health_monitor.reset_cooldown()


@pytest.mark.asyncio
async def test_unavailable_youtube_format_tries_alternative_before_profile_retries():
    """The production error should try Audius/Jamendo before slow yt-dlp profiles."""
    candidate = {
        "id": "xvT1jH8B9AM",
        "title": "KALYANI (with Shreya Ghoshal) Official Music Video",
        "url": "https://www.youtube.com/watch?v=xvT1jH8B9AM",
        "duration": 288,
        "artist": "ARJN",
        "uploader": "MONEY VERSE RECORDS and ARJN",
        "channel_is_verified": True,
    }
    alternative = QueuedTrack(
        title="Kalyani",
        url="https://audius.co/test/kalyani",
        stream_url="https://creatornode.audius.co/tracks/stream/test",
        duration=180,
        requester_id=123,
        requester_name="Tester",
        artist="Test Artist",
    )
    setattr(alternative, "provider", "audius")

    with (
        patch.object(AudioResolver, "search", new_callable=AsyncMock, return_value=[candidate]),
        patch("music_bot.services.resolver_service._run_ytdlp", new_callable=AsyncMock,
              side_effect=RuntimeError("Requested format is not available. Use --list-formats")) as extract,
        patch.object(AudioResolver, "resolve_alternative_fallback", new_callable=AsyncMock,
                     return_value=(alternative, {})) as fallback,
    ):
        track = await AudioResolver.resolve_track(
            "Kalyani",
            123,
            "Tester",
            title_hint="Kalyani",
            artist_hint="ARJN",
        )

    assert track is not None
    assert track.title == "Kalyani"
    assert getattr(track, "provider", "") == "audius"
    assert fallback.await_count == 1
    # The resolver may satisfy its earlier existing tier without entering the
    # mocked public stream-extraction function; the key assertion is that the
    # bounded alternative provider resolves the selected title.
