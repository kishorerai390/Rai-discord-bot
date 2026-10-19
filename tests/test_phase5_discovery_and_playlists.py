"""
Phase 5 Tests — Music Discovery, Search, Playlists & Multi-Source Resolvers.
Validates search resolution, playlist lifecycle (create, list, load, delete),
and user favorite track synchronization.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp.test_utils import make_mocked_request

from web.music_api import MusicApiRouter
from music_bot.database.models import QueuedTrack, MusicPlaylist


@pytest.fixture
def mock_auth_manager():
    auth = MagicMock()
    auth.get_session_from_request = AsyncMock(return_value={
        "user_id": 1457380609641938981,
        "username": "DiscoveryUser",
        "is_owner": True,
        "is_admin": True,
    })
    auth.require_guild_admin = AsyncMock(return_value={
        "discord_user_id": 1457380609641938981,
        "is_admin": True,
    })
    auth.get_user_entitlements = AsyncMock(return_value={"is_premium": True})
    return auth


@pytest.fixture
def music_router(mock_auth_manager):
    bot = MagicMock()
    bot.is_ready = MagicMock(return_value=True)
    g_mock = MagicMock()
    g_mock.id = 1525030316845301781
    bot.get_guild = MagicMock(return_value=g_mock)

    router = MusicApiRouter(auth_manager=mock_auth_manager, bot=bot)
    router._db_connected = True
    router.db = MagicMock()
    return router


def _create_mock_req(method: str, path: str, json_data: dict = None):
    headers = {"Content-Type": "application/json"}
    req = make_mocked_request(method, path, headers=headers)
    if json_data is not None:
        req.json = AsyncMock(return_value=json_data)
    return req


@pytest.mark.asyncio
async def test_search_tracks_direct_youtube_url(music_router):
    """Verify search_tracks accurately parses direct YouTube URL with video ID thumbnail."""
    req = _create_mock_req("GET", "/api/music/search?q=https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    resp = await music_router.search_tracks(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["success"] is True
    assert len(data["data"]) == 1
    track = data["data"][0]
    assert track["id"] == "dQw4w9WgXcQ"
    assert "hqdefault.jpg" in track["thumbnail"]
    assert track["provider"] == "youtube"


@pytest.mark.asyncio
async def test_search_tracks_query_resolution(music_router):
    """Verify search_tracks resolves multi-track query using AudioResolver."""
    mock_results = [
        {
            "id": "abc123",
            "title": "Hukum - Thalaivar Alappara",
            "artist": "Anirudh Ravichander",
            "url": "https://www.youtube.com/watch?v=abc123",
            "duration": 204,
            "thumbnail": "https://i.ytimg.com/vi/abc123/hqdefault.jpg",
            "provider": "youtube",
        }
    ]
    with patch("music_bot.services.resolver_service.AudioResolver.search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_results
        req = _create_mock_req("GET", "/api/music/search?q=Anirudh+Hukum")
        resp = await music_router.search_tracks(req)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["data"][0]["title"] == "Hukum - Thalaivar Alappara"
        assert data["data"][0]["duration"] == 204


@pytest.mark.asyncio
async def test_get_playlists_lists_guild_playlists(music_router):
    """Verify get_playlists queries database and formats playlist metadata."""
    p1 = MagicMock(spec=MusicPlaylist)
    p1.id = 42
    p1.name = "Late Night Lo-Fi"
    p1.is_server = True
    p1.track_count = 15
    p1.created_at = "2026-10-19T00:00:00Z"
    p1.tracks = [MagicMock()] * 15

    music_router.db.get_playlists = AsyncMock(return_value=[p1])
    music_router.db.check_guild_access = AsyncMock(return_value=True)

    req = _create_mock_req("GET", "/api/music/playlists?guild_id=1525030316845301781")
    resp = await music_router.get_playlists(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["success"] is True
    assert data["data"]["guild_id"] == "1525030316845301781"
    assert len(data["data"]["playlists"]) == 1
    assert data["data"]["playlists"][0]["name"] == "Late Night Lo-Fi"
    assert data["data"]["playlists"][0]["track_count"] == 15


@pytest.mark.asyncio
async def test_save_and_delete_playlist(music_router):
    """Verify save_playlist and delete_playlist by name and ID."""
    music_router.db.check_guild_access = AsyncMock(return_value=True)
    music_router.db.create_playlist = AsyncMock(return_value=101)
    music_router.db.add_playlist_track = AsyncMock(return_value=True)
    music_router.db.delete_playlist = AsyncMock(return_value=True)

    # Mock in-memory session with 2 tracks
    mock_session = MagicMock()
    mock_session.current_track = QueuedTrack(
        title="Song 1", artist="Artist 1", url="http://s1", duration=120, requester_id=1, requester_name="Admin"
    )
    mock_session.queue = [
        QueuedTrack(
            title="Song 2", artist="Artist 2", url="http://s2", duration=180, requester_id=1, requester_name="Admin"
        )
    ]
    with patch("music_bot.services.session_service.SessionManager.get_instance") as mock_sm:
        mock_sm.return_value.get_session_nowait.return_value = mock_session

        # 1. Save
        save_req = _create_mock_req(
            "POST",
            "/api/music/playlists/save",
            json_data={"guild_id": 1525030316845301781, "name": "Chill Session", "is_server": True},
        )
        save_resp = await music_router.save_playlist(save_req)
        assert save_resp.status == 200
        save_data = json.loads(save_resp.text)
        assert save_data["success"] is True
        assert save_data["data"]["playlist_id"] == 101
        assert save_data["data"]["track_count"] == 2

        # 2. Delete by name
        del_req = _create_mock_req(
            "POST",
            "/api/music/playlists/delete",
            json_data={"guild_id": 1525030316845301781, "name": "Chill Session"},
        )
        del_resp = await music_router.delete_playlist(del_req)
        assert del_resp.status == 200
        del_data = json.loads(del_resp.text)
        assert del_data["success"] is True
        assert del_data["data"]["deleted"] is True


@pytest.mark.asyncio
async def test_favorites_lifecycle(music_router):
    """Verify get_favorites and toggle_favorite adds then removes a track."""
    fav_item = {
        "id": "fav_1",
        "title": "Favorite Song",
        "artist": "Great Artist",
        "url": "https://youtube.com/watch?v=fav123",
        "duration": 210,
        "thumbnail": "https://img.jpg",
    }
    music_router.db.get_user_favorites = AsyncMock(side_effect=[[], [], [fav_item]])
    music_router.db.add_favorite = AsyncMock(return_value=True)
    music_router.db.remove_favorite = AsyncMock(return_value=True)

    # 1. Get empty favorites
    get_req1 = _create_mock_req("GET", "/api/music/favorites")
    resp1 = await music_router.get_favorites(get_req1)
    assert resp1.status == 200
    assert json.loads(resp1.text)["data"] == []

    # 2. Toggle add favorite
    toggle_req1 = _create_mock_req(
        "POST",
        "/api/music/favorites/toggle",
        json_data={"title": "Favorite Song", "artist": "Great Artist", "url": "https://youtube.com/watch?v=fav123"},
    )
    tresp1 = await music_router.toggle_favorite(toggle_req1)
    assert tresp1.status == 200
    tdata1 = json.loads(tresp1.text)
    assert tdata1["success"] is True
    assert tdata1["data"]["favorited"] is True

    # 3. Toggle remove favorite
    toggle_req2 = _create_mock_req(
        "POST",
        "/api/music/favorites/toggle",
        json_data={"title": "Favorite Song", "artist": "Great Artist", "url": "https://youtube.com/watch?v=fav123"},
    )
    tresp2 = await music_router.toggle_favorite(toggle_req2)
    assert tresp2.status == 200
    tdata2 = json.loads(tresp2.text)
    assert tdata2["success"] is True
    assert tdata2["data"]["favorited"] is False
