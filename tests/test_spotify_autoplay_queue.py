"""Regression tests for Spotify playlist/album autoplay import."""

from unittest.mock import AsyncMock, patch

import pytest

from music_bot.services.importer_service import PlaylistImporterService


@pytest.mark.asyncio
async def test_spotify_collection_import_preserves_order_and_does_not_fake_audio_streams():
    collection = {
        "title": "Ordered Anime Mix",
        "thumbnail": "https://example.test/cover.jpg",
        "tracks": [
            {"id": "track-a", "name": "First Song", "artist": "Artist A", "url": "https://open.spotify.com/track/track-a", "duration": 180},
            {"id": "track-b", "name": "Second Song", "artist": "Artist B", "url": "https://open.spotify.com/track/track-b", "duration": 200},
            {"id": "track-c", "name": "Third Song", "artist": "Artist C", "url": "https://open.spotify.com/track/track-c", "duration": 220},
        ],
    }

    with patch(
        "music_bot.services.importer_service.AudioResolver.resolve_spotify_collection",
        new_callable=AsyncMock,
        return_value=collection,
    ):
        title, tracks, platform = await PlaylistImporterService.extract_tracks_from_url(
            "https://open.spotify.com/playlist/abc123",
            requester_id=123,
            requester_name="Kishore",
            limit=10,
        )

    assert title == "Ordered Anime Mix"
    assert platform == "Spotify"
    assert [track.title for track in tracks] == ["First Song", "Second Song", "Third Song"]
    assert [track.url for track in tracks] == [
        "https://open.spotify.com/track/track-a",
        "https://open.spotify.com/track/track-b",
        "https://open.spotify.com/track/track-c",
    ]
    assert all(track.stream_url == "" for track in tracks)
    assert all(track.requester_id == 123 for track in tracks)
    assert all(track.requester_name == "Kishore" for track in tracks)


@pytest.mark.asyncio
async def test_spotify_collection_import_respects_limit():
    collection = {
        "title": "Long Mix",
        "tracks": [
            {"id": f"track-{i}", "name": f"Song {i}", "artist": "Artist", "duration": 120}
            for i in range(5)
        ],
    }

    with patch(
        "music_bot.services.importer_service.AudioResolver.resolve_spotify_collection",
        new_callable=AsyncMock,
        return_value=collection,
    ) as resolve:
        title, tracks, platform = await PlaylistImporterService.extract_tracks_from_url(
            "https://open.spotify.com/album/abc123",
            requester_id=1,
            requester_name="Tester",
            limit=2,
        )

    resolve.assert_awaited_once_with("https://open.spotify.com/album/abc123", limit=2)
    assert title == "Long Mix"
    assert platform == "Spotify"
    assert len(tracks) == 2
    assert [track.title for track in tracks] == ["Song 0", "Song 1"]
