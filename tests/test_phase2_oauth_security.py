"""
MusicMaid Phase 2 — OAuth & Session Security Comprehensive Test Suite
Validates OAuth state entropy, CSRF defenses, session lifecycle, token leakage prevention,
CORS credential compliance, realtime stream authentication, and fail-closed security.
All external Discord OAuth network calls are strictly mocked in-process.
"""

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from web.server import RaiCommunityOSServer
from web.auth import AuthManager, SESSION_COOKIE_NAME
from music_bot.database.db import MusicDatabase


class TestPhase2OAuthSecuritySuite(AioHTTPTestCase):

    async def get_application(self):
        # Configure isolated mock bot and database for in-process HTTP testing
        self.mock_bot = MagicMock()
        self.mock_bot.user.id = 1525030316845301781
        self.mock_bot.guilds = []

        import aiosqlite
        self.test_db_conn = await aiosqlite.connect(":memory:")
        await self.test_db_conn.execute("""
            CREATE TABLE IF NOT EXISTS web_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER,
                discord_user_id INTEGER,
                username TEXT,
                discriminator TEXT,
                avatar TEXT,
                access_token TEXT,
                refresh_token TEXT,
                expires_at TEXT,
                created_at TEXT,
                user_data TEXT
            );
        """)
        await self.test_db_conn.commit()

        self.mock_db = MagicMock()
        self.mock_db.is_connected = True
        self.mock_db._db = self.test_db_conn

        async def _create_session(**kwargs):
            await self.test_db_conn.execute("""
                INSERT OR REPLACE INTO web_sessions
                (session_id, user_id, discord_user_id, username, discriminator, avatar, access_token, refresh_token, expires_at, created_at, user_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
            """, (
                kwargs.get("session_id"),
                kwargs.get("user_id", 12345),
                kwargs.get("discord_user_id", 12345),
                kwargs.get("username", "TestUser"),
                kwargs.get("discriminator", "0001"),
                kwargs.get("avatar", ""),
                kwargs.get("access_token", "mock_tok"),
                kwargs.get("refresh_token", "mock_ref"),
                kwargs.get("expires_at", "2099-01-01T00:00:00Z"),
                "{}",
            ))
            await self.test_db_conn.commit()
            return True

        async def _get_session(session_id):
            async with self.test_db_conn.execute("SELECT * FROM web_sessions WHERE session_id = ?", (session_id,)) as cur:
                row = await cur.fetchone()
                if row:
                    return {
                        "session_id": row[0],
                        "user_id": row[1],
                        "discord_user_id": row[2],
                        "username": row[3],
                        "discriminator": row[4],
                        "avatar": row[5],
                        "expires_at": row[8],
                        "user_data": {},
                    }
            return None

        async def _delete_session(session_id):
            await self.test_db_conn.execute("DELETE FROM web_sessions WHERE session_id = ?", (session_id,))
            await self.test_db_conn.commit()
            return True

        self.mock_db.create_web_session = AsyncMock(side_effect=_create_session)
        self.mock_db.get_web_session = AsyncMock(side_effect=_get_session)
        self.mock_db.delete_web_session = AsyncMock(side_effect=_delete_session)

        self.rai_server = RaiCommunityOSServer(bot=self.mock_bot, db=self.mock_db, port=8197)
        app = web.Application()
        self.rai_server.setup_routes(app)
        return app

    async def asyncTearDown(self):
        if hasattr(self, "test_db_conn") and self.test_db_conn:
            await self.test_db_conn.close()
        await super().asyncTearDown()

    # 1. OAuth State & CSRF Protection
    async def test_01_oauth_login_sets_secure_state_cookie(self):
        with patch.object(self.rai_server.api_router.auth, "_client_id", "mock_client_id"), \
             patch.object(self.rai_server.api_router.auth, "_client_secret", "mock_secret"):
            resp = await self.client.get("/api/auth/login", allow_redirects=False)
            self.assertEqual(resp.status, 302)
            self.assertIn("oauth_state", resp.cookies)
            state_cookie = resp.cookies["oauth_state"]
            self.assertTrue(state_cookie["httponly"])
            self.assertEqual(state_cookie["samesite"], "Lax")
            loc = resp.headers.get("Location", "")
            self.assertIn("discord.com/oauth2/authorize", loc)
            self.assertIn(f"state={state_cookie.value}", loc)

    async def test_02_oauth_callback_rejects_missing_or_mismatched_state(self):
        # Missing state cookie
        resp = await self.client.get("/api/auth/callback?code=mock_code&state=forged_state", allow_redirects=False)
        self.assertEqual(resp.status, 302)
        self.assertIn("error=csrf_validation_failed", resp.headers.get("Location", ""))

        # Mismatched state
        self.client.session.cookie_jar.update_cookies({"oauth_state": "legitimate_state"})
        resp = await self.client.get("/api/auth/callback?code=mock_code&state=different_state", allow_redirects=False)
        self.assertEqual(resp.status, 302)
        self.assertIn("error=csrf_validation_failed", resp.headers.get("Location", ""))

    # 2. Token Leakage Prevention
    async def test_03_oauth_callback_success_does_not_leak_token_in_url(self):
        state = "valid_state_123"
        self.client.session.cookie_jar.update_cookies({"oauth_state": state})

        with patch.object(self.rai_server.api_router.auth, "exchange_code", AsyncMock(return_value={"access_token": "mock_at", "expires_in": 3600})), \
             patch.object(self.rai_server.api_router.auth, "fetch_discord_user", AsyncMock(return_value={"id": "999999999", "username": "Tester"})), \
             patch.object(self.rai_server.api_router.auth, "fetch_discord_guilds", AsyncMock(return_value=[])):

            resp = await self.client.get(f"/api/auth/callback?code=mock_code&state={state}", allow_redirects=False)
            self.assertEqual(resp.status, 302)
            loc = resp.headers.get("Location", "")
            self.assertIn("/?auth=success", loc)
            # CRITICAL: Verify session token is NOT leaked in the URL query string
            self.assertNotIn("token=", loc)
            # Verify session cookie was safely issued
            self.assertIn(SESSION_COOKIE_NAME, resp.cookies)
            self.assertTrue(resp.cookies[SESSION_COOKIE_NAME]["httponly"])

    # 3. Missing Credentials Fail-Closed
    async def test_04_missing_oauth_credentials_fail_closed(self):
        with patch.object(type(self.rai_server.api_router.auth), "is_configured", False):
            resp = await self.client.get("/api/auth/login", allow_redirects=False)
            self.assertEqual(resp.status, 302)
            self.assertIn("error=oauth_not_configured", resp.headers.get("Location", ""))

    # 4. Dev Login Blocked in Production
    async def test_05_dev_login_blocked_in_production(self):
        with patch.dict(os.environ, {"RENDER": "true", "ALLOW_DEV_LOGIN": "true"}):
            resp = await self.client.post("/api/auth/dev-login", json={"user_id": 12345})
            self.assertEqual(resp.status, 403)
            data = await resp.json()
            self.assertEqual(data["error"]["code"], "FORBIDDEN")

    # 5. Session Invalidation & Re-use Prevention
    async def test_06_logout_invalidates_session_and_clears_cookie(self):
        sess_id = "test_active_sess_999"
        await self.mock_db.create_web_session(session_id=sess_id, user_id=12345)

        # Confirm valid session access
        self.client.session.cookie_jar.update_cookies({SESSION_COOKIE_NAME: sess_id})
        resp = await self.client.get("/api/auth/me")
        data = await resp.json()
        self.assertTrue(data["data"]["authenticated"])

        # Execute logout
        logout_resp = await self.client.post("/api/auth/logout")
        self.assertEqual(logout_resp.status, 200)

        # Attempt to reuse the same session token
        self.client.session.cookie_jar.update_cookies({SESSION_COOKIE_NAME: sess_id})
        resp_after = await self.client.get("/api/auth/me")
        data_after = await resp_after.json()
        self.assertFalse(data_after["data"]["authenticated"])

    # 6. Realtime Endpoints Require Authentication
    async def test_07_realtime_stream_and_ws_require_auth(self):
        # SSE stream without session
        resp_sse = await self.client.get("/api/realtime/stream")
        self.assertEqual(resp_sse.status, 401)

        # WS without session
        resp_ws = await self.client.get("/api/realtime/ws")
        self.assertEqual(resp_ws.status, 401)

    # 7. Database Lookup Failure Fails Closed
    async def test_08_database_lookup_failure_fails_closed(self):
        sess_id = "test_failing_sess_001"
        self.mock_db.get_web_session.side_effect = RuntimeError("Simulated SQLite failure")

        self.client.session.cookie_jar.update_cookies({SESSION_COOKIE_NAME: sess_id})
        resp = await self.client.get("/api/auth/me")
        data = await resp.json()
        self.assertFalse(data["data"]["authenticated"])

    # 8. CORS Compliant Origin Reflection
    async def test_09_cors_origin_reflection_for_trusted_origins(self):
        trusted_origin = "http://localhost:8180"
        resp = await self.client.get("/api/health", headers={"Origin": trusted_origin})
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), trusted_origin)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Credentials"), "true")

        # Untrusted origin does not receive credential authorization
        untrusted_origin = "https://malicious-site.example"
        resp_untrusted = await self.client.get("/api/health", headers={"Origin": untrusted_origin})
        self.assertEqual(resp_untrusted.headers.get("Access-Control-Allow-Origin"), "*")
        self.assertIsNone(resp_untrusted.headers.get("Access-Control-Allow-Credentials"))


if __name__ == "__main__":
    unittest.main()
