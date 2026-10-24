import os
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import MagicMock

from web.server import RaiCommunityOSServer
from config.settings import SUPPORT_INVITE_URL
from music_bot.services.resolver_service import AudioResolver


@pytest.mark.asyncio
async def test_firebase_config_support_invite_url(monkeypatch):
    monkeypatch.setenv("SUPPORT_INVITE_URL", SUPPORT_INVITE_URL)
    server = RaiCommunityOSServer(bot=MagicMock(), port=8080)
    app = web.Application()
    server.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        resp = await client.get("/api/firebase/config")
        assert resp.status == 200
        json_data = await resp.json()
        assert json_data["success"] is True
        assert json_data["data"]["supportInviteUrl"] == SUPPORT_INVITE_URL
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cors_headers_preserved_on_unauthenticated_post():
    server = RaiCommunityOSServer(bot=MagicMock(), port=8080)
    app = web.Application()
    server.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        # Preflight OPTIONS
        options_resp = await client.options(
            "/api/music/control",
            headers={"Origin": "https://rai-discord-bot.onrender.com"}
        )
        assert options_resp.status == 204
        assert options_resp.headers.get("Access-Control-Allow-Origin") == "https://rai-discord-bot.onrender.com"

        # Unauthenticated POST should return 401 with CORS headers intact
        post_resp = await client.post(
            "/api/music/control",
            headers={"Origin": "https://rai-discord-bot.onrender.com", "Content-Type": "application/json"},
            json={"guild_id": 1494692962041467005, "action": "247_TOGGLE"}
        )
        assert post_resp.status == 401
        assert post_resp.headers.get("Access-Control-Allow-Origin") == "https://rai-discord-bot.onrender.com"
        json_body = await post_resp.json()
        assert json_body["success"] is False
        assert "Sign in with Discord required" in json_body["error"]["message"]
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_YOUTUBE_TESTS") != "1",
    reason="Live YouTube extraction is an opt-in integration test; CI must not depend on external auth/rate limits.",
)
async def test_resolver_alla_bolo_query():
    track = await AudioResolver.resolve_track(
        "Ala Bolelo Jailer 2",
        requester_id=1,
        requester_name="Tester",
    )
    assert track is not None
    assert track.stream_url is not None
    assert len(track.stream_url) > 10
    assert "Ala Bolelo" in track.title
