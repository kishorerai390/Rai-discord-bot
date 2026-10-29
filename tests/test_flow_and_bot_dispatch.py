import pytest
import unittest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp import web

class TestFlowAndBotDispatch(AioHTTPTestCase):
    async def get_application(self):
        # Create minimal test app modeling the routing
        app = web.Application()

        async def auth_me(request):
            auth = request.headers.get("Authorization", "")
            if "owner_token" in auth:
                return web.json_response({
                    "success": True,
                    "data": {
                        "authenticated": True,
                        "user": {"id": "1457380609641938981", "username": "Kishore (Owner)", "is_owner": True}
                    }
                })
            elif "user_token" in auth:
                return web.json_response({
                    "success": True,
                    "data": {
                        "authenticated": True,
                        "user": {"id": "999888777666", "username": "AnimeFan", "is_owner": False}
                    }
                })
            return web.json_response({"success": False, "data": {"authenticated": False}})

        async def music_control(request):
            data = await request.json()
            act = data.get("action", "").upper()
            payload = data.get("payload", {})
            return web.json_response({
                "success": True,
                "data": {"action": act, "executed": True, "payload": payload}
            })

        async def music_queue(request):
            return web.json_response({
                "success": True,
                "data": {
                    "queue": [],
                    "tracks": []
                }
            })

        app.router.add_get('/api/auth/me', auth_me)
        app.router.add_post('/api/music/control', music_control)
        app.router.add_get('/api/music/queue', music_queue)
        return app

    @unittest_run_loop
    async def test_owner_auth_routing(self):
        resp = await self.client.get('/api/auth/me', headers={"Authorization": "Bearer owner_token"})
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["user"]["is_owner"])

    @unittest_run_loop
    async def test_user_auth_routing(self):
        resp = await self.client.get('/api/auth/me', headers={"Authorization": "Bearer user_token"})
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["user"]["is_owner"])

    @unittest_run_loop
    async def test_bot_command_dispatch(self):
        commands = [
            ("PLAY", {}),
            ("PAUSE", {}),
            ("SKIP", {}),
            ("VOLUME", {"volume": 80}),
            ("PLAY_NOW", {"query": "YOASOBI - Monster"}),
            ("RADIO", {"station": "lofi"}),
            ("SOUNDBOARD", {"sound": "airhorn"}),
            ("VIBE", {"mood": "anime"})
        ]
        for cmd, payload in commands:
            resp = await self.client.post('/api/music/control', json={"action": cmd, "payload": payload})
            self.assertEqual(resp.status, 200)
            json_data = await resp.json()
            self.assertTrue(json_data["success"])
            self.assertEqual(json_data["data"]["action"], cmd)

    def test_landing_page_buttons_lead_to_login(self):
        from web_landing import LANDING_PAGE_HTML
        self.assertIn('href="/login"', LANDING_PAGE_HTML)
        self.assertIn('Open Web Dashboard', LANDING_PAGE_HTML)
        self.assertIn('Dashboard ↗', LANDING_PAGE_HTML)

    def test_dashboard_rich_default_tracks_rendered(self):
        from web_dashboard import DASHBOARD_HTML
        self.assertIn('怪物 (Monster)', DASHBOARD_HTML)
        self.assertIn('新時代 (New Genesis)', DASHBOARD_HTML)
        self.assertIn('Faded (Live Vocal Edition)', DASHBOARD_HTML)
        self.assertIn('KICK BACK', DASHBOARD_HTML)
        self.assertIn('dispatchCmd(\'PLAY_NOW\'', DASHBOARD_HTML)

    def test_kalyani_and_vibe_categories_in_landing(self):
        from web_landing import LANDING_PAGE_HTML
        # Kalyani should be present in the catalog
        self.assertIn('Kalyani', LANDING_PAGE_HTML)
        self.assertIn('Kalyana Samayal Saadham', LANDING_PAGE_HTML)
        # Multiple tracks in phonk & desi
        self.assertIn('Metamorphosis', LANDING_PAGE_HTML)
        self.assertIn('Murder In My Mind', LANDING_PAGE_HTML)
        self.assertIn('Naa Ready', LANDING_PAGE_HTML)
        # Reactive search functions
        self.assertIn('trackMatchesQuery', LANDING_PAGE_HTML)
        self.assertIn('renderSuggestions', LANDING_PAGE_HTML)
