"""
Voicelink Web – main FastAPI application (web/app.py)
This file sets up the FastAPI app, mounts static files, registers all routers,
and provides shared utilities (templates, session middleware, Jinja2 filters).
Merge or replace web/ui.py with this file as appropriate.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# ── Route imports ──────────────────────────────────────────────────
from web.routes import home, commands, help as help_route, status, auth, dashboard, player
from web.ws.player_ws import router as ws_router

# ── App config ─────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

app = FastAPI(
    title="Voicelink Bot",
    description="Web dashboard for Voicelink Discord music bot",
    version="2.0.0",
    docs_url=None,  # disable swagger in production; change to "/docs" for dev
    redoc_url=None,
)

# ── Middleware ─────────────────────────────────────────────────────
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "change-me-in-production"),
    max_age=7 * 24 * 3600,  # 7 days
    https_only=os.environ.get("ENVIRONMENT", "development") == "production",
)

# ── Static files ───────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# ── Jinja2 templates ───────────────────────────────────────────────
templates = Jinja2Templates(directory=BASE_DIR / "templates")

def format_number(n: int | float) -> str:
    """Format large numbers with commas: 12345 → '12,345'."""
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)

templates.env.filters["format_number"] = format_number
templates.env.globals["enumerate"] = enumerate
templates.env.globals["now"] = lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

# ── Config exposed to templates ────────────────────────────────────
APP_CONFIG = {
    "CLIENT_ID": os.environ.get("DISCORD_CLIENT_ID", ""),
    "SUPPORT_INVITE": os.environ.get("DISCORD_SUPPORT_INVITE", "https://discord.gg/support"),
    "GITHUB_URL": os.environ.get("GITHUB_URL", "https://github.com"),
    "ENVIRONMENT": os.environ.get("ENVIRONMENT", "development"),
}

# ── Context processor helper ───────────────────────────────────────
def base_context(request: Request) -> dict:
    """Return common context variables injected into every template."""
    return {
        "request": request,
        "config": APP_CONFIG,
        "user": request.session.get("user"),
        "now": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }

# Make base_context available to route modules
app.state.base_context = base_context
app.state.templates = templates

# ── Routers ────────────────────────────────────────────────────────
app.include_router(home.router)
app.include_router(commands.router)
app.include_router(help_route.router)
app.include_router(status.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(player.router)
app.include_router(ws_router)

# ── 404 handler ────────────────────────────────────────────────────
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    ctx = base_context(request)
    return templates.TemplateResponse("404.html", ctx, status_code=404)

# ── Dev server entrypoint ──────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        reload=os.environ.get("ENVIRONMENT", "development") == "development",
        log_level="info",
    )

