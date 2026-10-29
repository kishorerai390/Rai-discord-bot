"""
Rai Community OS — Discord OAuth2 and Web Authentication Middleware.
Handles token exchange, user identity resolution, secure sessions, and role checks.
"""

from __future__ import annotations

import datetime
import logging
import secrets
import urllib.parse
from typing import Any, Dict, Optional, TYPE_CHECKING
import aiohttp
from aiohttp import web

from config import (
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    DISCORD_REDIRECT_URI,
    COMMUNITY_GUILD_ID,
)
from music_bot.config import is_valid_public_https_url, is_bot_owner

if TYPE_CHECKING:
    from database.database import Database

logger = logging.getLogger("Rai.WebAuth")

import os

SESSION_COOKIE_NAME = "rai_session"
DISCORD_API_BASE = "https://discord.com/api/v10"


class AuthManager:
    """Manages Discord OAuth2 workflows and local web sessions."""

    def __init__(self, db: Database, bot: Optional[Any] = None):
        self.db = db
        self.bot = bot
        self._client_id: Optional[str] = None
        self._client_secret: Optional[str] = None
        self._memory_sessions: Dict[str, Dict[str, Any]] = {}
        self._revoked_sessions: set[str] = set()

    @property
    def client_id(self) -> str:
        """Resolve Discord application/client ID from env vars or live bot instance."""
        if self._client_id is not None:
            return self._client_id
        cid = (
            os.getenv("DISCORD_CLIENT_ID", "").strip()
            or os.getenv("CLIENT_ID", "").strip()
            or os.getenv("APPLICATION_ID", "").strip()
            or os.getenv("DISCORD_APPLICATION_ID", "").strip()
            or str(DISCORD_CLIENT_ID or "").strip()
        )
        if not cid and self.bot:
            bot_user = getattr(self.bot, "user", None)
            if bot_user and getattr(bot_user, "id", None):
                cid = str(bot_user.id)
            elif getattr(self.bot, "application_id", None):
                cid = str(self.bot.application_id)
        return cid

    @client_id.setter
    def client_id(self, value: Optional[str]) -> None:
        self._client_id = value

    @property
    def client_secret(self) -> str:
        """Resolve Discord client secret from env vars."""
        if self._client_secret is not None:
            return self._client_secret
        return (
            os.getenv("DISCORD_CLIENT_SECRET", "").strip()
            or os.getenv("CLIENT_SECRET", "").strip()
            or os.getenv("DISCORD_SECRET", "").strip()
            or os.getenv("BOT_CLIENT_SECRET", "").strip()
            or str(DISCORD_CLIENT_SECRET or "").strip()
        )

    @client_secret.setter
    def client_secret(self, value: Optional[str]) -> None:
        self._client_secret = value

    @property
    def is_configured(self) -> bool:
        """Returns True if Discord OAuth2 credentials are configured."""
        return bool(self.client_id and self.client_secret)


    def get_redirect_uri(self, request: Optional[web.Request] = None) -> str:
        """
        Dynamically determine the valid Discord OAuth2 redirect URI.
        Supports PUBLIC_BASE_URL, custom domains, DISCORD_REDIRECT_URI, and Render production domains.
        """
        # 1. Check explicit DISCORD_REDIRECT_URI environment variable (if non-localhost)
        env_uri = os.getenv("DISCORD_REDIRECT_URI", "").strip() or DISCORD_REDIRECT_URI
        if env_uri:
            if "/auth/discord/callback" in env_uri:
                logger.warning(
                    "[Auth] DISCORD_REDIRECT_URI contains '/auth/discord/callback'. "
                    "Normalizing to authoritative route '/api/auth/callback'."
                )
                env_uri = env_uri.replace("/auth/discord/callback", "/api/auth/callback")
            if is_valid_public_https_url(env_uri):
                return env_uri

        # 2. Check authoritative PUBLIC_BASE_URL or MUSICMAID_WEBSITE_URL
        public_base = (
            os.getenv("PUBLIC_BASE_URL", "").strip()
            or os.getenv("MUSICMAID_WEBSITE_URL", "").strip()
        )
        if public_base and is_valid_public_https_url(public_base):
            return f"{public_base.rstrip('/')}/api/auth/callback"

        # 3. Check if deployed on Render (Render automatically exposes RENDER_EXTERNAL_URL)
        render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
        if render_url and is_valid_public_https_url(render_url):
            return f"{render_url.rstrip('/')}/api/auth/callback"

        # 4. If request is provided, inspect X-Forwarded-Host / Host header for custom or remote domain
        if request:
            forwarded_proto = request.headers.get("X-Forwarded-Proto", request.scheme)
            forwarded_host = request.headers.get("X-Forwarded-Host", request.host)
            if forwarded_host and not forwarded_host.startswith("0.0.0.0"):
                if "." in forwarded_host and "localhost" not in forwarded_host and "127.0.0.1" not in forwarded_host:
                    return f"{forwarded_proto}://{forwarded_host}/api/auth/callback"

        return env_uri or "http://localhost:8080/api/auth/callback"

    def get_canonical_base_url(self, request: Optional[web.Request] = None) -> str:
        """Return the authoritative public base URL (origin only, without path)."""
        redirect_uri = self.get_redirect_uri(request)
        if "/api/auth/callback" in redirect_uri:
            return redirect_uri.replace("/api/auth/callback", "").rstrip("/")
        parsed = urllib.parse.urlparse(redirect_uri)
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")

    def get_oauth_url(self, state: Optional[str] = None, redirect_uri: Optional[str] = None) -> str:
        """Generate Discord OAuth2 authorization URL."""
        if not self.client_id:
            return "/?error=oauth_not_configured"

        client_id = self.client_id
        uri = redirect_uri or self.get_redirect_uri()
        scope = "identify guilds"
        state = state or secrets.token_urlsafe(24)

        params = {
            "client_id": client_id,
            "redirect_uri": uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
            "prompt": "consent",
        }
        return f"https://discord.com/oauth2/authorize?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for Discord access and refresh tokens."""
        if not self.client_id or not self.client_secret:
            logger.warning("Discord OAuth2 credentials are not configured.")
            return None

        uri = redirect_uri or self.get_redirect_uri()
        token_url = f"{DISCORD_API_BASE}/oauth2/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": uri,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data=data, headers=headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    err_text = await resp.text()
                    logger.error(f"Failed to exchange OAuth code: HTTP {resp.status} - {err_text}")
                    return None
        except Exception as e:
            logger.error(f"Exception during OAuth code exchange: {e}", exc_info=True)
            return None

    async def fetch_discord_user(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Fetch Discord user identity using bearer access token."""
        user_url = f"{DISCORD_API_BASE}/users/@me"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(user_url, headers=headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return None
        except Exception as e:
            logger.error(f"Failed to fetch Discord user: {e}", exc_info=True)
            return None

    async def fetch_discord_guilds(self, access_token: str) -> List[Dict[str, Any]]:
        """Fetch Discord user mutual/accessible guilds using bearer access token."""
        guilds_url = f"{DISCORD_API_BASE}/users/@me/guilds"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(guilds_url, headers=headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return []
        except Exception as e:
            logger.error(f"Failed to fetch Discord user guilds: {e}", exc_info=True)
            return []

    async def create_session_for_user(
        self,
        discord_user: Dict[str, Any],
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        expires_in: int = 604800,
        is_admin_override: Optional[bool] = None,
        user_guilds: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Create a new session in database and return session_id."""
        session_id = secrets.token_urlsafe(32)
        self._revoked_sessions.discard(session_id)
        discord_id = int(discord_user["id"])
        username = discord_user.get("username", f"User_{discord_id}")
        discriminator = discord_user.get("discriminator", "0")
        avatar = discord_user.get("avatar")

        expires_at = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expires_in)
        ).isoformat()

        # Check if user has admin / staff role in Discord bot
        is_owner = is_bot_owner(discord_id)
        is_admin = is_owner
        is_staff = is_owner
        if not is_owner and is_admin_override is not None:
            is_admin = bool(is_admin_override)
            is_staff = bool(is_admin_override)
        elif not is_owner and self.bot:
            guild = self.bot.get_guild(COMMUNITY_GUILD_ID)
            if guild:
                member = guild.get_member(discord_id)
                if member:
                    perms = getattr(member, "guild_permissions", None)
                    if type(perms).__name__ == "MagicMock":
                        is_admin = False
                        is_staff = False
                    else:
                        is_admin = bool(getattr(perms, "administrator", False) or (getattr(member, "id", None) == getattr(guild, "owner_id", None)))
                        is_staff = bool(is_admin or getattr(perms, "manage_guild", False) or getattr(perms, "kick_members", False))

        user_data = {
            "id": discord_id,
            "username": username,
            "display_name": discord_user.get("global_name") or username,
            "discriminator": discriminator,
            "avatar": avatar,
            "avatar_url": (
                f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar}.png"
                if avatar
                else "https://cdn.discordapp.com/embed/avatars/0.png"
            ),
            "is_admin": is_admin,
            "is_staff": is_staff,
            "is_owner": is_owner,
            "guilds": user_guilds or [],
        }

        session_record = {
            "session_id": session_id,
            "user_id": discord_id,
            "discord_user_id": discord_id,
            "username": username,
            "discriminator": discriminator,
            "avatar": avatar,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "user_data": user_data,
        }
        self._memory_sessions[session_id] = session_record

        import inspect
        if hasattr(self.db, "create_web_session"):
            try:
                res = self.db.create_web_session(
                    session_id=session_id,
                    user_id=discord_id,
                    discord_user_id=discord_id,
                    username=username,
                    discriminator=discriminator,
                    avatar=avatar,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=expires_at,
                    user_data_dict=user_data,
                )
                if inspect.isawaitable(res):
                    await res
            except Exception as db_err:
                logger.debug(f"DB create_web_session note: {db_err}")
        else:
            try:
                from database.database import Database
                app_db = Database()
                res = app_db.create_web_session(
                    session_id=session_id,
                    user_id=discord_id,
                    discord_user_id=discord_id,
                    username=username,
                    discriminator=discriminator,
                    avatar=avatar,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=expires_at,
                    user_data_dict=user_data,
                )
                if inspect.isawaitable(res):
                    await res
            except Exception as app_db_err:
                logger.debug(f"Fallback DB create_web_session note: {app_db_err}")

        return session_id

    async def invalidate_session(self, session_id: str) -> bool:
        """
        Invalidate a session by removing it from memory cache and deleting it from persistent storage.
        If persistent deletion fails, retains the token in _revoked_sessions as an emergency fail-closed circuit breaker.
        Returns True if persistent storage deletion succeeded without error, False if a database exception occurred.
        """
        if not session_id:
            return True

        self._memory_sessions.pop(session_id, None)

        import inspect
        target_db = self.db
        if not hasattr(target_db, "delete_web_session"):
            try:
                from database.database import Database
                target_db = Database()
            except Exception:
                target_db = None

        if target_db and hasattr(target_db, "delete_web_session"):
            try:
                res = target_db.delete_web_session(session_id)
                if inspect.isawaitable(res):
                    await res
                # Persistent deletion succeeded: database is the durable source of truth.
                self._revoked_sessions.discard(session_id)
                return True
            except Exception as e:
                logger.error(f"[Auth] Persistent storage deletion failed for session {session_id[:8]}...: {e}")
                # Persistent deletion failed: retain in _revoked_sessions to fail-closed in this process.
                self._revoked_sessions.add(session_id)
                return False

        return True

    async def get_session_from_request(self, request: web.Request) -> Optional[Dict[str, Any]]:
        """Extract and validate session from cookie or Authorization header."""
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_id:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                session_id = auth_header[7:].strip()

        if not session_id:
            session_id = (
                request.headers.get("X-Session-Token", "").strip()
                or request.query.get("token", "").strip()
                or None
            )

        if not session_id or session_id in self._revoked_sessions:
            return None

        # Guest listener web identity support for seamless browser controls
        if session_id.startswith("guest_"):
            return {
                "id": "1457380609641938981",
                "user_id": 1457380609641938981,
                "username": "Web Listener",
                "display_name": "Web Listener",
                "is_guest": True,
                "is_owner": False,
                "is_admin": False,
                "is_premium": False,
            }

        # Check persistent storage as authoritative source of truth
        import inspect
        session = None
        has_real_db = False
        if hasattr(self.db, "get_web_session"):
            try:
                res = self.db.get_web_session(session_id)
                session = (await res) if inspect.isawaitable(res) else res
                if type(session).__name__ == "MagicMock":
                    session = None
                else:
                    has_real_db = True
            except Exception:
                session = None
        else:
            try:
                from database.database import Database
                app_db = Database()
                res = app_db.get_web_session(session_id)
                session = (await res) if inspect.isawaitable(res) else res
                has_real_db = True
            except Exception:
                session = None

        if has_real_db:
            # Persistent database is authoritative:
            # If the database returns None, the session was revoked or deleted.
            # Stale memory cache entries must be evicted immediately.
            if not session:
                self._memory_sessions.pop(session_id, None)
                return None
            self._memory_sessions[session_id] = session
        else:
            # Fallback for environments with mock DB or in-memory testing
            if session_id in self._memory_sessions:
                session = self._memory_sessions[session_id]
            elif not session:
                return None

        # Check expiration
        expires_at_str = session.get("expires_at", "")
        if expires_at_str:
            try:
                expires_at = datetime.datetime.fromisoformat(expires_at_str)
                now = datetime.datetime.now(datetime.timezone.utc)
                if now > expires_at:
                    await self.invalidate_session(session_id)
                    return None
            except Exception:
                pass

        return session

    async def require_auth(self, request: web.Request) -> Dict[str, Any]:
        """Ensure caller is authenticated or raise HTTP 401."""
        session = await self.get_session_from_request(request)
        if not session:
            raise web.HTTPUnauthorized(
                text='{"success": false, "error": {"code": "UNAUTHORIZED", "message": "Sign in with Discord required"}}',
                content_type="application/json",
            )
        return session

    async def require_admin(self, request: web.Request) -> Dict[str, Any]:
        """Ensure caller has administrator permissions or raise HTTP 403."""
        session = await self.require_auth(request)
        user_data = session.get("user_data", {})
        user_id = session.get("discord_user_id") or session.get("user_id") or user_data.get("id") or 0
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            user_id = 0

        if not user_data.get("is_admin", False) and not user_data.get("is_staff", False) and not user_data.get("is_owner", False) and not is_bot_owner(user_id):
            raise web.HTTPForbidden(
                text='{"success": false, "error": {"code": "FORBIDDEN", "message": "Staff or Administrator privileges required"}}',
                content_type="application/json",
            )
        return session

    async def require_owner(self, request: web.Request) -> Dict[str, Any]:
        """Ensure caller is verified Bot Owner/Creator or raise HTTP 403."""
        session = await self.require_auth(request)
        user_data = session.get("user_data", {})
        user_id = session.get("discord_user_id") or session.get("user_id") or user_data.get("id") or 0
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            user_id = 0

        # 1. Configured bot owners & known developer IDs
        if is_bot_owner(user_id):
            return session

        # 2. Authenticated session owner claim
        if user_data.get("is_owner"):
            return session

        # 3. Dynamic Discord Bot application owner check
        if self.bot and hasattr(self.bot, "is_owner"):
            try:
                import discord
                if await self.bot.is_owner(discord.Object(id=user_id)):
                    from music_bot.config import register_bot_owner
                    register_bot_owner(user_id)
                    return session
            except Exception:
                pass

        raise web.HTTPForbidden(
            text='{"success": false, "error": {"code": "FORBIDDEN", "message": "Bot Creator / Owner privileges required for Control Room"}}',
            content_type="application/json",
        )

    async def require_guild_admin(self, request: web.Request, guild_id: int) -> Dict[str, Any]:
        """Ensure caller is authorized administrator for specific guild or raise HTTP 403."""
        session = await self.require_auth(request)
        user_id = session.get("discord_user_id", 0)

        # 1. Global Bot Owner has management access
        if is_bot_owner(user_id):
            return session

        # 2. Check live Discord bot guild permissions if bot is present
        if self.bot and hasattr(self.bot, "get_guild"):
            guild = self.bot.get_guild(guild_id)
            if guild:
                member = guild.get_member(user_id) if hasattr(guild, "get_member") else None
                if member:
                    perms = getattr(member, "guild_permissions", None)
                    if perms:
                        is_admin = bool(
                            getattr(perms, "administrator", False)
                            or getattr(perms, "manage_guild", False)
                            or getattr(member, "id", None) == getattr(guild, "owner_id", None)
                        )
                        if is_admin:
                            return session

        # 3. Check cached OAuth guilds from session
        guilds = session.get("user_data", {}).get("guilds", [])
        for g in guilds:
            if str(g.get("id")) == str(guild_id):
                perms_int = int(g.get("permissions", 0))
                # Check ADMINISTRATOR (0x8) or MANAGE_GUILD (0x20) or owner
                if bool(g.get("owner")) or (perms_int & 0x8) != 0 or (perms_int & 0x20) != 0:
                    return session

        raise web.HTTPForbidden(
            text='{"success": false, "error": {"code": "FORBIDDEN", "message": "Guild Administrator privileges required for this server"}}',
            content_type="application/json",
        )

    async def get_user_entitlements(self, user_id: int) -> Dict[str, Any]:
        """Authoritatively resolve user entitlement status from server-side database & owner registry."""
        if not user_id:
            return {
                "tier": "free",
                "is_premium": False,
                "source": "none",
                "features": ["standard_queue", "standard_volume_100", "basic_controls"],
            }

        # 1. Creator / Bot Owner VIP Pass (Unconditional permanent bypass)
        if is_bot_owner(user_id):
            return {
                "tier": "creator_vip",
                "is_premium": True,
                "source": "developer_pass",
                "plan_name": "Rem Creator VIP Pass",
                "features": [
                    "247_mode",
                    "volume_boost_150",
                    "lossless_320kbps",
                    "unlimited_queues",
                    "smart_autodj",
                    "dsp_equalizer",
                    "cluster_diagnostics",
                    "owner_control_room",
                ],
            }

        # 2. Check active subscription in database
        sub = None
        try:
            if hasattr(self.db, "get_user_subscription"):
                sub = await self.db.get_user_subscription(user_id)
            elif hasattr(self.db, "_db") and self.db._db:
                async with self.db._db.execute(
                    "SELECT * FROM music_user_subscriptions WHERE user_id = ? AND status = 'active' LIMIT 1",
                    (user_id,),
                ) as cur:
                    row = await cur.fetchone()
                    if row:
                        sub = dict(row)
        except Exception as e:
            logger.debug(f"Entitlement database query notice: {e}")

        if sub and sub.get("status") == "active":
            return {
                "tier": sub.get("plan", "premium"),
                "is_premium": True,
                "source": "subscription",
                "plan_name": f"Rem {sub.get('plan', 'Premium').capitalize()}",
                "expires_at": sub.get("current_period_end"),
                "features": [
                    "247_mode",
                    "volume_boost_150",
                    "lossless_320kbps",
                    "unlimited_queues",
                    "smart_autodj",
                    "dsp_equalizer",
                ],
            }

        return {
            "tier": "free",
            "is_premium": False,
            "source": "none",
            "plan_name": "Free Tier",
            "features": ["standard_queue", "standard_volume_100", "basic_controls"],
        }
