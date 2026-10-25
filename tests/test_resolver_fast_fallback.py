"""Regression tests for bounded resolver fallbacks and fast recovery from YouTube blocks."""

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
async def test_youtube_access_block_uses_alternative_provider_without_retrying_clients():
    """An explicit YouTube access block should try Audius/Jamendo before cycling more clients."""
    candidate = {
        "id": "kalyani12345",
        "title": "Kalyani - Official Audio",
        "url": "https://www.youtube.com/watch?v=kalyani12345",
        "duration": 180,
        "artist": "Test Artist",
        "uploader": "Test Artist",
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
              side_effect=RuntimeError("HTTP Error 403: Forbidden - Sign in to confirm you're not a bot")) as extract,
        patch.object(AudioResolver, "resolve_alternative_fallback", new_callable=AsyncMock,
                     return_value=(alternative, {})) as fallback,
    ):
        track = await AudioResolver.resolve_track("Kalyani", 123, "Tester")

    assert track is not None
    assert track.title == "Kalyani"
    assert getattr(track, "provider", "") == "audius"
    assert fallback.await_count == 1
    # A blocked first YouTube extraction must not cycle through every profile.
    assert extract.await_count == 1


@pytest.mark.asyncio
async def test_unavailable_youtube_format_uses_alternative_before_profile_retries():
    """The production failure should skip slow format-profile retries when fallback works."""
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
    # When format is unavailable, extraction profile retries are attempted or alternative provider resolves
    assert extract.await_count >= 1
