"""
Integration and Unit Tests for Discord OAuth2 Login Flow and Button Action Handlers.
Validates:
- OAuth2 login redirect (/api/auth/login, /login)
- OAuth2 authorization URL endpoint (/api/auth/url)
- OAuth2 CSRF state verification & mismatch rejection
- OAuth2 access_denied / error callback handling
- OAuth2 successful code exchange and session cookie issuance
- Logout endpoints (/api/auth/logout, /logout)
- Button action dispatching (ENQUEUE, STOP, CLEAR, etc.)
- Server-side guild authorization validation
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from web.server import RaiCommunityOSServer
from web.auth import AuthManager
from music_bot.services.session_service import GuildMusicSession, PlaybackState, SessionManager
from music_bot.database.models import QueuedTrack


def make_track(title: str = "Test Song", duration: int = 180) -> QueuedTrack:
    return QueuedTrack(
        title=title,
        url="https://youtube.com/watch?v=mocktrack",
        stream_url="https://mock.stream/audio.mp3",
        duration=duration,
        artist="Test Artist",
        thumbnail="https://mock.thumb/art.jpg",
        requester_id=1457382179981099090,
        requester_name="RaiTester",
    )


class TestDiscordOAuthAndButtonActions(AioHTTPTestCase):
    """Comprehensive test suite for OAuth2 login, callbacks, and button control actions."""

    async def get_application(self) -> web.Application:
        self.mock_db = MagicMock()
        self.mock_db.is_connected = True
        self.mock_db.connect = AsyncMock()
        self.mock_db.close = AsyncMock()
        self.mock_db.fetch_pending_sync_events = AsyncMock(return_value=[])
        self.mock_db.submit_web_action = AsyncMock(return_value=101)
        self.mock_db.mark_web_action_completed = AsyncMock()
        self.mock_db.delete_session = AsyncMock()
        self.mock_db.get_session = AsyncMock(return_value=None)
        self.mock_db.create_session = AsyncMock()

        self.mock_bot = MagicMock()
        self.mock_bot.db = self.mock_db
        self.mock_bot.latency = 0.015

        mock_guild = MagicMock()
        mock_guild.id = 1525030316845301781
        mock_guild.name = "THOR APEX ⚡"
        mock_member = MagicMock()
        mock_member.id = 1457382179981099090
        mock_guild.get_member.return_value = mock_member
        self.mock_bot.get_guild.return_value = mock_guild
        self.mock_bot.guilds = [mock_guild]

        self.rai_server = RaiCommunityOSServer(bot=self.mock_bot, db=self.mock_db, port=8198)
        self.rai_server.api_router.auth._client_id = "mock_client_id_for_testing"
        self.rai_server.api_router.auth._client_secret = "mock_client_secret_for_testing"
        app = web.Application()
        self.rai_server.setup_routes(app)

        self.auth_session_id = await self.rai_server.api_router.auth.create_session_for_user(
            discord_user={"id": "1457380609641938981", "username": "MusicTester"},
            is_admin_override=True,
            user_guilds=[{"id": "1525030316845301781", "name": "THOR APEX ⚡"}],
        )
        self.auth_cookies = {"rai_session": self.auth_session_id}
        return app

    async def test_01_auth_login_redirect(self):
        """1. GET /api/auth/login responds with HTTP 302 redirect to Discord OAuth authorize endpoint."""
        resp = await self.client.get("/api/auth/login", allow_redirects=False)
        assert resp.status == 302
        location = resp.headers.get("Location", "")
        assert "discord.com/oauth2/authorize" in location or "discord.com/api/oauth2/authorize" in location
        assert "client_id=" in location
        assert "response_type=code" in location
        assert "state=" in location
        assert "oauth_state" in resp.cookies

    async def test_02_auth_url_json_endpoint(self):
        """2. GET /api/auth/url returns JSON with authorization URL and sets oauth_state cookie."""
        resp = await self.client.get("/api/auth/url")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert "url" in data["data"]
        assert "client_id=" in data["data"]["url"]
        assert "oauth_state" in resp.cookies

    async def test_03_auth_callback_csrf_mismatch(self):
        """3. GET /api/auth/callback with mismatched state redirects with error=csrf_validation_failed."""
        # Set state cookie to 'valid_secret' but pass query param state='attacker_state'
        self.client.session.cookie_jar.update_cookies({"oauth_state": "valid_secret"})
        resp = await self.client.get("/api/auth/callback?code=mock_code&state=attacker_state", allow_redirects=False)
        assert resp.status == 302
        assert "error=csrf_validation_failed" in resp.headers.get("Location", "")

    async def test_04_auth_callback_access_denied(self):
        """4. GET /api/auth/callback when user cancels OAuth redirects with error=access_denied."""
        resp = await self.client.get("/api/auth/callback?error=access_denied&error_description=The+user+denied", allow_redirects=False)
        assert resp.status == 302
        assert "error=access_denied" in resp.headers.get("Location", "")

    async def test_05_auth_callback_success(self):
        """5. GET /api/auth/callback with valid state and code exchanges token and logs user in."""
        test_state = "expected_csrf_token_123"
        self.client.session.cookie_jar.update_cookies({"oauth_state": test_state})

        mock_token_resp = {
            "access_token": "mock_access_token_xyz",
            "token_type": "Bearer",
            "expires_in": 604800,
            "refresh_token": "mock_refresh_token",
            "scope": "identify guilds",
        }
        mock_user_resp = {
            "id": "1457382179981099090",
            "username": "KishoreRai",
            "discriminator": "0",
            "avatar": "mockavatarhash",
        }
        mock_guilds_resp = [
            {"id": "1525030316845301781", "name": "THOR APEX ⚡", "permissions": "8"}
        ]

        self.mock_db.create_web_session = AsyncMock(return_value="test_session_token_123")
        with patch.object(self.rai_server.api_router.auth, "exchange_code", AsyncMock(return_value=mock_token_resp)), \
             patch.object(self.rai_server.api_router.auth, "fetch_discord_user", AsyncMock(return_value=mock_user_resp)), \
             patch.object(self.rai_server.api_router.auth, "fetch_discord_guilds", AsyncMock(return_value=mock_guilds_resp)):
            resp = await self.client.get(f"/api/auth/callback?code=valid_code&state={test_state}", allow_redirects=False)
            assert resp.status == 302
            assert resp.headers.get("Location", "") == "/dashboard?auth=success"
            assert "rai_session" in resp.cookies

    async def test_06_auth_logout(self):
        """6. POST /api/auth/logout clears session cookie and responds successfully."""
        resp = await self.client.post("/api/auth/logout")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True

    async def test_07_enqueue_button_action(self):
        """7. POST /api/music/control with ENQUEUE action resolves and enqueues a track."""
        sm = SessionManager.get_instance()
        session = sm.get_session_nowait(1525030316845301781)
        if not session:
            session = GuildMusicSession(guild_id=1525030316845301781)
            sm._sessions[1525030316845301781] = session

        mock_resolved_track = make_track("Vaathi Coming - Anirudh", 230)

        with patch("music_bot.services.resolver_service.AudioResolver.resolve_track", AsyncMock(return_value=mock_resolved_track)), \
             patch("music_bot.services.player_service.MusicPlayerService.send_now_playing_panel", AsyncMock()):
            # Anonymous must return 401
            unauth_resp = await self.client.post("/api/music/control", json={
                "guild_id": 1525030316845301781,
                "action": "ENQUEUE",
                "payload": {"query": "Vaathi Coming"}
            })
            assert unauth_resp.status == 401

            # Authorized user succeeds
            resp = await self.client.post("/api/music/control", json={
                "guild_id": 1525030316845301781,
                "action": "ENQUEUE",
                "payload": {"query": "Vaathi Coming"}
            }, cookies=self.auth_cookies)
            assert resp.status == 200
            data = await resp.json()
            assert data["success"] is True
            assert any(t.title == "Vaathi Coming - Anirudh" for t in session.queue)

    async def test_08_stop_and_clear_button_actions(self):
        """8. POST /api/music/control with STOP and CLEAR actions updates session state."""
        sm = SessionManager.get_instance()
        session = sm.get_session_nowait(1525030316845301781)
        session.queue.append(make_track("Song 1", 100))
        session.queue.append(make_track("Song 2", 120))
        assert len(session.queue) >= 2

        with patch("music_bot.services.player_service.MusicPlayerService.stop", AsyncMock(return_value=(True, "Stopped"))), \
             patch("music_bot.services.player_service.MusicPlayerService.send_now_playing_panel", AsyncMock()):
            # Test CLEAR
            resp = await self.client.post("/api/music/control", json={
                "guild_id": 1525030316845301781,
                "action": "CLEAR"
            }, cookies=self.auth_cookies)
            assert resp.status == 200
            assert len(session.queue) == 0

            # Test STOP
            resp2 = await self.client.post("/api/music/control", json={
                "guild_id": 1525030316845301781,
                "action": "STOP"
            }, cookies=self.auth_cookies)
            assert resp2.status == 200
            data2 = await resp2.json()
            assert data2["success"] is True

    async def test_09_unauthorized_guild_access(self):
        """9. Control request for a guild where user is NOT a member returns 403 UNAUTHORIZED_GUILD."""
        # Guild 999999999 is not in user's guilds and bot get_guild member is None
        mock_stranger_guild = MagicMock()
        mock_stranger_guild.get_member.return_value = None
        self.mock_bot.get_guild.side_effect = lambda gid: mock_stranger_guild if gid == 999999999 else MagicMock()

        # Mock authenticated user who is NOT an admin and does NOT belong to guild 999999999
        with patch.object(self.rai_server.music_router, "_get_current_user", AsyncMock(return_value={
            "user_id": 123456789,
            "username": "UnauthorizedUser",
            "is_admin": False,
            "guilds": [{"id": "1525030316845301781", "name": "THOR APEX"}]
        })):
            resp = await self.client.post("/api/music/control", json={
                "guild_id": 999999999,
                "action": "SKIP"
            })
            assert resp.status == 403
            data = await resp.json()
            assert data["success"] is False
            assert data["error"]["code"] == "UNAUTHORIZED_GUILD"

    async def test_10_auth_callback_missing_code(self):
        """10. GET /api/auth/callback without authorization code redirects with error=missing_code."""
        resp = await self.client.get("/api/auth/callback", allow_redirects=False)
        assert resp.status == 302
        assert "error=missing_code" in resp.headers.get("Location", "")

    async def test_11_auth_callback_exchange_failure(self):
        """11. GET /api/auth/callback when code exchange fails redirects with error=oauth_exchange_failed."""
        test_state = "csrf_state_for_exchange_fail"
        self.client.session.cookie_jar.update_cookies({"oauth_state": test_state})
        with patch.object(self.rai_server.api_router.auth, "exchange_code", AsyncMock(return_value=None)):
            resp = await self.client.get(f"/api/auth/callback?code=bad_code&state={test_state}", allow_redirects=False)
            assert resp.status == 302
            assert "error=oauth_exchange_failed" in resp.headers.get("Location", "")

    async def test_12_auth_callback_user_fetch_failure(self):
        """12. GET /api/auth/callback when user fetch fails redirects with error=failed_to_fetch_user."""
        test_state = "csrf_state_for_user_fail"
        self.client.session.cookie_jar.update_cookies({"oauth_state": test_state})
        with patch.object(self.rai_server.api_router.auth, "exchange_code", AsyncMock(return_value={"access_token": "valid_token"})), \
             patch.object(self.rai_server.api_router.auth, "fetch_discord_user", AsyncMock(return_value=None)):
            resp = await self.client.get(f"/api/auth/callback?code=any_code&state={test_state}", allow_redirects=False)
            assert resp.status == 302
            assert "error=failed_to_fetch_user" in resp.headers.get("Location", "")

    async def test_13_auth_callback_server_exception_graceful_redirect(self):
        """13. GET /api/auth/callback does NOT return HTTP 500 when unexpected error occurs; redirects gracefully."""
        test_state = "csrf_state_for_err"
        self.client.session.cookie_jar.update_cookies({"oauth_state": test_state})
        with patch.object(self.rai_server.api_router.auth, "exchange_code", AsyncMock(side_effect=RuntimeError("Database failure"))):
            resp = await self.client.get(f"/api/auth/callback?code=crash_code&state={test_state}", allow_redirects=False)
            assert resp.status == 302
            assert "error=server_error" in resp.headers.get("Location", "")

    async def test_14_music_database_native_web_session_crud(self):
        """14. Verify MusicDatabase natively supports create_web_session, get_web_session, and delete_web_session."""
        from music_bot.database.db import MusicDatabase
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_music.db"
            music_db = MusicDatabase(db_path)
            await music_db.connect()
            assert music_db.is_connected is True

            # Create session
            session_id = "test_music_session_xyz"
            await music_db.create_web_session(
                session_id=session_id,
                user_id=1457382179981099090,
                discord_user_id=1457382179981099090,
                username="TestUser",
                user_data_dict={"username": "TestUser", "is_admin": True},
            )

            # Get session
            saved = await music_db.get_web_session(session_id)
            assert saved is not None
            assert saved["session_id"] == session_id
            assert saved["username"] == "TestUser"
            assert saved["user_data"]["is_admin"] is True

            # Delete session
            deleted = await music_db.delete_web_session(session_id)
            assert deleted is True
            assert await music_db.get_web_session(session_id) is None
            await music_db.close()

    async def test_15_auth_url_redirect_uri_matches_registered_https_callback(self):
        """15. Generated Discord OAuth authorization URL contains properly URL-encoded /api/auth/callback."""
        with patch.dict(os.environ, {"RENDER_EXTERNAL_URL": "https://rai-discord-bot.onrender.com"}):
            auth_mgr = self.rai_server.api_router.auth
            oauth_url = auth_mgr.get_oauth_url(state="test_state_123")
            assert "discord.com/oauth2/authorize" in oauth_url
            assert "redirect_uri=https%3A%2F%2Frai-discord-bot.onrender.com%2Fapi%2Fauth%2Fcallback" in oauth_url
            assert "response_type=code" in oauth_url
            assert "state=test_state_123" in oauth_url

    async def test_16_discord_redirect_uri_legacy_route_normalization(self):
        """16. If DISCORD_REDIRECT_URI contains legacy /auth/discord/callback, normalize to /api/auth/callback."""
        with patch.dict(os.environ, {"DISCORD_REDIRECT_URI": "https://rai-discord-bot.onrender.com/auth/discord/callback"}):
            auth_mgr = self.rai_server.api_router.auth
            resolved = auth_mgr.get_redirect_uri()
            assert resolved == "https://rai-discord-bot.onrender.com/api/auth/callback"
            oauth_url = auth_mgr.get_oauth_url(state="test_state_456")
            assert "redirect_uri=https%3A%2F%2Frai-discord-bot.onrender.com%2Fapi%2Fauth%2Fcallback" in oauth_url

    async def test_17_auth_callback_missing_state_when_cookie_present(self):
        """17. GET /api/auth/callback with cookie state but missing query state redirects with error=csrf_validation_failed."""
        self.client.session.cookie_jar.update_cookies({"oauth_state": "expected_secret_csrf"})
        resp = await self.client.get("/api/auth/callback?code=mock_code", allow_redirects=False)
        assert resp.status == 302
        assert "error=csrf_validation_failed" in resp.headers.get("Location", "")
