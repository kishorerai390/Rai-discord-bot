"""
Tests for JukeBot Music Integration (StreamRequest, Radio suite, queue insertion).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from music_bot.services.jukebot_service import JukeBotStreamRequest, JUKEBOT_RADIOS
from music_bot.services.resolver_service import AudioResolver


def test_jukebot_radios_available():
    """Verify radio stations are properly configured."""
    stations = JukeBotStreamRequest.list_radio_stations()
    assert "lofi" in stations
    assert "synthwave" in stations
    assert "phonk" in stations
    assert "jazz" in stations

    url = JukeBotStreamRequest.get_random_radio_url("lofi")
    assert url is not None
    assert url.startswith("https://")


@pytest.mark.asyncio
async def test_jukebot_stream_request_mocked_extraction():
    """Verify JukeBotStreamRequest extracts song metadata and stream URL."""
    fake_info = {
        "url": "https://rr1---sn-fake.googlevideo.com/videoplayback?expire=123",
        "title": "JukeBot Lofi Chill",
        "duration": 180,
        "thumbnail": "https://i.ytimg.com/vi/fake/default.jpg",
        "channel": "Lofi Girl",
        "webpage_url": "https://www.youtube.com/watch?v=fake",
        "id": "fake",
    }

    with patch("music_bot.services.jukebot_service.yt_dlp.YoutubeDL") as mock_ydl_cls:
        instance = MagicMock()
        instance.__enter__.return_value = instance
        instance.extract_info.return_value = fake_info
        mock_ydl_cls.return_value = instance

        result = await JukeBotStreamRequest.extract_stream("https://www.youtube.com/watch?v=fake")
        assert result is not None
        assert result["stream_url"] == fake_info["url"]
        assert result["title"] == "JukeBot Lofi Chill"
        assert result["duration"] == 180


@pytest.mark.asyncio
async def test_jukebot_tier_in_audio_resolver():
    """Verify AudioResolver invokes JukeBotStreamRequest when public profile tiers fail."""
    fake_stream_data = {
        "stream_url": "https://stream.googlevideo.com/audio",
        "title": "Tested Audio Song",
        "duration": 210,
        "thumbnail": "https://thumb.jpg",
        "uploader": "Test Uploader",
        "url": "https://www.youtube.com/watch?v=TEST_VID_ID",
        "id": "TEST_VID_ID",
    }

    with patch.object(AudioResolver, "search", new_callable=AsyncMock, return_value=[{"url": "https://www.youtube.com/watch?v=TEST_VID_ID", "title": "Tested Audio Song", "duration": 210, "artist": "Test Uploader"}]), \
         patch("music_bot.services.resolver_service._run_ytdlp", side_effect=RuntimeError("Sign in to confirm you're not a bot")), \
         patch.object(JukeBotStreamRequest, "extract_stream", new_callable=AsyncMock, return_value=fake_stream_data):
        
        track = await AudioResolver.resolve_track("Tested Audio Song", 12345, "Tester")
        assert track is not None
        assert track.title == "Tested Audio Song"
        assert track.stream_url == "https://stream.googlevideo.com/audio"
