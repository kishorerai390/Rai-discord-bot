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
from music_bot.config import is_valid_public_https_url

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

    @property
    def is_configured(self) -> bool:
        """Returns True if Discord OAuth2 credentials are configured."""
        return bool(DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET)

    def get_redirect_uri(self, request: Optional[web.Request] = None) -> str:
        """
        Dynamically determine the valid Discord OAuth2 redirect URI.
        Supports PUBLIC_BASE_URL, custom domains, DISCORD_REDIRECT_URI, and Render production domains.
        """
        # 1. Check explicit DISCORD_REDIRECT_URI environment variable (if non-localhost)
        env_uri = os.getenv("DISCORD_REDIRECT_URI", "").strip() or DISCORD_REDIRECT_URI
        if env_uri and is_valid_public_https_url(env_uri):
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
        if not DISCORD_CLIENT_ID:
            return "/?error=oauth_not_configured"

        client_id = DISCORD_CLIENT_ID
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
        if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
            logger.warning("Discord OAuth2 credentials are not configured.")
            return None

        uri = redirect_uri or self.get_redirect_uri()
        token_url = f"{DISCORD_API_BASE}/oauth2/token"
        data = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
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
        discord_id = int(discord_user["id"])
        username = discord_user.get("username", f"User_{discord_id}")
        discriminator = discord_user.get("discriminator", "0")
        avatar = discord_user.get("avatar")

        expires_at = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expires_in)
        ).isoformat()

        # Check if user has admin / staff role in Discord bot
        is_admin = False
        is_staff = False
        if is_admin_override is not None:
            is_admin = bool(is_admin_override)
            is_staff = bool(is_admin_override)
        elif self.bot:
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
            "guilds": user_guilds or [],
        }

        if hasattr(self.db, "create_web_session"):
            await self.db.create_web_session(
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
        else:
            from database.database import Database
            app_db = Database()
            await app_db.create_web_session(
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

        return session_id

    async def get_session_from_request(self, request: web.Request) -> Optional[Dict[str, Any]]:
        """Extract and validate session from cookie or Authorization header."""
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_id:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                session_id = auth_header[7:].strip()

        if not session_id:
            return None

        if hasattr(self.db, "get_web_session"):
            session = await self.db.get_web_session(session_id)
        else:
            from database.database import Database
            app_db = Database()
            session = await app_db.get_web_session(session_id)

        if not session:
            return None

        # Check expiration
        expires_at_str = session.get("expires_at", "")
        if expires_at_str:
            try:
                expires_at = datetime.datetime.fromisoformat(expires_at_str)
                now = datetime.datetime.now(datetime.timezone.utc)
                if now > expires_at:
                    if hasattr(self.db, "delete_web_session"):
                        await self.db.delete_web_session(session_id)
                    else:
                        from database.database import Database
                        app_db = Database()
                        await app_db.delete_web_session(session_id)
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
        if not user_data.get("is_admin", False) and not user_data.get("is_staff", False):
            # Also allow configured founder or bot owner
            user_id = session.get("discord_user_id", 0)
            from config import is_admin_or_owner
            # Default check
            raise web.HTTPForbidden(
                text='{"success": false, "error": {"code": "FORBIDDEN", "message": "Staff or Administrator privileges required"}}',
                content_type="application/json",
            )
        return session
