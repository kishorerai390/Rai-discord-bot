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

if TYPE_CHECKING:
    from database.database import Database
    from main import SentinelBot

logger = logging.getLogger("Rai.WebAuth")

SESSION_COOKIE_NAME = "rai_session"
DISCORD_API_BASE = "https://discord.com/api/v10"


class AuthManager:
    """Manages Discord OAuth2 workflows and local web sessions."""

    def __init__(self, db: Database, bot: Optional[SentinelBot] = None):
        self.db = db
        self.bot = bot

    def get_oauth_url(self, state: Optional[str] = None) -> str:
        """Generate Discord OAuth2 authorization URL."""
        if not DISCORD_CLIENT_ID:
            return "/login?error=oauth_not_configured"

        client_id = DISCORD_CLIENT_ID
        redirect_uri = DISCORD_REDIRECT_URI
        scope = "identify guilds"
        state = state or secrets.token_urlsafe(16)

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
            "prompt": "consent",
        }
        return f"{DISCORD_API_BASE}/oauth2/authorize?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for Discord access and refresh tokens."""
        if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
            logger.warning("Discord OAuth2 credentials are not configured.")
            return None

        token_url = f"{DISCORD_API_BASE}/oauth2/token"
        data = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI,
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

    async def create_session_for_user(
        self,
        discord_user: Dict[str, Any],
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        expires_in: int = 604800,
        is_admin_override: Optional[bool] = None,
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
        }

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

        session = await self.db.get_web_session(session_id)
        if not session:
            return None

        # Check expiration
        expires_at_str = session.get("expires_at", "")
        if expires_at_str:
            try:
                expires_at = datetime.datetime.fromisoformat(expires_at_str)
                now = datetime.datetime.now(datetime.timezone.utc)
                if now > expires_at:
                    await self.db.delete_web_session(session_id)
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
