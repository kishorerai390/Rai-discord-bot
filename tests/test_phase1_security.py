"""
Phase 1 Security & Authentication Hardening Test Suite for MusicMaid.

Tests:
1. Anonymous playback-control request is rejected (401).
2. Anonymous favorite and private-playlist requests cannot access another user's data (401).
3. An authenticated user without access to a guild cannot control that guild (403).
4. Authorized users can still use permitted playback controls (200).
5. Owner-only endpoints reject ordinary users (403).
6. OAuth state validation, session expiry, and logout work correctly.
7. Realtime connections reject unauthorized access (401).
8. User-owned data (e.g. passport) rejects unauthenticated requests without founder fallback.
"""

import asyncio
import os
import unittest
from aiohttp.test_utils import TestClient, TestServer
from aiohttp import web

from web.server import RaiCommunityOSServer
from music_bot.database.db import MusicDatabase
from music_bot.config import BOT_OWNER_ID


class TestPhase1SecurityHardening(unittest.IsolatedAsyncioTestCase):
    """Test suite validating Phase 1 Security Hardening requirements."""

    async def asyncSetUp(self):
        self.db = MusicDatabase()
        await self.db.connect()

        self.server = RaiCommunityOSServer(bot=None, db=self.db, port=8993)
        app = web.Application()
        self.server.setup_routes(app)

        self.test_server = TestServer(app)
        self.client = TestClient(self.test_server)
        await self.client.start_server()

        # Helper: Create an ordinary user session
        self.ordinary_user = {
            "id": "777888999111222",
            "username": "OrdinaryListener",
            "global_name": "Ordinary Listener",
            "guilds": [{"id": "1525030316845301781", "name": "Permitted Guild"}],
        }
        self.ordinary_session_id = await self.server.api_router.auth.create_session_for_user(
            discord_user=self.ordinary_user,
            is_admin_override=False,
            user_guilds=self.ordinary_user["guilds"],
        )
        self.ordinary_cookies = {"rai_session": self.ordinary_session_id}

        # Helper: Create a user with NO guilds
        self.guildless_user = {
            "id": "333444555666777",
            "username": "GuildlessVisitor",
            "global_name": "Guildless Visitor",
            "guilds": [],
        }
        self.guildless_session_id = await self.server.api_router.auth.create_session_for_user(
            discord_user=self.guildless_user,
            is_admin_override=False,
            user_guilds=[],
        )
        self.guildless_cookies = {"rai_session": self.guildless_session_id}

        # Helper: Create a verified Bot Owner session
        self.owner_user = {
            "id": str(BOT_OWNER_ID),
            "username": "MusicMaidCreator",
            "global_name": "Bot Creator",
            "guilds": [],
        }
        self.owner_session_id = await self.server.api_router.auth.create_session_for_user(
            discord_user=self.owner_user,
            is_admin_override=True,
            user_guilds=[],
        )
        self.owner_cookies = {"rai_session": self.owner_session_id}

    async def asyncTearDown(self):
        await self.client.close()
        await self.db.close()

    # =========================================================================
    # 1. ANONYMOUS PLAYBACK-CONTROL REQUEST IS REJECTED (401)
    # =========================================================================
    async def test_01_anonymous_playback_control_rejected(self):
        """Verify anonymous POST /api/music/control and /api/music/enqueue are rejected with 401."""
        ctrl_payload = {
            "guild_id": 1525030316845301781,
            "action": "VOLUME",
            "payload": {"volume": 75},
        }
        resp = await self.client.post("/api/music/control", json=ctrl_payload)
        self.assertEqual(resp.status, 401, "Anonymous control request must return 401 Unauthorized")
        data = await resp.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

        enqueue_payload = {
            "guild_id": 1525030316845301781,
            "query": "Test Song",
        }
        resp_enq = await self.client.post("/api/music/enqueue", json=enqueue_payload)
        self.assertEqual(resp_enq.status, 401, "Anonymous enqueue request must return 401 Unauthorized")

        # Sleep timer must also be rejected
        sleep_payload = {"guild_id": 1525030316845301781, "minutes": 15}
        resp_sleep = await self.client.post("/api/music/sleep-timer", json=sleep_payload)
        self.assertEqual(resp_sleep.status, 401, "Anonymous sleep-timer request must return 401 Unauthorized")

    # =========================================================================
    # 2. ANONYMOUS FAVORITE & PLAYLIST REQUESTS REJECTED (401)
    # =========================================================================
    async def test_02_anonymous_favorites_and_playlists_cannot_access_data(self):
        """Verify anonymous requests to favorites and playlists are rejected with 401."""
        resp_favs = await self.client.get("/api/music/favorites")
        self.assertEqual(resp_favs.status, 401, "Anonymous GET favorites must return 401 Unauthorized")

        resp_toggle = await self.client.post("/api/music/favorites/toggle", json={"title": "Song", "url": "https://yt.com/1"})
        self.assertEqual(resp_toggle.status, 401, "Anonymous toggle favorite must return 401 Unauthorized")

        resp_pl = await self.client.get("/api/music/playlists?guild_id=1525030316845301781")
        self.assertEqual(resp_pl.status, 401, "Anonymous GET playlists must return 401 Unauthorized")

        resp_save = await self.client.post("/api/music/playlists/save", json={"guild_id": 1525030316845301781, "name": "Vibes"})
        self.assertEqual(resp_save.status, 401, "Anonymous save playlist must return 401 Unauthorized")

    # =========================================================================
    # 3. AUTHENTICATED USER WITHOUT GUILD ACCESS CANNOT CONTROL THAT GUILD (403)
    # =========================================================================
    async def test_03_authenticated_user_without_guild_access_rejected(self):
        """Verify authenticated user without membership in target guild receives 403 Forbidden."""
        unauthorized_guild_id = 999111222333444  # User has no membership in this guild
        payload = {
            "guild_id": unauthorized_guild_id,
            "action": "VOLUME",
            "payload": {"volume": 70},
        }
        resp = await self.client.post("/api/music/control", json=payload, cookies=self.guildless_cookies)
        self.assertEqual(resp.status, 403, "User without guild access must receive 403 Forbidden")
        data = await resp.json()
        self.assertFalse(data["success"])
        self.assertIn(data["error"]["code"], ["FORBIDDEN", "UNAUTHORIZED_GUILD"])

    # =========================================================================
    # 4. AUTHORIZED USERS CAN STILL USE PERMITTED PLAYBACK CONTROLS (200)
    # =========================================================================
    async def test_04_authorized_users_can_use_permitted_controls(self):
        """Verify authorized user with guild membership can submit playback actions (200 OK)."""
        payload = {
            "guild_id": 1525030316845301781,  # ordinary_user has this guild in their mutual guilds list
            "action": "VOLUME",
            "payload": {"volume": 65},
        }
        resp = await self.client.post("/api/music/control", json=payload, cookies=self.ordinary_cookies)
        self.assertEqual(resp.status, 200, "Authorized user control action must return 200 OK")
        data = await resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["action"], "VOLUME")

    # =========================================================================
    # 5. OWNER-ONLY ENDPOINTS REJECT ORDINARY USERS (403)
    # =========================================================================
    async def test_05_owner_only_endpoints_reject_ordinary_users(self):
        """Verify creator control endpoints reject ordinary users with 403 Forbidden."""
        owner_endpoints = [
            "/api/owner/overview",
            "/api/owner/health",
            "/api/owner/guilds",
            "/api/owner/feature-flags",
            "/api/owner/presence",
            "/api/music/extractor-health",
        ]
        for ep in owner_endpoints:
            resp = await self.client.get(ep, cookies=self.ordinary_cookies)
            self.assertEqual(resp.status, 403, f"Ordinary user must receive 403 on owner endpoint {ep}")

        # Verify Bot Owner DOES get 200 OK
        resp_owner = await self.client.get("/api/owner/overview", cookies=self.owner_cookies)
        self.assertEqual(resp_owner.status, 200, "Bot Owner must receive 200 OK on /api/owner/overview")
        resp_ext = await self.client.get("/api/music/extractor-health", cookies=self.owner_cookies)
        self.assertEqual(resp_ext.status, 200, "Bot Owner must receive 200 OK on /api/music/extractor-health")

    # =========================================================================
    # 6. OAUTH STATE VALIDATION, SESSION EXPIRY, AND LOGOUT
    # =========================================================================
    async def test_06_oauth_state_validation_and_logout(self):
        """Verify OAuth CSRF state mismatch is rejected, and logout terminates session."""
        # A. Callback with missing or mismatched state
        resp_cb = await self.client.get("/api/auth/callback?code=mock_code&state=attack_state")
        # Should redirect to error=csrf_validation_failed
        self.assertIn("error=csrf_validation_failed", str(resp_cb.url))

        # B. User session verification on /api/auth/me
        resp_me = await self.client.get("/api/auth/me", cookies=self.ordinary_cookies)
        self.assertEqual(resp_me.status, 200)
        data_me = await resp_me.json()
        self.assertTrue(data_me["data"]["authenticated"])
        self.assertEqual(str(data_me["data"]["user"]["id"]), str(self.ordinary_user["id"]))

        # C. Logout
        resp_logout = await self.client.post("/api/auth/logout", cookies=self.ordinary_cookies)
        self.assertEqual(resp_logout.status, 200)

        # D. Verify session was deleted from database
        session_in_db = await self.db.get_web_session(self.ordinary_session_id)
        self.assertIsNone(session_in_db, "Session must be deleted from database upon logout")

    # =========================================================================
    # 7. REALTIME CONNECTIONS REJECT UNAUTHORIZED ACCESS (401)
    # =========================================================================
    async def test_07_realtime_connections_reject_unauthorized_access(self):
        """Verify unauthenticated requests to realtime SSE and WebSocket return 401."""
        resp_sse = await self.client.get("/api/realtime/stream")
        self.assertEqual(resp_sse.status, 401, "Unauthenticated SSE stream must return 401 Unauthorized")

        resp_ws = await self.client.get("/api/realtime/ws")
        self.assertEqual(resp_ws.status, 401, "Unauthenticated WebSocket must return 401 Unauthorized")

    # =========================================================================
    # 8. PASSPORT REJECTS UNAUTHENTICATED REQUESTS WITHOUT FOUNDER FALLBACK
    # =========================================================================
    async def test_08_passport_unauthenticated_rejected(self):
        """Verify unauthenticated GET /api/passport returns 401 instead of defaulting to founder ID."""
        resp_passport = await self.client.get("/api/passport")
        self.assertEqual(resp_passport.status, 401, "Unauthenticated passport access must return 401 Unauthorized")
        data = await resp_passport.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    # =========================================================================
    # 9. LOGOUT INVALIDATES MEMORY SESSIONS & REJECTS BEARER ACCESS
    # =========================================================================
    async def test_09_logout_invalidates_memory_and_db_and_bearer_rejected(self):
        """Verify logout removes token from _memory_sessions and rejects subsequent Bearer/Cookie requests."""
        test_user = {
            "id": "555666777888999",
            "username": "LogoutTestUser",
            "guilds": [],
        }
        test_session_id = await self.server.api_router.auth.create_session_for_user(
            discord_user=test_user,
            is_admin_override=False,
            user_guilds=[],
        )

        # 1. Confirm session exists in memory cache and database
        self.assertIn(test_session_id, self.server.api_router.auth._memory_sessions)
        db_record = await self.db.get_web_session(test_session_id)
        self.assertIsNotNone(db_record)

        # 2. Logout using Authorization Bearer header
        resp_logout = await self.client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {test_session_id}"},
        )
        self.assertEqual(resp_logout.status, 200)
        logout_data = await resp_logout.json()
        self.assertTrue(logout_data.get("data", {}).get("logged_out"))

        # 3. Verify session was removed from _memory_sessions and DB
        self.assertNotIn(test_session_id, self.server.api_router.auth._memory_sessions)
        session_in_db = await self.db.get_web_session(test_session_id)
        self.assertIsNone(session_in_db)

        # 4. Verify token is unauthenticated on /api/auth/me via Bearer header
        resp_me_bearer = await self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {test_session_id}"},
        )
        self.assertEqual(resp_me_bearer.status, 200)
        data_bearer = await resp_me_bearer.json()
        self.assertFalse(data_bearer["data"]["authenticated"])

        # 5. Verify token is also unauthenticated via Cookie
        resp_me_cookie = await self.client.get(
            "/api/auth/me",
            cookies={"rai_session": test_session_id},
        )
        self.assertEqual(resp_me_cookie.status, 200)
        data_cookie = await resp_me_cookie.json()
        self.assertFalse(data_cookie["data"]["authenticated"])

        # 6. Verify protected endpoint strictly rejects the invalidated token with 401
        resp_passport = await self.client.get(
            "/api/passport",
            headers={"Authorization": f"Bearer {test_session_id}"},
        )
        self.assertEqual(resp_passport.status, 401)

    # =========================================================================
    # 10. REPEATED LOGOUT IS HANDLED SAFELY
    # =========================================================================
    async def test_10_repeated_logout_handled_safely(self):
        """Verify repeated logout calls with already-invalidated or non-existent tokens succeed safely."""
        # Initial logout with invalid/random token
        resp1 = await self.client.post("/api/auth/logout", cookies={"rai_session": "non_existent_token_xyz"})
        self.assertEqual(resp1.status, 200)
        data1 = await resp1.json()
        self.assertTrue(data1.get("data", {}).get("logged_out"))

        # Repeated logout with no credentials
        resp2 = await self.client.post("/api/auth/logout")
        self.assertEqual(resp2.status, 200)
        data2 = await resp2.json()
        self.assertTrue(data2.get("data", {}).get("logged_out"))

    # =========================================================================
    # 11. DATABASE DELETION FAILURE HANDLED SAFELY WITHOUT FALSE COMPLETION
    # =========================================================================
    async def test_11_logout_database_deletion_failure_handled_safely(self):
        """Verify database deletion failure returns 500 error and does not falsely claim complete invalidation."""
        from unittest.mock import patch, AsyncMock

        test_user = {
            "id": "111222333444555",
            "username": "DbFailUser",
            "guilds": [],
        }
        test_session_id = await self.server.api_router.auth.create_session_for_user(
            discord_user=test_user,
            is_admin_override=False,
            user_guilds=[],
        )

        with patch.object(self.server.api_router.auth.db, "delete_web_session", AsyncMock(side_effect=Exception("Simulated SQLite lock error"))):
            resp = await self.client.post(
                "/api/auth/logout",
                cookies={"rai_session": test_session_id},
            )
            # Must return HTTP 500 indicating persistent invalidation failure
            self.assertEqual(resp.status, 500)
            data = await resp.json()
            self.assertFalse(data["success"])
            self.assertEqual(data["error"]["code"], "SESSION_INVALIDATION_FAILED")
            self.assertNotIn("logged_out", data.get("data", {}))

            # Verify memory session was still purged and revoked locally to protect current runtime
            self.assertNotIn(test_session_id, self.server.api_router.auth._memory_sessions)
            resp_check = await self.client.get(
                "/api/auth/me",
                cookies={"rai_session": test_session_id},
            )
            self.assertEqual(resp_check.status, 200)
            data_check = await resp_check.json()
            self.assertFalse(data_check["data"]["authenticated"])

            # Verify protected endpoint rejects the revoked session with 401
            resp_passport = await self.client.get(
                "/api/passport",
                cookies={"rai_session": test_session_id},
            )
            self.assertEqual(resp_passport.status, 401)

    # =========================================================================
    # 12. REVOCATION STORAGE IS NOT POLLUTED BY RANDOM OR SUCCESSFUL LOGOUTS
    # =========================================================================
    async def test_12_revocation_storage_not_polluted_by_random_or_successful_logouts(self):
        """Verify _revoked_sessions stays clean: neither random strings nor successful logouts bloat memory."""
        auth_mgr = self.server.api_router.auth
        auth_mgr._revoked_sessions.clear()

        # A. Unauthenticated / random token logout does not pollute _revoked_sessions
        resp_fake = await self.client.post(
            "/api/auth/logout",
            headers={"Authorization": "Bearer random_unregistered_token_xyz_999"},
        )
        self.assertEqual(resp_fake.status, 200)
        self.assertEqual(len(auth_mgr._revoked_sessions), 0, "_revoked_sessions must not store random unauthenticated tokens")

        # B. Successful logout purges DB and does not leave unnecessary tombstones
        test_user = {
            "id": "999888777666555",
            "username": "CleanLogoutUser",
            "guilds": [],
        }
        test_session_id = await auth_mgr.create_session_for_user(
            discord_user=test_user,
            is_admin_override=False,
            user_guilds=[],
        )
        self.assertEqual(len(auth_mgr._revoked_sessions), 0)

        resp_logout = await self.client.post(
            "/api/auth/logout",
            cookies={"rai_session": test_session_id},
        )
        self.assertEqual(resp_logout.status, 200)
        self.assertEqual(len(auth_mgr._revoked_sessions), 0, "Successful database deletion must not bloat _revoked_sessions")

    # =========================================================================
    # 13. STALE CACHED SESSIONS CANNOT BYPASS PERSISTENT REVOCATION
    # =========================================================================
    async def test_13_stale_cached_session_cannot_bypass_persistent_revocation(self):
        """Verify that a session deleted in persistent DB cannot be authenticated via a lingering in-memory cache."""
        auth_mgr = self.server.api_router.auth
        test_user = {
            "id": "444333222111000",
            "username": "StaleCacheUser",
            "guilds": [],
        }
        test_session_id = await auth_mgr.create_session_for_user(
            discord_user=test_user,
            is_admin_override=False,
            user_guilds=[],
        )

        # Confirm session is present in both memory and SQLite
        self.assertIn(test_session_id, auth_mgr._memory_sessions)
        db_record = await self.db.get_web_session(test_session_id)
        self.assertIsNotNone(db_record)

        # Simulate another process or direct DB action deleting the session
        await self.db.delete_web_session(test_session_id)
        self.assertIsNone(await self.db.get_web_session(test_session_id))

        # Intentionally re-plant or verify stale session in memory
        self.assertIn(test_session_id, auth_mgr._memory_sessions)

        # Request protected resource; auth manager must consult DB, evict stale cache, and return 401
        resp_passport = await self.client.get(
            "/api/passport",
            cookies={"rai_session": test_session_id},
        )
        self.assertEqual(resp_passport.status, 401, "Stale in-memory session must be rejected when absent in database")
        self.assertNotIn(test_session_id, auth_mgr._memory_sessions, "Stale cache must be evicted immediately upon check")

    # =========================================================================
    # 14. REVOCATION PERSISTS ACROSS SERVER RESTARTS AND MULTIPLE INSTANCES
    # =========================================================================
    async def test_14_cross_process_and_restart_revocation_survives(self):
        """Verify that revoking a session deletes the underlying SQLite row and survives new AuthManager instances."""
        from web.auth import AuthManager

        auth_mgr = self.server.api_router.auth
        test_user = {
            "id": "123123123123123",
            "username": "RestartUser",
            "guilds": [],
        }
        test_session_id = await auth_mgr.create_session_for_user(
            discord_user=test_user,
            is_admin_override=False,
            user_guilds=[],
        )

        # Perform logout
        resp_logout = await self.client.post(
            "/api/auth/logout",
            cookies={"rai_session": test_session_id},
        )
        self.assertEqual(resp_logout.status, 200)

        # Simulate a fresh process restart: new AuthManager instance sharing the same database
        restarted_auth_mgr = AuthManager(db=self.db, bot=None)
        self.assertEqual(len(restarted_auth_mgr._memory_sessions), 0)
        self.assertEqual(len(restarted_auth_mgr._revoked_sessions), 0)

        # Verify lookup on new instance rejects the revoked session
        from aiohttp.test_utils import make_mocked_request
        mock_req = make_mocked_request("GET", "/api/auth/me", headers={"Cookie": f"rai_session={test_session_id}"})
        recovered_sess = await restarted_auth_mgr.get_session_from_request(mock_req)
        self.assertIsNone(recovered_sess, "Revoked session must remain unrecoverable across process restarts")


if __name__ == "__main__":
    unittest.main()
