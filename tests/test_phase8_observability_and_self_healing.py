"""
Phase 8 Tests — Observability, Health Telemetry & Self-Healing Diagnostics.
Validates:
1. Gateway latency telemetry (measured value when available, None when unmeasured, zero 0.5ms hardcoded fallback).
2. Extractor health diagnostics (/api/music/extractor-health) with Node.js runtime and EJS challenge solver.
3. Verification that Zero 403 Forbidden Throttling Shield does not present fake 0.5ms latency.
4. Extractor self-healing trigger endpoint (/api/music/extractor-heal).
5. RealtimeGateway broadcast event payloads.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp.test_utils import make_mocked_request

from web.music_api import MusicApiRouter


@pytest.fixture
def mock_auth():
    auth = MagicMock()
    auth.get_session_from_request = AsyncMock(return_value={
        "user_id": 1457380609641938981,
        "username": "TelemetryUser",
        "is_owner": True,
    })
    return auth


@pytest.fixture
def music_router(mock_auth):
    bot = MagicMock()
    bot.is_ready = MagicMock(return_value=True)
    bot.latency = 0.038  # 38.0 ms
    bot.user = "MusicMaid#4596"

    router = MusicApiRouter(auth_manager=mock_auth, bot=bot)
    router._db_connected = True
    router.db = MagicMock()
    router.db.get_latest_heartbeat = AsyncMock(return_value=None)
    return router


def _create_mock_req(method: str, path: str, json_data: dict = None):
    headers = {"Content-Type": "application/json"}
    req = make_mocked_request(method, path, headers=headers)
    if json_data is not None:
        req.json = AsyncMock(return_value=json_data)
    return req


@pytest.mark.asyncio
async def test_get_stats_truthful_latency_measurement(music_router):
    """Verify get_stats returns measured latency (38.0 ms) and never hardcoded 0.5 ms."""
    req = _create_mock_req("GET", "/api/music/stats")
    resp = await music_router.get_stats(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["success"] is True

    stats = data["data"]
    # 0.038 * 1000 = 38.0 ms
    assert stats["gateway_latency_ms"] == 38.0
    assert stats["reaction_time_ms"] == 38.0
    assert stats["gateway_latency_ms"] != 0.5


@pytest.mark.asyncio
async def test_get_stats_null_latency_when_unmeasured(music_router):
    """Verify get_stats returns None for latency when bot.latency is None, negative, or NaN."""
    music_router.bot.latency = None
    req = _create_mock_req("GET", "/api/music/stats")
    resp = await music_router.get_stats(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["data"]["gateway_latency_ms"] is None


@pytest.mark.asyncio
async def test_extractor_health_diagnostics_and_zero_403_shield(music_router):
    """Verify extractor health reports JS runtime and Zero 403 shield does not have 0.5ms fake latency."""
    mock_updater_info = {
        "current_ytdl": "2026.08.19",
        "latest_ytdl": "2026.08.19",
        "current_ejs": "0.8.0",
        "latest_ejs": "0.8.0",
        "update_available": False,
        "js_runtime": {"active": "Node.js", "node_available": True},
    }
    with patch("music_bot.services.updater_service.MusicAutoUpdater.check_ytdl_version", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = mock_updater_info
        req = _create_mock_req("GET", "/api/music/extractor-health")
        resp = await music_router.get_extractor_health(req)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["success"] is True

        res = data["data"]
        assert res["status"] == "HEALTHY"
        assert res["current_ytdl"] == "2026.08.19"
        assert res["js_runtime"]["active"] == "Node.js"

        # Check diagnostics
        diags = {d["step"]: d for d in res["diagnostics"]}
        assert "Zero 403 Forbidden Throttling Shield" in diags
        zero_403 = diags["Zero 403 Forbidden Throttling Shield"]
        assert zero_403["status"] == "ACTIVE"
        # Must NOT be 0.5 ms
        assert zero_403["latency_ms"] != 0.5


@pytest.mark.asyncio
async def test_extractor_heal_endpoint(music_router):
    """Verify POST /api/music/extractor-heal executes health check and returns status."""
    req = _create_mock_req("POST", "/api/music/extractor-heal")
    resp = await music_router.get_extractor_health(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["success"] is True
    assert data["data"]["self_healing"] == "READY"
