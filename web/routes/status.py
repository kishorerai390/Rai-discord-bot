"""web/routes/status.py — System status page."""

from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


def _get_services() -> list[dict]:
    """
    Return live service status. Replace stub values with real health checks
    (e.g., ping Discord API, check Lavalink nodes, query your database).
    """
    return [
        {
            "name": "Discord API",
            "description": "Gateway and REST API connectivity",
            "icon": "fa-brands fa-discord",
            "status": "operational",   # 'operational' | 'degraded' | 'outage'
            "latency": 42,
        },
        {
            "name": "Lavalink Node 1",
            "description": "Primary audio streaming node (US East)",
            "icon": "fa-server",
            "status": "operational",
            "latency": 18,
        },
        {
            "name": "Lavalink Node 2",
            "description": "Backup audio streaming node (EU West)",
            "icon": "fa-server",
            "status": "operational",
            "latency": 55,
        },
        {
            "name": "Spotify Bridge",
            "description": "Spotify → audio source resolver",
            "icon": "fa-brands fa-spotify",
            "status": "operational",
            "latency": None,
        },
        {
            "name": "Web Dashboard",
            "description": "This website and the player WebSocket",
            "icon": "fa-globe",
            "status": "operational",
            "latency": None,
        },
        {
            "name": "Database",
            "description": "User playlists, guild settings, and analytics",
            "icon": "fa-database",
            "status": "operational",
            "latency": 5,
        },
    ]


def _get_uptime_days() -> list[dict]:
    """Return 90-day uptime bar data (percent per day)."""
    import random
    days = []
    for i in range(90):
        pct = 100
        if random.random() < 0.03:   # 3% chance of a blip
            pct = random.randint(80, 99)
        days.append({"date": f"Day -{90 - i}", "pct": pct})
    return days


def _get_incidents() -> list[dict]:
    """Return recent incidents. Hook this up to your incident tracker."""
    return []


def _overall_status(services: list[dict]) -> str:
    statuses = {s["status"] for s in services}
    if "outage"   in statuses: return "outage"
    if "degraded" in statuses: return "degraded"
    return "operational"


@router.get("/status", response_class=HTMLResponse)
async def status_page(request: Request):
    templates = request.app.state.templates
    ctx = request.app.state.base_context(request)

    services   = _get_services()
    uptime_days = _get_uptime_days()
    avg_uptime  = round(sum(d["pct"] for d in uptime_days) / len(uptime_days), 2)

    ctx.update({
        "services":       services,
        "overall_status": _overall_status(services),
        "uptime_days":    uptime_days,
        "overall_uptime": avg_uptime,
        "incidents":      _get_incidents(),
        "stats": {
            "uptime":             f"{avg_uptime}%",
            "discord_latency":    next((s["latency"] for s in services if "Discord" in s["name"] and s["latency"]), "—"),
            "lavalink_latency":   next((s["latency"] for s in services if "Node 1" in s["name"] and s["latency"]), "—"),
        },
        "now": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    })

    return templates.TemplateResponse("status.html", ctx)

