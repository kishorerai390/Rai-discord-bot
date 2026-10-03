"""
Rai Community OS — Central Realtime Gateway & Telemetry Event Bus.

Handles:
1. Realtime WebSockets (/api/realtime/ws, /ws/live)
2. Server-Sent Events (/api/realtime/stream)
3. Background telemetry heartbeat (Voice, Music, LFG, Projects, Events, Members)
4. Event broadcasting (PULSE_UPDATED, VOICE_UPDATED, MUSIC_UPDATED, LIVE_SESSION_ADDED, etc.)
5. Diagnostics and health metrics
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from aiohttp import web, WSMsgType

from config import COMMUNITY_GUILD_ID

if TYPE_CHECKING:
    from database.database import Database
    from main import SentinelBot

logger = logging.getLogger("Rai.RealtimeGateway")


def safe_json(data: Any) -> str:
    def default_serializer(o: Any) -> Any:
        if type(o).__name__ == "MagicMock":
            return "mock"
        if isinstance(o, (datetime.datetime, datetime.date)):
            return o.isoformat()
        return str(o)
    return json.dumps(data, default=default_serializer)


class RealtimeGateway:
    """Central gateway for real-time WebSocket and SSE event streaming."""

    _instance: Optional["RealtimeGateway"] = None

    def __init__(self, db: Database, bot: Optional[SentinelBot] = None):
        self.db = db
        self.bot = bot
        self.ws_clients: Set[web.WebSocketResponse] = set()
        self.sse_queues: Set[asyncio.Queue] = set()

        self._heartbeat_task: Optional[asyncio.Task] = None
        self._is_running: bool = False

        self.last_pulse: Dict[str, Any] = {}
        self.last_live_sessions: List[Dict[str, Any]] = []
        self.last_category_counts: Dict[str, Any] = {}

        self.start_time: float = time.time()
        self.total_connections: int = 0
        self.total_events_dispatched: int = 0
        self.dropped_events: int = 0
        self.reconnect_count: int = 0
        self.last_event: Optional[Dict[str, Any]] = None
        self.last_sync_time: Optional[str] = None

        RealtimeGateway._instance = self

    @classmethod
    def get_instance(cls) -> Optional["RealtimeGateway"]:
        return cls._instance

    def set_bot(self, bot: SentinelBot) -> None:
        self.bot = bot

    async def start(self) -> None:
        """Start the background telemetry broadcaster."""
        if self._is_running:
            return
        self._is_running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("✦ Rai Realtime Gateway online (WebSockets + SSE + Event Bus) ✦")

    async def stop(self) -> None:
        """Stop background tasks and close all connections."""
        self._is_running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Close all active WebSockets
        for ws in list(self.ws_clients):
            try:
                await ws.close(code=1001, message=b"Server shutting down")
            except Exception:
                pass
        self.ws_clients.clear()
        self.sse_queues.clear()
        logger.info("Rai Realtime Gateway stopped.")

    async def broadcast(self, event_type: str, data: Any) -> None:
        """Broadcast an event to all connected WebSocket clients and SSE streams."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        envelope = {
            "event": event_type,
            "data": data,
            "timestamp": now_iso,
            "id": str(uuid.uuid4())[:8],
        }
        self.last_event = envelope
        self.total_events_dispatched += 1

        payload_str = safe_json(envelope)

        # 1. Broadcast to WebSockets
        dead_ws = set()
        for ws in list(self.ws_clients):
            if ws.closed:
                dead_ws.add(ws)
                continue
            try:
                await ws.send_str(payload_str)
            except Exception as e:
                logger.debug(f"Error sending to WS client: {e}")
                dead_ws.add(ws)
                self.dropped_events += 1

        for ws in dead_ws:
            self.ws_clients.discard(ws)

        # 2. Broadcast to SSE queues
        dead_sse = set()
        sse_chunk = f"event: {event_type}\ndata: {payload_str}\n\n".encode("utf-8")
        for q in list(self.sse_queues):
            try:
                q.put_nowait(sse_chunk)
            except asyncio.QueueFull:
                self.dropped_events += 1
            except Exception:
                dead_sse.add(q)

        for q in dead_sse:
            self.sse_queues.discard(q)

    async def get_current_snapshot(self) -> Dict[str, Any]:
        """Collect the current single-source-of-truth telemetry snapshot."""
        pulse = await self.collect_pulse_metrics()
        live_sessions = await self.collect_live_sessions()
        category_counts = await self.collect_category_counts()
        recent_activity = await self.collect_recent_activity(limit=8)

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.last_sync_time = now_iso

        return {
            "pulse": pulse,
            "live_sessions": live_sessions,
            "category_counts": category_counts,
            "recent_activity": recent_activity,
            "server_time": now_iso,
            "gateway_status": "ONLINE",
        }

    async def collect_pulse_metrics(self) -> Dict[str, Any]:
        """Calculates real aggregate heartbeat metrics without inventing numbers."""
        members_online = None
        users_in_voice = None
        voice_rooms_active = None

        if self.bot and hasattr(self.bot, "is_ready") and self.bot.is_ready():
            try:
                guild = self.bot.get_guild(COMMUNITY_GUILD_ID)
                if guild and hasattr(guild, "members"):
                    online_m = [
                        m for m in guild.members
                        if getattr(m, "status", None) and str(m.status) not in ("offline", "invisible")
                    ]
                    members_online = len(online_m)
                    
                    # Voice channels & members
                    vcs = [vc for vc in getattr(guild, "voice_channels", []) if hasattr(vc, "members")]
                    users_in_voice = sum(len(vc.members) for vc in vcs)
                    voice_rooms_active = len([vc for vc in vcs if len(vc.members) > 0])
            except Exception as e:
                logger.debug(f"Bot guild presence telemetry error: {e}")

        # Music listeners & track
        music_listeners = None
        is_music_playing = False
        track_name = None
        if self.bot and hasattr(self.bot, "voice_clients") and self.bot.voice_clients:
            try:
                for vc in self.bot.voice_clients:
                    if hasattr(vc, "is_playing") and vc.is_playing():
                        is_music_playing = True
                        track_name = getattr(vc, "current_title", "Lossless Stream")
                        if hasattr(vc, "channel") and hasattr(vc.channel, "members"):
                            non_bots = [m for m in vc.channel.members if not getattr(m, "bot", False)]
                            music_listeners = (music_listeners or 0) + len(non_bots)
            except Exception as e:
                logger.debug(f"Bot music query error: {e}")

        # Active projects (status = 'active')
        active_projects = 0
        try:
            async with self.db._db.execute("SELECT COUNT(*) FROM projects WHERE status = 'active'") as cur:
                row = await cur.fetchone()
                active_projects = row[0] if row else 0
        except Exception:
            pass

        # Scheduled community events
        live_events = 0
        try:
            async with self.db._db.execute("SELECT COUNT(*) FROM community_events WHERE status = 'scheduled'") as cur:
                row = await cur.fetchone()
                live_events = row[0] if row else 0
        except Exception:
            pass

        # Gaming LFG open squads
        gaming_squads = 0
        gaming_players = 0
        try:
            async with self.db._db.execute("SELECT COUNT(*), SUM(current_players) FROM community_lfg WHERE status = 'OPEN'") as cur:
                row = await cur.fetchone()
                gaming_squads = row[0] if row else 0
                gaming_players = row[1] if (row and row[1]) else 0
        except Exception:
            pass

        # Active creators count
        creators_active = 0
        try:
            async with self.db._db.execute("SELECT COUNT(DISTINCT user_id) FROM creator_portfolios") as cur:
                row = await cur.fetchone()
                creators_active = row[0] if row else 0
        except Exception:
            pass

        # Activity DNA Calculation
        total_act = (users_in_voice or 0) + gaming_players + (music_listeners or 0) + creators_active
        dna = {"voice": 0, "gaming": 0, "music": 0, "creating": 0}
        if total_act > 0:
            if users_in_voice:
                dna["voice"] = round((users_in_voice / total_act) * 100)
            if gaming_players:
                dna["gaming"] = round((gaming_players / total_act) * 100)
            if music_listeners:
                dna["music"] = round((music_listeners / total_act) * 100)
            if creators_active:
                dna["creating"] = round((creators_active / total_act) * 100)

        return {
            "members_online": members_online,
            "users_in_voice": users_in_voice,
            "voice_rooms_active": voice_rooms_active,
            "music_listeners": music_listeners,
            "is_music_playing": is_music_playing,
            "track_name": track_name,
            "gaming_squads": gaming_squads,
            "gaming_players": gaming_players,
            "creators_active": creators_active,
            "active_projects": active_projects,
            "live_events": live_events,
            "dna": dna,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    async def collect_live_sessions(self) -> List[Dict[str, Any]]:
        """Collects real active sessions (Gaming, Music, Voice, Events)."""
        sessions = []

        # 1. Gaming LFG Sessions
        try:
            async with self.db._db.execute(
                "SELECT * FROM community_lfg WHERE status = 'OPEN' ORDER BY id DESC LIMIT 6"
            ) as cur:
                rows = await cur.fetchall()
            for r in rows:
                g = dict(r)
                sessions.append({
                    "id": f"lfg_{g['id']}",
                    "type": "Gaming Squad",
                    "icon": "🎮",
                    "title": f"{g.get('game_name', 'Gaming')}: {g.get('mode', 'Squad')}",
                    "community": "Vora Gaming Realm",
                    "participants": f"{g.get('current_players', 1)}/{g.get('max_players', 4)} players",
                    "participant_count": g.get("current_players", 1),
                    "started_at": g.get("created_at") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "status": "LIVE",
                    "destination": "/gaming",
                    "action_label": "Join Squad",
                })
        except Exception as e:
            logger.debug(f"Live LFG error: {e}")

        # 2. Live Music Playback Session
        if self.bot and hasattr(self.bot, "voice_clients") and self.bot.voice_clients:
            try:
                for vc in self.bot.voice_clients:
                    if hasattr(vc, "is_playing") and vc.is_playing():
                        listeners = len([m for m in getattr(vc.channel, "members", []) if not getattr(m, "bot", False)])
                        sessions.append({
                            "id": "session_music_live",
                            "type": "Listening Party",
                            "icon": "🎧",
                            "title": getattr(vc, "current_title", "Lossless Hi-Fi Audio"),
                            "community": "Nightwave Creative Studio",
                            "participants": f"{max(1, listeners)} listeners",
                            "participant_count": max(1, listeners),
                            "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            "status": "LIVE",
                            "destination": "/music",
                            "action_label": "Tune In",
                        })
            except Exception as e:
                logger.debug(f"Live music error: {e}")

        # 3. Active Voice Rooms (Public Voice with members)
        if self.bot and hasattr(self.bot, "is_ready") and self.bot.is_ready():
            try:
                guild = self.bot.get_guild(COMMUNITY_GUILD_ID)
                if guild:
                    for vc in getattr(guild, "voice_channels", []):
                        m_count = len(getattr(vc, "members", []))
                        # Only show rooms with active users and not private/staff
                        if m_count > 0 and not vc.name.lower().startswith(("[private]", "staff", "mod-")):
                            sessions.append({
                                "id": f"vc_{vc.id}",
                                "type": "Community Voice",
                                "icon": "🎙️",
                                "title": vc.name,
                                "community": guild.name,
                                "participants": f"{m_count} participants",
                                "participant_count": m_count,
                                "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                "status": "LIVE",
                                "destination": "/communities",
                                "action_label": "Join Voice",
                            })
            except Exception as e:
                logger.debug(f"Live voice error: {e}")

        return sessions

    async def collect_category_counts(self) -> Dict[str, Any]:
        """Collects dynamic counts for category navigation pills."""
        counts = {
            "gaming": 0,
            "music": "Hi-Fi",
            "creators": 0,
            "projects": 0,
            "media": "Watch",
            "events": 0,
            "resources": 0,
        }

        try:
            # Active gaming squads
            async with self.db._db.execute("SELECT COUNT(*) FROM community_lfg WHERE status = 'OPEN'") as cur:
                row = await cur.fetchone()
                counts["gaming"] = f"{row[0]} Live" if (row and row[0] > 0) else "LFG"
        except Exception:
            pass

        try:
            # Active projects
            async with self.db._db.execute("SELECT COUNT(*) FROM projects WHERE status = 'active'") as cur:
                row = await cur.fetchone()
                counts["projects"] = f"{row[0]} Active" if (row and row[0] > 0) else "0 Active"
        except Exception:
            pass

        try:
            # Public creators
            async with self.db._db.execute("SELECT COUNT(DISTINCT user_id) FROM creator_portfolios") as cur:
                row = await cur.fetchone()
                counts["creators"] = f"{row[0]} Active" if (row and row[0] > 0) else "Portfolios"
        except Exception:
            pass

        try:
            # Scheduled events
            async with self.db._db.execute("SELECT COUNT(*) FROM community_events WHERE status = 'scheduled'") as cur:
                row = await cur.fetchone()
                counts["events"] = f"{row[0]} Scheduled" if (row and row[0] > 0) else "Events"
        except Exception:
            pass

        try:
            # Community resources
            async with self.db._db.execute("SELECT COUNT(*) FROM community_resources") as cur:
                row = await cur.fetchone()
                counts["resources"] = f"{row[0]} Items" if (row and row[0] > 0) else "LUTs"
        except Exception:
            pass

        return counts

    async def collect_recent_activity(self, limit: int = 8) -> List[Dict[str, Any]]:
        """Populates the real community activity feed."""
        events = []

        # From community_events / projects / lfg
        try:
            async with self.db._db.execute(
                "SELECT title, game_name, created_at FROM community_lfg ORDER BY id DESC LIMIT ?",
                (limit,)
            ) as cur:
                rows = await cur.fetchall()
            for r in rows:
                events.append({
                    "event_type": "Gaming",
                    "title": f"New squad formed for {r['game_name']}",
                    "icon": "🎮",
                    "badge_color": "pill-green",
                    "created_at": r["created_at"],
                })
        except Exception:
            pass

        try:
            async with self.db._db.execute(
                "SELECT name, project_type, created_at FROM projects ORDER BY id DESC LIMIT ?",
                (limit,)
            ) as cur:
                rows = await cur.fetchall()
            for r in rows:
                events.append({
                    "event_type": "Project",
                    "title": f"Project '{r['name']}' started in {r['project_type'].title()}",
                    "icon": "🚀",
                    "badge_color": "pill-purple",
                    "created_at": r["created_at"],
                })
        except Exception:
            pass

        # Sort combined activity by created_at descending
        events.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return events[:limit]

    async def _heartbeat_loop(self) -> None:
        """Background task that samples state every 4 seconds and pushes diffs."""
        logger.info("Realtime telemetry heartbeat loop running (4s cadence).")
        while self._is_running:
            try:
                await asyncio.sleep(4.0)

                # Collect current metrics
                pulse = await self.collect_pulse_metrics()
                live_sessions = await self.collect_live_sessions()
                category_counts = await self.collect_category_counts()

                # Detect changes in Pulse
                if pulse != self.last_pulse:
                    # Specific sub-metric diff events
                    if pulse.get("users_in_voice") != self.last_pulse.get("users_in_voice"):
                        await self.broadcast("VOICE_UPDATED", {"users_in_voice": pulse.get("users_in_voice")})
                    if pulse.get("members_online") != self.last_pulse.get("members_online"):
                        await self.broadcast("MEMBER_COUNT_UPDATED", {"members_online": pulse.get("members_online")})
                    if pulse.get("is_music_playing") != self.last_pulse.get("is_music_playing") or \
                       pulse.get("music_listeners") != self.last_pulse.get("music_listeners"):
                        await self.broadcast("MUSIC_UPDATED", {
                            "is_music_playing": pulse.get("is_music_playing"),
                            "music_listeners": pulse.get("music_listeners"),
                            "track_name": pulse.get("track_name"),
                        })

                    # Broadcast aggregated PULSE_UPDATED
                    await self.broadcast("PULSE_UPDATED", pulse)
                    self.last_pulse = pulse

                # Detect changes in Live Sessions
                curr_ids = {s["id"] for s in live_sessions}
                prev_ids = {s["id"] for s in self.last_live_sessions}

                if curr_ids != prev_ids:
                    # Sessions added
                    for s in live_sessions:
                        if s["id"] not in prev_ids:
                            await self.broadcast("LIVE_SESSION_ADDED", s)
                    # Sessions removed
                    for s in self.last_live_sessions:
                        if s["id"] not in curr_ids:
                            await self.broadcast("LIVE_SESSION_REMOVED", {"id": s["id"]})

                    await self.broadcast("LIVE_SESSIONS_SYNC", live_sessions)
                    self.last_live_sessions = live_sessions

                # Broadcast Category Counts diff
                if category_counts != self.last_category_counts:
                    await self.broadcast("CATEGORY_COUNTS_UPDATED", category_counts)
                    self.last_category_counts = category_counts

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Error in realtime heartbeat loop: {e}")

    # ==========================================
    # HTTP / WEBSOCKET HANDLERS
    # ==========================================

    async def handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        """Upgrades client connection to a full-duplex WebSocket."""
        ws = web.WebSocketResponse(heartbeat=25.0)
        await ws.prepare(request)

        self.ws_clients.add(ws)
        self.total_connections += 1
        client_ip = request.remote or "unknown"
        logger.debug(f"WebSocket client connected from {client_ip}. Total active: {len(self.ws_clients)}")

        # Send initial full synchronization state
        try:
            snapshot = await self.get_current_snapshot()
            init_envelope = {
                "event": "INIT",
                "data": snapshot,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "id": str(uuid.uuid4())[:8],
            }
            await ws.send_str(safe_json(init_envelope))
        except Exception as e:
            logger.warning(f"Error sending INIT to WS client: {e}")

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        action = data.get("action")
                        if action == "ping":
                            await ws.send_str(safe_json({"event": "PONG", "time": time.time()}))
                        elif action == "sync":
                            snapshot = await self.get_current_snapshot()
                            await ws.send_str(safe_json({"event": "SYNC", "data": snapshot}))
                    except Exception:
                        pass
                elif msg.type == WSMsgType.ERROR:
                    logger.debug(f"WS connection closed with exception: {ws.exception()}")
        finally:
            self.ws_clients.discard(ws)
            logger.debug(f"WebSocket client disconnected from {client_ip}. Remaining: {len(self.ws_clients)}")

        return ws

    async def handle_sse(self, request: web.Request) -> web.StreamResponse:
        """Centralized Server-Sent Events (SSE) real-time stream fallback."""
        resp = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            },
        )
        await resp.prepare(request)

        queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self.sse_queues.add(queue)
        self.total_connections += 1

        # Send initial synchronization snapshot
        try:
            snapshot = await self.get_current_snapshot()
            init_data = safe_json(snapshot)
            await resp.write(f"event: init\ndata: {init_data}\n\n".encode("utf-8"))
        except Exception as e:
            logger.debug(f"Error sending SSE init: {e}")

        try:
            while True:
                chunk = await queue.get()
                await resp.write(chunk)
        except (asyncio.CancelledError, ConnectionResetError, Exception):
            pass
        finally:
            self.sse_queues.discard(queue)

        return resp

    def get_diagnostics(self) -> Dict[str, Any]:
        """Realtime diagnostics metrics for monitoring and admin telemetry."""
        uptime = round(time.time() - self.start_time, 2)
        return {
            "status": "HEALTHY" if self._is_running else "STOPPED",
            "uptime_seconds": uptime,
            "connected_websocket_clients": len(self.ws_clients),
            "connected_sse_clients": len(self.sse_queues),
            "total_connections_served": self.total_connections,
            "total_events_dispatched": self.total_events_dispatched,
            "dropped_events_count": self.dropped_events,
            "last_sync_time": self.last_sync_time,
            "last_event": self.last_event,
            "heartbeat_interval_sec": 4.0,
            "cache_entries": {
                "has_pulse": bool(self.last_pulse),
                "live_sessions_count": len(self.last_live_sessions),
                "category_counts": bool(self.last_category_counts),
            }
        }
