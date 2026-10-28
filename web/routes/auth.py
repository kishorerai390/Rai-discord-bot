"""web/routes/auth.py — Discord OAuth2 login / logout / callback."""

import os
import secrets
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()

DISCORD_API   = "https://discord.com/api/v10"
CLIENT_ID     = os.environ.get("DISCORD_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
REDIRECT_URI  = os.environ.get("DISCORD_REDIRECT_URI", "http://localhost:8080/callback")

SCOPES = "identify guilds"


# ── /login ─────────────────────────────────────────────────────────
@router.get("/login")
async def login(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    params = (
        f"client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={SCOPES.replace(' ', '%20')}"
        f"&state={state}"
    )
    return RedirectResponse(f"https://discord.com/oauth2/authorize?{params}")


# ── /callback ──────────────────────────────────────────────────────
@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    templates = request.app.state.templates
    ctx = request.app.state.base_context(request)

    if error:
        ctx["error"] = f"Discord returned: {error}"
        return templates.TemplateResponse("error.html", ctx, status_code=400)

    if state != request.session.get("oauth_state"):
        ctx["error"] = "Invalid state parameter. Please try again."
        return templates.TemplateResponse("error.html", ctx, status_code=400)

    # Exchange code → token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  REDIRECT_URI,
            },
        )
        if token_resp.status_code != 200:
            ctx["error"] = "Failed to exchange OAuth code. Please try again."
            return templates.TemplateResponse("error.html", ctx, status_code=500)

        token_data = token_resp.json()
        access_token = token_data.get("access_token", "")
        headers = {"Authorization": f"Bearer {access_token}"}

        # Fetch user info
        user_resp = await client.get(f"{DISCORD_API}/users/@me", headers=headers)
        user_data = user_resp.json()

        # Fetch user guilds
        guilds_resp = await client.get(f"{DISCORD_API}/users/@me/guilds", headers=headers)
        guilds_data = guilds_resp.json() if guilds_resp.status_code == 200 else []

    avatar_hash = user_data.get("avatar", "")
    user_id     = user_data.get("id", "")
    avatar_url  = (
        f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.webp?size=128"
        if avatar_hash
        else f"https://cdn.discordapp.com/embed/avatars/{int(user_data.get('discriminator', 0)) % 5}.png"
    )

    request.session["user"] = {
        "id":         user_id,
        "username":   user_data.get("global_name") or user_data.get("username", "Unknown"),
        "avatar_url": avatar_url,
        "guilds":     guilds_data,
    }
    request.session.pop("oauth_state", None)

    return RedirectResponse("/dashboard")


# ── /logout ────────────────────────────────────────────────────────
@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")

