"""
web/ws/player_ws.py — WebSocket handler for the real-time music player.

Each WebSocket connection is scoped to a guild (server).
The client sends action messages; the server forwards them to the bot
and broadcasts state changes back to all connected clients for that guild.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Connection manager ─────────────────────────────────────────────
class ConnectionManager:
    """Manage active WebSocket connections keyed by guild_id."""

    def __init__(self):
        # guild_id → set of connected WebSocket clients
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, guild_id: str, ws: WebSocket):
        await ws.accept()
        self._connections[guild_id].add(ws)
        logger.info("WS connect: guild=%s total=%d", guild_id, len(self._connections[guild_id]))

    def disconnect(self, guild_id: str, ws: WebSocket):
        self._connections[guild_id].discard(ws)
        if not self._connections[guild_id]:
            del self._connections[guild_id]
        logger.info("WS disconnect: guild=%s", guild_id)

    async def broadcast(self, guild_id: str, data: dict):
        """Send a message to all clients connected to a guild."""
        dead: list[WebSocket] = []
        for ws in self._connections.get(guild_id, set()):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(guild_id, ws)

    async def send(self, ws: WebSocket, data: dict):
        """Send a message to a single client."""
        try:
            await ws.send_json(data)
        except Exception as e:
            logger.warning("WS send error: %s", e)


manager = ConnectionManager()


# ── WebSocket endpoint ─────────────────────────────────────────────
@router.websocket("/ws/player/{guild_id}")
async def player_ws(ws: WebSocket, guild_id: str):
    await manager.connect(guild_id, ws)

    # Send initial player state to this client
    initial_state = await _fetch_player_state(guild_id)
    await manager.send(ws, {"type": "state", "data": initial_state})

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send(ws, {"type": "error", "message": "Invalid JSON"})
                continue

            await handle_action(guild_id, ws, msg)

    except WebSocketDisconnect:
        manager.disconnect(guild_id, ws)
    except Exception as e:
        logger.error("WS error: %s", e)
        manager.disconnect(guild_id, ws)


# ── Action dispatcher ──────────────────────────────────────────────
async def handle_action(guild_id: str, ws: WebSocket, msg: dict):
    action = msg.get("action", "")

    handlers: dict[str, Any] = {
        "pause_resume": _action_pause_resume,
        "skip":         _action_skip,
        "previous":     _action_previous,
        "seek":         _action_seek,
        "volume":       _action_volume,
        "shuffle":      _action_shuffle,
        "loop":         _action_loop,
        "play":         _action_play,
        "remove":       _action_remove,
        "move":         _action_move,
        "skip_to":      _action_skip_to,
        "clear":        _action_clear,
        "filter":       _action_filter,
        "like":         _action_like,
    }

    handler = handlers.get(action)
    if handler:
        await handler(guild_id, ws, msg)
    else:
        await manager.send(ws, {"type": "error", "message": f"Unknown action: {action}"})


# ── Individual action handlers ─────────────────────────────────────
# Each handler calls the bot layer (replace stubs with real bot calls)
# and then broadcasts the updated state to all guild clients.

async def _action_pause_resume(guild_id: str, ws: WebSocket, msg: dict):
    result = await _bot_command(guild_id, "pause_resume")
    await manager.broadcast(guild_id, {"type": "state", "data": result})


async def _action_skip(guild_id: str, ws: WebSocket, msg: dict):
    result = await _bot_command(guild_id, "skip")
    await manager.broadcast(guild_id, {"type": "state", "data": result})


async def _action_previous(guild_id: str, ws: WebSocket, msg: dict):
    result = await _bot_command(guild_id, "previous")
    await manager.broadcast(guild_id, {"type": "state", "data": result})


async def _action_seek(guild_id: str, ws: WebSocket, msg: dict):
    position = msg.get("position", 0)
    result = await _bot_command(guild_id, "seek", position=position)
    await manager.broadcast(guild_id, {"type": "state", "data": result})


async def _action_volume(guild_id: str, ws: WebSocket, msg: dict):
    value = max(0, min(100, int(msg.get("value", 80))))
    result = await _bot_command(guild_id, "volume", value=value)
    await manager.broadcast(guild_id, {"type": "volume", "data": {"volume": value}})


async def _action_shuffle(guild_id: str, ws: WebSocket, msg: dict):
    result = await _bot_command(guild_id, "shuffle")
    await manager.broadcast(guild_id, {"type": "state", "data": result})


async def _action_loop(guild_id: str, ws: WebSocket, msg: dict):
    result = await _bot_command(guild_id, "loop")
    await manager.broadcast(guild_id, {"type": "state", "data": result})


async def _action_play(guild_id: str, ws: WebSocket, msg: dict):
    query = msg.get("query", "")
    if not query:
        await manager.send(ws, {"type": "error", "message": "No query provided"})
        return
    result = await _bot_command(guild_id, "play", query=query)
    await manager.broadcast(guild_id, {"type": "state", "data": result})


async def _action_remove(guild_id: str, ws: WebSocket, msg: dict):
    index = int(msg.get("index", 0))
    result = await _bot_command(guild_id, "remove", index=index)
    await manager.broadcast(guild_id, {"type": "queue", "data": result.get("queue", [])})


async def _action_move(guild_id: str, ws: WebSocket, msg: dict):
    from_idx = int(msg.get("from", 0))
    to_idx   = int(msg.get("to", 0))
    result = await _bot_command(guild_id, "move", from_idx=from_idx, to_idx=to_idx)
    await manager.broadcast(guild_id, {"type": "queue", "data": result.get("queue", [])})


async def _action_skip_to(guild_id: str, ws: WebSocket, msg: dict):
    index = int(msg.get("index", 0))
    result = await _bot_command(guild_id, "skip_to", index=index)
    await manager.broadcast(guild_id, {"type": "state", "data": result})


async def _action_clear(guild_id: str, ws: WebSocket, msg: dict):
    result = await _bot_command(guild_id, "clear")
    await manager.broadcast(guild_id, {"type": "queue", "data": []})


async def _action_filter(guild_id: str, ws: WebSocket, msg: dict):
    filter_name = msg.get("filter", "")
    result = await _bot_command(guild_id, "filter", filter_name=filter_name)
    await manager.broadcast(guild_id, {
        "type": "filter",
        "data": {"filter": filter_name, "active": result.get("active", False)},
    })


async def _action_like(guild_id: str, ws: WebSocket, msg: dict):
    await _bot_command(guild_id, "like")


# ── Bot integration stubs ──────────────────────────────────────────
async def _fetch_player_state(guild_id: str) -> dict:
    """
    Fetch the current player state from the bot.
    Replace with your actual bot<→>web bridge (shared state, IPC, Redis pub/sub, etc.).
    """
    return {
        "is_playing":     False,
        "volume":         80,
        "shuffle":        False,
        "loop":           False,
        "position":       0,
        "duration":       0,
        "progress_pct":   0,
        "active_filters": [],
        "current_track":  None,
        "queue":          [],
    }


async def _bot_command(guild_id: str, command: str, **kwargs) -> dict:
    """
    Send a command to the bot and return the updated state.
    Replace with your actual IPC mechanism (e.g., asyncio.Queue, Redis, HTTP to bot).
    """
    logger.info("Bot command: guild=%s cmd=%s kwargs=%s", guild_id, command, kwargs)
    # Return the current state (stub)
    return await _fetch_player_state(guild_id)


# ── Bot event broadcaster (call this from your bot code) ───────────
async def broadcast_track_start(guild_id: str, track: dict):
    """Call from your bot when a new track starts."""
    await manager.broadcast(guild_id, {"type": "track_start", "data": track})


async def broadcast_track_end(guild_id: str):
    """Call from your bot when a track ends."""
    await manager.broadcast(guild_id, {"type": "track_end"})


async def broadcast_queue_update(guild_id: str, queue: list):
    """Call from your bot when the queue changes."""
    await manager.broadcast(guild_id, {"type": "queue", "data": queue})


async def broadcast_state(guild_id: str, state: dict):
    """Call from your bot to push a full state update."""
    await manager.broadcast(guild_id, {"type": "state", "data": state})

