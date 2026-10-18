"""
Rai Community OS — Master Web Platform Server & Shared API.
Provides an asynchronous, luxury external community hub on port 8080.
Connects directly to the canonical SQLite WAL database and Discord bot gateway.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import time
from typing import Optional, TYPE_CHECKING
from aiohttp import web

from config import WEB_PORT, COMMUNITY_GUILD_ID
from database.database import Database
from web.api import ApiRouter
from web.ui import UI_HTML
from web.legal import (
    TERMS_OF_SERVICE_HTML,
    PRIVACY_POLICY_HTML,
    REFUND_POLICY_HTML,
    CONTACT_US_HTML,
)

from web.realtime import RealtimeGateway
from web.music_api import MusicApiRouter

from typing import Any, Optional

logger = logging.getLogger("Rai.WebServer")


class RaiCommunityOSServer:
    """Master asynchronous Web Server hosting Rai Community OS UI and REST API."""

    def __init__(
        self,
        bot: Optional[Any] = None,
        db: Optional[Database] = None,
        port: Optional[int] = None,
    ):
        self.bot = bot
        if db is not None and hasattr(db, "create_web_session"):
            self.db = db
        elif bot is not None and hasattr(bot, "app_db") and hasattr(bot.app_db, "create_web_session"):
            self.db = bot.app_db
        elif bot is not None and hasattr(bot, "database") and hasattr(bot.database, "create_web_session"):
            self.db = bot.database
        elif bot is not None and hasattr(bot, "db") and hasattr(bot.db, "create_web_session"):
            self.db = bot.db
        else:
            from database.database import Database
            self.db = Database()
        self.port = port or WEB_PORT
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.realtime_gateway = RealtimeGateway(self.db, self.bot)
        self.api_router = ApiRouter(self.db, self.bot, realtime=self.realtime_gateway)
        self.music_router = MusicApiRouter(auth_manager=self.api_router.auth, bot=bot)
        from web.payment_api import PaymentApiRouter
        self.payment_router = PaymentApiRouter(bot=self.bot, db=self.db, auth=self.api_router.auth)
        from web.owner_api import OwnerApiRouter
        self.owner_router = OwnerApiRouter(bot=self.bot, db=self.db, auth=self.api_router.auth)
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
        """Lightweight health check endpoint for Render & UptimeRobot with safe runtime diagnostics."""
        bot_ready = bool(self.bot and getattr(self.bot, "is_ready", lambda: False)())
        music_status = "online" if bot_ready else "starting"

        import sys
        import discord
        from discord.voice_client import has_nacl
        has_dave = getattr(discord.voice_client, "has_dave", False)
        try:
            import davey
            davey_ver = getattr(davey, "__version__", "loaded")
            davey_ok = True
        except ImportError:
            davey_ver = None
            davey_ok = False

        opus_ok = discord.opus.is_loaded()

        git_commit = os.getenv("RENDER_GIT_COMMIT")
        if not git_commit:
            try:
                import subprocess
                git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], timeout=1.0).decode().strip()
            except Exception:
                git_commit = "unknown"

        import yt_dlp
        from music_bot.services.resolver_service import get_cookie_diagnostics
        cookie_diag = get_cookie_diagnostics()

        return web.json_response({
            "status": "healthy",
            "bot_name": "MusicMaid (Neko Songs)",
            "bot_status": music_status,
            "platform": "MusicMaid Web Player & Platform",
            "timestamp": int(time.time()),
            "commit": git_commit[:8] if git_commit else "unknown",
            "git_commit": git_commit,
            "yt_dlp_version": yt_dlp.version.__version__,
            "cookies": {
                "present": cookie_diag.get("present", False),
                "status": cookie_diag.get("status", "Missing"),
            },
            "voice_engine": {
                "python": sys.version.split()[0],
                "discord_py": discord.__version__,
                "has_dave": bool(has_dave),
                "davey_imported": davey_ok,
                "davey_version": davey_ver,
                "has_nacl": bool(has_nacl),
                "opus_loaded": bool(opus_ok),
                "voice_ready": bool(has_dave and has_nacl and opus_ok),
            },
            "oauth": {
                "configured": bool(self.api_router.auth.is_configured),
                "client_id_present": bool(self.api_router.auth.client_id),
                "client_secret_present": bool(self.api_router.auth.client_secret),
                "redirect_uri": self.api_router.auth.get_redirect_uri(),
            },
            "payments": {
                "enabled": bool(os.getenv("PAYMENTS_ENABLED", "false").lower() == "true"),
                "provider": os.getenv("PAYMENT_PROVIDER", "razorpay"),
                "razorpay_configured": bool(os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET")),
            },
        })

    async def handle_terms(self, request: web.Request) -> web.Response:
        """Render the official Terms of Service legal compliance page."""
        return web.Response(text=TERMS_OF_SERVICE_HTML, content_type="text/html")

    async def handle_privacy(self, request: web.Request) -> web.Response:
        """Render the official Privacy Policy legal compliance page."""
        return web.Response(text=PRIVACY_POLICY_HTML, content_type="text/html")

    async def handle_refund(self, request: web.Request) -> web.Response:
        """Render the official Refund and Cancellation Policy compliance page."""
        return web.Response(text=REFUND_POLICY_HTML, content_type="text/html")

    async def handle_contact(self, request: web.Request) -> web.Response:
        """Render the official Contact Us support and grievance page."""
        return web.Response(text=CONTACT_US_HTML, content_type="text/html")

    async def handle_manifest(self, request: web.Request) -> web.Response:
        """Serve official PWA web app manifest."""
        manifest_path = Path(__file__).resolve().parent.parent / "public" / "manifest.json"
        if manifest_path.exists():
            return web.Response(text=manifest_path.read_text(encoding="utf-8"), content_type="application/manifest+json")
        return web.Response(status=404)

    async def handle_icon(self, request: web.Request) -> web.Response:
        """Serve official brand icon for PWA and favicon."""
        icon_path = Path(__file__).resolve().parent.parent / "public" / "icon.png"
        if not icon_path.exists():
            icon_path = Path(__file__).resolve().parent.parent / "assets" / "branding" / "musicmaid_icon_1024x1024.png"
        if icon_path.exists():
            return web.Response(body=icon_path.read_bytes(), content_type="image/png")
        return web.Response(status=404)

    def setup_routes(self, app: web.Application) -> None:
        """Register all UI and REST API routes."""
        r = self.api_router

        # PWA & Assets
        app.router.add_get("/manifest.json", self.handle_manifest)
        app.router.add_get("/icon.png", self.handle_icon)
        app.router.add_get("/favicon.ico", self.handle_icon)

        # Legal Compliance Endpoints for Discord Developer Portal & Razorpay KYC Verification
        app.router.add_get("/terms", self.handle_terms)
        app.router.add_get("/terms-of-service", self.handle_terms)
        app.router.add_get("/privacy", self.handle_privacy)
        app.router.add_get("/privacy-policy", self.handle_privacy)
        app.router.add_get("/refund", self.handle_refund)
        app.router.add_get("/refund-policy", self.handle_refund)
        app.router.add_get("/cancellation-policy", self.handle_refund)
        app.router.add_get("/contact", self.handle_contact)
        app.router.add_get("/contact-us", self.handle_contact)
        app.router.add_get("/support", self.handle_contact)

        # UI Page Routes (rendered via the responsive SPA shell)
        ui_routes = [
            "/", "/dashboard", "/discover", "/brain", "/projects", "/projects/{id}",
            "/creators", "/creators/{id}", "/gaming", "/music", "/media",
            "/resources", "/events", "/events/{id}", "/ideas", "/ideas/{id}",
            "/workspace", "/profile", "/notifications", "/settings", "/labs",
            "/status", "/wiki", "/mission-control",
            "/communities", "/communities/{id}", "/saved", "/rai", "/rai/features",
            "/discover/constellation", "/studio", "/bounties", "/passport", "/invites",
            "/search", "/queue", "/autodj", "/library", "/audio", "/dsp", "/stats",
            "/canvas", "/visualizer",
            "/owner", "/dashboard/guilds",
            "/premium", "/premium/checkout", "/premium/success", "/premium/cancel", "/premium/manage"
        ]
        for path in ui_routes:
            app.router.add_get(path, self.handle_ui)

        # Legacy KeepAlive & Health Endpoints
        app.router.add_get("/health", self.handle_health)
        app.router.add_get("/healthz", self.handle_health)
        app.router.add_get("/api/health", self.handle_health)
        app.router.add_get("/api/leaderboard", self.handle_legacy_leaderboard)

        # Authentication API
        app.router.add_get("/api/auth/login", r.auth_login)
        app.router.add_get("/login", r.auth_login)
        app.router.add_get("/api/auth/url", r.auth_url)
        app.router.add_get("/api/auth/callback", r.auth_callback)
        app.router.add_get("/api/auth/me", r.auth_me)
        app.router.add_get("/api/auth/logout", r.auth_logout)
        app.router.add_post("/api/auth/logout", r.auth_logout)
        app.router.add_get("/logout", r.auth_logout)
        app.router.add_post("/api/auth/dev-login", r.auth_dev_login)
        app.router.add_post("/api/auth/discord-id-login", r.auth_dev_login)

        # Telemetry, Pulse, and Realtime API
        app.router.add_get("/api/stats", r.get_stats)
        app.router.add_get("/api/pulse", r.get_pulse)
        app.router.add_get("/api/live", r.get_live_sessions)
        app.router.add_get("/api/activity", r.get_activity_feed)
        app.router.add_get("/api/constellation", r.get_constellation)
        app.router.add_get("/api/personal/discovery", r.get_personal_discovery)
        app.router.add_post("/api/spaces/create", r.create_space)
        app.router.add_get("/api/realtime/stream", r.realtime_stream)
        app.router.add_get("/api/realtime/ws", r.realtime_ws)
        app.router.add_get("/ws/live", r.realtime_ws)
        app.router.add_get("/api/realtime/diagnostics", r.get_realtime_diagnostics)
        app.router.add_get("/api/categories/counts", r.get_category_counts)

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

        # Creator Bounties & Gigs API
        app.router.add_get("/api/bounties", r.get_bounties)
        app.router.add_post("/api/bounties", r.create_bounty)
        app.router.add_post("/api/bounties/{id}/apply", r.apply_bounty)

        # Web Studio & Playground API
        app.router.add_get("/api/studio/templates", r.get_studio_templates)
        app.router.add_post("/api/studio/test", r.test_studio_payload)

        # Holographic Passport API
        app.router.add_get("/api/passport/{user_id}", r.get_passport)
        app.router.add_get("/api/passport", r.get_passport)

        # Labs & Constellation API
        app.router.add_get("/api/labs/constellation", r.get_constellation)
        app.router.add_post("/api/labs/simulate", r.run_simulation)

        # Mission Control API
        app.router.add_get("/api/doctor", r.get_doctor_diagnostics)
        app.router.add_get("/api/mission-control/overview", r.mission_control_overview)
        app.router.add_post("/api/mission-control/emergency", r.toggle_emergency_safe_mode)

        # Invite Tracker (APEX INVITE) API
        app.router.add_get("/api/invites/overview", r.get_invite_overview)
        app.router.add_get("/api/invites/leaderboard", r.get_invite_leaderboard)
        app.router.add_get("/api/invites/history", r.get_invite_history)
        app.router.add_get("/api/invites/config", r.get_invite_config)
        app.router.add_post("/api/invites/config", r.update_invite_config)
        app.router.add_get("/api/invites/rewards", r.get_invite_rewards)
        app.router.add_post("/api/invites/rewards", r.update_invite_rewards)

        # Raivora Music Platform API (Phase 2 & Phase 3)
        m = self.music_router
        app.router.add_get("/api/music/guilds", m.get_guilds)
        app.router.add_get("/api/music/session", m.get_session)
        app.router.add_get("/api/music/queue", m.get_queue)
        app.router.add_get("/api/music/history", m.get_history)
        app.router.add_get("/api/music/favorites", m.get_favorites)
        app.router.add_post("/api/music/favorites/toggle", m.toggle_favorite)
        app.router.add_post("/api/music/control", m.dispatch_control)
        app.router.add_get("/api/music/search", m.search_tracks)
        app.router.add_post("/api/music/enqueue", m.enqueue_track)
        app.router.add_get("/api/music/lyrics", m.get_lyrics)
        app.router.add_get("/api/music/stats", m.get_stats)
        app.router.add_get("/api/music/playlists", m.get_playlists)
        app.router.add_post("/api/music/playlists/save", m.save_playlist)
        app.router.add_post("/api/music/playlists/load", m.load_playlist)
        app.router.add_post("/api/music/playlists/delete", m.delete_playlist)
        app.router.add_get("/api/music/autodj", m.get_autodj_status)
        app.router.add_post("/api/music/autodj/settings", m.set_autodj_settings)
        app.router.add_get("/api/music/autodj/recommendations", m.get_autodj_recommendations)
        app.router.add_get("/api/music/guild-settings", m.get_guild_settings)
        app.router.add_post("/api/music/guild-settings", m.update_guild_settings)

        # Premium Subscription & Payment API (Razorpay & Stripe)
        p = self.payment_router
        app.router.add_get("/api/premium/plans", p.get_plans)
        app.router.add_get("/api/premium/status", p.get_status)
        app.router.add_post("/api/premium/order", p.create_order)
        app.router.add_post("/api/premium/create-order", p.create_order)
        app.router.add_post("/api/premium/verify", p.verify_payment)
        app.router.add_post("/api/premium/create-checkout", p.create_checkout)
        app.router.add_get("/api/premium/verify-session", p.verify_session)
        app.router.add_post("/api/premium/cancel", p.cancel_subscription)
        app.router.add_post("/api/premium/webhook", p.handle_webhook)
        app.router.add_post("/api/premium/webhook/razorpay", p.handle_razorpay_webhook)

        # Creator Control Center & Intelligent Operations API (Exclusively for Bot Owners)
        o = self.owner_router
        app.router.add_get("/api/owner/overview", o.get_overview)
        app.router.add_get("/api/owner/health", o.get_health)
        app.router.add_get("/api/owner/guilds", o.list_guilds)
        app.router.add_get("/api/owner/users/search", o.search_user)
        app.router.add_post("/api/owner/users/entitlement", o.update_entitlement)
        app.router.add_get("/api/owner/incidents", o.list_incidents)
        app.router.add_post("/api/owner/incidents/acknowledge", o.acknowledge_incident)
        app.router.add_get("/api/owner/feature-flags", o.get_feature_flags)
        app.router.add_post("/api/owner/feature-flags", o.update_feature_flags)
        app.router.add_get("/api/owner/backups", o.list_backups)
        app.router.add_post("/api/owner/backups/create", o.create_backup)
        app.router.add_get("/api/owner/audit-logs", o.list_audit_logs)

        # Fallback SPA routing for direct navigation and browser refresh (e.g. /search, /queue)
        async def fallback_spa(request: web.Request) -> web.Response:
            if request.path.startswith("/api/"):
                return web.json_response({
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": f"Endpoint '{request.path}' not found"}
                }, status=404)
            return await self.handle_ui(request)

        app.router.add_get("/{tail:.*}", fallback_spa)


    async def _outbox_worker_loop(self) -> None:
        """Background worker for asynchronous, idempotent Discord channel synchronization."""
        while self._is_running:
            try:
                if not hasattr(self.db, "fetch_pending_sync_events"):
                    await asyncio.sleep(15.0)
                    continue
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
            await self.realtime_gateway.start()
            self._outbox_task = asyncio.create_task(self._outbox_worker_loop())
            logger.info(f"✦ Rai Community OS Platform online at http://0.0.0.0:{self.port} ✦")
        except Exception as e:
            logger.warning(f"Could not start Rai Community OS on port {self.port}: {e}")

    async def stop(self) -> None:
        """Gracefully stop web server and cleanup worker."""
        self._is_running = False
        await self.realtime_gateway.stop()
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
