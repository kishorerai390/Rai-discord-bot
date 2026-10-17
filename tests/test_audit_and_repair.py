"""
Automated Test Suite for Live Website Audit and Repair Verification.
Tests direct route access (including /search, /queue, /premium), OAuth configuration guards,
search fallback reliability, unified Noctyra branding, and player control actions.
Uses standard library unittest.IsolatedAsyncioTestCase for Python 3.14 stability.
"""

import os
import unittest
from unittest.mock import MagicMock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from web.server import RaiCommunityOSServer
from music_bot.config import BOT_OWNER_ID, is_bot_owner


class TestAuditAndRepairSuite(unittest.IsolatedAsyncioTestCase):
    """Integration verification suite for website audit and repairs."""

    async def asyncSetUp(self):
        mock_bot = MagicMock()
        mock_bot.is_ready.return_value = True
        mock_bot.application_id = 1457380609641938981
        mock_bot.user.id = 1457380609641938981

        self.server = RaiCommunityOSServer(bot=mock_bot)
        self.app = web.Application()
        self.server.setup_routes(self.app)

        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    # =========================================================================
    # PHASE A: ROUTING & SEARCH
    # =========================================================================

    async def test_01_search_direct_route_returns_200(self):
        """Verify direct navigation to /search does not return 404."""
        resp = await self.client.get("/search")
        self.assertEqual(resp.status, 200)
        text = await resp.text()
        self.assertIn("Noctyra Studio", text)
        self.assertIn("Search & Discover", text)

    async def test_02_queue_direct_route_returns_200(self):
        """Verify direct navigation to /queue does not return 404."""
        resp = await self.client.get("/queue")
        self.assertEqual(resp.status, 200)
        text = await resp.text()
        self.assertIn("Noctyra Studio", text)

    async def test_03_other_music_routes_return_200(self):
        """Verify /autodj, /library, /audio, /dsp, /stats, and /canvas all return 200."""
        for path in ["/autodj", "/library", "/audio", "/dsp", "/stats", "/canvas"]:
            resp = await self.client.get(path)
            self.assertEqual(resp.status, 200, f"Route {path} failed with {resp.status}")

    async def test_04_catchall_spa_route(self):
        """Verify arbitrary deep frontend paths load the SPA instead of returning 404."""
        resp = await self.client.get("/custom/deep/path")
        self.assertEqual(resp.status, 200)
        text = await resp.text()
        self.assertIn("Noctyra Studio", text)

    async def test_05_api_unknown_route_returns_404_json(self):
        """Verify non-existent API routes still return clean 404 JSON."""
        resp = await self.client.get("/api/unknown_endpoint")
        self.assertEqual(resp.status, 404)
        data = await resp.json()
        self.assertFalse(data["success"])

    async def test_06_search_empty_query(self):
        """Verify empty query returns empty list cleanly."""
        resp = await self.client.get("/api/music/search?q=")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"], [])

    async def test_07_search_normal_query(self):
        """Verify music search resolves track candidates with title and artist."""
        resp = await self.client.get("/api/music/search?q=Anirudh")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        self.assertIsInstance(data["data"], list)
        self.assertGreater(len(data["data"]), 0)
        candidate = data["data"][0]
        self.assertIn("title", candidate)
        self.assertIn("url", candidate)

    # =========================================================================
    # PHASE B: DISCORD OAUTH & DIAGNOSTICS
    # =========================================================================

    async def test_08_login_oauth_redirect_behavior(self):
        """Verify OAuth redirects to Discord when configured, and error=oauth_not_configured when unconfigured."""
        resp = await self.client.get("/api/auth/login", allow_redirects=False)
        self.assertEqual(resp.status, 302)
        location = resp.headers.get("Location", "")
        if self.server.api_router.auth.is_configured:
            self.assertIn("discord.com/oauth2/authorize", location)
            self.assertIn("client_id=", location)
        else:
            self.assertIn("error=oauth_not_configured", location)

        # Explicitly verify unconfigured behavior with mock
        original_cid = self.server.api_router.auth.client_id
        original_secret = self.server.api_router.auth.client_secret
        try:
            self.server.api_router.auth.client_id = ""
            self.server.api_router.auth.client_secret = ""
            unconf_resp = await self.client.get("/api/auth/login", allow_redirects=False)
            self.assertEqual(unconf_resp.status, 302)
            self.assertIn("error=oauth_not_configured", unconf_resp.headers.get("Location", ""))
        finally:
            self.server.api_router.auth.client_id = original_cid
            self.server.api_router.auth.client_secret = original_secret

    async def test_09_auth_url_diagnostic_response(self):
        """Verify /api/auth/url reports configured state without throwing."""
        resp = await self.client.get("/api/auth/url")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        self.assertIn("configured", data["data"])
        self.assertIn("redirect_uri", data["data"])

    async def test_10_health_includes_oauth_and_payments_diagnostics(self):
        """Verify health check includes safe diagnostic keys."""
        resp = await self.client.get("/health")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertIn("oauth", data)
        self.assertIn("configured", data["oauth"])
        self.assertIn("client_id_present", data["oauth"])
        self.assertIn("payments", data)

    # =========================================================================
    # PHASE C: PREMIUM & UNIFIED BRANDING
    # =========================================================================

    async def test_11_premium_direct_route_returns_200(self):
        """Verify direct navigation to /premium loads cleanly."""
        resp = await self.client.get("/premium")
        self.assertEqual(resp.status, 200)
        text = await resp.text()
        self.assertIn("Noctyra Premium", text)

    async def test_12_premium_plans_api(self):
        """Verify /api/premium/plans returns features, currency, and plan structure."""
        resp = await self.client.get("/api/premium/plans")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        plans_data = data["data"]
        self.assertIn("plans", plans_data)
        self.assertIn("features", plans_data)

    def test_13_creator_id_recognition(self):
        """Verify Bot Owner ID is trusted and recognized without browser trust."""
        owner_id = int(BOT_OWNER_ID or "1457380609641938981")
        self.assertTrue(is_bot_owner(owner_id))
        self.assertFalse(is_bot_owner(999999999999999999))

    async def test_14_unified_branding_in_legal_pages(self):
        """Verify Noctyra Studio branding in legal compliance pages."""
        resp = await self.client.get("/refund")
        self.assertEqual(resp.status, 200)
        text = await resp.text()
        self.assertIn("Noctyra Studio", text)
        self.assertNotIn("NyxTune", text)

    # =========================================================================
    # PHASE D: PLAYER & BACKEND ACTIONS
    # =========================================================================

    async def test_15_player_control_action_submission(self):
        """Verify music control actions submit cleanly to database."""
        resp = await self.client.post("/api/music/control", json={
            "guild_id": 1525030316845301781,
            "action": "VOLUME",
            "payload": {"volume": 90}
        })
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])

    async def test_16_player_missing_action_rejected(self):
        """Verify missing action parameter is rejected with 400."""
        resp = await self.client.post("/api/music/control", json={
            "guild_id": 1525030316845301781,
        })
        self.assertEqual(resp.status, 400)
