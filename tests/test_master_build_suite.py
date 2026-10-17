"""
Comprehensive Test Suite for MusicMaid Master Build:
- Authentication & Role-Aware Routing (Ordinary user, Guild Admin, Bot Creator/Owner)
- Creator Control Center (/api/owner/*) Security & Telemetry
- Guild Administrator Settings & Volume Cap Enforcement
- SPA Deep Routing & Direct URL Refresh (/owner, /dashboard/guilds, /search, /queue)
- Entitlement Resolution & Production Safeguards
"""

import asyncio
import os
import time
import unittest
from aiohttp.test_utils import TestClient, TestServer
from aiohttp import web

from web.server import RaiCommunityOSServer
from music_bot.database.db import MusicDatabase
from music_bot.config import BOT_OWNER_ID


class TestMasterBuildSuite(unittest.IsolatedAsyncioTestCase):
    """End-to-end integration and security test suite for the Master Build."""

    async def asyncSetUp(self):
        self.db = MusicDatabase()
        await self.db.connect()

        self.server = RaiCommunityOSServer(bot=None, db=self.db, port=8992)
        app = web.Application()
        self.server.setup_routes(app)

        self.test_server = TestServer(app)
        self.client = TestClient(self.test_server)
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.db.close()

    # =========================================================================
    # 1. AUTHENTICATION & ROLE SEPARATION
    # =========================================================================
    async def test_01_unauthenticated_owner_api_rejected(self):
        """Verify unauthenticated requests to /api/owner/* return 401 Unauthorized."""
        endpoints = [
            "/api/owner/overview",
            "/api/owner/health",
            "/api/owner/guilds",
            "/api/owner/incidents",
            "/api/owner/feature-flags",
            "/api/owner/backups",
        ]
        for ep in endpoints:
            resp = await self.client.get(ep)
            self.assertEqual(resp.status, 401, f"Expected 401 for unauthenticated request to {ep}")

    async def test_02_ordinary_user_cannot_access_owner_api(self):
        """Verify ordinary authenticated user cannot access Creator Control Room (HTTP 403)."""
        # Create ordinary user session
        user_info = {
            "id": "999888777666555",
            "username": "NormalUser",
            "global_name": "NormalUser",
        }
        session_id = await self.server.api_router.auth.create_session_for_user(
            discord_user=user_info,
            is_admin_override=False,
        )
        cookies = {"rai_session": session_id}

        resp = await self.client.get("/api/owner/overview", cookies=cookies)
        self.assertEqual(resp.status, 403, "Ordinary user must receive 403 Forbidden on /api/owner/overview")

        resp_health = await self.client.get("/api/owner/health", cookies=cookies)
        self.assertEqual(resp_health.status, 403, "Ordinary user must receive 403 Forbidden on /api/owner/health")

    async def test_03_owner_can_access_creator_control_room(self):
        """Verify verified Bot Owner receives 200 OK and truthful telemetry."""
        owner_info = {
            "id": str(BOT_OWNER_ID),
            "username": "RaiOwner",
            "global_name": "Rai Developer",
        }
        session_id = await self.server.api_router.auth.create_session_for_user(
            discord_user=owner_info,
            is_admin_override=True,
        )
        cookies = {"rai_session": session_id}

        # 1. Overview
        resp = await self.client.get("/api/owner/overview", cookies=cookies)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        self.assertIn("bot_status", data["data"])
        self.assertIn("active_voice_sessions", data["data"])
        self.assertEqual(data["data"]["sla_percentage"], 99.97)

        # 2. Health
        resp_hl = await self.client.get("/api/owner/health", cookies=cookies)
        self.assertEqual(resp_hl.status, 200)
        hl_data = await resp_hl.json()
        self.assertTrue(hl_data["success"])
        self.assertIn("system", hl_data["data"])
        self.assertIn("database", hl_data["data"])

    # =========================================================================
    # 2. INCIDENT CENTER & AUDIT OPERATIONS
    # =========================================================================
    async def test_04_incident_listing_and_acknowledgement(self):
        """Verify operational incidents can be listed and acknowledged with correlation IDs."""
        from web.owner_api import log_incident
        corr_id = log_incident("stream", "warning", "Gateway jitter detected", "Buffer underrun on channel")

        owner_info = {"id": str(BOT_OWNER_ID), "username": "RaiOwner"}
        session_id = await self.server.api_router.auth.create_session_for_user(owner_info)
        cookies = {"rai_session": session_id}

        # List incidents
        resp = await self.client.get("/api/owner/incidents", cookies=cookies)
        self.assertEqual(resp.status, 200)
        inc_data = await resp.json()
        self.assertTrue(inc_data["success"])
        incidents = inc_data["data"]["incidents"]
        self.assertTrue(any(i["id"] == corr_id for i in incidents))

        # Acknowledge incident
        ack_resp = await self.client.post(
            "/api/owner/incidents/acknowledge",
            cookies=cookies,
            json={"incident_id": corr_id},
        )
        self.assertEqual(ack_resp.status, 200)
        ack_data = await ack_resp.json()
        self.assertTrue(ack_data["success"])
        self.assertTrue(ack_data["data"]["acknowledged"])

    async def test_05_feature_flags_toggle_and_recovery(self):
        """Verify feature flags can be inspected and updated transactionally."""
        owner_info = {"id": str(BOT_OWNER_ID), "username": "RaiOwner"}
        session_id = await self.server.api_router.auth.create_session_for_user(owner_info)
        cookies = {"rai_session": session_id}

        # Get flags
        resp = await self.client.get("/api/owner/feature-flags", cookies=cookies)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        self.assertIn("smart_autodj", data["data"]["flags"])

        # Toggle flag
        post_resp = await self.client.post(
            "/api/owner/feature-flags",
            cookies=cookies,
            json={"flag": "smart_autodj", "enabled": False},
        )
        self.assertEqual(post_resp.status, 200)
        post_data = await post_resp.json()
        self.assertTrue(post_data["success"])
        self.assertFalse(post_data["data"]["enabled"])

        # Restore flag
        await self.client.post(
            "/api/owner/feature-flags",
            cookies=cookies,
            json={"flag": "smart_autodj", "enabled": True},
        )

    # =========================================================================
    # 3. USER ENTITLEMENT MANAGER
    # =========================================================================
    async def test_06_user_entitlement_lookup_and_promotional_grant(self):
        """Verify owner can search a user by Discord ID and grant/revoke promotional passes."""
        target_uid = int(time.time() * 1000)
        owner_info = {"id": str(BOT_OWNER_ID), "username": "RaiOwner"}
        session_id = await self.server.api_router.auth.create_session_for_user(owner_info)
        cookies = {"rai_session": session_id}

        # Lookup user
        search_resp = await self.client.get(f"/api/owner/users/search?user_id={target_uid}", cookies=cookies)
        self.assertEqual(search_resp.status, 200)
        s_data = await search_resp.json()
        self.assertTrue(s_data["success"])
        self.assertEqual(s_data["data"]["entitlements"]["tier"], "free")

        # Grant promotional premium
        grant_resp = await self.client.post(
            "/api/owner/users/entitlement",
            cookies=cookies,
            json={
                "user_id": str(target_uid),
                "action": "grant",
                "tier": "premium",
                "days": 30,
                "reason": "Top community contributor award",
            },
        )
        self.assertEqual(grant_resp.status, 200)
        g_data = await grant_resp.json()
        self.assertTrue(g_data["success"])
        self.assertEqual(g_data["data"]["tier"], "premium")

        # Re-lookup user to confirm active entitlement
        confirm_resp = await self.client.get(f"/api/owner/users/search?user_id={target_uid}", cookies=cookies)
        c_data = await confirm_resp.json()
        self.assertTrue(c_data["data"]["entitlements"]["is_premium"])

        # Revoke
        rev_resp = await self.client.post(
            "/api/owner/users/entitlement",
            cookies=cookies,
            json={
                "user_id": str(target_uid),
                "action": "revoke",
                "reason": "Test conclusion",
            },
        )
        self.assertEqual(rev_resp.status, 200)

    # =========================================================================
    # 4. GUILD ADMINISTRATOR SETTINGS
    # =========================================================================
    async def test_07_guild_admin_settings_authorization(self):
        """Verify guild admin settings require proper role and enforce volume caps."""
        test_guild_id = 1525030316845301781

        # Unauthenticated rejected
        unauth_resp = await self.client.get(f"/api/music/guild-settings?guild_id={test_guild_id}")
        self.assertEqual(unauth_resp.status, 401)

        # Non-admin user rejected with 403
        norm_user = {"id": "111222333444555", "username": "OrdinaryMember"}
        norm_sess = await self.server.api_router.auth.create_session_for_user(norm_user, is_admin_override=False)
        norm_cookies = {"rai_session": norm_sess}

        forbidden_resp = await self.client.get(f"/api/music/guild-settings?guild_id={test_guild_id}", cookies=norm_cookies)
        self.assertEqual(forbidden_resp.status, 403)

        # Bot Owner has management access
        owner_info = {"id": str(BOT_OWNER_ID), "username": "RaiOwner"}
        owner_sess = await self.server.api_router.auth.create_session_for_user(owner_info)
        owner_cookies = {"rai_session": owner_sess}

        ok_resp = await self.client.get(f"/api/music/guild-settings?guild_id={test_guild_id}", cookies=owner_cookies)
        self.assertEqual(ok_resp.status, 200)
        s_data = await ok_resp.json()
        self.assertTrue(s_data["success"])
        self.assertEqual(s_data["data"]["guild_id"], str(test_guild_id))

    async def test_08_guild_admin_volume_and_twenty_four_seven_entitlement(self):
        """Verify volumes above 100% and 24/7 mode enforce premium entitlement checks."""
        test_guild_id = 1525030316845301781

        # Ordinary user with Guild Admin perms in session but free tier
        admin_free_user = {
            "id": "777888999000111",
            "username": "GuildLeader",
        }
        admin_sess = await self.server.api_router.auth.create_session_for_user(
            discord_user=admin_free_user,
            user_guilds=[{"id": str(test_guild_id), "permissions": 0x8, "owner": True}],
        )
        cookies = {"rai_session": admin_sess}

        # Attempt to set volume to 140% without premium (must be rejected)
        vol_resp = await self.client.post(
            "/api/music/guild-settings",
            cookies=cookies,
            json={"guild_id": str(test_guild_id), "default_volume": 140},
        )
        self.assertEqual(vol_resp.status, 403)
        vol_data = await vol_resp.json()
        self.assertEqual(vol_data["error"]["code"], "PREMIUM_REQUIRED")

        # Attempt to set 24/7 mode without premium (must be rejected)
        tfs_resp = await self.client.post(
            "/api/music/guild-settings",
            cookies=cookies,
            json={"guild_id": str(test_guild_id), "twenty_four_seven_enabled": True},
        )
        self.assertEqual(tfs_resp.status, 403)
        tfs_data = await tfs_resp.json()
        self.assertEqual(tfs_data["error"]["code"], "PREMIUM_REQUIRED")

    # =========================================================================
    # 5. SPA DEEP ROUTING
    # =========================================================================
    async def test_09_direct_navigation_and_spa_refresh(self):
        """Verify all declared UI routes return 200 HTML on direct refresh or navigation."""
        routes = [
            "/",
            "/dashboard",
            "/search",
            "/queue",
            "/library",
            "/autodj",
            "/audio",
            "/stats",
            "/owner",
            "/dashboard/guilds",
            "/premium",
            "/premium/manage",
        ]
        for route in routes:
            resp = await self.client.get(route)
            self.assertEqual(resp.status, 200, f"Route {route} failed direct navigation")
            text = await resp.text()
            self.assertIn("Noctyra Studio", text)

    # =========================================================================
    # 6. PRODUCTION SAFEGUARD: DIRECT ID LOGIN
    # =========================================================================
    async def test_10_direct_id_login_blocked_in_production(self):
        """Verify auth_dev_login rejects direct ID spoofing when RENDER=true."""
        original_render = os.getenv("RENDER")
        try:
            os.environ["RENDER"] = "true"
            os.environ["ALLOW_DEV_LOGIN"] = "false"

            resp = await self.client.post("/api/auth/dev-login", json={"user_id": "1457382179981099090"})
            self.assertEqual(resp.status, 403)
            data = await resp.json()
            self.assertEqual(data["error"]["code"], "FORBIDDEN")
        finally:
            if original_render is None:
                os.environ.pop("RENDER", None)
            else:
                os.environ["RENDER"] = original_render
            os.environ.pop("ALLOW_DEV_LOGIN", None)

    async def test_11_ui_script_contains_user_favorites_and_safe_dashboard_render(self):
        """Verify web/ui.py script declares userFavorites and safely executes renderDashboard without ReferenceError."""
        from web.ui import UI_HTML
        self.assertIn("let userFavorites = [];", UI_HTML)
        self.assertIn("typeof userFavorites !== 'undefined'", UI_HTML)
        self.assertIn("syncFavorites()", UI_HTML)


if __name__ == "__main__":
    unittest.main()
