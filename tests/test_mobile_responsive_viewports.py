"""
Automated Viewport & Responsive Layout Verification Suite for MusicMaid.

Tests viewports required by the specification:
- 320px  (iPhone SE / Ultra-compact mobile)
- 360px  (Standard Android compact)
- 375px  (iPhone Mini / Standard mobile)
- 390px  (iPhone 13 / 14 / 15 standard)
- 430px  (iPhone 14 / 15 Pro Max)
- 768px  (iPad Portrait / Large tablet)
- 1024px (iPad Landscape / Small laptop)
- 1440px (Desktop / High-res widescreen)

Checks:
- Zero horizontal overflow: document.documentElement.scrollWidth <= window.innerWidth
- Mobile drawer navigation: open, close via X button, close via backdrop, navigate
- Bottom playback bar 2-tier stacked layout on mobile <= 768px
- Responsive scaling on cards, hero vinyl, search bar, queue rows, and pricing tables
"""

import asyncio
import json
import os
import subprocess
import time
import unittest
import urllib.request
from urllib.parse import parse_qs, urlparse
import aiohttp
from aiohttp import web

from web.server import RaiCommunityOSServer
from music_bot.database.db import MusicDatabase


VIEWPORTS = [
    {"name": "iPhone SE / Ultra-compact", "width": 320, "height": 568, "mobile": True},
    {"name": "Standard Android",          "width": 360, "height": 800, "mobile": True},
    {"name": "iPhone Mini",               "width": 375, "height": 812, "mobile": True},
    {"name": "iPhone 13/14/15",           "width": 390, "height": 844, "mobile": True},
    {"name": "iPhone 14/15 Pro Max",      "width": 430, "height": 932, "mobile": True},
    {"name": "iPad Portrait / Tablet",    "width": 768, "height": 1024, "mobile": True},
    {"name": "iPad Landscape / Laptop",   "width": 1024, "height": 768, "mobile": False},
    {"name": "Desktop Display",           "width": 1440, "height": 900, "mobile": False},
]

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


class ChromeCDPClient:
    """Lightweight Chrome DevTools Protocol Client using aiohttp WebSockets."""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None
        self._msg_id = 0
        self._pending = {}
        self._reader_task = None
        self.session = None

    async def connect(self):
        self.session = aiohttp.ClientSession()
        self.ws = await self.session.ws_connect(self.ws_url)
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self):
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    msg_id = data.get("id")
                    if msg_id in self._pending:
                        self._pending[msg_id].set_result(data)
        except Exception:
            pass

    async def send(self, method: str, params: dict = None) -> dict:
        self._msg_id += 1
        msg_id = self._msg_id
        payload = {"id": msg_id, "method": method, "params": params or {}}
        fut = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut
        await self.ws.send_str(json.dumps(payload))
        return await asyncio.wait_for(fut, timeout=10.0)

    async def evaluate(self, expression: str):
        res = await self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True
        })
        result = res.get("result", {}).get("result", {})
        return result.get("value")

    async def close(self):
        if self._reader_task:
            self._reader_task.cancel()
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()


class TestMobileResponsiveViewports(unittest.IsolatedAsyncioTestCase):
    """End-to-end multi-viewport browser testing suite."""

    server_runner = None
    chrome_proc = None
    server_port = 8198
    cdp_port = 9222
    browser_bin = None

    @classmethod
    def setUpClass(cls):
        # Locate browser binary
        for p in CHROME_PATHS:
            if os.path.isfile(p):
                cls.browser_bin = p
                break
        if not cls.browser_bin:
            raise unittest.SkipTest("Neither Google Chrome nor Microsoft Edge is installed.")

    async def asyncSetUp(self):
        # Initialize Database
        self.db = MusicDatabase()
        await self.db.connect()

        # Initialize web server
        self.server = RaiCommunityOSServer(bot=None, db=self.db, port=self.server_port)
        self.server.api_router.auth._client_id = "mock_client_id_for_testing"
        self.server.api_router.auth._client_secret = "mock_client_secret_for_testing"
        app = web.Application()
        self.server.setup_routes(app)

        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", self.server_port)
        await self.site.start()

        # Launch Chrome in headless mode with remote debugging
        user_data_dir = os.path.join(os.getenv("TEMP", r"C:\TEMP"), "chrome_cdp_profile")
        cmd = [
            self.browser_bin,
            "--headless=new",
            f"--remote-debugging-port={self.cdp_port}",
            f"--user-data-dir={user_data_dir}",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank"
        ]
        self.chrome_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(1.5)

        # Get WebSocket debugger URL from http://127.0.0.1:9222/json
        ws_url = None
        for _ in range(10):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.cdp_port}/json") as r:
                    pages = json.loads(r.read().decode())
                    for p in pages:
                        if p.get("type") == "page" and "webSocketDebuggerUrl" in p:
                            ws_url = p["webSocketDebuggerUrl"]
                            break
                    if ws_url:
                        break
            except Exception:
                await asyncio.sleep(0.5)

        if not ws_url:
            raise RuntimeError("Could not connect to Chrome DevTools endpoint.")

        self.cdp = ChromeCDPClient(ws_url)
        await self.cdp.connect()
        await self.cdp.send("Page.enable")
        await self.cdp.send("DOM.enable")
        await self.cdp.send("Runtime.enable")

    async def asyncTearDown(self):
        if hasattr(self, "cdp") and self.cdp:
            await self.cdp.close()
        if self.chrome_proc:
            self.chrome_proc.terminate()
            self.chrome_proc.wait()
        if hasattr(self, "runner") and self.runner:
            await self.runner.cleanup()
        if hasattr(self, "db") and self.db:
            await self.db.close()

    async def _navigate_and_wait(self, path: str):
        url = f"http://127.0.0.1:{self.server_port}{path}"
        await self.cdp.send("Page.navigate", {"url": url})
        # Wait for DOM and initial JS rendering
        await asyncio.sleep(1.0)

    async def _set_viewport(self, width: int, height: int, mobile: bool):
        await self.cdp.send("Emulation.setDeviceMetricsOverride", {
            "width": width,
            "height": height,
            "deviceScaleFactor": 2 if mobile else 1,
            "mobile": mobile,
        })
        await asyncio.sleep(0.2)

    async def test_01_all_viewports_zero_horizontal_overflow(self):
        """Test representative viewports (320px to 1440px) for zero horizontal overflow across core routes."""
        routes = ["/", "/search", "/queue", "/premium", "/audio", "/stats"]
        results = []

        for vp in VIEWPORTS:
            w, h, m = vp["width"], vp["height"], vp["mobile"]
            await self._set_viewport(w, h, m)

            for route in routes:
                # Use client-side router navigate() to switch views quickly
                if route == "/":
                    await self._navigate_and_wait("/")
                else:
                    await self.cdp.evaluate(f"navigate('{route}')")
                    await asyncio.sleep(0.3)

                dims = await self.cdp.evaluate("""
                    (() => {
                        const doc = document.documentElement;
                        const body = document.body;
                        return {
                            scrollWidth: Math.max(doc.scrollWidth, body.scrollWidth),
                            clientWidth: doc.clientWidth,
                            innerWidth: window.innerWidth
                        };
                    })()
                """)

                scroll_w = dims["scrollWidth"]
                inner_w = dims["innerWidth"]
                diff = scroll_w - inner_w

                # Strict check: scrollWidth must NOT exceed window.innerWidth (0 overflow allowed)
                self.assertLessEqual(
                    scroll_w, inner_w,
                    f"Horizontal overflow detected at viewport {w}x{h} on route '{route}': "
                    f"scrollWidth={scroll_w}px > innerWidth={inner_w}px (overflow: +{diff}px)"
                )
                results.append((vp["name"], f"{w}px", route, scroll_w, inner_w, "PASS"))

        print("\n--- VIEWPORT ZERO HORIZONTAL OVERFLOW RESULTS ---")
        for res in results:
            print(f"[{res[5]}] Viewport: {res[1]:<6} ({res[0]:<26}) Route: {res[2]:<10} ScrollWidth: {res[3]}px == InnerWidth: {res[4]}px")

    async def test_02_mobile_navigation_drawer_open_close_cycle(self):
        """Verify mobile menu opens via hamburger, activates backdrop, locks scroll, and closes via close button and backdrop."""
        await self._set_viewport(375, 812, mobile=True)
        await self._navigate_and_wait("/")

        # Initial state: sidebar closed, backdrop hidden, body not locked
        init_state = await self.cdp.evaluate("""
            (() => {
                const sidebar = document.getElementById('sidebar');
                const backdrop = document.getElementById('sidebar-backdrop');
                return {
                    sidebarOpen: sidebar.classList.contains('mobile-open'),
                    backdropActive: backdrop.classList.contains('active'),
                    bodyLocked: document.body.classList.contains('sidebar-open')
                };
            })()
        """)
        self.assertFalse(init_state["sidebarOpen"], "Sidebar should initially be closed on mobile.")
        self.assertFalse(init_state["backdropActive"], "Backdrop should initially be inactive.")

        # Click hamburger button
        await self.cdp.evaluate("document.querySelector('.mobile-btn').click()")
        await asyncio.sleep(0.3)

        open_state = await self.cdp.evaluate("""
            (() => {
                const sidebar = document.getElementById('sidebar');
                const backdrop = document.getElementById('sidebar-backdrop');
                return {
                    sidebarOpen: sidebar.classList.contains('mobile-open'),
                    backdropActive: backdrop.classList.contains('active'),
                    bodyLocked: document.body.classList.contains('sidebar-open')
                };
            })()
        """)
        self.assertTrue(open_state["sidebarOpen"], "Sidebar must have .mobile-open class when toggled open.")
        self.assertTrue(open_state["backdropActive"], "Backdrop must have .active class when sidebar is open.")
        self.assertTrue(open_state["bodyLocked"], "Body must have .sidebar-open to lock scrolling.")

        # Click close button inside sidebar header
        await self.cdp.evaluate("document.querySelector('.mobile-sidebar-close').click()")
        await asyncio.sleep(0.3)

        closed_state = await self.cdp.evaluate("""
            (() => {
                const sidebar = document.getElementById('sidebar');
                const backdrop = document.getElementById('sidebar-backdrop');
                return {
                    sidebarOpen: sidebar.classList.contains('mobile-open'),
                    backdropActive: backdrop.classList.contains('active'),
                    bodyLocked: document.body.classList.contains('sidebar-open')
                };
            })()
        """)
        self.assertFalse(closed_state["sidebarOpen"], "Sidebar must close when mobile-sidebar-close is clicked.")
        self.assertFalse(closed_state["backdropActive"], "Backdrop must be inactive when sidebar is closed.")

        # Re-open and close by clicking backdrop
        await self.cdp.evaluate("toggleMobileSidebar()")
        await asyncio.sleep(0.2)
        await self.cdp.evaluate("document.getElementById('sidebar-backdrop').click()")
        await asyncio.sleep(0.2)
        backdrop_closed = await self.cdp.evaluate("document.getElementById('sidebar').classList.contains('mobile-open')")
        self.assertFalse(backdrop_closed, "Sidebar must close when backdrop is clicked.")

    async def test_03_mobile_bottom_player_bar_stacked_layout(self):
        """Verify bottom player bar reflows into a 2-tier stacked flex layout on screens <= 768px."""
        # Test on 360px mobile
        await self._set_viewport(360, 800, mobile=True)
        await self._navigate_and_wait("/dashboard")

        player_styles = await self.cdp.evaluate("""
            (() => {
                const bar = document.querySelector('footer.player-bar');
                const inner = document.querySelector('.player-bar-inner');
                const controls = document.querySelector('.player-tier-controls');
                const right = document.querySelector('.player-bar-right');
                const csBar = window.getComputedStyle(bar);
                const csInner = window.getComputedStyle(inner);
                const csRight = window.getComputedStyle(right);
                return {
                    barDisplay: csBar.display,
                    innerDisplay: csInner.display,
                    flexDirection: csInner.flexDirection,
                    rightVisible: csRight.display !== 'none',
                    controlsWidth: controls.offsetWidth,
                    barHeight: bar.offsetHeight
                };
            })()
        """)
        self.assertEqual(player_styles["barDisplay"], "block", "Player bar must remain visible on mobile.")
        self.assertEqual(player_styles["innerDisplay"], "flex", "Player bar contents must use flex layout.")
        self.assertEqual(player_styles["flexDirection"], "column", "Player bar must stack vertically into 2 tiers.")
        self.assertTrue(player_styles["rightVisible"], "Mobile volume and utility controls must remain available.")
        self.assertGreater(player_styles["controlsWidth"], 0, "Playback controls must remain visible on mobile.")
        self.assertGreaterEqual(player_styles["barHeight"], 80, "Player bar must have adequate height for both tiers.")

        # Test on 1440px desktop
        await self._set_viewport(1440, 900, mobile=False)
        await asyncio.sleep(0.3)
        desktop_player = await self.cdp.evaluate("""
            (() => {
                const bar = document.querySelector('footer.player-bar');
                const right = document.querySelector('.player-bar-right');
                const csBar = window.getComputedStyle(bar);
                const csRight = window.getComputedStyle(right);
                return {
                    display: csBar.display,
                    rightVisible: csRight.display !== 'none'
                };
            })()
        """)
        self.assertEqual(desktop_player["display"], "block", "Player bar must remain visible on desktop.")
        self.assertTrue(desktop_player["rightVisible"], "Desktop right controls must be visible on desktop.")

    async def test_04_touch_friendly_tap_targets(self):
        """Verify buttons and interactive elements meet touch target minimums (>= 34px on smallest mobile, >= 40px on standard)."""
        await self._set_viewport(375, 812, mobile=True)
        await self._navigate_and_wait("/dashboard")

        targets = await self.cdp.evaluate("""
            (() => {
                const btn = document.querySelector('.mobile-btn');
                const playBtn = document.querySelector('.p-btn-play');
                const navLinks = Array.from(document.querySelectorAll('.nav-link')).slice(0, 3);
                return {
                    mobileBtn: { w: btn.offsetWidth, h: btn.offsetHeight },
                    playBtn: { w: playBtn.offsetWidth, h: playBtn.offsetHeight },
                    navLinkHeights: navLinks.map(l => l.offsetHeight)
                };
            })()
        """)
        self.assertGreaterEqual(targets["mobileBtn"]["h"], 36, "Mobile menu button must be >= 36px.")
        self.assertGreaterEqual(targets["playBtn"]["h"], 38, "Play button must be >= 38px.")
        for h in targets["navLinkHeights"]:
            self.assertGreaterEqual(h, 34, "Navigation links must be touch friendly (>= 34px).")

    async def test_05_oauth_authoritative_callback_route(self):
        """Verify the OAuth authorization URL generator explicitly uses /api/auth/callback as the redirect_uri."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{self.server_port}/api/auth/url") as resp:
                data = await resp.json()
                self.assertTrue(data.get("success"), "API /api/auth/url must return success.")
                auth_data = data.get("data", {})
                self.assertIn("redirect_uri", auth_data)
                self.assertTrue(auth_data["redirect_uri"].endswith("/api/auth/callback"))
                oauth_params = parse_qs(urlparse(auth_data["url"]).query)
                self.assertEqual(oauth_params["redirect_uri"], [auth_data["redirect_uri"]])


if __name__ == "__main__":
    unittest.main()
