"""
Phase 3 Tests — Real-Time Music Player & Queue Synchronization.
Validates player controls, queue mutations, range checks, duplicate detection,
queue limits, and authoritative player synchronization.
"""

import json
import pytest
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp.test_utils import make_mocked_request

from web.music_api import MusicApiRouter


class MockGuildSession:
    """Mock session class that avoids MagicMock type check filter."""
    def __init__(self):
        self.queue = deque()
        self.is_playing = False
        self.has_active_track = False
        self.voice_client = None
        self.voice_channel_name = "General Voice"


@pytest.fixture
def mock_auth_manager():
    auth = MagicMock()
    auth.get_session_from_request = AsyncMock(return_value={
        "user_id": 1457380609641938981,
        "username": "KishoreDev",
        "is_owner": True,
        "is_admin": True,
    })
    return auth


@pytest.fixture
def music_router(mock_auth_manager):
    bot = MagicMock()
    bot.is_ready = MagicMock(return_value=True)
    g_mock = MagicMock()
    bot.get_guild = MagicMock(return_value=g_mock)
    router = MusicApiRouter(auth_manager=mock_auth_manager, bot=bot)
    router._db_connected = True
    router.db = MagicMock()
    router.db.submit_web_action = AsyncMock(return_value=123)
    router.db.mark_web_action_completed = AsyncMock()
    return router


def _create_mock_req(method: str, path: str, json_data: dict):
    req = make_mocked_request(method, path, headers={"Content-Type": "application/json"})
    req.json = AsyncMock(return_value=json_data)
    return req


@pytest.mark.asyncio
async def test_dispatch_control_volume_validation(music_router):
    """Verify volume control rejects out-of-range volume values (<0 or >150)."""
    # Negative volume
    req_bad = _create_mock_req(
        "POST", "/api/music/control",
        {"guild_id": 1525030316845301781, "action": "VOLUME", "volume": -10}
    )
    resp_bad = await music_router.dispatch_control(req_bad)
    assert resp_bad.status == 400
    data_bad = json.loads(resp_bad.text)
    assert data_bad["error"]["code"] == "INVALID_VOLUME_RANGE"

    # Excess volume (>150)
    req_excess = _create_mock_req(
        "POST", "/api/music/control",
        {"guild_id": 1525030316845301781, "action": "VOLUME", "volume": 200}
    )
    resp_excess = await music_router.dispatch_control(req_excess)
    assert resp_excess.status == 400
    data_excess = json.loads(resp_excess.text)
    assert data_excess["error"]["code"] == "INVALID_VOLUME_RANGE"


@pytest.mark.asyncio
async def test_dispatch_control_missing_action(music_router):
    """Verify missing action parameter fails with 400."""
    req = _create_mock_req(
        "POST", "/api/music/control",
        {"guild_id": 1525030316845301781}
    )
    resp = await music_router.dispatch_control(req)
    assert resp.status == 400
    data = json.loads(resp.text)
    assert data["error"]["code"] == "MISSING_ACTION"


@pytest.mark.asyncio
async def test_queue_limit_enforcement(music_router):
    """Verify enqueue rejects when queue is at max capacity (250)."""
    fake_session = MockGuildSession()
    fake_session.queue = deque([MagicMock() for _ in range(250)])

    with patch("music_bot.services.session_service.SessionManager.get_instance") as mock_sm:
        sm_inst = MagicMock()
        sm_inst.get_session_nowait = MagicMock(return_value=fake_session)
        mock_sm.return_value = sm_inst

        req = _create_mock_req(
            "POST", "/api/music/control",
            {"guild_id": 1525030316845301781, "action": "ENQUEUE", "query": "Never Gonna Give You Up"}
        )
        resp = await music_router.dispatch_control(req)
        assert resp.status == 400
        data = json.loads(resp.text)
        assert data["error"]["code"] == "QUEUE_LIMIT_REACHED"


@pytest.mark.asyncio
async def test_duplicate_detection(music_router):
    """Verify duplicate detection identifies tracks already present in queue."""
    existing_track = MagicMock()
    existing_track.url = "https://youtube.com/watch?v=dQw4w9WgXcQ"
    existing_track.title = "Never Gonna Give You Up"
    existing_track.artist = "Rick Astley"

    fake_session = MockGuildSession()
    fake_session.queue = deque([existing_track])
    fake_session.is_playing = True
    fake_session.has_active_track = True

    resolved_track = MagicMock()
    resolved_track.url = "https://youtube.com/watch?v=dQw4w9WgXcQ"
    resolved_track.title = "Never Gonna Give You Up"
    resolved_track.artist = "Rick Astley"

    with patch("music_bot.services.session_service.SessionManager.get_instance") as mock_sm:
        sm_inst = MagicMock()
        sm_inst.get_session_nowait = MagicMock(return_value=fake_session)
        mock_sm.return_value = sm_inst

        with patch("music_bot.services.resolver_service.AudioResolver.resolve_track", AsyncMock(return_value=resolved_track)):
            with patch("music_bot.services.player_service.MusicPlayerService.send_now_playing_panel", AsyncMock()):
                req = _create_mock_req(
                    "POST", "/api/music/control",
                    {"guild_id": 1525030316845301781, "action": "ENQUEUE", "query": "Never Gonna Give You Up"}
                )
                resp = await music_router.dispatch_control(req)
                assert resp.status == 200
                data = json.loads(resp.text)
                assert data["success"] is True
                assert data["data"]["is_duplicate"] is True
                assert "Duplicate track noted" in data["data"]["message"]
