"""
Rai Community OS — Master Web Platform Server & Shared API.
Provides an asynchronous, luxury external community hub on port 8080.
Connects directly to the canonical SQLite WAL database and Discord bot gateway.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional, TYPE_CHECKING
from aiohttp import web

from config import WEB_PORT, COMMUNITY_GUILD_ID
from database.database import Database
from web.api import ApiRouter
from web.ui import UI_HTML

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger("Rai.WebServer")


class RaiCommunityOSServer:
    """Master asynchronous Web Server hosting Rai Community OS UI and REST API."""

    def __init__(
        self,
        bot: Optional[SentinelBot] = None,
        db: Optional[Database] = None,
        port: Optional[int] = None,
    ):
        self.bot = bot
        self.db = db or (bot.db if bot else Database())
        self.port = port or WEB_PORT
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.api_router = ApiRouter(self.db, self.bot)
        self._outbox_task: Optional[asyncio.Task] = None
        self._is_running = False

    async def handle_ui(self, request: web.Request) -> web.Response:
        """Render the Rai Community OS luxury single-page application."""
        return web.Response(text=UI_HTML, content_type="text/html")

    async def handle_legacy_leaderboard(self, request: web.Request) -> web.Response:
        """Backward-compatible economy leaderboard API."""
        try:
            users = await self.db.get_top_economy_users(COMMUNITY_GUILD_ID, limit=10, order_by="coins")
            results = []
            for u in users:
                results.append({
                    "id": u.user_id,
                    "name": f"Member {u.user_id}",
                    "coins": u.coins,
                    "level": u.level,
                    "streak": u.daily_streak,
                })
            return web.json_response(results)
        except Exception:
            return web.json_response([])

    async def handle_health(self, request: web.Request) -> web.Response:
        """Lightweight health check endpoint."""
        return web.json_response({
            "status": "healthy",
            "bot": "The Raivora",
            "platform": "Rai Community OS",
            "timestamp": int(time.time()),
        })

    def setup_routes(self, app: web.Application) -> None:
        """Register all UI and REST API routes."""
        r = self.api_router

        # UI Page Routes (rendered via the responsive SPA shell)
        ui_routes = [
            "/", "/dashboard", "/discover", "/brain", "/projects", "/projects/{id}",
            "/creators", "/creators/{id}", "/gaming", "/music", "/media",
            "/resources", "/events", "/events/{id}", "/ideas", "/ideas/{id}",
            "/workspace", "/profile", "/notifications", "/settings", "/labs",
            "/status", "/wiki", "/mission-control", "/login",
            "/communities", "/communities/{id}", "/saved", "/rai", "/rai/features"
        ]
        for path in ui_routes:
            app.router.add_get(path, self.handle_ui)

        # Legacy KeepAlive & Health Endpoints
        app.router.add_get("/health", self.handle_health)
        app.router.add_get("/healthz", self.handle_health)
        app.router.add_get("/api/health", self.handle_health)
        app.router.add_get("/api/leaderboard", self.handle_legacy_leaderboard)

        # Authentication API
        app.router.add_get("/api/auth/url", r.auth_url)
        app.router.add_get("/api/auth/callback", r.auth_callback)
        app.router.add_get("/api/auth/me", r.auth_me)
        app.router.add_post("/api/auth/logout", r.auth_logout)
        app.router.add_post("/api/auth/dev-login", r.auth_dev_login)
        app.router.add_post("/api/auth/discord-id-login", r.auth_dev_login)

        # Telemetry & Stats API
        app.router.add_get("/api/stats", r.get_stats)

        # Communities Discovery API
        app.router.add_get("/api/communities", r.list_communities)
        app.router.add_get("/api/communities/{id}", r.get_community)

        # Rai Features & Platform Architecture API
        app.router.add_get("/api/rai/features", r.get_rai_features)

        # Saved & Bookmarks API
        app.router.add_get("/api/saved", r.list_saved)
        app.router.add_post("/api/saved/toggle", r.toggle_saved)

        # Profiles API
        app.router.add_get("/api/profiles", r.list_profiles)
        app.router.add_get("/api/profiles/{id}", r.get_profile)
        app.router.add_put("/api/profiles/me", r.update_my_profile)

        # Creators & Portfolios API
        app.router.add_get("/api/creators", r.list_creators)
        app.router.add_post("/api/creators/portfolio", r.create_portfolio_item)

        # Projects & Tasks API
        app.router.add_get("/api/projects", r.list_projects)
        app.router.add_post("/api/projects", r.create_project)
        app.router.add_get("/api/projects/{id}", r.get_project_details)
        app.router.add_post("/api/projects/{id}/tasks", r.create_task)
        app.router.add_put("/api/projects/{id}/tasks/{task_id}", r.update_task_status)

        # Gaming & LFG API
        app.router.add_get("/api/gaming/lfg", r.list_lfg)
        app.router.add_post("/api/gaming/lfg", r.create_lfg)
        app.router.add_post("/api/gaming/lfg/{id}/join", r.join_lfg)

        # Events API
        app.router.add_get("/api/events", r.list_events)
        app.router.add_post("/api/events/{id}/rsvp", r.rsvp_event)

        # Resources API
        app.router.add_get("/api/resources", r.list_resources)
        app.router.add_post("/api/resources", r.submit_resource)

        # Ideas API
        app.router.add_get("/api/ideas", r.list_ideas)
        app.router.add_post("/api/ideas", r.submit_idea)
        app.router.add_post("/api/ideas/{id}/vote", r.vote_idea)
        app.router.add_post("/api/ideas/{id}/comment", r.comment_idea)
        app.router.add_get("/api/ideas/{id}/comments", r.list_idea_comments)

        # Notifications API
        app.router.add_get("/api/notifications", r.list_notifications)
        app.router.add_post("/api/notifications/{id}/read", r.mark_notification_read)
        app.router.add_post("/api/notifications/read-all", r.mark_all_notifications_read)

        # Workspace API
        app.router.add_get("/api/workspace/summary", r.get_workspace_summary)

        # Brain & Search API
        app.router.add_get("/api/brain/search", r.brain_search)
        app.router.add_get("/api/search", r.brain_search)

        # Wiki API
        app.router.add_get("/api/wiki", r.list_wiki)
        app.router.add_get("/api/wiki/{slug}", r.get_wiki_slug)

        # Labs & Constellation API
        app.router.add_get("/api/labs/constellation", r.get_constellation)
        app.router.add_post("/api/labs/simulate", r.run_simulation)

        # Mission Control API
        app.router.add_get("/api/doctor", r.get_doctor_diagnostics)
        app.router.add_get("/api/mission-control/overview", r.mission_control_overview)
        app.router.add_post("/api/mission-control/emergency", r.toggle_emergency_safe_mode)

    async def _outbox_worker_loop(self) -> None:
        """Background worker for asynchronous, idempotent Discord channel synchronization."""
        while self._is_running:
            try:
                events = await self.db.fetch_pending_sync_events(limit=5)
                for ev in events:
                    event_id = ev["event_id"]
                    event_type = ev["event_type"]
                    payload = ev.get("payload", {})

                    if event_type == "PROJECT_CREATED" and self.bot:
                        # Attempt to create Discord channels if bot has permissions
                        guild_id = payload.get("guild_id", COMMUNITY_GUILD_ID)
                        proj_id = payload.get("project_id")
                        name = payload.get("name", "Project")
                        guild = self.bot.get_guild(guild_id)

                        if guild and guild.me.guild_permissions.manage_channels:
                            try:
                                cat = await guild.create_category(f"📁 Proj: {name[:20]}")
                                chat_ch = await guild.create_text_channel(f"chat-{name[:15].lower().replace(' ', '-')}", category=cat)
                                vc_ch = await guild.create_voice_channel(f"VC-{name[:15]}", category=cat)
                                # Update project record with created channel IDs
                                await self.db._db.execute(
                                    "UPDATE projects SET category_id = ?, chat_channel_id = ?, voice_channel_id = ? WHERE id = ?",
                                    (cat.id, chat_ch.id, vc_ch.id, proj_id),
                                )
                                await self.db._db.commit()
                                await self.db.mark_sync_event_processed(event_id)
                                logger.info(f"[OUTBOX] Synced project {proj_id} with Discord channels.")
                                continue
                            except Exception as c_err:
                                logger.warning(f"[OUTBOX] Discord channel sync transient error for {event_id}: {c_err}")
                                await self.db.mark_sync_event_failed(event_id, str(c_err))
                                continue

                    # If bot is not available or sync not applicable, safely mark processed
                    await self.db.mark_sync_event_processed(event_id)
            except Exception as e:
                logger.error(f"[OUTBOX] Error in outbox worker loop: {e}", exc_info=True)

            await asyncio.sleep(15.0)

    async def start(self) -> None:
        """Start the web server and background outbox sync worker."""
        if not self.db.is_connected:
            await self.db.connect()

        try:
            self.app = web.Application()
            self.setup_routes(self.app)
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, "0.0.0.0", self.port)
            await self.site.start()
            self._is_running = True
            self._outbox_task = asyncio.create_task(self._outbox_worker_loop())
            logger.info(f"✦ Rai Community OS Platform online at http://0.0.0.0:{self.port} ✦")
        except Exception as e:
            logger.warning(f"Could not start Rai Community OS on port {self.port}: {e}")

    async def stop(self) -> None:
        """Gracefully stop web server and cleanup worker."""
        self._is_running = False
        if self._outbox_task:
            self._outbox_task.cancel()
            try:
                await self._outbox_task
            except asyncio.CancelledError:
                pass
        if self.runner:
            await self.runner.cleanup()
            logger.info("Rai Community OS Web Server stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db = Database()
    server = RaiCommunityOSServer(db=db)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server.start())
        print(f"Rai Community OS running on port {server.port}. Press Ctrl+C to stop.")
        loop.run_forever()
    except KeyboardInterrupt:
        loop.run_until_complete(server.stop())
