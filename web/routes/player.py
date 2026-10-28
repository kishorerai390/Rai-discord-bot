"""web/routes/player.py — Player page route."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()


@router.get("/player", response_class=HTMLResponse)
async def player_page(request: Request, guild: str = ""):
    templates = request.app.state.templates
    ctx = request.app.state.base_context(request)
    user = ctx.get("user")

    if not user:
        return templates.TemplateResponse("player.html", ctx)

    # Fetch guild list for the selector
    user_guilds = user.get("guilds", [])
    bot_guild_ids = _get_bot_guild_ids()
    guilds = [
        {"id": g["id"], "name": g["name"]}
        for g in user_guilds if g["id"] in bot_guild_ids
    ]

    # Current player state for the selected guild
    player_state = _get_player_state(guild) if guild else _empty_player()
    ws_host = request.base_url.hostname
    ws_scheme = "wss" if request.url.scheme == "https" else "ws"

    ctx.update({
        "guilds":            guilds,
        "selected_guild_id": guild,
        "player":            player_state,
        "ws_url":            f"{ws_scheme}://{ws_host}/ws/player/{guild}" if guild else "",
    })

    return templates.TemplateResponse("player.html", ctx)


# ── Stubs ──────────────────────────────────────────────────────────
def _get_bot_guild_ids() -> set[str]:
    return set()


def _get_player_state(guild_id: str) -> dict:
    """Fetch player state from your bot instance for the given guild."""
    return _empty_player()


def _empty_player() -> dict:
    return {
        "is_playing":     False,
        "volume":         80,
        "shuffle":        False,
        "loop":           False,
        "progress_pct":   0,
        "position":       "0:00",
        "active_filters": [],
        "current": {
            "title":     "",
            "author":    "",
            "duration":  "0:00",
            "thumbnail": "",
            "source":    "",
            "liked":     False,
        },
        "queue": [],
    }

