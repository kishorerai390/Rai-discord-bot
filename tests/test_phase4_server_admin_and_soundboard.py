"""
Phase 4 Tests — Server Administrator Dashboard, Settings & Soundboard.
Validates server configuration, 24/7 mode, auto-leave timeout, DJ role RBAC,
soundboard audio triggers, and 3-second cooldown protection.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp.test_utils import make_mocked_request

from web.music_api import MusicApiRouter, SOUNDBOARD_LIBRARY
from music_bot.database.models import MusicGuildSettings


@pytest.fixture
def mock_auth_manager():
    auth = MagicMock()
    auth.get_session_from_request = AsyncMock(return_value={
        "user_id": 1457380609641938981,
        "username": "AdminUser",
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


def _create_mock_req(method: str, path: str, json_data: dict = None, query: dict = None):
    headers = {"Content-Type": "application/json"}
    req = make_mocked_request(method, path, headers=headers)
    if json_data is not None:
        req.json = AsyncMock(return_value=json_data)
    if query:
        req._query = query
        req._rel_url = MagicMock()
        req._rel_url.query = query
    return req


@pytest.mark.asyncio
async def test_get_guild_settings_returns_complete_fields(music_router):
    """Verify get_guild_settings returns full server configuration including DJ role and request channel."""
    fake_settings = MusicGuildSettings(
        guild_id=1525030316845301781,
        prefix="!",
        default_volume=85,
        autoplay_enabled=True,
        auto_leave_enabled=True,
        auto_leave_timeout=120,
        dj_mode_enabled=True,
        dj_role_id=987654321098765432,
        request_channel_id=112233445566778899,
        twenty_four_seven_enabled=True,
        twenty_four_seven_channel_id=998877665544332211,
    )
    music_router.db.get_guild_settings = AsyncMock(return_value=fake_settings)

    req = _create_mock_req("GET", "/api/music/guild-settings?guild_id=1525030316845301781")
    resp = await music_router.get_guild_settings(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["success"] is True
    s = data["data"]
    assert s["prefix"] == "!"
    assert s["default_volume"] == 85
    assert s["dj_mode_enabled"] is True
    assert s["dj_role_id"] == "987654321098765432"
    assert s["request_channel_id"] == "112233445566778899"
    assert s["twenty_four_seven_enabled"] is True
    assert s["twenty_four_seven_channel_id"] == "998877665544332211"


@pytest.mark.asyncio
async def test_update_guild_settings_validation(music_router):
    """Verify update_guild_settings properly validates and updates server preferences."""
    fake_settings = MusicGuildSettings(guild_id=1525030316845301781)
    music_router.db.get_guild_settings = AsyncMock(return_value=fake_settings)
    music_router.db.update_guild_settings = AsyncMock()

    update_payload = {
        "guild_id": 1525030316845301781,
        "prefix": "?",
        "default_volume": 90,
        "twenty_four_seven_enabled": True,
        "twenty_four_seven_channel_id": 998877665544332211,
        "auto_leave_enabled": False,
        "auto_leave_timeout": 300,
        "dj_mode_enabled": True,
        "dj_role_id": "987654321098765432",
        "request_channel_id": "112233445566778899",
        "vote_skip_threshold": 0.65,
    }

    req = _create_mock_req("POST", "/api/music/guild-settings", update_payload)
    resp = await music_router.update_guild_settings(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["success"] is True
    assert data["data"]["message"] == "Guild settings updated successfully"

    music_router.db.update_guild_settings.assert_called_once()
    saved = music_router.db.update_guild_settings.call_args[0][0]
    assert saved.prefix == "?"
    assert saved.default_volume == 90
    assert saved.twenty_four_seven_enabled is True
    assert saved.auto_leave_enabled is False
    assert saved.auto_leave_timeout == 300
    assert saved.dj_mode_enabled is True
    assert saved.dj_role_id == 987654321098765432
    assert saved.request_channel_id == 112233445566778899
    assert saved.vote_skip_threshold == 0.65


@pytest.mark.asyncio
async def test_get_soundboard_sounds(music_router):
    """Verify soundboard library endpoint returns registered sound effects."""
    req = _create_mock_req("GET", "/api/music/soundboard")
    resp = await music_router.get_soundboard_sounds(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["success"] is True
    sounds = data["data"]["sounds"]
    assert len(sounds) >= 10
    sound_ids = [s["id"] for s in sounds]
    assert "airhorn" in sound_ids
    assert "bruh" in sound_ids
    assert "anime_wow" in sound_ids
    assert "vineboom" in sound_ids


@pytest.mark.asyncio
async def test_soundboard_cooldown_enforcement(music_router):
    """Verify soundboard enforces 3.0-second cooldown between sound triggers."""
    music_router._soundboard_cooldowns.clear()

    # First trigger should succeed
    req1 = _create_mock_req(
        "POST", "/api/music/soundboard",
        {"guild_id": 1525030316845301781, "sound_id": "bruh"}
    )
    with patch("music_bot.services.resolver_service.AudioResolver.resolve_track", AsyncMock(return_value=None)):
        resp1 = await music_router.trigger_soundboard(req1)
        assert resp1.status == 200
        data1 = json.loads(resp1.text)
        assert data1["success"] is True
        assert data1["data"]["sound_id"] == "bruh"

        # Immediate second trigger must be rate-limited (429)
        req2 = _create_mock_req(
            "POST", "/api/music/soundboard",
            {"guild_id": 1525030316845301781, "sound_id": "airhorn"}
        )
        resp2 = await music_router.trigger_soundboard(req2)
        assert resp2.status == 429
        data2 = json.loads(resp2.text)
        assert data2["success"] is False
        assert data2["error"]["code"] == "COOLDOWN_ACTIVE"
        assert "Soundboard cooldown active" in data2["error"]["message"]


@pytest.mark.asyncio
async def test_soundboard_invalid_sound_returns_404(music_router):
    """Verify requesting an unknown sound ID returns 404 SOUND_NOT_FOUND."""
    req = _create_mock_req(
        "POST", "/api/music/soundboard",
        {"guild_id": 1525030316845301781, "sound_id": "nonexistent_sound"}
    )
    resp = await music_router.trigger_soundboard(req)
    assert resp.status == 404
    data = json.loads(resp.text)
    assert data["success"] is False
    assert data["error"]["code"] == "SOUND_NOT_FOUND"
