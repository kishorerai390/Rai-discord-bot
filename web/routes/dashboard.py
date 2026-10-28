"""web/routes/dashboard.py — Dashboard page."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    templates = request.app.state.templates
    ctx = request.app.state.base_context(request)
    user = ctx.get("user")

    if not user:
        return templates.TemplateResponse("dashboard.html", ctx)

    # Fetch guilds the user shares with the bot
    user_guilds = user.get("guilds", [])
    bot_guild_ids = _get_bot_guild_ids()

    guilds = []
    for g in user_guilds:
        guilds.append({
            "id":           g["id"],
            "name":         g["name"],
            "icon":         _guild_icon_url(g["id"], g.get("icon")),
            "member_count": 0,   # fetch from bot cache if available
            "has_bot":      g["id"] in bot_guild_ids,
        })
    guilds.sort(key=lambda g: (not g["has_bot"], g["name"].lower()))

    # Active player sessions
    active_players = _get_active_players(bot_guild_ids & {g["id"] for g in user_guilds})

    ctx.update({
        "guilds":          guilds,
        "active_players":  active_players,
        "active_sessions": len(active_players),
        "global_stats": {
            "songs_today":    _songs_played_today(),
            "hours_listened": _hours_listened(user["id"]),
            "saved_tracks":   _saved_tracks(user["id"]),
        },
    })

    return templates.TemplateResponse("dashboard.html", ctx)


# ── Guild-specific dashboard ────────────────────────────────────────
@router.get("/dashboard/guild/{guild_id}", response_class=HTMLResponse)
async def guild_dashboard(request: Request, guild_id: str):
    ctx = request.app.state.base_context(request)
    if not ctx.get("user"):
        return RedirectResponse("/login")
    # For now redirect to player for that guild
    return RedirectResponse(f"/player?guild={guild_id}")


# ── Stubs ──────────────────────────────────────────────────────────
def _get_bot_guild_ids() -> set[str]:
    """Return set of guild IDs where the bot is present. Hook to your bot instance."""
    return set()


def _guild_icon_url(guild_id: str, icon_hash: str | None) -> str:
    if icon_hash:
        ext = "gif" if icon_hash.startswith("a_") else "webp"
        return f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.{ext}?size=64"
    return "/static/img/default-guild.png"


def _get_active_players(guild_ids: set[str]) -> list[dict]:
    """Return active player sessions for the given guild IDs."""
    return []


def _songs_played_today() -> int:
    return 0


def _hours_listened(user_id: str) -> int:
    return 0


def _saved_tracks(user_id: str) -> int:
    return 0

