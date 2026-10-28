"""web/routes/home.py — Landing page."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    templates = request.app.state.templates
    ctx = request.app.state.base_context(request)

    # Fetch live stats from your bot's data layer
    # Replace these with real queries to your database / bot instance
    ctx["stats"] = {
        "servers": _get_server_count(),
        "songs_played": _get_songs_played(),
        "users": _get_user_count(),
        "uptime": "99.9%",
    }

    return templates.TemplateResponse("index.html", ctx)


# ── Stub helpers (replace with real data sources) ─────────────────
def _get_server_count() -> int:
    try:
        # Example: return db.query("SELECT COUNT(*) FROM guilds")
        return 0
    except Exception:
        return 0


def _get_songs_played() -> int:
    try:
        return 0
    except Exception:
        return 0


def _get_user_count() -> int:
    try:
        return 0
    except Exception:
        return 0

